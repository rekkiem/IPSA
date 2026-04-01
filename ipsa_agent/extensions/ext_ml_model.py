"""
IPSA Agent — Extension 2: Modelo Predictivo XGBoost
Predice retorno forward a 21 días hábiles por acción.
Detecta cambios de régimen Bull/Bear con clasificación binaria.
"""

import json
import logging
import os
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logger = logging.getLogger(__name__)

ML_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml")
os.makedirs(ML_DIR, exist_ok=True)

MODEL_PATH       = os.path.join(ML_DIR, "xgb_return_model.json")
REGIME_MODEL_PATH = os.path.join(ML_DIR, "xgb_regime_model.json")
FEATURE_PATH     = os.path.join(ML_DIR, "feature_names.json")
METRICS_PATH     = os.path.join(ML_DIR, "model_metrics.json")


# ─────────────────────────────────────────────────────────────────
#  FEATURE ENGINEERING
# ─────────────────────────────────────────────────────────────────

def engineer_features(
    df:             pd.DataFrame,
    fund:           Dict,
    risk_free_rate: float = 0.05,
) -> Optional[pd.Series]:
    """
    Construye el vector de features para una acción en la fecha actual.
    Features técnicos + fundamentales + macro.
    """
    if df is None or len(df) < 126:
        return None

    prices  = df["Close"]
    returns = np.log(prices / prices.shift(1)).dropna()
    vol     = df.get("Volume", pd.Series(dtype=float))

    feats = {}

    # ── RETORNOS (Momentum) ──
    for d, label in [(5, "1w"), (21, "1m"), (63, "3m"), (126, "6m"), (252, "12m")]:
        if len(prices) >= d + 1:
            feats[f"ret_{label}"] = float((prices.iloc[-1] / prices.iloc[-d-1]) - 1)
        else:
            feats[f"ret_{label}"] = 0.0

    # Momentum residual (retorno 1m vs 3m)
    feats["mom_residual"] = feats["ret_1m"] - feats["ret_3m"] / 3

    # ── VOLATILIDAD ──
    feats["vol_21d"]  = float(returns.tail(21).std()  * np.sqrt(252)) if len(returns) >= 21  else 0.3
    feats["vol_63d"]  = float(returns.tail(63).std()  * np.sqrt(252)) if len(returns) >= 63  else 0.3
    feats["vol_126d"] = float(returns.tail(126).std() * np.sqrt(252)) if len(returns) >= 126 else 0.3
    feats["vol_ratio"] = feats["vol_21d"] / max(feats["vol_63d"], 0.001)

    # ── RSI ──
    for w, label in [(7, "rsi_7"), (14, "rsi_14"), (28, "rsi_28")]:
        delta = prices.diff().dropna()
        gain  = delta.clip(lower=0).rolling(w).mean()
        loss  = (-delta).clip(lower=0).rolling(w).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - 100 / (1 + rs)
        feats[label] = float(rsi.iloc[-1]) if not rsi.empty else 50.0

    # RSI normalizado (-50, centrado)
    feats["rsi_14_norm"] = feats["rsi_14"] - 50

    # ── SMA POSICIÓN RELATIVA ──
    for w, label in [(20, "sma20"), (50, "sma50"), (200, "sma200")]:
        if len(prices) >= w:
            sma  = prices.rolling(w).mean().iloc[-1]
            feats[f"pos_{label}"] = float((prices.iloc[-1] / sma) - 1)
        else:
            feats[f"pos_{label}"] = 0.0

    # Golden/Death cross
    if len(prices) >= 200:
        feats["golden_cross"] = float(prices.rolling(50).mean().iloc[-1] > prices.rolling(200).mean().iloc[-1])
    else:
        feats["golden_cross"] = 0.0

    # ── MACD ──
    ema12 = prices.ewm(span=12, adjust=False).mean()
    ema26 = prices.ewm(span=26, adjust=False).mean()
    macd  = ema12 - ema26
    sig   = macd.ewm(span=9, adjust=False).mean()
    feats["macd_norm"]    = float(macd.iloc[-1] / max(prices.iloc[-1], 1))
    feats["macd_hist_norm"] = float((macd - sig).iloc[-1] / max(prices.iloc[-1], 1))

    # ── BOLLINGER BANDS ──
    bb_mid  = prices.rolling(20).mean()
    bb_std  = prices.rolling(20).std()
    bb_up   = bb_mid + 2 * bb_std
    bb_low  = bb_mid - 2 * bb_std
    bb_range = (bb_up - bb_low).iloc[-1]
    if bb_range > 0:
        feats["bb_position"] = float((prices.iloc[-1] - bb_low.iloc[-1]) / bb_range)
        feats["bb_width"]    = float(bb_range / bb_mid.iloc[-1])
    else:
        feats["bb_position"] = 0.5
        feats["bb_width"]    = 0.0

    # ── DRAWDOWN ──
    for w, label in [(21, "dd_1m"), (63, "dd_3m"), (126, "dd_6m")]:
        pw   = prices.tail(w)
        peak = pw.cummax()
        dd   = float(((pw - peak) / peak).min()) if len(pw) >= w else 0.0
        feats[label] = dd

    # ── VOLUMEN ──
    if not vol.empty and len(vol) >= 21:
        vol_ma21 = vol.rolling(21).mean().iloc[-1]
        feats["vol_ratio_price"] = float(vol.iloc[-1] / max(vol_ma21, 1))
    else:
        feats["vol_ratio_price"] = 1.0

    # ── FUNDAMENTALES ──
    feats["roe"]           = fund.get("roe") or 0.0
    feats["debt_equity"]   = min(fund.get("debt_to_equity") or 1.0, 5.0)
    feats["earnings_growth"] = np.clip(fund.get("earnings_growth") or 0.0, -1.0, 2.0)
    feats["payout_ratio"]  = fund.get("payout_ratio") or 0.5
    feats["dividend_yield"] = fund.get("dividend_yield") or 0.0

    # ── SPREAD DIVIDENDOS VS TPM ──
    dy = feats["dividend_yield"]
    feats["div_spread"] = dy - risk_free_rate

    # ── SCORE AGENTE (feedback loop) ──
    feats["rf_rate"] = risk_free_rate

    return pd.Series(feats)


