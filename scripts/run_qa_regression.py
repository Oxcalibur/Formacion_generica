"""
Runner de Pruebas de Regresión Conversacional (qa_auto) — Pre-commit Gate.

Uso:
  py scripts/run_qa_regression.py                       # Ejecuta todas las suites en modo live (si hay API key) o offline
  py scripts/run_qa_regression.py --mode offline        # Solo validaciones deterministas (router, cambio de caso, memoria 2 capas, motor legal) - 0 llamadas API
  py scripts/run_qa_regression.py --suite multi_caso_contaminacion
  py scripts/run_qa_regression.py --no-judge            # Live sin juez LLM (más rápido)
  py scripts/run_qa_regression.py --log-sheet           # Registra las conversaciones en Google Sheets (username='qa_auto')
  py scripts/run_qa_regression.py --log-sheet-on-pass   # Solo registra en Google Sheets si el 100 % pasa en verde

Exit codes:
  0 -> TODAS las suites pasaron (luz verde para commit & push)
  1 -> Alguna aserción o criterio falló (revisar qa_regression_latest.md antes de hacer commit)
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)

# Cargar API Key desde .streamlit/secrets.toml si no está en el entorno
def _load_secrets_into_env() -> Dict[str, Any]:
    secrets_path = ROOT_DIR / ".streamlit" / "secrets.toml"
    loaded: Dict[str, Any] = {}
    if not secrets_path.exists():
        return loaded

    raw_bytes = secrets_path.read_bytes()
    try:
        import tomllib  # Python 3.11+
        loaded = tomllib.loads(raw_bytes.decode("utf-8", errors="replace"))
    except Exception:
        # Fallback simple para líneas KEY = "VALUE"
        text = raw_bytes.decode("utf-8", errors="replace")
        for m in re.finditer(r'^\s*([A-Za-z0-9_]+)\s*=\s*"([^"]+)"', text, flags=re.MULTILINE):
            loaded[m.group(1)] = m.group(2)

    if not os.environ.get("GOOGLE_API_KEY"):
        for k, v in loaded.items():
            if k.startswith("GOOGLE_API_KEY") and isinstance(v, str) and v.strip():
                os.environ["GOOGLE_API_KEY"] = v.strip()
                break
    return loaded


def _norm(text: str) -> str:
    if not text:
        return ""
    nfd = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def _build_base_system_prompt(local_resources: list) -> str:
    from config import CLIENT_CONFIG

    base_prompt = (
        CLIENT_CONFIG["system_prompt"]
        .replace("{client_name}", CLIENT_CONFIG["client_name"])
        .replace("{language}", "es")
        .replace("{multimedia_index_placeholder}", json.dumps(local_resources, ensure_ascii=False) if local_resources else "[]")
    )
    role_context = (
        "\n\nCONTEXTO DE PERFIL EN LA PLATAFORMA (solo orientativo, NO asumir titularidad legal): Propietario / Inversor\n"
        "INSTRUCCIÓN CRÍTICA: CERO ASUNCIONES y SEPARACIÓN DE CASOS. Respeta estrictamente el especialista activado en este turno: "
        "no hagas preguntas irrelevantes en consultas operativas, no inventes tipos de interés ni plazos para refutar cálculos del usuario, "
        "no arrastres hechos de un inmueble anterior a otro nuevo, y nunca muestres rutas ni archivos internos (.md)."
    )
    return base_prompt + role_context


def _evaluate_with_llm_judge(
    prompt_user: str,
    response_text: str,
    criteria: List[str],
    model_name: str,
) -> Tuple[bool, List[str]]:
    """Usa Gemini como juez estricto sobre criterios de matiz (Nivel 2)."""
    if not criteria:
        return True, []

    from google.genai import types
    from logic import llamar_gemini_con_rotacion_y_reintento

    criteria_str = "\n".join(f"{i+1}. {c}" for i, c in enumerate(criteria))
    fecha_hoy = datetime.datetime.now().strftime("%d/%m/%Y")
    judge_prompt = f"""Eres un auditor QA estricto para un Asesor Inmobiliario Integral en España.
