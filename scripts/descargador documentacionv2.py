import argparse
import json
import re
from datetime import date
from pathlib import Path
import requests
from bs4 import BeautifulSoup


def obtener_raiz_proyecto() -> Path:
    """Sube desde la ubicación del script hasta encontrar la raíz del repo (.git)."""
    ruta = Path(__file__).resolve().parent
    for carpeta in [ruta, *ruta.parents]:
        if (carpeta / ".git").exists():
            return carpeta
    return ruta


RAIZ_PROYECTO = obtener_raiz_proyecto()
DIR_KB = RAIZ_PROYECTO / "knowledge_base"
ARCHIVO_MANIFEST = DIR_KB / "manifest.json"

CARPETAS_PROYECTO = [
    "01_Normativa_Estatal_Vigente",
    "02_Jurisprudencia_y_Criterios",
    "03_Plantillas_Accionables",
    "04_Datos_Volatiles_y_CCAA",
    "05_Fiscalidad_y_Financiacion",
    "06_Estrategia_Inversion_y_Mercado",
]

HEADERS_XML = {"Accept": "application/xml", "User-Agent": "RAG-Inmobiliario-ETL/4.0"}
HEADERS_HTML = {"User-Agent": "RAG-Inmobiliario-ETL/4.0"}

# Resoluciones trimestrales oficiales del BOE de Zonas de Mercado Residencial Tensionado
# (Secretaría de Estado de Vivienda y Agenda Urbana, Art. 18 Ley 12/2023).
# Puedes añadir aquí cualquier nuevo ID trimestral si el buscador HTML del BOE cambia parámetros.
RESOLUCIONES_ZONA_TENSIONADA_BASE = [
    "BOE-A-2024-5214",   # Q1 2024 - 14 mar 2024 (Cataluña, primeros 140 municipios)
    "BOE-A-2024-20576",  # Q3 2024 - 8 oct 2024 (Cataluña, ampliación 131 municipios)
    "BOE-A-2025-1721",   # Q4 2024 - 28 ene 2025 (País Vasco - Errenteria)
    "BOE-A-2025-8636",   # Q1 2025 - 29 abr 2025 (País Vasco - Lasarte-Oria, Zumaia, Barakaldo, Irun)
    "BOE-A-2025-15728",  # Q2 2025 - 28 jul 2025 (Navarra + A Coruña)
    "BOE-A-2025-21901",  # Q3 2025 - 29 oct 2025 (ampliaciones Q3 2025)
    "BOE-A-2026-2448",   # Q4 2025 - 30 ene 2026 (País Vasco - Hernani, Lezo, Tolosa)
    "BOE-A-2026-9175",   # Q1 2026 - 23 abr 2026 (ampliaciones Q1 2026)
    "BOE-A-2026-16532",  # Q2 2026 - 24 jul 2026 (Asturias + Galicia + ampliaciones Q2 2026)
    "BOE-A-2026-23088",  # Q3 2026 - 29 oct 2026 (País Vasco - Sopela, Urduliz, Bergara)
]

