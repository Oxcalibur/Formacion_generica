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
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.path.basename(BASE_DIR) == "scripts":
    BASE_DIR = os.path.dirname(BASE_DIR)

# Búsqueda robusta del archivo multimedia.csv
possible_paths = [
    os.path.join(BASE_DIR, "knowledge_base", "multimedia.csv"),
    os.path.join(BASE_DIR, "knowledge_Base", "multimedia.csv"),
    os.path.join(BASE_DIR, "data", "multimedia.csv")
]

DATA_FILE = next((p for p in possible_paths if os.path.exists(p)), possible_paths[0])
OUTPUT_INDEX = os.path.join(os.path.dirname(DATA_FILE), "video_index.json")

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
        # Soporte para columna URL o Ruta_o_URL
        url = row.get('URL', row.get('Ruta_o_URL', ''))
        
        if not url or not resource_id:
            continue

        yt_id = get_video_id(url)
        if not yt_id:
            print(f"   ⚠️ Saltando URL no reconocida: {url}")
            continue

        print(f"   🎥 Procesando ID: {resource_id} (YouTube: {yt_id})")
        
        try:
            # Intentamos obtener subtítulos en español o inglés
            # 1. Instanciamos el cliente de la API (Nueva arquitectura requerida)
            yt_api = YouTubeTranscriptApi()
            
            # 2. Usamos el método fetch() en lugar del antiguo método estático
            fetched_transcript = yt_api.fetch(yt_id, languages=['es', 'en'])
            
            # 3. Convertimos el nuevo objeto FetchedTranscript a la clásica lista de diccionarios
            transcript_list = fetched_transcript.to_raw_data() if hasattr(fetched_transcript, 'to_raw_data') else fetched_transcript
            
            # 4. Concatenamos el texto
            full_text = " ".join([t['text'] for t in transcript_list])

            # Prompt estricto para Gemini
            prompt = f"""
            Analiza la siguiente transcripción de un video de formación corporativa.
            Genera metadatos JSON estrictos para indexación con alto nivel de detalle.
            
            TRANSCRIPCIÓN (Fragmento):
            {full_text[:25000]} 
            
            INSTRUCCIONES:
            1. Identifica el 'tema_clave' principal.
            2. Extrae una lista de 'conceptos_secundarios' tratados en el video.
            3. Define el 'nivel_dificultad' (Principiante, Intermedio, Avanzado).
            4. Define el 'perfil_ideal' (ej. Manager, Consultor, Liderazgo, General).
            5. Explica el 'contexto_uso' (En qué situación específica un empleado debería ver este video).
            6. Encuentra el momento (timestamp) más relevante donde empieza la explicación clave y su fin ('timestamp_inicio' y 'timestamp_fin').
            7. Genera un 'resumen_ejecutivo' de 2 líneas y un 'resumen_detallado' de 1 párrafo.
            8. Genera los 'parametros_url' con el formato exacto del inicio (ej. "&t=120s").
            9. Devuelve SOLO JSON con claves: tema_clave, conceptos_secundarios (lista), nivel_dificultad, perfil_ideal, contexto_uso, timestamp_inicio, timestamp_fin, parametros_url, resumen_ejecutivo, resumen_detallado.
            """

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            datos_gemini = json.loads(response.text)
            
            # Validación robusta: Si Gemini devuelve una lista, tomamos el primer elemento.
            if isinstance(datos_gemini, list):
                if len(datos_gemini) > 0:
                    metadata = datos_gemini[0]
                else:
                    raise ValueError("Gemini devolvió una lista JSON vacía.")
            else:
                # Si devuelve un diccionario directamente
                metadata = datos_gemini

            # Ahora inyectamos nuestras variables con seguridad
            metadata["original_url"] = url
            metadata["full_url"] = f"{url}{metadata.get('parametros_url', '')}"
            
            master_index[resource_id] = metadata
            print(f"      ✅ Indexado: {metadata.get('tema_clave', 'Tema no definido')}")

        except Exception as e:
            print(f"      ❌ Fallo al procesar video: {e}")

    # Guardar el índice maestro
    os.makedirs(os.path.dirname(OUTPUT_INDEX), exist_ok=True)
    with open(OUTPUT_INDEX, 'w', encoding='utf-8') as f:
        json.dump(master_index, f, indent=4, ensure_ascii=False)
    
    print(f"\n✨ Índice generado exitosamente en: {OUTPUT_INDEX}")

if __name__ == "__main__":
    generate_index()