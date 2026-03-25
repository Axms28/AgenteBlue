"""
ingestor_jim.py
Ingesta de documentos de BlueBallon hacia Supabase + pgvector
para el cerebro del Agente JIM de onboarding.

Uso:
    python ingestor_jim.py

Requiere en .env:
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_KEY=tu_service_role_key
    OPENAI_API_KEY=tu_openai_key
"""

import os
import json
import time
from dataclasses import dataclass
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from supabase import create_client, Client
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv()

# ─── Clientes ────────────────────────────────────────────────────────────────

cliente_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
cliente_supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY"),
)

# ─── Configuración de chunking ────────────────────────────────────────────────

MODELO_EMBEDDING = "text-embedding-3-small"
TAMANO_CHUNK     = 300   # tokens aprox.
OVERLAP_CHUNK    = 50
TABLA_SUPABASE   = "conocimiento_jim"

divisor = RecursiveCharacterTextSplitter(
    chunk_size=TAMANO_CHUNK,
    chunk_overlap=OVERLAP_CHUNK,
    separators=["\n\n", "\n", ". ", " "],
)

# ─── Tipo de documento ────────────────────────────────────────────────────────

Categoria = Literal["empresa", "area", "puesto", "politica"]
Prioridad = Literal["alta", "media", "baja"]


@dataclass
class Documento:
    """
    Representa un documento fuente listo para ingestar.

    Atributos:
        contenido    : Texto completo del documento.
        categoria    : Tipo de información (empresa, area, puesto, politica).
        nombre_area  : Área a la que pertenece (ej. "JimTech", "RRHH").
        nombre_puesto: Puesto específico si aplica (ej. "Desarrollador").
        prioridad    : Nivel de relevancia para el RAG.
    """
    contenido:     str
    categoria:     Categoria
    nombre_area:   str = ""
    nombre_puesto: str = ""
    prioridad:     Prioridad = "alta"


# ─── Base de conocimiento de BlueBallon ──────────────────────────────────────
# Aquí defines todos los documentos de la empresa.
# Cada Documento se divide en chunks automáticamente.

DOCUMENTOS_BLUEBALLON: list[Documento] = [

    # ── EMPRESA GENERAL ──
    Documento(
        categoria="empresa",
        prioridad="alta",
        contenido="""
BlueBallon es una empresa tecnológica mexicana fundada en 2018,
especializada en el desarrollo de soluciones digitales para el sector
educativo y empresarial. Opera principalmente en México y Latinoamérica.

Misión:
Transformar la manera en que las personas aprenden y trabajan mediante
tecnología accesible, innovadora y centrada en las personas.

Visión:
Ser la plataforma tecnológica de referencia en Latinoamérica para
la educación y productividad digital para el año 2030.

Valores:
- Innovación continua
- Colaboración y trabajo en equipo
- Responsabilidad y transparencia
- Impacto social positivo
        """,
    ),

    # ── ÁREA JIMTECH ──
    Documento(
        categoria="area",
        nombre_area="JimTech",
        prioridad="alta",
        contenido="""
JimTech es el área de desarrollo de software de BlueBallon.
Es responsable del diseño, construcción y mantenimiento de todos los
productos digitales internos y externos de la empresa.

Funciones principales:
- Desarrollo de aplicaciones web y móviles.
- Diseño de arquitecturas de sistemas escalables.
- Integración de APIs e inteligencia artificial.
- Mantenimiento y mejora continua de productos en producción.

Metodología: Scrum con sprints de dos semanas.
Herramientas: GitHub, Jira, Figma, VS Code, Docker.
Líder de área: Por asignar.
        """,
    ),

    # ── ÁREA RRHH ──
    Documento(
        categoria="area",
        nombre_area="RRHH",
        prioridad="alta",
        contenido="""
El área de Recursos Humanos de BlueBallon gestiona el talento y bienestar
de todos los colaboradores de la empresa.

Funciones principales:
- Reclutamiento y selección de personal.
- Onboarding y capacitación de nuevos empleados.
- Administración de nómina y prestaciones.
- Gestión del clima organizacional y cultura empresarial.
- Evaluaciones de desempeño semestrales.

Contacto: rrhh@blueballon.mx
        """,
    ),

    # ── PUESTO: DESARROLLADOR ──
    Documento(
        categoria="puesto",
        nombre_area="JimTech",
        nombre_puesto="Desarrollador",
        prioridad="alta",
        contenido="""
El Desarrollador en JimTech es responsable de construir y mantener
las aplicaciones y servicios digitales de BlueBallon.

Responsabilidades:
- Escribir código limpio, documentado y con cobertura de pruebas.
- Participar activamente en las ceremonias Scrum del equipo.
- Colaborar con diseño (UX) y producto para implementar funcionalidades.
- Revisar código de compañeros mediante pull requests.
- Reportar avance diario en Jira.

Herramientas del día a día:
Python, JavaScript/TypeScript, React, FastAPI, PostgreSQL, Docker, Git.

Reporta a: Tech Lead de JimTech.
        """,
    ),

    # ── POLÍTICAS GENERALES ──
    Documento(
        categoria="politica",
        prioridad="alta",
        contenido="""
Políticas generales de BlueBallon para nuevos colaboradores:

Horario: Lunes a viernes de 9:00 a 18:00 hrs (modalidad híbrida).
Días de home office: Martes y jueves.

Beneficios:
- Sueldo mensual conforme a contrato.
- 15 días de vacaciones al año desde el primer año.
- Seguro de gastos médicos mayores.
- Bono de productividad semestral.
- Presupuesto anual de capacitación: $5,000 MXN.

Primeros 30 días:
El nuevo colaborador tendrá un período de inducción acompañado por
su líder directo y el área de RRHH. Se espera participación activa
en el onboarding con el agente JIM.

Dudas o incidencias: Contactar a RRHH en rrhh@blueballon.mx
        """,
    ),
]


