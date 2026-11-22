import json
import os
import unicodedata
from typing import List, Dict, Union, Optional

# Importación segura para entornos donde no se requiera búsqueda externa
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

# --- CONFIGURACIÓN ---
# Ruta absoluta al índice generado (raíz del proyecto)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_INDEX_PATH = os.path.join(BASE_DIR, "knowledge_base", "video_index.json")

# Fecha límite tras la reforma RDL 29/2026 (publicados después de octubre de 2026)
POST_OCT_2026_RFC3339 = "2026-11-01T00:00:00Z"
POST_OCT_2026_PREFIX = "2026-11-01"

# Temas afectados por la reforma de octubre de 2026 que exigen vídeos posteriores a esa fecha
TEMAS_POST_OCT_2026 = (
    "subida de renta",
    "subida renta",
    "subir renta",
    "actualizar renta",
    "actualizacion renta",
    "actualizacion de renta",
    "tope renta",
    "tope de renta",
    "irav",
    "ipc",
    "prorroga",
    "prorrogas",
    "renovacion",
    "no renovar",
    "temporal",
    "temporada",
    "habitacion",
    "habitaciones",
    "rdl 29/2026",
    "29/2026",
    "zona tensionada",
)

# NOTA PARA EL DESARROLLADOR:
# Inserta tu API Key de YouTube (Google Cloud Console) en las variables de entorno
# o en .streamlit/secrets.toml como YOUTUBE_API_KEY.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")


def _normalizar_texto(texto: str) -> str:
    """Elimina tildes y pasa a minúsculas para comparaciones robustas en español."""
    if not texto:
        return ""
    nfd = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def requiere_video_post_oct_2026(texto: str) -> bool:
    """Indica si el tema afecta a materias reformadas tras octubre de 2026."""
    norm = _normalizar_texto(texto)
    return any(clave in norm for clave in TEMAS_POST_OCT_2026)


def buscar_biblioteca_local(tema: str, solo_post_oct_2026: Optional[bool] = None) -> str:
    """
    Busca contenido multimedia curado y seguro dentro de la biblioteca local.
    Utiliza un índice pre-generado para garantizar que las URLs y los tiempos son exactos.

    Args:
        tema (str): El concepto o tema legal inmobiliario a consultar.
        solo_post_oct_2026 (Optional[bool]): Si es True (o se detecta automáticamente por tema),
            filtra únicamente vídeos cuya fecha de publicación sea posterior a octubre de 2026.

    Returns:
        str: Una cadena formateada con los resultados encontrados (Título, Resumen, URL exacta)
             o "NO_LOCAL_RESULTS" si no hay coincidencias válidas.
    """
    if not os.path.exists(LOCAL_INDEX_PATH):
        return "NO_LOCAL_RESULTS (Index file missing)"

    try:
        with open(LOCAL_INDEX_PATH, 'r', encoding='utf-8') as f:
            index = json.load(f)
    except Exception:
        return "NO_LOCAL_RESULTS (Error reading index)"

    filtrar_fecha = solo_post_oct_2026 if solo_post_oct_2026 is not None else requiere_video_post_oct_2026(tema)
    tema_norm = _normalizar_texto(tema)
    resultados = []

    # Búsqueda lineal simple en el índice JSON
    for video_id, data in index.items():
        if filtrar_fecha:
            fecha_pub = str(data.get("fecha_publicacion") or data.get("published_at") or "").strip()
            if not fecha_pub or fecha_pub[:10] < POST_OCT_2026_PREFIX:
                continue

        tema_clave = _normalizar_texto(data.get("tema_clave", ""))
        resumen = _normalizar_texto(data.get("resumen_ejecutivo", data.get("resumen", "")))
        conceptos = _normalizar_texto(" ".join(data.get("conceptos_secundarios", [])))
        contexto = _normalizar_texto(data.get("contexto_uso", ""))
        
        # Coincidencia laxa en tema, resumen, conceptos o contexto
        if tema_norm in tema_clave or tema_norm in resumen or tema_norm in conceptos or tema_norm in contexto:
            resultados.append(data)

    if not resultados:
        return "NO_LOCAL_RESULTS"

    # Formatear salida para que el LLM la interprete fácilmente
    output = f"Recursos encontrados en biblioteca local para '{tema}':\n"
    for res in resultados[:3]: # Limitamos a 3 para no saturar contexto
        output += f"- TEMA: {res.get('tema_clave')}\n"
        output += f"  CONCEPTOS: {', '.join(res.get('conceptos_secundarios', []))}\n"
        output += f"  PERFIL: {res.get('perfil_ideal')} (Nivel: {res.get('nivel_dificultad')})\n"
        output += f"  CONTEXTO DE USO: {res.get('contexto_uso')}\n"
        output += f"  RESUMEN: {res.get('resumen_ejecutivo', res.get('resumen', ''))}\n"
        if res.get("fecha_publicacion") or res.get("published_at"):
            output += f"  FECHA PUBLICACIÓN: {res.get('fecha_publicacion') or res.get('published_at')}\n"
        output += f"  URL DIRECTA: {res.get('full_url')}\n\n"
    
    return output


