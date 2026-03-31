"""
panel_admin.py
Panel de administración del Agente Blue — BlueBallon
Gestión de base de conocimiento y empleados sin tocar código.

Uso local:
    streamlit run panel_admin.py

Deploy:
    Subir a GitHub + conectar en share.streamlit.io
"""

import os
import io
import time
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# ─── Configuración de página ──────────────────────────────────────────────────

st.set_page_config(
    page_title="Admin — Agente Blue",
    page_icon="🤖",
    layout="wide",
)

# ─── Clientes ────────────────────────────────────────────────────────────────

@st.cache_resource
def obtener_clientes():
    openai_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", "")
    supa_url   = os.getenv("SUPABASE_URL")   or st.secrets.get("SUPABASE_URL", "")
    supa_key   = os.getenv("SUPABASE_KEY")   or st.secrets.get("SUPABASE_KEY", "")
    openai_c   = OpenAI(api_key=openai_key)
    supabase_c = create_client(supa_url, supa_key)
    return openai_c, supabase_c

cliente_openai, cliente_supabase = obtener_clientes()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def obtener_divisor(chunk_size: int = 800, chunk_overlap: int = 100):
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " "],
    )


def generar_embedding(texto: str) -> list[float]:
    respuesta = cliente_openai.embeddings.create(
        model="text-embedding-3-small",
        input=texto.replace("\n", " "),
    )
    return respuesta.data[0].embedding


def ingestar_texto(
    contenido:     str,
    categoria:     str,
    nombre_area:   str,
    nombre_puesto: str,
    prioridad:     str,
    no_dividir:    bool = False,
    chunk_size:    int  = 800,
) -> int:
    if no_dividir:
        chunks = [contenido.strip()]
    else:
        divisor = obtener_divisor(chunk_size=chunk_size)
        chunks  = divisor.split_text(contenido.strip())

    insertados = 0
    for chunk in chunks:
        if len(chunk.strip()) < 30:
            continue
        vector = generar_embedding(chunk)
        cliente_supabase.table("conocimiento_jim").insert({
            "contenido":     chunk,
            "vector":        vector,
            "categoria":     categoria,
            "nombre_area":   nombre_area or "",
            "nombre_puesto": nombre_puesto or "",
            "prioridad":     prioridad,
        }).execute()
        insertados += 1
        time.sleep(0.1)
    return insertados


def extraer_texto_docx(archivo_bytes: bytes) -> str:
    """Extrae texto limpio de un archivo .docx manteniendo la estructura."""
    from docx import Document
    doc = Document(io.BytesIO(archivo_bytes))
    parrafos = []
    for parrafo in doc.paragraphs:
        texto = parrafo.text.strip()
        if texto:
            parrafos.append(texto)
    return "\n\n".join(parrafos)


def obtener_conocimiento() -> list[dict]:
    resp = (
        cliente_supabase
        .table("conocimiento_jim")
        .select("id, categoria, nombre_area, nombre_puesto, prioridad, contenido, creado_en")
        .order("creado_en", desc=True)
        .execute()
    )
    return resp.data or []


def obtener_empleados() -> list[dict]:
    resp = (
        cliente_supabase
        .table("empleados_jim")
        .select("*")
        .order("creado_en", desc=True)
        .execute()
    )
    return resp.data or []


def registrar_empleado(nombre, apellido, area, puesto, email, fecha_ingreso):
    cliente_supabase.table("empleados_jim").insert({
        "nombre":        nombre.strip(),
        "apellido":      apellido.strip(),
        "area":          area.strip(),
        "puesto":        puesto.strip(),
        "email":         email.strip(),
        "fecha_ingreso": str(fecha_ingreso),
        "activo":        True,
    }).execute()


def eliminar_chunk(chunk_id: int):
    cliente_supabase.table("conocimiento_jim").delete().eq("id", chunk_id).execute()


def eliminar_por_filtro(categoria: str, nombre_area: str = "", nombre_puesto: str = ""):
    """Elimina todos los chunks que coincidan con los filtros dados."""
    query = cliente_supabase.table("conocimiento_jim").delete().eq("categoria", categoria)
    if nombre_area.strip():
        query = query.eq("nombre_area", nombre_area.strip())
    if nombre_puesto.strip():
        query = query.eq("nombre_puesto", nombre_puesto.strip())
    query.execute()


def eliminar_empleado(emp_id: int):
    cliente_supabase.table("empleados_jim").delete().eq("id", emp_id).execute()


def toggle_empleado(emp_id: int, activo: bool):
    cliente_supabase.table("empleados_jim").update({"activo": activo}).eq("id", emp_id).execute()


# ─── UI ──────────────────────────────────────────────────────────────────────

