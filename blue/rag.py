"""
blue/rag.py
Consulta de contexto relevante desde la base vectorial de Supabase.
"""

import os
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
    respuesta = cliente_openai.embeddings.create(
        model="text-embedding-3-small",
        input=texto.replace("\n", " "),
    )
    return respuesta.data[0].embedding


def buscar_contexto(
    pregunta:      str,
    subsidiaria:   str = "",
    nombre_area:   str = "",
    nombre_puesto: str = "",
    top_k:         int = 4,
) -> str:
    """
    Busca chunks relevantes filtrando por subsidiaria, área y puesto.
    Siempre incluye la información general del Grupo Blue Balloon.
    """
    vector = generar_embedding(pregunta)

    respuesta = cliente_supabase.rpc(
        "buscar_conocimiento_jim",
        {
            "query_vector":  vector,
            "filtro_sub":    subsidiaria,
            "filtro_area":   nombre_area,
            "filtro_puesto": nombre_puesto,
            "top_k":         top_k,
        },
    ).execute()

    chunks = respuesta.data or []
    if not chunks:
        return ""

    return "\n\n---\n\n".join(
        c["contenido"] for c in chunks if c.get("contenido")
    )


def buscar_empleado(nombre: str) -> dict | None:
    respuesta = cliente_supabase.rpc(
        "buscar_empleado",
        {"nombre_busqueda": nombre.strip()},
    ).execute()
    datos = respuesta.data
    return datos[0] if datos else None


def buscar_video_relevante(
    tema:          str,
    subsidiaria:   str = "",
    nombre_area:   str = "",
    nombre_puesto: str = "",
) -> dict | None:
    """
    Busca un video activo relevante.
    Prioridad: área específica → puesto → subsidiaria → bienvenida general.
    """
    # 1. Video del área
    if nombre_area:
        resp = cliente_supabase.table("videos_jim").select("*").eq("activo", True).eq("nombre_area", nombre_area).limit(1).execute()
        if resp.data:
            return resp.data[0]

    # 2. Video del puesto
    if nombre_puesto:
        resp = cliente_supabase.table("videos_jim").select("*").eq("activo", True).eq("nombre_puesto", nombre_puesto).limit(1).execute()
        if resp.data:
            return resp.data[0]

    # 3. Video de la subsidiaria
    if subsidiaria:
        resp = cliente_supabase.table("videos_jim").select("*").eq("activo", True).eq("nombre_area", subsidiaria).limit(1).execute()
        if resp.data:
            return resp.data[0]

    # 4. Video general de bienvenida
    if any(p in tema.lower() for p in ["bienvenida", "empresa", "misión", "visión", "hola", "inicio"]):
        resp = cliente_supabase.table("videos_jim").select("*").eq("activo", True).eq("categoria", "empresa").limit(1).execute()
        if resp.data:
            return resp.data[0]

    return None