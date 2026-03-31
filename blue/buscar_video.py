# ─── Agregar en blue/rag.py ───────────────────────────────────────────────────
# Copia esta función al final de tu blue/rag.py existente

def buscar_video_relevante(
    tema: str,
    nombre_area: str = "",
    nombre_puesto: str = "",
) -> dict | None:
    """
    Busca un video activo relevante para el tema actual de la conversación.
    Prioriza videos del área/puesto del empleado sobre los generales.
    Retorna el primer video relevante o None si no hay ninguno.
    """
    from supabase import create_client
    import os

    supa = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

    # 1. Buscar video específico del área/puesto
    if nombre_area:
        resp = supa.table("videos_jim").select("*").eq("activo", True).eq("nombre_area", nombre_area).limit(1).execute()
        if resp.data:
            return resp.data[0]

    # 2. Buscar video específico del puesto
    if nombre_puesto:
        resp = supa.table("videos_jim").select("*").eq("activo", True).eq("nombre_puesto", nombre_puesto).limit(1).execute()
        if resp.data:
            return resp.data[0]

    # 3. Buscar video general de empresa (bienvenida)
    if "bienvenida" in tema.lower() or "empresa" in tema.lower() or "misión" in tema.lower():
        resp = supa.table("videos_jim").select("*").eq("activo", True).eq("categoria", "empresa").limit(1).execute()
        if resp.data:
            return resp.data[0]

    return None