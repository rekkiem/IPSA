"""
IPSA Agent — Suite de Tests Unitarios
Cubre: parsers de datos, serialización JSON, scoring, kill conditions, caché.

Ejecutar:
    cd ipsa_agent
    python -m pytest tests.py -v
    python -m pytest tests.py -v --tb=short   # traceback corto
"""

import json
import math
import os
import sys
import tempfile
import unittest
import warnings
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
warnings.filterwarnings("ignore")


# ─────────────────────────────────────────────────────────────────
#  FIXTURES
# ─────────────────────────────────────────────────────────────────

def make_price_df(n=300, base=100.0, trend=0.10, vol=0.18, seed=42) -> pd.DataFrame:
    """Genera DataFrame de precios sintético reproducible."""
    np.random.seed(seed)
    r = np.random.normal(trend / 252, vol / np.sqrt(252), n)
    p = base * np.exp(np.cumsum(r))
    idx = pd.date_range(end=datetime.now(), periods=n, freq="B")
    return pd.DataFrame({"Close": p, "Open": p * 0.999, "High": p * 1.003,
                         "Low": p * 0.997, "Volume": 100_000}, index=idx)


def make_fund(roe=0.18, de=0.85, eg=0.10, pr=0.55, dy=0.055) -> dict:
    return {"roe": roe, "debt_to_equity": de, "earnings_growth": eg,
            "payout_ratio": pr, "dividend_yield": dy, "current_ratio": 1.8}


# ─────────────────────────────────────────────────────────────────
#  TEST: SERIALIZACIÓN JSON (crítico — NaN destruye el dashboard)
# ─────────────────────────────────────────────────────────────────

class TestJsonSerialization(unittest.TestCase):
    """Verifica que el JSON generado es siempre parseable."""

    def setUp(self):
        from report_generator import save_json_report
        self.save_json = save_json_report

    def _build_df_with_nan(self) -> pd.DataFrame:
        return pd.DataFrame({
            "ticker":         ["CHILE.SN", "TEST.SN"],
            "score":          [0.48, float("nan")],
            "dividend_yield": [0.058, float("nan")],
            "momentum_3m":    [8.5, float("inf")],
            "momentum_6m":    [12.0, float("-inf")],
            "rsi":            [50.0, float("nan")],
            "max_drawdown":   [-8.5, float("nan")],
            "signal":         ["🟢 COMPRAR", "🟡 ESPERAR"],
            "is_excluded":    [False, True],
            "kill_reasons":   [[], ["test"]],
            "thesis":         ["tesis1", "tesis2"],
            "factor_dividend":[0.70, float("nan")],
            "factor_quality": [0.68, float("nan")],
            "factor_momentum":[0.62, float("nan")],
            "factor_risk":    [0.75, float("nan")],
            "weight_pct":     [30.0, float("nan")],
        })

    def test_nan_serialized_as_null(self):
        """NaN y Inf en DataFrame → null en JSON."""
        import config as cfg
        df = self._build_df_with_nan()
        with tempfile.TemporaryDirectory() as td:
            orig = cfg.REPORTS_DIR
            cfg.REPORTS_DIR = td
            fname = self.save_json(df, df.copy(),
                                   {"usdclp": 929.21, "risk_free_rate": 0.05, "inflation": 0.048},
                                   {"regime": "BULL"}, {"changed": False}, "2026-01-01 09:00")
            cfg.REPORTS_DIR = orig
            raw = open(fname).read()
            self.assertNotIn("NaN", raw, "JSON contiene literal NaN")
            self.assertNotIn(": inf", raw.lower(), "JSON contiene Infinity")
            parsed = json.loads(raw)   # debe ser parseable
            top5 = parsed["top5"]
            # El valor nan debe haberse convertido a null
            self.assertIsNone(top5[1]["score"], "float(nan) debe ser null en JSON")
            self.assertIsNone(top5[1]["momentum_3m"], "float(inf) debe ser null en JSON")

    def test_clean_values_are_preserved(self):
        """Valores normales no deben corromperse."""
        import config as cfg
        df = pd.DataFrame({
            "ticker": ["CHILE.SN"], "score": [0.485],
            "dividend_yield": [0.058], "rsi": [50.0],
            "signal": ["🟢 COMPRAR"], "is_excluded": [False],
            "kill_reasons": [[]], "thesis": ["tesis"],
            "factor_dividend":[0.72],"factor_quality":[0.68],
            "factor_momentum":[0.62],"factor_risk":[0.75],
            "weight_pct":[29.8],
        })
        with tempfile.TemporaryDirectory() as td:
            orig = cfg.REPORTS_DIR
            cfg.REPORTS_DIR = td
            fname = self.save_json(df, df.copy(),
                                   {"usdclp": 929.21}, {}, {}, "2026-01-01 09:00")
            cfg.REPORTS_DIR = orig
            parsed = json.loads(open(fname).read())
            row = parsed["top5"][0]
            self.assertAlmostEqual(row["score"], 0.485, places=3)
            self.assertAlmostEqual(row["dividend_yield"], 0.058, places=4)


