"""
IPSA Agent — Extension 1: Fuentes de Datos con Retry/Backoff
v2.1: endpoints validados, retry exponencial, JSON sanitizado
"""

import json
import logging
import math
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
    "Accept":     "application/json, text/html, */*",
    "Accept-Language": "es-CL,es;q=0.9",
}

TICKER_TO_NEMO = {
    "AGUAS-A.SN":"AGUAS-A","BSANTANDER.SN":"BSANTANDER","BCI.SN":"BCI",
    "CHILE.SN":"CHILE","CMPC.SN":"CMPC","CENCOSUD.SN":"CENCOSUD",
    "COLBUN.SN":"COLBUN","COPEC.SN":"COPEC","ENELAM.SN":"ENELAM",
    "ENELCHILE.SN":"ENELCHILE","FALABELLA.SN":"FALABELLA","IAM.SN":"IAM",
    "ITAUCL.SN":"ITAUCL","LTM.SN":"LTM","MALLPLAZA.SN":"MALLPLAZA",
    "PARAUCO.SN":"PARAUCO","SQM-B.SN":"SQM-B","CCU.SN":"CCU",
    "ENTEL.SN":"ENTEL","EMBONOR-B.SN":"EMBONOR-B","VAPORES.SN":"VAPORES",
    "RIPLEY.SN":"RIPLEY","SALFACORP.SN":"SALFACORP","SK.SN":"SK",
}

def _parse_float(v) -> Optional[float]:
    try:
        if v is None: return None
        if isinstance(v, float):
            return None if (math.isnan(v) or math.isinf(v)) else v
        if isinstance(v, int): return float(v)
        s = str(v).strip().replace(" ","").replace(",",".")
        if not s or s in ("—","-","N/A","null","None"): return None
        return float(s)
    except (ValueError, TypeError):
        return None

def _safe_float(data: dict, keys: List[str]) -> Optional[float]:
    for k in keys:
        v = data.get(k)
        if v is not None:
            f = _parse_float(v)
            if f is not None: return f
    return None

def _safe_request(session, url, params=None, timeout=12, max_retries=3, backoff=1.5) -> Optional[requests.Response]:
    """GET con retry exponencial y validación de respuesta."""
    for attempt in range(max_retries):
        try:
            resp = session.get(url, params=params, timeout=timeout)
            if resp.status_code == 404:
                logger.debug(f"[HTTP] 404: {url}")
                return None
            if resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            if not resp.content:
                raise ValueError("Respuesta vacía")
            # Validar JSON si aplica
            ct = resp.headers.get("Content-Type","")
            if "json" in ct or resp.content.lstrip()[:1] in (b"{", b"["):
                try:
                    resp.json()
                except (json.JSONDecodeError, ValueError) as e:
                    raise ValueError(f"JSON inválido: {e}")
            return resp
        except (requests.ConnectionError, requests.Timeout, ValueError, requests.HTTPError) as e:
            wait = backoff ** attempt
            if attempt < max_retries - 1:
                logger.warning(f"[HTTP] Intento {attempt+1}/{max_retries} ({url[:60]}): {e}. Esperando {wait:.1f}s")
                time.sleep(wait)
            else:
                logger.warning(f"[HTTP] Todos los intentos fallaron: {url[:60]}")
        except Exception as e:
            logger.warning(f"[HTTP] Error inesperado {url[:60]}: {e}")
            break
    return None


