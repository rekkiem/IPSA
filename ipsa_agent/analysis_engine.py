"""
IPSA Agent - Motor de Análisis Central
Calcula todos los factores cuantitativos por acción.
"""

import logging
import warnings
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  UTILIDADES TÉCNICAS BASE
# ─────────────────────────────────────────────────────────────────

def compute_returns(prices: pd.Series) -> pd.Series:
    """Retornos diarios logarítmicos."""
    return np.log(prices / prices.shift(1)).dropna()


def compute_rsi(prices: pd.Series, window: int = 14) -> float:
    """RSI clásico de Wilder."""
    delta  = prices.diff().dropna()
    gain   = delta.clip(lower=0)
    loss   = (-delta).clip(lower=0)
    avg_g  = gain.rolling(window).mean().iloc[-1]
    avg_l  = loss.rolling(window).mean().iloc[-1]
    if avg_l == 0:
        return 100.0
    rs  = avg_g / avg_l
    return float(100 - (100 / (1 + rs)))


def compute_sma(prices: pd.Series, window: int) -> pd.Series:
    return prices.rolling(window=window).mean()


def compute_ema(prices: pd.Series, span: int) -> pd.Series:
    return prices.ewm(span=span, adjust=False).mean()


def compute_macd(prices: pd.Series) -> Tuple[float, float, float]:
    """Retorna (MACD, signal, histogram)."""
    ema12 = compute_ema(prices, 12)
    ema26 = compute_ema(prices, 26)
    macd  = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist   = macd - signal
    return float(macd.iloc[-1]), float(signal.iloc[-1]), float(hist.iloc[-1])


def compute_bollinger(prices: pd.Series, window: int = 20) -> Tuple[float, float, float]:
    """Retorna (upper, mid, lower)."""
    mid   = prices.rolling(window).mean()
    std   = prices.rolling(window).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    return float(upper.iloc[-1]), float(mid.iloc[-1]), float(lower.iloc[-1])


# ─────────────────────────────────────────────────────────────────
#  FACTOR A: DIVIDEND ARBITRAGE
# ─────────────────────────────────────────────────────────────────

def factor_dividend_arbitrage(
    dividend_yield: Optional[float],
    risk_free_rate: float,
    trailing_yield: Optional[float] = None,
) -> Dict:
    """
    SpreadDividendos = DividendYieldForward - RiskFreeRate
    Score normalizado [0, 1] con cap en 10% spread máximo.
    """
    # Preferir trailing yield si está disponible y forward no lo está
    dy = dividend_yield or trailing_yield or 0.0

    spread = dy - risk_free_rate
    # Normalizar para mercado chileno: spread 0% = 0.3 (base), +5% = 1.0
    # Una acción que paga igual que la TPM ya tiene valor neutral
    base_score = 0.30 if dy > 0 else 0.10
    if spread >= 0:
        score_raw = base_score + (1.0 - base_score) * min(spread / 0.05, 1.0)
    else:
        score_raw = max(0.05, base_score + spread / 0.05 * base_score)

    return {
        "dividend_yield":   dy,
        "risk_free_rate":   risk_free_rate,
        "spread":           spread,
        "factor_dividend":  score_raw,
        "signal_div":       "positivo" if spread > 0 else "negativo",
    }


# ─────────────────────────────────────────────────────────────────
#  FACTOR B: CALIDAD
# ─────────────────────────────────────────────────────────────────