def buscar_youtube_externo(
    tema: str,
    solo_post_oct_2026: Optional[bool] = None,
    contexto_consulta: str = ""
) -> Union[str, List[Dict[str, str]]]:
    """
    Realiza una búsqueda en YouTube alineada con el derecho de arrendamientos urbanos en España.
    Si el tema afecta a subidas de renta, prórrogas, alquiler temporal o habitaciones,
    restringe estrictamente los resultados a vídeos publicados después de octubre de 2026.

    Args:
        tema (str): El tema jurídico inmobiliario a buscar.
        solo_post_oct_2026 (Optional[bool]): Fuerza o desactiva el filtro de fecha posterior a octubre 2026.
        contexto_consulta (str): Texto adicional de la consulta del usuario para detectar materias sensibles.

    Returns:
        Union[str, List[Dict[str, str]]]: Lista de diccionarios con los vídeos válidos encontrados,
                                          o un string indicando error o ausencia de resultados.
    """
    if not build:
        return "ERROR_EXTERNAL_SEARCH (Library google-api-python-client missing)"
    
    # Leer dinámicamente para soportar recargas en caliente de Streamlit
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("YOUTUBE_API_KEY")
        except Exception:
            pass

    if not api_key:
        return "ERROR_EXTERNAL_SEARCH (Missing YOUTUBE_API_KEY)"

    filtrar_fecha = (
        solo_post_oct_2026
        if solo_post_oct_2026 is not None
        else requiere_video_post_oct_2026(f"{tema} {contexto_consulta}")
    )

    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # Enriquecemos la query para derecho de arrendamientos urbanos en España
        query_enriquecida = (
            f"{tema} (alquiler España | LAU | arrendamientos urbanos | derecho inmobiliario España)"
        )
        
        search_params = {
            "part": "snippet",
            "maxResults": 3,
            "q": query_enriquecida,
            "type": "video",
            "relevanceLanguage": "es",
            "regionCode": "ES",
            "safeSearch": "moderate",
        }
        if filtrar_fecha:
            search_params["publishedAfter"] = POST_OCT_2026_RFC3339
            search_params["order"] = "date"

        request = youtube.search().list(**search_params)
        response = request.execute()
        
        items = response.get("items", [])
        if not items:
            return "NO_EXTERNAL_RESULTS"
            
        resultados = []
        for item in items:
            snippet = item.get("snippet", {})
            published_at = snippet.get("publishedAt", "")
            fecha_corta = published_at[:10] if published_at else ""

            # Doble verificación estricta de fecha para materias reformadas en octubre de 2026
            if filtrar_fecha and (not fecha_corta or fecha_corta < POST_OCT_2026_PREFIX):
                continue

            title = snippet.get("title", "Vídeo explicativo")
            channel = snippet.get("channelTitle", "YouTube")
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            url = f"https://www.youtube.com/watch?v={video_id}"
            fecha_txt = f" — Publicado: {fecha_corta}" if fecha_corta else ""
            
            resultados.append({
                "title": f"{title} ({channel}){fecha_txt}",
                "url": url,
                "reason": f"Vídeo explicativo actualizado sobre '{tema}' en normativa española de alquiler."
            })

            if len(resultados) >= 2:
                break

        if not resultados:
            return "NO_EXTERNAL_RESULTS"
            
        return resultados

    except Exception:
        return "ERROR_EXTERNAL_SEARCH"