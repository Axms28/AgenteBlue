"""
blue/voz.py
Capa de voz del Agente Blue — BlueBallon.

STT: OpenAI Whisper  → convierte audio a texto
TTS: ElevenLabs      → convierte texto a audio (.mp3)
"""

import os
import tempfile
from pathlib import Path

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

cliente_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ─── Configuración ElevenLabs ─────────────────────────────────────────────────

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")

# Voice ID de ElevenLabs — puedes cambiarlo por cualquier voz de tu cuenta.
# "Rachel" es una voz en inglés/español incluida en el plan gratuito.
# Para voces en español busca en: https://elevenlabs.io/voice-library
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")

ELEVENLABS_MODEL = "eleven_multilingual_v2"   # soporta español nativo


# ─── STT: Whisper ─────────────────────────────────────────────────────────────

def transcribir_audio(ruta_audio: str | Path) -> str:
    """
    Transcribe un archivo de audio a texto usando OpenAI Whisper.

    Args:
        ruta_audio: Ruta al archivo de audio (.mp3, .wav, .ogg, .m4a, .webm).

    Returns:
        Texto transcrito. Cadena vacía si falla.
    """
    ruta = Path(ruta_audio)
    if not ruta.exists():
        raise FileNotFoundError(f"Archivo de audio no encontrado: {ruta}")

    with open(ruta, "rb") as archivo_audio:
        transcripcion = cliente_openai.audio.transcriptions.create(
            model    = "whisper-1",
            file     = archivo_audio,
            language = "es",        # forzar español para mayor precisión
        )

    return transcripcion.text.strip()


# ─── TTS: OpenAI TTS ──────────────────────────────────────────────────────────

def texto_a_voz(texto: str, ruta_salida: str | Path | None = None) -> Path:
    """
    Convierte texto a audio usando OpenAI TTS.
    Genera .ogg (opus) — compatible con WhatsApp.
    """
    if ruta_salida is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".ogg", delete=False)
        ruta_salida = Path(tmp.name)
        tmp.close()
    else:
        ruta_salida = Path(ruta_salida)

    respuesta = cliente_openai.audio.speech.create(
        model          = "tts-1",
        voice          = "nova",
        input          = texto,
        response_format = "opus",   # ← formato que acepta WhatsApp
    )

    respuesta.stream_to_file(str(ruta_salida))
    return ruta_salida

# ─── Reproducción local (solo para pruebas en terminal) ──────────────────────

def reproducir_audio(ruta_audio: str | Path):
    """
    Reproduce un archivo de audio en la terminal (Windows / Mac / Linux).
    Solo para pruebas locales — en producción el audio se envía por WhatsApp.
    """
    ruta = str(Path(ruta_audio))
    import platform
    sistema = platform.system()

    if sistema == "Windows":
        import winsound
        # winsound solo soporta .wav — convertimos con pygame si está disponible
        try:
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(ruta)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.wait(100)
        except ImportError:
            # Fallback: abrir con el reproductor predeterminado
            os.startfile(ruta)

    elif sistema == "Darwin":  # macOS
        os.system(f"afplay '{ruta}'")

    else:  # Linux
        os.system(f"mpg123 '{ruta}' 2>/dev/null || ffplay -nodisp -autoexit '{ruta}' 2>/dev/null")


# ─── Grabación desde micrófono (para pruebas locales) ────────────────────────

def grabar_audio(segundos: int = 5, ruta_salida: str | Path | None = None) -> Path:
    """
    Graba audio desde el micrófono por N segundos.
    Requiere: pip install sounddevice soundfile

    Args:
        segundos    : Duración de la grabación.
        ruta_salida : Ruta donde guardar el .wav. Si es None, crea un temporal.

    Returns:
        Path al archivo .wav grabado.
    """
    try:
        import sounddevice as sd
        import soundfile as sf
        import numpy as np
    except ImportError:
        raise ImportError(
            "Para grabar desde micrófono instala:\n"
            "pip install sounddevice soundfile"
        )

    SAMPLE_RATE = 16000  # Whisper funciona mejor a 16kHz

    print(f"  🎙  Grabando {segundos} segundos... habla ahora")
    audio = sd.rec(
        int(segundos * SAMPLE_RATE),
        samplerate = SAMPLE_RATE,
        channels   = 1,
        dtype      = "float32",
    )
    sd.wait()
    print("  ✓  Grabación terminada")

    if ruta_salida is None:
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        ruta_salida = Path(tmp.name)
        tmp.close()
    else:
        ruta_salida = Path(ruta_salida)

    sf.write(str(ruta_salida), audio, SAMPLE_RATE)
    return ruta_salida