# ─────────────────────────────────────────────────────────────────
#  TEST: FACTORES DE ANÁLISIS
# ─────────────────────────────────────────────────────────────────

class TestFactors(unittest.TestCase):

    def setUp(self):
        from analysis_engine import (factor_dividend_arbitrage, factor_quality,
                                     factor_momentum, factor_risk)
        self.fda = factor_dividend_arbitrage
        self.fq  = factor_quality
        self.fm  = factor_momentum
        self.fr  = factor_risk
        self.df  = make_price_df()

    # ── Dividend ──
    def test_div_spread_positive(self):
        """DY > TPM debe producir spread positivo."""
        r = self.fda(0.065, 0.05)
        self.assertGreater(r["spread"], 0)
        self.assertGreater(r["factor_dividend"], 0.3)  # > neutro

    def test_div_spread_negative(self):
        """DY < TPM debe producir score bajo."""
        r = self.fda(0.02, 0.05)
        self.assertLess(r["spread"], 0)
        self.assertLess(r["factor_dividend"], 0.35)

    def test_div_yield_zero(self):
        """Sin dividendo → factor bajo pero no error."""
        r = self.fda(0.0, 0.05)
        self.assertIsNotNone(r["factor_dividend"])
        self.assertGreaterEqual(r["factor_dividend"], 0.0)

    # ── Quality ──
    def test_quality_high_roe_low_debt(self):
        """ROE alto + D/E bajo → score de calidad alto."""
        r = self.fq(roe=0.25, debt_to_equity=0.30, earnings_growth=0.15,
                    payout_ratio=0.45, current_ratio=2.0)
        self.assertGreater(r["factor_quality"], 0.70)

    def test_quality_negative_roe(self):
        """ROE negativo → score bajo."""
        r = self.fq(roe=-0.05, debt_to_equity=2.0, earnings_growth=-0.30,
                    payout_ratio=0.85, current_ratio=0.9)
        self.assertLess(r["factor_quality"], 0.40)

    def test_quality_with_none_values(self):
        """None en cualquier campo → usa valor por defecto, no error."""
        r = self.fq(roe=None, debt_to_equity=None, earnings_growth=None,
                    payout_ratio=None, current_ratio=None)
        self.assertIn("factor_quality", r)
        self.assertIsNotNone(r["factor_quality"])

    def test_quality_bank_high_de_not_penalized(self):
        """Bancos con D/E 8-10x (Basilea III normal) deben tener score >= 0.60."""
        # BSANTANDER: D/E=8.5, ROE=19.8% — debe rankear bien
        r = self.fq(roe=0.198, debt_to_equity=8.5, earnings_growth=0.12,
                    payout_ratio=0.58, current_ratio=None, is_bank=True)
        self.assertGreaterEqual(r["factor_quality"], 0.60,
            "Banco con D/E regulatorio 8.5x no debe ser penalizado")

    def test_quality_nonbank_high_de_penalized(self):
        """No-banco con D/E 8.5x sí debe ser penalizado."""
        r = self.fq(roe=0.10, debt_to_equity=8.5, earnings_growth=0.05,
                    payout_ratio=0.60, current_ratio=1.2, is_bank=False)
        self.assertLess(r["factor_quality"], 0.40,
            "No-banco con D/E 8.5x debe tener score bajo")

    # ── Momentum ──
    def test_momentum_basic_fields(self):
        """factor_momentum devuelve todos los campos esperados."""
        r = self.fm(self.df)
        for field in ["momentum_3m", "momentum_6m", "rsi", "factor_momentum",
                      "above_sma50", "macd_histogram", "bb_position"]:
            self.assertIn(field, r)

    def test_momentum_rsi_range(self):
        """RSI debe estar entre 0 y 100."""
        r = self.fm(self.df)
        self.assertGreaterEqual(r["rsi"], 0)
        self.assertLessEqual(r["rsi"], 100)

    def test_momentum_empty_df(self):
        """DataFrame vacío o insuficiente → retorna dict con factor neutral."""
        r = self.fm(None)
        self.assertIn("factor_momentum", r)
        r2 = self.fm(make_price_df(n=5))
        self.assertIn("factor_momentum", r2)

    def test_momentum_score_range(self):
        """factor_momentum debe estar entre 0 y 1."""
        r = self.fm(self.df)
        self.assertGreaterEqual(r["factor_momentum"], 0.0)
        self.assertLessEqual(r["factor_momentum"], 1.0)

    # ── Risk ──
    def test_risk_fields(self):
        r = self.fr(self.df)
        for field in ["max_drawdown", "volatility_annual", "sharpe_ratio", "factor_risk"]:
            self.assertIn(field, r)

    def test_risk_drawdown_negative(self):
        """Max drawdown siempre debe ser <= 0."""
        r = self.fr(self.df)
        self.assertLessEqual(r["max_drawdown"], 0)

    def test_risk_score_range(self):
        r = self.fr(self.df)
        self.assertGreaterEqual(r["factor_risk"], 0.0)
        self.assertLessEqual(r["factor_risk"], 1.0)


