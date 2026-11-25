"""
Generador Seguro de Mejoras Automáticas Semanales (Paso 2 del Pipeline QA en GitHub Actions).

Lee el informe generado por `scripts/weekly_qa_audit.py` (`qa_report_latest.md` + `qa_report_meta.json`),
evalúa si existen mejoras concretas, seguras y de alto impacto (no duplicadas), y aplica únicamente
cambios en la lista blanca permitida:
  1. Nuevos casos de regresión validados en `tests/qa_cases.json`.
  2. Parches quirúrgicos (búsqueda y reemplazo exacto) en `config.py`, `specialists.py` o
     documentos `.md` existentes dentro de `knowledge_base/`.
  3. Nuevos documentos `.md` en carpetas permitidas de `knowledge_base/`
     (`02_Jurisprudencia_y_Criterios/`, `04_Datos_Volatiles_y_CCAA/`, `06_Estrategia_Inversion_y_Mercado/`).

Seguridad:
- NUNCA modifica workflows, auth, secrets ni lógica crítica de seguridad.
- Verifica compilación Python (`py_compile`) y validez JSON de `tests/qa_cases.json` tras aplicar parches.
- Si algo falla, revierte automáticamente los archivos tocados y marca `has_changes: false`.
- Escribe `qa_autofix_meta.json` y `qa_autofix_summary.md` para el paso siguiente del workflow
  (ejecución de `scripts/run_qa_regression.py --mode live` y apertura de Pull Request).
"""

import json
import os
import py_compile
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

from google import genai
from google.genai import types

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from scripts.weekly_qa_audit import (
    _extract_clean_secret_value,
    _load_local_streamlit_secrets,
    build_kb_inventory_summary,
)

REPORT_PATH = ROOT_DIR / "qa_report_latest.md"
META_PATH = ROOT_DIR / "qa_report_meta.json"
AUTOFIX_META_PATH = ROOT_DIR / "qa_autofix_meta.json"
AUTOFIX_SUMMARY_PATH = ROOT_DIR / "qa_autofix_summary.md"
QA_CASES_PATH = ROOT_DIR / "tests" / "qa_cases.json"

ALLOWED_PATCH_FILES = {
    "config.py",
    "specialists.py",
}
ALLOWED_NEW_KB_PREFIXES = (
    "knowledge_base/02_Jurisprudencia_y_Criterios/",
    "knowledge_base/04_Datos_Volatiles_y_CCAA/",
    "knowledge_base/06_Estrategia_Inversion_y_Mercado/",
)