def factor_quality(
    roe:             Optional[float],
    debt_to_equity:  Optional[float],
    earnings_growth: Optional[float],
    payout_ratio:    Optional[float],
    current_ratio:   Optional[float],
    is_bank:         bool = False,
) -> Dict:
    """
    Score de calidad compuesto por:
      - ROE normalizado (>20% = excelente)
      - Estabilidad utilidades (earnings_growth >= 0)
      - Solvencia: D/E < 1 ideal para no-bancos; bancos usan CET1/Tier1 regulatorio
      - Payout controlado (<70%)
    """
    scores = []

    # ROE: escala 0-25%+ → 0-1
    if roe is not None:
        roe_score = min(max(roe, 0) / 0.25, 1.0)
        scores.append(("roe", roe_score, 0.35))
    else:
        scores.append(("roe", 0.3, 0.35))

    # Deuda/Equity: sector-aware
    if debt_to_equity is not None:
        if is_bank:
            # Bancos: D/E 8-12x es normal bajo Basilea III → score neutro-positivo
            # Penalizamos solo si es EXTREMADAMENTE alto (>15x) o muy bajo (<3x, subgearing)
            de = float(debt_to_equity)
            if de < 3:
                de_score = 0.55   # sub-leveraged bank (inusual)
            elif de <= 12:
                de_score = 0.70   # rango saludable regulatorio
            else:
                de_score = max(0.0, 0.70 - (de - 12) * 0.05)
        else:
            # No-banco: D/E 0 → 1.0; D/E >= 2.5 → 0
            de_norm  = debt_to_equity if debt_to_equity < 50 else debt_to_equity / 100
            de_score = max(0.0, 1.0 - (de_norm / 2.5))
        scores.append(("debt_equity", de_score, 0.30))
    else:
        scores.append(("debt_equity", 0.4 if not is_bank else 0.60, 0.30))

    # Crecimiento utilidades: [-50%, +50%] → [0, 1]
    if earnings_growth is not None:
        eg_score = min(max((earnings_growth + 0.5) / 1.0, 0.0), 1.0)
        scores.append(("earnings_growth", eg_score, 0.20))
    else:
        scores.append(("earnings_growth", 0.3, 0.20))

    # Payout ratio: < 50% ideal, > 90% penalizado
    if payout_ratio is not None:
        pr_score = max(0.0, 1.0 - max(payout_ratio - 0.5, 0) / 0.5)
        scores.append(("payout_ratio", pr_score, 0.15))
    else:
        scores.append(("payout_ratio", 0.4, 0.15))

    total_w       = sum(w for _, _, w in scores)
    quality_score = sum(s * w for _, s, w in scores) / total_w

    return {
        "roe":             roe,
        "debt_to_equity":  debt_to_equity,
        "earnings_growth": earnings_growth,
        "payout_ratio":    payout_ratio,
        "factor_quality":  quality_score,
        "quality_detail":  {k: round(v, 3) for k, v, _ in scores},
    }


# ─────────────────────────────────────────────────────────────────
#  FACTOR C: MOMENTUM TÉCNICO
# ─────────────────────────────────────────────────────────────────

def factor_momentum(df: pd.DataFrame) -> Dict:
    """
    Calcula:
      - Momentum 3M y 6M (retorno de precio)
      - RSI (14 días)
      - Posición respecto a SMA50/SMA200
      - MACD
      - Score técnico compuesto [0, 1]
    """
    if df is None or len(df) < 50:
        return {
            "momentum_3m":     None,
            "momentum_6m":     None,
            "rsi":             None,
            "above_sma50":     None,
            "above_sma200":    None,
            "macd_signal":     None,
            "factor_momentum": 0.3,  # neutral
        }

    prices = df["Close"]
    n      = len(prices)

    # Momentum 3M
    mom_3m = None
    if n >= 63:
        mom_3m = float((prices.iloc[-1] / prices.iloc[-63]) - 1)

    # Momentum 6M
    mom_6m = None
    if n >= 126:
        mom_6m = float((prices.iloc[-1] / prices.iloc[-126]) - 1)

    # RSI
    rsi_val = compute_rsi(prices)

    # SMA
    sma50  = compute_sma(prices, 50)
    sma200 = compute_sma(prices, 200)
    above_50  = bool(prices.iloc[-1] > sma50.iloc[-1]) if not sma50.isna().iloc[-1] else None
    above_200 = bool(prices.iloc[-1] > sma200.iloc[-1]) if not sma200.isna().iloc[-1] else None

    # MACD
    macd_val, macd_sig, macd_hist = compute_macd(prices)

    # Bollinger
    bb_up, bb_mid, bb_low = compute_bollinger(prices)
    bb_position = (prices.iloc[-1] - bb_low) / max(bb_up - bb_low, 1)  # 0-1

    # ── Score compuesto ──
    sub_scores = []

    # Momentum 3M: [-30% , +30%] → [0, 1]
    if mom_3m is not None:
        sub_scores.append(min(max((mom_3m + 0.30) / 0.60, 0.0), 1.0) * 0.30)
    else:
        sub_scores.append(0.3 * 0.30)

    # Momentum 6M
    if mom_6m is not None:
        sub_scores.append(min(max((mom_6m + 0.40) / 0.80, 0.0), 1.0) * 0.25)
    else:
        sub_scores.append(0.3 * 0.25)

    # RSI: zona óptima 40-60 = 1, sobrecompra/sobreventa penalizadas
    rsi_score = 1.0 - abs(rsi_val - 50) / 50
    sub_scores.append(max(rsi_score, 0) * 0.20)

    # SMA50 above
    sub_scores.append((0.8 if above_50 else 0.2) * 0.15)

    # MACD positivo
    macd_score = 0.7 if macd_hist > 0 else 0.3
    sub_scores.append(macd_score * 0.10)

    momentum_score = sum(sub_scores)

    return {
        "momentum_3m":     round(mom_3m * 100, 2) if mom_3m is not None else None,
        "momentum_6m":     round(mom_6m * 100, 2) if mom_6m is not None else None,
        "rsi":             round(rsi_val, 1),
        "above_sma50":     above_50,
        "above_sma200":    above_200,
        "macd_histogram":  round(macd_hist, 4),
        "bb_position":     round(bb_position, 3),
        "factor_momentum": round(momentum_score, 4),
    }


