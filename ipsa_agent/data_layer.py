"""
IPSA Agent - Capa de Ingesta de Datos
Obtiene precios históricos, datos fundamentales y macro
"""

import logging
import time
import warnings
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import yfinance as yf

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  PRECIOS HISTÓRICOS
# ─────────────────────────────────────────────────────────────────

def fetch_price_history(tickers: list, period: str = "2y") -> Dict[str, pd.DataFrame]:
    """
    Descarga histórico de precios para todos los tickers del IPSA.
    Retorna dict {ticker: DataFrame con OHLCV}.
    """
    price_data = {}
    failed = []

    for ticker in tickers:
        try:
            obj = yf.Ticker(ticker)
            df = obj.history(period=period, auto_adjust=True)
            if df.empty or len(df) < 30:
                logger.warning(f"[DATA] Sin datos suficientes para {ticker}")
                failed.append(ticker)
                continue
            df.index = pd.to_datetime(df.index).tz_localize(None)
            price_data[ticker] = df
            time.sleep(0.15)  # Rate limiting
        except Exception as e:
            logger.warning(f"[DATA] Error fetching {ticker}: {e}")
            failed.append(ticker)

    logger.info(f"[DATA] Precios cargados: {len(price_data)}/{len(tickers)} tickers")
    if failed:
        logger.warning(f"[DATA] Fallaron: {failed}")

    return price_data


def fetch_current_prices(tickers: list) -> Dict[str, float]:
    """Obtiene precios actuales de cierre."""
    prices = {}
    for ticker in tickers:
        try:
            obj = yf.Ticker(ticker)
            hist = obj.history(period="5d")
            if not hist.empty:
                prices[ticker] = float(hist["Close"].iloc[-1])
        except Exception as e:
            logger.warning(f"[PRICE] Error {ticker}: {e}")
    return prices


# ─────────────────────────────────────────────────────────────────
#  DATOS FUNDAMENTALES
# ─────────────────────────────────────────────────────────────────

def fetch_fundamentals(ticker: str) -> Dict:
    """
    Extrae métricas fundamentales desde yfinance.
    Retorna dict con ROE, EPS, D/E, Payout Ratio, Forward Dividend Yield, etc.
    """
    defaults = {
        "ticker":              ticker,
        "roe":                 None,
        "eps":                 None,
        "debt_to_equity":      None,
        "payout_ratio":        None,
        "dividend_yield":      None,
        "forward_dividend":    None,
        "trailing_dividend":   None,
        "earnings_growth":     None,
        "revenue_growth":      None,
        "current_ratio":       None,
        "gross_margins":       None,
        "market_cap":          None,
        "pe_ratio":            None,
        "pb_ratio":            None,
        "dividend_history":    [],
        "name":                ticker,
    }

    try:
        obj  = yf.Ticker(ticker)
        info = obj.info

        defaults.update({
            "name":              info.get("shortName", ticker),
            "roe":               info.get("returnOnEquity"),
            "eps":               info.get("trailingEps"),
            "debt_to_equity":    info.get("debtToEquity"),
            "payout_ratio":      info.get("payoutRatio"),
            "dividend_yield":    info.get("dividendYield"),
            "forward_dividend":  info.get("dividendRate"),
            "earnings_growth":   info.get("earningsGrowth"),
            "revenue_growth":    info.get("revenueGrowth"),
            "current_ratio":     info.get("currentRatio"),
            "gross_margins":     info.get("grossMargins"),
            "market_cap":        info.get("marketCap"),
            "pe_ratio":          info.get("trailingPE"),
            "pb_ratio":          info.get("priceToBook"),
        })

        # ── Normalización inteligente de Deuda/Equity ────────────────
        # yfinance tiene tres posibles representaciones:
        #   1. Decimal real:     0.85  (85% D/E → 0.85x)
        #   2. Porcentaje:       85.0  (mismo, pero *100)
        #   3. Bancario real:    8.5   (apalancamiento regulatorio: ~8-10x es normal)
        #
        # Problema: no podemos distinguir 8.5 (bancario) de 8.5 (% mal formateado)
        # Solución: detectar sector financiero por ticker y aplicar umbral ad-hoc
        de      = defaults["debt_to_equity"]
        sector  = info.get("sector", "").lower()
        industry = info.get("industry", "").lower()
        is_bank = any(k in sector + industry for k in
                      ("bank", "financial", "insurance", "credit", "banco", "financier"))
        defaults["is_financial_sector"] = is_bank

        if de is not None:
            if de > 20:
                # Probablemente viene en porcentaje (ej: 85 → 0.85x)
                defaults["debt_to_equity"] = de / 100
            elif de > 5 and is_bank:
                # Banco con D/E 5-15: apalancamiento regulatorio normal → no penalizar
                # Guardamos el valor real pero marcamos para el filtro
                defaults["debt_to_equity"] = de   # lo guardamos real
            # Si de <= 5 y no banco: valor correcto, no tocar

        # Historial de dividendos
        try:
            divs = obj.dividends
            if not divs.empty:
                divs.index = pd.to_datetime(divs.index).tz_localize(None)
                defaults["dividend_history"] = divs.tail(8).to_dict()
        except Exception:
            pass

        time.sleep(0.2)
    except Exception as e:
        logger.warning(f"[FUND] Error {ticker}: {e}")

    return defaults