def _is_allowed_patch_path(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/").strip().lstrip("./")
    if ".." in norm or norm.startswith("/"):
        return False
    if norm in ALLOWED_PATCH_FILES:
        return True
    if norm.startswith("knowledge_base/") and norm.endswith(".md"):
        return (ROOT_DIR / norm).exists()
    return False


def _is_allowed_new_kb_path(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/").strip().lstrip("./")
    if ".." in norm or norm.startswith("/") or not norm.endswith(".md"):
        return False
    return any(norm.startswith(prefix) for prefix in ALLOWED_NEW_KB_PREFIXES)


def _validate_new_suite(suite: Any, existing_ids: set) -> bool:
    if not isinstance(suite, dict):
        return False
    sid = str(suite.get("id") or "").strip()
    if not sid or sid in existing_ids or not re.match(r"^[a-z0-9_]{3,50}$", sid):
        return False
    if not str(suite.get("name") or "").strip():
        return False
    turns = suite.get("turns")
    if not isinstance(turns, list) or not (1 <= len(turns) <= 3):
        return False
    valid_specs = {"operativa_gestion", "inversion_financiacion", "fiscalidad", "legal_arrendamientos"}
    for t in turns:
        if not isinstance(t, dict):
            return False
        if not str(t.get("turn_id") or "").strip() or not str(t.get("prompt") or "").strip():
            return False
        for k in ("expected_specialists_exact", "expected_specialists_include", "expected_specialists_exclude"):
            if k in t:
                if not isinstance(t[k], list) or not all(s in valid_specs for s in t[k]):
                    return False
    return True


def _write_meta(meta: Dict[str, Any], summary_md: str = "") -> None:
    AUTOFIX_META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if summary_md:
        AUTOFIX_SUMMARY_PATH.write_text(summary_md, encoding="utf-8")


def main() -> None:
    _load_local_streamlit_secrets()

    if not META_PATH.exists() or not REPORT_PATH.exists():
        print("Sin informe semanal previo (qa_report_latest.md). Saltando autofix.")
        _write_meta({"has_changes": False, "reason": "no_report"})
        return

    report_meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    if not report_meta.get("has_report"):
        print("Sin nuevas interacciones esta semana. Saltando autofix.")
        _write_meta({"has_changes": False, "reason": "no_new_interactions"})
        return

    api_key = _extract_clean_secret_value(os.environ.get("GOOGLE_API_KEY", ""))
    if not api_key:
        print("Falta GOOGLE_API_KEY para autofix.")
        _write_meta({"has_changes": False, "reason": "missing_api_key"})
        return

    report_md = REPORT_PATH.read_text(encoding="utf-8")
    config_src = (ROOT_DIR / "config.py").read_text(encoding="utf-8")
    specialists_src = (ROOT_DIR / "specialists.py").read_text(encoding="utf-8")
    qa_cases_data = json.loads(QA_CASES_PATH.read_text(encoding="utf-8"))
    kb_inventory = build_kb_inventory_summary()

    existing_suite_ids = [s.get("id") for s in qa_cases_data.get("suites", [])]

    prompt = f"""
Eres un Ingeniero Senior de Mantenimiento de Agentes IA para el proyecto **Asesor Inmobiliario Integral** (España).
Acabas de recibir el informe de Auditoría QA Semanal generado sobre conversaciones reales de usuarios.

TU OBJETIVO:
Proponer **ÚNICAMENTE** cambios **quirúrgicos, seguros, concretos y de alto valor** que corrijan fallos REALES que **todavía NO estén ya resueltos** en `config.py`, `specialists.py` o `knowledge_base/`.
- Si los fallos del informe ya están cubiertos en el código actual (por ejemplo, sesiones antiguas antes de los últimos parches) o son solo observaciones menores, devuelve listas vacías (`has_actionable_changes: false`).
- **PROHIBIDO** duplicar reglas ya existentes en `config.py` o `specialists.py`.
- **PROHIBIDO** inventar leyes, sentencias o códigos DGT que no sean reales y contrastados.
- **MÁXIMO** 2 parches quirúrgicos + 1 nuevo documento KB (solo si hay hueco claro) + 1-2 nuevas suites de regresión para `tests/qa_cases.json`.

### INVENTARIO ACTUAL DE `knowledge_base/`:
{kb_inventory}

### SUITES YA EXISTENTES EN `tests/qa_cases.json`:
{json.dumps(existing_suite_ids, ensure_ascii=False)}

### CONTENIDO ACTUAL DE `config.py` (extracto):
{config_src[:14000]}

### CONTENIDO ACTUAL DE `specialists.py` (extracto):
{specialists_src[:16000]}

### INFORME DE AUDITORÍA QA SEMANAL:
{report_md[:24000]}

### FORMATO DE SALIDA (JSON ESTRICTO ÚNICAMENTE):
{{
  "has_actionable_changes": true o false,
  "rationale": "Explicación breve en español de qué se cambia y qué hallazgos se descartaron por estar ya cubiertos.",
  "file_patches": [
    {{
      "path": "config.py o specialists.py o knowledge_base/.../*.md",
      "description": "Qué mejora aporta este parche",
      "target": "Fragmento EXACTO literal existente en el archivo (mínimo 40 caracteres para ser único)",
      "replacement": "Reemplazo exacto"
    }}
  ],
  "new_kb_files": [
    {{
      "path": "knowledge_base/04_Datos_Volatiles_y_CCAA/ejemplo.md",
      "description": "Por qué aporta valor este nuevo documento",
      "content": "---\\ntipo: ...\\n---\\n# Título\\n..."
    }}
  ],
  "new_qa_suites": [
    {{
      "id": "snake_case_unico",
      "name": "Nombre descriptivo de la suite",
      "description": "Qué bug real previene",
      "turns": [
        {{
          "turn_id": "T1_ejemplo",
          "prompt": "Pregunta realista del usuario",
          "expected_specialists_include": ["legal_arrendamientos"],
          "expected_case_switched": false,
          "must_not_contain": [".md"],
          "judge_criteria": ["Criterio claro y verificable"]
        }}
      ]
    }}
  ]
}}
"""

    model_name = os.environ.get("GEMINI_QA_MODEL", "gemini-2.5-flash").strip()
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(api_version="v1beta"),
    )
    cfg_kwargs: Dict[str, Any] = {
        "temperature": 0.1,
        "response_mime_type": "application/json",
    }
    if "2.5" in model_name and hasattr(types, "ThinkingConfig"):
        cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=2048)

    resp = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(**cfg_kwargs),
    )

    visible_parts = []
    try:
        for part in (resp.candidates[0].content.parts or []):
            if getattr(part, "thought", False):
                continue
            if getattr(part, "text", None):
                visible_parts.append(part.text)
    except Exception:
        pass
    raw_text = ("".join(visible_parts) if visible_parts else (resp.text or "")).strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()

    plan = json.loads(raw_text)
    rationale = str(plan.get("rationale") or "").strip()

    if not plan.get("has_actionable_changes"):
        print(f"Sin mejoras accionables pendientes esta semana: {rationale}")
        _write_meta({"has_changes": False, "reason": "no_actionable_changes", "rationale": rationale})
        return

    backups: Dict[Path, Any] = {}
    applied_changes: List[str] = []

    try:
        # 1. Aplicar parches quirúrgicos permitidos (máx 2)
        for patch in (plan.get("file_patches") or [])[:2]:
            rel = str(patch.get("path") or "").strip().replace("\\", "/")
            target = str(patch.get("target") or "")
            replacement = str(patch.get("replacement") or "")
            desc = str(patch.get("description") or rel).strip()
            if not _is_allowed_patch_path(rel) or len(target) < 30 or not replacement:
                continue
            fpath = ROOT_DIR / rel
            original = fpath.read_text(encoding="utf-8")
            if original.count(target) != 1:
                print(f"  [Saltado] Parche en {rel}: target no coincide exactamente 1 vez.")
                continue
            if fpath not in backups:
                backups[fpath] = original
            fpath.write_text(original.replace(target, replacement, 1), encoding="utf-8")
            applied_changes.append(f"Parche en `{rel}`: {desc}")

        # 2. Crear nuevos documentos KB permitidos (máx 1)
        for kb_item in (plan.get("new_kb_files") or [])[:1]:
            rel = str(kb_item.get("path") or "").strip().replace("\\", "/")
            content = str(kb_item.get("content") or "").strip()
            desc = str(kb_item.get("description") or rel).strip()
            if not _is_allowed_new_kb_path(rel) or len(content) < 120:
                continue
            fpath = ROOT_DIR / rel
            if fpath.exists():
                continue
            backups[fpath] = None  # marcar para borrado si hay rollback
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content + "\n", encoding="utf-8")
            applied_changes.append(f"Nuevo documento KB `{rel}`: {desc}")

        # 3. Añadir nuevas suites de regresión válidas (máx 2)
        existing_ids_set = {s.get("id") for s in qa_cases_data.get("suites", [])}
        new_suites_added = 0
        for suite in (plan.get("new_qa_suites") or [])[:2]:
            if _validate_new_suite(suite, existing_ids_set):
                if QA_CASES_PATH not in backups:
                    backups[QA_CASES_PATH] = QA_CASES_PATH.read_text(encoding="utf-8")
                qa_cases_data["suites"].append(suite)
                existing_ids_set.add(suite["id"])
                new_suites_added += 1
                applied_changes.append(f"Nueva suite QA `{suite['id']}` en `tests/qa_cases.json`: {suite['name']}")

        if new_suites_added > 0:
            QA_CASES_PATH.write_text(json.dumps(qa_cases_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        if not applied_changes:
            print("Ningún cambio propuesto pasó las validaciones de seguridad.")
            _write_meta({"has_changes": False, "reason": "no_valid_patches", "rationale": rationale})
            return

        # 4. Verificar compilación de los módulos Python críticos
        for py_file in ("config.py", "specialists.py", "logic.py", "streamlit_app.py"):
            py_compile.compile(str(ROOT_DIR / py_file), doraise=True)

        # Verificar que tests/qa_cases.json sigue siendo JSON válido
        json.loads(QA_CASES_PATH.read_text(encoding="utf-8"))

    except Exception as e:
        print(f"ERROR aplicando cambios ({e}). Revirtiendo todos los archivos...")
        for fpath, orig in backups.items():
            if orig is None:
                if fpath.exists():
                    fpath.unlink()
            else:
                fpath.write_text(orig, encoding="utf-8")
        _write_meta({"has_changes": False, "reason": f"rollback_on_error: {e}", "rationale": rationale})
        return

    audit_date = report_meta.get("audit_date", "latest")
    branch_name = f"qa/mejoras-{audit_date}"
    summary_lines = [
        f"## Propuesta automática de mejoras QA ({audit_date})",
        "",
        f"**Criterio aplicado:** {rationale}",
        "",
        "### Cambios aplicados en esta rama:",
    ]
    for item in applied_changes:
        summary_lines.append(f"- {item}")
    summary_md = "\n".join(summary_lines) + "\n"

    _write_meta(
        {
            "has_changes": True,
            "branch": branch_name,
            "audit_date": audit_date,
            "rationale": rationale,
            "changes": applied_changes,
        },
        summary_md=summary_md,
    )
    print(f"Autofix aplicó {len(applied_changes)} mejora(s) segura(s) listas para la puerta de regresión LIVE.")


if __name__ == "__main__":
    main()
