# 🇨🇱 IPSA Agent — Gestor Autónomo de Inversión

Agente cuantitativo autónomo para selección diaria de acciones del IPSA chileno.
Opera como gestor institucional: análisis de dividendos, calidad, momentum y riesgo.

---

## 🏗️ Arquitectura

```
ipsa_agent/
├── config.py           # Configuración global (tickers, pesos, umbrales)
├── data_layer.py       # Ingesta: precios, fundamentales, macro
├── analysis_engine.py  # Factores: dividendos, calidad, momentum, riesgo
├── scoring.py          # Score unificado, filtros, ranking, portafolio
├── report_generator.py # Reportes HTML + JSON + consola
├── backtest.py         # Motor de backtesting histórico
├── main.py             # Orquestador principal (CLI)
├── scheduler.py        # Automatización diaria (cron)
├── requirements.txt
├── data/               # Historial de decisiones (JSON)
├── reports/            # Reportes HTML y JSON diarios
└── logs/               # Logs de ejecución
```

---

## ⚡ Instalación

```bash
# 1. Clonar / descomprimir el proyecto
cd ipsa_agent

# 2. Crear entorno virtual
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Crear directorios necesarios
mkdir -p data reports logs
```

---

## 🚀 Uso

### Análisis diario completo
```bash
python main.py
```
Genera:
- Output detallado en consola
- `reports/ipsa_report_YYYY-MM-DD.html` → abrir en navegador
- `reports/ipsa_data_YYYY-MM-DD.json`
- Guarda en `data/decisions_history.json`

### Solo análisis sin HTML
```bash
python main.py --no-html --no-json
```

### Ver historial de decisiones
```bash
python main.py --mode history
```

### Backtesting histórico (6-12 meses)
```bash
# Backtest últimos 12 meses
python main.py --mode backtest

# Rango específico
python main.py --mode backtest --start 2024-01-01 --end 2025-01-01
```

### Automatización diaria
```bash
# Ejecutar scheduler (corre todos los días hábiles a las 09:15)
python scheduler.py

# Ver línea crontab equivalente
python scheduler.py --crontab

# Hora personalizada (ej: 10:30 AM)
python scheduler.py --hour 10 --minute 30
```

---

## ⚙️ Configuración

Editar `config.py` para personalizar:

```python
# Ajustar tasa libre de riesgo manualmente si el scraping falla
DEFAULT_RISK_FREE_RATE = 0.05  # TPM BCCh actual

# Pesos del score (deben sumar ~1.0)
WEIGHT_DIVIDEND = 0.40  # Factor dividendos
WEIGHT_QUALITY  = 0.25  # Factor calidad
WEIGHT_MOMENTUM = 0.20  # Factor técnico
WEIGHT_RISK     = 0.15  # Factor riesgo

# Filtros de exclusión
MAX_DIVIDEND_YIELD = 0.15  # > 15% = posible trampa
MAX_PAYOUT_RATIO   = 0.90
MAX_DEBT_EQUITY    = 2.0
```

---

## 📊 Fórmula del Score

```
Score = (DividendFactor × 0.40)
      + (QualityFactor  × 0.25)
      + (MomentumFactor × 0.20)
      - (RiskPenalty    × 0.15)
```

Donde:
- **DividendFactor**: (DY Forward - TPM) normalizado [0,1]
- **QualityFactor**: ROE, D/E, crecimiento utilidades, payout [0,1]
- **MomentumFactor**: Retorno 3M/6M, RSI, SMA50, MACD [0,1]
- **RiskPenalty**: (1 - risk_score), donde risk_score = f(drawdown, volatilidad)

---

## 🛑 Kill Conditions (Filtros automáticos)

Una acción se excluye automáticamente si:
| Condición | Umbral | Razón |
|-----------|--------|-------|
| Dividend Yield | > 15% | Posible trampa de dividendos |
| Payout Ratio | > 90% | Dividendo insostenible |
| Deuda/Equity | > 2.0x | Exceso de apalancamiento |
| Momentum 3M+6M | < -20%/-25% | Tendencia bajista severa |
| RSI | > 75 | Sobrecompra extrema |

---

## 📈 Ejemplo de Output (consola)

```
================================================================================
  🇨🇱  IPSA AGENT | REPORTE DIARIO | 2025-06-15 09:15

📊 CONTEXTO MACROECONÓMICO
  USD/CLP:              935.20
  Tasa libre de riesgo:  5.00%
  IPC anual:             4.80%
  Régimen IPSA:         BULL (Momentum 3M: +8.3%)

🔥 TOP 5 ACCIONES IPSA HOY
  Rank Ticker           Score   DY%     Spread   RSI    DD%     Vol%    Señal
  1    BSANTANDER.SN    0.6821  5.2%    +0.2%    48.3   -12.4%  18.2%   🟢 COMPRAR
  2    CHILE.SN         0.6543  4.8%    -0.2%    52.1   -10.1%  15.6%   🟢 COMPRAR
  3    AGUAS-A.SN       0.6102  4.5%    -0.5%    44.7   -8.3%   12.1%   🟢 COMPRAR
  4    COPEC.SN         0.5834  3.2%    -1.8%    58.9   -14.7%  22.4%   🟡 ESPERAR
  5    CMPC.SN          0.5621  2.9%    -2.1%    41.2   -11.2%  19.8%   🟡 ESPERAR

⚖️  ASIGNACIÓN DE PORTAFOLIO
  BSANTANDER.SN   28.0%  ██████████████
  CHILE.SN        22.0%  ███████████
  AGUAS-A.SN      20.0%  ██████████
  COPEC.SN        17.0%  ████████
  CMPC.SN         13.0%  ██████
  CAJA/CASH        0.0%
```

---

## ⚠️ Disclaimer

Este software es **únicamente para fines educativos e informativos**.
No constituye asesoramiento financiero. Las inversiones en bolsa conllevan riesgo de pérdida de capital.
Siempre consulta con un asesor financiero certificado antes de invertir.

---

## 🔧 Fuentes de Datos

| Dato | Fuente |
|------|--------|
| Precios históricos | Yahoo Finance (yfinance, sufijo .SN) |
| Dividendos | Yahoo Finance (ticker.dividends) |
| Fundamentales | Yahoo Finance (ticker.info) |
| Tasa libre de riesgo | Configuración manual (BCCh) |
| IPC | Configuración manual (INE Chile) |
| USD/CLP | Yahoo Finance (USDCLP=X) |
| Índice IPSA | Yahoo Finance (^IPSA) |
