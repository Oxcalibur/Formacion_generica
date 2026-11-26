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
SPECIALISTS_PATH = os.path.join(BASE_DIR, "specialists.py")
REPORT_OUTPUT_PATH = os.path.join(BASE_DIR, "qa_report_latest.md")
META_OUTPUT_PATH = os.path.join(BASE_DIR, "qa_report_meta.json")
LOCAL_SECRETS_PATH = os.path.join(BASE_DIR, ".streamlit", "secrets.toml")


def _load_local_streamlit_secrets() -> None:
    """
    Si faltan variables de entorno en ejecución local, carga automáticamente
    GOOGLE_API_KEY, GSHEETS_SPREADSHEET_URL y GSHEETS_SERVICE_ACCOUNT_JSON desde
    `.streamlit/secrets.toml` (sin imprimir nunca secretos en consola).
    """
    if not os.path.exists(LOCAL_SECRETS_PATH):
        return
    try:
        import tomllib  # Python 3.11+
        with open(LOCAL_SECRETS_PATH, "rb") as f:
            secrets = tomllib.load(f)
    except Exception:
        return

    if not os.environ.get("GOOGLE_API_KEY"):
        for k, v in secrets.items():
            if k.startswith("GOOGLE_API_KEY") and isinstance(v, str) and v.strip():
                os.environ["GOOGLE_API_KEY"] = v.strip()
                break

    gs_conf = (secrets.get("connections") or {}).get("gsheets") or {}
    if isinstance(gs_conf, dict) and gs_conf:
        if not os.environ.get("GSHEETS_SPREADSHEET_URL") and gs_conf.get("spreadsheet"):
            os.environ["GSHEETS_SPREADSHEET_URL"] = str(gs_conf["spreadsheet"]).strip()
        if not os.environ.get("GSHEETS_SERVICE_ACCOUNT_JSON") and gs_conf.get("private_key") and gs_conf.get("client_email"):
            sa_keys = (
                "type", "project_id", "private_key_id", "private_key", "client_email",
                "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url",
                "client_x509_cert_url", "universe_domain",
            )
            sa_obj = {k: gs_conf[k] for k in sa_keys if k in gs_conf}
            sa_obj.setdefault("type", "service_account")
            sa_obj.setdefault("auth_uri", "https://accounts.google.com/o/oauth2/auth")
            sa_obj.setdefault("token_uri", "https://oauth2.googleapis.com/token")
            os.environ["GSHEETS_SERVICE_ACCOUNT_JSON"] = json.dumps(sa_obj)

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

    # Excluir ejecuciones sintéticas de regresión automática (qa_auto) para auditar solo usuarios reales
    if "username" in df.columns:
        df = df[df["username"].astype(str).str.strip().str.lower() != "qa_auto"].copy()

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


def load_current_system_prompt_excerpt(
    config_path: str = CONFIG_PATH,
    specialists_path: str = SPECIALISTS_PATH,
    max_chars: int = 16000,
) -> str:
    """Lee el núcleo de config.py y los 4 especialistas de specialists.py para no proponer reglas ya implementadas."""
    parts = []
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            marker = '"system_prompt": """'
            start = content.find(marker)
            if start != -1:
                end = content.find('"""', start + len(marker))
                prompt_txt = content[start + len(marker):end] if end != -1 else content[start + len(marker):]
                parts.append("--- NÚCLEO (config.py) ---\n" + prompt_txt.strip()[:8000])
        except Exception:
            pass

    if os.path.exists(specialists_path):
        try:
            with open(specialists_path, "r", encoding="utf-8", errors="replace") as f:
                spec_content = f.read()
            # Extraer únicamente el bloque SPECIALIST_META (reglas de los 4 especialistas)
            s_start = spec_content.find("SPECIALIST_META")
            s_end = spec_content.find("DOMAIN_SIGNALS")
            if s_start != -1:
                spec_excerpt = spec_content[s_start:s_end] if s_end != -1 else spec_content[s_start:]
                parts.append("--- ESPECIALISTAS ACTIVABLES (specialists.py) ---\n" + spec_excerpt.strip()[:8000])
        except Exception:
            pass

    return "\n\n".join(parts)[:max_chars]


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
            uname = str(row.get("username") or "").strip()
            role = str(row.get("role") or "").strip()
            arq = str(row.get("arquetipo") or "").strip()
            espec = str(row.get("especialistas") or "").strip()
            doc = str(row.get("doc_attached") or "").strip()
            prompt = str(row.get("prompt") or "").strip()
            resp = str(row.get("response") or "").strip()

            meta = f"[{ts_str}] Usuario: {uname or 'N/A'} | Perfil: {role or 'N/A'} | Arquetipo: {arq or 'vacío'} | Especialistas: {espec or 'N/A'} | Doc: {doc or 'N/A'}"
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