# ─────────────────────────────────────────────────────────────────
#  TEST: KILL CONDITIONS (FILTROS)
# ─────────────────────────────────────────────────────────────────

class TestKillConditions(unittest.TestCase):

    def setUp(self):
        from scoring import apply_kill_conditions
        self.kc = apply_kill_conditions

    def test_high_dividend_yield_excluded(self):
        """DY > 25% debe excluir (trampa de dividendo evidente)."""
        excluded, reasons = self.kc({"dividend_yield": 0.30})
        self.assertTrue(excluded)
        self.assertTrue(any("DY" in r for r in reasons))

    def test_moderate_dividend_yield_not_excluded(self):
        """DY = 20% NO debe excluir — puede ser legítimo en mercado caído."""
        excluded, reasons = self.kc({"dividend_yield": 0.20})
        self.assertFalse(excluded, f"DY 20% no es trampa evidente: {reasons}")

    def test_high_payout_not_excluded(self):
        """
        Payout > 95-120% NO debe excluir.
        Ya es penalizado en factor_quality. Ocurre normalmente cuando
        una empresa paga dividendos de utilidades previas en año malo.
        """
        excluded, reasons = self.kc({"payout_ratio": 1.20})
        self.assertFalse(excluded, f"Payout 120% no debe excluir en crash de mercado: {reasons}")
        excluded2, _ = self.kc({"payout_ratio": 2.90})
        self.assertFalse(excluded2, "Payout extremo tampoco excluye — lo maneja el score")

    def test_high_debt_equity_excluded(self):
        """D/E > 4.0x debe excluir para no-bancos."""
        excluded, reasons = self.kc({"debt_to_equity": 5.0, "is_financial_sector": False})
        self.assertTrue(excluded)

    def test_moderate_debt_not_excluded(self):
        """D/E = 2.8x NO debe excluir — ya penalizado en quality score."""
        excluded, reasons = self.kc({"debt_to_equity": 2.8, "is_financial_sector": False})
        self.assertFalse(excluded, f"D/E 2.8x no debe excluir (ya en score): {reasons}")

    def test_bank_high_debt_not_excluded(self):
        """Banco con D/E 9x (Basilea III) NO debe ser excluido."""
        excluded, reasons = self.kc({
            "debt_to_equity": 9.0, "is_financial_sector": True,
            "dividend_yield": 0.058, "payout_ratio": 0.55,
            "rsi": 52, "momentum_3m": 5.0, "momentum_6m": 8.0,
        })
        self.assertFalse(excluded, f"Banco D/E 9x no debe excluirse: {reasons}")

    def test_rsi_overbought_excluded(self):
        """RSI > 88 debe excluir (sobrecompra extrema)."""
        excluded, reasons = self.kc({"rsi": 90})
        self.assertTrue(excluded)

    def test_rsi_80_not_excluded(self):
        """RSI = 80-85 NO debe excluir — ocurre frecuentemente en bull runs."""
        excluded, reasons = self.kc({"rsi": 82})
        self.assertFalse(excluded, f"RSI 82 no debe excluir: {reasons}")

    def test_severe_momentum_not_excluded(self):
        """
        Momentum bajista sistémico NO debe excluir.
        En crash de mercado (Trump tariffs Abril 2026) TODOS los stocks
        tienen m3 < -20% y m6 < -25% → kill condition sistémica vacía el Top5.
        El factor_momentum ya penaliza esto en el score.
        """
        excluded, reasons = self.kc({"momentum_3m": -22.0, "momentum_6m": -28.0})
        self.assertFalse(excluded,
            "Momentum negativo NO debe excluir — ya penalizado en factor. "
            "En crash sistémico (tariff shock) eliminaría TODOS los tickers.")

    def test_normal_stock_not_excluded(self):
        """Acción normal no debe ser excluida."""
        good = {
            "dividend_yield": 0.055, "payout_ratio": 0.58,
            "debt_to_equity": 0.85,  "rsi": 52,
            "momentum_3m": 3.5,       "momentum_6m": 8.2,
        }
        excluded, reasons = self.kc(good)
        self.assertFalse(excluded, f"No debería excluirse: {reasons}")

    def test_none_values_not_excluded(self):
        """None en todos los campos → no debe excluir."""
        excluded, reasons = self.kc({})
        self.assertFalse(excluded)


