"""
whatsapp/webhook.py
Servidor webhook del Agente Blue — BlueBallon.
Integración con Meta Cloud API (WhatsApp Business).
Soporta: texto, audio (STT+TTS), y videos automáticos.
"""

import os
import uuid
import tempfile
import httpx
from pathlib import Path
from dotenv import load_dotenv

from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from supabase import create_client

from blue.jim import SesionJIM, procesar_turno
from blue.voz import transcribir_audio, texto_a_voz
from blue.rag import buscar_video_relevante

load_dotenv()

# ─── Configuración ────────────────────────────────────────────────────────────

META_ACCESS_TOKEN    = os.getenv("META_ACCESS_TOKEN")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID")
META_VERIFY_TOKEN    = os.getenv("META_VERIFY_TOKEN", "agente_blue_2026")

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


# ─── Verificación del webhook ─────────────────────────────────────────────────

@app.get("/webhook")
def verificar_webhook(
    hub_mode:         str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge:    str = Query(None, alias="hub.challenge"),
):
    """Meta llama a este GET una sola vez al configurar el webhook."""
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        print("✅ Webhook verificado por Meta")
        return PlainTextResponse(content=hub_challenge)
    print("❌ Verificación fallida — token incorrecto")
    return PlainTextResponse(content="Forbidden", status_code=403)


# ─── Webhook principal ────────────────────────────────────────────────────────

@app.post("/webhook")
async def recibir_mensaje(request: Request):
    """Meta envía cada mensaje entrante como JSON a este endpoint."""
    data = await request.json()

    try:
        entry    = data["entry"][0]
        changes  = entry["changes"][0]["value"]
        mensajes = changes.get("messages", [])

        if not mensajes:
            return {"status": "ok"}  # notificación de estado, ignorar

        mensaje        = mensajes[0]
        numero_usuario = normalizar_numero_mx(mensaje["from"])
        tipo_mensaje   = mensaje["type"]

        print(f"\n{'='*40}")
        print(f"📩 Mensaje de: {numero_usuario}")
        print(f"   Tipo: {tipo_mensaje}")

        # ── Sesión ────────────────────────────────────────────────────────────
        if numero_usuario not in sesiones:
            sesiones[numero_usuario] = SesionJIM()
        sesion = sesiones[numero_usuario]

        # ── Obtener texto del mensaje ─────────────────────────────────────────
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

        # ── Enviar audio de respuesta ─────────────────────────────────────────
        try:
            print("🔊 Generando audio...")
            url_audio = generar_y_subir_audio(respuesta_texto)
            print(f"   URL audio: {url_audio}")
            await enviar_audio_meta(numero_usuario, url_audio, respuesta_texto)
        except Exception as e:
            print(f"⚠️  Error audio: {e} — enviando solo texto")
            await enviar_texto_meta(numero_usuario, respuesta_texto)

        # ── Enviar video si hay uno relevante ─────────────────────────────────
        area_emp  = sesion.empleado.get("area", "")   if sesion.empleado else ""
        puesto_emp = sesion.empleado.get("puesto", "") if sesion.empleado else ""

        video = buscar_video_relevante(
            tema          = texto_usuario,
            nombre_area   = area_emp,
            nombre_puesto = puesto_emp,
        )

        if video:
            print(f"🎥 Enviando video: '{video['titulo']}'")
            await enviar_video_meta(numero_usuario, video["url_video"], video["titulo"])

    except (KeyError, IndexError) as e:
        print(f"⚠️  Error parseando mensaje: {e}")

    return {"status": "ok"}


# ─── Helpers número ───────────────────────────────────────────────────────────

def normalizar_numero_mx(numero: str) -> str:
    """
    WhatsApp México a veces agrega un '1' extra después del código de país.
    Meta API necesita el formato: 52XXXXXXXXXX (sin el 1 extra).
    Ej: 5215574243703 → 525574243703
    """
    numero = numero.replace("whatsapp:", "").replace("+", "").strip()
    if numero.startswith("521") and len(numero) == 13:
        numero = "52" + numero[3:]
    return numero


# ─── Helpers Meta API ─────────────────────────────────────────────────────────

async def descargar_y_transcribir_meta(audio_id: str) -> str:
    """Descarga el audio de Meta y transcribe con Whisper."""
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    carpeta = Path("audio_sesion")
    carpeta.mkdir(exist_ok=True)

    async with httpx.AsyncClient() as cliente:
        resp_url = await cliente.get(
            f"https://graph.facebook.com/v22.0/{audio_id}",
            headers=headers,
        )
        resp_url.raise_for_status()
        url_descarga = resp_url.json()["url"]

        resp_audio = await cliente.get(url_descarga, headers=headers)
        resp_audio.raise_for_status()

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False, dir=carpeta) as tmp:
            tmp.write(resp_audio.content)
            ruta_tmp = Path(tmp.name)

    texto = transcribir_audio(ruta_tmp)
    ruta_tmp.unlink(missing_ok=True)
    return texto


async def enviar_texto_meta(numero: str, texto: str):
    """Envía un mensaje de texto por WhatsApp."""
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
    """Envía una nota de voz por WhatsApp."""
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
            await enviar_texto_meta(numero, caption)


async def enviar_video_meta(numero: str, url_video: str, caption: str = ""):
    """Envía un video por WhatsApp. Límite: 16 MB."""
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type":  "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to":   numero,
        "type": "video",
        "video": {
            "link":    url_video,
            "caption": caption[:1024],
        },
    }
    async with httpx.AsyncClient() as cliente:
        resp = await cliente.post(META_API_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"⚠️  Error enviando video: {resp.text}")


# ─── Helpers audio ────────────────────────────────────────────────────────────

def generar_y_subir_audio(texto: str) -> str:
    """Genera audio .ogg con OpenAI TTS, sube a Supabase y retorna URL pública."""
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