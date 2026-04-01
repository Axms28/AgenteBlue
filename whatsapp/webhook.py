"""
whatsapp/webhook.py
Servidor webhook del Agente Blue — BlueBallon.
Integración con Meta Cloud API (WhatsApp Business).
Soporta: texto, audio (STT+TTS), videos automáticos,
         filtro de echoes y deduplicación de mensajes.
"""

import os
import uuid
import asyncio
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

sesiones:            dict[str, SesionJIM] = {}
mensajes_procesados: set[str]             = set()

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
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        print("✅ Webhook verificado por Meta")
        return PlainTextResponse(content=hub_challenge)
    print("❌ Verificación fallida — token incorrecto")
    return PlainTextResponse(content="Forbidden", status_code=403)


# ─── Webhook principal ────────────────────────────────────────────────────────

@app.post("/webhook")
async def recibir_mensaje(request: Request):
    data = await request.json()

    try:
        entry    = data["entry"][0]
        changes  = entry["changes"][0]["value"]
        mensajes = changes.get("messages", [])

        if not mensajes:
            return {"status": "ok"}

        mensaje = mensajes[0]

        # Filtrar echoes
        if mensaje.get("from") == META_PHONE_NUMBER_ID:
            print("ℹ️  Echo ignorado")
            return {"status": "ok"}

        # Filtrar duplicados
        mensaje_id = mensaje.get("id", "")
        if mensaje_id in mensajes_procesados:
            print(f"ℹ️  Duplicado ignorado: {mensaje_id}")
            return {"status": "ok"}
        mensajes_procesados.add(mensaje_id)

        numero_usuario = normalizar_numero_mx(mensaje["from"])
        tipo_mensaje   = mensaje["type"]

        print(f"\n{'='*40}")
        print(f"📩 Mensaje de: {numero_usuario} | Tipo: {tipo_mensaje}")

        if numero_usuario not in sesiones:
            sesiones[numero_usuario] = SesionJIM()
        sesion = sesiones[numero_usuario]

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

        # Procesar en segundo plano — Meta recibe 200 OK inmediatamente
        asyncio.create_task(procesar_y_responder(numero_usuario, texto_usuario, sesion))

    except (KeyError, IndexError) as e:
        print(f"⚠️  Error parseando mensaje: {e}")

    return {"status": "ok"}


# ─── Procesamiento en segundo plano ──────────────────────────────────────────

async def procesar_y_responder(numero: str, texto: str, sesion: SesionJIM):
    try:
        # 1. Respuesta de Blue
        print("🤖 Procesando con Blue...")
        respuesta_texto = procesar_turno(sesion, texto)
        print(f"   Blue: '{respuesta_texto[:100]}...'")

        # 2. Generar y enviar audio
        try:
            print("🔊 Generando audio...")
            url_audio = generar_y_subir_audio(respuesta_texto)
            print(f"   URL audio: {url_audio}")
            await enviar_audio_meta(numero, url_audio, respuesta_texto)
            print("   ✅ Audio enviado")
        except Exception as e:
            print(f"⚠️  Error audio: {e} — enviando solo texto")
            await enviar_texto_meta(numero, respuesta_texto)
            print("   ✅ Texto enviado como fallback")

        # 3. Buscar y enviar video (SIEMPRE, no solo cuando falla el audio)
        tema_video = sesion.tema_video_pendiente
        area_emp   = sesion.empleado.get("area", "")   if sesion.empleado else ""
        puesto_emp = sesion.empleado.get("puesto", "") if sesion.empleado else ""

        print(f"🔍 Buscando video — tema: '{tema_video}' área: '{area_emp}'")
        video = buscar_video_relevante(tema_video or texto, area_emp, puesto_emp)
        print(f"   Video encontrado: {video['titulo'] if video else 'ninguno'}")

        if video:
            # Solo enviar si no se ha enviado antes en esta sesión
            if video["id"] not in sesion.videos_enviados:
                frase = f"Mira este video sobre {video['titulo'].lower()}, te va a dar más contexto."
                await enviar_texto_meta(numero, frase)
                await asyncio.sleep(1)
                await enviar_video_meta(numero, video["url_video"], video["titulo"])
                print(f"🎥 Video enviado: '{video['titulo']}'")
                sesion.videos_enviados.add(video["id"])
                sesion.tema_video_pendiente = ""
            else:
                print(f"ℹ️  Video '{video['titulo']}' ya enviado en esta sesión")

    except Exception as e:
        print(f"⚠️  Error en procesar_y_responder: {e}")
        await enviar_texto_meta(numero, "Ocurrió un error. Por favor intenta de nuevo.")


# ─── Helpers número ───────────────────────────────────────────────────────────

def normalizar_numero_mx(numero: str) -> str:
    numero = numero.replace("whatsapp:", "").replace("+", "").strip()
    if numero.startswith("521") and len(numero) == 13:
        numero = "52" + numero[3:]
    return numero


# ─── Helpers Meta API ─────────────────────────────────────────────────────────

async def descargar_y_transcribir_meta(audio_id: str) -> str:
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
            await enviar_texto_meta(numero, f"🎥 {caption}\n{url_video}")


# ─── Helper audio ─────────────────────────────────────────────────────────────

def generar_y_subir_audio(texto: str) -> str:
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