CONTEXTO TEMPORAL Y NORMATIVO DE ESTE ENTORNO DE PRUEBAS:
- La fecha actual es {fecha_hoy}.
- El Real Decreto-ley 29/2026 (en vigor desde el 15/11/2026) y la consulta vinculante DGT V2457-25 forman parte de la base normativa oficial vigente del sistema: NO los penalices como inexistentes ni futuros.

Evalúa si la RESPUESTA DEL ASISTENTE cumple TODOS los criterios de calidad listados abajo.

PREGUNTA DEL USUARIO:
{prompt_user}

RESPUESTA DEL ASISTENTE:
{response_text}

CRITERIOS OBLIGATORIOS:
{criteria_str}

Responde ÚNICAMENTE con un JSON válido con esta estructura exacta:
{{
  "passed": true o false,
  "failed_reasons": ["motivo breve de cada criterio incumplido; lista vacía si passed es true"]
}}
Sé objetivo y estricto: si un criterio falla aunque sea parcialmente (por ejemplo, si inventa un 4% a 30 años antes de preguntar o si arrastra Zazume/seguro de otro caso), marca passed=false."""

    try:
        resp = llamar_gemini_con_rotacion_y_reintento(
            model_name=model_name,
            contents=judge_prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        data = json.loads(resp.text)
        passed = bool(data.get("passed", False))
        reasons = [str(r) for r in (data.get("failed_reasons") or [])]
        return passed, reasons
    except Exception as e:
        return False, [f"Error ejecutando juez LLM: {e}"]


def _log_results_to_gsheets(records: List[Dict[str, Any]], spreadsheet_id: str) -> bool:
    """Registra las filas de qa_auto en la pestaña Prompts_Inmobiliaria usando el CLI gsheets si está disponible."""
    if not records:
        return False
    values = [
        [
            r["session_id"],
            r["timestamp"],
            "qa_auto",
            "QA Regression",
            r.get("arquetipo", ""),
            r.get("especialistas", ""),
            r["prompt"],
            (r.get("response", "") or "")[:14000],
            "No",
        ]
        for r in records
    ]
    payload = json.dumps(values, ensure_ascii=False)
    try:
        proc = subprocess.run(
            [
                "gsheets",
                "values",
                "append",
                spreadsheet_id,
                "Prompts_Inmobiliaria!A:I",
                "--values",
                payload,
                "--value-input-option",
                "USER_ENTERED",
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
        if proc.returncode == 0:
            print(f"[Sheets] {len(records)} turnos de qa_auto registrados en Prompts_Inmobiliaria.")
            return True
        print(f"[Sheets] Aviso: no se pudo escribir vía CLI gsheets: {proc.stderr.strip()}")
        return False
    except Exception as e:
        print(f"[Sheets] Aviso: CLI gsheets no disponible ({e}).")
        return False


def _check_turn_assertions(
    turn_spec: Dict[str, Any],
    active_specialists: List[str],
    case_switched: bool,
    conceptual: bool,
    updated_profile: Dict[str, Any],
    response_text: str,
    mode: str,
    case_facts_before_turn: Optional[List[str]] = None,
) -> List[str]:
    """Ejecuta todas las aserciones deterministas (Nivel 1)."""
    errors: List[str] = []

    if "expected_specialists_exact" in turn_spec:
        if active_specialists != turn_spec["expected_specialists_exact"]:
            errors.append(
                f"Especialistas esperados {turn_spec['expected_specialists_exact']}, obtenidos {active_specialists}"
            )

    if "expected_specialists_include" in turn_spec:
        for req in turn_spec["expected_specialists_include"]:
            if req not in active_specialists:
                errors.append(f"Faltó especialista requerido '{req}' (activos: {active_specialists})")

    if "expected_specialists_exclude" in turn_spec:
        for excl in turn_spec["expected_specialists_exclude"]:
            if excl in active_specialists:
                errors.append(f"Especialista prohibido '{excl}' se activó (activos: {active_specialists})")

    if "expected_case_switched" in turn_spec:
        if bool(case_switched) != bool(turn_spec["expected_case_switched"]):
            errors.append(
                f"case_switched esperado={turn_spec['expected_case_switched']}, obtenido={case_switched}"
            )

    if turn_spec.get("expected_case_facts_empty_before_turn") and case_facts_before_turn:
        errors.append(f"hechos_caso NO se limpió al cambiar de caso: {case_facts_before_turn}")

    if "expected_conceptual" in turn_spec:
        if bool(conceptual) != bool(turn_spec["expected_conceptual"]):
            errors.append(f"conceptual esperado={turn_spec['expected_conceptual']}, obtenido={conceptual}")

    if "expected_web_search" in turn_spec:
        from logic import _debe_activar_busqueda_web
        ws_on, _ = _debe_activar_busqueda_web(turn_spec["prompt"])
        if bool(ws_on) != bool(turn_spec["expected_web_search"]):
            errors.append(f"web_search esperado={turn_spec['expected_web_search']}, obtenido={ws_on}")

    if "expected_user_profile" in turn_spec:
        for k, exp_v in turn_spec["expected_user_profile"].items():
            got_v = updated_profile.get(k)
            if got_v != exp_v:
                errors.append(f"Perfil '{k}' esperado={exp_v!r}, obtenido={got_v!r}")

    if "expected_case_fields_null" in turn_spec:
        for k in turn_spec["expected_case_fields_null"]:
            got_v = updated_profile.get(k)
            if got_v is not None:
                errors.append(f"Campo de caso '{k}' debería ser None tras cambio de caso, obtenido={got_v!r}")

    if mode == "live":
        norm_resp = _norm(response_text)
        # Reglas globales anti-fuga que aplican a TODOS los turnos de TODAS las suites
        global_forbidden = ("tool_code", "google_search.search", "print(google_search", "thought the user", "\nthought ")
        for gf in global_forbidden:
            if gf in norm_resp:
                errors.append(f"FUGA INTERNA DEL MODELO detectada en respuesta visible: '{gf}'")
        for forbidden in turn_spec.get("must_not_contain", []):
            if _norm(forbidden) in norm_resp:
                errors.append(f"Texto prohibido encontrado en respuesta: '{forbidden}'")

        for group in turn_spec.get("must_contain_any", []):
            if not any(_norm(opt) in norm_resp for opt in group):
                errors.append(f"Falta al menos uno de estos conceptos requeridos: {group}")

    return errors


def run_regression(
    mode: str,
    suite_filter: str,
    use_judge: bool,
    log_sheet: bool,
    log_sheet_on_pass: bool,
) -> int:
    _load_secrets_into_env()

    has_api_key = bool(os.environ.get("GOOGLE_API_KEY"))
    if mode == "auto":
        mode = "live" if has_api_key else "offline"
    if mode == "live" and not has_api_key:
        print("ERROR: Modo 'live' requiere GOOGLE_API_KEY en .streamlit/secrets.toml o variable de entorno.")
        print("       Puedes ejecutar '--mode offline' para validar la lógica determinista sin API key.")
        return 1

    from config import CLIENT_CONFIG
    from logic import (
        aplicar_motor_a_perfil,
        get_chat_response,
        get_default_session_profile,
        load_multimedia_resources,
        reset_case_state,
        _extract_explicit_facts_from_user_text,
    )
    from specialists import (
        detect_case_switch,
        format_specialists_badge,
        is_conceptual_question,
        route_specialists,
        score_domains,
    )

    cases_path = ROOT_DIR / "tests" / "qa_cases.json"
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    suites = data.get("suites", [])
    if suite_filter and suite_filter != "all":
        suites = [s for s in suites if s.get("id") == suite_filter]
        if not suites:
            print(f"ERROR: Suite '{suite_filter}' no encontrada en tests/qa_cases.json.")
            return 1

    kb_path = str(ROOT_DIR / "knowledge_base")
    local_resources = load_multimedia_resources(kb_path)
    system_prompt = _build_base_system_prompt(local_resources)
    model_name = CLIENT_CONFIG.get("ai_model", "gemini-2.5-flash")

    run_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    all_passed = True
    total_turns = 0
    passed_turns = 0
    sheet_records: List[Dict[str, Any]] = []
    report_lines = [
        f"# Informe de Regresión QA (`qa_auto` — modo `{mode}`)",
        f"- **Fecha:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Modelo:** `{model_name}` | **Juez LLM:** `{'ON' if (mode == 'live' and use_judge) else 'OFF'}`",
        "",
    ]

    print(f"\n=== QA REGRESSION GATE (qa_auto | mode={mode} | suites={len(suites)}) ===\n")

    for suite in suites:
        suite_id = suite["id"]
        session_id = f"qa_{run_stamp}_{suite_id[:12]}"
        history: List[Dict[str, str]] = []
        profile = get_default_session_profile()

        print(f"--- Suite: {suite['name']} ({suite_id}) ---")
        report_lines.append(f"## Suite: {suite['name']} (`{suite_id}`)")
        report_lines.append("")

        for turn in suite.get("turns", []):
            total_turns += 1
            turn_id = turn["turn_id"]
            user_prompt = turn["prompt"]
            t0 = time.time()

            history.append({"role": "user", "content": user_prompt})
            prior_user_turns = sum(1 for m in history[:-1] if m.get("role") == "user")
            prev_specs = list(profile.get("especialistas_activos") or [])

            if mode == "offline":
                scores = score_domains(user_prompt)
                case_switched, switch_reason = detect_case_switch(
                    user_prompt, profile, prev_specs, scores, has_prior_turns=prior_user_turns > 0
                )
                if case_switched:
                    profile = reset_case_state(profile, case_start_idx=max(0, len(history) - 1))
                case_facts_before = list(profile.get("hechos_caso") or [])
                routing = route_specialists(
                    user_prompt,
                    prev_specialists=None if case_switched else prev_specs,
                    case_switched=case_switched,
                )
                active_specs = routing["active_ids"]
                conceptual = bool(routing.get("conceptual"))
                if not conceptual:
                    profile["especialistas_activos"] = list(active_specs)
                profile = _extract_explicit_facts_from_user_text(user_prompt, profile, active_specs)
                if turn.get("simulate_case_facts"):
                    profile["hechos_caso"] = list(dict.fromkeys((profile.get("hechos_caso") or []) + turn["simulate_case_facts"]))
                profile, _ = aplicar_motor_a_perfil(profile)
                response_text = "[offline]"
                specialists_badge = format_specialists_badge(active_specs)
                history.append({"role": "assistant", "content": response_text})
            else:
                # Comprobar limpieza tras reset (antes de respuesta)
                scores = score_domains(user_prompt)
                pre_switched, _ = detect_case_switch(
                    user_prompt, profile, prev_specs, scores, has_prior_turns=prior_user_turns > 0
                )
                case_facts_before = [] if pre_switched else list(profile.get("hechos_caso") or [])

                resp = get_chat_response(
                    history=history,
                    user_input=user_prompt,
                    system_instruction=system_prompt,
                    multimedia_index=local_resources,
                    kb_folder=kb_path,
                    session_profile=profile,
                )
                response_text = resp.get("text", "")
                profile = resp.get("updated_profile", profile)
                active_specs = resp.get("specialists", [])
                specialists_badge = resp.get("specialists_badge", format_specialists_badge(active_specs))
                case_switched = bool(resp.get("case_switched", False))
                conceptual = is_conceptual_question(user_prompt)
                history.append({"role": "assistant", "content": response_text})

            errors = _check_turn_assertions(
                turn_spec=turn,
                active_specialists=active_specs,
                case_switched=case_switched,
                conceptual=conceptual,
                updated_profile=profile,
                response_text=response_text,
                mode=mode,
                case_facts_before_turn=case_facts_before,
            )

            judge_reasons: List[str] = []
            if mode == "live" and use_judge and turn.get("judge_criteria"):
                j_ok, judge_reasons = _evaluate_with_llm_judge(
                    prompt_user=user_prompt,
                    response_text=response_text,
                    criteria=turn["judge_criteria"],
                    model_name=model_name,
                )
                if not j_ok:
                    errors.extend([f"[Juez LLM] {r}" for r in judge_reasons])

            elapsed = time.time() - t0
            turn_ok = len(errors) == 0
            if turn_ok:
                passed_turns += 1
                status_icon = "PASS"
            else:
                all_passed = False
                status_icon = "FAIL"

            print(
                f"  [{status_icon}] {turn_id} | {specialists_badge} | switch={case_switched} | {elapsed:.1f}s"
            )
            for err in errors:
                print(f"         -> {err}")

            sheet_records.append(
                {
                    "session_id": session_id,
                    "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "arquetipo": str(profile.get("arquetipo_detectado") or ""),
                    "especialistas": specialists_badge,
                    "prompt": user_prompt,
                    "response": response_text,
                }
            )

            report_lines.append(f"### {'✅' if turn_ok else '❌'} `{turn_id}` ({elapsed:.1f}s)")
            report_lines.append(f"- **Especialistas:** {specialists_badge} | **Cambio de caso:** `{case_switched}` | **Arquetipo:** `{profile.get('arquetipo_detectado')}` | **Gran Tenedor:** `{profile.get('gran_tenedor')}`")
            report_lines.append(f"- **Prompt:** {user_prompt}")
            if errors:
                report_lines.append("- **Fallos detectados:**")
                for err in errors:
                    report_lines.append(f"  - {err}")
            if mode == "live":
                report_lines.append("")
                report_lines.append("<details><summary>Ver respuesta completa</summary>\n\n" + response_text + "\n\n</details>")
            report_lines.append("")

    summary_line = f"Resultado global: {passed_turns}/{total_turns} turnos superados ({'VERDE - LISTO PARA COMMIT' if all_passed else 'ROJO - AJUSTAR ANTES DE COMMIT'})"
    print(f"\n=== {summary_line} ===")

    report_lines.insert(4, f"- **{summary_line}**\n")
    report_path = ROOT_DIR / "qa_regression_latest.md"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    print(f"Informe guardado en: {report_path}")

    # Solo escribir en Google Sheets cuando genere valor (explícito por flag)
    should_log = (mode == "live") and (log_sheet or (log_sheet_on_pass and all_passed))
    if should_log:
        spreadsheet_id = "17XRCtvPXy1l5pstQxdYul_WqNrf2EkzbhheBvZUDDsE"
        _log_results_to_gsheets(sheet_records, spreadsheet_id)

    return 0 if all_passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Pre-commit QA regression suite (qa_auto)")
    parser.add_argument("--mode", choices=["auto", "live", "offline"], default="auto")
    parser.add_argument("--suite", default="all", help="ID de suite en tests/qa_cases.json o 'all'")
    parser.add_argument("--no-judge", action="store_true", help="Desactivar juez LLM (solo aserciones deterministas)")
    parser.add_argument("--log-sheet", action="store_true", help="Registrar resultados en Google Sheets (qa_auto)")
    parser.add_argument("--log-sheet-on-pass", action="store_true", help="Registrar en Sheets solo si pasa el 100%")
    args = parser.parse_args()

    code = run_regression(
        mode=args.mode,
        suite_filter=args.suite,
        use_judge=not args.no_judge,
        log_sheet=args.log_sheet,
        log_sheet_on_pass=args.log_sheet_on_pass,
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