def _parse_service_account_credentials(raw_text: str) -> Dict[str, Any]:
    """
    Parsea las credenciales de cuenta de servicio aceptando tanto formato JSON estándar
    como el formato TOML de Streamlit (`.streamlit/secrets.toml`, con o sin cabecera [connections.gsheets]).
    """
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Falta la variable de entorno GSHEETS_SERVICE_ACCOUNT_JSON.")

    # 1. Intentar JSON estándar primero
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2. Fallback automático: formato TOML de Streamlit Secrets (Python 3.11+ tomllib)
    try:
        import tomllib
        parsed = tomllib.loads(text)
        if isinstance(parsed, dict):
            gs = (parsed.get("connections") or {}).get("gsheets") if "connections" in parsed else parsed
            if isinstance(gs, dict) and gs.get("private_key") and gs.get("client_email"):
                sa_keys = (
                    "type", "project_id", "private_key_id", "private_key", "client_email",
                    "client_id", "auth_uri", "token_uri", "auth_provider_x509_cert_url",
                    "client_x509_cert_url", "universe_domain",
                )
                sa_obj = {k: gs[k] for k in sa_keys if k in gs}
                if isinstance(sa_obj.get("private_key"), str):
                    sa_obj["private_key"] = sa_obj["private_key"].replace("\\n", "\n")
                sa_obj.setdefault("type", "service_account")
                sa_obj.setdefault("auth_uri", "https://accounts.google.com/o/oauth2/auth")
                sa_obj.setdefault("token_uri", "https://oauth2.googleapis.com/token")
                return sa_obj
    except Exception:
        pass

    raise ValueError(
        "GSHEETS_SERVICE_ACCOUNT_JSON no tiene formato JSON válido ni TOML de cuenta de servicio "
        "(debe contener 'client_email' y 'private_key')."
    )


def _extract_clean_secret_value(raw_val: str) -> str:
    """Limpia espacios, comillas o asignaciones TOML tipo KEY = \"valor\" en secrets."""
    val = (raw_val or "").strip()
    if "=" in val and not val.startswith("http"):
        # Ej. spreadsheet = "https://..." o GOOGLE_API_KEY = "AIza..."
        _, rhs = val.split("=", 1)
        val = rhs.strip()
    return val.strip().strip('"').strip("'").strip()


def _extract_spreadsheet_id(raw_url_or_id: str) -> str:
    """Extrae el ID limpio de Google Sheets desde una URL, asignación TOML o ID directo."""
    import re
    cleaned = _extract_clean_secret_value(raw_url_or_id)
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", cleaned)
    if m:
        return m.group(1)
    return cleaned


