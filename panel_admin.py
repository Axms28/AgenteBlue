"""
panel_admin.py
Panel de administración del Agente Blue — Grupo Blue Balloon
"""

import os
import io
import uuid
import time
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

st.set_page_config(page_title="Admin — Agente Blue", page_icon="🤖", layout="wide")

@st.cache_resource
def obtener_clientes():
    openai_key = os.getenv("OPENAI_API_KEY") or st.secrets.get("OPENAI_API_KEY", "")
    supa_url   = os.getenv("SUPABASE_URL")   or st.secrets.get("SUPABASE_URL", "")
    supa_key   = os.getenv("SUPABASE_KEY")   or st.secrets.get("SUPABASE_KEY", "")
    return OpenAI(api_key=openai_key), create_client(supa_url, supa_key)

cliente_openai, cliente_supabase = obtener_clientes()

# ─── Subsidiarias disponibles ─────────────────────────────────────────────────
# Agrega aquí las empresas del grupo — aparecerán en todos los formularios
SUBSIDIARIAS = [
    "Grupo Blue Balloon (general)",
    "JimTech",
    "Green Balloon",
]

# ─── Helpers conocimiento ─────────────────────────────────────────────────────

def obtener_divisor(chunk_size=800, chunk_overlap=100):
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " "],
    )

def generar_embedding(texto):
    return cliente_openai.embeddings.create(
        model="text-embedding-3-small",
        input=texto.replace("\n", " "),
    ).data[0].embedding

def ingestar_texto(contenido, categoria, subsidiaria, nombre_area, nombre_puesto, prioridad, no_dividir=False, chunk_size=800):
    # Si es info general del grupo, subsidiaria queda vacía para que el RAG la incluya siempre
    sub_guardar = "" if subsidiaria == "Grupo Blue Balloon (general)" else subsidiaria
    chunks = [contenido.strip()] if no_dividir else obtener_divisor(chunk_size).split_text(contenido.strip())
    insertados = 0
    for chunk in chunks:
        if len(chunk.strip()) < 30:
            continue
        cliente_supabase.table("conocimiento_jim").insert({
            "contenido":     chunk,
            "vector":        generar_embedding(chunk),
            "categoria":     categoria,
            "subsidiaria":   sub_guardar,
            "nombre_area":   nombre_area or "",
            "nombre_puesto": nombre_puesto or "",
            "prioridad":     prioridad,
        }).execute()
        insertados += 1
        time.sleep(0.1)
    return insertados

def extraer_texto_docx(archivo_bytes):
    from docx import Document
    doc = Document(io.BytesIO(archivo_bytes))
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())

def obtener_conocimiento():
    return cliente_supabase.table("conocimiento_jim").select(
        "id, subsidiaria, categoria, nombre_area, nombre_puesto, prioridad, contenido, creado_en"
    ).order("creado_en", desc=True).execute().data or []

def eliminar_chunk(chunk_id):
    cliente_supabase.table("conocimiento_jim").delete().eq("id", chunk_id).execute()

def eliminar_por_filtro(categoria, subsidiaria="", nombre_area="", nombre_puesto=""):
    q = cliente_supabase.table("conocimiento_jim").delete().eq("categoria", categoria)
    if subsidiaria.strip():
        q = q.eq("subsidiaria", subsidiaria.strip())
    if nombre_area.strip():
        q = q.eq("nombre_area", nombre_area.strip())
    if nombre_puesto.strip():
        q = q.eq("nombre_puesto", nombre_puesto.strip())
    q.execute()

# ─── Helpers empleados ────────────────────────────────────────────────────────

def obtener_empleados():
    return cliente_supabase.table("empleados_jim").select("*").order("creado_en", desc=True).execute().data or []

def registrar_empleado(nombre, apellido, subsidiaria, area, puesto, email, fecha_ingreso):
    sub_guardar = "" if subsidiaria == "Grupo Blue Balloon (general)" else subsidiaria
    cliente_supabase.table("empleados_jim").insert({
        "nombre": nombre.strip(), "apellido": apellido.strip(),
        "subsidiaria": sub_guardar,
        "area": area.strip(), "puesto": puesto.strip(),
        "email": email.strip(), "fecha_ingreso": str(fecha_ingreso), "activo": True,
    }).execute()

