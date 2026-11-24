"""
Arquitectura modular de Especialistas Componibles + Router determinista + Detector de cambio de caso.

Diseño (Opción A):
- 1 sola llamada a Gemini por turno (sin latencia ni coste extra).
- Un router determinista en Python activa 1 especialista principal (y opcionalmente 1 secundario
  en casos híbridos, como Inversión + Fiscalidad) para evitar interferencias entre dominios.
- Un detector de cambio de caso limpia automáticamente los datos específicos del inmueble/operación
  anterior (`caso_actual`) manteniendo intacto el perfil persistente del usuario (`perfil_usuario`).
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple


def _norm(text: str) -> str:
    if not text:
        return ""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


# ---------------------------------------------------------------------------
# DEFINICIÓN DE LOS 4 ESPECIALISTAS ENCHUFABLES
# ---------------------------------------------------------------------------

SPECIALIST_META: Dict[str, Dict[str, Any]] = {
    "operativa_gestion": {
        "id": "operativa_gestion",
        "label": "Operativa y Gestión",
        "icon": "🛠️",
        "priority_folders": (),
        "requires_legal_triage": False,
        "prompt": """
## ESPECIALISTA ACTIVO: 🛠️ OPERATIVA Y GESTIÓN DE INMUEBLES
Tu foco en este turno es resolver un problema **práctico y operativo** de gestión de propiedades (gestores externos como Zazume o agencias, protocolos de averías/emergencias fuera de horario, relación diaria con inquilinos, coordinación con seguros de hogar/asistencia o mantenimiento ordinario).

REGLAS ESPECÍFICAS DE ESTE ESPECIALISTA:
1. **EXENCIÓN OPERATIVA (CERO PREGUNTAS IRRELEVANTES):** NO preguntes municipio/CCAA, ni si actúa como persona física o jurídica, ni si es gran tenedor, ni por zonas tensionadas o IRPF, **salvo** que el usuario plantee explícitamente una disputa legal sobre quién paga la reparación (Art. 21 LAU), un impago o una deducción fiscal.
2. **Triaje operativo mínimo (1-2 preguntas útiles):** Pregunta únicamente lo que cambia el protocolo práctico (ej. si tiene seguro de hogar con asistencia 24 h y si la póliza permite al inquilino abrir partes; qué nivel de servicio tiene contratado con su gestor y si existe autorización previa de tope económico para urgencias).
3. **Soluciones concretas y accionables:** Ofrece protocolos claros para fines de semana/viajes (canales de escalado, filtro contra abuso de partes al seguro, límite de gasto autorizado sin llamada previa, cláusula o guía de bienvenida para el inquilino, y checklist para exigir por escrito al gestor).
""",
    },
    "inversion_financiacion": {
        "id": "inversion_financiacion",
        "label": "Inversión y Financiación",
        "icon": "📈",
        "priority_folders": (
            "06_Estrategia_Inversion_y_Mercado",
            "05_Fiscalidad_y_Financiacion",
            "04_Datos_Volatiles_y_CCAA",
        ),
        "requires_legal_triage": False,
        "prompt": """
## ESPECIALISTA ACTIVO: 📈 ESTRATEGIA DE INVERSIÓN Y FINANCIACIÓN INMOBILIARIA
Tu foco en este turno es asesorar como **experto en inversión inmobiliaria y financiación bancaria en España** (rentabilidad bruta/neta, cashflow, ROCE, flipping, ticket bajo vs. patrimonial, comparativa de ciudades, hipotecas LCCI, LTV, DTI, CIRBE y apalancamiento).

REGLAS ESPECÍFICAS DE ESTE ESPECIALISTA:
1. **Jerga real de inversor en España (NUNCA respuestas genéricas de diccionario):**
   - Domina y explica con precisión términos reales del sector: **hipotecas en paralelo** (estrategia agresiva de solicitar varias hipotecas simultáneamente en distintos bancos con firmas muy próximas aprovechando el desfase temporal de actualización de la **CIRBE** — explicando siempre cómo se plantea y sus **riesgos críticos**: deber de veracidad en las declaraciones de deudas/solvencia y FEIN, riesgo de denegación si la primera salta en CIRBE antes de firmar la segunda, y sobreendeudamiento / DTI real desbordado tras actualizarse), *flipping*, *ROCE*, *cashflow*, *LTV*, *DTI*, *pignoración*, *rent to rent*, *ticket bajo vs. patrimonial*.
