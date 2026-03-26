"""
whatsapp/webhook.py
Servidor webhook del Agente Blue — BlueBallon.
Integración con Meta Cloud API (WhatsApp Business).
"""

import os
import uuid
import tempfile
import httpx
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Form, Request, Query
from fastapi.responses import Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from supabase import create_client

from blue.jim import SesionJIM, procesar_turno
from blue.voz import transcribir_audio, texto_a_voz

load_dotenv()

# ─── Configuración ────────────────────────────────────────────────────────────

META_ACCESS_TOKEN   = os.getenv("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
META_VERIFY_TOKEN   = os.getenv("META_VERIFY_TOKEN", "agente_blue_2026")

cliente_supa = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
BUCKET_AUDIO = "audio-blue"

META_API_URL = f"https://graph.facebook.com/v22.0/{META_PHONE_NUMBER_ID}/messages"

# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(title="Agente Blue — Meta WhatsApp")
sesiones: dict[str, SesionJIM] = {}

Path("audio_sesion").mkdir(exist_ok=True)
app.mount("/audio", StaticFiles(directory="audio_sesion"), name="audio")


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "Blue activo 🤖", "sesiones_activas": len(sesiones)}


# ─── Verificación del webhook (Meta lo llama una sola vez al configurar) ──────

@app.get("/webhook")
def normalizar_numero_mx(numero: str) -> str:
    """
    WhatsApp México a veces agrega un '1' extra después del código de país.
    Meta API necesita el formato sin ese '1': 52XXXXXXXXXX (10 dígitos locales)
    """
    # Quitar prefijos si los hay
    numero = numero.replace("whatsapp:", "").replace("+", "").strip()
    
    # Si es número mexicano con el '1' extra: 521XXXXXXXXXX → 52XXXXXXXXXX
    if numero.startswith("521") and len(numero) == 13:
        numero = "52" + numero[3:]
    
    return numero

def verificar_webhook(
    hub_mode:        str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge:   str = Query(None, alias="hub.challenge"),
):
    """
    Meta llama a este endpoint GET para verificar que el webhook es tuyo.
    Debes responder con hub.challenge si el token coincide.
    """
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        print(f"✅ Webhook verificado por Meta")
        return PlainTextResponse(content=hub_challenge)
    print(f"❌ Verificación fallida — token incorrecto")
    return PlainTextResponse(content="Forbidden", status_code=403)


# ─── Webhook principal (Meta envía los mensajes aquí) ────────────────────────

@app.post("/webhook")
async def recibir_mensaje(request: Request):
    """
    Meta envía cada mensaje entrante como JSON a este endpoint.
    """
    data = await request.json()

    try:
        entry    = data["entry"][0]
        changes  = entry["changes"][0]["value"]
        mensajes = changes.get("messages", [])

        if not mensajes:
            return {"status": "ok"}  # notificación de estado, ignorar

        mensaje        = mensajes[0]
        numero_usuario = mensaje["from"]  # ej: "5215574243703"
        numero_usuario = normalizar_numero_mx(numero_usuario)  # ← agregar esta línea
        tipo_mensaje   = mensaje["type"]  # "text" o "audio"

        print(f"\n{'='*40}")
        print(f"📩 Mensaje de: {numero_usuario}")
        print(f"   Tipo: {tipo_mensaje}")

        # ── Sesión ────────────────────────────────────────────────────────────
        if numero_usuario not in sesiones:
            sesiones[numero_usuario] = SesionJIM()
        sesion = sesiones[numero_usuario]

        # ── Obtener texto ─────────────────────────────────────────────────────
        texto_usuario = ""

        if tipo_mensaje == "text":
            texto_usuario = mensaje["text"]["body"]
            print(f"   Texto: '{texto_usuario}'")

        elif tipo_mensaje == "audio":
            audio_id = mensaje["audio"]["id"]
            print(f"   Audio ID: {audio_id}")
            texto_usuario = await descargar_y_transcribir_meta(audio_id)
            print(f"   Transcripción: '{texto_usuario}'")
            if not texto_usuario:
                await enviar_texto_meta(numero_usuario, "No pude escuchar tu mensaje. ¿Puedes intentarlo de nuevo?")
                return {"status": "ok"}

        else:
            await enviar_texto_meta(numero_usuario, "Mándame un mensaje de texto o una nota de voz 🎙")
            return {"status": "ok"}

        # ── Procesar con Blue ─────────────────────────────────────────────────
        print("🤖 Procesando con Blue...")
        respuesta_texto = procesar_turno(sesion, texto_usuario)
        print(f"   Blue: '{respuesta_texto[:100]}...'")

        # ── Generar audio → Supabase → WhatsApp ──────────────────────────────
        try:
            print("🔊 Generando audio...")
            url_audio = generar_y_subir_audio(respuesta_texto)
            print(f"   URL: {url_audio}")
            await enviar_audio_meta(numero_usuario, url_audio, respuesta_texto)
        except Exception as e:
            print(f"⚠️  Error audio: {e} — enviando solo texto")
            await enviar_texto_meta(numero_usuario, respuesta_texto)

    except (KeyError, IndexError) as e:
        print(f"⚠️  Error parseando mensaje: {e}")

    return {"status": "ok"}


