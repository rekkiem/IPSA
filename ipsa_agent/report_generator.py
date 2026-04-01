"""
IPSA Agent - Generador de Reportes Diarios
Produce output en HTML (visual) y JSON (máquina).
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from config import REPORTS_DIR, SIGNAL_BUY, SIGNAL_WAIT, SIGNAL_AVOID

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  REPORTE CONSOLA
# ─────────────────────────────────────────────────────────────────

def print_daily_report(
    top5:         pd.DataFrame,
    ranked_all:   pd.DataFrame,
    macro:        Dict,
    regime:       Dict,
    changes:      Dict,
    date_str:     str,
):
    """Imprime el reporte diario formateado en consola."""
    sep = "─" * 80

    print(f"\n{'='*80}")
    print(f"  🇨🇱  IPSA AGENT | REPORTE DIARIO | {date_str}")
    print(f"{'='*80}")

    # Macro context
    usdclp = macro.get("usdclp")
    rfr    = macro.get("risk_free_rate", 0)
    infl   = macro.get("inflation", 0)
    regime_name = regime.get("regime", "N/D")
    regime_mom  = regime.get("ipsa_momentum_3m")

    print(f"\n📊 CONTEXTO MACROECONÓMICO")
    print(sep)
    print(f"  USD/CLP:             {usdclp:.2f}" if usdclp else "  USD/CLP:             N/D")
    print(f"  Tasa libre de riesgo: {rfr*100:.2f}%")
    print(f"  IPC anual:           {infl*100:.2f}%")
    print(f"  Régimen IPSA:        {regime_name} (Momentum 3M: {regime_mom:+.1f}%)" if regime_mom is not None else f"  Régimen IPSA:        {regime_name}")

    # Alerta de cambios
    if changes.get("alert"):
        print(f"\n{changes['alert']}")

    print(f"\n🔥 TOP 5 ACCIONES IPSA HOY")
    print(sep)

    if top5.empty:
        print("  ⚠️ No hay suficientes acciones elegibles hoy.")
        return

    # Tabla header
    header = (
        f"  {'Rank':<4} {'Ticker':<16} {'Score':<7} {'DY%':<7} "
        f"{'Spread':<8} {'RSI':<6} {'DD%':<8} {'Vol%':<8} {'Señal'}"
    )
    print(header)
    print(f"  {'-'*80}")

    for i, row in top5.iterrows():
        dy_pct     = f"{row['dividend_yield']*100:.1f}%" if row.get("dividend_yield") else "N/D"
        spread_pct = f"{row['spread']*100:+.1f}%" if row.get("spread") is not None else "N/D"
        rsi_str    = f"{row['rsi']:.0f}" if row.get("rsi") is not None else "N/D"
        dd_str     = f"{row['max_drawdown']:.1f}%" if row.get("max_drawdown") is not None else "N/D"
        vol_str    = f"{row['volatility_annual']:.1f}%" if row.get("volatility_annual") is not None else "N/D"

        signal_icon = "🟢" if SIGNAL_BUY in row["signal"] else ("🟡" if SIGNAL_WAIT in row["signal"] else "🔴")

        print(
            f"  {i+1:<4} {row['ticker']:<16} {row['score']:<7.4f} {dy_pct:<7} "
            f"{spread_pct:<8} {rsi_str:<6} {dd_str:<8} {vol_str:<8} "
            f"{signal_icon} {row['signal']}"
        )

    print(f"\n🧠 TESIS DE CADA ACTIVO")
    print(sep)
    for i, row in top5.iterrows():
        name   = row.get("name", row["ticker"])
        price  = row.get("current_price", 0)
        weight = row.get("weight_pct", 0)
        print(f"\n  [{i+1}] {name} ({row['ticker']}) — CLP ${price:,.0f}")
        print(f"      {row['thesis']}")

    print(f"\n⚖️  ASIGNACIÓN DE PORTAFOLIO")
    print(sep)
    for i, row in top5.iterrows():
        bar = "█" * int(row.get("weight_pct", 0) / 2)
        print(f"  {row['ticker']:<16} {row.get('weight_pct', 0):>5.1f}%  {bar}")
    total_alloc = top5["weight_pct"].sum()
    cash_pct    = max(0, 100 - total_alloc)
    print(f"  {'CAJA/CASH':<16} {cash_pct:>5.1f}%")

    print(f"\n🎯 TIMING DE ENTRADA")
    print(sep)
    for i, row in top5.iterrows():
        print(
            f"  {row['ticker']:<16} "
            f"Actual: {row.get('current_price', 0):>8,.0f} CLP | "
            f"Entrada: {row.get('entry_low', 0):>8,.0f}–{row.get('entry_high', 0):>8,.0f} | "
            f"StopLoss: {row.get('stop_loss', 0):>8,.0f} | "
            f"Horizonte: {row.get('horizon', 'N/D')}"
        )

    print(f"\n🚨 RIESGOS DEL DÍA")
    print(sep)
    generate_risk_alerts(top5, macro, regime)

    print(f"\n{'='*80}\n")


def generate_risk_alerts(top5: pd.DataFrame, macro: Dict, regime: Dict):
    """Imprime alertas de riesgo macro y micro."""
    alerts = []

    rfr  = macro.get("risk_free_rate", 0)
    infl = macro.get("inflation", 0)

    if rfr > 0.06:
        alerts.append("⚠️  MACRO: Tasa libre de riesgo alta — presión sobre valuaciones")
    if infl > 0.05:
        alerts.append("⚠️  MACRO: IPC elevado — riesgo de ajuste monetario adicional")

    regime_name = regime.get("regime", "NEUTRAL")
    if regime_name == "BEAR":
        alerts.append("🐻 MACRO: Mercado en régimen BEAR — mantener stop loss estrictos")
    if regime_name == "BULL":
        alerts.append("🐂 MACRO: Mercado BULL — vigilar sobrecompra en índice")

    # Micro
    if not top5.empty:
        for _, row in top5.iterrows():
            rsi = row.get("rsi") or 50
            dd  = abs(row.get("max_drawdown") or 0)
            if rsi > 65:
                alerts.append(f"📌 MICRO [{row['ticker']}]: RSI={rsi:.0f} — entrada tardía, esperar corrección")
            if dd > 20:
                alerts.append(f"📌 MICRO [{row['ticker']}]: Drawdown {dd:.0f}% — alta volatilidad reciente")

    if not alerts:
        alerts.append("✅ Sin alertas significativas para hoy")

    for a in alerts:
        print(f"  {a}")


# ─────────────────────────────────────────────────────────────────
#  REPORTE HTML (VISUAL)
# ─────────────────────────────────────────────────────────────────

def generate_html_report(
    top5:       pd.DataFrame,
    ranked_all: pd.DataFrame,
    macro:      Dict,
    regime:     Dict,
    changes:    Dict,
    date_str:   str,
) -> str:
    """Genera reporte HTML completo con diseño dark/cyan."""

    def fmt_pct(v, decimals=1):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/D"
        return f"{float(v)*100:.{decimals}f}%"

    def fmt_num(v, decimals=1):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/D"
        return f"{float(v):.{decimals}f}"

    def fmt_clp(v):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return "N/D"
        return f"CLP ${float(v):,.0f}"

    def signal_badge(sig):
        if SIGNAL_BUY in sig:
            return f'<span class="badge buy">{sig}</span>'
        elif SIGNAL_WAIT in sig:
            return f'<span class="badge wait">{sig}</span>'
        else:
            return f'<span class="badge avoid">{sig}</span>'

    def regime_class(r):
        return {"BULL": "bull", "BEAR": "bear", "NEUTRAL": "neutral"}.get(r, "neutral")

    rows_top5 = ""
    for i, row in top5.iterrows():
        dy_pct = fmt_pct(row.get("dividend_yield"))
        spread = f"{(row.get('spread') or 0)*100:+.1f}%" if row.get("spread") is not None else "N/D"
        rows_top5 += f"""
        <tr>
            <td class="rank">{i+1}</td>
            <td><strong>{row.get('ticker','')}</strong><br><small>{row.get('name','')}</small></td>
            <td class="score">{row.get('score', 0):.4f}</td>
            <td>{dy_pct}</td>
            <td class="{'positive' if (row.get('spread') or 0) > 0 else 'negative'}">{spread}</td>
            <td>{fmt_num(row.get('rsi'))}</td>
            <td class="negative">{fmt_num(row.get('max_drawdown'))}%</td>
            <td>{fmt_num(row.get('volatility_annual'))}%</td>
            <td>{row.get('weight_pct', 0):.1f}%</td>
            <td>{signal_badge(row.get('signal', ''))}</td>
        </tr>"""

    thesis_cards = ""
    for i, row in top5.iterrows():
        entry_zone = f"{fmt_clp(row.get('entry_low'))} – {fmt_clp(row.get('entry_high'))}"
        thesis_cards += f"""
        <div class="card">
            <div class="card-header">
                <span class="card-rank">#{i+1}</span>
                <h3>{row.get('name', row.get('ticker', ''))} 
                    <span class="ticker-label">{row.get('ticker','')}</span>
                </h3>
                {signal_badge(row.get('signal', ''))}
            </div>
            <p class="thesis">{row.get('thesis', '')}</p>
            <div class="metrics-grid">
                <div class="metric"><span>Score</span><strong>{row.get('score', 0):.4f}</strong></div>
                <div class="metric"><span>Precio</span><strong>{fmt_clp(row.get('current_price'))}</strong></div>
                <div class="metric"><span>DY</span><strong>{fmt_pct(row.get('dividend_yield'))}</strong></div>
                <div class="metric"><span>Spread</span><strong>{spread}</strong></div>
                <div class="metric"><span>ROE</span><strong>{fmt_pct(row.get('roe'))}</strong></div>
                <div class="metric"><span>D/E</span><strong>{fmt_num(row.get('debt_to_equity'))}</strong></div>
                <div class="metric"><span>RSI</span><strong>{fmt_num(row.get('rsi'))}</strong></div>
                <div class="metric"><span>Mom 3M</span><strong class="{'positive' if (row.get('momentum_3m') or 0) > 0 else 'negative'}">{fmt_num(row.get('momentum_3m'))}%</strong></div>
                <div class="metric"><span>Mom 6M</span><strong class="{'positive' if (row.get('momentum_6m') or 0) > 0 else 'negative'}">{fmt_num(row.get('momentum_6m'))}%</strong></div>
                <div class="metric"><span>Drawdown</span><strong class="negative">{fmt_num(row.get('max_drawdown'))}%</strong></div>
                <div class="metric"><span>Sharpe</span><strong>{fmt_num(row.get('sharpe_ratio'))}</strong></div>
                <div class="metric"><span>Peso</span><strong>{row.get('weight_pct', 0):.1f}%</strong></div>
            </div>
            <div class="entry-zone">
                <div><span>🎯 Zona entrada:</span> <strong>{entry_zone}</strong></div>
                <div><span>🛑 Stop Loss:</span> <strong class="negative">{fmt_clp(row.get('stop_loss'))}</strong></div>
                <div><span>⏱ Horizonte:</span> <strong>{row.get('horizon', 'N/D')}</strong></div>
            </div>
        </div>"""

    # Tabla completa ranking
    all_rows = ""
    show_cols = ["ticker", "name", "score", "signal", "dividend_yield", "rsi",
                 "momentum_3m", "max_drawdown", "sharpe_ratio"]
    for _, row in ranked_all.iterrows():
        excl_class = "excluded" if row.get("is_excluded") else ""
        all_rows += f"""
        <tr class="{excl_class}">
            <td>{row.get('rank','')}</td>
            <td><strong>{row.get('ticker','')}</strong></td>
            <td>{row.get('name','')}</td>
            <td>{row.get('score', 0):.4f}</td>
            <td>{signal_badge(row.get('signal',''))}</td>
            <td>{fmt_pct(row.get('dividend_yield'))}</td>
            <td>{fmt_num(row.get('rsi'))}</td>
            <td class="{'positive' if (row.get('momentum_3m') or 0) > 0 else 'negative'}">{fmt_num(row.get('momentum_3m'))}%</td>
            <td class="negative">{fmt_num(row.get('max_drawdown'))}%</td>
            <td>{fmt_num(row.get('sharpe_ratio'))}</td>
            <td>{'⚠️ ' + '; '.join(row.get('kill_reasons', [])) if row.get('is_excluded') else '✓'}</td>
        </tr>"""

    usdclp_val = f"{macro.get('usdclp', 0):,.2f}" if macro.get("usdclp") else "N/D"
    regime_name = regime.get("regime", "NEUTRAL")
    regime_mom  = regime.get("ipsa_momentum_3m")
    regime_mom_str = f"{regime_mom:+.1f}%" if regime_mom is not None else "N/D"
    change_alert = f'<div class="alert-box">{changes.get("alert", "")}</div>' if changes.get("alert") else ""

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IPSA Agent — {date_str}</title>
    <style>
        :root {{
            --bg:       #0a0e1a;
            --surface:  #111827;
            --surface2: #1a2235;
            --border:   #1e3a5f;
            --cyan:     #00d4ff;
            --green:    #00ff88;
            --purple:   #a855f7;
            --red:      #ff4d6d;
            --yellow:   #ffd166;
            --text:     #e2e8f0;
            --muted:    #64748b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background: var(--bg); color: var(--text); font-family: 'Inter', 'Segoe UI', sans-serif; padding: 24px; }}
        h1 {{ font-size: 1.8rem; color: var(--cyan); letter-spacing: -0.5px; }}
        h2 {{ font-size: 1.2rem; color: var(--cyan); margin: 32px 0 16px; border-left: 3px solid var(--cyan); padding-left: 12px; }}
        h3 {{ font-size: 1rem; color: var(--text); }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 28px; }}
        .date-badge {{ background: var(--surface2); border: 1px solid var(--border); padding: 6px 14px; border-radius: 20px; font-size: 0.85rem; color: var(--muted); }}
        .macro-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 28px; }}
        .macro-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }}
        .macro-card span {{ font-size: 0.75rem; color: var(--muted); display: block; margin-bottom: 4px; }}
        .macro-card strong {{ font-size: 1.1rem; color: var(--cyan); }}
        .regime-badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; font-weight: 700; font-size: 0.85rem; }}
        .regime-badge.bull {{ background: rgba(0,255,136,0.15); color: var(--green); border: 1px solid var(--green); }}
        .regime-badge.bear {{ background: rgba(255,77,109,0.15); color: var(--red); border: 1px solid var(--red); }}
        .regime-badge.neutral {{ background: rgba(255,209,102,0.15); color: var(--yellow); border: 1px solid var(--yellow); }}
        table {{ width: 100%; border-collapse: collapse; background: var(--surface); border-radius: 10px; overflow: hidden; margin-bottom: 24px; }}
        th {{ background: var(--surface2); color: var(--cyan); text-align: left; padding: 10px 14px; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; }}
        td {{ padding: 10px 14px; font-size: 0.88rem; border-bottom: 1px solid var(--border); }}
        tr:last-child td {{ border-bottom: none; }}
        tr:hover td {{ background: rgba(0,212,255,0.04); }}
        tr.excluded td {{ opacity: 0.45; }}
        .rank {{ color: var(--muted); font-weight: 700; }}
        .score {{ color: var(--cyan); font-weight: 700; }}
        .positive {{ color: var(--green); }}
        .negative {{ color: var(--red); }}
        .badge {{ padding: 3px 10px; border-radius: 10px; font-size: 0.78rem; font-weight: 600; }}
        .badge.buy   {{ background: rgba(0,255,136,0.15); color: var(--green); border: 1px solid var(--green); }}
        .badge.wait  {{ background: rgba(255,209,102,0.15); color: var(--yellow); border: 1px solid var(--yellow); }}
        .badge.avoid {{ background: rgba(255,77,109,0.15); color: var(--red); border: 1px solid var(--red); }}
        .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
        .card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }}
        .card-rank {{ background: var(--border); color: var(--cyan); width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.85rem; flex-shrink: 0; }}
        .ticker-label {{ color: var(--muted); font-size: 0.8rem; font-weight: 400; margin-left: 8px; }}
        .thesis {{ color: var(--muted); font-size: 0.85rem; line-height: 1.6; margin-bottom: 16px; padding: 10px; background: var(--surface2); border-radius: 6px; border-left: 3px solid var(--border); }}
        .metrics-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; margin-bottom: 16px; }}
        .metric {{ background: var(--surface2); border-radius: 6px; padding: 8px 10px; }}
        .metric span {{ display: block; font-size: 0.7rem; color: var(--muted); margin-bottom: 2px; }}
        .metric strong {{ font-size: 0.95rem; }}
        .entry-zone {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; background: var(--surface2); border-radius: 8px; padding: 12px; font-size: 0.85rem; }}
        .entry-zone span {{ color: var(--muted); }}
        .alert-box {{ background: rgba(255,209,102,0.1); border: 1px solid var(--yellow); color: var(--yellow); padding: 12px 16px; border-radius: 8px; margin-bottom: 20px; font-size: 0.9rem; }}
        .footer {{ text-align: center; color: var(--muted); font-size: 0.78rem; margin-top: 40px; padding-top: 20px; border-top: 1px solid var(--border); }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🇨🇱 IPSA Agent</h1>
        <span class="date-badge">📅 {date_str}</span>
    </div>

    {change_alert}

    <div class="macro-grid">
        <div class="macro-card"><span>USD/CLP</span><strong>{usdclp_val}</strong></div>
        <div class="macro-card"><span>Tasa Libre de Riesgo</span><strong>{macro.get('risk_free_rate', 0)*100:.2f}%</strong></div>
        <div class="macro-card"><span>IPC Anual</span><strong>{macro.get('inflation', 0)*100:.2f}%</strong></div>
        <div class="macro-card"><span>Régimen IPSA</span><strong><span class="regime-badge {regime_class(regime_name)}">{regime_name}</span></strong></div>
        <div class="macro-card"><span>IPSA Momentum 3M</span><strong class="{'positive' if (regime_mom or 0) > 0 else 'negative'}">{regime_mom_str}</strong></div>
    </div>

    <h2>🔥 Top 5 IPSA — {date_str}</h2>
    <table>
        <thead>
            <tr>
                <th>#</th><th>Acción</th><th>Score</th>
                <th>Div Yield</th><th>Spread vs TPM</th>
                <th>RSI</th><th>Drawdown</th><th>Vol Anual</th>
                <th>Peso %</th><th>Señal</th>
            </tr>
        </thead>
        <tbody>{rows_top5}</tbody>
    </table>

    <h2>🧠 Tesis por Activo</h2>
    {thesis_cards}

    <h2>📊 Ranking Completo IPSA</h2>
    <table>
        <thead>
            <tr>
                <th>Rank</th><th>Ticker</th><th>Nombre</th><th>Score</th>
                <th>Señal</th><th>DY</th><th>RSI</th>
                <th>Mom 3M</th><th>Drawdown</th><th>Sharpe</th><th>Estado</th>
            </tr>
        </thead>
        <tbody>{all_rows}</tbody>
    </table>

    <div class="footer">
        IPSA Agent v1.0 — Generado {date_str} — Solo para fines informativos. No constituye asesoramiento financiero.
    </div>
</body>
</html>"""

    return html