# Catálogo unificado de normas consolidadas del BOE (Legal + Fiscal + Hipotecario)
NORMAS = [
    # --- 01. NORMATIVA LEGAL DE ALQUILER ---
    {
        "carpeta": "01_Normativa_Estatal_Vigente",
        "boe_id": "BOE-A-1994-26003",
        "archivo": "01_LAU_consolidada.md",
        "nombre": "Ley 29/1994, de Arrendamientos Urbanos (LAU)",
        "temas": ["vivienda_habitual", "temporada", "fianza", "desistimiento", "renta"],
        "articulos_permitidos": None,
    },
    {
        "carpeta": "01_Normativa_Estatal_Vigente",
        "boe_id": "BOE-A-2023-12203",
        "archivo": "02_Ley_Vivienda_2023.md",
        "nombre": "Ley 12/2023, por el Derecho a la Vivienda",
        "temas": ["zona_tensionada", "gran_tenedor", "irpf", "prorroga"],
        "articulos_permitidos": None,
    },
    {
        "carpeta": "01_Normativa_Estatal_Vigente",
        "boe_id": "BOE-A-1889-4763",
        "archivo": "03_Codigo_Civil_Arrendamientos.md",
        "nombre": "Código Civil Español (Arts. 1542-1582 Arrendamientos)",
        "temas": ["arrendamiento_supletorio", "obligaciones", "daños"],
        "articulos_permitidos": set(range(1542, 1583)),
    },
    {
        "carpeta": "01_Normativa_Estatal_Vigente",
        "boe_id": "BOE-A-2000-323",
        "archivo": "04_LEC_Desahucios.md",
        "nombre": "Ley 1/2000, de Enjuiciamiento Civil (Arts. de Desahucio y Enervación)",
        "temas": ["desahucio", "impago", "enervacion", "vulnerabilidad", "juicio_verbal"],
        "articulos_permitidos": {22, 250, 549} | set(range(437, 448)),
    },
    {
        "carpeta": "01_Normativa_Estatal_Vigente",
        "boe_id": "BOE-A-1960-10906",
        "archivo": "05_LPH_Propiedad_Horizontal.md",
        "nombre": "Ley 49/1960, sobre Propiedad Horizontal",
        "temas": ["comunidad_propietarios", "vivienda_turistica", "obras"],
        "articulos_permitidos": None,
    },
    # Nota: BOE-A-2026-20822 (RDL 28/2026) fue derogado / no convalidado (estatus_derogacion='S' en BOE)
    # y por tanto NO se incluye como normativa vigente en el RAG.
    {
        "carpeta": "01_Normativa_Estatal_Vigente",
        "boe_id": "BOE-A-2026-20823",
        "archivo": "06_RDL_29_2026_Vivienda.md",
        "nombre": "Real Decreto-ley 29/2026, de 6 de octubre, de medidas urgentes para la protección de la función social de la vivienda",
        "temas": ["tope_renta", "prorroga_extraordinaria", "irpf_100", "alquiler_temporal", "habitaciones", "desahucios", "tanteo_retracto", "iva_corta_duracion"],
        "articulos_permitidos": None,
    },
    {
        "carpeta": "01_Normativa_Estatal_Vigente",
        "boe_id": "BOE-A-1889-4763",
        "archivo": "07_Codigo_Civil_Compraventa_y_Arras.md",
        "nombre": "Código Civil Español (Arts. 1445-1505 Compraventa, Arras y Saneamiento)",
        "temas": ["compraventa", "arras", "vicios_ocultos", "saneamiento", "entrega_posesion"],
        "articulos_permitidos": set(range(1445, 1506)),
    },
    # --- 05. FISCALIDAD Y FINANCIACIÓN ---
    {
        "carpeta": "05_Fiscalidad_y_Financiacion",
        "boe_id": "BOE-A-2006-20764",
        "archivo": "01_LIRPF_Alquileres.md",
        "nombre": "Ley 35/2006 del IRPF (Rendimientos capital inmobiliario)",
        "temas": ["irpf", "base_imponible", "gastos_deducibles", "reducciones", "imputacion_rentas"],
        "articulos_permitidos": {21, 22, 23, 24, 27, 85},
    },
    {
        "carpeta": "05_Fiscalidad_y_Financiacion",
        "boe_id": "BOE-A-2007-6820",
        "archivo": "02_Reglamento_IRPF_Amortizacion.md",
        "nombre": "Reglamento del IRPF - RD 439/2007 (Amortización y gastos)",
        "temas": ["amortizacion_3_por_ciento", "muebles", "saldos_dudoso_cobro", "gastos_deducibles"],
        "articulos_permitidos": {13, 14, 15, 16},
    },
    {
        "carpeta": "05_Fiscalidad_y_Financiacion",
        "boe_id": "BOE-A-1993-25359",
        "archivo": "03_Ley_ITP_AJD_Compra.md",
        "nombre": "Ley del ITP y AJD - RDL 1/1993 (Base imponible y valor de referencia)",
        "temas": ["itp", "valor_referencia", "impuestos_compra"],
        "articulos_permitidos": {7, 8, 9, 10, 11, 12},
    },
    {
        "carpeta": "05_Fiscalidad_y_Financiacion",
        "boe_id": "BOE-A-2019-3814",
        "archivo": "04_LCCI_Hipotecas.md",
        "nombre": "Ley 5/2019 de Crédito Inmobiliario (Gastos hipoteca y amortización)",
        "temas": ["hipoteca", "gastos_hipoteca", "amortizacion_anticipada", "fein"],
        "articulos_permitidos": {14, 20, 21, 22, 23, 24},
    },
]

