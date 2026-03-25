"""
panel_admin.py
Panel de administración del Agente JIM — BlueBallon
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
    page_title="Admin — Agente JIM",
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

divisor = RecursiveCharacterTextSplitter(
    chunk_size=300,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " "],
)

# ─── Helpers ─────────────────────────────────────────────────────────────────

def generar_embedding(texto: str) -> list[float]:
    respuesta = cliente_openai.embeddings.create(
        model="text-embedding-3-small",
        input=texto.replace("\n", " "),
    )
    return respuesta.data[0].embedding


def ingestar_texto(contenido, categoria, nombre_area, nombre_puesto, prioridad) -> int:
    chunks = divisor.split_text(contenido.strip())
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


def eliminar_empleado(emp_id: int):
    cliente_supabase.table("empleados_jim").delete().eq("id", emp_id).execute()


def toggle_empleado(emp_id: int, activo: bool):
    cliente_supabase.table("empleados_jim").update({"activo": activo}).eq("id", emp_id).execute()


# ─── UI ──────────────────────────────────────────────────────────────────────

st.title("🤖 Panel de administración — Agente JIM")
st.caption("BlueBallon · Gestión de conocimiento y empleados")

tab_conocimiento, tab_empleados = st.tabs(["📚 Base de conocimiento", "👥 Empleados"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — BASE DE CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════════════════

with tab_conocimiento:

    st.subheader("Agregar contenido")

    modo_conocimiento = st.radio(
        "Modo de carga",
        ["✍️  Manual (un documento)", "📊 Excel (carga masiva)"],
        horizontal=True,
    )

    # ── Manual ──────────────────────────────────────────────────────────────
    if modo_conocimiento == "✍️  Manual (un documento)":

        with st.form("form_conocimiento", clear_on_submit=True):
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
            nombre_puesto = st.text_input("Nombre del puesto", placeholder="Desarrollador, Analista... (solo si es puesto)")
            prioridad     = st.select_slider("Prioridad RAG", options=["baja", "media", "alta"], value="alta")
            contenido     = st.text_area(
                "Contenido *", height=220,
                placeholder="Escribe aquí la información que JIM debe conocer...",
            )
            enviado = st.form_submit_button("⬆️  Subir a la base de conocimiento", use_container_width=True, type="primary")

        if enviado:
            if not contenido.strip():
                st.error("El contenido no puede estar vacío.")
            else:
                with st.spinner("Procesando chunks y generando embeddings..."):
                    n = ingestar_texto(contenido, categoria, nombre_area, nombre_puesto, prioridad)
                st.success(f"✅ {n} fragmento(s) subidos correctamente.")
                st.rerun()

    # ── Excel masivo ─────────────────────────────────────────────────────────
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
            file_name="plantilla_conocimiento_jim.xlsx",
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
        cats   = sorted(set(d["categoria"] for d in datos))
        filtro = st.multiselect("Filtrar por categoría", cats, default=cats)
        datos_f = [d for d in datos if d["categoria"] in filtro]
        st.caption(f"{len(datos_f)} fragmento(s)")

        for chunk in datos_f:
            etiqueta = chunk.get("nombre_area") or chunk.get("nombre_puesto") or chunk["categoria"]
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

    # ── Manual ──────────────────────────────────────────────────────────────
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

    # ── Excel masivo ─────────────────────────────────────────────────────────
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
            file_name="plantilla_empleados_jim.xlsx",
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