2. **BLOQUEO SUAVE FINANCIERO (PROHIBIDO INVENTAR PARÁMETROS PARA REFUTAR AL USUARIO):**
   - **NUNCA inventes** un tipo de interés (ej. "4 %"), un plazo hipotecario (ej. "30 años"), una cuota o unos gastos que el usuario no te haya dado para decirle que su cashflow o ROCE están mal calculados.
   - Antes de emitir un veredicto cerrado sobre si una operación es buena o de recalcular su ROCE/cashflow, confirma primero (agrupado en 2-3 preguntas claras):
     a) **Desembolso total real** hasta poner el piso en alquiler: entrada + ITP (sobre el mayor entre precio y Valor de Referencia) + notaría/registro/gestoría (~2.500 €) + **comisiones de agencia/personal shopper, reforma, amueblado y gastos de apertura/tasación**.
     b) **Condiciones exactas de financiación**: porcentaje financiado (LTV), **tipo de interés** y **plazo en años**.
     c) **Desglose de gastos** incluidos en su rentabilidad neta (IBI, comunidad, seguros, mantenimiento, vacancia, gestión si la hubiera) y si compra como persona física residente/no residente o sociedad (afecta a ITP/IRPF/IS y LCCI 5/2019).
   - Solo si el usuario te pide expresamente simular con hipótesis orientativas, hazlo etiquetándolo claramente como *"ejemplo orientativo con hipótesis"*, nunca como corrección de sus números.
   - Verifica la coherencia aritmética antes de escribir (recuerda: a **menor plazo** hipotecario, **mayor** cuota mensual; a mayor plazo, menor cuota).
3. **CERO ASUNCIONES sobre el tipo de financiación (VALIDAR ANTES DE CONCLUIR):**
   - Si el usuario dice *"un préstamo"* sin especificar de qué tipo, **PROHIBIDO** asumir o titular un bloque dando por hecho que se trata de un **préstamo personal**.
   - **PRIMERO pregunta expresamente** qué tipo de préstamo contempla (*¿préstamo personal, hipoteca, pignoración de activos o préstamo familiar/entre particulares?*).
   - Solo después (y en tono claramente condicional: *"Si te refirieras a un préstamo personal, ten en cuenta que..."*) advierte del riesgo de DTI (30–35 %) y CIRBE. Nunca des un veredicto cerrado rechazando su estrategia antes de confirmar qué tipo de préstamo está pensando.
4. **Transparencia total en el origen de las cifras de mercado:**
   - Distingue **siempre** de forma explícita qué porcentajes o precios provienen de **las cifras que el propio usuario ha indicado**, cuáles son **rangos generales orientativos** del mercado/framework y cuáles son **datos oficiales contrastados**. Nunca repitas las cifras del usuario presentándolas como estadísticas oficiales propias.
5. **Zonas tensionadas en estrategia de inversión (OBLIGATORIO si indica municipio/barrio):** Siempre que el usuario mencione un municipio o barrio concreto (ej. Vallecas, Talavera, Alcalá, Barcelona), confirma **desde el primer turno** en 1 frase directa si está o no declarado zona de mercado residencial tensionado según los datos oficiales vigentes (citando *resoluciones autonómicas publicadas en el BOE / registro MIVAU*, **JAMÁS** rutas o nombres de archivos internos `.md`).
""",
    },
    "fiscalidad": {
        "id": "fiscalidad",
        "label": "Fiscalidad Inmobiliaria",
        "icon": "🧾",
        "priority_folders": (
            "05_Fiscalidad_y_Financiacion",
            "06_Estrategia_Inversion_y_Mercado",
            "04_Datos_Volatiles_y_CCAA",
        ),
        "requires_legal_triage": False,
        "prompt": """
## ESPECIALISTA ACTIVO: 🧾 FISCALIDAD INMOBILIARIA (ESPAÑA)
Tu foco en este turno es la fiscalidad inmobiliaria en España: **IRPF del alquiler** (Ley 35/2006 y RD 439/2007), gastos deducibles, amortización del 3 %, reducciones del Art. 23.2 LIRPF, **ITP y AJD** (RDL 1/1993 y Valor de Referencia de Catastro), **IRNR (Modelo 210)** para no residentes, y encuadre general de **Impuesto sobre Sociedades / Comunidad de Bienes / Patrimonio**.