# ─── Helpers Meta API ─────────────────────────────────────────────────────────

async def descargar_y_transcribir_meta(audio_id: str) -> str:
    """
    Descarga el audio de Meta usando el audio_id y transcribe con Whisper.
    """
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    carpeta = Path("audio_sesion")
    carpeta.mkdir(exist_ok=True)

    async with httpx.AsyncClient() as cliente:
        # 1. Obtener URL de descarga
        resp_url = await cliente.get(
            f"https://graph.facebook.com/v22.0/{audio_id}",
            headers=headers,
        )
        resp_url.raise_for_status()
        url_descarga = resp_url.json()["url"]

        # 2. Descargar el audio
        resp_audio = await cliente.get(url_descarga, headers=headers)
        resp_audio.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False, dir=carpeta) as tmp:
            tmp.write(resp_audio.content)
            ruta_tmp = Path(tmp.name)

    texto = transcribir_audio(ruta_tmp)
    ruta_tmp.unlink(missing_ok=True)
    return texto


async def enviar_texto_meta(numero: str, texto: str):
    """Envía un mensaje de texto por WhatsApp vía Meta API."""
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":   numero,
        "type": "text",
        "text": {"body": texto[:4096]},
    }
    async with httpx.AsyncClient() as cliente:
        resp = await cliente.post(META_API_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"⚠️  Error enviando texto: {resp.text}")


async def enviar_audio_meta(numero: str, url_audio: str, caption: str = ""):
    """Envía una nota de voz por WhatsApp vía Meta API."""
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":   numero,
        "type": "audio",
        "audio": {"link": url_audio},
    }
    async with httpx.AsyncClient() as cliente:
        resp = await cliente.post(META_API_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"⚠️  Error enviando audio: {resp.text}")
            # Fallback a texto
            await enviar_texto_meta(numero, caption)


# ─── Helpers audio ────────────────────────────────────────────────────────────

def generar_y_subir_audio(texto: str) -> str:
    """
    Genera audio .ogg con OpenAI TTS, sube a Supabase Storage
    y retorna URL pública para Meta API.
    """
    carpeta = Path("audio_sesion")
    carpeta.mkdir(exist_ok=True)

    nombre     = f"blue_{uuid.uuid4().hex[:10]}.ogg"
    ruta_local = carpeta / nombre

    texto_a_voz(texto, ruta_salida=ruta_local)

    with open(ruta_local, "rb") as f:
        cliente_supa.storage.from_(BUCKET_AUDIO).upload(
            path         = nombre,
            file         = f,
            file_options = {"content-type": "audio/ogg"},
        )

    url = cliente_supa.storage.from_(BUCKET_AUDIO).get_public_url(nombre)
    ruta_local.unlink(missing_ok=True)
    return url