def eliminar_empleado(emp_id):
    cliente_supabase.table("empleados_jim").delete().eq("id", emp_id).execute()

def toggle_empleado(emp_id, activo):
    cliente_supabase.table("empleados_jim").update({"activo": activo}).eq("id", emp_id).execute()

# ─── Helpers videos ───────────────────────────────────────────────────────────

BUCKET_VIDEOS = "videos-blue"

def subir_video_supabase(archivo_bytes, extension):
    nombre = f"video_{uuid.uuid4().hex[:10]}.{extension}"
    cliente_supabase.storage.from_(BUCKET_VIDEOS).upload(
        path=nombre, file=archivo_bytes,
        file_options={"content-type": f"video/{extension}"},
    )
    return cliente_supabase.storage.from_(BUCKET_VIDEOS).get_public_url(nombre)

def registrar_video(titulo, descripcion, categoria, subsidiaria, nombre_area, nombre_puesto, url_video):
    sub_guardar = "" if subsidiaria == "Grupo Blue Balloon (general)" else subsidiaria
    cliente_supabase.table("videos_jim").insert({
        "titulo": titulo.strip(), "descripcion": descripcion.strip(),
        "categoria": categoria, "subsidiaria": sub_guardar,
        "nombre_area": nombre_area or "", "nombre_puesto": nombre_puesto or "",
        "url_video": url_video, "activo": True,
    }).execute()

def obtener_videos():
    return cliente_supabase.table("videos_jim").select("*").order("creado_en", desc=True).execute().data or []

def eliminar_video(video_id):
    cliente_supabase.table("videos_jim").delete().eq("id", video_id).execute()

def toggle_video(video_id, activo):
    cliente_supabase.table("videos_jim").update({"activo": activo}).eq("id", video_id).execute()


# ─── UI ──────────────────────────────────────────────────────────────────────

st.title("🤖 Panel de administración — Agente Blue")
st.caption("Grupo Blue Balloon · JimTech · Green Balloon · Gestión de conocimiento, videos y empleados")

with st.expander("ℹ️ ¿Qué es este panel y cómo funciona?", expanded=False):
    st.markdown("""
    Este panel le enseña información al Agente Blue y registra a los empleados nuevos.

    **Estructura del Grupo:**
    Grupo Blue Balloon es la empresa holding. Debajo están las empresas hermanas: JimTech, Green Balloon, etc.
    Cada empresa tiene sus propias áreas y puestos. Blue sabe distinguir entre ellas.

    **¿Qué debes hacer aquí?**
    1. 📚 **Base de conocimiento** → Sube documentos indicando a qué empresa pertenecen.
    2. 🎥 **Videos** → Sube videos de onboarding por empresa y área.
    3. 👥 **Empleados** → Registra a cada empleado indicando su empresa, área y puesto.
    """)