REGLAS ESPECÍFICAS DE ESTE ESPECIALISTA:
1. **Confirmar siempre perfil fiscal antes de calcular:** Distingue Persona Física residente (IRPF) vs. Persona Física no residente (IRNR Modelo 210, sin reducciones IRPF; diferencia UE/EEE con gastos deducibles vs. extracomunitario) vs. Persona Jurídica/SL (Impuesto sobre Sociedades, sin reducciones de vivienda habitual del IRPF) vs. Comunidad de Bienes (atribución de rentas).
2. **Alquiler por habitaciones — Criterio DGT completo desde el primer momento:**
   - **NUNCA** sugieras que el alquiler por habitaciones pierde automáticamente la reducción fiscal.
   - Explica desde el principio el criterio vigente de la Dirección General de Tributos (consulta vinculante **V2457-25** y Art. 23.2 LIRPF): **SÍ puede aplicarse la reducción del rendimiento neto positivo** (50 % general o porcentajes superiores si se cumplen requisitos adicionales) **siempre que se acredite que la habitación satisface la necesidad permanente de vivienda habitual** del arrendatario (contrato redactado como vivienda habitual sujeto a LAU, empadronamiento y residencia principal). Si son contratos de temporada o no se acredita uso habitual permanente, **se pierde la reducción**.
3. **Visión de cartera completa del contribuyente (OBLIGATORIO si tiene varias viviendas):** Si en `<perfil_usuario_persistente>` consta `viviendas_total_espana` > 1 (ej. varias viviendas en alquiler tradicional) y pregunta por su declaración de la renta personal al alquilar una bajo otra modalidad (ej. habitaciones), dedica **SIEMPRE un apartado breve específico a su cartera completa**: cómo tributa cada inmueble por separado en su misma declaración de IRPF (sus viviendas en alquiler tradicional con su reducción de vivienda habitual vs. la vivienda por habitaciones y sus requisitos de permanencia).
4. **Cálculos paso a paso verificados:**
   - *IRPF alquiler:* Ingresos íntegros − Gastos deducibles (recordando límite de intereses + conservación/reparación y exceso compensable a 4 años) − Amortización 3 % sobre el mayor entre coste de adquisición satisfecho o valor catastral (excluyendo suelo) = Rendimiento Neto → Reducción aplicable (solo si rendimiento neto positivo y vivienda habitual) = Rendimiento Neto Reducido.
   - *ITP compra:* Base = el **mayor** entre precio escriturado y **Valor de Referencia de Catastro**; tipo según CCAA del inmueble.
   - Si pregunta por deducciones autonómicas, tipos reducidos de ITP, Impuesto sobre Sociedades, EDAV o Patrimonio no detallados en la base documental, contrasta con búsqueda web oficial y/o remite con transparencia al BOE/consejería autonómica o asesor fiscal colegiado.
""",
    },
    "legal_arrendamientos": {
        "id": "legal_arrendamientos",
        "label": "Legal y Arrendamientos",
        "icon": "⚖️",
        "priority_folders": (
            "01_Normativa_Estatal_Vigente",
            "02_Jurisprudencia_y_Criterios",
            "03_Plantillas_Accionables",
            "04_Datos_Volatiles_y_CCAA",
        ),
        "requires_legal_triage": True,
        "prompt": """
## ESPECIALISTA ACTIVO: ⚖️ DERECHO INMOBILIARIO Y ARRENDAMIENTOS URBANOS
Tu foco en este turno es la normativa jurídica española de arrendamientos y propiedad: **LAU consolidada**, **Ley 12/2023 por el Derecho a la Vivienda**, **RDL 29/2026**, **Código Civil**, **LEC** (desahucios y enervación), **LPH** (comunidad de propietarios), **IRAV**, **zonas tensionadas** y **fianzas autonómicas**.

