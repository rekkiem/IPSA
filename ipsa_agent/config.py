"""
IPSA Agent - Configuración Global
Agente Autónomo de Inversión para el mercado chileno
"""

# ─────────────────────────────────────────────
#  UNIVERSO DE ACCIONES IPSA
# ─────────────────────────────────────────────
IPSA_TICKERS = [
    # ── BANCOS ──────────────────────────────────────────────────
    "BSANTANDER.SN", # Banco Santander Chile
    "BCI.SN",        # Banco de Crédito e Inversiones
    "CHILE.SN",      # Banco de Chile
    "ITAUCL.SN",     # Itaú CorpBanca Chile
    # ── UTILITIES ───────────────────────────────────────────────
    "AGUAS-A.SN",    # Aguas Andinas
    "COLBUN.SN",     # Colbún
    "ENELAM.SN",     # Enel Américas
    "ENELCHILE.SN",  # Enel Chile
    # ── COMMODITIES / INDUSTRIA ─────────────────────────────────
    "CMPC.SN",       # Empresas CMPC
    "COPEC.SN",      # Empresas Copec
    "SQM-B.SN",      # SQM (Serie B)
    "VAPORES.SN",    # CSAV
    "SK.SN",         # Sigdo Koppers
    # ── RETAIL / CONSUMO ────────────────────────────────────────
    "CENCOSUD.SN",   # Cencosud
    "FALABELLA.SN",  # S.A.C.I. Falabella
    "RIPLEY.SN",     # Ripley Corp
    "CCU.SN",        # Compañía Cervecerías Unidas
    "EMBONOR-B.SN",  # Embotelladora Andina (Serie B)
    # ── REAL ESTATE ─────────────────────────────────────────────
    "MALLPLAZA.SN",  # Mall Plaza
    "PARAUCO.SN",    # Parque Arauco
    # ── TELECOMUNICACIONES ───────────────────────────────────────
    "ENTEL.SN",      # Entel
    "LTM.SN",        # LATAM Airlines
    # ── OTROS ───────────────────────────────────────────────────
    "IAM.SN",        # Inversiones Aguas Metropolitanas
    "SALFACORP.SN",  # Salfacorp
    # ── REMOVIDOS (delisted/sin datos en Yahoo Finance) ──────────
    # "SECURITY.SN"  → delisted 2025
    # "CONCHA.SN"    → no disponible en Yahoo (.SN)
    # "SMCHILE.SN"   → delisted
    # "NUEVAPOLAR.SN"→ delisted
    # "HITES.SN"     → sin liquidez suficiente
    # "ECL.SN"       → fusionada con Engie
]

# Fallback más robusto si algún ticker falla
IPSA_TICKER_NAMES = {
    "AGUAS-A.SN":    "Aguas Andinas",
    "BSANTANDER.SN": "Santander Chile",
    "BCI.SN":        "BCI",
    "CHILE.SN":      "Banco de Chile",
    "CMPC.SN":       "CMPC",
    "CENCOSUD.SN":   "Cencosud",
    "COLBUN.SN":     "Colbún",
    "COPEC.SN":      "Copec",
    "ENELAM.SN":     "Enel Américas",
    "ENELCHILE.SN":  "Enel Chile",
    "FALABELLA.SN":  "Falabella",
    "IAM.SN":        "IAM",
    "ITAUCL.SN":     "Itaú CorpBanca",
    "LTM.SN":        "LATAM Airlines",
    "MALLPLAZA.SN":  "Mall Plaza",
    "PARAUCO.SN":    "Parque Arauco",
    "RIPLEY.SN":     "Ripley",
    "SALFACORP.SN":  "Salfacorp",
    "SQM-B.SN":      "SQM-B",
    "SECURITY.SN":   "Grupo Security",
    "CCU.SN":        "CCU",
    "ENTEL.SN":      "Entel",
    "CONCHA.SN":     "Concha y Toro",
    "ECL.SN":        "E.CL",
    "EMBONOR-B.SN":  "Embotelladora Andina B",
    "VAPORES.SN":    "CSAV",
    "SMCHILE.SN":    "SMU",
    "SK.SN":         "Sigdo Koppers",
    "NUEVAPOLAR.SN": "La Polar",
    "HITES.SN":      "Hites",
}

# ─────────────────────────────────────────────
#  ACTIVOS MACRO
# ─────────────────────────────────────────────
USDCLP_TICKER   = "USDCLP=X"
IPSA_INDEX      = "^IPSA"

# ─────────────────────────────────────────────
#  PARÁMETROS MACROECONÓMICOS DEFAULT
#  (se intentan actualizar en tiempo real)
# ─────────────────────────────────────────────
DEFAULT_RISK_FREE_RATE = 0.05      # TPM BCCh ~5% (actualizar según mercado)
DEFAULT_INFLATION      = 0.048     # IPC anual ~4.8%

# ─────────────────────────────────────────────
#  VENTANAS TEMPORALES
# ─────────────────────────────────────────────
LOOKBACK_PRICES     = "2y"   # Histórico precios para backtesting
MOMENTUM_3M_DAYS    = 63
MOMENTUM_6M_DAYS    = 126
DRAWDOWN_WINDOW     = 126    # 6 meses
VOLATILITY_WINDOW   = 252    # 1 año anualizado

# ─────────────────────────────────────────────
#  PESOS DEL SCORE UNIFICADO
# ─────────────────────────────────────────────
WEIGHT_DIVIDEND  = 0.40
WEIGHT_QUALITY   = 0.25
WEIGHT_MOMENTUM  = 0.20
WEIGHT_RISK      = 0.15

# ─────────────────────────────────────────────
#  FILTROS (KILL CONDITIONS)
# ─────────────────────────────────────────────
MAX_DIVIDEND_YIELD  = 0.25   # > 25% = trampa evidente de dividendo
MAX_PAYOUT_RATIO    = 2.50   # > 250% = extremo insostenible (no 95% → era demasiado estricto)
MAX_DEBT_EQUITY     = 4.0    # > 4.0x non-banco = riesgo quiebra
RSI_OVERBOUGHT      = 88     # > 88 = sobrecompra extrema real
RSI_OVERSOLD        = 20

# ─────────────────────────────────────────────
#  KELLY SIMPLIFICADO - ASIGNACIÓN
# ─────────────────────────────────────────────
WEIGHT_HIGH_CONVICTION  = 0.28  # 25-30%
WEIGHT_MEDIUM           = 0.18  # 15-20%
WEIGHT_LOW              = 0.12  # 10-15%

# Umbral de score para convicción
SCORE_HIGH_THRESHOLD    = 0.42  # COMPRAR: recalibrado para datos reales
SCORE_MEDIUM_THRESHOLD  = 0.28  # ESPERAR

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
import os
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
DATA_DIR         = os.path.join(BASE_DIR, "data")
REPORTS_DIR      = os.path.join(BASE_DIR, "reports")
LOGS_DIR         = os.path.join(BASE_DIR, "logs")
HISTORY_FILE     = os.path.join(DATA_DIR, "decisions_history.json")
BACKTEST_FILE    = os.path.join(DATA_DIR, "backtest_results.json")

# ─────────────────────────────────────────────
#  SEÑALES
# ─────────────────────────────────────────────
SIGNAL_BUY     = "🟢 COMPRAR"
SIGNAL_WAIT    = "🟡 ESPERAR"
SIGNAL_AVOID   = "🔴 EVITAR"
SIGNAL_CAUTION = "🟠 CAUTELA"   # Mercado en crash sistémico — operar con precaución

# Stop loss %
STOP_LOSS_DEFAULT = 0.07  # 7%
