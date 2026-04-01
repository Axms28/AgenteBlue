"""
blue/jim.py
Orquestador conversacional del Agente Blue — Grupo Blue Balloon.
"""

import os
import json
import re
from anthropic import Anthropic
from dotenv import load_dotenv
from blue.rag import buscar_contexto, buscar_empleado

load_dotenv()

cliente = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODELO  = "claude-sonnet-4-5"

SYSTEM_PROMPT = """
Eres Ali, el agente de onboarding de Grupo Blue Balloon. Tu misión es dar la bienvenida
a los nuevos empleados y guiarlos por su proceso de inducción de forma cálida,
clara y profesional.

PERSONALIDAD:
- Tu nombre es Ali, preséntate así cuando saludes
- Amigable y cercana, pero profesional
- Usas el nombre del empleado frecuentemente
- Explicas las cosas con claridad, sin jerga innecesaria

ESTRUCTURA DEL GRUPO:
Grupo Blue Balloon es la empresa holding. Está conformada por varias empresas hermanas
como JimTech, Green Balloon y otras subsidiarias. Cada una tiene sus propias áreas y puestos.
Cuando hables con el empleado, ten claro a qué empresa y área pertenece.

FLUJO DE ONBOARDING:
1. Bienvenida personalizada (usa el nombre, subsidiaria y área del empleado)
2. Presentación del Grupo Blue Balloon (misión, visión y valores generales)
3. Presentación de su empresa específica (JimTech, Green Balloon, etc.)
4. Presentación de su área dentro de esa empresa
5. Explicación de su puesto y responsabilidades
6. Políticas generales (horarios, beneficios, primeros 30 días)
7. Cierre: invitar al empleado a hacer preguntas

REGLAS:
- Nunca inventes información. Si no la tienes en el contexto, dilo honestamente
- Avanza un tema a la vez, no abrumes con todo de golpe
- Si el empleado pregunta algo fuera del onboarding, responde brevemente y regresa al flujo
- Cuando termines un tema, pregunta si tiene dudas antes de continuar
- Si detectas que el empleado no entendió algo, explícalo de otra forma
- Nunca uses markdown, asteriscos, negritas, cursivas ni listas con guiones
- Escribe siempre en texto plano, como si estuvieras hablando en voz
- En lugar de listas, di "primero... segundo... y tercero..."
- Usa puntos y comas para pausas naturales
- Responde en máximo 3 oraciones por turno, sé conciso
- No expliques todo de golpe, ve un tema a la vez
- Al final de cada respuesta, si el tema amerita un video de apoyo,
  agrega en una línea separada exactamente esto:
  [VIDEO: nombre del tema]
  Ejemplos: [VIDEO: bienvenida], [VIDEO: JimTech], [VIDEO: Director General]
  Si no hay video relevante, no agregues nada extra.

CONTEXTO DEL EMPLEADO:
{contexto_empleado}

INFORMACIÓN RELEVANTE DEL GRUPO:
{contexto_rag}
"""


class SesionJIM:
    def __init__(self):
        self.historial:             list[dict] = []
        self.empleado:              dict | None = None
        self.etapa:                 int = 1
        self.eventos:               list[dict] = []
        self.nombre_detectado:      str = ""
        self.tema_video_pendiente:  str = ""
        self.videos_enviados:       set = set()


