"""
IPSA Agent - Orquestador Principal
Pipeline completo: Ingesta → Análisis → Score → Reporte
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

# ── Configurar logging ANTES de imports locales ──
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/ipsa_agent_{datetime.now().strftime('%Y%m%d')}.log"),
    ],
)
logger = logging.getLogger("ipsa_agent.main")

import pandas as pd

from config import IPSA_TICKERS, IPSA_TICKER_NAMES
from data_layer import (
    fetch_price_history,
    fetch_all_fundamentals,
    fetch_macro_snapshot,
    fetch_ipsa_index_data,
    compute_trailing_dividend_yield,
)
from analysis_engine import analyze_ticker, detect_market_regime
from scoring import (
    rank_all_tickers,
    select_top5,
    assign_portfolio_weights,
    detect_significant_changes,
)
from report_generator import (
    print_daily_report,
    generate_html_report,
    save_html_report,
    save_json_report,
)
from backtest import (
    load_history,
    save_decision,
    get_previous_top5_tickers,
    BacktestEngine,
    print_backtest_summary,
)


# ─────────────────────────────────────────────────────────────────
#  PIPELINE DIARIO
# ─────────────────────────────────────────────────────────────────

def run_daily_pipeline(
    tickers:    Optional[list] = None,
    save_html:  bool = True,
    save_json:  bool = True,
    verbose:    bool = True,
) -> dict:
    """
    Pipeline completo de análisis diario.
    Retorna dict con top5, ranked_all, macro, regime.
    """
    start_time = time.time()
    date_str   = datetime.now().strftime("%Y-%m-%d %H:%M")
    tickers    = tickers or IPSA_TICKERS

    logger.info("=" * 60)
    logger.info(f"IPSA AGENT — Iniciando análisis diario: {date_str}")
    logger.info("=" * 60)

    # ── 1. INGESTA DE DATOS ──────────────────────────────────────
    logger.info("[PIPELINE] Paso 1/5: Descargando datos de mercado...")

    price_data   = fetch_price_history(tickers, period="2y")
    fundamentals = fetch_all_fundamentals(list(price_data.keys()))
    macro        = fetch_macro_snapshot()
    ipsa_df      = fetch_ipsa_index_data()

    risk_free_rate = macro.get("risk_free_rate", 0.05)

    # Yields trailing (más confiables que forward en Chile)
    trailing_yields = {}
    for ticker in price_data:
        ty = compute_trailing_dividend_yield(ticker, price_data)
        if ty is not None:
            trailing_yields[ticker] = ty

    logger.info(f"[PIPELINE] Datos cargados: {len(price_data)} tickers con precios")

    # ── 2. ANÁLISIS TÉCNICO + FUNDAMENTAL ───────────────────────
    logger.info("[PIPELINE] Paso 2/5: Calculando factores de análisis...")

    analyses = {}
    for ticker in price_data:
        analyses[ticker] = analyze_ticker(
            ticker          = ticker,
            price_data      = price_data,
            fundamentals    = fundamentals,
            risk_free_rate  = risk_free_rate,
            trailing_yield  = trailing_yields.get(ticker),
        )

    # ── 3. SCORING Y RANKING ─────────────────────────────────────
    logger.info("[PIPELINE] Paso 3/5: Scoring y ranking del universo IPSA...")

    ranked_all = rank_all_tickers(analyses, risk_free_rate)
    top5       = select_top5(ranked_all)
    top5       = assign_portfolio_weights(top5)

    # ── 4. RÉGIMEN Y CAMBIOS ─────────────────────────────────────
    logger.info("[PIPELINE] Paso 4/5: Detectando régimen y cambios...")

    regime            = detect_market_regime(ipsa_df)
    prev_tickers      = get_previous_top5_tickers()
    changes           = detect_significant_changes(top5, prev_tickers)

    # ── 5. REPORTE ───────────────────────────────────────────────
    logger.info("[PIPELINE] Paso 5/5: Generando reportes...")

    if verbose:
        print_daily_report(top5, ranked_all, macro, regime, changes, date_str)

    html_path = None
    if save_html:
        html = generate_html_report(top5, ranked_all, macro, regime, changes, date_str)
        html_path = save_html_report(html, date_str)

    json_path = None
    if save_json:
        json_path = save_json_report(top5, ranked_all, macro, regime, changes, date_str)

    # ── PERSISTIR DECISIÓN ───────────────────────────────────────
    if not top5.empty:
        save_decision(top5, macro, regime, date_str)

    elapsed = time.time() - start_time
    logger.info(f"[PIPELINE] Completado en {elapsed:.1f}s")
    if html_path:
        logger.info(f"[PIPELINE] Reporte HTML: {html_path}")

    return {
        "top5":        top5,
        "ranked_all":  ranked_all,
        "macro":       macro,
        "regime":      regime,
        "changes":     changes,
        "html_path":   html_path,
        "json_path":   json_path,
    }


# ─────────────────────────────────────────────────────────────────
#  BACKTESTING CLI
# ─────────────────────────────────────────────────────────────────

def run_backtest(start_date: str = None, end_date: str = None):
    """Ejecuta el backtesting con datos históricos."""
    logger.info("[BACKTEST] Descargando datos históricos (esto puede tomar varios minutos)...")

    price_data   = fetch_price_history(IPSA_TICKERS, period="2y")
    fundamentals = fetch_all_fundamentals(list(price_data.keys()))
    macro        = fetch_macro_snapshot()

    engine = BacktestEngine(
        price_data      = price_data,
        fundamentals    = fundamentals,
        risk_free_rate  = macro.get("risk_free_rate", 0.05),
        top_n           = 5,
        rebalance_days  = 21,
        initial_capital = 10_000_000,
    )

    metrics = engine.run(start_date=start_date, end_date=end_date)
    print_backtest_summary(metrics)
    return metrics


# ─────────────────────────────────────────────────────────────────
#  CLI ENTRY POINT
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🇨🇱 IPSA Agent — Gestor Autónomo de Inversión",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main.py                          # Análisis diario completo
  python main.py --mode backtest          # Backtesting histórico
  python main.py --mode daily --no-html  # Sin reporte HTML
  python main.py --mode backtest --start 2023-01-01 --end 2024-01-01
        """
    )

    parser.add_argument(
        "--mode", choices=["daily", "backtest", "history"],
        default="daily", help="Modo de operación"
    )
    parser.add_argument("--start", default=None, help="Fecha inicio backtest (YYYY-MM-DD)")
    parser.add_argument("--end",   default=None, help="Fecha fin backtest (YYYY-MM-DD)")
    parser.add_argument("--no-html",  action="store_true", help="Omitir reporte HTML")
    parser.add_argument("--no-json",  action="store_true", help="Omitir reporte JSON")
    parser.add_argument("--quiet",    action="store_true", help="Suprimir output consola")

    args = parser.parse_args()

    if args.mode == "daily":
        run_daily_pipeline(
            save_html = not args.no_html,
            save_json = not args.no_json,
            verbose   = not args.quiet,
        )

    elif args.mode == "backtest":
        run_backtest(start_date=args.start, end_date=args.end)

    elif args.mode == "history":
        history = load_history()
        if not history:
            print("📭 Sin historial de decisiones aún.")
        else:
            print(f"\n📚 Historial: {len(history)} sesiones guardadas")
            for entry in history[-10:]:  # últimas 10
                tickers_str = ", ".join(entry.get("tickers", []))
                regime_str  = entry.get("regime", {}).get("regime", "N/D")
                print(f"  {entry['date']:20s} | {regime_str:8s} | Top5: {tickers_str}")


if __name__ == "__main__":
    main()