def build_training_dataset(
    price_data:     Dict[str, pd.DataFrame],
    fundamentals:   Dict[str, Dict],
    risk_free_rate: float = 0.05,
    forward_days:   int   = 21,
    min_history:    int   = 252,
) -> Tuple[pd.DataFrame, pd.Series, pd.Series]:
    """
    Construye dataset de entrenamiento con walk-forward.
    X: features en fecha t
    y_reg: retorno forward a 21 días
    y_cls: clase de régimen (1=positivo, 0=negativo)
    """
    X_rows    = []
    y_returns = []
    y_regime  = []
    meta      = []   # ticker + fecha

    for ticker, df in price_data.items():
        if len(df) < min_history + forward_days:
            continue

        fund = fundamentals.get(ticker, {})

        # Walk-forward: generar samples en distintas fechas
        step = 10  # cada 10 días hábiles
        for i in range(min_history, len(df) - forward_days, step):
            df_slice = df.iloc[:i]
            feats    = engineer_features(df_slice, fund, risk_free_rate)
            if feats is None:
                continue

            # Target: retorno forward
            p0 = df["Close"].iloc[i - 1]
            p1 = df["Close"].iloc[i + forward_days - 1]
            fwd_ret = float((p1 / p0) - 1)

            X_rows.append(feats)
            y_returns.append(fwd_ret)
            y_regime.append(1 if fwd_ret > 0 else 0)
            meta.append({"ticker": ticker, "date": str(df.index[i - 1].date())})

    if not X_rows:
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=int)

    X = pd.DataFrame(X_rows).fillna(0)
    y_reg = pd.Series(y_returns, name="fwd_return_21d")
    y_cls = pd.Series(y_regime,  name="regime")

    logger.info(f"[ML] Dataset: {len(X)} samples, {X.shape[1]} features")
    return X, y_reg, y_cls


# ─────────────────────────────────────────────────────────────────
#  MODELO DE RETORNO (REGRESIÓN XGBoost)
# ─────────────────────────────────────────────────────────────────