# ─────────────────────────────────────────────────────────────────
#  TEST: SCORE UNIFICADO
# ─────────────────────────────────────────────────────────────────

class TestUnifiedScore(unittest.TestCase):

    def setUp(self):
        from scoring import compute_unified_score
        self.score = compute_unified_score

    def _analysis(self, div=0.60, qual=0.65, mom=0.55, risk=0.70) -> dict:
        return {"factor_dividend": div, "factor_quality": qual,
                "factor_momentum": mom, "factor_risk": risk}

    def test_score_range(self):
        """Score debe estar entre 0 y 1."""
        s = self.score(self._analysis())
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 1.0)

    def test_score_increases_with_better_factors(self):
        """Factores mejores → score más alto."""
        low  = self.score(self._analysis(div=0.2, qual=0.2, mom=0.2, risk=0.2))
        high = self.score(self._analysis(div=0.9, qual=0.9, mom=0.9, risk=0.9))
        self.assertGreater(high, low)

    def test_score_with_none_factors(self):
        """None en factores → usa 0.3 por defecto, no error."""
        s = self.score({"factor_dividend": None, "factor_quality": None,
                        "factor_momentum": None, "factor_risk": None})
        self.assertIsNotNone(s)
        self.assertGreaterEqual(s, 0.0)


