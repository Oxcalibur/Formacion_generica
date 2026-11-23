"""
Auditoría QA Semanal Incremental para el Asesor Inmobiliario Integral.

Lee únicamente las filas NUEVAS (timestamp > último cursor guardado en la pestaña QA_Aprendizajes)
de la pestaña `Prompts_Inmobiliaria` en Google Sheets, agrupa las conversaciones por `session_id`,
analiza fallos, asunciones, huecos documentales y mejoras con Gemini, actualiza el cursor
en `QA_Aprendizajes` y genera `qa_report_latest.md` para que GitHub Actions abra un Issue semanal.

Variables de entorno requeridas:
- GOOGLE_API_KEY: API Key de Gemini.
- GSHEETS_SPREADSHEET_URL: URL completa (o ID) del Google Sheet.
- GSHEETS_SERVICE_ACCOUNT_JSON: JSON completo de la cuenta de servicio de Google Cloud.

Variables opcionales:
- PROMPTS_WORKSHEET_NAME (default: "Prompts_Inmobiliaria")
- QA_WORKSHEET_NAME (default: "QA_Aprendizajes")
- GEMINI_QA_MODEL (default: "gemini-2.5-flash")
- DRY_RUN ("true" / "false", default: "false")
"""

import argparse
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

import gspread
import pandas as pd
from google import genai
from google.genai import types
from google.oauth2.service_account import Credentials

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(BASE_DIR, "knowledge_base")
CONFIG_PATH = os.path.join(BASE_DIR, "config.py")
REPORT_OUTPUT_PATH = os.path.join(BASE_DIR, "qa_report_latest.md")
META_OUTPUT_PATH = os.path.join(BASE_DIR, "qa_report_meta.json")

