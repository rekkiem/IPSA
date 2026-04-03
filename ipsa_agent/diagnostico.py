"""
IPSA Agent — Herramienta de Diagnóstico
Inspecciona qué datos reales llegan de yfinance para cada ticker
y por qué un ticker puede estar siendo excluido o con score bajo.

Uso:
    cd ipsa_agent
    python diagnostico.py                     # Analiza todos los tickers
    python diagnostico.py CHILE.SN            # Analiza un ticker específico
    python diagnostico.py --top5              # Muestra por qué Top5 está vacío
    python diagnostico.py --kill              # Solo muestra exclusiones
"""

import sys
import os
import warnings
import argparse
import json

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np

from config import IPSA_TICKERS, SCORE_HIGH_THRESHOLD, SCORE_MEDIUM_THRESHOLD
from price_cache import PriceCache


def fmt(v, pct=False, mult=100):
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))):
        return "N/D"
    if pct:
        return f"{float(v)*mult:.1f}%"
    return f"{float(v):.4f}"


def inspect_fundamentals(ticker: str) -> dict:
    """Descarga y muestra todos los campos de yfinance para un ticker."""
    import yfinance as yf
    print(f"\n{'='*60}")
    print(f"  FUNDAMENTALES yfinance: {ticker}")
    print(f"{'='*60}")
    try:
        obj  = yf.Ticker(ticker)
        info = obj.info
        campos = [
            ("sector",          "Sector"),
            ("industry",        "Industria"),
            ("returnOnEquity",  "ROE"),
            ("debtToEquity",    "D/E (raw yfinance)"),
            ("payoutRatio",     "Payout Ratio"),
            ("dividendYield",   "DY (forward)"),
            ("dividendRate",    "DY Rate"),
            ("earningsGrowth",  "EPS Growth"),
            ("revenueGrowth",   "Revenue Growth"),
            ("currentRatio",    "Current Ratio"),
            ("marketCap",       "Market Cap"),
            ("trailingPE",      "P/E"),
            ("priceToBook",     "P/B"),
            ("shortName",       "Nombre"),
        ]
        for key, label in campos:
            val = info.get(key)
            print(f"  {label:<25} {val}")
        return info
    except Exception as e:
        print(f"  ERROR: {e}")
        return {}