# ─────────────────────────────────────────────────────────────────
#  TEST: PRICE CACHE
# ─────────────────────────────────────────────────────────────────

class TestPriceCache(unittest.TestCase):

    def setUp(self):
        from price_cache import PriceCache
        self.tmpdir = tempfile.mkdtemp()
        self.cache  = PriceCache(cache_dir=self.tmpdir, stale_hours=1)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_set_and_get(self):
        """Guardar y leer un DataFrame del caché."""
        df = make_price_df(n=100)
        self.cache.set("CHILE.SN", df)
        result = self.cache.get("CHILE.SN")
        self.assertIsNotNone(result)
        self.assertGreater(len(result), 50)

    def test_stale_returns_none(self):
        """Después de expirar, get() debe retornar None."""
        from price_cache import PriceCache
        cache = PriceCache(cache_dir=self.tmpdir, stale_hours=0)  # stale inmediato
        cache.set("TEST.SN", make_price_df(n=50))
        result = cache.get("TEST.SN")
        self.assertIsNone(result, "Caché con stale_hours=0 debe retornar None")

    def test_missing_ticker_returns_none(self):
        """Ticker no cacheado → None."""
        self.assertIsNone(self.cache.get("NOEXISTE.SN"))

    def test_nan_values_handled(self):
        """DataFrame con NaN se guarda sin error."""
        df = make_price_df(n=50)
        df.loc[df.index[:5], "Close"] = float("nan")
        self.cache.set("NAN.SN", df)  # no debe lanzar excepción
        result = self.cache.get("NAN.SN")
        self.assertIsNotNone(result)

    def test_get_or_fetch_uses_cache(self):
        """get_or_fetch no llama al fetcher si el caché es fresco."""
        df = make_price_df(n=100)
        self.cache.set("CHILE.SN", df)
        calls = []
        def mock_fetcher(ticker, period): calls.append(ticker); return None
        result = self.cache.get_or_fetch("CHILE.SN", mock_fetcher)
        self.assertEqual(calls, [], "Fetcher no debe llamarse con caché fresco")
        self.assertIsNotNone(result)

    def test_get_or_fetch_calls_fetcher_when_missing(self):
        """get_or_fetch llama al fetcher cuando no hay caché."""
        expected_df = make_price_df(n=50)
        def mock_fetcher(ticker, period): return expected_df
        result = self.cache.get_or_fetch("NUEVO.SN", mock_fetcher)
        self.assertIsNotNone(result)
        # Ahora debe estar en caché
        cached = self.cache.get("NUEVO.SN")
        self.assertIsNotNone(cached)

    def test_status(self):
        """status() retorna dict con campos esperados."""
        self.cache.set("A.SN", make_price_df())
        s = self.cache.status()
        self.assertIn("total_cached", s)
        self.assertIn("fresh", s)
        self.assertIn("disk_mb", s)
        self.assertGreaterEqual(s["total_cached"], 1)


# ─────────────────────────────────────────────────────────────────
#  TEST: DATA SOURCE UTILITIES
# ─────────────────────────────────────────────────────────────────

class TestDataSourceUtils(unittest.TestCase):

    def setUp(self):
        from extensions.ext_data_sources import _parse_float, _safe_float
        self.parse_float = _parse_float
        self.safe_float  = _safe_float

    def test_parse_float_normal(self):
        self.assertAlmostEqual(self.parse_float(1.23), 1.23)
        self.assertAlmostEqual(self.parse_float("1.23"), 1.23)
        self.assertAlmostEqual(self.parse_float("1,23"), 1.23)

    def test_parse_float_nan_returns_none(self):
        self.assertIsNone(self.parse_float(float("nan")))
        self.assertIsNone(self.parse_float(float("inf")))
        self.assertIsNone(self.parse_float(float("-inf")))

    def test_parse_float_invalid_returns_none(self):
        self.assertIsNone(self.parse_float("N/A"))
        self.assertIsNone(self.parse_float("—"))
        self.assertIsNone(self.parse_float(None))
        self.assertIsNone(self.parse_float(""))

    def test_safe_float_finds_value(self):
        data = {"ultimo": 1250.5, "otro": "no"}
        r = self.safe_float(data, ["precio", "ultimo", "last"])
        self.assertAlmostEqual(r, 1250.5)

    def test_safe_float_returns_none_when_missing(self):
        r = self.safe_float({}, ["precio", "ultimo"])
        self.assertIsNone(r)