QA_HEADERS = [
    "audit_date",
    "last_timestamp_processed",
    "rows_analyzed",
    "sessions_analyzed",
    "summary",
    "prompt_improvements",
    "kb_gaps",
    "full_report",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


def parse_timestamp(val: Any) -> Optional[pd.Timestamp]:
    """Parsea timestamps de Google Sheets de forma tolerante."""
    if val is None:
        return None
    text = str(val).strip()
    if not text or text.lower() in ("nan", "nat", "none"):
        return None
    ts = pd.to_datetime(text, errors="coerce")
    if pd.isna(ts):
        return None
    return ts


def filter_unread_rows(
    df_prompts: pd.DataFrame,
    last_timestamp_str: Optional[str] = None,
) -> Tuple[pd.DataFrame, Optional[str]]:
    """
    Filtra estrictamente las filas con timestamp > last_timestamp_str.
    Devuelve (df_nuevas_ordenado, nuevo_max_timestamp_str).
    """
    if df_prompts is None or df_prompts.empty:
        return pd.DataFrame(), last_timestamp_str

    df = df_prompts.copy()
    df = df.dropna(how="all")
    if "timestamp" not in df.columns or "prompt" not in df.columns:
        return pd.DataFrame(), last_timestamp_str

    df["_parsed_ts"] = df["timestamp"].apply(parse_timestamp)
    df = df[df["_parsed_ts"].notna()].copy()
    df = df[df["prompt"].astype(str).str.strip() != ""].copy()

    if df.empty:
        return pd.DataFrame(), last_timestamp_str

    cursor_ts = parse_timestamp(last_timestamp_str)
    if cursor_ts is not None:
        df = df[df["_parsed_ts"] > cursor_ts].copy()

    if df.empty:
        return pd.DataFrame(), last_timestamp_str

    df = df.sort_values(by="_parsed_ts", ascending=True).reset_index(drop=True)
    max_ts = df["_parsed_ts"].max()
    new_cursor_str = max_ts.strftime("%Y-%m-%d %H:%M:%S")
    return df, new_cursor_str


def build_kb_inventory_summary(kb_dir: str = KB_DIR) -> str:
    """Devuelve un resumen compacto de todos los documentos ya existentes en knowledge_base/."""
    if not os.path.exists(kb_dir):
        return "Carpeta knowledge_base no encontrada."
    lines = []
    for root, dirs, files in os.walk(kb_dir):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        files = sorted(f for f in files if not f.startswith("."))
        rel_dir = os.path.relpath(root, kb_dir).replace("\\", "/")
        if rel_dir == ".":
            continue
        if files:
            lines.append(f"- {rel_dir}/: {', '.join(files)}")
        else:
            lines.append(f"- {rel_dir}/: (vacía)")
    return "\n".join(lines) if lines else "Sin subcarpetas."


def load_current_system_prompt_excerpt(config_path: str = CONFIG_PATH, max_chars: int = 12000) -> str:
    """Lee el system_prompt actual en config.py para no repetir reglas ya implementadas."""
    if not os.path.exists(config_path):
        return ""
    try:
        with open(config_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        marker = '"system_prompt": """'
        start = content.find(marker)
        if start == -1:
            return ""
        end = content.find('"""', start + len(marker))
        prompt_txt = content[start + len(marker):end] if end != -1 else content[start + len(marker):]
        return prompt_txt.strip()[:max_chars]
    except Exception:
        return ""


def format_conversations_for_audit(df_new: pd.DataFrame, max_chars: int = 85000) -> Tuple[str, int]:
    """Agrupa los turnos nuevos por session_id y los formatea para la auditoría QA."""
    if df_new.empty:
        return "", 0

    df = df_new.copy()
    if "session_id" not in df.columns:
        df["session_id"] = ""

    def _resolve_session(row):
        sid = str(row.get("session_id") or "").strip()
        if sid and sid.lower() not in ("nan", "none", "sin_sesion"):
            return sid
        ts = row["_parsed_ts"]
        return f"legacy_{ts.strftime('%Y%m%d_%H')}"

    df["_session_key"] = df.apply(_resolve_session, axis=1)
    grouped = list(df.groupby("_session_key", sort=False))

    blocks = []
    used_chars = 0
    for sid, group in grouped:
        lines = [f"=== SESIÓN: {sid} ({len(group)} turnos) ==="]
        for _, row in group.iterrows():
            ts_str = row["_parsed_ts"].strftime("%Y-%m-%d %H:%M:%S")
            role = str(row.get("role") or "").strip()
            arq = str(row.get("arquetipo") or "").strip()
            doc = str(row.get("doc_attached") or "").strip()
            prompt = str(row.get("prompt") or "").strip()
            resp = str(row.get("response") or "").strip()

            meta = f"[{ts_str}] Perfil: {role or 'N/A'} | Arquetipo: {arq or 'vacío'} | Doc: {doc or 'N/A'}"
            lines.append(meta)
            lines.append(f"  USUARIO: {prompt[:1500]}")
            if resp and resp.lower() != "nan":
                lines.append(f"  ASISTENTE: {resp[:2500]}")
            else:
                lines.append("  ASISTENTE: (respuesta no registrada en log)")
        block_text = "\n".join(lines) + "\n"
        if used_chars + len(block_text) > max_chars:
            blocks.append(f"\n[... {len(grouped) - len(blocks)} sesiones adicionales omitidas por límite de contexto ...]")
            break
        blocks.append(block_text)
        used_chars += len(block_text)

    return "\n".join(blocks), len(grouped)


def connect_spreadsheet() -> gspread.Spreadsheet:
    """Conecta con el Google Sheet usando credenciales de cuenta de servicio desde variables de entorno."""
    sa_json_raw = os.environ.get("GSHEETS_SERVICE_ACCOUNT_JSON", "").strip()
    spreadsheet_url = os.environ.get("GSHEETS_SPREADSHEET_URL", "").strip()

    if not sa_json_raw:
        raise ValueError("Falta la variable de entorno GSHEETS_SERVICE_ACCOUNT_JSON.")
    if not spreadsheet_url:
        raise ValueError("Falta la variable de entorno GSHEETS_SPREADSHEET_URL.")

    sa_info = json.loads(sa_json_raw)
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    gc = gspread.authorize(creds)

    if spreadsheet_url.startswith("http"):
        return gc.open_by_url(spreadsheet_url)
    return gc.open_by_key(spreadsheet_url)


def get_or_create_qa_worksheet(sh: gspread.Spreadsheet, qa_ws_name: str) -> gspread.Worksheet:
    """Obtiene la pestaña QA_Aprendizajes o la crea automáticamente con cabeceras si no existe."""
    try:
        ws = sh.worksheet(qa_ws_name)
        existing_headers = ws.row_values(1)
        if not existing_headers:
            ws.update("A1:H1", [QA_HEADERS])
        return ws
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=qa_ws_name, rows=200, cols=len(QA_HEADERS))
        ws.update("A1:H1", [QA_HEADERS])
        return ws


def read_last_cursor(qa_ws: gspread.Worksheet) -> Optional[str]:
    """Lee el último `last_timestamp_processed` registrado en QA_Aprendizajes."""
    records = qa_ws.get_all_records()
    if not records:
        return None
    valid_ts = []
    for rec in records:
        ts_val = rec.get("last_timestamp_processed")
        parsed = parse_timestamp(ts_val)
        if parsed is not None:
            valid_ts.append(parsed)
    if not valid_ts:
        return None
    return max(valid_ts).strftime("%Y-%m-%d %H:%M:%S")


def read_worksheet_df(sh: gspread.Spreadsheet, ws_name: str) -> pd.DataFrame:
    """Lee una pestaña completa como DataFrame de pandas."""
    ws = sh.worksheet(ws_name)
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return pd.DataFrame()
    headers = values[0]
    rows = values[1:]
    return pd.DataFrame(rows, columns=headers)


def run_gemini_qa_audit(
    conversations_text: str,
    rows_count: int,
    sessions_count: int,
    period_start: str,
    period_end: str,
) -> Dict[str, str]:
    """Ejecuta el análisis QA con Gemini y devuelve campos estructurados + informe Markdown."""
    api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    if not api_key:
        raise ValueError("Falta la variable de entorno GOOGLE_API_KEY.")

    model_name = os.environ.get("GEMINI_QA_MODEL", "gemini-2.5-flash").strip()
    kb_inventory = build_kb_inventory_summary()
    current_prompt = load_current_system_prompt_excerpt()

    audit_prompt = f"""
Eres un **Auditor Senior de Calidad (QA) de Agentes IA Inmobiliarios en España** (derecho LAU/RDL 29/2026, fiscalidad IRPF/ITP, financiación LCCI/CIRBE e inversión inmobiliaria).

Vas a auditar **{rows_count} nuevas interacciones** agrupadas en **{sessions_count} sesiones** ocurridas entre `{period_start}` y `{period_end}` (solo logs NO analizados previamente).

### DOCUMENTOS QUE YA EXISTEN HOY EN `knowledge_base/`:
{kb_inventory}

### EXTRACTOS DEL `system_prompt` ACTUAL EN `config.py` (NO propongas reglas que ya existan tal cual, salvo si ves que el modelo las incumple y hay que reforzarlas):
{current_prompt}

### CONVERSACIONES NUEVAS A AUDITAR:
{conversations_text}

### TU TAREA:
Analiza con máximo rigor las conversaciones y responde ÚNICAMENTE con un JSON válido con exactamente estas 4 claves de texto:
1. `"summary"`: Resumen ejecutivo breve (3-5 líneas) con temas predominantes, arquetipos vistos y calidad general.
2. `"prompt_improvements"`: Lista concisa en texto plano de mejoras concretas para `config.py` (o "Sin cambios urgentes en prompt" si todo fue sólido).
3. `"kb_gaps"`: Lista concisa de documentos o datos que faltan en `knowledge_base/` y en qué carpeta (`01_`..`06_`) deberían añadirse.
4. `"full_report_markdown"`: Informe completo en Markdown bien estructurado con estas secciones:
   - `## 1. Resumen ejecutivo` (sesiones, turnos, arquetipos detectados, nivel de fiabilidad)
   - `## 2. Fallos críticos y contradicciones detectadas` (asunciones no confirmadas, errores de fechas/cálculos, respuestas vagas, incumplimientos del triaje — citando la sesión/hora exacta)
   - `## 3. Propuestas concretas de ajuste para config.py` (reglas listas para revisar y aplicar)
   - `## 4. Huecos detectados en knowledge_base/` (qué fichero concreto añadir y en qué carpeta `01_`..`06_`)
   - `## 5. Observaciones de UX y telemetría` (duplicados, arquetipo vacío, uso de documentos adjuntos, tiempos)

IMPORTANTE: Sé riguroso y específico. Nunca inventes conversaciones que no estén en los logs. Si las conversaciones fueron correctas, dilo claramente.
"""

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version="v1beta"),
    )
    cfg_kwargs: Dict[str, Any] = {
        "temperature": 0.2,
        "response_mime_type": "application/json",
    }
    if "2.5" in model_name and hasattr(types, "ThinkingConfig"):
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=2048)

    response = client.models.generate_content(
        model=model_name,
        contents=audit_prompt,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )

    raw_text = (response.text or "").strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    parsed = json.loads(raw_text)
    return {
        "summary": str(parsed.get("summary", "")).strip(),
        "prompt_improvements": str(parsed.get("prompt_improvements", "")).strip(),
        "kb_gaps": str(parsed.get("kb_gaps", "")).strip(),
        "full_report_markdown": str(parsed.get("full_report_markdown", "")).strip(),
    }


