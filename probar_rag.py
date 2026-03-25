from dotenv import load_dotenv
from ingestor_jim import buscar_contexto

load_dotenv()

preguntas = [
    ("¿Cuál es la misión de BlueBallon?", "", ""),
    ("¿Qué hace el área de JimTech?", "JimTech", ""),
    ("¿Cuáles son mis responsabilidades como desarrollador?", "JimTech", "Desarrollador"),
]

for pregunta, area, puesto in preguntas:
    print(f"\n{'─'*50}")
    print(f"Pregunta: {pregunta}")
    chunks = buscar_contexto(pregunta, nombre_area=area, nombre_puesto=puesto)
    for c in chunks:
        print(f"  [{c['similitud']:.2f}] {c['contenido'][:80]}...")