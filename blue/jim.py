"""
agente/jim.py
Orquestador conversacional del Agente JIM — BlueBallon.

Flujo por turno:
  1. Detectar nombre del empleado si aún no se conoce
  2. Buscar perfil en empleados_jim
  3. Consultar RAG con contexto del empleado
  4. Llamar a Claude con historial + contexto
  5. Guardar evento de comprensión para el panel de resumen
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

# ─── System prompt base de JIM ────────────────────────────────────────────────

SYSTEM_PROMPT = """
Eres Blue, el agente de onboarding de BlueBallon. Tu misión es dar la bienvenida
a los nuevos empleados y guiarlos por su proceso de inducción de forma cálida,
clara y profesional.

PERSONALIDAD:
- Tu nombre es Blue, preséntate así cuando saludes
- Amigable y cercano, pero profesional
- Usas el nombre del empleado frecuentemente
- Explicas las cosas con claridad, sin jerga innecesaria
- Haces preguntas cortas para verificar que el empleado entendió

FLUJO DE ONBOARDING:
Sigue este orden durante la conversación:
1. Bienvenida personalizada (usa el nombre y área del empleado)
2. Presentación de la empresa (misión, visión y valores)
3. Presentación de su área específica y su función
4. Explicación de su puesto y responsabilidades
5. Políticas generales (horarios, beneficios, primeros 30 días)
6. Cierre: invitar al empleado a hacer preguntas

REGLAS:
- Nunca inventes información. Si no la tienes en el contexto, dilo honestamente
- Avanza un tema a la vez, no abrumes con todo de golpe
- Si el empleado pregunta algo fuera del onboarding, responde brevemente
  y regresa al flujo
- Cuando termines un tema, pregunta si tiene dudas antes de continuar
- Si detectas que el empleado no entendió algo, explícalo de otra forma

CONTEXTO DEL EMPLEADO:
{contexto_empleado}

INFORMACIÓN RELEVANTE DE BLUEBALLON:
{contexto_rag}
"""

# ─── Estado de sesión ─────────────────────────────────────────────────────────

class SesionJIM:
    """
    Mantiene el estado completo de una conversación de onboarding.

    Atributos:
        historial        : Lista de mensajes en formato Anthropic.
        empleado         : Dict con datos del empleado (o None si no se identificó).
        etapa            : Etapa actual del onboarding (1-6).
        eventos          : Lista de eventos de comprensión para el panel.
        nombre_detectado : Nombre extraído del primer mensaje del empleado.
    """

    def __init__(self):
        self.historial:         list[dict] = []
        self.empleado:          dict | None = None
        self.etapa:             int = 1
        self.eventos:           list[dict] = []
        self.nombre_detectado:  str = ""


# ─── Detección de nombre ──────────────────────────────────────────────────────

def extraer_nombre(mensaje: str) -> str:
    """
    Intenta extraer un nombre propio del mensaje del empleado.
    Detecta patrones como: 'soy Axel', 'me llamo Ana', 'hola, soy Carlos'.
    """
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


# ─── Evaluador silencioso de comprensión ─────────────────────────────────────

def evaluar_comprension(
    turno_empleado: str,
    respuesta_jim: str,
    etapa: int,
    empleado: dict,
) -> dict | None:
    """
    Usa Claude Haiku para detectar si el empleado comprendió el tema.
    Retorna un dict con el evento o None si no hay suficiente información.
    Este evaluador corre en segundo plano y NO bloquea la conversación.
    """
    etapas = {
        1: "bienvenida",
        2: "misión y visión",
        3: "área de trabajo",
        4: "puesto y responsabilidades",
        5: "políticas generales",
        6: "cierre",
    }
    tema = etapas.get(etapa, "general")

    prompt = f"""Analiza este intercambio de onboarding y evalúa la comprensión del empleado.

Tema tratado: {tema}
Respuesta del empleado: "{turno_empleado}"
Explicación de Blue: "{respuesta_jim[:500]}"

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
        texto = respuesta.content[0].text.strip()
        evento = json.loads(texto)
        evento["empleado"] = empleado.get("nombre", "") if empleado else ""
        evento["area"]     = empleado.get("area", "") if empleado else ""
        evento["etapa"]    = etapa
        return evento
    except Exception:
        return None