REGLAS ESPECÍFICAS DE ESTE ESPECIALISTA:
1. **Persona Física vs. Jurídica en LAU (Arts. 9 y 10):**
   - Persona física → duración mínima obligatoria **5 años** (puede recuperar por necesidad propia/familiar Art. 9.3 si consta expresamente en contrato).
   - Persona jurídica (SL/SA/entidad) → duración mínima obligatoria **7 años** (NO puede recuperar por necesidad familiar del Art. 9.3).
   - Plazos contados SIEMPRE desde la **fecha de firma/inicio del contrato** (o puesta a disposición posterior), NUNCA desde una anualidad intermedia ni desde hoy.
2. **Bloqueo suave de triaje legal:** Si falta un dato imprescindible que cambia la ley (fecha de firma, persona física vs. jurídica, tipo de alquiler, o distinguir actualización unilateral Art. 18 vs. adenda pactada Art. 6 vs. nuevo contrato Art. 10.1/RDL 29/2026), **NO emitas veredictos cerrados** hasta confirmarlo. Haz 1-2 preguntas claras y ofrece la opción de subir el contrato/burofax en memoria.
3. **Regla estricta y Anti-Trampa de Gran Tenedor (Art. 3.k Ley 12/2023):**
   - Solo pregunta por Gran Tenedor cuando `<estado_motor_calificacion_legal>` indique `preguntar_gran_tenedor_ahora: true` (zona tensionada, desahucio Art. 439.6 LEC o prórroga por vulnerabilidad Art. 10.2 LAU). Si es `false`, **PROHIBIDO** preguntar por nº de viviendas o 1.500 m².
   - Cuando sí aplica: **PROHIBIDO** descartar Gran Tenedor (`false`) con un dato geográfico parcial. Exige confirmar los **3 umbrales**: (1) **≤10 inmuebles residenciales en toda España** (incluyendo vivienda habitual, alquiler tradicional, turísticas y habitaciones; excluyendo garajes, trasteros y locales), (2) **≤1.500 m² construidos residenciales** en España, y (3) en zona tensionada con umbral rebajado (ej. Cataluña), **<5 viviendas** en esa zona tensionada. Si hay copropiedad/proindiviso, avisa que los m² computan por cuota y el nº de inmuebles presenta criterios dispares en Audiencias/CCAA.
4. **Autoridad directa en Zonas Tensionadas:** Comprueba los datos oficiales de zonas tensionadas y responde con claridad directa (*"Sí, Terrassa está declarada zona tensionada por resolución oficial en el BOE"* / *"No, Madrid no es zona tensionada"*), **NUNCA** citando rutas o nombres de archivos internos `.md`.
5. **Precisión en matices y plazos procesales:**
   - Verifica literalmente cada plazo con el artículo recuperado.
   - Separa siempre apartados/figuras distintas (ej. Art. 10.2 prórroga vulnerabilidad hasta 1 año vs. Art. 10.3 prórroga zona tensionada hasta 3 años; fianza legal vs. garantía adicional; conservación Art. 21 vs. mejora Art. 19; desistimiento antes vs. después del mes 6 Art. 11).
   - Separa siempre **plazo práctico recomendado** en una carta/burofax (ej. 7-10 días) del **plazo legal imperativo** (ej. **30 días** antes de demandar para impedir la enervación conforme al Art. 22.4 LEC), garantizando coherencia absoluta entre explicación y borrador `[DOCUMENT]`.
