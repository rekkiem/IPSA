"""
IPSA Agent v2 — Orquestador Principal con Extensiones
Integra: Data Cascade, ML Predictivo, Telegram, Dashboard JSON
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional

os.makedirs("logs", exist_ok=True)

def _build_stream_handler() -> logging.StreamHandler:
    """
    StreamHandler con UTF-8 forzado en Windows.
    Windows usa cp1252 por defecto → UnicodeEncodeError con emojis/caracteres especiales.
    """
    try:
        # Python 3.9+: reconfigure stdout a UTF-8
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        handler = logging.StreamHandler(sys.stdout)
    except Exception:
        handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    return handler

def _build_file_handler() -> logging.FileHandler:
    fname = f"logs/ipsa_agent_{datetime.now().strftime('%Y%m%d')}.log"
    # encoding='utf-8' evita el error en el handler de archivo en Windows
    handler = logging.FileHandler(fname, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    return handler

logging.basicConfig(
    level    = logging.INFO,
    format   = "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers = [_build_stream_handler(), _build_file_handler()],
)
logger = logging.getLogger("ipsa_agent.main_v2")

# Cargar .env si existe
def _load_env():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
_load_env()

import pandas as pd

from config import IPSA_TICKERS
from data_layer import (
    fetch_price_history, fetch_all_fundamentals,
    fetch_macro_snapshot, fetch_ipsa_index_data,
    compute_trailing_dividend_yield,
)
from analysis_engine import analyze_ticker, detect_market_regime
from scoring import (
    rank_all_tickers, select_top5,
    assign_portfolio_weights, detect_significant_changes,
)
from report_generator import (
    print_daily_report, generate_html_report,
    save_html_report, save_json_report,
)
from backtest import (
    load_history, save_decision,
    get_previous_top5_tickers,
    BacktestEngine, print_backtest_summary,
)

# Extensions (import con fallback si no están instaladas las deps)
try:
    from extensions.ext_data_sources import CascadeDataFetcher, get_data_source_status
    HAS_CASCADE = True
except ImportError:
    HAS_CASCADE = False

try:
    from extensions.ext_ml_model import MLPipeline, print_ml_metrics
    HAS_ML = True
except ImportError:
    HAS_ML = False

try:
    from extensions.ext_telegram import TelegramAlerter, TelegramCommandHandler
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False

try:
    from price_cache import PriceCache
    HAS_CACHE = True
except ImportError:
    HAS_CACHE = False

try:
    from health_server import HealthServer, monitor as health_monitor, install_log_handler
    HAS_HEALTH = True
except ImportError:
    HAS_HEALTH = False


# ─────────────────────────────────────────────────────────────────
#  ESTADO GLOBAL (régimen anterior para detectar cambios)
# ─────────────────────────────────────────────────────────────────

_STATE_FILE = os.path.join("data", "agent_state.json")

def load_agent_state() -> dict:
    if os.path.exists(_STATE_FILE):
        try:
            with open(_STATE_FILE) as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_agent_state(state: dict):
    os.makedirs("data", exist_ok=True)
    with open(_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────
#  PIPELINE v2.1 COMPLETO
# ─────────────────────────────────────────────────────────────────

def run_daily_pipeline_v2(
    tickers:      Optional[list] = None,
    save_html:    bool = True,
    save_json:    bool = True,
    verbose:      bool = True,
    use_ml:       bool = True,
    use_cascade:  bool = True,
    use_telegram: bool = True,
    use_cache:    bool = True,
    retrain_ml:   bool = False,
) -> dict:
    """
    Pipeline completo v2.1 con caché local, health server y tests.
    """
    start_time = time.time()
    date_str   = datetime.now().strftime("%Y-%m-%d %H:%M")
    tickers    = tickers or IPSA_TICKERS
    state      = load_agent_state()

    logger.info("=" * 70)
    logger.info(f"IPSA AGENT v2.1 — {date_str}")
    logger.info("=" * 70)

    # ── INIT EXTENSIONES ─────────────────────────────────────────
    if HAS_HEALTH:
        install_log_handler()

    telegram = None
    if use_telegram and HAS_TELEGRAM:
        telegram = TelegramAlerter()
        if telegram.enabled:
            logger.info("[MAIN] Telegram configurado ✓")

    ml_pipeline = None
    if use_ml and HAS_ML:
        ml_pipeline = MLPipeline()
        logger.info(f"[MAIN] ML Pipeline {'cargado' if ml_pipeline.is_trained() else 'no entrenado aún'}")

    cascade = None
    if use_cascade and HAS_CASCADE:
        cascade = CascadeDataFetcher(
            cmf_token = os.environ.get("CMF_API_TOKEN", ""),
        )
        logger.info("[MAIN] Cascade data fetcher inicializado")

    price_cache = None
    if use_cache and HAS_CACHE:
        price_cache = PriceCache()
        logger.info(f"[MAIN] Price cache: {price_cache.status()['fresh']} tickers frescos en disco")

    # ── 1. DATOS ─────────────────────────────────────────────────
    logger.info("[PIPELINE] Paso 1/6: Ingesta de datos...")

    if cascade:
        cascade.prefetch()
        if price_cache:
            # Usar caché para tickers frescos, descargar solo los stale
            from extensions.ext_data_sources import fetch_yfinance_robust
            price_data = price_cache.fetch_missing(
                tickers  = tickers,
                fetcher  = fetch_yfinance_robust,
                period   = "2y",
                delay    = 0.1,
            )
            # Complementar con cascade para los que aún falten
            missing = [t for t in tickers if t not in price_data]
            if missing:
                cascade_data = {t: cascade.get_price_history(t) for t in missing}
                for t, df in cascade_data.items():
                    if df is not None:
                        price_cache.set(t, df)
                        price_data[t] = df
        else:
            price_data = cascade.get_all_histories(tickers)
    else:
        if price_cache:
            from extensions.ext_data_sources import fetch_yfinance_robust
            price_data = price_cache.fetch_missing(tickers, fetch_yfinance_robust, "2y")
        else:
            price_data = fetch_price_history(tickers, period="2y")

    if not price_data:
        logger.error("[PIPELINE] Sin datos de precios. Abortando.")
        if telegram:
            telegram.send_error_alert("Sin datos de precios. Pipeline abortado.")
        if HAS_HEALTH:
            health_monitor.record_error("Sin datos de precios. Pipeline abortado.")
        return {}

    logger.info(f"[PIPELINE] {len(price_data)} tickers con datos de precios")
    fundamentals    = fetch_all_fundamentals(list(price_data.keys()))
    macro           = fetch_macro_snapshot()
    ipsa_df         = fetch_ipsa_index_data()
    risk_free_rate  = macro.get("risk_free_rate", 0.05)

    # Enriquecer DY con CMF si está disponible
    trailing_yields = {}
    for ticker in price_data:
        ty = compute_trailing_dividend_yield(ticker, price_data)
        if ty is not None:
            trailing_yields[ticker] = ty

        if cascade:
            price_now = price_data[ticker]["Close"].iloc[-1] if not price_data[ticker].empty else 0
            cmf_dy = cascade.get_cmf_dividend_yield(ticker, float(price_now))
            if cmf_dy is not None:
                trailing_yields[ticker] = cmf_dy  # CMF prevalece
                fundamentals.setdefault(ticker, {})["dividend_yield"] = cmf_dy

    # ── 2. ML TRAINING (si aplica) ───────────────────────────────
    if ml_pipeline and retrain_ml:
        logger.info("[PIPELINE] Paso 2/6: Entrenamiento ML (modo completo)...")
        train_results = ml_pipeline.train_all(
            price_data, fundamentals, ipsa_df, risk_free_rate
        )
        if verbose:
            print_ml_metrics({"return_model": train_results.get("return_model", {})})
    else:
        logger.info("[PIPELINE] Paso 2/6: ML training omitido (usar --retrain)")

    # ── 3. PREDICCIONES ML ───────────────────────────────────────
    ml_predictions = {}
    if ml_pipeline and ml_pipeline.is_trained():
        logger.info("[PIPELINE] Paso 3/6: Generando predicciones ML...")
        ml_predictions = ml_pipeline.predict_all(
            price_data, fundamentals, ipsa_df, risk_free_rate
        )
        regime_ml = ml_predictions.get("__regime__", {})
        if regime_ml:
            logger.info(f"[ML] Régimen predicho: {regime_ml.get('regime_ml')} "
                       f"P(BULL)={regime_ml.get('regime_prob_bull',0.5):.1%}")
    else:
        logger.info("[PIPELINE] Paso 3/6: ML predictions omitidas (modelo no entrenado)")

    # ── 4. ANÁLISIS Y SCORING ─────────────────────────────────────
    logger.info("[PIPELINE] Paso 4/6: Análisis y scoring...")

    analyses = {}
    for ticker in price_data:
        analysis = analyze_ticker(
            ticker, price_data, fundamentals,
            risk_free_rate, trailing_yields.get(ticker),
        )
        # Enriquecer con predicción ML si existe
        if ticker in ml_predictions:
            analysis.update(ml_predictions[ticker])
        analyses[ticker] = analysis

    ranked_all = rank_all_tickers(analyses, risk_free_rate)
    top5       = select_top5(ranked_all)
    top5       = assign_portfolio_weights(top5)

    # ── 5. RÉGIMEN + CAMBIOS ──────────────────────────────────────
    logger.info("[PIPELINE] Paso 5/6: Régimen y cambios...")

    regime       = detect_market_regime(ipsa_df)

    # Fusionar régimen ML con régimen técnico
    if ml_predictions.get("__regime__"):
        regime["regime_ml"]        = ml_predictions["__regime__"].get("regime_ml")
        regime["regime_prob_bull"] = ml_predictions["__regime__"].get("regime_prob_bull")

    prev_tickers = get_previous_top5_tickers()
    changes      = detect_significant_changes(top5, prev_tickers)

    # Detectar cambio de régimen
    prev_regime  = state.get("last_regime")
    curr_regime  = regime.get("regime", "NEUTRAL")
    if prev_regime and prev_regime != curr_regime and telegram:
        telegram.send_regime_change(
            old_regime  = prev_regime,
            new_regime  = curr_regime,
            confidence  = str(regime.get("confidence", 0.5)),
        )

    # ── 6. REPORTES ───────────────────────────────────────────────
    logger.info("[PIPELINE] Paso 6/6: Generando reportes...")

    if verbose:
        print_daily_report(top5, ranked_all, macro, regime, changes, date_str)
        if ml_predictions:
            _print_ml_summary(top5, ml_predictions)

    html_path = None
    if save_html:
        html = generate_html_report(top5, ranked_all, macro, regime, changes, date_str)
        # Inyectar columna ML en el HTML si hay predicciones
        if ml_predictions:
            html = _inject_ml_into_html(html, ml_predictions)
        html_path = save_html_report(html, date_str)

    if save_json:
        save_json_report(top5, ranked_all, macro, regime, changes, date_str)
        # Guardar predicciones ML por separado
        if ml_predictions:
            _save_ml_predictions(ml_predictions, date_str)

    # Persistir decisión
    if not top5.empty:
        save_decision(top5, macro, regime, date_str)

    # ── TELEGRAM ──────────────────────────────────────────────────
    if telegram and telegram.enabled:
        telegram.send_daily_report(
            top5       = top5,
            macro      = macro,
            regime     = regime,
            changes    = changes,
            date_str   = date_str,
            ml_preds   = ml_predictions or None,
            html_path  = html_path,
        )
        if changes.get("changed"):
            telegram.send_top5_change_alert(changes)

    # ── ESTADO ────────────────────────────────────────────────────
    elapsed = time.time() - start_time
    top5_tickers = top5["ticker"].tolist() if not top5.empty else []

    save_agent_state({
        "last_run":     date_str,
        "last_regime":  curr_regime,
        "last_top5":    top5_tickers,
        "ml_trained":   ml_pipeline.is_trained() if ml_pipeline else False,
    })

    # Registrar en health monitor
    if HAS_HEALTH:
        health_monitor.record_run(
            ok           = not top5.empty,
            duration_s   = elapsed,
            top5_tickers = top5_tickers,
            regime       = curr_regime,
            usdclp       = macro.get("usdclp") or 0.0,
        )
        if price_cache:
            health_monitor.update_cache(price_cache.status())
        if ml_pipeline:
            health_monitor.update_ml(ml_pipeline.is_trained(), ml_pipeline.get_metrics())

    logger.info(f"[PIPELINE] Completado en {elapsed:.1f}s | Top5: {top5_tickers}")

    return {
        "top5":          top5,
        "ranked_all":    ranked_all,
        "macro":         macro,
        "regime":        regime,
        "changes":       changes,
        "ml_predictions": ml_predictions,
        "html_path":     html_path,
    }


# ─────────────────────────────────────────────────────────────────
#  HELPERS PRIVADOS
# ─────────────────────────────────────────────────────────────────

def _print_ml_summary(top5: pd.DataFrame, ml_preds: dict):
    """Imprime resumen ML en consola."""
    print("\n🤖 PREDICCIONES ML (21 días hábiles)")
    print("─" * 60)
    for _, row in top5.iterrows():
        t    = row.get("ticker", "")
        pred = ml_preds.get(t, {})
        if pred:
            ret  = pred.get("predicted_return_21d", 0)
            conf = pred.get("confidence", "?")
            sig  = pred.get("signal_ml", "")
            print(f"  {t:<16} {ret:+.1f}% ({conf}) — {sig}")
    regime_ml = ml_preds.get("__regime__", {})
    if regime_ml:
        print(f"\n  Régimen ML: {regime_ml.get('regime_ml')} "
              f"[P(BULL)={regime_ml.get('regime_prob_bull',0.5):.1%}]")


def _inject_ml_into_html(html: str, ml_preds: dict) -> str:
    """Inyecta sección de predicciones ML en el HTML generado."""
    ml_block = "<h2>🤖 Predicciones ML (21 días)</h2><div class='ml-grid'>"
    for t, pred in ml_preds.items():
        if t == "__regime__":
            continue
        ret  = pred.get("predicted_return_21d", 0)
        conf = pred.get("confidence", "?")
        sig  = pred.get("signal_ml", "")
        cls  = "positive" if ret > 0 else "negative"
        ml_block += (
            f"<div class='metric'><span>{t}</span>"
            f"<strong class='{cls}'>{ret:+.1f}%</strong>"
            f"<small>{conf} — {sig}</small></div>"
        )
    # Régimen ML
    r_ml = ml_preds.get("__regime__", {})
    if r_ml:
        r_name = r_ml.get("regime_ml", "N/D")
        r_prob = r_ml.get("regime_prob_bull", 0.5)
        ml_block += (
            f"<div class='metric'><span>Régimen ML</span>"
            f"<strong>{r_name}</strong><small>P(BULL)={r_prob:.1%}</small></div>"
        )
    ml_block += "</div>"
    return html.replace("</body>", f"{ml_block}</body>")


def _save_ml_predictions(ml_preds: dict, date_str: str):
    """Guarda predicciones ML en disco."""
    os.makedirs("data", exist_ok=True)
    fname = os.path.join("data", f"ml_preds_{date_str[:10]}.json")
    with open(fname, "w") as f:
        json.dump(ml_preds, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────
#  CLI v2.1
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="🇨🇱 IPSA Agent v2.1 — Gestor Autónomo con ML + Telegram + Cache",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python main_v2.py                          # Pipeline completo
  python main_v2.py --no-ml                  # Sin ML (rápido, ~30s)
  python main_v2.py --retrain                # Reentrenar modelo ML
  python main_v2.py --mode backtest          # Backtesting histórico
  python main_v2.py --mode test              # Ejecutar suite de tests
  python main_v2.py --mode cache-status      # Estado del caché local
  python main_v2.py --mode cache-clear       # Limpiar caché
  python main_v2.py --mode data-status       # Verificar fuentes de datos
  python main_v2.py --mode health            # Iniciar health server
  python main_v2.py --mode setup-telegram    # Generar .env para Telegram
  python main_v2.py --no-ml --no-telegram    # Solo análisis clásico
        """
    )

    parser.add_argument(
        "--mode",
        choices=["daily", "backtest", "history", "ml-train", "test",
                 "cache-status", "cache-clear", "data-status",
                 "health", "setup-telegram", "setup-env"],
        default="daily",
    )
    parser.add_argument("--start",        default=None)
    parser.add_argument("--end",          default=None)
    parser.add_argument("--port",         type=int, default=8765, help="Puerto del health server")
    parser.add_argument("--no-html",      action="store_true")
    parser.add_argument("--no-json",      action="store_true")
    parser.add_argument("--no-ml",        action="store_true")
    parser.add_argument("--no-telegram",  action="store_true")
    parser.add_argument("--no-cascade",   action="store_true")
    parser.add_argument("--no-cache",     action="store_true", help="Deshabilitar caché local")
    parser.add_argument("--retrain",      action="store_true", help="Reentrenar modelo ML")
    parser.add_argument("--quiet",        action="store_true")

    args = parser.parse_args()

    if args.mode == "daily":
        run_daily_pipeline_v2(
            save_html    = not args.no_html,
            save_json    = not args.no_json,
            verbose      = not args.quiet,
            use_ml       = not args.no_ml and HAS_ML,
            use_cascade  = not args.no_cascade and HAS_CASCADE,
            use_telegram = not args.no_telegram and HAS_TELEGRAM,
            use_cache    = not args.no_cache and HAS_CACHE,
            retrain_ml   = args.retrain,
        )

    elif args.mode == "backtest":
        if HAS_CACHE and not args.no_cache:
            from price_cache import PriceCache
            from extensions.ext_data_sources import fetch_yfinance_robust
            cache      = PriceCache()
            price_data = cache.fetch_missing(IPSA_TICKERS, fetch_yfinance_robust, "2y")
        else:
            price_data = fetch_price_history(IPSA_TICKERS, period="2y")
        fundamentals = fetch_all_fundamentals(list(price_data.keys()))
        macro        = fetch_macro_snapshot()
        engine = BacktestEngine(
            price_data      = price_data,
            fundamentals    = fundamentals,
            risk_free_rate  = macro.get("risk_free_rate", 0.05),
            initial_capital = 10_000_000,
        )
        metrics = engine.run(start_date=args.start, end_date=args.end)
        print_backtest_summary(metrics)
        if HAS_TELEGRAM and not args.no_telegram:
            alerter = TelegramAlerter()
            if alerter.enabled:
                alerter.send_backtest_results(metrics)

    elif args.mode == "ml-train":
        if not HAS_ML:
            print("❌ XGBoost no instalado: pip install xgboost scikit-learn")
            return
        if HAS_CACHE and not args.no_cache:
            from price_cache import PriceCache
            from extensions.ext_data_sources import fetch_yfinance_robust
            price_data = PriceCache().fetch_missing(IPSA_TICKERS, fetch_yfinance_robust, "2y")
        else:
            price_data = fetch_price_history(IPSA_TICKERS, period="2y")
        fundamentals = fetch_all_fundamentals(list(price_data.keys()))
        ipsa_df      = fetch_ipsa_index_data()
        macro        = fetch_macro_snapshot()
        ml           = MLPipeline()
        results      = ml.train_all(price_data, fundamentals, ipsa_df,
                                    macro.get("risk_free_rate", 0.05))
        print_ml_metrics({"return_model": results.get("return_model", {})})

    elif args.mode == "test":
        print("\n🧪 Ejecutando suite de tests...\n")
        import subprocess
        ret = subprocess.run([sys.executable, "-m", "pytest", "tests.py", "-v", "--tb=short"])
        sys.exit(ret.returncode)

    elif args.mode == "cache-status":
        if HAS_CACHE:
            from price_cache import PriceCache
            PriceCache().print_status()
        else:
            print("❌ pyarrow no instalado: pip install pyarrow")

    elif args.mode == "cache-clear":
        if HAS_CACHE:
            from price_cache import PriceCache
            c = PriceCache()
            c.print_status()
            print("\n⚠️  ¿Limpiar todo el caché? [s/N]: ", end="")
            if input().strip().lower() == "s":
                c.invalidate_all()
                print("✅ Caché eliminado.")
            else:
                print("Cancelado.")
        else:
            print("❌ pyarrow no instalado: pip install pyarrow")

    elif args.mode == "data-status":
        if HAS_CASCADE:
            status = get_data_source_status()
            print("\n📡 ESTADO FUENTES DE DATOS")
            print("─" * 40)
            for name, info in status.items():
                ok   = "✅" if info.get("ok") else "❌"
                code = info.get("code", info.get("error", "?"))
                print(f"  {ok} {name:<10} {code}")
            if HAS_CACHE:
                from price_cache import PriceCache
                PriceCache().print_status()
        else:
            print("❌ Extensión cascade no disponible")

    elif args.mode == "health":
        if HAS_HEALTH:
            from health_server import HealthServer, install_log_handler
            install_log_handler()
            server = HealthServer(port=args.port)
            server.start()
            print(f"\n✅ Health server → http://localhost:{args.port}")
            print("   /health  /status  /metrics  /last-report")
            print("   Ctrl+C para detener\n")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                server.stop()
        else:
            print("❌ health_server.py no encontrado")

    elif args.mode in ("setup-telegram", "setup-env"):
        if HAS_TELEGRAM:
            from extensions.ext_telegram import setup_telegram_env
            setup_telegram_env()
        else:
            print("❌ requests no instalado")

    elif args.mode == "history":
        history = load_history()
        if not history:
            print("📭 Sin historial de decisiones aún.")
        else:
            print(f"\n📚 Historial: {len(history)} sesiones\n")
            print(f"  {'Fecha':<22} {'Régimen':<10} {'Top 5'}")
            print("  " + "─" * 70)
            for entry in history[-15:]:
                tickers_str = ", ".join(entry.get("tickers", []))
                regime_str  = entry.get("regime", {}).get("regime", "N/D")
                emoji = {"BULL":"🐂","BEAR":"🐻","NEUTRAL":"⚖️"}.get(regime_str, "")
                print(f"  {entry['date']:22s} {emoji} {regime_str:<8} {tickers_str}")


if __name__ == "__main__":
    main()
