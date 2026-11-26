import json
import html as _html
import streamlit as st
import streamlit.components.v1 as components

error_msg = ""
try:
    from streamlit_mic_recorder import speech_to_text
except Exception as e:
    speech_to_text = None
    error_msg = str(e)

DEFAULT_SIMULATOR_PARAMS = {
    "titulo": "Simulador Interactivo de Inversión Inmobiliaria",
    "precio_compra": 180000,
    "itp_pct": 6.0,
    "gastos_compra": 2500,
    "reforma": 5000,
    "ltv_pct": 70,
    "interes_pct": 3.0,
    "plazo_anos": 30,
    "renta_mensual": 950,
    "ibi_anual": 250,
    "comunidad_mensual": 50,
    "seguro_hogar": 250,
    "seguro_impago_pct": 4.5,
    "mantenimiento_pct": 5.0,
    "vacancia_pct": 5.0,
    "reduccion_irpf_pct": 50,
    "tipo_marginal_irpf_pct": 30,
    "pct_construccion": 70,
}


def sanitize_simulator_params(raw: dict | None) -> dict:
    """Valida, limpia y acota los parámetros iniciales del simulador para evitar valores inválidos."""
    out = dict(DEFAULT_SIMULATOR_PARAMS)
    if not isinstance(raw, dict):
        return out

    if raw.get("titulo"):
        out["titulo"] = str(raw["titulo"]).strip()[:110]

    bounds = {
        "precio_compra": (20000, 1500000, float),
        "itp_pct": (0.0, 15.0, float),
        "gastos_compra": (0, 25000, float),
        "reforma": (0, 250000, float),
        "ltv_pct": (0, 95, float),
        "interes_pct": (0.0, 10.0, float),
        "plazo_anos": (5, 40, int),
        "renta_mensual": (200, 8000, float),
        "ibi_anual": (0, 5000, float),
        "comunidad_mensual": (0, 800, float),
        "seguro_hogar": (0, 2000, float),
        "seguro_impago_pct": (0.0, 10.0, float),
        "mantenimiento_pct": (0.0, 20.0, float),
        "vacancia_pct": (0.0, 25.0, float),
        "reduccion_irpf_pct": (0, 100, int),
        "tipo_marginal_irpf_pct": (19, 47, int),
        "pct_construccion": (20, 95, int),
    }
    for k, (lo, hi, caster) in bounds.items():
        if k in raw and raw[k] is not None:
            try:
                val = caster(float(str(raw[k]).replace(",", ".").replace("€", "").replace("%", "").strip()))
                out[k] = max(lo, min(hi, val))
            except (ValueError, TypeError):
                pass
    # Ajustar reducción IRPF al valor legal más cercano del selector
    valid_red = (0, 50, 60, 70, 90, 100)
    out["reduccion_irpf_pct"] = min(valid_red, key=lambda x: abs(x - out["reduccion_irpf_pct"]))
    return out