# ─────────────────────────────────────────────────────────────────
#  FACTOR D: RIESGO
# ─────────────────────────────────────────────────────────────────

def factor_risk(df: pd.DataFrame) -> Dict:
    """
    Calcula métricas de riesgo:
      - Max Drawdown 6M
      - Volatilidad anualizada
      - VaR 95% diario
      - Score de riesgo [0, 1] (0=máximo riesgo, 1=mínimo riesgo)
    """
    if df is None or len(df) < 30:
        return {
            "max_drawdown":       None,
            "volatility_annual":  None,
            "var_95":             None,
            "sharpe_ratio":       None,
            "factor_risk":        0.3,
        }

    prices  = df["Close"]
    returns = compute_returns(prices)

    # Max Drawdown 6M
    window  = min(126, len(prices))
    p_win   = prices.iloc[-window:]
    peak    = p_win.cummax()
    dd      = (p_win - peak) / peak
    max_dd  = float(dd.min())

    # Volatilidad anualizada
    vol_annual = float(returns.std() * np.sqrt(252))

    # VaR 95% (diario)
    var_95 = float(np.percentile(returns.dropna(), 5))

    # Sharpe simplificado (sin risk_free en este punto)
    mean_r = float(returns.mean() * 252)
    sharpe = mean_r / vol_annual if vol_annual > 0 else 0.0

    # Score de riesgo (penalización → menor es peor)
    # Max DD: 0% = 1.0, -40% = 0.0
    dd_score  = max(0.0, 1.0 + max_dd / 0.40)
    # Vol: 0% = 1.0, 80% = 0.0
    vol_score = max(0.0, 1.0 - vol_annual / 0.80)
    risk_score = 0.60 * dd_score + 0.40 * vol_score

    return {
        "max_drawdown":      round(max_dd * 100, 2),
        "volatility_annual": round(vol_annual * 100, 2),
        "var_95":            round(var_95 * 100, 2),
        "sharpe_ratio":      round(sharpe, 3),
        "factor_risk":       round(risk_score, 4),
    }


# ─────────────────────────────────────────────────────────────────
#  ZONA ÓPTIMA DE ENTRADA
# ─────────────────────────────────────────────────────────────────

def compute_entry_zone(df: pd.DataFrame, current_price: float) -> Dict:
    """
    Calcula soporte/resistencia y zona óptima de entrada
    basada en Bollinger Bands y máx/mín reciente.
    """
    if df is None or len(df) < 20:
        return {
            "entry_low":  current_price * 0.97,
            "entry_high": current_price * 1.00,
            "stop_loss":  current_price * 0.93,
            "resistance": current_price * 1.07,
        }

    prices    = df["Close"]
    bb_up, bb_mid, bb_low = compute_bollinger(prices)
    low_20    = float(prices.tail(20).min())
    high_20   = float(prices.tail(20).max())
    low_5     = float(prices.tail(5).min())

    entry_low  = max(bb_low, low_20 * 0.99)
    entry_high = bb_mid
    stop_loss  = low_20 * 0.93   # -7% bajo mínimo 20 días
    resistance = min(bb_up, high_20 * 1.01)

    return {
        "entry_low":  round(entry_low, 2),
        "entry_high": round(entry_high, 2),
        "stop_loss":  round(stop_loss, 2),
        "resistance": round(resistance, 2),
    }