def save_html_report(html: str, date_str: str) -> str:
    """Guarda el reporte HTML en disco."""
    os.makedirs(REPORTS_DIR, exist_ok=True)
    fname = os.path.join(REPORTS_DIR, f"ipsa_report_{date_str.replace(' ', '_').replace(':', '-')}.html")
    with open(fname, "w", encoding="utf-8") as f:
        f.write(html)
    logger.info(f"[REPORT] HTML guardado: {fname}")
    return fname


def save_json_report(
    top5:       pd.DataFrame,
    ranked_all: pd.DataFrame,
    macro:      Dict,
    regime:     Dict,
    changes:    Dict,
    date_str:   str,
) -> str:
    """
    Guarda snapshot JSON del día.
    Maneja correctamente NaN/Infinity → null (JSON válido).
    """
    os.makedirs(REPORTS_DIR, exist_ok=True)
    fname = os.path.join(REPORTS_DIR, f"ipsa_data_{date_str.replace(' ', '_').replace(':', '-')}.json")

    def clean_value(v):
        """Convierte NaN/Inf/None a null-safe para JSON."""
        if v is None:
            return None
        if isinstance(v, float):
            import math
            if math.isnan(v) or math.isinf(v):
                return None
            return v
        if isinstance(v, (list, tuple)):
            return [clean_value(x) for x in v]
        if isinstance(v, dict):
            return {k: clean_value(val) for k, val in v.items()}
        # numpy types
        try:
            import numpy as np
            if isinstance(v, np.floating):
                f = float(v)
                return None if (math.isnan(f) or math.isinf(f)) else f
            if isinstance(v, np.integer):
                return int(v)
            if isinstance(v, np.bool_):
                return bool(v)
        except ImportError:
            pass
        return v

    def safe_df(df: pd.DataFrame) -> list:
        """Convierte DataFrame a lista de dicts limpia de NaN."""
        if df is None or df.empty:
            return []
        # Reemplazar NaN por None en el DataFrame
        df_clean = df.copy()
        for col in df_clean.select_dtypes(include=['float64', 'float32']).columns:
            df_clean[col] = df_clean[col].apply(
                lambda x: None if (x is None or (isinstance(x, float) and (x != x or x == float('inf') or x == float('-inf')))) else x
            )
        records = df_clean.to_dict(orient="records")
        return [clean_value(r) for r in records]

    data = {
        "date":       date_str,
        "macro":      clean_value(macro),
        "regime":     clean_value(regime),
        "changes":    clean_value(changes),
        "top5":       safe_df(top5),
        "ranked_all": safe_df(ranked_all),
    }

    # Verificar JSON válido antes de escribir
    try:
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        # Doble check: re-parsear para detectar NaN residuales
        json.loads(json_str)
    except (ValueError, TypeError) as e:
        logger.error(f"[REPORT] JSON inválido detectado: {e}. Aplicando sanitización de emergencia.")
        # Fallback: serializar con default que convierte todo lo no-serializable
        import math
        def emergency_default(obj):
            if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
                return None
            return str(obj)
        json_str = json.dumps(data, ensure_ascii=False, indent=2, default=emergency_default)

    with open(fname, "w", encoding="utf-8") as f:
        f.write(json_str)
    logger.info(f"[REPORT] JSON guardado: {fname} ({len(json_str):,} bytes)")
    return fname