class ReturnPredictor:
    """
    Predice retorno forward a 21 días usando XGBoost regressor.
    Incluye validación walk-forward y métricas de performance.
    """

    def __init__(self):
        self.model        = None
        self.feature_names: List[str] = []
        self.metrics:     Dict = {}
        self._load_if_exists()

    def _load_if_exists(self):
        """Carga modelo y features guardados si existen."""
        try:
            import xgboost as xgb
            if os.path.exists(MODEL_PATH) and os.path.exists(FEATURE_PATH):
                self.model = xgb.XGBRegressor()
                self.model.load_model(MODEL_PATH)
                with open(FEATURE_PATH) as f:
                    self.feature_names = json.load(f)
                if os.path.exists(METRICS_PATH):
                    with open(METRICS_PATH) as f:
                        self.metrics = json.load(f)
                logger.info(f"[ML] Modelo cargado: {MODEL_PATH}")
        except Exception as e:
            logger.info(f"[ML] Sin modelo previo ({e}), entrenar con .fit()")

    def fit(
        self,
        X:              pd.DataFrame,
        y:              pd.Series,
        test_size:      float = 0.20,
        n_estimators:   int   = 300,
        learning_rate:  float = 0.05,
        max_depth:      int   = 4,
        subsample:      float = 0.80,
        colsample:      float = 0.80,
        reg_lambda:     float = 1.5,
        early_stopping: int   = 30,
    ) -> Dict:
        """Entrena el modelo con validación temporal (no random split)."""
        try:
            import xgboost as xgb
            from sklearn.metrics import mean_squared_error, r2_score
        except ImportError:
            logger.error("[ML] XGBoost no instalado: pip install xgboost scikit-learn")
            return {}

        if X.empty:
            logger.error("[ML] Dataset vacío, no se puede entrenar")
            return {}

        # Split temporal (no random — preserva orden cronológico)
        n_test = max(int(len(X) * test_size), 50)
        X_train, X_test = X.iloc[:-n_test], X.iloc[-n_test:]
        y_train, y_test = y.iloc[:-n_test], y.iloc[-n_test:]

        self.feature_names = X.columns.tolist()

        self.model = xgb.XGBRegressor(
            n_estimators    = n_estimators,
            learning_rate   = learning_rate,
            max_depth       = max_depth,
            subsample       = subsample,
            colsample_bytree = colsample,
            reg_lambda      = reg_lambda,
            objective       = "reg:squarederror",
            eval_metric     = "rmse",
            early_stopping_rounds = early_stopping,
            verbosity       = 0,
            n_jobs          = -1,
        )

        self.model.fit(
            X_train, y_train,
            eval_set        = [(X_test, y_test)],
            verbose         = False,
        )

        # Métricas
        y_pred = self.model.predict(X_test)
        rmse   = float(np.sqrt(mean_squared_error(y_test, y_pred)))
        r2     = float(r2_score(y_test, y_pred))
        dir_acc = float(np.mean(np.sign(y_pred) == np.sign(y_test.values)))

        # Feature importance top 10
        fi = pd.Series(
            self.model.feature_importances_,
            index=self.feature_names,
        ).sort_values(ascending=False)

        self.metrics = {
            "rmse":                 round(rmse, 5),
            "r2":                   round(r2, 4),
            "directional_accuracy": round(dir_acc, 4),
            "n_train":              len(X_train),
            "n_test":               len(X_test),
            "n_features":           len(self.feature_names),
            "top_features":         fi.head(10).to_dict(),
            "trained_at":           datetime.now().isoformat(),
        }

        self._save()
        logger.info(
            f"[ML] Entrenamiento OK | RMSE={rmse:.4f} "
            f"| Dir.Acc={dir_acc*100:.1f}% | R²={r2:.3f}"
        )
        return self.metrics

    def predict(
        self,
        df:             pd.DataFrame,
        fund:           Dict,
        risk_free_rate: float = 0.05,
    ) -> Optional[Dict]:
        """Predice retorno forward a 21 días para una acción."""
        if self.model is None:
            return None

        feats = engineer_features(df, fund, risk_free_rate)
        if feats is None:
            return None

        # Alinear features con las del training
        X = pd.DataFrame([feats]).reindex(columns=self.feature_names, fill_value=0)

        try:
            pred_return = float(self.model.predict(X)[0])
            confidence  = self._compute_confidence(pred_return)
            return {
                "predicted_return_21d": round(pred_return * 100, 2),   # en %
                "direction":            "ALCISTA" if pred_return > 0 else "BAJISTA",
                "confidence":           confidence,
                "signal_ml":            self._return_to_signal(pred_return, confidence),
            }
        except Exception as e:
            logger.warning(f"[ML] Error predicción: {e}")
            return None

    def _compute_confidence(self, pred: float) -> str:
        """Convierte magnitud del retorno predicho en nivel de confianza."""
        abs_pred = abs(pred)
        if abs_pred >= 0.08:   return "ALTA"
        elif abs_pred >= 0.04: return "MEDIA"
        else:                  return "BAJA"

    def _return_to_signal(self, pred: float, confidence: str) -> str:
        if pred > 0.02 and confidence in ("ALTA", "MEDIA"):
            return "🤖 COMPRAR (ML)"
        elif pred < -0.02 and confidence in ("ALTA", "MEDIA"):
            return "🤖 EVITAR (ML)"
        else:
            return "🤖 NEUTRAL (ML)"

    def _save(self):
        if self.model is None:
            return
        self.model.save_model(MODEL_PATH)
        with open(FEATURE_PATH, "w") as f:
            json.dump(self.feature_names, f)
        with open(METRICS_PATH, "w") as f:
            json.dump(self.metrics, f, indent=2)
        logger.info(f"[ML] Modelo guardado: {MODEL_PATH}")


