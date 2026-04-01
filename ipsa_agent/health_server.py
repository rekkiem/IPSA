"""
IPSA Agent — Health Check y Monitoreo
Servidor HTTP liviano (puerto 8765) que expone:
  GET /health        → estado general del agente
  GET /status        → estado detallado (fuentes, cache, último reporte)
  GET /metrics       → métricas del modelo ML
  GET /last-report   → resumen del último Top 5

Uso:
    # Arrancar junto al agente
    python health_server.py &

    # Consultar
    curl http://localhost:8765/health
    curl http://localhost:8765/status
"""

import json
import logging
import os
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict

logger = logging.getLogger(__name__)

HEALTH_PORT = int(os.environ.get("HEALTH_PORT", 8765))


# ─────────────────────────────────────────────────────────────────
#  ESTADO GLOBAL DEL AGENTE
# ─────────────────────────────────────────────────────────────────

class AgentMonitor:
    """Singleton que mantiene el estado del agente en memoria."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init()
        return cls._instance

    def _init(self):
        self._lock             = threading.Lock()
        self.last_run:         str  = "nunca"
        self.last_run_ok:      bool = False
        self.last_duration_s:  float = 0.0
        self.last_top5:        list  = []
        self.last_regime:      str   = "NEUTRAL"
        self.last_usdclp:      float = 0.0
        self.errors:           list  = []      # últimos 10 errores
        self.warnings:         list  = []      # últimas 10 advertencias
        self.pipeline_count:   int   = 0
        self.ml_trained:       bool  = False
        self.ml_metrics:       dict  = {}
        self.cache_status:     dict  = {}
        self.data_sources:     dict  = {}
        self.started_at:       str   = datetime.now().isoformat()

    def record_run(
        self,
        ok:          bool,
        duration_s:  float,
        top5_tickers: list,
        regime:      str,
        usdclp:      float,
    ):
        with self._lock:
            self.last_run        = datetime.now().isoformat()
            self.last_run_ok     = ok
            self.last_duration_s = duration_s
            self.last_top5       = top5_tickers
            self.last_regime     = regime
            self.last_usdclp     = usdclp
            self.pipeline_count += 1

    def record_error(self, error: str):
        with self._lock:
            self.errors = (self.errors + [{"ts": datetime.now().isoformat(), "msg": error}])[-10:]

    def record_warning(self, warning: str):
        with self._lock:
            self.warnings = (self.warnings + [{"ts": datetime.now().isoformat(), "msg": warning}])[-10:]

    def update_ml(self, trained: bool, metrics: dict):
        with self._lock:
            self.ml_trained = trained
            self.ml_metrics = metrics

    def update_cache(self, status: dict):
        with self._lock:
            self.cache_status = status

    def update_data_sources(self, status: dict):
        with self._lock:
            self.data_sources = status

    def to_health(self) -> dict:
        with self._lock:
            return {
                "status":           "ok" if self.last_run_ok else ("degraded" if self.pipeline_count > 0 else "starting"),
                "last_run":         self.last_run,
                "last_run_ok":      self.last_run_ok,
                "pipeline_count":   self.pipeline_count,
                "started_at":       self.started_at,
                "top5":             self.last_top5,
                "regime":           self.last_regime,
                "usdclp":           self.last_usdclp,
            }

    def to_status(self) -> dict:
        with self._lock:
            return {
                **self.to_health(),
                "last_duration_s":  self.last_duration_s,
                "ml_trained":       self.ml_trained,
                "ml_metrics":       self.ml_metrics,
                "cache":            self.cache_status,
                "data_sources":     self.data_sources,
                "recent_errors":    self.errors[-5:],
                "recent_warnings":  self.warnings[-5:],
            }


# Singleton global
monitor = AgentMonitor()


# ─────────────────────────────────────────────────────────────────
#  HANDLER HTTP
# ─────────────────────────────────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):

    ROUTES = {
        "/health":      "_handle_health",
        "/status":      "_handle_status",
        "/metrics":     "_handle_metrics",
        "/last-report": "_handle_last_report",
        "/ping":        "_handle_ping",
    }

    def do_GET(self):
        path = self.path.split("?")[0]
        handler_name = self.ROUTES.get(path)
        if handler_name:
            getattr(self, handler_name)()
        else:
            self._respond(404, {"error": f"Not found: {path}", "routes": list(self.ROUTES.keys())})

    def _handle_ping(self):
        self._respond(200, {"pong": True, "ts": datetime.now().isoformat()})

    def _handle_health(self):
        data   = monitor.to_health()
        status = 200 if data["status"] in ("ok", "starting") else 503
        self._respond(status, data)

    def _handle_status(self):
        self._respond(200, monitor.to_status())

    def _handle_metrics(self):
        self._respond(200, {
            "ml_trained":  monitor.ml_trained,
            "ml_metrics":  monitor.ml_metrics,
            "pipeline_count": monitor.pipeline_count,
        })

    def _handle_last_report(self):
        """Lee el último reporte JSON del agente."""
        try:
            import glob
            base = os.path.join(os.path.dirname(__file__), "reports")
            files = sorted(glob.glob(os.path.join(base, "ipsa_data_*.json")), reverse=True)
            if not files:
                self._respond(404, {"error": "No reports yet"})
                return
            with open(files[0]) as f:
                raw = f.read()
            # Sanitizar NaN residuales
            import re
            clean = re.sub(r':\s*NaN',  ': null', raw)
            clean = re.sub(r':\s*-?Infinity', ': null', clean)
            data  = json.loads(clean)
            self._respond(200, data)
        except Exception as e:
            self._respond(500, {"error": str(e)})

    def _respond(self, code: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        logger.debug(f"[HEALTH] {self.address_string()} {fmt % args}")


# ─────────────────────────────────────────────────────────────────
#  SERVIDOR EN THREAD SEPARADO
# ─────────────────────────────────────────────────────────────────

class HealthServer:
    """Servidor health check en background thread."""

    def __init__(self, port: int = HEALTH_PORT):
        self.port   = port
        self._server: HTTPServer = None
        self._thread: threading.Thread = None

    def start(self):
        try:
            self._server = HTTPServer(("0.0.0.0", self.port), HealthHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            logger.info(f"[HEALTH] Servidor iniciado en http://0.0.0.0:{self.port}")
        except OSError as e:
            logger.warning(f"[HEALTH] No se pudo iniciar en puerto {self.port}: {e}")

    def stop(self):
        if self._server:
            self._server.shutdown()
            logger.info("[HEALTH] Servidor detenido")


# ─────────────────────────────────────────────────────────────────
#  LOGGING HANDLER PARA CAPTURAR WARNINGS/ERRORS
# ─────────────────────────────────────────────────────────────────

class MonitorLogHandler(logging.Handler):
    """Captura logs WARNING+ y los registra en el monitor."""

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            if record.levelno >= logging.ERROR:
                monitor.record_error(msg[:200])
            elif record.levelno >= logging.WARNING:
                monitor.record_warning(msg[:200])
        except Exception:
            pass


def install_log_handler():
    """Instala el handler de monitoreo en el logger raíz."""
    handler = MonitorLogHandler()
    handler.setLevel(logging.WARNING)
    logging.getLogger().addHandler(handler)


# ─────────────────────────────────────────────────────────────────
#  DECORADOR PARA INSTRUMENTAR EL PIPELINE
# ─────────────────────────────────────────────────────────────────

def instrument_pipeline(func):
    """
    Decorator que envuelve el pipeline diario y registra métricas.
    Uso: @instrument_pipeline en run_daily_pipeline_v2()
    """
    import functools, time as _time

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        t0  = _time.time()
        ok  = False
        result = {}
        try:
            result = func(*args, **kwargs)
            ok     = True
            # Extraer métricas del resultado
            top5    = result.get("top5")
            macro   = result.get("macro", {})
            regime  = result.get("regime", {})
            tickers = top5["ticker"].tolist() if top5 is not None and not top5.empty else []
            monitor.record_run(
                ok          = True,
                duration_s  = _time.time() - t0,
                top5_tickers = tickers,
                regime       = regime.get("regime", "NEUTRAL"),
                usdclp       = macro.get("usdclp") or 0.0,
            )
        except Exception as e:
            monitor.record_error(f"Pipeline exception: {e}")
            monitor.record_run(False, _time.time() - t0, [], "ERROR", 0.0)
            raise
        return result

    return wrapper


# ─────────────────────────────────────────────────────────────────
#  ENTRY POINT STANDALONE
# ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    install_log_handler()

    port   = int(sys.argv[1]) if len(sys.argv) > 1 else HEALTH_PORT
    server = HealthServer(port)
    server.start()
    print(f"\n✅ Health server en http://localhost:{port}")
    print(f"   GET /health       → estado general")
    print(f"   GET /status       → estado detallado")
    print(f"   GET /metrics      → métricas ML")
    print(f"   GET /last-report  → último reporte Top 5\n")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
        print("\nDetenido.")
