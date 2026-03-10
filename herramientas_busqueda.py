import json
import os
from typing import Optional

# Importación segura para entornos donde no se requiera búsqueda externa
try:
    from googleapiclient.discovery import build
except ImportError:
    build = None

# --- CONFIGURACIÓN ---
# Ruta absoluta al índice generado
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_INDEX_PATH = os.path.join(BASE_DIR, "knowledge_base", "video_index.json")

# NOTA PARA EL DESARROLLADOR:
# Inserta tu API Key de YouTube (Google Cloud Console) en las variables de entorno
# o pégala aquí directamente si es un entorno de pruebas seguro.
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

def buscar_biblioteca_local(tema: str) -> str:
    """
    Busca contenido multimedia curado y seguro dentro de la biblioteca local de la empresa.
    Utiliza un índice pre-generado para garantizar que las URLs y los tiempos son exactos.

    Args:
        tema (str): El concepto, habilidad o tema que el usuario quiere aprender.

    Returns:
        str: Una cadena formateada con los resultados encontrados (Título, Resumen, URL exacta) 
             o "NO_LOCAL_RESULTS" si no hay coincidencias.
    """
    if not os.path.exists(LOCAL_INDEX_PATH):
        return "NO_LOCAL_RESULTS (Index file missing)"

    try:
        with open(LOCAL_INDEX_PATH, 'r', encoding='utf-8') as f:
            index = json.load(f)
    except Exception:
        return "NO_LOCAL_RESULTS (Error reading index)"

    tema_lower = tema.lower()
    resultados = []

    # Búsqueda lineal simple en el índice JSON
    for video_id, data in index.items():
        tema_clave = data.get("tema_clave", "").lower()
        resumen = data.get("resumen", "").lower()
        
        # Coincidencia laxa en tema o resumen
        if tema_lower in tema_clave or tema_lower in resumen:
            resultados.append(data)

    if not resultados:
        return "NO_LOCAL_RESULTS"

    # Formatear salida para que el LLM la interprete fácilmente
    output = f"Recursos encontrados en biblioteca local para '{tema}':\n"
    for res in resultados[:3]: # Limitamos a 3 para no saturar contexto
        output += f"- TEMA: {res.get('tema_clave')}\n"
        output += f"  RESUMEN: {res.get('resumen')}\n"
        output += f"  URL DIRECTA: {res.get('full_url')}\n\n"
    
    return output

def buscar_youtube_externo(tema: str) -> str:
    """
    Realiza una búsqueda en YouTube (Internet abierto) para encontrar material complementario.
    Útil cuando la biblioteca local no cubre el tema solicitado.
    
    Args:
        tema (str): El tema a buscar.

    Returns:
        str: Los 2 mejores videos encontrados con Título, Canal y URL, o "ERROR_EXTERNAL_SEARCH".
    """
    if not build:
        return "ERROR_EXTERNAL_SEARCH (Library google-api-python-client missing)"
    
    if not YOUTUBE_API_KEY:
        return "ERROR_EXTERNAL_SEARCH (Missing YOUTUBE_API_KEY)"

    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        
        # Enriquecemos la query para asegurar calidad corporativa
        query_enrichida = f"{tema} (management | leadership | ted talk | business training)"
        
        request = youtube.search().list(
            part="snippet",
            maxResults=2,
            q=query_enrichida,
            type="video",
            relevanceLanguage="es",
            safeSearch="moderate"
        )
        response = request.execute()
        
        items = response.get("items", [])
        if not items:
            return "NO_EXTERNAL_RESULTS"
            
        output = "Resultados externos recomendados (YouTube):\n"
        for item in items:
            title = item["snippet"]["title"]
            channel = item["snippet"]["channelTitle"]
            video_id = item["id"]["videoId"]
            url = f"https://www.youtube.com/watch?v={video_id}"
            
            output += f"- VIDEO: {title} ({channel})\n  URL: {url}\n"
            
        return output

    except Exception as e:
        print(f"Error en búsqueda externa: {e}")
        return "ERROR_EXTERNAL_SEARCH"