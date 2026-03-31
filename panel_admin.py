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
    return OpenAI(api_key=openai_key), create_client(supa_url, supa_key)

cliente_openai, cliente_supabase = obtener_clientes()


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

def ingestar_texto(contenido, categoria, nombre_area, nombre_puesto, prioridad, no_dividir=False, chunk_size=800):
    chunks = [contenido.strip()] if no_dividir else obtener_divisor(chunk_size).split_text(contenido.strip())
    insertados = 0
    for chunk in chunks:
        if len(chunk.strip()) < 30:
            continue
        cliente_supabase.table("conocimiento_jim").insert({
            "contenido": chunk, "vector": generar_embedding(chunk),
            "categoria": categoria, "nombre_area": nombre_area or "",
            "nombre_puesto": nombre_puesto or "", "prioridad": prioridad,
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
        "id, categoria, nombre_area, nombre_puesto, prioridad, contenido, creado_en"
    ).order("creado_en", desc=True).execute().data or []

def eliminar_chunk(chunk_id):
    cliente_supabase.table("conocimiento_jim").delete().eq("id", chunk_id).execute()

def eliminar_por_filtro(categoria, nombre_area="", nombre_puesto=""):
    q = cliente_supabase.table("conocimiento_jim").delete().eq("categoria", categoria)
    if nombre_area.strip():
        q = q.eq("nombre_area", nombre_area.strip())
    if nombre_puesto.strip():
        q = q.eq("nombre_puesto", nombre_puesto.strip())
    q.execute()


# ─── Helpers empleados ────────────────────────────────────────────────────────

def obtener_empleados():
    return cliente_supabase.table("empleados_jim").select("*").order("creado_en", desc=True).execute().data or []

def registrar_empleado(nombre, apellido, area, puesto, email, fecha_ingreso):
    cliente_supabase.table("empleados_jim").insert({
        "nombre": nombre.strip(), "apellido": apellido.strip(),
        "area": area.strip(), "puesto": puesto.strip(),
        "email": email.strip(), "fecha_ingreso": str(fecha_ingreso), "activo": True,
    }).execute()

def eliminar_empleado(emp_id):
    cliente_supabase.table("empleados_jim").delete().eq("id", emp_id).execute()

def toggle_empleado(emp_id, activo):
    cliente_supabase.table("empleados_jim").update({"activo": activo}).eq("id", emp_id).execute()


# ─── Helpers videos ───────────────────────────────────────────────────────────

BUCKET_VIDEOS = "videos-blue"

def subir_video_supabase(archivo_bytes: bytes, extension: str) -> str:
    """Sube el video a Supabase Storage y retorna la URL pública."""
    nombre = f"video_{uuid.uuid4().hex[:10]}.{extension}"
    cliente_supabase.storage.from_(BUCKET_VIDEOS).upload(
        path         = nombre,
        file         = archivo_bytes,
        file_options = {"content-type": f"video/{extension}"},
    )
    return cliente_supabase.storage.from_(BUCKET_VIDEOS).get_public_url(nombre)

def registrar_video(titulo, descripcion, categoria, nombre_area, nombre_puesto, url_video):
    cliente_supabase.table("videos_jim").insert({
        "titulo":        titulo.strip(),
        "descripcion":   descripcion.strip(),
        "categoria":     categoria,
        "nombre_area":   nombre_area or "",
        "nombre_puesto": nombre_puesto or "",
        "url_video":     url_video,
        "activo":        True,
    }).execute()

def obtener_videos():
    return cliente_supabase.table("videos_jim").select("*").order("creado_en", desc=True).execute().data or []

def eliminar_video(video_id):
    cliente_supabase.table("videos_jim").delete().eq("id", video_id).execute()

def toggle_video(video_id, activo):
    cliente_supabase.table("videos_jim").update({"activo": activo}).eq("id", video_id).execute()


# ─── UI ──────────────────────────────────────────────────────────────────────

st.title("🤖 Panel de administración — Agente Blue")
st.caption("Grupo Blue Balloon · Gestión de conocimiento, videos y empleados")

with st.expander("ℹ️ ¿Qué es este panel y cómo funciona?", expanded=False):
    st.markdown("""
    Este panel te permite **enseñarle información al Agente Blue**, **subir videos de onboarding** y **registrar a los empleados nuevos**.

    **¿Cómo aprende Blue?**
    Tú subes la información de la empresa y Blue la guarda en su memoria. Cuando un empleado nuevo le escribe por WhatsApp, Blue responde con información real y personalizada — y puede enviarle videos automáticamente cuando sea relevante.

    **¿Qué debes hacer aquí?**
    1. 📚 **Base de conocimiento** → Sube documentos de la empresa: misión, visión, áreas, puestos, políticas.
    2. 🎥 **Videos** → Sube videos de bienvenida, tutoriales o presentaciones de áreas. Blue los enviará en el momento correcto.
    3. 👥 **Empleados** → Registra a cada persona nueva antes de que empiece su onboarding.
    """)

tab_conocimiento, tab_videos, tab_empleados = st.tabs([
    "📚 Base de conocimiento",
    "🎥 Videos",
    "👥 Empleados",
])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — BASE DE CONOCIMIENTO
# ══════════════════════════════════════════════════════════════════════════════

with tab_conocimiento:

    st.info(
        "**¿Qué es la base de conocimiento?**  \n"
        "Es la memoria de Blue. Todo lo que subas aquí es lo que Blue podrá decirle a los empleados. "
        "Si no está aquí, Blue no lo sabe.",
        icon="🧠",
    )

    st.subheader("➕ Agregar nuevo contenido")

    st.markdown("""
    **Elige cómo quieres subir la información:**
    - **Manual** → Escribes o pegas el texto directamente.
    - **Documento Word** → Subes un .docx y Blue extrae el texto automáticamente.
    - **Excel** → Subes varios documentos a la vez.
    """)

    modo_conocimiento = st.radio(
        "Modo de carga",
        ["✍️  Manual (texto)", "📄 Documento Word (.docx)", "📊 Excel (carga masiva)"],
        horizontal=True,
    )

    if modo_conocimiento == "✍️  Manual (texto)":
        with st.form("form_conocimiento", clear_on_submit=True):
            st.markdown("**1. ¿De qué tipo es este contenido?**")
            st.caption("Esto le dice a Blue en qué contexto usar esta información.")
            categoria = st.selectbox("Categoría *", ["empresa", "area", "puesto", "politica"],
                format_func=lambda x: {
                    "empresa":  "🏢 Empresa — misión, visión, historia, valores",
                    "area":     "🗂  Área / Departamento",
                    "puesto":   "👤 Puesto / Rol",
                    "politica": "📋 Política / Reglamento",
                }[x],
            )
            st.markdown("**2. ¿A qué área y puesto pertenece?**")
            st.caption("Si es información general de la empresa, deja estos campos vacíos.")
            col_a, col_b = st.columns(2)
            with col_a:
                nombre_area = st.text_input("Nombre del área", placeholder="RRHH, JimTech, Ventas...",
                    help="Área específica. Vacío = aplica a toda la empresa.")
            with col_b:
                nombre_puesto = st.text_input("Nombre del puesto (solo si aplica)", placeholder="Director General, Analista...",
                    help="Solo si el contenido es de un puesto en particular.")
            st.markdown("**3. Configuración**")
            col_c, col_d = st.columns(2)
            with col_c:
                prioridad = st.select_slider("Prioridad", options=["baja", "media", "alta"], value="alta",
                    help="Alta = Blue usa esto primero cuando es relevante.")
            with col_d:
                chunk_size = st.select_slider("Tamaño de fragmento", options=[300, 500, 800, 1200, 2000], value=800,
                    help="Documentos largos → 1200-2000. Textos cortos → 300-500.")
            no_dividir = st.checkbox("No dividir (documento corto, menos de 300 palabras)", value=False)
            st.markdown("**4. Pega el contenido aquí**")
            contenido = st.text_area("Contenido *", height=260,
                placeholder="Escribe o pega aquí el texto que quieres que Blue aprenda...")
            enviado = st.form_submit_button("⬆️  Guardar en la memoria de Blue", use_container_width=True, type="primary")

        if enviado:
            if not contenido.strip():
                st.error("⚠️ El contenido no puede estar vacío.")
            else:
                with st.spinner("Guardando en la memoria de Blue..."):
                    n = ingestar_texto(contenido, categoria, nombre_area, nombre_puesto, prioridad, no_dividir, chunk_size)
                st.success(f"✅ ¡Listo! {n} fragmento(s) guardados en la memoria de Blue.")
                st.rerun()

    elif modo_conocimiento == "📄 Documento Word (.docx)":
        st.success(
            "**¿Cómo funciona?**  \n"
            "1. Selecciona el tipo de documento y el área/puesto.  \n"
            "2. Sube el archivo Word (.docx).  \n"
            "3. Verifica la vista previa del texto.  \n"
            "4. Clic en 'Guardar' y listo.",
            icon="📄",
        )
        col_meta, col_cfg = st.columns(2)
        with col_meta:
            st.markdown("**Información del documento**")
            cat_docx = st.selectbox("¿Qué tipo de documento es?",
                ["empresa", "area", "puesto", "politica"],
                format_func=lambda x: {
                    "empresa": "🏢 Información general de la empresa",
                    "area": "🗂  Descripción de un área",
                    "puesto": "👤 Perfil de un puesto",
                    "politica": "📋 Política o reglamento",
                }[x], key="cat_docx",
            )
            area_docx   = st.text_input("¿A qué área pertenece?", placeholder="RRHH, JimTech...", key="area_docx")
            puesto_docx = st.text_input("¿Es el perfil de un puesto?", placeholder="Director General...", key="puesto_docx")
            prio_docx   = st.select_slider("Prioridad", options=["baja", "media", "alta"], value="alta", key="prio_docx")
        with col_cfg:
            st.markdown("**Configuración del procesamiento**")
            chunk_docx  = st.select_slider("Tamaño de fragmento", options=[300, 500, 800, 1200, 2000], value=1200,
                key="chunk_docx", help="Para perfiles de puesto y manuales se recomienda 1200.")
            no_div_docx = st.checkbox("No dividir (documento muy corto)", value=False, key="nodiv_docx")

        archivo_docx = st.file_uploader("Arrastra tu archivo Word (.docx) aquí", type=["docx"],
            help="Solo .docx. Si tienes .doc, ábrelo en Word y guárdalo como .docx.")
        if archivo_docx:
            try:
                texto_extraido = extraer_texto_docx(archivo_docx.read())
                palabras = len(texto_extraido.split())
                st.success(f"✅ '{archivo_docx.name}' leído: **{palabras} palabras** extraídas")
                with st.expander("👁 Ver el texto que se va a guardar"):
                    st.text(texto_extraido[:2000] + ("...\n[El texto continúa]" if len(texto_extraido) > 2000 else ""))
                if st.button("⬆️  Guardar en la memoria de Blue", type="primary", use_container_width=True):
                    with st.spinner(f"Procesando '{archivo_docx.name}'..."):
                        n = ingestar_texto(texto_extraido, cat_docx, area_docx, puesto_docx, prio_docx, no_div_docx, chunk_docx)
                    st.success(f"✅ ¡Listo! '{archivo_docx.name}' guardado en {n} fragmento(s).")
                    st.balloons()
                    st.rerun()
            except Exception as e:
                st.error(f"❌ No se pudo leer el archivo: {e}")

    else:
        st.info("Descarga la plantilla, llénala y súbela aquí.", icon="📊")
        plantilla = pd.DataFrame([{
            "categoria": "area", "nombre_area": "JimTech", "nombre_puesto": "",
            "prioridad": "alta", "contenido": "JimTech es el área de desarrollo...",
        }])
        buf = io.BytesIO()
        plantilla.to_excel(buf, index=False)
        st.download_button("⬇️  Descargar plantilla Excel", data=buf.getvalue(),
            file_name="plantilla_conocimiento_blue.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        archivo = st.file_uploader("Sube tu Excel (.xlsx)", type=["xlsx"])
        if archivo:
            df = pd.read_excel(archivo)
            if not {"categoria", "contenido"}.issubset(set(df.columns)):
                st.error("⚠️ Faltan columnas obligatorias: `categoria` y `contenido`.")
            else:
                st.dataframe(df, use_container_width=True)
                if st.button("⬆️  Subir todo a la memoria de Blue", type="primary"):
                    total = 0
                    barra = st.progress(0)
                    for i, fila in df.iterrows():
                        barra.progress((i + 1) / len(df), text=f"Guardando {i+1}/{len(df)}...")
                        total += ingestar_texto(str(fila.get("contenido", "")), str(fila.get("categoria", "empresa")),
                            str(fila.get("nombre_area", "")), str(fila.get("nombre_puesto", "")), str(fila.get("prioridad", "alta")))
                    barra.empty()
                    st.success(f"✅ {total} fragmento(s) guardados.")
                    st.balloons()
                    st.rerun()

    st.divider()
    st.subheader("🗂 Contenido guardado en la memoria de Blue")
    st.caption("Todo lo que Blue ya sabe. Elimina fragmentos si la información está desactualizada.")
    datos = obtener_conocimiento()

    if not datos:
        st.warning("⚠️ La memoria de Blue está vacía. Sube contenido usando las opciones de arriba.")
    else:
        col_filtro, col_borrar = st.columns([3, 2])
        with col_filtro:
            cats   = sorted(set(d["categoria"] for d in datos))
            filtro = st.multiselect("Filtrar por tipo", cats, default=cats)
        with col_borrar:
            st.write("")
            with st.expander("🗑 Borrado masivo"):
                st.caption("Elimina varios fragmentos a la vez. Útil para reemplazar información desactualizada.")
                cat_borrar    = st.selectbox("Tipo a eliminar", cats, key="cat_borrar")
                area_borrar   = st.text_input("Área (vacío = todas)", key="area_borrar")
                puesto_borrar = st.text_input("Puesto (vacío = todos)", key="puesto_borrar")
                st.warning("⚠️ Esta acción no se puede deshacer.")
                if st.button("🗑 Eliminar fragmentos", type="secondary"):
                    eliminar_por_filtro(cat_borrar, area_borrar, puesto_borrar)
                    st.success("✅ Fragmentos eliminados.")
                    st.rerun()

        datos_f = [d for d in datos if d["categoria"] in filtro]
        st.caption(f"Mostrando **{len(datos_f)}** de {len(datos)} fragmento(s)")
        for chunk in datos_f:
            etiqueta = chunk.get("nombre_puesto") or chunk.get("nombre_area") or chunk["categoria"]
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
        "Sube videos de onboarding aquí — bienvenidas, presentaciones de áreas, tutoriales, etc.  \n"
        "Blue los enviará automáticamente por WhatsApp cuando detecte que el tema es relevante en la conversación.  \n\n"
        "**Ejemplo:** Si subes un video de 'Bienvenida al área de JimTech' y un desarrollador está haciendo su onboarding, "
        "Blue enviará ese video cuando llegue al tema de su área.",
        icon="🎥",
    )

    st.subheader("➕ Subir nuevo video")

    col_info_vid, col_archivo_vid = st.columns([1, 1])

    with col_info_vid:
        st.markdown("**Información del video**")
        st.caption("Estos datos le dicen a Blue cuándo y a quién enviar este video.")

        titulo_vid = st.text_input(
            "Título del video *",
            placeholder="Ej: Bienvenida a BlueBallon, Presentación de JimTech...",
            help="El título que verá el empleado cuando reciba el video.",
        )
        descripcion_vid = st.text_area(
            "Descripción / ¿Cuándo debe enviarlo Blue?",
            height=100,
            placeholder="Ej: Enviar este video cuando el empleado pregunte sobre el área de JimTech o al inicio del onboarding de desarrolladores.",
            help="Describe en qué momento Blue debe enviar este video. Mientras más claro, mejor.",
        )
        cat_vid = st.selectbox(
            "¿A qué tipo de contenido pertenece?",
            ["empresa", "area", "puesto", "politica"],
            format_func=lambda x: {
                "empresa":  "🏢 Empresa — video general de bienvenida",
                "area":     "🗂  Área — presentación de un departamento",
                "puesto":   "👤 Puesto — explicación de un cargo",
                "politica": "📋 Política — video sobre reglas o beneficios",
            }[x],
            key="cat_vid",
            help="Categoría del video. Blue usará esto para enviarlo en el contexto correcto.",
        )
        col_va, col_vb = st.columns(2)
        with col_va:
            area_vid = st.text_input("Área (si aplica)", placeholder="JimTech, RRHH...", key="area_vid",
                help="Deja vacío si el video es para toda la empresa.")
        with col_vb:
            puesto_vid = st.text_input("Puesto (si aplica)", placeholder="Director General...", key="puesto_vid",
                help="Solo si el video es específico de un puesto.")

    with col_archivo_vid:
        st.markdown("**Archivo de video**")
        st.caption("Formatos aceptados: MP4, MOV, AVI. Tamaño máximo recomendado: 16 MB (límite de WhatsApp).")

        archivo_vid = st.file_uploader(
            "Arrastra tu video aquí o haz clic para buscarlo",
            type=["mp4", "mov", "avi"],
            help="WhatsApp solo acepta videos de hasta 16 MB. Si tu video es más grande, comprimelo antes de subir.",
        )

        if archivo_vid:
            st.video(archivo_vid)
            size_mb = len(archivo_vid.getvalue()) / (1024 * 1024)
            if size_mb > 16:
                st.warning(f"⚠️ El video pesa {size_mb:.1f} MB. WhatsApp tiene un límite de 16 MB. Considera comprimirlo.")
            else:
                st.success(f"✅ Video listo: {size_mb:.1f} MB")

    st.markdown("---")

    if archivo_vid and titulo_vid:
        if st.button("⬆️  Subir video y activar en Blue", type="primary", use_container_width=True):
            with st.spinner("Subiendo video a Supabase... puede tardar unos segundos según el tamaño."):
                try:
                    extension = archivo_vid.name.split(".")[-1].lower()
                    url_video = subir_video_supabase(archivo_vid.getvalue(), extension)
                    registrar_video(titulo_vid, descripcion_vid, cat_vid, area_vid, puesto_vid, url_video)
                    st.success(f"✅ ¡Listo! El video '{titulo_vid}' ya está disponible para Blue.")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Error al subir el video: {e}")
    elif archivo_vid and not titulo_vid:
        st.warning("⚠️ Falta el título del video para poder subirlo.")

    st.divider()

    # ── Lista de videos ───────────────────────────────────────────────────────
    st.subheader("🎬 Videos disponibles para Blue")
    st.caption("Todos los videos que Blue puede enviar durante el onboarding. El toggle activa o desactiva cada video.")

    videos = obtener_videos()

    if not videos:
        st.warning("⚠️ No hay videos registrados aún. Sube videos usando el formulario de arriba.")
    else:
        activos_v   = sum(1 for v in videos if v["activo"])
        inactivos_v = len(videos) - activos_v
        st.caption(f"**{activos_v}** activo(s) · **{inactivos_v}** inactivo(s) · **{len(videos)}** en total")

        for vid in videos:
            icono = "🟢" if vid["activo"] else "🔴"
            with st.expander(f"{icono} {vid['titulo']} — [{vid['categoria'].upper()}] {vid.get('nombre_area') or vid.get('nombre_puesto') or 'General'}"):
                col_prev, col_meta = st.columns([2, 1])

                with col_prev:
                    st.video(vid["url_video"])

                with col_meta:
                    st.markdown(f"**Título:** {vid['titulo']}")
                    if vid.get("descripcion"):
                        st.markdown(f"**¿Cuándo enviarlo?**  \n{vid['descripcion']}")
                    st.markdown(f"**Categoría:** {vid['categoria']}")
                    if vid.get("nombre_area"):
                        st.markdown(f"**Área:** {vid['nombre_area']}")
                    if vid.get("nombre_puesto"):
                        st.markdown(f"**Puesto:** {vid['nombre_puesto']}")
                    st.caption(f"Subido: {vid['creado_en'][:10]}")

                    col_tog, col_del = st.columns(2)
                    with col_tog:
                        nuevo_estado = st.toggle(
                            "Activo",
                            value=vid["activo"],
                            key=f"tog_v_{vid['id']}",
                            help="Activo = Blue puede enviar este video. Inactivo = Blue no lo enviará.",
                        )
                        if nuevo_estado != vid["activo"]:
                            toggle_video(vid["id"], nuevo_estado)
                            st.rerun()
                    with col_del:
                        if st.button("🗑 Eliminar", key=f"del_v_{vid['id']}"):
                            eliminar_video(vid["id"])
                            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — EMPLEADOS
# ══════════════════════════════════════════════════════════════════════════════

with tab_empleados:

    st.info(
        "**¿Por qué registrar empleados aquí?**  \n"
        "Cuando un empleado nuevo le escriba a Blue por WhatsApp y diga su nombre, "
        "Blue lo buscará aquí para saber a qué área pertenece y personalizar el onboarding.  \n\n"
        "**Importante:** El empleado debe estar registrado ANTES de iniciar el onboarding.",
        icon="👥",
    )

    st.subheader("➕ Registrar nuevo empleado")

    modo_empleados = st.radio(
        "¿Cómo quieres registrar al empleado?",
        ["✍️  Uno por uno", "📊 Varios a la vez con Excel"],
        horizontal=True, key="modo_emp",
    )

    if modo_empleados == "✍️  Uno por uno":
        with st.form("form_empleado", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                nombre    = st.text_input("Nombre *", placeholder="Axel",
                    help="El nombre que el empleado usará al presentarse con Blue.")
                area_emp  = st.text_input("Área *", placeholder="JimTech, RRHH...",
                    help="Blue mostrará información específica de esta área.")
                email_emp = st.text_input("Email", placeholder="axel@blueballon.mx")
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
                registrar_empleado(nombre, apellido, area_emp, puesto_emp, email_emp, fecha_ing)
                st.success(f"✅ {nombre} {apellido} registrado. Ya puede iniciar su onboarding con Blue.")
                st.rerun()

    else:
        st.info("Descarga la plantilla, llénala y súbela aquí.", icon="📊")
        plantilla_emp = pd.DataFrame([{
            "nombre": "Axel", "apellido": "García", "area": "JimTech",
            "puesto": "Desarrollador", "email": "axel@blueballon.mx", "fecha_ingreso": "2026-03-24",
        }])
        buf_emp = io.BytesIO()
        plantilla_emp.to_excel(buf_emp, index=False)
        st.download_button("⬇️  Descargar plantilla Excel de empleados",
            data=buf_emp.getvalue(), file_name="plantilla_empleados_blue.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        archivo_emp = st.file_uploader("Sube tu Excel (.xlsx)", type=["xlsx"], key="xlsx_emp")
        if archivo_emp:
            df_emp = pd.read_excel(archivo_emp)
            if not {"nombre", "area"}.issubset(set(df_emp.columns)):
                st.error("⚠️ Faltan columnas: `nombre` y `area`.")
            else:
                st.dataframe(df_emp, use_container_width=True)
                if st.button("➕  Registrar todos", type="primary", key="btn_excel_emp"):
                    for _, fila in df_emp.iterrows():
                        registrar_empleado(
                            str(fila.get("nombre", "")), str(fila.get("apellido", "")),
                            str(fila.get("area", "")), str(fila.get("puesto", "")),
                            str(fila.get("email", "")), str(fila.get("fecha_ingreso", "")),
                        )
                    st.success(f"✅ {len(df_emp)} empleado(s) registrados.")
                    st.balloons()
                    st.rerun()

    st.divider()
    st.subheader("📋 Empleados registrados")
    st.caption("El toggle verde/rojo indica si el empleado puede hacer onboarding con Blue.")

    empleados = obtener_empleados()

    if not empleados:
        st.warning("⚠️ No hay empleados registrados aún.")
    else:
        activos = sum(1 for e in empleados if e["activo"])
        st.caption(f"**{activos}** activo(s) · **{len(empleados) - activos}** inactivo(s)")

        for emp in empleados:
            icono = "🟢" if emp["activo"] else "🔴"
            col_info, col_toggle, col_del = st.columns([5, 1, 1])
            with col_info:
                st.markdown(
                    f"{icono} **{emp['nombre']} {emp['apellido']}** — {emp['area']} / {emp['puesto']}  \n"
                    f"<small>{emp.get('email') or '—'} · Ingreso: {emp.get('fecha_ingreso', '—')}</small>",
                    unsafe_allow_html=True,
                )
            with col_toggle:
                nuevo_estado = st.toggle("Activo", value=emp["activo"],
                    key=f"tog_{emp['id']}", label_visibility="collapsed",
                    help="Inactivo = Blue no reconocerá a este empleado.")
                if nuevo_estado != emp["activo"]:
                    toggle_empleado(emp["id"], nuevo_estado)
                    st.rerun()
            with col_del:
                if st.button("🗑", key=f"del_e_{emp['id']}", help="Eliminar"):
                    eliminar_empleado(emp["id"])
                    st.rerun()
            st.divider()