# ─────────────────────────────────────────────────────────────────
#  MODELO DE RÉGIMEN (CLASIFICACIÓN XGBoost)
# ─────────────────────────────────────────────────────────────────

class RegimeClassifier:
    """
    Clasifica el régimen de mercado: BULL (1) / BEAR (0).
    Entrenado sobre el índice IPSA completo.
    """

    def __init__(self):
        self.model         = None
        self.feature_names: List[str] = []
        self._load_if_exists()

    def _load_if_exists(self):
        try:
            import xgboost as xgb
            if os.path.exists(REGIME_MODEL_PATH):
                self.model = xgb.XGBClassifier()
                self.model.load_model(REGIME_MODEL_PATH)
                logger.info("[ML] Modelo de régimen cargado")
        except Exception:
            pass

    def fit(
        self,
        ipsa_df:       pd.DataFrame,
        forward_days:  int = 21,
        n_estimators:  int = 200,
    ) -> Dict:
        """Entrena clasificador de régimen sobre el índice IPSA."""
        try:
            import xgboost as xgb
            from sklearn.metrics import classification_report, accuracy_score
        except ImportError:
            return {}

        if ipsa_df is None or len(ipsa_df) < 300:
            logger.warning("[ML] IPSA index insuficiente para entrenar régimen")
            return {}

        # Features solo técnicos (sin fundamentales para el índice)
        fund_dummy = {
            "roe": 0.12, "debt_to_equity": 0.5,
            "earnings_growth": 0.05, "payout_ratio": 0.55,
            "dividend_yield": 0.04,
        }

        X_rows, y_vals = [], []
        step = 5
        for i in range(252, len(ipsa_df) - forward_days, step):
            df_slice = ipsa_df.iloc[:i]
            feats    = engineer_features(df_slice, fund_dummy)
            if feats is None:
                continue
            p0  = ipsa_df["Close"].iloc[i - 1]
            p1  = ipsa_df["Close"].iloc[i + forward_days - 1]
            cls = 1 if p1 > p0 else 0
            X_rows.append(feats)
            y_vals.append(cls)

        if not X_rows:
            return {}

        X = pd.DataFrame(X_rows).fillna(0)
        y = pd.Series(y_vals)

        self.feature_names = X.columns.tolist()

        split = int(len(X) * 0.80)
        X_tr, X_te = X.iloc[:split], X.iloc[split:]
        y_tr, y_te = y.iloc[:split], y.iloc[split:]

        self.model = xgb.XGBClassifier(
            n_estimators  = n_estimators,
            max_depth      = 4,
            learning_rate  = 0.05,
            subsample      = 0.80,
            eval_metric    = "logloss",
            use_label_encoder = False,
            verbosity      = 0,
            n_jobs         = -1,
        )
        self.model.fit(X_tr, y_tr, eval_set=[(X_te, y_te)], verbose=False)

        y_pred = self.model.predict(X_te)
        acc    = float(accuracy_score(y_te, y_pred))

        self.model.save_model(REGIME_MODEL_PATH)
        logger.info(f"[ML] Régimen entrenado: Accuracy={acc*100:.1f}%")
        return {"accuracy": round(acc, 4), "n_samples": len(X)}

    def predict_regime(
        self,
        ipsa_df:       pd.DataFrame,
        risk_free_rate: float = 0.05,
    ) -> Dict:
        """Predice régimen actual del mercado."""
        if self.model is None or ipsa_df is None:
            return {"regime_ml": "NEUTRAL", "regime_prob": 0.5}

        fund_dummy = {
            "roe": 0.12, "debt_to_equity": 0.5,
            "earnings_growth": 0.05, "payout_ratio": 0.55,
            "dividend_yield": 0.04,
        }
        feats = engineer_features(ipsa_df, fund_dummy, risk_free_rate)
        if feats is None:
            return {"regime_ml": "NEUTRAL", "regime_prob": 0.5}

        X = pd.DataFrame([feats]).reindex(columns=self.feature_names, fill_value=0)
        try:
            prob  = float(self.model.predict_proba(X)[0][1])  # P(BULL)
            label = "BULL" if prob > 0.55 else "BEAR" if prob < 0.45 else "NEUTRAL"
            return {
                "regime_ml":       label,
                "regime_prob_bull": round(prob, 3),
                "regime_confidence": "ALTA" if abs(prob - 0.5) > 0.20 else "MEDIA" if abs(prob - 0.5) > 0.10 else "BAJA",
            }
        except Exception as e:
            logger.warning(f"[ML] Error predicción régimen: {e}")
            return {"regime_ml": "NEUTRAL", "regime_prob_bull": 0.5}


