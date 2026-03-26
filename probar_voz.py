"""
probar_voz.py
Prueba el Agente Blue con voz real — micrófono + altavoz.

Modos:
  - MODO_VOZ = True  → graba desde micrófono, responde con audio
  - MODO_VOZ = False → modo texto (fallback si no tienes micrófono)

Uso:
    python probar_voz.py
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from blue.jim import SesionJIM, procesar_turno, obtener_resumen_sesion
from blue.voz import transcribir_audio, texto_a_voz, reproducir_audio, grabar_audio

# ─── Configuración ────────────────────────────────────────────────────────────

MODO_VOZ       = True   # False para modo texto puro
SEGUNDOS_GRAB  = 6      # Segundos de grabación por turno
CARPETA_AUDIO  = Path("audio_sesion")
SEPARADOR      = "─" * 55

# ─── Setup ───────────────────────────────────────────────────────────────────

CARPETA_AUDIO.mkdir(exist_ok=True)


def turno_con_voz(sesion: SesionJIM, texto_usuario: str, num_turno: int) -> str:
    """Procesa un turno y genera audio de respuesta."""
    print(f"\n  Tú: {texto_usuario}")

    # Obtener respuesta de Blue
    respuesta = procesar_turno(sesion, texto_usuario)
    print(f"\n  Blue: {respuesta}")

    # Convertir respuesta a audio
    if os.getenv("ELEVENLABS_API_KEY"):
        try:
            ruta_audio = texto_a_voz(
                texto       = respuesta,
                ruta_salida = CARPETA_AUDIO / f"respuesta_{num_turno}.mp3",
            )
            print(f"\n  🔊 Reproduciendo respuesta...")
            reproducir_audio(ruta_audio)
        except Exception as e:
            print(f"\n  ⚠️  TTS no disponible: {e}")
    else:
        print("\n  ℹ️  Agrega ELEVENLABS_API_KEY al .env para escuchar la respuesta en voz.")

    return respuesta


def main():
    print(f"\n{SEPARADOR}")
    print("  Agente Blue — BlueBallon  |  Modo VOZ")
    print(f"{SEPARADOR}")

    if MODO_VOZ:
        print("  🎙  Micrófono activo")
        print(f"  ⏱  {SEGUNDOS_GRAB} segundos por turno")
    else:
        print("  ⌨️  Modo texto (sin micrófono)")

    print("  Escribe/di 'salir' para terminar")
    print(f"{SEPARADOR}\n")

    sesion = SesionJIM()
    num_turno = 0

    # ── Bienvenida inicial de Blue ────────────────────────────────────────────
    print("  Blue pensando...\n")
    num_turno += 1
    turno_con_voz(sesion, "Hola, acabo de ingresar a la empresa.", num_turno)

    # ── Loop conversacional ───────────────────────────────────────────────────
    while True:
        print(f"\n{SEPARADOR}")

        if MODO_VOZ:
            print("  Presiona ENTER para grabar tu mensaje (o escribe algo y ENTER para modo texto)")
            entrada_previa = input("  > ").strip()

            if entrada_previa.lower() == "salir":
                break
            if entrada_previa.lower() == "resumen":
                imprimir_resumen(sesion)
                continue

            if entrada_previa:
                # El usuario escribió algo — usarlo como texto
                texto_usuario = entrada_previa
            else:
                # Grabar desde micrófono
                try:
                    ruta_grabacion = grabar_audio(
                        segundos    = SEGUNDOS_GRAB,
                        ruta_salida = CARPETA_AUDIO / f"entrada_{num_turno + 1}.wav",
                    )
                    print("  Transcribiendo...")
                    texto_usuario = transcribir_audio(ruta_grabacion)

                    if not texto_usuario:
                        print("  ⚠️  No se detectó voz. Intenta de nuevo.")
                        continue

                except Exception as e:
                    print(f"  ❌ Error al grabar: {e}")
                    print("  Escribe tu mensaje en texto:")
                    texto_usuario = input("  > ").strip()

        else:
            # Modo texto puro
            texto_usuario = input("  Tú: ").strip()
            if not texto_usuario:
                continue
            if texto_usuario.lower() == "salir":
                break
            if texto_usuario.lower() == "resumen":
                imprimir_resumen(sesion)
                continue

        num_turno += 1
        turno_con_voz(sesion, texto_usuario, num_turno)

    # ── Resumen final ─────────────────────────────────────────────────────────
    if sesion.eventos:
        imprimir_resumen(sesion)


def imprimir_resumen(sesion: SesionJIM):
    print(f"\n{SEPARADOR}")
    print("  REPORTE PARA RRHH:")
    print(f"{SEPARADOR}")
    print(obtener_resumen_sesion(sesion))
    print(f"{SEPARADOR}\n")


if __name__ == "__main__":
    main()