tab_conocimiento, tab_videos, tab_empleados = st.tabs([
    "📚 Base de conocimiento", "🎥 Videos", "👥 Empleados"
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — BASE DE CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════════════════

with tab_conocimiento:

    st.info(
        "**¿Qué es la base de conocimiento?**  \n"
        "Es la memoria de Blue. Todo lo que subas aquí es lo que Blue le dirá a los empleados.  \n"
        "Puedes subir información del Grupo en general, o específica de JimTech, Green Balloon, etc.",
        icon="🧠",
    )

    st.subheader("➕ Agregar nuevo contenido")

    modo = st.radio("Modo de carga",
        ["✍️  Manual (texto)", "📄 Documento Word (.docx)", "📊 Excel (carga masiva)"],
        horizontal=True,
    )

    # ── Selector de empresa (común a todos los modos) ─────────────────────────
    def selector_empresa(key_prefix=""):
        return st.selectbox(
            "¿A qué empresa pertenece este contenido? *",
            SUBSIDIARIAS,
            help="Grupo Blue Balloon (general) = aplica a todas las empresas. JimTech, Green Balloon = solo para esa empresa.",
            key=f"sub_{key_prefix}",
        )

    # ── Manual ───────────────────────────────────────────────────────────────
    if modo == "✍️  Manual (texto)":
        with st.form("form_conocimiento", clear_on_submit=True):
            subsidiaria = st.selectbox(
                "¿A qué empresa pertenece este contenido? *",
                SUBSIDIARIAS,
                help="Selecciona la empresa. Si es información del grupo en general (misión, visión), elige 'Grupo Blue Balloon (general)'.",
            )
            categoria = st.selectbox("Categoría *", ["empresa", "area", "puesto", "politica"],
                format_func=lambda x: {
                    "empresa":  "🏢 Empresa — misión, visión, historia, valores",
                    "area":     "🗂  Área / Departamento",
                    "puesto":   "👤 Puesto / Rol",
                    "politica": "📋 Política / Reglamento",
                }[x],
            )
            col_a, col_b = st.columns(2)
            with col_a:
                nombre_area = st.text_input("Nombre del área (si aplica)", placeholder="Desarrollo, RRHH, Ventas...",
                    help="Deja vacío si el contenido aplica a toda la empresa seleccionada.")
            with col_b:
                nombre_puesto = st.text_input("Nombre del puesto (si aplica)", placeholder="Director General, Analista...",
                    help="Solo si el contenido es específico de un puesto.")
            col_c, col_d = st.columns(2)
            with col_c:
                prioridad = st.select_slider("Prioridad", options=["baja", "media", "alta"], value="alta")
            with col_d:
                chunk_size = st.select_slider("Tamaño de fragmento", options=[300, 500, 800, 1200, 2000], value=800)
            no_dividir = st.checkbox("No dividir (documento corto, menos de 300 palabras)")
            contenido = st.text_area("Contenido *", height=240,
                placeholder="Pega aquí el texto que Blue debe aprender...")
            enviado = st.form_submit_button("⬆️  Guardar en la memoria de Blue", use_container_width=True, type="primary")

        if enviado:
            if not contenido.strip():
                st.error("⚠️ El contenido no puede estar vacío.")
            else:
                with st.spinner("Procesando y guardando..."):
                    n = ingestar_texto(contenido, categoria, subsidiaria, nombre_area, nombre_puesto, prioridad, no_dividir, chunk_size)
                st.success(f"✅ {n} fragmento(s) guardados en la memoria de Blue.")
                st.rerun()

    # ── Word ─────────────────────────────────────────────────────────────────
    elif modo == "📄 Documento Word (.docx)":
        st.success("Sube el archivo Word y Blue extrae el texto automáticamente.", icon="📄")
        col_meta, col_cfg = st.columns(2)
        with col_meta:
            sub_docx = st.selectbox("¿A qué empresa pertenece?", SUBSIDIARIAS, key="sub_docx")
            cat_docx = st.selectbox("Tipo de documento",
                ["empresa", "area", "puesto", "politica"],
                format_func=lambda x: {
                    "empresa": "🏢 Empresa", "area": "🗂  Área",
                    "puesto": "👤 Puesto", "politica": "📋 Política",
                }[x], key="cat_docx",
            )
            area_docx   = st.text_input("Área (si aplica)", key="area_docx")
            puesto_docx = st.text_input("Puesto (si aplica)", key="puesto_docx")
            prio_docx   = st.select_slider("Prioridad", options=["baja", "media", "alta"], value="alta", key="prio_docx")
        with col_cfg:
            chunk_docx  = st.select_slider("Tamaño de fragmento", options=[300, 500, 800, 1200, 2000], value=1200, key="chunk_docx")
            no_div_docx = st.checkbox("No dividir", key="nodiv_docx")

        archivo_docx = st.file_uploader("Arrastra tu archivo .docx aquí", type=["docx"])
        if archivo_docx:
            try:
                texto_extraido = extraer_texto_docx(archivo_docx.read())
                palabras = len(texto_extraido.split())
                st.success(f"✅ '{archivo_docx.name}' leído: {palabras} palabras")
                with st.expander("👁 Vista previa"):
                    st.text(texto_extraido[:2000] + ("..." if len(texto_extraido) > 2000 else ""))
                if st.button("⬆️  Guardar en la memoria de Blue", type="primary", use_container_width=True):
                    with st.spinner("Procesando..."):
                        n = ingestar_texto(texto_extraido, cat_docx, sub_docx, area_docx, puesto_docx, prio_docx, no_div_docx, chunk_docx)
                    st.success(f"✅ {n} fragmento(s) guardados.")
                    st.balloons()
                    st.rerun()
            except Exception as e:
                st.error(f"❌ Error: {e}")

    # ── Excel ─────────────────────────────────────────────────────────────────
    else:
        st.info("Cada fila del Excel es un documento. Descarga la plantilla para ver el formato.", icon="📊")
        st.markdown("""
        | Columna | Descripción | Ejemplo |
        |---|---|---|
        | `subsidiaria` | Empresa del grupo | `JimTech`, `Green Balloon`, vacío = general |
        | `categoria` | Tipo | `empresa`, `area`, `puesto`, `politica` |
        | `nombre_area` | Área | `Desarrollo`, `RRHH` |
        | `nombre_puesto` | Puesto | `Director General` |
        | `prioridad` | Importancia | `alta`, `media`, `baja` |
        | `contenido` | Texto completo | El documento |
        """)
        plantilla = pd.DataFrame([{
            "subsidiaria": "JimTech", "categoria": "area", "nombre_area": "Desarrollo",
            "nombre_puesto": "", "prioridad": "alta", "contenido": "El área de Desarrollo de JimTech...",
        }, {
            "subsidiaria": "", "categoria": "empresa", "nombre_area": "",
            "nombre_puesto": "", "prioridad": "alta", "contenido": "Grupo Blue Balloon es una empresa...",
        }])
        buf = io.BytesIO()
        plantilla.to_excel(buf, index=False)
        st.download_button("⬇️  Descargar plantilla", data=buf.getvalue(),
            file_name="plantilla_conocimiento_blue.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        archivo = st.file_uploader("Sube tu Excel", type=["xlsx"])
        if archivo:
            df = pd.read_excel(archivo)
            if "contenido" not in df.columns:
                st.error("⚠️ Falta la columna `contenido`.")
            else:
                st.dataframe(df, use_container_width=True)
                if st.button("⬆️  Subir todo", type="primary"):
                    total = 0
                    barra = st.progress(0)
                    for i, fila in df.iterrows():
                        barra.progress((i+1)/len(df), text=f"Guardando {i+1}/{len(df)}...")
                        total += ingestar_texto(
                            str(fila.get("contenido", "")),
                            str(fila.get("categoria", "empresa")),
                            str(fila.get("subsidiaria", "")),
                            str(fila.get("nombre_area", "")),
                            str(fila.get("nombre_puesto", "")),
                            str(fila.get("prioridad", "alta")),
                        )
                    barra.empty()
                    st.success(f"✅ {total} fragmento(s) guardados.")
                    st.balloons()
                    st.rerun()

    st.divider()
    st.subheader("🗂 Contenido guardado en la memoria de Blue")
    datos = obtener_conocimiento()

    if not datos:
        st.warning("⚠️ La memoria de Blue está vacía.")
    else:
        col_f1, col_f2, col_borrar = st.columns([2, 2, 2])
        with col_f1:
            cats   = sorted(set(d["categoria"] for d in datos))
            filtro_cat = st.multiselect("Filtrar por categoría", cats, default=cats)
        with col_f2:
            subs   = sorted(set(d.get("subsidiaria", "") or "General" for d in datos))
            filtro_sub = st.multiselect("Filtrar por empresa", subs, default=subs)
        with col_borrar:
            st.write("")
            with st.expander("🗑 Borrado masivo"):
                cat_b = st.selectbox("Categoría", cats, key="cat_borrar")
                sub_b = st.text_input("Empresa (vacío = todas)", key="sub_borrar")
                area_b = st.text_input("Área (vacío = todas)", key="area_borrar")
                st.warning("⚠️ No se puede deshacer.")
                if st.button("🗑 Eliminar", type="secondary"):
                    eliminar_por_filtro(cat_b, sub_b, area_b)
                    st.success("✅ Eliminados.")
                    st.rerun()

        datos_f = [d for d in datos
                   if d["categoria"] in filtro_cat
                   and (d.get("subsidiaria") or "General") in filtro_sub]
        st.caption(f"Mostrando **{len(datos_f)}** de {len(datos)} fragmento(s)")

        for chunk in datos_f:
            sub_label  = chunk.get("subsidiaria") or "General"
            area_label = chunk.get("nombre_puesto") or chunk.get("nombre_area") or ""
            etiqueta   = f"{sub_label} · {area_label}" if area_label else sub_label
            col_txt, col_btn = st.columns([6, 1])
            with col_txt:
                with st.expander(f"[{chunk['categoria'].upper()}] {etiqueta} — ID {chunk['id']}"):
                    st.write(chunk["contenido"])
                    st.caption(f"Prioridad: {chunk['prioridad']} · Guardado: {chunk['creado_en'][:10]}")
            with col_btn:
                st.write("")
                if st.button("🗑", key=f"del_c_{chunk['id']}", help="Eliminar"):
                    eliminar_chunk(chunk["id"])
                    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — VIDEOS
# ══════════════════════════════════════════════════════════════════════════════

with tab_videos:

    st.info(
        "**¿Cómo funcionan los videos?**  \n"
        "Blue los enviará automáticamente por WhatsApp cuando el tema sea relevante.  \n"
        "Puedes subir videos generales del grupo o específicos de cada empresa.",
        icon="🎥",
    )

    st.subheader("➕ Subir nuevo video")

    col_info_vid, col_archivo_vid = st.columns([1, 1])
    with col_info_vid:
        titulo_vid      = st.text_input("Título del video *", placeholder="Bienvenida a JimTech...")
        descripcion_vid = st.text_area("¿Cuándo debe enviarlo Blue?", height=80,
            placeholder="Enviar cuando el empleado pregunte sobre JimTech o al inicio del onboarding...")
        sub_vid = st.selectbox("¿A qué empresa pertenece?", SUBSIDIARIAS, key="sub_vid")
        cat_vid = st.selectbox("Categoría", ["empresa", "area", "puesto", "politica"],
            format_func=lambda x: {"empresa": "🏢 General", "area": "🗂  Área",
                "puesto": "👤 Puesto", "politica": "📋 Política"}[x], key="cat_vid")
        col_va, col_vb = st.columns(2)
        with col_va:
            area_vid  = st.text_input("Área (si aplica)", key="area_vid")
        with col_vb:
            puesto_vid = st.text_input("Puesto (si aplica)", key="puesto_vid")

    with col_archivo_vid:
        st.caption("Formato: MP4, MOV. Límite WhatsApp: **16 MB**")
        archivo_vid = st.file_uploader("Arrastra tu video aquí", type=["mp4", "mov", "avi"])
        if archivo_vid:
            st.video(archivo_vid)
            size_mb = len(archivo_vid.getvalue()) / (1024*1024)
            if size_mb > 16:
                st.warning(f"⚠️ El video pesa {size_mb:.1f} MB. WhatsApp tiene límite de 16 MB.")
            else:
                st.success(f"✅ {size_mb:.1f} MB — listo para subir")

    st.markdown("---")
    if archivo_vid and titulo_vid:
        if st.button("⬆️  Subir video y activar en Blue", type="primary", use_container_width=True):
            with st.spinner("Subiendo video..."):
                try:
                    ext = archivo_vid.name.split(".")[-1].lower()
                    url = subir_video_supabase(archivo_vid.getvalue(), ext)
                    registrar_video(titulo_vid, descripcion_vid, cat_vid, sub_vid, area_vid, puesto_vid, url)
                    st.success(f"✅ '{titulo_vid}' disponible para Blue.")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error: {e}")
    elif archivo_vid and not titulo_vid:
        st.warning("⚠️ Falta el título del video.")

    st.divider()
    st.subheader("🎬 Videos disponibles")
    videos = obtener_videos()

    if not videos:
        st.warning("⚠️ No hay videos registrados.")
    else:
        for vid in videos:
            icono = "🟢" if vid["activo"] else "🔴"
            sub_v = vid.get("subsidiaria") or "General"
            with st.expander(f"{icono} {vid['titulo']} — {sub_v}"):
                col_p, col_m = st.columns([2, 1])
                with col_p:
                    st.video(vid["url_video"])
                with col_m:
                    st.markdown(f"**Empresa:** {sub_v}")
                    if vid.get("descripcion"):
                        st.markdown(f"**Cuándo enviarlo:** {vid['descripcion']}")
                    if vid.get("nombre_area"):
                        st.markdown(f"**Área:** {vid['nombre_area']}")
                    st.caption(f"Subido: {vid['creado_en'][:10]}")
                    col_t, col_d = st.columns(2)
                    with col_t:
                        nuevo = st.toggle("Activo", value=vid["activo"], key=f"tog_v_{vid['id']}")
                        if nuevo != vid["activo"]:
                            toggle_video(vid["id"], nuevo)
                            st.rerun()
                    with col_d:
                        if st.button("🗑 Eliminar", key=f"del_v_{vid['id']}"):
                            eliminar_video(vid["id"])
                            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — EMPLEADOS
# ══════════════════════════════════════════════════════════════════════════════

with tab_empleados:

    st.info(
        "**¿Por qué registrar empleados?**  \n"
        "Cuando el empleado le escriba a Blue y diga su nombre, Blue lo buscará aquí "
        "para saber a qué empresa, área y puesto pertenece y personalizar el onboarding.  \n\n"
        "**Importante:** Registra al empleado ANTES de que inicie su onboarding.",
        icon="👥",
    )

    st.subheader("➕ Registrar empleado")
    modo_emp = st.radio("Modo", ["✍️  Uno por uno", "📊 Varios con Excel"], horizontal=True, key="modo_emp")

    if modo_emp == "✍️  Uno por uno":
        with st.form("form_empleado", clear_on_submit=True):
            # Empresa primero — es lo más importante
            subsidiaria_emp = st.selectbox(
                "Empresa donde trabaja *",
                SUBSIDIARIAS,
                help="Blue usará esto para mostrar información específica de esa empresa.",
            )
            col1, col2 = st.columns(2)
            with col1:
                nombre    = st.text_input("Nombre *", placeholder="Axel",
                    help="El nombre que usará al presentarse con Blue.")
                area_emp  = st.text_input("Área *", placeholder="Desarrollo, RRHH, Ventas...",
                    help="Blue mostrará información específica de esta área.")
                email_emp = st.text_input("Email", placeholder="axel@jimtech.mx")
            with col2:
                apellido   = st.text_input("Apellido", placeholder="García")
                puesto_emp = st.text_input("Puesto *", placeholder="Desarrollador, Analista...",
                    help="Blue explicará las responsabilidades de este puesto.")
                fecha_ing  = st.date_input("Fecha de ingreso")
            enviado_emp = st.form_submit_button("➕  Registrar empleado", use_container_width=True, type="primary")

        if enviado_emp:
            if not nombre.strip():
                st.error("⚠️ El nombre es obligatorio.")
            elif not area_emp.strip():
                st.error("⚠️ El área es obligatoria.")
            elif not puesto_emp.strip():
                st.error("⚠️ El puesto es obligatorio.")
            else:
                registrar_empleado(nombre, apellido, subsidiaria_emp, area_emp, puesto_emp, email_emp, fecha_ing)
                st.success(f"✅ {nombre} {apellido} registrado en {subsidiaria_emp}. Ya puede iniciar su onboarding.")
                st.rerun()

    else:
        st.info("Descarga la plantilla, llénala y súbela.", icon="📊")
        st.markdown("""
        | Columna | Descripción | Ejemplo |
        |---|---|---|
        | `nombre` | Nombre | `Axel` |
        | `apellido` | Apellido | `García` |
        | `subsidiaria` | Empresa del grupo | `JimTech`, `Green Balloon` |
        | `area` | Área | `Desarrollo` |
        | `puesto` | Cargo | `Desarrollador` |
        | `email` | Correo | `axel@jimtech.mx` |
        | `fecha_ingreso` | Fecha inicio | `2026-03-31` |
        """)
        plantilla_emp = pd.DataFrame([{
            "nombre": "Axel", "apellido": "García", "subsidiaria": "JimTech",
            "area": "Desarrollo", "puesto": "Desarrollador",
            "email": "axel@jimtech.mx", "fecha_ingreso": "2026-03-31",
        }, {
            "nombre": "Ana", "apellido": "López", "subsidiaria": "Green Balloon",
            "area": "RRHH", "puesto": "Analista RRHH",
            "email": "ana@greenballoon.mx", "fecha_ingreso": "2026-03-31",
        }])
        buf_emp = io.BytesIO()
        plantilla_emp.to_excel(buf_emp, index=False)
        st.download_button("⬇️  Descargar plantilla", data=buf_emp.getvalue(),
            file_name="plantilla_empleados_blue.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        archivo_emp = st.file_uploader("Sube tu Excel", type=["xlsx"], key="xlsx_emp")
        if archivo_emp:
            df_emp = pd.read_excel(archivo_emp)
            if "nombre" not in df_emp.columns:
                st.error("⚠️ Falta la columna `nombre`.")
            else:
                st.dataframe(df_emp, use_container_width=True)
                if st.button("➕  Registrar todos", type="primary", key="btn_excel_emp"):
                    for _, fila in df_emp.iterrows():
                        registrar_empleado(
                            str(fila.get("nombre", "")), str(fila.get("apellido", "")),
                            str(fila.get("subsidiaria", "")), str(fila.get("area", "")),
                            str(fila.get("puesto", "")), str(fila.get("email", "")),
                            str(fila.get("fecha_ingreso", "")),
                        )
                    st.success(f"✅ {len(df_emp)} empleado(s) registrados.")
                    st.balloons()
                    st.rerun()

    st.divider()
    st.subheader("📋 Empleados registrados")
    empleados = obtener_empleados()

    if not empleados:
        st.warning("⚠️ No hay empleados registrados.")
    else:
        activos = sum(1 for e in empleados if e["activo"])
        st.caption(f"**{activos}** activo(s) · **{len(empleados)-activos}** inactivo(s)")

        for emp in empleados:
            icono = "🟢" if emp["activo"] else "🔴"
            sub_e = emp.get("subsidiaria") or "General"
            col_info, col_tog, col_del = st.columns([5, 1, 1])
            with col_info:
                st.markdown(
                    f"{icono} **{emp['nombre']} {emp['apellido']}** — "
                    f"{sub_e} · {emp['area']} / {emp['puesto']}  \n"
                    f"<small>{emp.get('email') or '—'} · Ingreso: {emp.get('fecha_ingreso','—')}</small>",
                    unsafe_allow_html=True,
                )
            with col_tog:
                nuevo = st.toggle("Activo", value=emp["activo"],
                    key=f"tog_{emp['id']}", label_visibility="collapsed",
                    help="Inactivo = Blue no reconocerá a este empleado.")
                if nuevo != emp["activo"]:
                    toggle_empleado(emp["id"], nuevo)
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_e_{emp['id']}", help="Eliminar"):
                    eliminar_empleado(emp["id"])
                    st.rerun()
            st.divider()