def run_full_analysis(tickers=None, verbose=True):
    """Ejecuta el análisis completo y muestra el diagnóstico."""
    from data_layer import fetch_fundamentals, fetch_macro_snapshot, fetch_ipsa_index_data
    from analysis_engine import analyze_ticker, detect_market_regime
    from scoring import rank_all_tickers, select_top5, assign_portfolio_weights, apply_kill_conditions
    from extensions.ext_data_sources import fetch_yfinance_robust

    tickers = tickers or IPSA_TICKERS
    cache   = PriceCache()

    print("\n📦 CARGANDO PRECIOS DEL CACHÉ...")
    price_data = cache.fetch_missing(tickers, fetch_yfinance_robust, "2y", delay=0.05)
    print(f"   {len(price_data)}/{len(tickers)} tickers con precios\n")

    macro = fetch_macro_snapshot()
    rfr   = macro.get("risk_free_rate", 0.05)

    print("💾 DESCARGANDO FUNDAMENTALES...")
    fundamentals = {}
    for t in list(price_data.keys()):
        fundamentals[t] = fetch_fundamentals(t)
    print(f"   {len(fundamentals)} fundamentales cargados\n")

    # Análisis completo
    analyses = {}
    for t in price_data:
        analyses[t] = analyze_ticker(t, price_data, fundamentals, rfr)

    ranked = rank_all_tickers(analyses, rfr)
    top5   = select_top5(ranked)
    top5   = assign_portfolio_weights(top5)

    # ── TABLA COMPLETA ────────────────────────────────────────────
    print(f"\n{'='*100}")
    print(f"  RANKING COMPLETO — {len(ranked)} tickers")
    print(f"{'='*100}")
    hdr = f"  {'#':<3} {'Ticker':<16} {'Score':<8} {'DY%':<7} {'M3%':<8} {'M6%':<8} {'PR%':<7} {'D/E':<7} {'RSI':<6} {'Banco':<7} {'Excl':<6} {'Motivo'}"
    print(hdr)
    print("  " + "-"*97)

    for _, row in ranked.iterrows():
        dy  = (row.get("dividend_yield") or 0) * 100
        m3  = row.get("momentum_3m") or 0
        m6  = row.get("momentum_6m") or 0
        pr  = (row.get("payout_ratio") or 0) * 100
        de  = row.get("debt_to_equity") or 0
        rsi = row.get("rsi") or 0
        bank = "Si" if row.get("is_financial_sector") else "No"
        excl = "SI" if row.get("is_excluded") else "no"
        reason = row.get("kill_reasons", [])
        reason_str = reason[0][:35] if reason else "elegible"
        signal = row.get("signal","")
        emoji = "🟢" if "COMPRAR" in signal else "🟡" if "ESPERAR" in signal else "🟠" if "CAUTELA" in signal else "🔴"

        print(f"  {row['rank']:<3} {row['ticker']:<16} {row['score']:.4f}   {dy:>5.1f}%  {m3:>+7.1f}%  {m6:>+7.1f}%  {pr:>5.0f}%  {de:>5.1f}x  {rsi:>5.0f}  {bank:<7} {excl:<6} {emoji} {reason_str}")

    # ── TOP 5 ─────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  TOP 5")
    print(f"{'='*80}")
    if top5.empty:
        print("  ❌ Top5 VACÍO — ninguna acción pasó los filtros")
    else:
        for i, row in top5.iterrows():
            sig = row.get("signal","")
            print(f"  {i+1}. {row['ticker']:<16} Score={row['score']:.4f} | {sig}")

    # ── DIAGNÓSTICO DE EXCLUSIONES ────────────────────────────────
    excluded = ranked[ranked["is_excluded"]]
    if len(excluded) > 0:
        print(f"\n⚠️  ACCIONES EXCLUIDAS ({len(excluded)}):")
        for _, row in excluded.iterrows():
            reasons = row.get("kill_reasons", [])
            for r in reasons:
                print(f"   {row['ticker']:<16} → {r}")

    # ── ANÁLISIS DE POR QUÉ EL SCORE ES BAJO ─────────────────────
    print(f"\n📊 DESGLOSE DE FACTORES (Top 8 por score):")
    print(f"  {'Ticker':<16} {'Div':>6} {'Cal':>6} {'Mom':>6} {'Risk':>6} {'Score':>7}")
    print(f"  {'-'*50}")
    for _, row in ranked.head(8).iterrows():
        fd = row.get("factor_dividend") or 0
        fq = row.get("factor_quality")  or 0
        fm = row.get("factor_momentum") or 0
        fr = row.get("factor_risk")     or 0
        print(f"  {row['ticker']:<16} {fd:>6.3f} {fq:>6.3f} {fm:>6.3f} {fr:>6.3f} {row['score']:>7.4f}")

    # ── RÉGIMEN ───────────────────────────────────────────────────
    ipsa_df = fetch_ipsa_index_data()
    regime  = detect_market_regime(ipsa_df)
    print(f"\n🌍 RÉGIMEN DE MERCADO: {regime.get('regime')} (confianza: {regime.get('confidence')})")
    print(f"   IPSA Momentum 3M: {regime.get('ipsa_momentum_3m')}%")
    print(f"   Sobre SMA50:  {regime.get('ipsa_above_sma50')}   Sobre SMA200: {regime.get('ipsa_above_sma200')}")

    print(f"\n💱 MACRO: USD/CLP={macro.get('usdclp')} | TPM={macro.get('risk_free_rate')*100:.2f}%")
    print()

    return ranked, top5


def main():
    parser = argparse.ArgumentParser(description="IPSA Agent — Herramienta de Diagnóstico")
    parser.add_argument("ticker", nargs="?", help="Ticker específico a inspeccionar (ej: CHILE.SN)")
    parser.add_argument("--top5",  action="store_true", help="Mostrar análisis Top5")
    parser.add_argument("--kill",  action="store_true", help="Mostrar solo exclusiones")
    parser.add_argument("--fund",  action="store_true", help="Mostrar fundamentales raw de yfinance")
    args = parser.parse_args()

    if args.ticker and args.fund:
        inspect_fundamentals(args.ticker)
    elif args.ticker:
        run_full_analysis(tickers=[args.ticker])
    else:
        run_full_analysis()


if __name__ == "__main__":
    main()