st.title("🤖 Panel de administración — Agente Blue")
st.caption("Grupo Blue Balloon · Gestión de conocimiento y empleados")

tab_conocimiento, tab_empleados = st.tabs(["📚 Base de conocimiento", "👥 Empleados"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — BASE DE CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════════════════

with tab_conocimiento:

    st.subheader("Agregar contenido")

    modo_conocimiento = st.radio(
        "Modo de carga",
        ["✍️  Manual (texto)", "📄 Documento Word (.docx)", "📊 Excel (carga masiva)"],
        horizontal=True,
    )

    # ── Manual ───────────────────────────────────────────────────────────────
    if modo_conocimiento == "✍️  Manual (texto)":

        with st.form("form_conocimiento", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            with col_a:
                categoria = st.selectbox(
                    "Categoría *",
                    ["empresa", "area", "puesto", "politica"],
                    format_func=lambda x: {
                        "empresa":  "🏢 Empresa — misión, visión, valores",
                        "area":     "🗂  Área / Departamento",
                        "puesto":   "👤 Puesto / Rol",
                        "politica": "📋 Política / Reglamento",
                    }[x],
                )
                nombre_area   = st.text_input("Nombre del área", placeholder="JimTech, RRHH, Ventas...")
                nombre_puesto = st.text_input("Nombre del puesto", placeholder="Director General, Desarrollador...")
            with col_b:
                prioridad  = st.select_slider("Prioridad RAG", options=["baja", "media", "alta"], value="alta")
                chunk_size = st.select_slider(
                    "Tamaño de fragmento",
                    options=[300, 500, 800, 1200, 2000],
                    value=800,
                    help="Documentos largos → 800-1200. Textos cortos → 300-500.",
                )
                no_dividir = st.checkbox("No dividir (documento corto, menos de 400 palabras)")

            contenido = st.text_area("Contenido *", height=260,
                placeholder="Pega aquí la información que Blue debe conocer...")
            enviado = st.form_submit_button("⬆️  Subir a la base de conocimiento", use_container_width=True, type="primary")

        if enviado:
            if not contenido.strip():
                st.error("El contenido no puede estar vacío.")
            else:
                with st.spinner("Procesando y generando embeddings..."):
                    n = ingestar_texto(contenido, categoria, nombre_area, nombre_puesto, prioridad, no_dividir, chunk_size)
                st.success(f"✅ {n} fragmento(s) subidos correctamente.")
                st.rerun()

    # ── Word (.docx) ──────────────────────────────────────────────────────────
    elif modo_conocimiento == "📄 Documento Word (.docx)":

        st.info(
            "Sube directamente el archivo Word — Blue extrae el texto automáticamente.  \n"
            "Ideal para: perfiles de puesto, reglamentos, manuales, descripciones de área.",
            icon="📄",
        )

        col_meta, col_cfg = st.columns(2)
        with col_meta:
            cat_docx = st.selectbox(
                "Categoría *",
                ["empresa", "area", "puesto", "politica"],
                format_func=lambda x: {
                    "empresa":  "🏢 Empresa",
                    "area":     "🗂  Área",
                    "puesto":   "👤 Puesto",
                    "politica": "📋 Política",
                }[x],
                key="cat_docx",
            )
            area_docx   = st.text_input("Nombre del área", placeholder="RRHH, JimTech...", key="area_docx")
            puesto_docx = st.text_input("Nombre del puesto", placeholder="Director General, Analista...", key="puesto_docx")
            prio_docx   = st.select_slider("Prioridad", options=["baja", "media", "alta"], value="alta", key="prio_docx")

        with col_cfg:
            chunk_docx = st.select_slider(
                "Tamaño de fragmento",
                options=[300, 500, 800, 1200, 2000],
                value=1200,
                help="Para perfiles de puesto y manuales se recomienda 1200.",
                key="chunk_docx",
            )
            no_div_docx = st.checkbox(
                "No dividir (subir como un solo bloque)",
                value=False,
                key="nodiv_docx",
            )

        archivo_docx = st.file_uploader("Sube tu archivo Word (.docx)", type=["docx"])

        if archivo_docx:
            try:
                texto_extraido = extraer_texto_docx(archivo_docx.read())
                palabras       = len(texto_extraido.split())

                st.success(f"✅ Documento leído: {palabras} palabras extraídas")

                with st.expander("👁 Vista previa del texto extraído"):
                    st.text(texto_extraido[:2000] + ("..." if len(texto_extraido) > 2000 else ""))

                if st.button("⬆️  Ingestar documento en la base de conocimiento", type="primary", use_container_width=True):
                    with st.spinner("Procesando chunks y generando embeddings..."):
                        n = ingestar_texto(
                            texto_extraido, cat_docx, area_docx, puesto_docx,
                            prio_docx, no_div_docx, chunk_docx,
                        )
                    st.success(f"✅ {n} fragmento(s) subidos desde el documento Word.")
                    st.rerun()

            except Exception as e:
                st.error(f"Error leyendo el archivo: {e}")

    # ── Excel masivo ──────────────────────────────────────────────────────────
    else:
        st.info(
            "El Excel debe tener estas columnas:  \n"
            "`categoria` · `nombre_area` · `nombre_puesto` · `prioridad` · `contenido`",
            icon="📋",
        )

        plantilla = pd.DataFrame([{
            "categoria": "area", "nombre_area": "JimTech",
            "nombre_puesto": "", "prioridad": "alta",
            "contenido": "JimTech es el área de desarrollo de software de BlueBallon...",
        }, {
            "categoria": "puesto", "nombre_area": "JimTech",
            "nombre_puesto": "Desarrollador", "prioridad": "alta",
            "contenido": "El Desarrollador es responsable de construir y mantener...",
        }])
        buf = io.BytesIO()
        plantilla.to_excel(buf, index=False)
        st.download_button(
            "⬇️  Descargar plantilla Excel",
            data=buf.getvalue(),
            file_name="plantilla_conocimiento_blue.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        archivo = st.file_uploader("Sube tu Excel (.xlsx)", type=["xlsx"])
        if archivo:
            df = pd.read_excel(archivo)
            if not {"categoria", "contenido"}.issubset(set(df.columns)):
                st.error("Faltan columnas obligatorias: `categoria` y `contenido`.")
            else:
                st.dataframe(df, use_container_width=True)
                st.caption(f"{len(df)} fila(s) detectadas")
                if st.button("⬆️  Subir todo a la base de conocimiento", type="primary"):
                    total = 0
                    barra = st.progress(0, text="Iniciando...")
                    for i, fila in df.iterrows():
                        barra.progress((i + 1) / len(df), text=f"Procesando {i+1}/{len(df)}...")
                        total += ingestar_texto(
                            str(fila.get("contenido", "")),
                            str(fila.get("categoria", "empresa")),
                            str(fila.get("nombre_area", "")),
                            str(fila.get("nombre_puesto", "")),
                            str(fila.get("prioridad", "alta")),
                        )
                    barra.empty()
                    st.success(f"✅ {total} fragmento(s) subidos desde el Excel.")
                    st.rerun()

    st.divider()

    # ── Chunks existentes ─────────────────────────────────────────────────────
    st.subheader("Contenido actual en la base")
    datos = obtener_conocimiento()

    if not datos:
        st.info("La base de conocimiento está vacía.")
    else:
        col_filtro, col_borrar = st.columns([3, 2])

        with col_filtro:
            cats   = sorted(set(d["categoria"] for d in datos))
            filtro = st.multiselect("Filtrar por categoría", cats, default=cats)

        with col_borrar:
            st.write("")
            with st.expander("🗑 Borrado masivo"):
                st.caption("Elimina todos los fragmentos que coincidan con los filtros.")
                cat_borrar    = st.selectbox("Categoría", cats, key="cat_borrar")
                area_borrar   = st.text_input("Área (dejar vacío = todas)", key="area_borrar")
                puesto_borrar = st.text_input("Puesto (dejar vacío = todos)", key="puesto_borrar")
                if st.button("🗑 Eliminar fragmentos", type="secondary"):
                    eliminar_por_filtro(cat_borrar, area_borrar, puesto_borrar)
                    st.success("✅ Fragmentos eliminados.")
                    st.rerun()

        datos_f = [d for d in datos if d["categoria"] in filtro]
        st.caption(f"{len(datos_f)} fragmento(s)")

        for chunk in datos_f:
            etiqueta = chunk.get("nombre_puesto") or chunk.get("nombre_area") or chunk["categoria"]
            col_txt, col_btn = st.columns([6, 1])
            with col_txt:
                with st.expander(f"[{chunk['categoria'].upper()}] {etiqueta} — ID {chunk['id']}"):
                    st.write(chunk["contenido"])
                    st.caption(f"Prioridad: {chunk['prioridad']} · Creado: {chunk['creado_en'][:10]}")
            with col_btn:
                st.write("")
                if st.button("🗑", key=f"del_c_{chunk['id']}", help="Eliminar"):
                    eliminar_chunk(chunk["id"])
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — EMPLEADOS
# ══════════════════════════════════════════════════════════════════════════════

with tab_empleados:

    st.subheader("Registrar empleados")

    modo_empleados = st.radio(
        "Modo de carga",
        ["✍️  Manual (uno por uno)", "📊 Excel (carga masiva)"],
        horizontal=True,
        key="modo_emp",
    )

    # ── Manual ───────────────────────────────────────────────────────────────
    if modo_empleados == "✍️  Manual (uno por uno)":

        with st.form("form_empleado", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nombre    = st.text_input("Nombre *", placeholder="Axel")
                area_emp  = st.text_input("Área *", placeholder="JimTech")
                email_emp = st.text_input("Email", placeholder="axel@blueballon.mx")
            with col2:
                apellido   = st.text_input("Apellido", placeholder="García")
                puesto_emp = st.text_input("Puesto *", placeholder="Desarrollador")
                fecha_ing  = st.date_input("Fecha de ingreso")

            enviado_emp = st.form_submit_button("➕  Registrar empleado", use_container_width=True, type="primary")

        if enviado_emp:
            if not nombre.strip():
                st.error("El nombre es obligatorio.")
            elif not area_emp.strip():
                st.error("El área es obligatoria.")
            elif not puesto_emp.strip():
                st.error("El puesto es obligatorio.")
            else:
                registrar_empleado(nombre, apellido, area_emp, puesto_emp, email_emp, fecha_ing)
                st.success(f"✅ {nombre} {apellido} registrado correctamente.")
                st.rerun()

    # ── Excel masivo ──────────────────────────────────────────────────────────
    else:
        st.info(
            "El Excel debe tener estas columnas:  \n"
            "`nombre` · `apellido` · `area` · `puesto` · `email` · `fecha_ingreso`",
            icon="📋",
        )

        plantilla_emp = pd.DataFrame([{
            "nombre": "Axel", "apellido": "García",
            "area": "JimTech", "puesto": "Desarrollador",
            "email": "axel@blueballon.mx", "fecha_ingreso": "2026-03-24",
        }, {
            "nombre": "Ana", "apellido": "López",
            "area": "RRHH", "puesto": "Analista RRHH",
            "email": "ana@blueballon.mx", "fecha_ingreso": "2026-03-24",
        }])
        buf_emp = io.BytesIO()
        plantilla_emp.to_excel(buf_emp, index=False)
        st.download_button(
            "⬇️  Descargar plantilla Excel",
            data=buf_emp.getvalue(),
            file_name="plantilla_empleados_blue.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        archivo_emp = st.file_uploader("Sube tu Excel (.xlsx)", type=["xlsx"], key="xlsx_emp")
        if archivo_emp:
            df_emp = pd.read_excel(archivo_emp)
            if not {"nombre", "area"}.issubset(set(df_emp.columns)):
                st.error("Faltan columnas obligatorias: `nombre` y `area`.")
            else:
                st.dataframe(df_emp, use_container_width=True)
                st.caption(f"{len(df_emp)} empleado(s) detectados")
                if st.button("➕  Registrar todos", type="primary", key="btn_excel_emp"):
                    for _, fila in df_emp.iterrows():
                        registrar_empleado(
                            str(fila.get("nombre", "")),
                            str(fila.get("apellido", "")),
                            str(fila.get("area", "")),
                            str(fila.get("puesto", "")),
                            str(fila.get("email", "")),
                            str(fila.get("fecha_ingreso", "")),
                        )
                    st.success(f"✅ {len(df_emp)} empleado(s) registrados.")
                    st.rerun()

    st.divider()

    # ── Lista de empleados ────────────────────────────────────────────────────
    st.subheader("Empleados registrados")
    empleados = obtener_empleados()

    if not empleados:
        st.info("No hay empleados registrados aún.")
    else:
        activos = sum(1 for e in empleados if e["activo"])
        st.caption(f"{activos} activo(s) · {len(empleados) - activos} inactivo(s)")

        for emp in empleados:
            icono = "🟢" if emp["activo"] else "🔴"
            col_info, col_toggle, col_del = st.columns([5, 1, 1])

            with col_info:
                st.markdown(
                    f"{icono} **{emp['nombre']} {emp['apellido']}** — "
                    f"{emp['area']} / {emp['puesto']}  \n"
                    f"<small>{emp.get('email') or '—'} · Ingreso: {emp.get('fecha_ingreso', '—')}</small>",
                    unsafe_allow_html=True,
                )
            with col_toggle:
                nuevo_estado = st.toggle(
                    "Activo", value=emp["activo"],
                    key=f"tog_{emp['id']}", label_visibility="collapsed",
                )
                if nuevo_estado != emp["activo"]:
                    toggle_empleado(emp["id"], nuevo_estado)
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_e_{emp['id']}", help="Eliminar"):
                    eliminar_empleado(emp["id"])
                    st.rerun()

            st.divider()