def extraer_nombre(mensaje: str) -> str:
    patrones = [
        r"(?:soy|me llamo|mi nombre es)\s+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        r"^hola[,\s]+([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)",
        r"^([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)\s+(?:aquí|presente|reportándome)",
    ]
    for patron in patrones:
        match = re.search(patron, mensaje, re.IGNORECASE)
        if match:
            return match.group(1).capitalize()
    return ""


def extraer_señal_video(respuesta: str) -> tuple[str, str]:
    match = re.search(r'\[VIDEO:\s*(.+?)\]', respuesta, re.IGNORECASE)
    if match:
        tema_video   = match.group(1).strip()
        texto_limpio = re.sub(r'\[VIDEO:\s*.+?\]', '', respuesta).strip()
        return texto_limpio, tema_video
    return respuesta.strip(), ""


def evaluar_comprension(turno_empleado, respuesta_blue, etapa, empleado) -> dict | None:
    etapas = {
        1: "bienvenida",
        2: "misión y visión del grupo",
        3: "empresa/subsidiaria",
        4: "área de trabajo",
        5: "puesto y responsabilidades",
        6: "políticas generales",
        7: "cierre",
    }
    tema = etapas.get(etapa, "general")

    prompt = f"""Analiza este intercambio de onboarding y evalúa la comprensión del empleado.

Tema tratado: {tema}
Respuesta del empleado: "{turno_empleado}"
Explicación de Blue: "{respuesta_blue[:500]}"

Responde ÚNICAMENTE con un JSON válido, sin texto adicional:
{{
  "tema": "{tema}",
  "nivel": "alto|medio|bajo",
  "observacion": "Una frase corta sobre qué entendió o no entendió el empleado",
  "requiere_refuerzo": true|false
}}"""

    try:
        respuesta = cliente.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        evento = json.loads(respuesta.content[0].text.strip())
        evento["empleado"]    = empleado.get("nombre", "")      if empleado else ""
        evento["subsidiaria"] = empleado.get("subsidiaria", "") if empleado else ""
        evento["area"]        = empleado.get("area", "")        if empleado else ""
        evento["etapa"]       = etapa
        return evento
    except Exception:
        return None


def procesar_turno(sesion: SesionJIM, mensaje_usuario: str) -> str:
    # 1. Detectar nombre
    if not sesion.nombre_detectado:
        nombre = extraer_nombre(mensaje_usuario)
        if nombre:
            sesion.nombre_detectado = nombre
            sesion.empleado = buscar_empleado(nombre)

    # 2. Contexto del empleado
    if sesion.empleado:
        emp = sesion.empleado
        contexto_empleado = (
            f"Nombre: {emp.get('nombre', '')} {emp.get('apellido', '')}\n"
            f"Empresa (subsidiaria): {emp.get('subsidiaria', 'Grupo Blue Balloon')}\n"
            f"Área: {emp.get('area', '')}\n"
            f"Puesto: {emp.get('puesto', '')}\n"
            f"Email: {emp.get('email', '')}\n"
            f"Fecha de ingreso: {emp.get('fecha_ingreso', '')}"
        )
        subsidiaria = emp.get("subsidiaria", "")
        area_emp    = emp.get("area", "")
        puesto_emp  = emp.get("puesto", "")
    else:
        contexto_empleado = "Empleado no identificado aún."
        subsidiaria = ""
        area_emp    = ""
        puesto_emp  = ""

    # 3. RAG con subsidiaria
    contexto_rag = buscar_contexto(
        pregunta      = mensaje_usuario,
        subsidiaria   = subsidiaria,
        nombre_area   = area_emp,
        nombre_puesto = puesto_emp,
        top_k         = 4,
    )

    # 4. System prompt
    system = SYSTEM_PROMPT.format(
        contexto_empleado = contexto_empleado,
        contexto_rag      = contexto_rag or "Sin contexto disponible aún.",
    )

    # 5. Historial
    sesion.historial.append({"role": "user", "content": mensaje_usuario})

    # 6. Claude Sonnet
    respuesta = cliente.messages.create(
        model      = MODELO,
        max_tokens = 1024,
        system     = system,
        messages   = sesion.historial,
    )

    # 7. Extraer texto limpio y señal de video
    respuesta_limpia, tema_video = extraer_señal_video(respuesta.content[0].text)
    sesion.tema_video_pendiente = tema_video

    # 8. Historial limpio (una sola vez)
    sesion.historial.append({"role": "assistant", "content": respuesta_limpia})

    # 9. Evaluación silenciosa
    evento = evaluar_comprension(mensaje_usuario, respuesta_limpia, sesion.etapa, sesion.empleado)
    if evento:
        sesion.eventos.append(evento)

    return respuesta_limpia


def obtener_resumen_sesion(sesion: SesionJIM) -> str:
    if not sesion.eventos:
        return "Sin eventos registrados en esta sesión."

    nombre = sesion.empleado.get("nombre", "el empleado") if sesion.empleado else "el empleado"
    sub    = sesion.empleado.get("subsidiaria", "")        if sesion.empleado else ""

    prompt = f"""Genera un resumen ejecutivo del onboarding de {nombre} ({sub}) basado en estos eventos:

{json.dumps(sesion.eventos, ensure_ascii=False, indent=2)}

El resumen debe:
- Indicar qué temas comprendió bien
- Indicar qué temas necesitan refuerzo
- Dar una evaluación general (excelente / satisfactoria / necesita seguimiento)
- Ser breve, máximo 5 oraciones
- Estar escrito para el área de RRHH
- Escribir en texto plano sin markdown"""

    respuesta = cliente.messages.create(
        model      = "claude-haiku-4-5-20251001",
        max_tokens = 400,
        messages   = [{"role": "user", "content": prompt}],
    )
    return respuesta.content[0].text