class BCSDataSource:
    """Bolsa de Santiago — múltiples endpoints con fallback."""
    LIVE_EPS = [
        "https://www.bolsadesantiago.com/api/Hs/GetLastPrice",
        "https://www.bolsadesantiago.com/api/Mercado/MercadoEnVivo",
    ]
    HIST_EPS = [
        "https://www.bolsadesantiago.com/api/Hs/GetHistoricalData",
        "https://www.bolsadesantiago.com/api/Mercado/getDetalleHistoricoByNemo",
    ]

    def __init__(self, timeout=12):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout
        self._failed: set = set()

    def get_live_prices(self) -> Dict[str, Dict]:
        for ep in self.LIVE_EPS:
            if ep in self._failed: continue
            resp = _safe_request(self.session, ep, timeout=self.timeout, max_retries=2)
            if resp is None: self._failed.add(ep); continue
            try:
                data = resp.json()
            except Exception: self._failed.add(ep); continue
            result = {}
            items = data if isinstance(data, list) else data.get("data", data.get("Data", []))
            for item in (items if isinstance(items, list) else []):
                if not isinstance(item, dict): continue
                nemo = next((str(item[k]).upper().strip() for k in ("nemo","Nemo","nemotecnico","symbol") if k in item and item[k]), None)
                price = _safe_float(item, ["ultimo","Ultimo","price","Price","cierre","Cierre","last"])
                if nemo and price and price > 0:
                    result[nemo] = {"price": price, "source": "BCS_LIVE", "timestamp": datetime.now().isoformat()}
            if result:
                logger.info(f"[BCS] Precios en vivo: {len(result)} instrumentos")
                return result
            self._failed.add(ep)
        logger.warning("[BCS] Live prices no disponibles")
        return {}

    def get_historical(self, nemo: str, days_back=730) -> Optional[pd.DataFrame]:
        end = datetime.now(); start = end - timedelta(days=days_back)
        for ep in self.HIST_EPS:
            if ep in self._failed: continue
            for params in [
                {"nemo": nemo, "fechaInicio": start.strftime("%Y-%m-%d"), "fechaFin": end.strftime("%Y-%m-%d")},
                {"symbol": nemo, "from": start.strftime("%Y-%m-%d"), "to": end.strftime("%Y-%m-%d")},
            ]:
                resp = _safe_request(self.session, ep, params=params, timeout=self.timeout, max_retries=2)
                if resp is None: continue
                try:
                    data = resp.json()
                except Exception: continue
                records = data if isinstance(data, list) else data.get("data", data.get("Data", []))
                rows = []
                for r in (records if isinstance(records, list) else []):
                    if not isinstance(r, dict): continue
                    date_str = next((str(r[k]) for k in ("fecha","Fecha","date","Date") if k in r and r[k]), None)
                    close = _safe_float(r, ["cierre","Cierre","Close","close","last","Last","precio"])
                    if date_str and close and close > 0:
                        rows.append({"Date": date_str, "Open": _safe_float(r,["apertura","Open"]) or close,
                                     "High": _safe_float(r,["maximo","High"]) or close,
                                     "Low": _safe_float(r,["minimo","Low"]) or close,
                                     "Close": close, "Volume": _safe_float(r,["volumen","Volume"]) or 0})
                if len(rows) >= 30:
                    df = pd.DataFrame(rows)
                    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
                    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
                    logger.info(f"[BCS] Histórico {nemo}: {len(df)} registros")
                    return df
            self._failed.add(ep)
        return None


class CMFDataSource:
    """CMF Chile — dividendos anunciados."""

    def __init__(self, api_token="", timeout=15):
        self.api_token = api_token
        self.session   = requests.Session()
        self.session.headers.update(HEADERS)
        self.timeout = timeout
        self._cache: List[Dict] = []
        self._cache_ts = None

    def get_announced_dividends(self) -> List[Dict]:
        if self._cache and self._cache_ts and (datetime.now() - self._cache_ts).seconds < 21600:
            return self._cache
        result = []
        if self.api_token:
            result = self._api()
        if not result:
            result = self._scrape()
        if result:
            self._cache = result; self._cache_ts = datetime.now()
            logger.info(f"[CMF] Dividendos: {len(result)}")
        else:
            logger.info("[CMF] Sin dividendos (registra token en api.cmfchile.cl para más datos)")
        return result

    def _api(self) -> List[Dict]:
        resp = _safe_request(self.session, "https://api.cmfchile.cl/api-sbifv3/recursos_api/dividendos",
                             params={"apikey": self.api_token, "formato": "json"}, timeout=self.timeout)
        if not resp: return []
        try:
            data = resp.json()
        except Exception: return []
        divs = data.get("Dividendos", data.get("dividendos", []))
        return [{"ticker": d.get("Nemotecnico","").strip()+".SN",
                 "monto_clp": _parse_float(d.get("Dividendo",0)),
                 "fecha_pago": d.get("FechaPago",""), "source":"CMF_API"} for d in divs if d.get("Nemotecnico")]

    def _scrape(self) -> List[Dict]:
        """Scraping con URL actualizada 2025."""
        urls = [
            "https://www.cmfchile.cl/portal/principal/613/w3-propertyvalue-18248.html",
            "https://www.cmfchile.cl/portal/principal/613/articles-48155_recurso_2.html",
        ]
        import re
        for url in urls:
            resp = _safe_request(self.session, url, timeout=self.timeout, max_retries=2)
            if resp is None: continue
            try:
                html = resp.text
                td_re = re.compile(r'<td[^>]*>\s*([^<\n]{1,50}?)\s*</td>', re.I)
                tds = td_re.findall(html)
                nemo_re = re.compile(r'^[A-Z][A-Z0-9\-]{1,9}$')
                results = []
                for i, td in enumerate(tds):
                    td_c = td.strip()
                    if nemo_re.match(td_c) and i + 2 < len(tds):
                        monto = _parse_float(tds[i+1].replace(".","").replace(",","."))
                        fecha = tds[i+2].strip()
                        if monto and monto > 0 and len(fecha) >= 8:
                            results.append({"ticker": td_c+".SN", "monto_clp": monto,
                                            "fecha_pago": fecha, "source": "CMF_SCRAPE"})
                if results: return results
            except Exception as e:
                logger.debug(f"[CMF] Scrape {url}: {e}")
        return []

    def enrich_dividend_yield(self, ticker: str, current_price: float, announced: List[Dict]) -> Optional[float]:
        if not announced or current_price <= 0: return None
        nemo = ticker.replace(".SN","").upper()
        total = sum(d.get("monto_clp",0) or 0 for d in announced
                    if d.get("ticker","").replace(".SN","").upper() == nemo)
        return (total / current_price) if total > 0 else None