# ─── Turno principal ──────────────────────────────────────────────────────────

def procesar_turno(sesion: SesionJIM, mensaje_usuario: str) -> str:
    """
    Procesa un turno de conversación y retorna la respuesta de Blue.

    Args:
        sesion          : Estado actual de la sesión.
        mensaje_usuario : Texto enviado por el empleado.

    Returns:
        Respuesta de Blue como string.
    """

    # 1. Detectar nombre si aún no se tiene
    if not sesion.nombre_detectado:
        nombre = extraer_nombre(mensaje_usuario)
        if nombre:
            sesion.nombre_detectado = nombre
            empleado = buscar_empleado(nombre)
            sesion.empleado = empleado

    # 2. Construir contexto del empleado para el system prompt
    if sesion.empleado:
        emp = sesion.empleado
        contexto_empleado = (
            f"Nombre: {emp.get('nombre', '')} {emp.get('apellido', '')}\n"
            f"Área: {emp.get('area', '')}\n"
            f"Puesto: {emp.get('puesto', '')}\n"
            f"Email: {emp.get('email', '')}\n"
            f"Fecha de ingreso: {emp.get('fecha_ingreso', '')}"
        )
        area_emp  = emp.get("area", "")
        puesto_emp = emp.get("puesto", "")
    else:
        contexto_empleado = "Empleado no identificado aún."
        area_emp  = ""
        puesto_emp = ""

    # 3. Consultar RAG con el mensaje actual
    contexto_rag = buscar_contexto(
        pregunta      = mensaje_usuario,
        nombre_area   = area_emp,
        nombre_puesto = puesto_emp,
        top_k         = 4,
    )

    # 4. Construir system prompt con contextos inyectados
    system = SYSTEM_PROMPT.format(
        contexto_empleado = contexto_empleado,
        contexto_rag      = contexto_rag or "Sin contexto disponible aún.",
    )

    # 5. Agregar mensaje del empleado al historial
    sesion.historial.append({
        "role":    "user",
        "content": mensaje_usuario,
    })

    # 6. Llamar a Claude Sonnet
    respuesta = cliente.messages.create(
        model      = MODELO,
        max_tokens = 1024,
        system     = system,
        messages   = sesion.historial,
    )

    respuesta_jim = respuesta.content[0].text

    # 7. Agregar respuesta de JIM al historial
    sesion.historial.append({
        "role":    "assistant",
        "content": respuesta_jim,
    })

    # 8. Evaluación silenciosa de comprensión (no bloquea la respuesta)
    evento = evaluar_comprension(
        turno_empleado = mensaje_usuario,
        respuesta_jim  = respuesta_jim,
        etapa          = sesion.etapa,
        empleado       = sesion.empleado,
    )
    if evento:
        sesion.eventos.append(evento)

    return respuesta_jim


def obtener_resumen_sesion(sesion: SesionJIM) -> str:
    """
    Genera un resumen de la sesión para el panel de RRHH.
    Llama a Claude con todos los eventos acumulados.
    """
    if not sesion.eventos:
        return "Sin eventos registrados en esta sesión."

    nombre = sesion.empleado.get("nombre", "el empleado") if sesion.empleado else "el empleado"

    prompt = f"""Genera un resumen ejecutivo del onboarding de {nombre} basado en estos eventos:

{json.dumps(sesion.eventos, ensure_ascii=False, indent=2)}

El resumen debe:
- Indicar qué temas comprendió bien
- Indicar qué temas necesitan refuerzo
- Dar una evaluación general (excelente / satisfactoria / necesita seguimiento)
- Ser breve, máximo 5 oraciones
- Estar escrito para el área de RRHH"""

    respuesta = cliente.messages.create(
        model      = "claude-haiku-4-5-20251001",
        max_tokens = 400,
        messages   = [{"role": "user", "content": prompt}],
    )
    return respuesta.content[0].text