# ─────────────────────────────────────────────────────────────────
#  DETECCIÓN DE RÉGIMEN DE MERCADO
# ─────────────────────────────────────────────────────────────────

def detect_market_regime(ipsa_df: Optional[pd.DataFrame]) -> Dict:
    """
    Detecta si el mercado está en régimen Bull/Bear/Neutral
    usando el índice IPSA.
    """
    if ipsa_df is None or len(ipsa_df) < 50:
        return {"regime": "NEUTRAL", "confidence": 0.5, "ipsa_momentum_3m": None}

    prices = ipsa_df["Close"]
    sma50  = compute_sma(prices, 50)
    sma200 = compute_sma(prices, min(200, len(prices)))

    above_50  = prices.iloc[-1] > sma50.iloc[-1]
    above_200 = prices.iloc[-1] > sma200.iloc[-1]

    mom_3m = (prices.iloc[-1] / prices.iloc[-63] - 1) if len(prices) >= 63 else 0
    mom_1m = (prices.iloc[-1] / prices.iloc[-21] - 1) if len(prices) >= 21 else 0

    # Reglas simples de régimen
    bull_signals = sum([above_50, above_200, mom_3m > 0, mom_1m > 0])

    if bull_signals >= 3:
        regime     = "BULL"
        confidence = bull_signals / 4
    elif bull_signals <= 1:
        regime     = "BEAR"
        confidence = 1 - bull_signals / 4
    else:
        regime     = "NEUTRAL"
        confidence = 0.5

    return {
        "regime":            regime,
        "confidence":        round(confidence, 2),
        "ipsa_momentum_3m":  round(mom_3m * 100, 2),
        "ipsa_above_sma50":  above_50,
        "ipsa_above_sma200": above_200,
    }


# ─────────────────────────────────────────────────────────────────
#  ANÁLISIS COMPLETO POR ACCIÓN
# ─────────────────────────────────────────────────────────────────

def analyze_ticker(
    ticker:         str,
    price_data:     Dict,
    fundamentals:   Dict,
    risk_free_rate: float,
    trailing_yield: Optional[float] = None,
) -> Dict:
    """
    Ejecuta todos los factores para una acción y retorna análisis completo.
    """
    df   = price_data.get(ticker)
    fund = fundamentals.get(ticker, {})

    current_price = float(df["Close"].iloc[-1]) if df is not None and not df.empty else 0.0

    # Factor A: Dividendos
    div_factor = factor_dividend_arbitrage(
        dividend_yield  = fund.get("dividend_yield"),
        risk_free_rate  = risk_free_rate,
        trailing_yield  = trailing_yield,
    )

    # Factor B: Calidad
    qual_factor = factor_quality(
        roe             = fund.get("roe"),
        debt_to_equity  = fund.get("debt_to_equity"),
        earnings_growth = fund.get("earnings_growth"),
        payout_ratio    = fund.get("payout_ratio"),
        current_ratio   = fund.get("current_ratio"),
        is_bank         = fund.get("is_financial_sector", False),
    )

    # Factor C: Momentum
    mom_factor = factor_momentum(df)

    # Factor D: Riesgo
    risk_factor = factor_risk(df)

    # Zona de entrada
    entry_zone = compute_entry_zone(df, current_price)

    return {
        "ticker":               ticker,
        "name":                 fund.get("name", ticker),
        "current_price":        round(current_price, 2),
        "market_cap":           fund.get("market_cap"),
        "pe_ratio":             fund.get("pe_ratio"),
        "pb_ratio":             fund.get("pb_ratio"),
        "is_financial_sector":  fund.get("is_financial_sector", False),
        **div_factor,
        **qual_factor,
        **mom_factor,
        **risk_factor,
        **entry_zone,
    }
