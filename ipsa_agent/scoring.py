"""
IPSA Agent - Motor de Scoring, Filtros y Gestión de Portafolio
"""

import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import (
    MAX_DEBT_EQUITY, MAX_DIVIDEND_YIELD, MAX_PAYOUT_RATIO,
    RSI_OVERBOUGHT, RSI_OVERSOLD,
    WEIGHT_DIVIDEND, WEIGHT_QUALITY, WEIGHT_MOMENTUM, WEIGHT_RISK,
    WEIGHT_HIGH_CONVICTION, WEIGHT_MEDIUM, WEIGHT_LOW,
    SCORE_HIGH_THRESHOLD, SCORE_MEDIUM_THRESHOLD,
    SIGNAL_BUY, SIGNAL_WAIT, SIGNAL_AVOID,
    STOP_LOSS_DEFAULT,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  KILL CONDITIONS (FILTROS)
# ─────────────────────────────────────────────────────────────────

def apply_kill_conditions(analysis: Dict) -> Tuple[bool, List[str]]:
    """
    Retorna (is_excluded, reasons).
    Si is_excluded = True → la acción no entra en el ranking.
    """
    reasons = []

    dy = analysis.get("dividend_yield") or 0
    pr = analysis.get("payout_ratio")   or 0
    de = analysis.get("debt_to_equity") or 0
    m3 = analysis.get("momentum_3m")    or 0
    m6 = analysis.get("momentum_6m")    or 0
    rsi = analysis.get("rsi")           or 50

    # 1. Dividend yield sospechoso
    if dy > MAX_DIVIDEND_YIELD:
        reasons.append(f"DY={dy*100:.1f}% > {MAX_DIVIDEND_YIELD*100:.0f}% (posible trampa)")

    # 2. Payout insostenible
    if pr > MAX_PAYOUT_RATIO:
        reasons.append(f"Payout={pr*100:.0f}% > {MAX_PAYOUT_RATIO*100:.0f}% (insostenible)")

    # 3. Deuda excesiva
    if de > MAX_DEBT_EQUITY:
        reasons.append(f"D/E={de:.2f} > {MAX_DEBT_EQUITY} (apalancamiento alto)")

    # 4. Tendencia bajista prolongada: mom 3M < -20% Y mom 6M < -25%
    if m3 < -20 and m6 < -25:
        reasons.append(f"Momentum bajista severo (3M={m3:.1f}%, 6M={m6:.1f}%)")

    # 5. RSI sobrecomprado extremo
    if rsi > RSI_OVERBOUGHT:
        reasons.append(f"RSI={rsi:.0f} > {RSI_OVERBOUGHT} (sobrecompra)")

    return (len(reasons) > 0, reasons)


# ─────────────────────────────────────────────────────────────────
#  SCORE UNIFICADO
# ─────────────────────────────────────────────────────────────────

def compute_unified_score(analysis: Dict) -> float:
    """
    Score = (DivFactor × 0.40) + (QualFactor × 0.25) + (MomFactor × 0.20) - (RiskPenalty × 0.15)
    Robusto ante None en cualquier factor.
    """
    div_f  = analysis.get("factor_dividend")  or 0.30
    qual_f = analysis.get("factor_quality")   or 0.30
    mom_f  = analysis.get("factor_momentum")  or 0.30
    risk_f = analysis.get("factor_risk")      or 0.30

    # Asegurar floats válidos (None, NaN, Inf → neutro)
    def _safe(v, default=0.30):
        import math
        if v is None: return default
        try:
            f = float(v)
            return default if (math.isnan(f) or math.isinf(f)) else f
        except (TypeError, ValueError):
            return default

    div_f  = _safe(div_f)
    qual_f = _safe(qual_f)
    mom_f  = _safe(mom_f)
    risk_f = _safe(risk_f)

    risk_penalty = 1.0 - risk_f

    score = (
        WEIGHT_DIVIDEND * div_f +
        WEIGHT_QUALITY  * qual_f +
        WEIGHT_MOMENTUM * mom_f -
        WEIGHT_RISK     * risk_penalty
    )

    return round(max(0.0, min(score, 1.0)), 4)


# ─────────────────────────────────────────────────────────────────
#  SEÑAL DE ENTRADA
# ─────────────────────────────────────────────────────────────────

def compute_signal(analysis: Dict, score: float, is_excluded: bool) -> str:
    """Determina la señal de trading."""
    if is_excluded:
        return SIGNAL_AVOID

    rsi   = analysis.get("rsi") or 50
    mom3  = analysis.get("momentum_3m") or 0
    above = analysis.get("above_sma50")

    if score >= SCORE_HIGH_THRESHOLD and rsi < RSI_OVERBOUGHT and above:
        return SIGNAL_BUY
    elif score >= SCORE_MEDIUM_THRESHOLD and rsi < 70:
        return SIGNAL_WAIT
    elif score < 0.30 or rsi > RSI_OVERBOUGHT:
        return SIGNAL_AVOID
    else:
        return SIGNAL_WAIT


# ─────────────────────────────────────────────────────────────────
#  GENERACIÓN DE TESIS
# ─────────────────────────────────────────────────────────────────

def generate_thesis(analysis: Dict, score: float, kill_reasons: List[str]) -> str:
    """Genera una tesis cuantitativa breve (máx 3 líneas)."""
    lines = []

    dy     = (analysis.get("dividend_yield") or 0) * 100
    spread = (analysis.get("spread") or 0) * 100
    roe    = (analysis.get("roe") or 0) * 100
    de     = analysis.get("debt_to_equity") or 0
    mom3   = analysis.get("momentum_3m") or 0
    mom6   = analysis.get("momentum_6m") or 0
    rsi    = analysis.get("rsi") or 50
    dd     = analysis.get("max_drawdown") or 0
    vol    = analysis.get("volatility_annual") or 0

    if kill_reasons:
        lines.append(f"⚠️ EXCLUIDA: {kill_reasons[0]}")
        if len(kill_reasons) > 1:
            lines.append(f"   También: {kill_reasons[1]}")
        return " | ".join(lines)

    # Línea 1: Dividendos
    if dy > 0:
        lines.append(f"DY={dy:.1f}% | Spread vs TPM: {spread:+.1f}% | ROE={roe:.1f}%")

    # Línea 2: Momentum
    mom_str = f"Momentum 3M={mom3:+.1f}%, 6M={mom6:+.1f}%"
    rsi_str = f"RSI={rsi:.0f}"
    de_str  = f"D/E={de:.2f}" if de else "D/E=N/D"
    lines.append(f"{mom_str} | {rsi_str} | {de_str}")

    # Línea 3: Riesgo
    lines.append(f"Drawdown máx 6M: {dd:.1f}% | Vol anual: {vol:.1f}% | Score: {score:.3f}")

    return " · ".join(lines[:3])


# ─────────────────────────────────────────────────────────────────
#  PIPELINE COMPLETO DE RANKING
# ─────────────────────────────────────────────────────────────────

def rank_all_tickers(analyses: Dict[str, Dict], risk_free_rate: float) -> pd.DataFrame:
    """
    Aplica scoring y kill conditions a todos los tickers.
    Retorna DataFrame ordenado por Score.
    """
    rows = []

    for ticker, analysis in analyses.items():
        is_excluded, kill_reasons = apply_kill_conditions(analysis)
        score  = compute_unified_score(analysis) if not is_excluded else 0.0
        signal = compute_signal(analysis, score, is_excluded)
        thesis = generate_thesis(analysis, score, kill_reasons)

        rows.append({
            "ticker":             ticker,
            "name":               analysis.get("name", ticker),
            "score":              score,
            "signal":             signal,
            "is_excluded":        is_excluded,
            "kill_reasons":       kill_reasons,
            "thesis":             thesis,
            "current_price":      analysis.get("current_price"),
            "dividend_yield":     analysis.get("dividend_yield"),
            "spread":             analysis.get("spread"),
            "roe":                analysis.get("roe"),
            "debt_to_equity":     analysis.get("debt_to_equity"),
            "payout_ratio":       analysis.get("payout_ratio"),
            "momentum_3m":        analysis.get("momentum_3m"),
            "momentum_6m":        analysis.get("momentum_6m"),
            "rsi":                analysis.get("rsi"),
            "max_drawdown":       analysis.get("max_drawdown"),
            "volatility_annual":  analysis.get("volatility_annual"),
            "sharpe_ratio":       analysis.get("sharpe_ratio"),
            "above_sma50":        analysis.get("above_sma50"),
            "above_sma200":       analysis.get("above_sma200"),
            "factor_dividend":    analysis.get("factor_dividend"),
            "factor_quality":     analysis.get("factor_quality"),
            "factor_momentum":    analysis.get("factor_momentum"),
            "factor_risk":        analysis.get("factor_risk"),
            "entry_low":          analysis.get("entry_low"),
            "entry_high":         analysis.get("entry_high"),
            "stop_loss":          analysis.get("stop_loss"),
            "resistance":         analysis.get("resistance"),
            "market_cap":         analysis.get("market_cap"),
            "pe_ratio":           analysis.get("pe_ratio"),
            "pb_ratio":           analysis.get("pb_ratio"),
            "bb_position":        analysis.get("bb_position"),
            "macd_histogram":     analysis.get("macd_histogram"),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    return df


def select_top5(ranked_df: pd.DataFrame) -> pd.DataFrame:
    """Selecciona el Top 5 excluyendo activos con kill conditions."""
    eligible = ranked_df[~ranked_df["is_excluded"]].head(5)
    return eligible.reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────
#  GESTIÓN DE PORTAFOLIO (KELLY SIMPLIFICADO)
# ─────────────────────────────────────────────────────────────────

def assign_portfolio_weights(top5: pd.DataFrame) -> pd.DataFrame:
    """
    Asigna pesos usando Kelly simplificado basado en score.
    Total = 100% (posición de caja/cash implícita si hay menos de 5 acciones).
    """
    if top5.empty:
        return top5

    df = top5.copy()

    def get_weight_bucket(score: float) -> float:
        if score >= SCORE_HIGH_THRESHOLD:
            return WEIGHT_HIGH_CONVICTION
        elif score >= SCORE_MEDIUM_THRESHOLD:
            return WEIGHT_MEDIUM
        else:
            return WEIGHT_LOW

    raw_weights = df["score"].apply(get_weight_bucket)

    # Normalizar a 100%
    total = raw_weights.sum()
    df["weight_pct"] = (raw_weights / total * 100).round(1)

    # Horizonte sugerido
    def suggest_horizon(row):
        mom3 = row.get("momentum_3m") or 0
        dy   = (row.get("dividend_yield") or 0) * 100
        if dy > 4 and mom3 > 5:
            return "Medio plazo (3-6M)"
        elif mom3 > 10:
            return "Corto plazo (1-3M)"
        else:
            return "Medio plazo (3-6M)"

    df["horizon"] = df.apply(suggest_horizon, axis=1)

    return df


# ─────────────────────────────────────────────────────────────────
#  DETECCIÓN DE CAMBIOS SIGNIFICATIVOS
# ─────────────────────────────────────────────────────────────────

def detect_significant_changes(
    current_top5: pd.DataFrame,
    previous_top5_tickers: List[str],
    score_change_threshold: float = 0.05,
) -> Dict:
    """
    Detecta si el Top 5 cambió significativamente respecto a la sesión anterior.
    """
    if not previous_top5_tickers:
        return {"changed": False, "new_entries": [], "exits": [], "alert": None}

    current_tickers = set(current_top5["ticker"].tolist())
    previous_tickers = set(previous_top5_tickers)

    new_entries = list(current_tickers - previous_tickers)
    exits       = list(previous_tickers - current_tickers)

    changed = len(new_entries) > 0 or len(exits) > 0
    alert   = None

    if changed:
        alert = (
            f"🚨 ALERTA: Top 5 cambió. "
            f"Nuevas entradas: {new_entries}. "
            f"Salidas: {exits}."
        )

    return {
        "changed":     changed,
        "new_entries": new_entries,
        "exits":       exits,
        "alert":       alert,
    }