def main():
    parser = argparse.ArgumentParser(description="Auditoría QA semanal incremental sobre Prompts_Inmobiliaria.")
    parser.add_argument("--dry-run", action="store_true", help="Analiza sin actualizar QA_Aprendizajes.")
    args = parser.parse_args()

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    prompts_ws_name = os.environ.get("PROMPTS_WORKSHEET_NAME", "Prompts_Inmobiliaria").strip()
    qa_ws_name = os.environ.get("QA_WORKSHEET_NAME", "QA_Aprendizajes").strip()

    print(f"🔍 Iniciando auditoría QA incremental (dry_run={dry_run})...")
    sh = connect_spreadsheet()
    qa_ws = get_or_create_qa_worksheet(sh, qa_ws_name)
    last_cursor = read_last_cursor(qa_ws)
    print(f"📌 Último timestamp auditado en '{qa_ws_name}': {last_cursor or 'NINGUNO (primera ejecución)'}")

    df_prompts = read_worksheet_df(sh, prompts_ws_name)
    df_new, new_cursor = filter_unread_rows(df_prompts, last_cursor)

    if df_new.empty:
        print("✅ No hay nuevas interacciones desde el último corte. Finalizando sin consumir API de Gemini.")
        meta = {"has_report": False, "rows_analyzed": 0, "sessions_analyzed": 0}
        with open(META_OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return

    period_start = df_new["_parsed_ts"].min().strftime("%Y-%m-%d %H:%M:%S")
    period_end = df_new["_parsed_ts"].max().strftime("%Y-%m-%d %H:%M:%S")
    conversations_text, sessions_count = format_conversations_for_audit(df_new)
    rows_count = len(df_new)

    print(f"📊 Encontradas {rows_count} nuevas interacciones ({sessions_count} sesiones) entre {period_start} y {period_end}.")
    audit_result = run_gemini_qa_audit(
        conversations_text=conversations_text,
        rows_count=rows_count,
        sessions_count=sessions_count,
        period_start=period_start,
        period_end=period_end,
    )

    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    header_md = (
        f"# 🧠 Auditoría QA Semanal — {today_str}\n\n"
        f"- **Periodo analizado (solo logs nuevos):** `{period_start}` → `{period_end}`\n"
        f"- **Interacciones nuevas:** `{rows_count}` | **Sesiones:** `{sessions_count}`\n"
        f"- **Cursor anterior:** `{last_cursor or 'Inicio'}` → **Nuevo cursor:** `{new_cursor}`\n"
        f"- **Modo simulación (dry-run):** `{'Sí' if dry_run else 'No'}`\n\n---\n\n"
    )
    full_markdown = header_md + audit_result["full_report_markdown"]

    with open(REPORT_OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(full_markdown)

    meta = {
        "has_report": True,
        "audit_date": today_str,
        "rows_analyzed": rows_count,
        "sessions_analyzed": sessions_count,
        "period_start": period_start,
        "period_end": period_end,
        "new_cursor": new_cursor,
        "dry_run": dry_run,
    }
    with open(META_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    if not dry_run:
        new_row = [
            datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            new_cursor or "",
            rows_count,
            sessions_count,
            audit_result["summary"][:4000],
            audit_result["prompt_improvements"][:4000],
            audit_result["kb_gaps"][:4000],
            full_markdown[:45000],
        ]
        qa_ws.append_row(new_row, value_input_option="USER_ENTERED")
        print(f"☁️ Informe y nuevo cursor ({new_cursor}) guardados en '{qa_ws_name}'.")
    else:
        print("🧪 Dry-run activo: informe generado localmente sin modificar Google Sheets.")

    print("✅ Auditoría QA semanal completada.")


if __name__ == "__main__":
    main()
