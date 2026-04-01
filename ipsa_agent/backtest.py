"""
IPSA Agent - Persistencia de Historial y Motor de Backtesting
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config import HISTORY_FILE, BACKTEST_FILE, DATA_DIR

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  HISTORIAL DE DECISIONES
# ─────────────────────────────────────────────────────────────────

def load_history() -> List[Dict]:
    """Carga historial de decisiones anteriores."""
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"[HISTORY] Error cargando historial: {e}")
        return []


def save_decision(
    top5:      pd.DataFrame,
    macro:     Dict,
    regime:    Dict,
    date_str:  str,
):
    """Persiste la decisión diaria en el historial JSON."""
    os.makedirs(DATA_DIR, exist_ok=True)
    history = load_history()

    def safe_row(row):
        d = {}
        for k, v in row.items():
            if isinstance(v, float) and np.isnan(v):
                d[k] = None
            elif isinstance(v, (np.integer, np.floating)):
                d[k] = float(v)
            elif isinstance(v, bool):
                d[k] = v
            else:
                d[k] = v
        return d

    decision = {
        "date":     date_str,
        "top5":     [safe_row(row) for _, row in top5.iterrows()],
        "tickers":  top5["ticker"].tolist() if not top5.empty else [],
        "macro":    macro,
        "regime":   regime,
    }

    history.append(decision)

    # Mantener solo últimos 365 días
    history = history[-365:]

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"[HISTORY] Decisión guardada ({len(history)} registros)")


def get_previous_top5_tickers() -> List[str]:
    """Obtiene los tickers del Top 5 del día anterior."""
    history = load_history()
    if len(history) < 2:
        return []
    return history[-2].get("tickers", [])


def build_performance_history() -> pd.DataFrame:
    """
    Construye un DataFrame con el historial de scores y señales
    para análisis de rendimiento del agente.
    """
    history = load_history()
    if not history:
        return pd.DataFrame()

    rows = []
    for entry in history:
        for stock in entry.get("top5", []):
            rows.append({
                "date":           entry["date"],
                "ticker":         stock.get("ticker"),
                "score":          stock.get("score"),
                "signal":         stock.get("signal"),
                "current_price":  stock.get("current_price"),
                "dividend_yield": stock.get("dividend_yield"),
                "momentum_3m":    stock.get("momentum_3m"),
                "sharpe_ratio":   stock.get("sharpe_ratio"),
                "regime":         entry.get("regime", {}).get("regime"),
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────
#  BACKTESTING ENGINE
# ─────────────────────────────────────────────────────────────────

class BacktestEngine:
    """
    Simula el rendimiento histórico de la estrategia aplicando
    el mismo scoring sobre datos pasados.
    """

    def __init__(
        self,
        price_data:     Dict[str, pd.DataFrame],
        fundamentals:   Dict[str, Dict],
        risk_free_rate: float = 0.05,
        top_n:          int   = 5,
        rebalance_days: int   = 21,   # mensual
        initial_capital: float = 10_000_000,  # CLP
    ):
        self.price_data      = price_data
        self.fundamentals    = fundamentals
        self.risk_free_rate  = risk_free_rate
        self.top_n           = top_n
        self.rebalance_days  = rebalance_days
        self.initial_capital = initial_capital

    def _get_price_at(self, ticker: str, date: pd.Timestamp) -> Optional[float]:
        df = self.price_data.get(ticker)
        if df is None:
            return None
        idx = df.index.searchsorted(date)
        if idx >= len(df):
            idx = len(df) - 1
        if idx < 0:
            return None
        return float(df["Close"].iloc[idx])

    def _select_portfolio_at(self, date: pd.Timestamp) -> List[str]:
        """Aplica scoring usando datos disponibles hasta `date`."""
        from analysis_engine import analyze_ticker
        from scoring import rank_all_tickers, select_top5

        # Recortar price_data hasta `date`
        sliced_prices = {}
        for ticker, df in self.price_data.items():
            hist = df[df.index <= date]
            if len(hist) >= 30:
                sliced_prices[ticker] = hist

        analyses = {}
        for ticker in sliced_prices:
            analyses[ticker] = analyze_ticker(
                ticker         = ticker,
                price_data     = sliced_prices,
                fundamentals   = self.fundamentals,
                risk_free_rate = self.risk_free_rate,
            )

        ranked = rank_all_tickers(analyses, self.risk_free_rate)
        top5   = select_top5(ranked)
        return top5["ticker"].tolist()

    def run(self, start_date: str = None, end_date: str = None) -> Dict:
        """
        Ejecuta el backtest completo.
        Retorna métricas: retorno total, Sharpe, max drawdown, win rate.
        """
        logger.info("[BACKTEST] Iniciando backtest...")

        # Determinar rango de fechas
        all_dates = sorted(set(
            d for df in self.price_data.values() for d in df.index
        ))
        if not all_dates:
            logger.error("[BACKTEST] Sin datos de precios")
            return {}

        if start_date:
            start_dt = pd.Timestamp(start_date)
        else:
            start_dt = all_dates[len(all_dates)//2]  # Usar segunda mitad

        if end_date:
            end_dt = pd.Timestamp(end_date)
        else:
            end_dt = all_dates[-1]

        trade_dates = [d for d in all_dates if start_dt <= d <= end_dt]
        if len(trade_dates) < self.rebalance_days:
            logger.warning("[BACKTEST] Período muy corto")
            return {}

        # Puntos de rebalanceo
        rebalance_dates = trade_dates[::self.rebalance_days]

        portfolio       = {}      # {ticker: shares}
        capital         = self.initial_capital
        nav_series      = {}
        portfolio_tickers_history = {}

        for i, rb_date in enumerate(rebalance_dates):
            logger.info(f"[BACKTEST] Rebalanceo {i+1}/{len(rebalance_dates)}: {rb_date.date()}")

            selected = self._select_portfolio_at(rb_date)
            if not selected:
                continue

            # Liquidar posiciones anteriores
            for ticker, shares in portfolio.items():
                price = self._get_price_at(ticker, rb_date)
                if price:
                    capital += shares * price

            portfolio = {}
            portfolio_tickers_history[str(rb_date.date())] = selected

            # Invertir equitativamente en el nuevo Top N
            weight_per_stock = 1.0 / len(selected)
            for ticker in selected:
                price = self._get_price_at(ticker, rb_date)
                if price and price > 0:
                    alloc  = capital * weight_per_stock
                    shares = alloc / price
                    portfolio[ticker] = shares
                    capital -= shares * price  # remanente a caja

            nav_series[rb_date] = self._compute_nav(portfolio, rb_date, capital)

        # NAV al final del período
        final_nav = self._compute_nav(portfolio, trade_dates[-1], capital)
        nav_series[trade_dates[-1]] = final_nav

        # Series temporales NAV
        nav_ts = pd.Series(nav_series).sort_index()

        # Benchmark: IPSA buy & hold
        ipsa_start = self._get_ipsa_price(start_dt)
        ipsa_end   = self._get_ipsa_price(trade_dates[-1])
        benchmark_return = ((ipsa_end / ipsa_start) - 1) if ipsa_start and ipsa_end else None

        # Métricas
        metrics = self._compute_metrics(nav_ts, benchmark_return)
        metrics["portfolio_history"] = portfolio_tickers_history

        logger.info(f"[BACKTEST] Completado. Retorno: {metrics.get('total_return', 0)*100:.1f}%")

        self._save_results(metrics)
        return metrics

    def _compute_nav(self, portfolio: Dict, date: pd.Timestamp, cash: float) -> float:
        nav = cash
        for ticker, shares in portfolio.items():
            price = self._get_price_at(ticker, date)
            if price:
                nav += shares * price
        return nav

    def _get_ipsa_price(self, date: pd.Timestamp) -> Optional[float]:
        """Proxy: usamos precio promedio del universo como benchmark."""
        prices = []
        for df in self.price_data.values():
            hist = df[df.index <= date]
            if not hist.empty:
                prices.append(float(hist["Close"].iloc[-1]))
        return float(np.mean(prices)) if prices else None

    def _compute_metrics(self, nav_ts: pd.Series, benchmark_return: Optional[float]) -> Dict:
        if len(nav_ts) < 2:
            return {}

        nav_returns = nav_ts.pct_change().dropna()
        total_return = (nav_ts.iloc[-1] / nav_ts.iloc[0]) - 1

        # Anualizar
        n_years = (nav_ts.index[-1] - nav_ts.index[0]).days / 365.25
        annual_return = (1 + total_return) ** (1 / n_years) - 1 if n_years > 0 else 0

        vol = float(nav_returns.std() * np.sqrt(252 / 21))  # ajustar por rebalanceo mensual
        sharpe = (annual_return - self.risk_free_rate) / vol if vol > 0 else 0

        # Drawdown
        peak = nav_ts.cummax()
        dd   = (nav_ts - peak) / peak
        max_dd = float(dd.min())

        # Win rate: rebalanceos con retorno positivo
        rebalance_returns = nav_ts.pct_change().dropna()
        win_rate = float((rebalance_returns > 0).mean()) if len(rebalance_returns) > 0 else 0

        return {
            "initial_capital":     self.initial_capital,
            "final_nav":           float(nav_ts.iloc[-1]),
            "total_return":        round(total_return, 4),
            "annual_return":       round(annual_return, 4),
            "volatility":          round(vol, 4),
            "sharpe_ratio":        round(sharpe, 4),
            "max_drawdown":        round(max_dd, 4),
            "win_rate":            round(win_rate, 4),
            "benchmark_return":    round(benchmark_return, 4) if benchmark_return else None,
            "alpha":               round(total_return - (benchmark_return or 0), 4),
            "n_rebalances":        len(nav_ts) - 1,
            "start_date":          str(nav_ts.index[0].date()),
            "end_date":            str(nav_ts.index[-1].date()),
            "nav_series":          {str(k.date()): round(v, 2) for k, v in nav_ts.items()},
        }

    def _save_results(self, metrics: Dict):
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(BACKTEST_FILE, "w", encoding="utf-8") as f:
            json.dump(metrics, f, ensure_ascii=False, indent=2, default=str)
        logger.info(f"[BACKTEST] Resultados guardados en {BACKTEST_FILE}")


def print_backtest_summary(metrics: Dict):
    """Imprime resumen del backtest en consola."""
    if not metrics:
        print("❌ Backtest sin resultados.")
        return

    sep = "─" * 60
    print(f"\n{'='*60}")
    print(f"  📈 BACKTEST SUMMARY | {metrics.get('start_date')} → {metrics.get('end_date')}")
    print(f"{'='*60}")
    print(sep)
    print(f"  Capital inicial:    CLP ${metrics.get('initial_capital', 0):>14,.0f}")
    print(f"  NAV final:          CLP ${metrics.get('final_nav', 0):>14,.0f}")
    print(f"  Retorno total:      {metrics.get('total_return', 0)*100:>8.1f}%")
    print(f"  Retorno anualizado: {metrics.get('annual_return', 0)*100:>8.1f}%")
    print(f"  Volatilidad:        {metrics.get('volatility', 0)*100:>8.1f}%")
    print(f"  Sharpe Ratio:       {metrics.get('sharpe_ratio', 0):>8.3f}")
    print(f"  Max Drawdown:       {metrics.get('max_drawdown', 0)*100:>8.1f}%")
    print(f"  Win Rate:           {metrics.get('win_rate', 0)*100:>8.1f}%")
    if metrics.get("benchmark_return"):
        print(f"  Benchmark (IPSA):   {metrics.get('benchmark_return', 0)*100:>8.1f}%")
        print(f"  Alpha generado:     {metrics.get('alpha', 0)*100:>8.1f}%")
    print(f"  Rebalanceos:        {metrics.get('n_rebalances', 0):>8d}")
    print(f"{'='*60}\n")