# ─────────────────────────────────────────────────────────────────
#  TEST: TICKER CONFIG
# ─────────────────────────────────────────────────────────────────

class TestConfig(unittest.TestCase):

    def test_no_delisted_tickers(self):
        """Verificar que los tickers delisted no estén en la lista."""
        from config import IPSA_TICKERS
        delisted = ["SECURITY.SN", "CONCHA.SN", "SMCHILE.SN", "NUEVAPOLAR.SN", "HITES.SN", "ECL.SN"]
        for t in delisted:
            self.assertNotIn(t, IPSA_TICKERS, f"{t} delisted pero sigue en IPSA_TICKERS")

    def test_tickers_have_sn_suffix(self):
        """Todos los tickers deben terminar en .SN."""
        from config import IPSA_TICKERS
        for t in IPSA_TICKERS:
            self.assertTrue(t.endswith(".SN"), f"{t} no tiene sufijo .SN")

    def test_minimum_ticker_count(self):
        """Debe haber al menos 15 tickers activos."""
        from config import IPSA_TICKERS
        self.assertGreaterEqual(len(IPSA_TICKERS), 15)

    def test_thresholds_calibrated(self):
        """Thresholds de señal calibrados para datos reales."""
        from config import SCORE_HIGH_THRESHOLD, SCORE_MEDIUM_THRESHOLD
        # Valores razonables para datos reales del IPSA
        self.assertLessEqual(SCORE_HIGH_THRESHOLD, 0.55)
        self.assertGreaterEqual(SCORE_HIGH_THRESHOLD, 0.30)
        self.assertLess(SCORE_MEDIUM_THRESHOLD, SCORE_HIGH_THRESHOLD)

    def test_kill_conditions_not_too_strict(self):
        """Kill conditions no deben ser tan estrictas que excluyan todo."""
        from config import MAX_DIVIDEND_YIELD, MAX_PAYOUT_RATIO, MAX_DEBT_EQUITY, RSI_OVERBOUGHT
        self.assertGreaterEqual(MAX_DIVIDEND_YIELD, 0.15)  # al menos 15%
        self.assertGreaterEqual(MAX_PAYOUT_RATIO, 0.90)    # al menos 90%
        self.assertGreaterEqual(MAX_DEBT_EQUITY, 2.0)       # al menos 2x
        self.assertGreaterEqual(RSI_OVERBOUGHT, 75)         # al menos 75


# ─────────────────────────────────────────────────────────────────
#  INTEGRATION TEST: Pipeline completo con datos mock
# ─────────────────────────────────────────────────────────────────

