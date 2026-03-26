"""
agente/rag.py
Consulta de contexto relevante desde la base vectorial de Supabase.
"""

import os
import time
from openai import OpenAI
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

cliente_openai: OpenAI   = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
cliente_supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
)


def generar_embedding(texto: str) -> list[float]:
    """Genera embedding para una consulta de texto."""
    respuesta = cliente_openai.embeddings.create(
        model="text-embedding-3-small",
        input=texto.replace("\n", " "),
    )
    return respuesta.data[0].embedding


def buscar_contexto(
    pregunta: str,
    nombre_area: str = "",
    nombre_puesto: str = "",
    top_k: int = 4,
) -> str:
    """
    Busca los chunks más relevantes para la pregunta del empleado.
    Filtra por área y puesto para personalizar el contexto.
    Retorna el texto concatenado listo para inyectar en el prompt.
    """
    vector = generar_embedding(pregunta)

    respuesta = cliente_supabase.rpc(
        "buscar_conocimiento_jim",
        {
            "query_vector":  vector,
            "filtro_area":   nombre_area,
            "filtro_puesto": nombre_puesto,
            "top_k":         top_k,
        },
    ).execute()

    chunks = respuesta.data or []

    if not chunks:
        return ""

    # Concatenar chunks ordenados por similitud
    contexto = "\n\n---\n\n".join(
        c["contenido"] for c in chunks if c.get("contenido")
    )
    return contexto


def buscar_empleado(nombre: str) -> dict | None:
    """
    Busca un empleado por nombre en la tabla empleados_jim.
    Retorna el dict del empleado o None si no existe.
    """
    respuesta = cliente_supabase.rpc(
        "buscar_empleado",
        {"nombre_busqueda": nombre.strip()},
    ).execute()

    datos = respuesta.data
    if datos:
        return datos[0]
    return None