def fetch_yfinance_robust(ticker: str, period="2y", max_retries=3) -> Optional[pd.DataFrame]:
    """Yahoo Finance con reintentos y fallback de períodos."""
    import yfinance as yf, warnings
    warnings.filterwarnings("ignore")
    for p in [period, "1y", "6mo"]:
        for attempt in range(max_retries):
            try:
                df = yf.Ticker(ticker).history(period=p, auto_adjust=True)
                if df is not None and not df.empty and len(df) >= 20:
                    df.index = pd.to_datetime(df.index).tz_localize(None)
                    if "Close" in df.columns:
                        return df
                elif df is not None and df.empty:
                    return None  # delisted
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))
    return None


class CascadeDataFetcher:
    """
    Orquestador de ingesta: BCS → Yahoo Finance.
    v2.1: retry, caché, detección de delisted, estado detallado.
    """

    def __init__(self, cmf_token="", use_bcs=True, use_yfinance=True):
        self.bcs     = BCSDataSource()  if use_bcs  else None
        self.cmf     = CMFDataSource(api_token=cmf_token)
        self.use_yf  = use_yfinance
        self._live:  Dict              = {}
        self._divs:  List[Dict]        = []
        self._cache: Dict[str, pd.DataFrame] = {}
        self._failed: set              = set()

    def prefetch(self):
        logger.info("[CASCADE] Prefetch iniciando...")
        if self.bcs:
            self._live = self.bcs.get_live_prices()
        self._divs = self.cmf.get_announced_dividends()
        logger.info(f"[CASCADE] Prefetch: {len(self._live)} precios BCS, {len(self._divs)} dividendos CMF")

    def get_price_history(self, ticker: str, period="2y") -> Optional[pd.DataFrame]:
        if ticker in self._failed: return None
        if ticker in self._cache:  return self._cache[ticker]
        nemo = TICKER_TO_NEMO.get(ticker, ticker.replace(".SN",""))
        # Fuente 1: BCS
        if self.bcs:
            df = self.bcs.get_historical(nemo, days_back=730)
            if df is not None and len(df) >= 30:
                live_p = self._live.get(nemo, {}).get("price")
                if live_p:
                    today = pd.Timestamp(datetime.now().date())
                    if today not in df.index:
                        df = pd.concat([df, pd.DataFrame(
                            {"Close":[live_p],"Open":[live_p],"High":[live_p],"Low":[live_p],"Volume":[0]},
                            index=[today])]).sort_index()
                self._cache[ticker] = df
                return df
        # Fuente 2: Yahoo
        if self.use_yf:
            df = fetch_yfinance_robust(ticker, period)
            if df is not None:
                self._cache[ticker] = df
                return df
            self._failed.add(ticker)
            logger.info(f"[CASCADE] {ticker} → delisted/no disponible")
        return None

    def get_all_histories(self, tickers: List[str], period="2y") -> Dict[str, pd.DataFrame]:
        result = {}
        for i, ticker in enumerate(tickers, 1):
            logger.info(f"[CASCADE] {ticker} ({i}/{len(tickers)})...")
            df = self.get_price_history(ticker, period)
            if df is not None:
                result[ticker] = df
            time.sleep(0.08)
        logger.info(f"[CASCADE] {len(result)}/{len(tickers)} tickers OK | {len(self._failed)} sin datos")
        return result

    def get_current_price(self, ticker: str) -> Optional[float]:
        nemo = TICKER_TO_NEMO.get(ticker, ticker.replace(".SN",""))
        p = self._live.get(nemo, {}).get("price")
        if p: return p
        df = self._cache.get(ticker)
        return float(df["Close"].iloc[-1]) if df is not None and not df.empty else None

    def get_cmf_dividend_yield(self, ticker: str, current_price: float) -> Optional[float]:
        return self.cmf.enrich_dividend_yield(ticker, current_price, self._divs)

    def get_announced_dividends_for_ticker(self, ticker: str) -> List[Dict]:
        nemo = ticker.replace(".SN","").upper()
        return [d for d in self._divs if d.get("ticker","").replace(".SN","").upper() == nemo]

    def get_status(self) -> Dict:
        return {"bcs_live": len(self._live), "cmf_divs": len(self._divs),
                "cached": len(self._cache), "failed": sorted(self._failed),
                "bcs_failed_eps": sorted(self.bcs._failed) if self.bcs else []}


def get_data_source_status() -> Dict:
    """Verifica disponibilidad de fuentes en paralelo."""
    import concurrent.futures
    sources = {"BCS":"https://www.bolsadesantiago.com","CMF":"https://www.cmfchile.cl",
               "Yahoo":"https://finance.yahoo.com","YF_API":"https://query1.finance.yahoo.com/v8/finance/chart/CHILE.SN"}
    def check(nv):
        n, u = nv
        try:
            r = requests.get(u, timeout=8, headers=HEADERS)
            return n, {"ok": r.status_code < 500, "code": r.status_code}
        except Exception as e:
            return n, {"ok": False, "error": str(e)[:50]}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        return dict(ex.map(check, sources.items()))