class TestPipelineIntegration(unittest.TestCase):
    """Test de integración: análisis → scoring → Top 5."""

    @classmethod
    def setUpClass(cls):
        """Preparar datos mock una sola vez para todos los tests."""
        from analysis_engine import analyze_ticker
        from scoring import rank_all_tickers, select_top5, assign_portfolio_weights

        np.random.seed(123)
        tickers = ["CHILE.SN","BSANTANDER.SN","AGUAS-A.SN","BCI.SN","CCU.SN",
                   "COLBUN.SN","COPEC.SN","ENELAM.SN","MALLPLAZA.SN","PARAUCO.SN"]
        funds = {
            "CHILE.SN":      make_fund(roe=0.221, de=0.72,  eg=0.09,  pr=0.52, dy=0.058),
            "BSANTANDER.SN": make_fund(roe=0.198, de=0.85,  eg=0.12,  pr=0.58, dy=0.062),
            "AGUAS-A.SN":    make_fund(roe=0.142, de=0.98,  eg=0.04,  pr=0.78, dy=0.055),
            "BCI.SN":        make_fund(roe=0.176, de=0.90,  eg=0.07,  pr=0.56, dy=0.051),
            "CCU.SN":        make_fund(roe=0.111, de=0.38,  eg=0.05,  pr=0.62, dy=0.036),
            "COLBUN.SN":     make_fund(roe=0.103, de=0.55,  eg=0.08,  pr=0.60, dy=0.042),
            "COPEC.SN":      make_fund(roe=0.087, de=0.62,  eg=-0.05, pr=0.61, dy=0.031),
            "ENELAM.SN":     make_fund(roe=0.094, de=0.76,  eg=0.02,  pr=0.71, dy=0.045),
            "MALLPLAZA.SN":  make_fund(roe=0.088, de=1.05,  eg=0.06,  pr=0.72, dy=0.044),
            "PARAUCO.SN":    make_fund(roe=0.095, de=0.92,  eg=0.11,  pr=0.68, dy=0.048),
        }
        price_data = {t: make_price_df(n=350, base=100+i*10, trend=0.08) for i, t in enumerate(tickers)}
        for t, d in funds.items():
            if t in price_data:
                funds[t]["name"] = t
        analyses = {t: analyze_ticker(t, price_data, funds, 0.05) for t in tickers}
        cls.ranked = rank_all_tickers(analyses, 0.05)
        cls.top5   = select_top5(cls.ranked)
        cls.top5   = assign_portfolio_weights(cls.top5)

    def test_top5_has_5_entries(self):
        """Debe producir exactamente 5 acciones."""
        self.assertEqual(len(self.top5), 5)

    def test_top5_ranked_by_score(self):
        """Top 5 debe estar ordenado de mayor a menor score."""
        scores = self.top5["score"].tolist()
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_top5_no_excluded(self):
        """Ninguna acción excluida debe aparecer en el Top 5."""
        self.assertFalse(self.top5["is_excluded"].any())

    def test_portfolio_weights_sum_to_100(self):
        """Pesos de portafolio deben sumar ~100%."""
        total = self.top5["weight_pct"].sum()
        self.assertAlmostEqual(total, 100.0, delta=5.0)

    def test_all_scores_in_range(self):
        """Todos los scores entre 0 y 1."""
        for s in self.top5["score"]:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 1.0)

    def test_signals_valid(self):
        """Señales deben ser uno de los tres valores válidos."""
        from config import SIGNAL_BUY, SIGNAL_WAIT, SIGNAL_AVOID
        valid = {SIGNAL_BUY, SIGNAL_WAIT, SIGNAL_AVOID}
        for sig in self.top5["signal"]:
            self.assertIn(sig, valid, f"Señal inválida: {sig}")

    def test_ranked_all_contains_top5(self):
        """Todos los tickers del Top 5 deben aparecer en el ranking completo."""
        all_tickers = set(self.ranked["ticker"].tolist())
        top5_tickers = set(self.top5["ticker"].tolist())
        self.assertTrue(top5_tickers.issubset(all_tickers))


# ─────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Formateo colorido en consola
    import unittest
    loader  = unittest.TestLoader()
    suite   = loader.discover(start_dir=os.path.dirname(__file__), pattern="tests.py")
    runner  = unittest.TextTestRunner(verbosity=2, failfast=False)
    result  = runner.run(suite)

    print(f"\n{'='*60}")
    print(f"  Tests:   {result.testsRun}")
    print(f"  OK:      {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  Fallos:  {len(result.failures)}")
    print(f"  Errores: {len(result.errors)}")
    print(f"{'='*60}")

    sys.exit(0 if result.wasSuccessful() else 1)