def render_investment_simulator(params: dict | None = None, height: int = 870) -> None:
    """
    Renderiza un simulador inmobiliario 100 % interactivo en tiempo real (HTML5 + JS puro,
    0 ms de latencia al arrastrar sliders y sin provocar recargas de Streamlit ni llamadas a la API).
    Incluye cálculo exacto de hipoteca francesa, ITP, Cash-Flow, ROCE e IRPF español (amortización 3 % y Art. 23.2 LIRPF).
    """
    cfg = sanitize_simulator_params(params)
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    safe_title = _html.escape(cfg["titulo"])

    max_precio = max(600000, int(cfg["precio_compra"] * 1.8 // 10000 * 10000))
    max_renta = max(3500, int(cfg["renta_mensual"] * 2.2 // 50 * 50))
    max_reforma = max(100000, int(cfg["reforma"] * 2 // 1000 * 1000))

    widget_html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  body {{ margin: 0; padding: 6px; background: transparent; color: #1e293b; }}
  .sim-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 10px rgba(15, 23, 42, 0.05);
  }}
  .sim-header {{
    display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;
    border-bottom: 1px solid #e2e8f0; padding-bottom: 10px; margin-bottom: 14px;
  }}
  .sim-title {{ font-size: 15px; font-weight: 700; color: #0f172a; margin: 0; }}
  .sim-sub {{ font-size: 12px; color: #64748b; margin-top: 2px; }}
  .sim-btn {{
    background: #f1f5f9; border: 1px solid #cbd5e1; color: #334155; border-radius: 8px;
    padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer;
  }}
  .sim-btn:hover {{ background: #e2e8f0; }}

  .kpi-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
    gap: 10px; margin-bottom: 14px;
  }}
  .kpi {{
    background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px;
  }}
  .kpi.highlight {{ background: #f0f9ff; border-color: #7dd3fc; }}
  .kpi.good {{ background: #ecfdf5; border-color: #6ee7b7; }}
  .kpi.warn {{ background: #fffbeb; border-color: #fcd34d; }}
  .kpi.bad {{ background: #fef2f2; border-color: #fca5a5; }}
  .kpi-label {{ font-size: 11px; color: #475569; font-weight: 600; text-transform: uppercase; letter-spacing: .02em; }}
  .kpi-val {{ font-size: 19px; font-weight: 800; color: #0f172a; margin-top: 3px; }}
  .kpi-sub {{ font-size: 11px; color: #64748b; margin-top: 2px; }}

  .bar-wrap {{ margin-bottom: 16px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 10px 12px; }}
  .bar-title {{ font-size: 12px; font-weight: 700; color: #334155; margin-bottom: 7px; display: flex; justify-content: space-between; }}
  .stacked-bar {{ display: flex; height: 18px; border-radius: 9px; overflow: hidden; background: #e2e8f0; }}
  .seg-hip {{ background: #3b82f6; }}
  .seg-gas {{ background: #f59e0b; }}
  .seg-irpf {{ background: #ef4444; }}
  .seg-cf {{ background: #10b981; }}
  .legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 7px; font-size: 11px; color: #475569; }}
  .dot {{ display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }}

  .sections {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
  .sec {{ background: #fbfdff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 11px 13px; }}
  .sec h4 {{ margin: 0 0 9px 0; font-size: 12.5px; color: #0284c7; text-transform: uppercase; letter-spacing: .03em; }}
  .ctrl {{ margin-bottom: 9px; }}
  .ctrl:last-child {{ margin-bottom: 0; }}
  .ctrl-top {{ display: flex; justify-content: space-between; align-items: center; font-size: 12px; margin-bottom: 3px; }}
  .ctrl-name {{ color: #334155; font-weight: 500; }}
  .ctrl-val {{ font-weight: 700; color: #0f172a; font-variant-numeric: tabular-nums; }}
  input[type="range"] {{
    width: 100%; accent-color: #00a8e8; cursor: pointer; height: 5px;
  }}
  select {{
    width: 100%; padding: 5px 8px; border: 1px solid #cbd5e1; border-radius: 7px;
    font-size: 12px; background: #fff; color: #0f172a;
  }}

  .summary-table {{
    margin-top: 12px; width: 100%; border-collapse: collapse; font-size: 12px;
  }}
  .summary-table td {{ padding: 5px 6px; border-bottom: 1px solid #f1f5f9; }}
  .summary-table td:last-child {{ text-align: right; font-weight: 700; font-variant-numeric: tabular-nums; }}
  .note {{ margin-top: 8px; font-size: 11px; color: #64748b; line-height: 1.4; }}
</style>
</head>
<body>
<div class="sim-card">
  <div class="sim-header">
    <div>
      <div class="sim-title">🧮 {safe_title}</div>
      <div class="sim-sub">Mueve cualquier barra para simular escenarios en tiempo real (0 ms · cálculo exacto)</div>
    </div>
    <button class="sim-btn" id="btnReset">↺ Restaurar valores</button>
  </div>

  <div class="kpi-grid">
    <div class="kpi highlight">
      <div class="kpi-label">Capital propio</div>
      <div class="kpi-val" id="k_cap">-</div>
      <div class="kpi-sub" id="k_inv">Inversión total: -</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Rent. Bruta / Neta</div>
      <div class="kpi-val" id="k_rent">-</div>
      <div class="kpi-sub" id="k_cuota">Cuota hipoteca: -</div>
    </div>
    <div class="kpi" id="box_cf">
      <div class="kpi-label">Cash-Flow Neto / mes</div>
      <div class="kpi-val" id="k_cfm">-</div>
      <div class="kpi-sub" id="k_cfa">Anual tras IRPF: -</div>
    </div>
    <div class="kpi" id="box_roce">
      <div class="kpi-label">ROCE Neto (tras IRPF)</div>
      <div class="kpi-val" id="k_roce">-</div>
      <div class="kpi-sub" id="k_roce_tot">Con amort. capital: -</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">IRPF estimado / año</div>
      <div class="kpi-val" id="k_irpf">-</div>
      <div class="kpi-sub" id="k_base">Base reducida: -</div>
    </div>
  </div>

  <div class="bar-wrap">
    <div class="bar-title">
      <span>Distribución de cada euro de alquiler mensual</span>
      <span id="bar_renta_lbl">-</span>
    </div>
    <div class="stacked-bar">
      <div class="seg-hip" id="seg_hip" style="width:0%"></div>
      <div class="seg-gas" id="seg_gas" style="width:0%"></div>
      <div class="seg-irpf" id="seg_irpf" style="width:0%"></div>
      <div class="seg-cf" id="seg_cf" style="width:0%"></div>
    </div>
    <div class="legend">
      <span><i class="dot" style="background:#3b82f6"></i>Hipoteca: <b id="l_hip">-</b></span>
      <span><i class="dot" style="background:#f59e0b"></i>Gastos + Vacancia: <b id="l_gas">-</b></span>
      <span><i class="dot" style="background:#ef4444"></i>IRPF: <b id="l_irpf">-</b></span>
      <span><i class="dot" style="background:#10b981"></i>Cash-Flow neto: <b id="l_cf">-</b></span>
    </div>
  </div>

  <div class="sections">
    <div class="sec">
      <h4>1. Compra e Impuestos</h4>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">CCAA (ITP general orientativo)</span></div>
        <select id="sel_ccaa">
          <option value="">Personalizado (usar barra ITP)</option>
          <option value="6">Madrid (6 %)</option>
          <option value="7">Andalucía (7 %)</option>
          <option value="10">Cataluña (10 %)</option>
          <option value="10">Comunidad Valenciana (10 %)</option>
          <option value="4">País Vasco (4 %)</option>
          <option value="6">Navarra (6 %)</option>
          <option value="6.5">Canarias (6,5 %)</option>
          <option value="8">Aragón / Asturias / Murcia / C. León (8 %)</option>
          <option value="9">Castilla-La Mancha / Cantabria (9 %)</option>
          <option value="8">Galicia / Baleares (8 %)</option>
        </select>
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Precio de compra</span><span class="ctrl-val" id="v_precio"></span></div>
        <input type="range" id="precio_compra" min="20000" max="{max_precio}" step="1000" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">ITP (%)</span><span class="ctrl-val" id="v_itp"></span></div>
        <input type="range" id="itp_pct" min="0" max="13" step="0.5" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Reforma + amueblado + agencia</span><span class="ctrl-val" id="v_ref"></span></div>
        <input type="range" id="reforma" min="0" max="{max_reforma}" step="500" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Notaría + Registro + Gestoría</span><span class="ctrl-val" id="v_gcompra"></span></div>
        <input type="range" id="gastos_compra" min="500" max="10000" step="250" />
      </div>
    </div>

    <div class="sec">
      <h4>2. Financiación (Hipoteca)</h4>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">% Financiado (LTV · 0 % = contado)</span><span class="ctrl-val" id="v_ltv"></span></div>
        <input type="range" id="ltv_pct" min="0" max="90" step="5" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Tipo de interés (TIN)</span><span class="ctrl-val" id="v_tin"></span></div>
        <input type="range" id="interes_pct" min="0.5" max="7.5" step="0.1" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Plazo hipoteca</span><span class="ctrl-val" id="v_plazo"></span></div>
        <input type="range" id="plazo_anos" min="5" max="40" step="1" />
      </div>
      <table class="summary-table">
        <tr><td>Importe hipoteca</td><td id="t_hip">-</td></tr>
        <tr><td>Intereses deducibles Año 1</td><td id="t_int1">-</td></tr>
        <tr><td>Principal amortizado Año 1</td><td id="t_prin1">-</td></tr>
      </table>
    </div>

    <div class="sec">
      <h4>3. Alquiler y Gastos Operativos</h4>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Renta mensual estimada</span><span class="ctrl-val" id="v_renta"></span></div>
        <input type="range" id="renta_mensual" min="250" max="{max_renta}" step="25" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">IBI anual / Comunidad mensual</span><span class="ctrl-val" id="v_ibicom"></span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
          <input type="range" id="ibi_anual" min="0" max="2500" step="25" title="IBI anual" />
          <input type="range" id="comunidad_mensual" min="0" max="350" step="5" title="Comunidad mensual" />
        </div>
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Seguro hogar anual</span><span class="ctrl-val" id="v_segh"></span></div>
        <input type="range" id="seguro_hogar" min="0" max="1000" step="25" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Seguro impago (% renta)</span><span class="ctrl-val" id="v_segi"></span></div>
        <input type="range" id="seguro_impago_pct" min="0" max="8" step="0.5" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Mantenimiento / Vacancia (% renta)</span><span class="ctrl-val" id="v_mantvac"></span></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
          <input type="range" id="mantenimiento_pct" min="0" max="15" step="0.5" title="Mantenimiento %" />
          <input type="range" id="vacancia_pct" min="0" max="15" step="0.5" title="Vacancia %" />
        </div>
      </div>
    </div>

    <div class="sec">
      <h4>4. Fiscalidad IRPF (Persona Física)</h4>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Reducción Art. 23.2 LIRPF</span></div>
        <select id="reduccion_irpf_pct">
          <option value="0">0 % (Temporada / sin reducción)</option>
          <option value="50">50 % (Vivienda habitual general)</option>
          <option value="60">60 % (Rehabilitación reciente)</option>
          <option value="70">70 % (Jóvenes / asequible en ZT)</option>
          <option value="90">90 % (Rebaja >5 % en ZT)</option>
          <option value="100">100 % (Supuestos RDL 29/2026)</option>
        </select>
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">Tipo marginal IRPF</span><span class="ctrl-val" id="v_marg"></span></div>
        <input type="range" id="tipo_marginal_irpf_pct" min="19" max="47" step="1" />
      </div>
      <div class="ctrl">
        <div class="ctrl-top"><span class="ctrl-name">% Valor construcción (amort. 3 %)</span><span class="ctrl-val" id="v_const"></span></div>
        <input type="range" id="pct_construccion" min="30" max="90" step="5" />
      </div>
      <table class="summary-table">
        <tr><td>Amortización 3 % anual</td><td id="t_amort">-</td></tr>
        <tr><td>Gastos op. deducibles / año</td><td id="t_gop">-</td></tr>
        <tr><td>Rendimiento neto IRPF</td><td id="t_rneto">-</td></tr>
      </table>
    </div>
  </div>

  <div class="note" id="sim_note">
    Simulación orientativa en tiempo real (Año 1, sistema francés). La vacancia reduce los ingresos efectivos percibidos; la amortización del 3 % se aplica sobre el % de construcción de la inversión total (excluyendo suelo). Para persona jurídica (SL) o no residentes (IRNR), consulta al asesor en el chat.
  </div>
</div>

<script>
  const INITIAL = {cfg_json};
  const IDS = [
    "precio_compra","itp_pct","reforma","gastos_compra",
    "ltv_pct","interes_pct","plazo_anos",
    "renta_mensual","ibi_anual","comunidad_mensual","seguro_hogar",
    "seguro_impago_pct","mantenimiento_pct","vacancia_pct",
    "reduccion_irpf_pct","tipo_marginal_irpf_pct","pct_construccion"
  ];
  const fmtEur = (v) => new Intl.NumberFormat("es-ES", {{ maximumFractionDigits: 0 }}).format(Math.round(v)) + " €";
  const fmtPct = (v) => v.toFixed(2).replace(".", ",") + " %";

  function loadInitial() {{
    IDS.forEach(id => {{
      const el = document.getElementById(id);
      if (el && INITIAL[id] !== undefined) el.value = INITIAL[id];
    }});
    document.getElementById("sel_ccaa").value = "";
    recalc();
  }}

  function val(id) {{ return parseFloat(document.getElementById(id).value) || 0; }}

  function recalc() {{
    const precio = val("precio_compra");
    const itpPct = val("itp_pct");
    const reforma = val("reforma");
    const gCompra = val("gastos_compra");
    const ltv = val("ltv_pct");
    const tin = val("interes_pct");
    const plazo = Math.max(1, Math.round(val("plazo_anos")));
    const renta = val("renta_mensual");
    const ibi = val("ibi_anual");
    const comMes = val("comunidad_mensual");
    const segHogar = val("seguro_hogar");
    const segImpPct = val("seguro_impago_pct");
    const mantPct = val("mantenimiento_pct");
    const vacPct = val("vacancia_pct");
    const redIrpf = val("reduccion_irpf_pct");
    const margIrpf = val("tipo_marginal_irpf_pct");
    const pctConst = val("pct_construccion");

    // Etiquetas sliders
    document.getElementById("v_precio").textContent = fmtEur(precio);
    document.getElementById("v_itp").textContent = itpPct.toFixed(1).replace(".", ",") + " % (" + fmtEur(precio * itpPct / 100) + ")";
    document.getElementById("v_ref").textContent = fmtEur(reforma);
    document.getElementById("v_gcompra").textContent = fmtEur(gCompra);
    document.getElementById("v_ltv").textContent = ltv.toFixed(0) + " %";
    document.getElementById("v_tin").textContent = tin.toFixed(1).replace(".", ",") + " %";
    document.getElementById("v_plazo").textContent = plazo + " años";
    document.getElementById("v_renta").textContent = fmtEur(renta) + "/mes";
    document.getElementById("v_ibicom").textContent = fmtEur(ibi) + "/año · " + fmtEur(comMes) + "/mes";
    document.getElementById("v_segh").textContent = fmtEur(segHogar) + "/año";
    document.getElementById("v_segi").textContent = segImpPct.toFixed(1).replace(".", ",") + " %";
    document.getElementById("v_mantvac").textContent = mantPct.toFixed(1).replace(".", ",") + " % · " + vacPct.toFixed(1).replace(".", ",") + " %";
    document.getElementById("v_marg").textContent = margIrpf.toFixed(0) + " %";
    document.getElementById("v_const").textContent = pctConst.toFixed(0) + " %";

    // Compra y financiación
    const itpEur = precio * (itpPct / 100);
    const invTotal = precio + itpEur + gCompra + reforma;
    const hipoteca = precio * (ltv / 100);
    const capPropio = Math.max(1, invTotal - hipoteca);

    let cuotaMes = 0, intAno1 = 0, prinAno1 = 0;
    if (hipoteca > 0) {{
      const r = (tin / 100) / 12;
      const n = plazo * 12;
      cuotaMes = r > 0 ? hipoteca * (r * Math.pow(1 + r, n)) / (Math.pow(1 + r, n) - 1) : hipoteca / n;
      let saldo = hipoteca;
      for (let m = 0; m < 12; m++) {{
        const iM = saldo * r;
        const pM = Math.min(saldo, cuotaMes - iM);
        intAno1 += iM;
        prinAno1 += pM;
        saldo = Math.max(0, saldo - pM);
      }}
    }}
    const cuotaAno = cuotaMes * 12;

    // Ingresos y gastos operativos
    const ingBrutos = renta * 12;
    const vacEur = ingBrutos * (vacPct / 100);
    const ingEfectivos = ingBrutos - vacEur;
    const comAno = comMes * 12;
    const segImpEur = ingEfectivos * (segImpPct / 100);
    const mantEur = ingEfectivos * (mantPct / 100);
    const gastosOpDed = ibi + comAno + segHogar + segImpEur + mantEur;

    // Rentabilidades y Cash-Flow antes de IRPF
    const rentBruta = (ingBrutos / invTotal) * 100;
    const rentNeta = ((ingEfectivos - gastosOpDed) / invTotal) * 100;
    const cfAnoAntes = ingEfectivos - gastosOpDed - cuotaAno;

    // IRPF exacto (con límite Art. 23.1.a LIRPF para intereses + conservación/mantenimiento)
    const amort3 = invTotal * (pctConst / 100) * 0.03;
    const grupoA = intAno1 + mantEur;
    const grupoADed = Math.min(grupoA, ingEfectivos);
    const grupoBDed = ibi + comAno + segHogar + segImpEur;
    const rNeto = ingEfectivos - grupoADed - grupoBDed - amort3;
    const baseRed = rNeto > 0 ? rNeto * (1 - redIrpf / 100) : 0;
    const irpfAno = baseRed > 0 ? baseRed * (margIrpf / 100) : 0;

    const cfAnoNeto = cfAnoAntes - irpfAno;
    const cfMesNeto = cfAnoNeto / 12;
    const roceNeto = (cfAnoNeto / capPropio) * 100;
    const roceTotal = ((cfAnoNeto + prinAno1) / capPropio) * 100;

    // KPIs
    document.getElementById("k_cap").textContent = fmtEur(capPropio);
    document.getElementById("k_inv").textContent = "Inversión total: " + fmtEur(invTotal);
    document.getElementById("k_rent").textContent = rentBruta.toFixed(1).replace(".", ",") + " % / " + rentNeta.toFixed(1).replace(".", ",") + " %";
    document.getElementById("k_cuota").textContent = "Cuota hipoteca: " + fmtEur(cuotaMes) + "/mes";
    document.getElementById("k_cfm").textContent = (cfMesNeto >= 0 ? "+" : "") + fmtEur(cfMesNeto) + "/mes";
    document.getElementById("k_cfa").textContent = "Anual tras IRPF: " + (cfAnoNeto >= 0 ? "+" : "") + fmtEur(cfAnoNeto);
    document.getElementById("k_roce").textContent = fmtPct(roceNeto);
    document.getElementById("k_roce_tot").textContent = "Con amort. capital: " + fmtPct(roceTotal);
    document.getElementById("k_irpf").textContent = fmtEur(irpfAno);
    document.getElementById("k_base").textContent = "Base reducida: " + fmtEur(baseRed);

    const boxCf = document.getElementById("box_cf");
    boxCf.className = "kpi " + (cfMesNeto >= 150 ? "good" : (cfMesNeto >= 0 ? "warn" : "bad"));
    const boxRoce = document.getElementById("box_roce");
    boxRoce.className = "kpi " + (roceNeto >= 6 ? "good" : (roceNeto >= 2 ? "warn" : "bad"));

    // Tablas auxiliares
    document.getElementById("t_hip").textContent = fmtEur(hipoteca);
    document.getElementById("t_int1").textContent = fmtEur(intAno1);
    document.getElementById("t_prin1").textContent = fmtEur(prinAno1);
    document.getElementById("t_amort").textContent = fmtEur(amort3);
    document.getElementById("t_gop").textContent = fmtEur(gastosOpDed);
    document.getElementById("t_rneto").textContent = fmtEur(rNeto);

    // Barra de distribución mensual
    const hipMes = cuotaMes;
    const gasMes = (gastosOpDed + vacEur) / 12;
    const irpfMes = irpfAno / 12;
    const cfPosMes = Math.max(0, cfMesNeto);
    const denom = Math.max(1, hipMes + gasMes + irpfMes + cfPosMes);
    document.getElementById("seg_hip").style.width = ((hipMes / denom) * 100).toFixed(1) + "%";
    document.getElementById("seg_gas").style.width = ((gasMes / denom) * 100).toFixed(1) + "%";
    document.getElementById("seg_irpf").style.width = ((irpfMes / denom) * 100).toFixed(1) + "%";
    document.getElementById("seg_cf").style.width = ((cfPosMes / denom) * 100).toFixed(1) + "%";
    document.getElementById("bar_renta_lbl").textContent = "Renta bruta: " + fmtEur(renta) + "/mes";
    document.getElementById("l_hip").textContent = fmtEur(hipMes);
    document.getElementById("l_gas").textContent = fmtEur(gasMes);
    document.getElementById("l_irpf").textContent = fmtEur(irpfMes);
    document.getElementById("l_cf").textContent = (cfMesNeto >= 0 ? "+" : "") + fmtEur(cfMesNeto);
  }}

  IDS.forEach(id => {{
    const el = document.getElementById(id);
    if (el) el.addEventListener("input", recalc);
    if (el) el.addEventListener("change", recalc);
  }});
  document.getElementById("sel_ccaa").addEventListener("change", (e) => {{
    if (e.target.value) {{
      document.getElementById("itp_pct").value = e.target.value;
      recalc();
    }}
  }});
  document.getElementById("btnReset").addEventListener("click", loadInitial);
  loadInitial();
</script>
</body>
</html>"""

    components.html(widget_html, height=height, scrolling=True)


def hybrid_chat_input(placeholder="¿En qué puedo ayudarte hoy?"):
    """
    Componente modular que combina la entrada de teclado tradicional (st.chat_input)
    con la entrada por voz usando la API web del navegador.
    Retorna el string de texto ingresado por cualquiera de los medios.
    """
    # 1. Entrada de Teclado clásica
    prompt_teclado = st.chat_input(placeholder)
    
    # 2. Entrada por Voz flotante
    prompt_voz = None
    if speech_to_text:
        col_espacio, col_mic = st.columns([5, 1])
        with col_mic:
            prompt_voz = speech_to_text(
                language='es-ES',
                start_prompt="🎙️ Usar Voz",
                stop_prompt="🛑 Detener",
                just_once=True,
                use_container_width=True, # Aprovechamos novedad de v0.0.8
                key='stt_input_2'
            )
    else:
        st.error(f"⚠️ Error cargando la librería de voz: {error_msg}. Detén la app (Ctrl+C) y vuelve a ejecutar 'streamlit run streamlit_app.py'")
            
    return prompt_teclado or prompt_voz