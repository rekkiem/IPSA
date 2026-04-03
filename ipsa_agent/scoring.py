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
    Kill conditions: SOLO para situaciones individualmente peligrosas.
    
    FILOSOFÍA: El score ya penaliza momentum, payout, deuda, etc.
    Las kill conditions captan SOLO lo que el score NO puede cuantificar:
    - Trampas de dividendo evidentes (yield > 25%: precio cayó en picada)
    - Quiebra inminente (D/E > 4x no-banco)
    - Sobrecompra extrema que haría la entrada ridícula
    
    NO incluir condiciones de mercado sistémicas (momentum negativo de mercado
    completo por macro shock) → el score los penaliza y quedan al fondo del ranking.
    """
    reasons = []

    dy  = analysis.get("dividend_yield") or 0
    de  = analysis.get("debt_to_equity") or 0
    rsi = analysis.get("rsi")            or 50
    is_bank = analysis.get("is_financial_sector", False)

    # 1. Trampa de dividendo: precio desplomado → yield artificialmente alto
    if dy > MAX_DIVIDEND_YIELD:
        reasons.append(f"DY={dy*100:.1f}% > {MAX_DIVIDEND_YIELD*100:.0f}% (trampa evidente)")

    # 2. Apalancamiento extremo para no-bancos (riesgo de quiebra)
    #    Bancos exentos: D/E 8-12x = normal bajo Basilea III
    if not is_bank and de > MAX_DEBT_EQUITY:
        reasons.append(f"D/E={de:.1f}x > {MAX_DEBT_EQUITY}x (riesgo quiebra - no banco)")

    # 3. Sobrecompra extrema (RSI > 88 prácticamente nunca ocurre normalmente)
    if rsi > RSI_OVERBOUGHT:
        reasons.append(f"RSI={rsi:.0f} > {RSI_OVERBOUGHT} (sobrecompra extrema)")

    # NOTA IMPORTANTE: NO incluimos momentum bajista ni payout ratio elevado como kill conditions.
    # Razón: en un crash de mercado (ej: aranceles Trump 2/4/2026) TODOS los tickers
    # tienen momentum negativo → kill condition sistémica vacía el Top 5 completamente.
    # El factor_momentum y factor_quality ya penalizan estos aspectos en el score.

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
    Retorna DataFrame ordenado por Score con logging diagnóstico.
    """
    rows = []
    excluded_log = []

    for ticker, analysis in analyses.items():
        is_excluded, kill_reasons = apply_kill_conditions(analysis)
        score  = compute_unified_score(analysis) if not is_excluded else 0.0
        signal = compute_signal(analysis, score, is_excluded)
        thesis = generate_thesis(analysis, score, kill_reasons)

        if is_excluded:
            excluded_log.append(f"  EXCLUIDO {ticker}: {kill_reasons[0][:60]}")

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
            "is_financial_sector": analysis.get("is_financial_sector", False),
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1

    # Diagnóstico en log
    n_eligible  = len(df[~df["is_excluded"]])
    n_excluded  = len(df[df["is_excluded"]])
    logger.info(f"[SCORING] Elegibles: {n_eligible}/{len(df)} | Excluidos: {n_excluded}")
    if excluded_log:
        for line in excluded_log:
            logger.info(f"[SCORING]{line}")
    if n_eligible == 0:
        logger.warning(
            "[SCORING] ADVERTENCIA: 0 acciones elegibles. "
            "Se usara fallback con Top5 sin filtro (señal CAUTELA)."
        )

    return df


def select_top5(ranked_df: pd.DataFrame) -> pd.DataFrame:
    """
    Selecciona el Top 5.
    Si hay suficientes acciones elegibles: selecciona las mejores 5.
    Si hay menos de 5 elegibles: rellena con las mejores no-excluidas del ranking
    con señal CAUTELA para advertir al usuario.
    """
    if ranked_df.empty:
        return ranked_df

    eligible = ranked_df[~ranked_df["is_excluded"]]

    if len(eligible) >= 5:
        return eligible.head(5).reset_index(drop=True)

    # Fallback: tomar lo mejor disponible, incluyendo parcialmente excluidos si es necesario
    if len(eligible) > 0:
        # Tenemos algunos elegibles pero menos de 5
        # Completar con los mejor-rankeados de los excluidos (con señal de cautela)
        excluded_sorted = ranked_df[ranked_df["is_excluded"]].copy()
        # Re-calcular score para excluidos (darles score real aunque estén "excluidos")
        excluded_sorted = excluded_sorted.sort_values("score", ascending=False)
        needed = 5 - len(eligible)
        fill   = excluded_sorted.head(needed).copy()
        fill["signal"]      = "🟠 CAUTELA"
        fill["is_excluded"] = False  # para que aparezcan en el Top5
        result = pd.concat([eligible, fill]).reset_index(drop=True)
    else:
        # 0 elegibles: todo el universo en modo cautela (condición de mercado extrema)
        result = ranked_df.head(5).copy()
        result["signal"]      = "🟠 CAUTELA"
        result["is_excluded"] = False
        logger.warning(
            "[SCORING] Modo CAUTELA activo: 0 acciones pasaron los filtros. "
            "Top 5 seleccionado por score puro sin kill conditions."
        )

    return result.reset_index(drop=True)


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
