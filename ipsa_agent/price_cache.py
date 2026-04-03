"""
IPSA Agent — Cache Local de Datos Históricos
Persiste precios en disco (Parquet/CSV) para:
  - Evitar re-descargas en cada ejecución
  - Fallback cuando Yahoo Finance no responde
  - Acelerar el pipeline de 2-3 min → 20-30 seg en ejecuciones subsiguientes

Uso:
    cache = PriceCache()
    df = cache.get("CHILE.SN")          # lee de disco si existe y no está stale
    cache.set("CHILE.SN", df)           # guarda en disco
    df = cache.get_or_fetch("CHILE.SN") # lee cache o descarga
"""

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Directorio de caché dentro de ipsa_agent/
CACHE_DIR      = os.path.join(os.path.dirname(__file__), "data", "price_cache")
CACHE_META     = os.path.join(CACHE_DIR, "_meta.json")
STALE_HOURS    = 8      # Cache válido por 8 horas (renueva intraday)
STALE_DAYS_DF  = 1      # Si el archivo tiene > 1 día, forzar re-descarga


class PriceCache:
    """
    Caché persistente de series de precios en formato Parquet.
    Diseñado para ser transparente: si el caché falla, el agente funciona igual.
    """

    def __init__(self, cache_dir: str = CACHE_DIR, stale_hours: int = STALE_HOURS):
        self.cache_dir   = cache_dir
        self.stale_hours = stale_hours
        self._meta_path  = os.path.join(cache_dir, "_meta.json")   # per-instance
        self._meta: Dict = {}
        os.makedirs(cache_dir, exist_ok=True)
        self._load_meta()

    # ── LECTURA ─────────────────────────────────────────────────

    def get(self, ticker: str) -> Optional[pd.DataFrame]:
        """Lee serie de precios del caché si existe y no está stale."""
        if not self._is_fresh(ticker):
            return None
        path = self._path(ticker)
        if not os.path.exists(path):
            return None
        try:
            df = pd.read_parquet(path)
            df.index = pd.to_datetime(df.index)
            logger.debug(f"[CACHE] {ticker}: {len(df)} filas desde disco")
            return df
        except Exception as e:
            logger.warning(f"[CACHE] Error leyendo {ticker}: {e}")
            return None

    def get_or_fetch(
        self,
        ticker:   str,
        fetcher,           # callable(ticker) → Optional[pd.DataFrame]
        period:   str = "2y",
        force:    bool = False,
    ) -> Optional[pd.DataFrame]:
        """
        Intenta caché primero; si está stale o ausente, descarga y guarda.
        fetcher: función que descarga el dato (ej. fetch_yfinance_robust).
        """
        if not force:
            cached = self.get(ticker)
            if cached is not None and len(cached) >= 20:
                return cached

        logger.debug(f"[CACHE] {ticker}: descargando (caché stale o vacío)")
        df = fetcher(ticker, period)
        if df is not None and len(df) >= 20:
            self.set(ticker, df)
        return df

    # ── ESCRITURA ────────────────────────────────────────────────

    def set(self, ticker: str, df: pd.DataFrame):
        """Guarda serie de precios en disco."""
        if df is None or df.empty:
            return
        try:
            # Limpiar NaN en el DataFrame antes de guardar
            df_clean = df.copy()
            for col in df_clean.select_dtypes(include=["float64", "float32"]).columns:
                df_clean[col] = df_clean[col].where(df_clean[col].notna(), other=None)
            df_clean.to_parquet(self._path(ticker), index=True)
            self._meta[ticker] = {"ts": datetime.now().isoformat(), "rows": len(df)}
            self._save_meta()
            logger.debug(f"[CACHE] {ticker}: {len(df)} filas guardadas")
        except Exception as e:
            logger.warning(f"[CACHE] Error guardando {ticker}: {e}")

    def invalidate(self, ticker: str):
        """Invalida caché de un ticker específico."""
        if ticker in self._meta:
            del self._meta[ticker]
            self._save_meta()
        path = self._path(ticker)
        if os.path.exists(path):
            os.remove(path)
        logger.info(f"[CACHE] {ticker} invalidado")

    def invalidate_all(self):
        """Limpia todo el caché."""
        import shutil
        shutil.rmtree(self.cache_dir, ignore_errors=True)
        os.makedirs(self.cache_dir, exist_ok=True)
        self._meta = {}
        logger.info("[CACHE] Caché completo eliminado")

    # ── BATCH ────────────────────────────────────────────────────

    def get_all(self, tickers: List[str]) -> Dict[str, pd.DataFrame]:
        """Lee todos los tickers del caché (solo los que son frescos)."""
        result = {}
        for t in tickers:
            df = self.get(t)
            if df is not None:
                result[t] = df
        if result:
            logger.info(f"[CACHE] {len(result)}/{len(tickers)} tickers leídos del caché")
        return result

    def fetch_missing(
        self,
        tickers:  List[str],
        fetcher,
        period:   str = "2y",
        delay:    float = 0.1,
    ) -> Dict[str, pd.DataFrame]:
        """
        Descarga solo los tickers que no están en caché o están stale.
        Combina con get_all() para el pipeline completo.
        """
        cached  = self.get_all(tickers)
        missing = [t for t in tickers if t not in cached]

        if not missing:
            logger.info("[CACHE] Todos los tickers en cache OK")
            return cached

        logger.info(f"[CACHE] Descargando {len(missing)} tickers faltantes...")
        for i, ticker in enumerate(missing, 1):
            logger.info(f"[CACHE] Fetch {ticker} ({i}/{len(missing)})...")
            df = fetcher(ticker, period)
            if df is not None:
                self.set(ticker, df)
                cached[ticker] = df
            time.sleep(delay)

        logger.info(f"[CACHE] Total: {len(cached)}/{len(tickers)} tickers disponibles")
        return cached

    # ── STATUS ───────────────────────────────────────────────────

    def status(self) -> Dict:
        """Estado del caché: tickers frescos, stale, ausentes."""
        fresh, stale, absent = [], [], []
        for ticker, info in self._meta.items():
            if self._is_fresh(ticker):
                fresh.append(ticker)
            else:
                stale.append(ticker)

        return {
            "cache_dir":    self.cache_dir,
            "total_cached": len(self._meta),
            "fresh":        len(fresh),
            "stale":        len(stale),
            "stale_tickers": stale,
            "stale_hours":  self.stale_hours,
            "disk_mb":      self._disk_usage_mb(),
        }

    def print_status(self):
        s = self.status()
        print(f"\n📦 PRICE CACHE STATUS")
        print(f"  Dir:      {s['cache_dir']}")
        print(f"  Frescos:  {s['fresh']}  |  Stale: {s['stale']}  |  Disco: {s['disk_mb']:.1f} MB")
        if s["stale_tickers"]:
            print(f"  Stale:    {', '.join(s['stale_tickers'])}")

    # ── PRIVADOS ─────────────────────────────────────────────────

    def _path(self, ticker: str) -> str:
        safe = ticker.replace("/", "_").replace("\\", "_").replace(".", "_")
        return os.path.join(self.cache_dir, f"{safe}.parquet")

    def _is_fresh(self, ticker: str) -> bool:
        info = self._meta.get(ticker)
        if not info:
            return False
        try:
            ts    = datetime.fromisoformat(info["ts"])
            delta = datetime.now() - ts
            return delta.total_seconds() < self.stale_hours * 3600
        except Exception:
            return False

    def _load_meta(self):
        if os.path.exists(self._meta_path):
            try:
                with open(self._meta_path) as f:
                    self._meta = json.load(f)
            except Exception:
                self._meta = {}

    def _save_meta(self):
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self._meta_path, "w") as f:
                json.dump(self._meta, f, indent=2)
        except Exception as e:
            logger.warning(f"[CACHE] Error guardando meta: {e}")

    def _disk_usage_mb(self) -> float:
        total = 0
        for f in os.listdir(self.cache_dir):
            fpath = os.path.join(self.cache_dir, f)
            if os.path.isfile(fpath):
                total += os.path.getsize(fpath)
        return total / (1024 * 1024)