def connect_spreadsheet() -> gspread.Spreadsheet:
    """Conecta con el Google Sheet usando credenciales de cuenta de servicio desde variables de entorno."""
    sa_json_raw = os.environ.get("GSHEETS_SERVICE_ACCOUNT_JSON", "").strip()
    spreadsheet_url = os.environ.get("GSHEETS_SPREADSHEET_URL", "").strip()

    if not sa_json_raw:
        raise ValueError("Falta la variable de entorno GSHEETS_SERVICE_ACCOUNT_JSON.")
    if not spreadsheet_url:
        raise ValueError("Falta la variable de entorno GSHEETS_SPREADSHEET_URL.")

    sa_info = _parse_service_account_credentials(sa_json_raw)
    creds = Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    gc = gspread.authorize(creds)

    sheet_id = _extract_spreadsheet_id(spreadsheet_url)
    return gc.open_by_key(sheet_id)


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
    api_key = _extract_clean_secret_value(os.environ.get("GOOGLE_API_KEY", ""))
    if not api_key:
        raise ValueError("Falta la variable de entorno GOOGLE_API_KEY.")

    model_name = os.environ.get("GEMINI_QA_MODEL", "gemini-2.5-flash").strip()
    kb_inventory = build_kb_inventory_summary()
    current_prompt = load_current_system_prompt_excerpt()

    fecha_hoy = datetime.datetime.now().strftime("%d/%m/%Y")
    audit_prompt = f"""
Eres un **Auditor Senior de Calidad (QA) de Agentes IA Inmobiliarios en España** (derecho LAU/RDL 29/2026, fiscalidad IRPF/ITP, financiación LCCI/CIRBE e inversión inmobiliaria).

CONTEXTO TEMPORAL Y NORMATIVO DE ESTE SISTEMA:
- La fecha actual es **{fecha_hoy}**.
- El **Real Decreto-ley 29/2026** (BOE-A-2026-20823, en vigor desde el 08/10/2026 y convalidado por el Congreso; el RDL 28/2026 fue derogado/no convalidado), la **Ley 11/2026 de Cataluña** y la consulta vinculante **DGT V2457-25** son normativa y doctrina oficial vigente cargada en `knowledge_base/`: **NO los marques nunca como futuros o inexistentes**.
- La arquitectura actual usa un núcleo común (`config.py`) + 4 especialistas componibles (`specialists.py`) + memoria en 2 capas (`perfil_usuario` vs. `caso_actual`).
- **IMPORTANTE sobre telemetría:** el bloque técnico oculto `[PROFILE_UPDATE]` se extrae y se ELIMINA del texto antes de guardar la columna `response` en Google Sheets. Por tanto, es **100 % normal** que `[PROFILE_UPDATE]` no aparezca en el texto de `ASISTENTE` en los logs; **NUNCA** lo reportes como fallo (solo revisa si el `Arquetipo` o las respuestas muestran incoherencia real).

Vas a auditar **{rows_count} nuevas interacciones** agrupadas en **{sessions_count} sesiones** ocurridas entre `{period_start}` y `{period_end}` (solo logs NO analizados previamente, excluyendo pruebas automáticas `qa_auto`).

### DOCUMENTOS QUE YA EXISTEN HOY EN `knowledge_base/`:
{kb_inventory}

### EXTRACTOS DE LAS INSTRUCCIONES ACTUALES (`config.py` + `specialists.py`) — NO propongas reglas que ya existan tal cual, salvo si ves que el modelo las incumple y hay que reforzarlas:
{current_prompt}

### CONVERSACIONES NUEVAS A AUDITAR:
{conversations_text}

### TU TAREA:
Analiza con máximo rigor las conversaciones y responde ÚNICAMENTE con un JSON válido con exactamente estas 4 claves de texto:
1. `"summary"`: Resumen ejecutivo breve (3-5 líneas) con temas predominantes, especialistas/arquetipos vistos y calidad general.
2. `"prompt_improvements"`: Lista concisa en texto plano de mejoras concretas para `config.py` o `specialists.py` (o "Sin cambios urgentes en prompt" si todo fue sólido).
3. `"kb_gaps"`: Lista concisa de documentos o datos que faltan en `knowledge_base/` y en qué carpeta (`01_`..`06_`) deberían añadirse.
4. `"full_report_markdown"`: Informe completo en Markdown bien estructurado con estas secciones:
   - `## 1. Resumen ejecutivo` (sesiones, turnos, usuarios/arquetipos/especialistas detectados, nivel de fiabilidad)
   - `## 2. Fallos críticos y contradicciones detectadas` (asunciones no confirmadas, arrastre entre casos, errores de fechas/cálculos, fugas de trazas/rutas, incumplimientos del triaje — citando la sesión/hora exacta)
   - `## 3. Propuestas concretas de ajuste para config.py / specialists.py / logic.py` (reglas listas para revisar y aplicar)
   - `## 4. Huecos detectados en knowledge_base/` (qué fichero concreto añadir y en qué carpeta `01_`..`06_`)
   - `## 5. Observaciones de UX y telemetría` (duplicados, arquetipo vacío, uso de documentos adjuntos, tiempos)
   - `## 6. Nuevos casos recomendados para tests/qa_cases.json` (1–3 escenarios concretos derivados de fallos reales de esta semana para prevenir regresiones)

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

    visible_parts = []
    try:
        for part in (response.candidates[0].content.parts or []):
            if getattr(part, "thought", False):
                continue
            if getattr(part, "text", None):
                visible_parts.append(part.text)
    except Exception:
        pass
    raw_text = ("".join(visible_parts) if visible_parts else (response.text or "")).strip()
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
    _load_local_streamlit_secrets()
    parser = argparse.ArgumentParser(description="Auditoría QA semanal incremental sobre Prompts_Inmobiliaria.")
    parser.add_argument("--dry-run", action="store_true", help="Analiza sin actualizar QA_Aprendizajes.")
    args = parser.parse_args()

    dry_run = args.dry_run or os.environ.get("DRY_RUN", "false").strip().lower() == "true"
    prompts_ws_name = os.environ.get("PROMPTS_WORKSHEET_NAME", "Prompts_Inmobiliaria").strip()
    qa_ws_name = os.environ.get("QA_WORKSHEET_NAME", "QA_Aprendizajes").strip()

    print(f"🔍 Iniciando auditoría QA incremental (dry_run={dry_run})...")
    sh = connect_spreadsheet()
    if dry_run:
        try:
            qa_ws = sh.worksheet(qa_ws_name)
            last_cursor = read_last_cursor(qa_ws)
        except gspread.WorksheetNotFound:
            qa_ws = None
            last_cursor = None
    else:
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
