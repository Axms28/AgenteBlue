"""
probar_agente.py
Prueba el Agente JIM directamente en la terminal.
Simula una conversación de onboarding completa.

Uso:
    python probar_agente.py
"""

from blue.jim import SesionJIM, procesar_turno, obtener_resumen_sesion

SEPARADOR = "─" * 55


def main():
    print(f"\n{SEPARADOR}")
    print("  Agente Blue — BlueBallon  |  Modo prueba")
    print(f"{SEPARADOR}")
    print("  Escribe 'salir' para terminar la sesión")
    print(f"  Escribe 'resumen' para ver el reporte de RRHH")
    print(f"{SEPARADOR}\n")

    sesion = SesionJIM()

    # Mensaje inicial de JIM (sin input del usuario)
    bienvenida = procesar_turno(
        sesion,
        "Hola, acabo de ingresar a la empresa.",
    )
    print(f"JIM: {bienvenida}\n")

    while True:
        try:
            entrada = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not entrada:
            continue

        if entrada.lower() == "salir":
            print(f"\n{SEPARADOR}")
            print("Sesión terminada.")
            break

        if entrada.lower() == "resumen":
            print(f"\n{SEPARADOR}")
            print("REPORTE PARA RRHH:")
            print(f"{SEPARADOR}")
            print(obtener_resumen_sesion(sesion))
            print(f"{SEPARADOR}\n")
            continue

        respuesta = procesar_turno(sesion, entrada)
        print(f"\nJIM: {respuesta}\n")

    # Mostrar resumen al salir
    if sesion.eventos:
        print(f"\n{SEPARADOR}")
        print("REPORTE FINAL PARA RRHH:")
        print(f"{SEPARADOR}")
        print(obtener_resumen_sesion(sesion))
        print(f"{SEPARADOR}\n")


if __name__ == "__main__":
    main()