# Guías curadas en Markdown para 06_Estrategia_Inversion_y_Mercado
GUIAS_ESTRATEGIA = {
    "01_guia_calculo_irpf_alquiler.md": """---
tipo: guia_practica_fiscal
ambito: ES_NACIONAL
temas: [irpf, base_imponible, gastos_deducibles, amortizacion, reducciones]
---
# Guía práctica: Cómo declarar el alquiler en el IRPF y calcular la base imponible

## 1. Fórmula paso a paso
1. **Ingresos íntegros:** Total de rentas cobradas en el año natural (más gastos repercutidos al inquilino si los paga al propietario).
2. **(-) Gastos deducibles:**
   - **Grupo A (con límite):** Intereses de hipoteca/préstamo de compra + gastos de reparación y conservación (pintura, fontanería, sustitución de caldera). *Límite:* La suma de este grupo no puede superar los ingresos íntegros del año; el exceso se deduce en los **4 años siguientes**.
   - **Grupo B (sin límite):** IBI, tasa de basuras, comunidad de propietarios, seguro de hogar, seguro de impago, honorarios de agencia/gestoría y suministros si los paga el propietario.
3. **(-) Amortización del inmueble (3 %):** 3 % anual sobre el **mayor** de dos valores: el coste de adquisición satisfecho (precio + ITP + notaría + registro) o el valor catastral, **excluyendo siempre el valor del suelo** (se aplica el % de construcción que figura en el recibo del IBI).
   - *Mobiliario y electrodomésticos:* 10 % anual sobre su valor de compra (máximo 20 años).
4. **(=) Rendimiento Neto:** Ingresos − Gastos − Amortización.
5. **(-) Reducción por alquiler de vivienda habitual (solo si el Rendimiento Neto es positivo):**
   - **50 %** general (contratos firmados desde el 26/05/2023; 60 % para contratos anteriores).
   - **60 %** si la vivienda ha sido rehabilitada en los 2 años anteriores.
   - **70 %** si es primer alquiler en zona tensionada a jóvenes (18–35 años) o vivienda asequible.
   - **90 %** si es zona tensionada y se rebaja la renta >5 % respecto al contrato anterior.
   - **0 % (sin reducción):** Alquileres de temporada, turísticos o por habitaciones cuando no constituyan vivienda habitual del inquilino.
6. **(=) Rendimiento Neto Reducido:** Es la cifra que se suma a la **Base Imponible General** del IRPF y tributa al tipo marginal del propietario.

## 2. Días en los que el piso está vacío
- Los gastos fijos (IBI, comunidad, intereses, amortización) solo se deducen en proporción a los días que el inmueble estuvo **alquilado** (o en expectativa de alquiler con anuncios acreditables según criterio AEAT/TEAC).
- Por los días vacío a disposición del propietario, se tributa por **imputación de rentas inmobiliarias** (1,1 % del valor catastral revisado o 2 % si no está revisado).
""",
    "02_tabla_itp_y_gastos_compra_ccaa.md": """---
tipo: referencia_fiscal_autonomica
ambito: ES_CCAA
temas: [itp, impuestos_compra, gastos_compra, valor_referencia]
---
# Impuestos y gastos al comprar vivienda de segunda mano en España

## 1. Regla de oro de la base imponible (ITP)
El ITP se paga sobre el **mayor** entre el precio escriturado y el **Valor de Referencia de Catastro**. Antes de ofertar, comprobar siempre el Valor de Referencia para evitar liquidaciones complementarias.

## 2. Tipo general de ITP por Comunidad Autónoma (referencia orientativa)
| Comunidad Autónoma | Tipo general ITP | Notas clave para inversores |
| :--- | :---: | :--- |
| **Madrid** | **6 %** | Uno de los más bajos; clave al comparar Alcalá/Madrid vs. Guadalajara/Talavera. |
| **Andalucía** | **7 %** | Tipo único general simplificado. |
| **Canarias** | **6,5 %** | — |
| **País Vasco / Navarra** | **4 % – 7 %** | Depende de territorio foral y si es vivienda habitual. |
| **Murcia / Aragón / Asturias** | **8 %** | Tramos progresivos en Asturias (8–10 %) y Aragón (8–10 %). |
| **Castilla-La Mancha** | **9 %** | Aplica en **Talavera de la Reina** y **Guadalajara** (sube la necesidad de capital inicial frente a Madrid). |
| **Castilla y León / Extremadura / Galicia** | **8 % – 10 %** | Tramos según valor del inmueble. |
| **Cataluña / C. Valenciana** | **10 % – 11 %** | En Cataluña y C. Valenciana tramos superiores a partir de 1M €; atención a zonas tensionadas. |
| **Baleares / Cantabria** | **8 % – 13 %** | Escala progresiva según precio. |

*(Nota: Verificar siempre tipos reducidos o recargos autonómicos vigentes en la fecha exacta de escritura).*

## 3. Otros gastos fijos de compra (estimación)
- **Notaría + Registro de la Propiedad + Gestoría:** ~1.500 € a 2.500 € (según precio).
- **Tasación (si hay hipoteca):** ~300 € a 500 € (la paga el comprador).
- **Gastos de constitución de hipoteca (notaría, registro, gestoría, AJD):** Los paga el **banco** por Ley 5/2019 (LCCI).
- **Honorarios de agencia inmobiliaria (si los cobra al comprador):** 2 % – 5 % + IVA.
""",
    "03_framework_estrategia_inmobiliaria.md": """---
tipo: framework_inversion
ambito: ES_NACIONAL
temas: [estrategia_inversion, ticket_bajo, habitaciones, rentabilidad, cash_flow]
---
# Framework de Estrategia Inmobiliaria (Ticket Bajo vs. Patrimonial y Habitaciones)

## 1. Comparativa de modelos de inversión
| Variable | Ticket Bajo / Cash-Flow (70k–115k €) | Ticket Medio-Alto / Patrimonial (>180k €) |
| :--- | :--- | :--- |
| **Ejemplos de mercado** | Talavera de la Reina, ciudades satélite secundarias, barrios periféricos. | Madrid capital, Alcalá de Henares, Guadalajara centro, capitales dinámicas. |
| **Rentabilidad bruta típica** | 8 % – 10 % | 5 % – 6,5 % (tradicional) / 8 % – 10 % (habitaciones) |
| **Liquidez de salida (venta)** | Media-Baja (cuesta más vender rápido). | Alta (demanda constante de comprador final e inversor). |
| **Revalorización esperada** | Baja / ligada a inflación. | Media-Alta (crecimiento poblacional y empleo). |
| **Riesgo de impago / rotación** | Más alto (requiere filtro estricto y seguro de impago). | Menor (perfiles de inquilino con mayor solvencia). |

## 2. Alquiler tradicional vs. Alquiler por habitaciones
- **Tradicional:** Menos gestión, menor desgaste del inmueble y acceso a la **reducción del 50 % en IRPF** (vivienda habitual).
- **Habitaciones:** Eleva el ingreso bruto un 25–40 %, pero exige gestión intensiva (o pagar un 10–15 % + IVA a un gestor), mayor rotación y mantenimiento, y **riesgo normativo/fiscal** (tope de suma de rentas bajo RDL 29/2026 y posible pérdida de la reducción del IRPF si no es vivienda habitual).

## 3. Fórmulas de evaluación obligatorias
- **Rentabilidad Bruta (%)** = `(Renta anual / (Precio compra + gastos + impuestos + reforma)) × 100`
- **Rentabilidad Neta (%)** = `((Renta anual − IBI − Comunidad − Seguros − Mantenimiento 5% − Vacancia 5%) / Inversión total) × 100`
- **ROCE (Retorno sobre capital propio)** = `(Cash-flow anual neto tras cuota hipoteca / Capital propio aportado) × 100`
""",
    "04_reglas_financiacion_y_apalancamiento.md": """---
tipo: reglas_financiacion
ambito: ES_NACIONAL
temas: [financiacion, hipoteca, prestamo_personal, cirbe, apalancamiento, ltv]
---
# Reglas Bancarias de Financiación y Apalancamiento en España

## 1. Ratio de endeudamiento (DTI)
- Los bancos en España suelen limitar el total de cuotas mensuales (hipoteca actual + nueva hipoteca + préstamos personales + tarjetas) al **30 % – 35 % de los ingresos netos mensuales** del solicitante.
- En compras de inversión, los bancos rara vez computan el 100 % del alquiler futuro como ingreso hasta que no aparece consolidado en al menos 1–2 declaraciones de la Renta (IRPF).

## 2. Trampa crítica: Préstamo personal + Hipoteca simultánea
- **Por qué suele fallar:** Pedir un préstamo personal (ej. 50.000–80.000 € a 5–8 años al 6–8 % TIN) para comprar un piso barato y luego pedir una hipoteca para un segundo piso genera una **cuota mensual altísima** que aparece inmediatamente en **CIRBE**.
- **Consecuencia:** Esa cuota consume casi toda la capacidad de endeudamiento y provoca que el banco **deniegue la hipoteca del segundo inmueble**.
- **Alternativa habitual:** Priorizar siempre financiación hipotecaria a largo plazo (20–30 años, cuota baja) antes que préstamos personales cortos, o financiar primero el inmueble más exigente en banco.

## 3. Capital propio real necesario para invertir (Segunda vivienda / Inversión)
- **Financiación habitual (LTV):** 60 % – 70 % sobre el menor entre tasación y compraventa (hasta 80 % solo en perfiles muy solventes).
- **Liquidez real necesaria:** `30–40 % de entrada` + `ITP autonómico (6–10 %)` + `~2.500 € gastos` + `reforma/amueblado` + `colchón de seguridad (6 meses de cuotas)`.
""",
}