def fetch_all_fundamentals(tickers: list) -> Dict[str, Dict]:
    """Descarga fundamentales para todos los tickers."""
    logger.info("[FUND] Iniciando descarga de fundamentales...")
    result = {}
    for ticker in tickers:
        result[ticker] = fetch_fundamentals(ticker)
    logger.info(f"[FUND] Fundamentales cargados: {len(result)} tickers")
    return result


# ─────────────────────────────────────────────────────────────────
#  DATOS MACRO
# ─────────────────────────────────────────────────────────────────

def fetch_usdclp() -> Optional[float]:
    """Obtiene el tipo de cambio USD/CLP actual."""
    try:
        obj  = yf.Ticker("USDCLP=X")
        hist = obj.history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            logger.info(f"[MACRO] USD/CLP: {rate:.2f}")
            return rate
    except Exception as e:
        logger.warning(f"[MACRO] Error USDCLP: {e}")
    return None


def fetch_risk_free_rate() -> float:
    """
    Intenta obtener la TPM del Banco Central de Chile.
    Si falla, usa valor por defecto configurado.
    """
    from config import DEFAULT_RISK_FREE_RATE

    # BCCh no tiene API pública directa; usamos el dato publicado en su sitio
    # Intentamos scraping liviano
    try:
        url = "https://si3.bcentral.cl/Indicadoressiete/secure/Indicadoressiete.aspx"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=5)
        # Si devuelve 200 parseamos, si no usamos default
        # (El sitio del BCCh requiere JS, así que usamos default)
        if resp.status_code != 200:
            raise ValueError("No accesible")
    except Exception:
        pass

    # Fuente alternativa: bancocentral.cl API de estadísticas (si disponible)
    # Por ahora usamos el default configurado
    rate = DEFAULT_RISK_FREE_RATE
    logger.info(f"[MACRO] Tasa libre de riesgo: {rate*100:.2f}%")
    return rate


def fetch_inflation() -> float:
    """
    IPC anual de Chile (INE).
    Retorna el valor configurado como fallback.
    """
    from config import DEFAULT_INFLATION
    return DEFAULT_INFLATION


def fetch_ipsa_index_data() -> Optional[pd.DataFrame]:
    """Descarga datos del índice IPSA para análisis de régimen de mercado."""
    try:
        obj = yf.Ticker("^IPSA")
        df  = obj.history(period="2y", auto_adjust=True)
        if not df.empty:
            df.index = pd.to_datetime(df.index).tz_localize(None)
            return df
    except Exception as e:
        logger.warning(f"[MACRO] Error IPSA index: {e}")
    return None


def fetch_macro_snapshot() -> Dict:
    """Retorna snapshot macroeconómico completo."""
    return {
        "usdclp":          fetch_usdclp(),
        "risk_free_rate":  fetch_risk_free_rate(),
        "inflation":       fetch_inflation(),
        "timestamp":       datetime.now().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────
#  HELPER: DIVIDENDOS ANUALIZADOS
# ─────────────────────────────────────────────────────────────────

def compute_trailing_dividend_yield(ticker: str, price_data: Dict[str, pd.DataFrame]) -> Optional[float]:
    """
    Calcula dividend yield trailing a partir del historial real de dividendos.
    Divide dividendos pagados en los últimos 12M entre precio actual.
    """
    try:
        obj  = yf.Ticker(ticker)
        divs = obj.dividends
        if divs.empty:
            return None
        divs.index = pd.to_datetime(divs.index).tz_localize(None)
        cutoff = datetime.now() - timedelta(days=365)
        ttm_divs = divs[divs.index >= cutoff].sum()

        if ticker in price_data and not price_data[ticker].empty:
            current_price = float(price_data[ticker]["Close"].iloc[-1])
            if current_price > 0:
                return ttm_divs / current_price
    except Exception:
        pass
    return None
