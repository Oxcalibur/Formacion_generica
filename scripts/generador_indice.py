import os
import json
import pandas as pd
from youtube_transcript_api import YouTubeTranscriptApi
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("Error: La librería 'google-genai' no está instalada.")
    genai = None

# --- CONFIGURACIÓN ---
# NOTA PARA EL DESARROLLADOR:
# Asegúrate de que la variable de entorno GOOGLE_API_KEY esté configurada con tu API Key de Gemini.
GEMINI_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not GEMINI_API_KEY:
    try:
        import streamlit as st
        GEMINI_API_KEY = st.secrets.get("GOOGLE_API_KEY")
    except Exception:
        pass

# Rutas relativas asumiendo ejecución desde la raíz del proyecto
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "knowledge_base", "multimedia.csv")
OUTPUT_INDEX = os.path.join(BASE_DIR, "knowledge_base", "video_index.json")

def get_video_id(url):
    """Extrae el ID de video de una URL de YouTube estándar."""
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return None

def generate_index():
    """
    Lee el CSV de multimedia, extrae transcripciones de videos y usa Gemini
    para generar metadatos precisos (timestamps y resúmenes).
    """
    if not GEMINI_API_KEY:
        print("❌ Error Crítico: Falta la variable de entorno GOOGLE_API_KEY para usar Gemini.")
        return

    if not os.path.exists(DATA_FILE):
        print(f"❌ Error: No se encuentra el archivo de datos: {DATA_FILE}")
        return

    print(f"📂 Leyendo inventario desde {DATA_FILE}...")
    try:
        df = pd.read_csv(DATA_FILE)
    except Exception as e:
        print(f"❌ Error leyendo CSV: {e}")
        return

    # Filtrar solo recursos tipo 'Video'
    if 'Tipo' in df.columns:
        videos = df[df['Tipo'] == 'Video']
    else:
        print("⚠️ Advertencia: Columna 'Tipo' no encontrada, procesando todo el CSV.")
        videos = df

    master_index = {}
    client = genai.Client(api_key=GEMINI_API_KEY)

    print(f"🔍 Procesando {len(videos)} videos para indexación semántica...")

    for _, row in videos.iterrows():
        resource_id = str(row.get('ID_Recurso', ''))
        url = row.get('URL', '')
        
        if not url or not resource_id:
            continue

        yt_id = get_video_id(url)
        if not yt_id:
            print(f"   ⚠️ Saltando URL no reconocida: {url}")
            continue

        print(f"   🎥 Procesando ID: {resource_id} (YouTube: {yt_id})")
        
        try:
            # Intentamos obtener subtítulos en español o inglés
            transcript_list = YouTubeTranscriptApi.get_transcript(yt_id, languages=['es', 'en'])
            full_text = " ".join([t['text'] for t in transcript_list])
            
            # Prompt estricto para Gemini
            prompt = f"""
            Analiza la siguiente transcripción de un video de formación corporativa.
            Genera metadatos JSON estrictos para indexación.
            
            TRANSCRIPCIÓN (Fragmento):
            {full_text[:25000]} 
            
            INSTRUCCIONES:
            1. Identifica el 'tema_clave' principal.
            2. Encuentra el momento (timestamp) más relevante donde empieza la explicación clave.
            3. Genera un 'resumen' ejecutivo de 2 líneas.
            4. Devuelve SOLO JSON con claves: tema_clave, timestamp_inicio, timestamp_fin, parametros_url (ej. "&t=120s"), resumen.
            """

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            metadata = json.loads(response.text)
            metadata["original_url"] = url
            metadata["full_url"] = f"{url}{metadata.get('parametros_url', '')}"
            
            master_index[resource_id] = metadata
            print(f"      ✅ Indexado: {metadata.get('tema_clave')}")

        except Exception as e:
            print(f"      ❌ Fallo al procesar video: {e}")

    # Guardar el índice maestro
    os.makedirs(os.path.dirname(OUTPUT_INDEX), exist_ok=True)
    with open(OUTPUT_INDEX, 'w', encoding='utf-8') as f:
        json.dump(master_index, f, indent=4, ensure_ascii=False)
    
    print(f"\n✨ Índice generado exitosamente en: {OUTPUT_INDEX}")

if __name__ == "__main__":
    generate_index()