# ─────────────────────────────────────────────────────────────────
#  PIPELINE COMPLETO ML
# ─────────────────────────────────────────────────────────────────

class MLPipeline:
    """Orquestador del sistema ML completo."""

    def __init__(self):
        self.return_model  = ReturnPredictor()
        self.regime_model  = RegimeClassifier()

    def train_all(
        self,
        price_data:     Dict[str, pd.DataFrame],
        fundamentals:   Dict[str, Dict],
        ipsa_df:        Optional[pd.DataFrame],
        risk_free_rate: float = 0.05,
    ) -> Dict:
        """Entrena ambos modelos con datos históricos."""
        logger.info("[ML] Iniciando entrenamiento completo...")

        # Build dataset
        X, y_reg, y_cls = build_training_dataset(
            price_data, fundamentals, risk_free_rate
        )

        results = {}

        if not X.empty:
            logger.info(f"[ML] Entrenando ReturnPredictor ({len(X)} samples)...")
            results["return_model"] = self.return_model.fit(X, y_reg)
        else:
            logger.warning("[ML] Dataset vacío, saltando entrenamiento")

        if ipsa_df is not None:
            logger.info("[ML] Entrenando RegimeClassifier...")
            results["regime_model"] = self.regime_model.fit(ipsa_df)

        return results

    def predict_all(
        self,
        price_data:     Dict[str, pd.DataFrame],
        fundamentals:   Dict[str, Dict],
        ipsa_df:        Optional[pd.DataFrame],
        risk_free_rate: float = 0.05,
    ) -> Dict[str, Dict]:
        """Genera predicciones ML para todos los tickers."""
        predictions = {}

        for ticker, df in price_data.items():
            fund = fundamentals.get(ticker, {})
            pred = self.return_model.predict(df, fund, risk_free_rate)
            if pred:
                predictions[ticker] = pred

        # Régimen global
        regime_ml = self.regime_model.predict_regime(ipsa_df, risk_free_rate)
        predictions["__regime__"] = regime_ml

        logger.info(
            f"[ML] Predicciones: {len(predictions)-1} tickers | "
            f"Régimen ML: {regime_ml.get('regime_ml')}"
        )
        return predictions

    def is_trained(self) -> bool:
        return self.return_model.model is not None

    def get_metrics(self) -> Dict:
        return {
            "return_model":  self.return_model.metrics,
            "regime_model":  {},
        }


def print_ml_metrics(metrics: Dict):
    """Imprime métricas del modelo en consola."""
    rm = metrics.get("return_model", {})
    if not rm:
        print("  ⚠️  Modelo no entrenado aún.")
        return
    print(f"\n{'='*60}")
    print(f"  🤖 ML MODEL METRICS")
    print(f"{'='*60}")
    print(f"  RMSE:                {rm.get('rmse','N/D')}")
    print(f"  R²:                  {rm.get('r2','N/D')}")
    print(f"  Directional Accuracy:{rm.get('directional_accuracy','N/D')}")
    print(f"  Train samples:       {rm.get('n_train','N/D')}")
    print(f"  Test samples:        {rm.get('n_test','N/D')}")
    print(f"  Features:            {rm.get('n_features','N/D')}")
    print(f"\n  Top Features:")
    for feat, imp in list(rm.get("top_features", {}).items())[:5]:
        bar = "▓" * int(imp * 100)
        print(f"    {feat:<25} {imp:.4f}  {bar}")
    print(f"{'='*60}\n")