# ─── Funciones ───────────────────────────────────────────────────────────────

def generar_embedding(texto: str) -> list[float]:
    """Genera el vector de embedding para un texto usando OpenAI."""
    respuesta = cliente_openai.embeddings.create(
        model=MODELO_EMBEDDING,
        input=texto.replace("\n", " "),
    )
    return respuesta.data[0].embedding


def ingestar_documento(doc: Documento) -> int:
    """
    Divide un documento en chunks, genera embeddings e inserta en Supabase.
    Retorna la cantidad de chunks insertados.
    """
    chunks = divisor.split_text(doc.contenido.strip())
    insertados = 0

    for chunk in chunks:
        if len(chunk.strip()) < 30:
            continue  # ignorar fragmentos muy cortos

        vector = generar_embedding(chunk)

        registro = {
            "contenido":     chunk,
            "vector":        vector,
            "categoria":     doc.categoria,
            "nombre_area":   doc.nombre_area,
            "nombre_puesto": doc.nombre_puesto,
            "prioridad":     doc.prioridad,
        }

        cliente_supabase.table(TABLA_SUPABASE).insert(registro).execute()
        insertados += 1

        time.sleep(0.1)  # evitar rate limit de OpenAI

    return insertados


def ejecutar_ingesta():
    """Ingesta todos los documentos de DOCUMENTOS_BLUEBALLON."""
    print("=" * 55)
    print("  Ingestor RAG — Agente JIM / BlueBallon")
    print("=" * 55)

    total_chunks = 0

    for i, doc in enumerate(DOCUMENTOS_BLUEBALLON, 1):
        etiqueta = doc.nombre_area or doc.categoria
        print(f"\n[{i}/{len(DOCUMENTOS_BLUEBALLON)}] {doc.categoria.upper()} — {etiqueta}")
        chunks_insertados = ingestar_documento(doc)
        print(f"    ✓ {chunks_insertados} chunk(s) insertado(s)")
        total_chunks += chunks_insertados

    print(f"\n{'=' * 55}")
    print(f"  Ingesta completa: {total_chunks} chunks en Supabase")
    print(f"  Tabla: {TABLA_SUPABASE}")
    print("=" * 55)


# ─── Función de consulta (para probar el RAG) ─────────────────────────────────

def buscar_contexto(
    pregunta: str,
    nombre_area: str = "",
    nombre_puesto: str = "",
    top_k: int = 3,
) -> list[dict]:
    """
    Busca los chunks más relevantes para una pregunta.
    Filtra por área y puesto si se proporcionan.

    Ejemplo:
        chunks = buscar_contexto(
            "¿qué hace el área de JimTech?",
            nombre_area="JimTech"
        )
    """
    vector_query = generar_embedding(pregunta)

    # Construir filtros de metadata
    filtros = {}
    if nombre_area:
        filtros["nombre_area"] = nombre_area
    if nombre_puesto:
        filtros["nombre_puesto"] = nombre_puesto

    respuesta = cliente_supabase.rpc(
        "buscar_conocimiento_jim",
        {
            "query_vector": vector_query,
            "filtro_area":  nombre_area,
            "filtro_puesto": nombre_puesto,
            "top_k":        top_k,
        },
    ).execute()

    return respuesta.data


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ejecutar_ingesta()