# Patrones de limpieza y filtrado
RE_ARTICULO = re.compile(r"^(?:Art(?:ículo|\.)?)\s+(\d+)\b", re.IGNORECASE)
RE_REDACCION_ANTERIOR = re.compile(r"^Redacción anterior\s*:", re.IGNORECASE)
RE_NOTA_HISTORIAL = re.compile(
    r"^(?:Se\s+(?:modifica|añade|deroga|deja sin efecto|renumera|suprime|declara|sustituye|actualiza|prorroga)|"
    r"Téngase en cuenta|Redactado conforme|Véase\s|Última actualización)",
    re.IGNORECASE,
)
RE_BOE_ID = re.compile(r"BOE-A-\d{4}-\d+")


def cargar_manifest() -> dict:
    if ARCHIVO_MANIFEST.exists():
        with open(ARCHIVO_MANIFEST, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def guardar_manifest(manifest: dict) -> None:
    with open(ARCHIVO_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def obtener_metadatos_boe(boe_id: str) -> dict:
    """Consulta los metadatos consolidados del BOE (incluyendo vigencia y derogación)."""
    url = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{boe_id}/metadatos"
    meta = {
        "fecha_actualizacion": None,
        "fecha_publicacion": None,
        "fecha_vigencia": None,
        "estatus_derogacion": "N",
        "vigencia_agotada": "N",
    }
    try:
        resp = requests.get(url, headers=HEADERS_XML, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, "xml")
        for campo in meta:
            nodo = soup.find(campo)
            if nodo and nodo.get_text(strip=True):
                meta[campo] = nodo.get_text(strip=True)
    except requests.RequestException as e:
        print(f"[AVISO] No se pudieron consultar metadatos de {boe_id}: {e}")
    return meta


def es_bloque_valido(titulo: str, tipo: str, articulos_permitidos: set | None) -> bool:
    titulo_lower = titulo.lower()
    if (
        not titulo
        or tipo == "preambulo"
        or "[preambulo]" in titulo_lower
        or "[derogado]" in titulo_lower
        or "(derogado)" in titulo_lower
    ):
        return False

    if articulos_permitidos is None:
        return True

    coincidencia = RE_ARTICULO.match(titulo)
    if not coincidencia:
        return False
    return int(coincidencia.group(1)) in articulos_permitidos


def extraer_parrafos_limpios(nodo) -> list[str]:
    """
    Extrae el texto legal vigente del bloque XML del BOE.
    IMPORTANTE: En los Reales Decretos-leyes que modifican otras leyes (ej. RDL 28/2026 y RDL 29/2026),
    el BOE coloca la nueva redacción de los artículos modificados dentro de <blockquote>,
    por lo que NUNCA se deben descartar los <blockquote> (solo las etiquetas <nota>).
    """
    parrafos = []
    for p in nodo.find_all("p"):
        if p.find_parent("nota"):
            continue
        clases = p.get("class") or []
        if any("nota" in c.lower() for c in clases):
            continue

        texto = " ".join(p.get_text().split())
        if not texto:
            continue

        if RE_REDACCION_ANTERIOR.match(texto):
            break
        if RE_NOTA_HISTORIAL.match(texto):
            continue

        parrafos.append(texto)
    return parrafos


def procesar_norma(norma: dict, manifest: dict, forzar: bool) -> bool:
    boe_id = norma["boe_id"]
    manifest_key = f"{boe_id}:{norma['archivo']}"
    ruta_salida = DIR_KB / norma["carpeta"] / norma["archivo"]
    ruta_relativa = str(ruta_salida.relative_to(RAIZ_PROYECTO)).replace("\\", "/")

    meta = obtener_metadatos_boe(boe_id)
    fecha_boe = meta["fecha_actualizacion"]

    # Salvaguarda crítica de RAG legal: si la norma figura derogada o con vigencia agotada en BOE,
    # NO se descarga y se elimina del directorio vigente para no contaminar respuestas.
    if meta["estatus_derogacion"] == "S" or meta["vigencia_agotada"] == "S":
        if ruta_salida.exists():
            ruta_salida.unlink()
            print(f"[DEROGADA - ELIMINADA] {ruta_relativa} ({boe_id})")
        else:
            print(f"[DEROGADA - OMITIDA] {ruta_relativa} ({boe_id})")
        manifest.pop(manifest_key, None)
        manifest.pop(boe_id, None)
        return True

    registro_previo = manifest.get(manifest_key) or manifest.get(boe_id, {})

    if (
        not forzar
        and fecha_boe
        and registro_previo.get("fecha_actualizacion_boe") == fecha_boe
        and ruta_salida.exists()
    ):
        print(f"[SIN CAMBIOS] {ruta_relativa} (BOE act.: {fecha_boe})")
        return False

    url_texto = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{boe_id}/texto"
    try:
        resp = requests.get(url_texto, headers=HEADERS_XML, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[ERROR] No se pudo descargar {boe_id}: {e}")
        return False

    soup = BeautifulSoup(resp.content, "xml")
    bloques = soup.find_all("bloque")
    if not bloques:
        print(f"[AVISO] {boe_id} no devolvió bloques de texto.")
        return False

    contenido_md = []
    contador_bloques = 0

    for bloque in bloques:
        titulo = (bloque.get("titulo") or "").strip()
        tipo = bloque.get("tipo", "")

        if not es_bloque_valido(titulo, tipo, norma["articulos_permitidos"]):
            continue

        versiones = bloque.find_all("version")
        nodo_objetivo = versiones[-1] if versiones else bloque

        parrafos = extraer_parrafos_limpios(nodo_objetivo)
        if not parrafos:
            continue

        nivel = "##" if tipo == "encabezado" else "###"
        contenido_md.append(f"{nivel} {titulo}\n")
        contenido_md.append("\n".join(parrafos) + "\n")
        contador_bloques += 1

    temas_yaml = ", ".join(norma["temas"])
    frontmatter = (
        "---\n"
        f"boe_id: {boe_id}\n"
        f'norma: "{norma["nombre"]}"\n'
        "ambito: ES_NACIONAL\n"
        f"temas: [{temas_yaml}]\n"
        f"fecha_publicacion_boe: {meta['fecha_publicacion'] or 'desconocida'}\n"
        f"fecha_vigencia_boe: {meta['fecha_vigencia'] or 'desconocida'}\n"
        f"estatus_derogacion: {meta['estatus_derogacion']}\n"
        f"fecha_actualizacion_boe: {fecha_boe or 'desconocida'}\n"
        f"fecha_descarga: {date.today().isoformat()}\n"
        f"bloques_vigentes: {contador_bloques}\n"
        "---\n\n"
        f"# {norma['nombre']} ({boe_id})\n\n"
    )

    texto_final = frontmatter + "\n".join(contenido_md)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(texto_final)

    tokens_aprox = len(texto_final) // 4
    manifest[manifest_key] = {
        "boe_id": boe_id,
        "ruta": ruta_relativa,
        "fecha_actualizacion_boe": fecha_boe,
        "ultima_descarga": date.today().isoformat(),
        "bloques_vigentes": contador_bloques,
        "tokens_aprox": tokens_aprox,
    }
    print(f"[ACTUALIZADO] {ruta_relativa} | Bloques: {contador_bloques} | ~{tokens_aprox:,} tokens")
    return True


def descubrir_resoluciones_zonas_tensionadas() -> list[str]:
    """Busca en el BOE todas las resoluciones oficiales de zonas de mercado residencial tensionado."""
    ids_encontrados = list(RESOLUCIONES_ZONA_TENSIONADA_BASE)
    url_busqueda = "https://www.boe.es/buscar/boe.php"
    params = {
        "campo[0]": "TIT",
        "dato[0]": "zonas de mercado residencial tensionado",
        "page_hits": "50",
        "sort_field[0]": "fpu",
        "sort_order[0]": "desc",
        "accion": "Buscar",
    }

    try:
        resp = requests.get(url_busqueda, params=params, headers=HEADERS_HTML, timeout=25)
        resp.raise_for_status()
        for boe_id in RE_BOE_ID.findall(resp.text):
            if boe_id not in ids_encontrados:
                ids_encontrados.append(boe_id)
    except requests.RequestException as e:
        print(f"[AVISO] Error buscando resoluciones de zonas tensionadas en BOE: {e}. Se usarán las base.")

    # Ordenar de más reciente a más antigua por año y número
    ids_encontrados.sort(reverse=True)
    return ids_encontrados


def actualizar_zonas_tensionadas(manifest: dict, forzar: bool) -> bool:
    """Descarga el XML de cada resolución oficial del BOE y compila 03_resoluciones_boe_zonas_tensionadas.md."""
    ruta_salida = DIR_KB / "04_Datos_Volatiles_y_CCAA" / "03_resoluciones_boe_zonas_tensionadas.md"
    ruta_relativa = str(ruta_salida.relative_to(RAIZ_PROYECTO)).replace("\\", "/")

    ids_resoluciones = descubrir_resoluciones_zonas_tensionadas()
    previo = manifest.get("ZONAS_TENSIONADAS", {})

    if not forzar and previo.get("resoluciones") == ids_resoluciones and ruta_salida.exists():
        print(f"[SIN CAMBIOS] {ruta_relativa} ({len(ids_resoluciones)} resoluciones indexadas)")
        return False

    secciones = []
    resoluciones_validas = []

    for boe_id in ids_resoluciones:
        url_xml = f"https://www.boe.es/diario_boe/xml.php?id={boe_id}"
        try:
            resp = requests.get(url_xml, headers=HEADERS_XML, timeout=25)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[AVISO] No se pudo descargar resolución {boe_id}: {e}")
            continue

        soup = BeautifulSoup(resp.content, "xml")
        titulo_nodo = soup.find("titulo")
        fecha_nodo = soup.find("fecha_publicacion")
        texto_nodo = soup.find("texto")

        if not titulo_nodo or not texto_nodo:
            continue

        titulo = " ".join(titulo_nodo.get_text().split())
        # Filtrar para asegurar que es una resolución de relación de zonas tensionadas (no otra norma)
        if "zona" not in titulo.lower() or "tensionado" not in titulo.lower():
            continue

        fecha_pub = fecha_nodo.get_text(strip=True) if fecha_nodo else "desconocida"
        bloques_res = [f"## {titulo} ({boe_id} | Publicado: {fecha_pub})\n"]

        # Extraer tablas (donde suelen venir los listados de municipios y vigencias)
        tablas = texto_nodo.find_all("table")
        if tablas:
            for tabla in tablas:
                filas = tabla.find_all("tr")
                for idx, fila in enumerate(filas):
                    celdas = [" ".join(c.get_text().split()) for c in fila.find_all(["th", "td"])]
                    if any(celdas):
                        bloques_res.append("| " + " | ".join(celdas) + " |")
                        if idx == 0:
                            bloques_res.append("| " + " | ".join(["---"] * len(celdas)) + " |")
                bloques_res.append("")

        # Extraer párrafos con municipios/anexos fuera de tablas
        for p in texto_nodo.find_all("p"):
            if p.find_parent("table"):
                continue
            linea = " ".join(p.get_text().split())
            if linea and len(linea) > 2:
                bloques_res.append(linea)

        secciones.append("\n".join(bloques_res) + "\n")
        resoluciones_validas.append(boe_id)

    if not secciones:
        print("[AVISO] No se pudo extraer contenido de resoluciones de zonas tensionadas.")
        return False

    frontmatter = (
        "---\n"
        "tipo: listado_oficial_zonas_tensionadas\n"
        "ambito: ES_CCAA\n"
        "temas: [zona_tensionada, municipios, tope_renta, gran_tenedor, serpavi]\n"
        f"resoluciones_boe: [{', '.join(resoluciones_validas)}]\n"
        f"fecha_actualizacion: {date.today().isoformat()}\n"
        "---\n\n"
        "# Relación Oficial de Municipios en Zona de Mercado Residencial Tensionado (BOE)\n\n"
        "> **Instrucción para el agente:** Usa este listado oficial del BOE para confirmar si un municipio "
        "está declarado zona tensionada y su periodo de vigencia. Si un municipio figura en estas resoluciones "
        "dentro de su periodo vigente, responde afirmativamente citando el ID del BOE correspondiente.\n\n"
    )

    texto_final = frontmatter + "\n---\n\n".join(secciones)
    with open(ruta_salida, "w", encoding="utf-8") as f:
        f.write(texto_final)

    tokens_aprox = len(texto_final) // 4
    manifest["ZONAS_TENSIONADAS"] = {
        "ruta": ruta_relativa,
        "resoluciones": resoluciones_validas,
        "ultima_descarga": date.today().isoformat(),
        "tokens_aprox": tokens_aprox,
    }
    print(
        f"[ACTUALIZADO] {ruta_relativa} | Resoluciones BOE: {len(resoluciones_validas)} | ~{tokens_aprox:,} tokens"
    )
    return True


def generar_guias_estrategia(forzar: bool) -> None:
    carpeta = DIR_KB / "06_Estrategia_Inversion_y_Mercado"
    print(f"\n3) Comprobando guías en {carpeta.relative_to(RAIZ_PROYECTO)} ...")
    for nombre_archivo, contenido in GUIAS_ESTRATEGIA.items():
        ruta = carpeta / nombre_archivo
        ruta_relativa = str(ruta.relative_to(RAIZ_PROYECTO)).replace("\\", "/")
        if ruta.exists() and not forzar:
            print(f"[EXISTE] {ruta_relativa} (usa --forzar para regenerar)")
            continue
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido.strip() + "\n")
        tokens_aprox = len(contenido) // 4
        print(f"[CREADO] {ruta_relativa} | ~{tokens_aprox:,} tokens")


def main():
    parser = argparse.ArgumentParser(
        description="Generador y actualizador diferencial de knowledge_base inmobiliaria (BOE + Zonas Tensionadas + Guías)."
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Fuerza la re-descarga de normativa BOE y resoluciones de zonas tensionadas (NO sobreescribe guías curadas).",
    )
    parser.add_argument(
        "--regenerar-guias",
        action="store_true",
        help="Regenera también las guías curadas de 06_Estrategia_Inversion_y_Mercado (cuidado: puede pisar ediciones manuales).",
    )
    args = parser.parse_args()

    for carpeta in CARPETAS_PROYECTO:
        (DIR_KB / carpeta).mkdir(parents=True, exist_ok=True)

    manifest = cargar_manifest()
    hubo_cambios = False

    print(f"Raíz del proyecto detectada: {RAIZ_PROYECTO}")
    print(f"Destino knowledge_base: {DIR_KB}\n")

    print("1) Comprobando normativa consolidada en la API del BOE...\n")
    for norma in NORMAS:
        if procesar_norma(norma, manifest, forzar=args.forzar):
            hubo_cambios = True

    print("\n2) Comprobando resoluciones de Zonas Tensionadas en el BOE...\n")
    if actualizar_zonas_tensionadas(manifest, forzar=args.forzar):
        hubo_cambios = True

    if hubo_cambios or not ARCHIVO_MANIFEST.exists():
        guardar_manifest(manifest)
        print(f"\nManifest actualizado en {ARCHIVO_MANIFEST.relative_to(RAIZ_PROYECTO)}")
    else:
        print("\nToda la normativa y zonas tensionadas están al día.")

    generar_guias_estrategia(forzar=args.regenerar_guias)
    print("\nProceso finalizado.")


if __name__ == "__main__":
    main()