6. **Escalado obligatorio a abogado colegiado:** En impagos acumulados/desahucio, okupación, vulnerabilidad, demanda judicial recibida o reclamación >2.000 €.
""",
    },
}


# ---------------------------------------------------------------------------
# SEÑALES DE ENRUTAMIENTO DETERMINISTA (0 ms de latencia extra)
# ---------------------------------------------------------------------------

DOMAIN_SIGNALS: Dict[str, List[Tuple[str, float]]] = {
    "operativa_gestion": [
        ("zazume", 4.0),
        ("alquiler seguro", 3.5),
        ("gestor de propiedades", 3.5),
        ("gestion de propiedades", 3.5),
        ("property manager", 3.5),
        ("fuera del horario", 3.5),
        ("horario laboral", 3.0),
        ("fin de semana", 2.0),
        ("emergencia", 3.0),
        ("urgencia", 2.2),
        ("incidencia", 2.8),
        ("incidencias", 2.8),
        ("bote sifonico", 3.0),
        ("inundando", 2.8),
        ("inundacion", 2.5),
        ("desague", 2.5),
        ("fontanero", 2.5),
        ("fontaneria", 2.5),
        ("cerrajero", 2.5),
        ("electricista", 2.5),
        ("averia", 2.2),
        ("seguro de hogar", 2.5),
        ("telefono del seguro", 3.5),
        ("dar parte", 3.0),
        ("abrir incidencia", 3.5),
        ("abran incidencias", 3.5),
        ("estoy viajando", 2.0),
        ("me acaba de llamar un inquilino", 3.0),
        ("nos contacte", 2.0),
        ("protocolo", 2.0),
        ("sin tiempo de gestionar", 3.0),
    ],
    "inversion_financiacion": [
        ("hipotecas en paralelo", 5.0),
        ("en paralelo", 3.5),
        ("flipping", 3.5),
        ("roce", 3.5),
        ("cashflow", 3.5),
        ("cash flow", 3.5),
        ("rentabilidad bruta", 3.5),
        ("rentabilidad neta", 3.5),
        ("rentabilidad", 2.8),
        ("primera inversion", 3.5),
        ("inversion inmobiliaria", 3.5),
        ("invertir", 2.8),
        ("inversion", 2.5),
        ("inversor", 2.2),
        ("ticket bajo", 3.5),
        ("patrimonial", 2.0),
        ("revalorizacion", 2.5),
        ("hipoteca", 3.0),
        ("hipotecas", 3.0),
        ("financiacion", 3.0),
        ("financiar", 3.0),
        ("financio", 3.0),
        ("prestamo", 2.8),
        ("cirbe", 3.5),
        ("dti", 3.5),
        ("ltv", 3.5),
        ("fein", 3.0),
        ("lcci", 3.0),
        ("apalancamiento", 3.5),
        ("tipo de interes", 2.8),
        ("cuota mensual", 2.5),
        ("cuotas", 2.0),
        ("entrada", 1.5),
        ("capital propio", 3.0),
        ("liquidez", 2.2),
        ("pignoracion", 3.5),
        ("subrogacion", 3.0),
        ("house hacking", 3.5),
        ("rent to rent", 3.5),
        ("he encontrado un piso", 3.0),
        ("estoy mirando en", 2.8),
        ("estudiando mucho las zonas", 3.5),
        ("donde invertir", 3.5),
        ("comprar un piso", 2.5),
        ("aglutinar", 2.0),
    ],
    "fiscalidad": [
        ("irpf", 4.0),
        ("hacienda", 3.2),
        ("aeat", 3.5),
        ("dgt", 3.5),
        ("consulta vinculante", 3.5),
        ("tributos", 3.2),
        ("v2457", 4.0),
        ("desgravacion", 3.5),
        ("desgravar", 3.5),
        ("declaracion de la renta", 3.5),
        ("reduccion fiscal", 3.8),
        ("reduccion del 50", 3.5),
        ("reduccion del 60", 3.5),
        ("deducir", 3.0),
        ("deducible", 3.0),
        ("amortizacion", 3.2),
        ("itp", 3.5),
        ("ajd", 3.5),
        ("valor de referencia", 3.5),
        ("impuesto", 2.8),
        ("impuestos", 2.8),
        ("fiscalidad", 3.5),
        ("fiscal", 2.5),
        ("residente fiscal", 2.5),
        ("irnr", 4.0),
        ("modelo 210", 4.0),
        ("impuesto sobre sociedades", 4.0),
        ("impuesto de sociedades", 4.0),
        ("sociedad patrimonial", 3.0),
        ("edav", 3.5),
        ("patrimonio", 2.2),
        ("plusvalia", 3.0),
        ("iva ", 2.5),
    ],
    "legal_arrendamientos": [
        ("lau", 3.8),
        ("ley 12/2023", 4.0),
        ("rdl 29/2026", 4.0),
        ("29/2026", 4.0),
        ("arrendamientos urbanos", 3.5),
        ("subir la renta", 3.5),
        ("subir el alquiler", 3.5),
        ("subida de renta", 3.5),
        ("actualizar la renta", 3.5),
        ("actualizacion de renta", 3.5),
        ("irav", 3.8),
        ("ipc", 2.8),
        ("adenda", 3.2),
        ("novacion", 3.2),
        ("no renovar", 3.5),
        ("no renovarle", 3.5),
        ("prorroga", 3.5),
        ("preaviso", 3.2),
        ("vence el contrato", 3.5),
        ("finalizar contrato", 3.5),
        ("recuperar la vivienda", 3.5),
        ("necesidad propia", 3.5),
        ("desistimiento", 3.5),
        ("se marcha antes", 3.0),
        ("fianza", 3.2),
        ("devolver la fianza", 3.5),
        ("garantia adicional", 3.2),
        ("desahucio", 4.0),
        ("impago", 3.5),
        ("impagos", 3.5),
        ("no paga", 3.5),
        ("sin pagar", 3.5),
        ("moroso", 3.5),
        ("burofax", 3.5),
        ("enervacion", 3.8),
        ("okupa", 4.0),
        ("okupacion", 4.0),
        ("vulnerabilidad", 3.5),
        ("conciliacion", 3.5),
        ("intermediacion", 3.2),
        ("gran tenedor", 4.0),
        ("zona tensionada", 3.5),
        ("serpavi", 3.8),
        ("comunidad de propietarios", 3.2),
        ("derrama", 3.0),
        ("estatutos", 2.8),
        ("vivienda turistica", 3.0),
        ("vivienda de uso turistico", 3.2),
        ("empadron", 2.5),
        ("contrato de alquiler", 2.5),
        ("clausula", 2.8),
        ("subarriendo", 3.2),
        ("cesion", 2.5),
        ("lph", 3.5),
        ("lec", 3.0),
    ],
}


EXPLICIT_CASE_SWITCH_PHRASES = (
    "otro asunto",
    "asunto distinto",
    "totalmente distinto",
    "cambiando de tema",
    "cambio de tema",
    "cambiando de asunto",
    "aparte de esto",
    "dejando esto aparte",
    "dejando eso aparte",
    "pasando a otro",
    "pasando a otra cosa",
    "otra consulta distinta",
    "nueva consulta",
    "otro caso",
    "otro tema",
    "sin relacion con",
    "nada que ver con lo anterior",
    "olvidemos lo anterior",
    "cambiemos de tema",
)

NEW_PROPERTY_INTRO_PHRASES = (
    "he encontrado un piso",
    "he encontrado una vivienda",
    "he visto un piso",
    "he visto una vivienda",
    "estoy mirando un piso",
    "estoy mirando pisos",
    "estoy mirando en",
    "he estado mirando en",
    "he estado estas",
    "estudiando mucho las zonas",
    "estoy pensando en comprar",
    "quiero comprar un piso",
    "quiero comprar otro piso",
    "para una primera inversion",
    "una pregunta: he encontrado",
    "tengo otra propiedad distinta",
)

CONCEPTUAL_QUESTION_PREFIXES = (
    "que es para ti",
    "que es ",
    "que son ",
    "que significa ",
    "a que llamas ",
    "a que te refieres con ",
    "explicame que es ",
    "me explicas que es ",
    "definicion de ",
    "como funciona ",
)

OPERATIONAL_ANAPHORA = (
    "zazume", "seguro", "bano", "agua", "bote", "desague", "inund", "averia",
    "emergencia", "urgencia", "incidencia", "gestor", "horario", "fin de semana",
    "fontaner", "parte", "ese piso", "esa vivienda", "este piso", "el inquilino",
)


def is_conceptual_question(user_input: str) -> bool:
    """Detecta preguntas breves de definición o concepto (ej. '¿qué es para ti hipotecas en paralelo?')."""
    norm = _norm(user_input).strip().lstrip("¿¡?!")
    if not norm or len(norm) > 220:
        return False
    return any(norm.startswith(p) or f" {p}" in norm for p in CONCEPTUAL_QUESTION_PREFIXES)


def score_domains(user_input: str) -> Dict[str, float]:
    """Puntúa cada uno de los 4 especialistas para un mensaje concreto."""
    norm = _norm(user_input)
    scores = {k: 0.0 for k in SPECIALIST_META.keys()}
    if not norm:
        return scores

    for domain, pairs in DOMAIN_SIGNALS.items():
        for phrase, weight in pairs:
            if phrase in norm:
                scores[domain] += weight

    # Desambiguar consultas cortas de código DGT (ej. V2457-25) -> fiscalidad
    if re.search(r"\bv\d{3,4}-\d{2}\b", norm):
        scores["fiscalidad"] += 4.5
    # Desambiguar referencias de artículos LIRPF vs LAU/LEC
    if re.search(r"\bart(?:iculo)?\.?\s*(?:21|22|23)\b", norm) and any(
        w in norm for w in ("irpf", "renta", "reduccion", "amortizacion", "deducir", "hacienda")
    ):
        scores["fiscalidad"] += 3.0
    if re.search(r"\bart(?:iculo)?\.?\s*(?:9|10|11|17|18|19|27|36|439)\b", norm):
        scores["legal_arrendamientos"] += 3.0

    return scores


def detect_case_switch(
    user_input: str,
    current_profile: Optional[Dict[str, Any]] = None,
    prev_specialists: Optional[List[str]] = None,
    new_scores: Optional[Dict[str, float]] = None,
    has_prior_turns: bool = False,
) -> Tuple[bool, str]:
    """
    Detecta de forma determinista cuándo el usuario abre un NUEVO caso/inmueble distinto
    al que se estaba tratando en la misma sesión, para limpiar `caso_actual` y evitar
    contaminación cruzada (ej. arrastrar 'no tienes seguro' o 'Zazume' a otra inversión).
    """
    if not has_prior_turns or not user_input:
        return False, ""

    norm = _norm(user_input).strip()
    if is_conceptual_question(user_input):
        # Una duda conceptual puntual no debe borrar ni contaminar el caso ni el perfil
        return False, ""

    # 1. Cambio explícito anunciado por el usuario ("Vamos por otro asunto totalmente distinto...")
    for phrase in EXPLICIT_CASE_SWITCH_PHRASES:
        if phrase in norm:
            return True, f"cambio_explicito:{phrase}"

    scores = new_scores if new_scores is not None else score_domains(user_input)
    prev = list(prev_specialists or [])
    profile = current_profile or {}

    # 2. El usuario presenta una nueva oportunidad/inmueble para comprar
    has_new_prop_intro = any(p in norm for p in NEW_PROPERTY_INTRO_PHRASES)
    if has_new_prop_intro:
        # Si veníamos de operativa (Zazume/avería) o ya había otro municipio/caso activo -> nuevo caso
        if prev == ["operativa_gestion"]:
            return True, "nuevo_inmueble_desde_operativa"
        prev_muni = _norm(str(profile.get("municipio_inmueble") or ""))
        if prev_muni and prev_muni not in norm:
            return True, "nuevo_inmueble_otra_ubicacion"
        if profile.get("hechos_caso") or profile.get("hechos_clave"):
            return True, "nueva_oportunidad_inmobiliaria"

    # 3. Salto desde una consulta puramente operativa (ej. Zazume/seguro) hacia inversión, fiscalidad o legal
    if prev == ["operativa_gestion"] and len(norm) >= 55:
        top_non_op = max(
            scores.get("inversion_financiacion", 0.0),
            scores.get("fiscalidad", 0.0),
            scores.get("legal_arrendamientos", 0.0),
        )
        op_score = scores.get("operativa_gestion", 0.0)
        mentions_prior_op = any(w in norm for w in OPERATIONAL_ANAPHORA)
        if top_non_op >= 4.0 and op_score < 2.0 and not mentions_prior_op:
            return True, "salto_desde_operativa_a_otro_dominio"

    return False, ""


def route_specialists(
    user_input: str,
    prev_specialists: Optional[List[str]] = None,
    case_switched: bool = False,
) -> Dict[str, Any]:
    """
    Selecciona 1 especialista principal y, si el caso es genuinamente híbrido,
    hasta 1 especialista secundario.
    """
    scores = score_domains(user_input)
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_id, top_score = ranked[0]
    second_id, second_score = ranked[1]

    # Pregunta o respuesta corta de seguimiento en el mismo caso -> heredar especialistas del caso
    if not case_switched and prev_specialists and top_score < 3.0:
        active = list(prev_specialists)[:2]
        # Si aun siendo seguimiento añade una señal secundaria clara (ej. usuario responde 'reducción fiscal'), incorporarla
        if top_score >= 2.2 and top_id not in active and len(active) < 2:
            # No mezclar operativa_gestion con otros dominios si el caso previo no era operativo
            if not (top_id == "operativa_gestion" and "operativa_gestion" not in active):
                active.append(top_id)
        return {
            "active_ids": active,
            "primary_id": active[0],
            "scores": scores,
            "inherited": True,
            "conceptual": is_conceptual_question(user_input),
        }

    # Si no hubo ninguna señal clara (ej. saludo o consulta muy abierta) -> Legal + Inversión en modo general ligero
    if top_score < 1.5:
        active = ["legal_arrendamientos"]
        return {
            "active_ids": active,
            "primary_id": active[0],
            "scores": scores,
            "inherited": False,
            "conceptual": is_conceptual_question(user_input),
        }

    active = [top_id]

    # Regla de aislamiento de Operativa: si el turno es claramente Operativa (ej. emergencia Zazume),
    # NO activar Legal/Fiscal/Inversión a menos que haya una señal muy fuerte (>= 5.0) de otro dominio.
    if top_id == "operativa_gestion":
        if second_score >= 5.0:
            active.append(second_id)
    else:
        # En Inversión / Fiscalidad / Legal sí permitimos casos híbridos (ej. Vallecas = Inversión + Fiscalidad),
        # pero NO metemos Operativa como secundario salvo señal muy clara (>= 5.0)
        if second_id == "operativa_gestion":
            if second_score >= 5.0:
                active.append(second_id)
        elif second_score >= 3.0 and second_score >= top_score * 0.30:
            active.append(second_id)

    # Si es seguimiento del mismo caso (no cambio de caso) y el especialista previo principal es complementario
    # (ej. Turno 1 era Inversión Vallecas y Turno 2 el usuario contesta mencionando IRPF/habitaciones),
    # mantener el vínculo híbrido (máximo 2 especialistas).
    if not case_switched and prev_specialists and not is_conceptual_question(user_input):
        prev_primary = prev_specialists[0]
        if prev_primary not in active and prev_primary != "operativa_gestion" and len(active) < 2:
            # Solo heredar si el turno actual es una respuesta de seguimiento (no una pregunta autónoma totalmente nueva)
            if len(_norm(user_input)) < 320 and prev_primary in ("inversion_financiacion", "fiscalidad", "legal_arrendamientos"):
                active.append(prev_primary)

    return {
        "active_ids": active[:2],
        "primary_id": active[0],
        "scores": scores,
        "inherited": False,
        "conceptual": is_conceptual_question(user_input),
    }


def format_specialists_badge(active_ids: List[str]) -> str:
    """Devuelve una etiqueta legible para la UI y el log QA (ej. '📈 Inversión y Financiación · 🧾 Fiscalidad Inmobiliaria')."""
    labels = []
    for sid in active_ids or []:
        meta = SPECIALIST_META.get(sid)
        if meta:
            labels.append(f"{meta['icon']} {meta['label']}")
    return " · ".join(labels) if labels else "⚖️ Asesor Inmobiliario Integral"


def get_priority_kb_folders(active_ids: List[str]) -> Tuple[str, ...]:
    """Devuelve las carpetas prioritarias de knowledge_base para los especialistas activos."""
    folders: List[str] = []
    for sid in active_ids or []:
        meta = SPECIALIST_META.get(sid)
        if not meta:
            continue
        for f in meta.get("priority_folders", ()):
            if f not in folders:
                folders.append(f)
    return tuple(folders)


def build_specialist_prompt_section(active_ids: List[str], conceptual: bool = False) -> str:
    """Compone dinámicamente las instrucciones exclusivas de los especialistas activos en este turno."""
    blocks = []
    for sid in active_ids or ["legal_arrendamientos"]:
        meta = SPECIALIST_META.get(sid)
        if meta:
            blocks.append(meta["prompt"].strip())

    if conceptual:
        blocks.append(
            "## MODO PREGUNTA CONCEPTUAL / DEFINICIÓN DIRECTA\n"
            "El usuario está preguntando por el significado o funcionamiento de un concepto concreto del sector "
            "(ej. 'hipotecas en paralelo', 'IRAV', 'ROCE', 'enervación').\n"
            "- Responde de forma **directa, experta y clara** desde la primera frase usando la acepción real del sector inmobiliario español.\n"
            "- Explica cómo funciona en la práctica, sus riesgos/matices clave y pon un ejemplo breve.\n"
            "- NO fuerces un 'Resumen de tu caso' artificial ni hagas preguntas de triaje innecesarias si solo pide entender el concepto."
        )

    return "\n\n".join(blocks)
