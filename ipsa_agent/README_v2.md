# 🇨🇱 IPSA Agent v2 — Gestor Autónomo de Inversión

Sistema cuantitativo completo para selección diaria de acciones del IPSA chileno.
Integra análisis fundamental, técnico, ML predictivo, alertas Telegram y dashboard web.

---

## 🏗️ Arquitectura Completa

```
ipsa_agent/
├── config.py                    ← Configuración global
├── data_layer.py                ← Ingesta Yahoo Finance
├── analysis_engine.py           ← Factores: div, calidad, momentum, riesgo
├── scoring.py                   ← Score unificado + kill conditions + portafolio
├── report_generator.py          ← Reportes HTML dark + JSON
├── backtest.py                  ← Backtesting walk-forward + historial
├── main.py                      ← CLI v1 (solo análisis)
├── main_v2.py                   ← CLI v2 (todas las extensiones)
├── scheduler.py                 ← Automatización diaria (días hábiles)
├── requirements.txt
├── .env.example                 ← Variables de entorno
│
├── extensions/
│   ├── ext_data_sources.py      ← Cascade: BCS → CMF → BICE → Yahoo
│   ├── ext_ml_model.py          ← XGBoost: ReturnPredictor + RegimeClassifier
│   └── ext_telegram.py          ← Bot Telegram + alertas + comandos
│
├── ml/                          ← Modelos entrenados (auto-generado)
│   ├── xgb_return_model.json
│   ├── xgb_regime_model.json
│   ├── feature_names.json
│   └── model_metrics.json
│
├── data/                        ← Persistencia (auto-generado)
│   ├── decisions_history.json
│   ├── backtest_results.json
│   ├── agent_state.json
│   └── ml_preds_YYYY-MM-DD.json
│
├── reports/                     ← Reportes diarios (auto-generado)
│   ├── ipsa_report_YYYY-MM-DD.html
│   └── ipsa_data_YYYY-MM-DD.json
│
└── logs/                        ← Logs de ejecución (auto-generado)

dashboard/                       ← Next.js 14 Dashboard
├── src/
│   ├── app/
│   │   ├── page.tsx             ← Dashboard principal
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   └── api/
│   │       ├── report/latest/route.ts
│   │       └── history/route.ts
│   ├── components/
│   │   ├── MacroPanel.tsx       ← Panel macroeconómico
│   │   ├── RegimePanel.tsx      ← Régimen de mercado
│   │   ├── Top5Table.tsx        ← Tabla Top 5 con ML
│   │   ├── StockCards.tsx       ← Cards con tesis + timing + ML
│   │   ├── PortfolioChart.tsx   ← Donut pie asignación
│   │   ├── ScoreChart.tsx       ← Stacked bar factores
│   │   ├── RankedAllTable.tsx   ← Ranking universo completo
│   │   ├── AlertBanner.tsx      ← Alertas de cambio
│   │   └── HistoryPanel.tsx     ← Historial de decisiones
│   └── lib/
│       ├── types.ts             ← TypeScript types
│       └── data.ts              ← Data fetching + formatters
├── package.json
├── next.config.js
└── tailwind.config.js
```

---

## ⚡ Instalación Rápida

```bash
# ── BACKEND (Python) ──────────────────────────────────────────
cd ipsa_agent

python -m venv venv && source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate                           # Windows

pip install -r requirements.txt

mkdir -p data reports logs ml

# ── FRONTEND (Next.js) ────────────────────────────────────────
cd ../dashboard

npm install
# o: yarn install / pnpm install
```

---

## 🚀 Comandos

### Agente Python

```bash
# Análisis diario completo (con ML + Telegram si configurado)
python main_v2.py

# Primera vez: entrenar modelo ML
python main_v2.py --mode ml-train

# Análisis diario + reentrenar ML
python main_v2.py --retrain

# Solo análisis clásico (sin ML ni Telegram)
python main_v2.py --no-ml --no-telegram

# Backtesting histórico
python main_v2.py --mode backtest
python main_v2.py --mode backtest --start 2024-01-01 --end 2025-01-01

# Ver estado de fuentes de datos
python main_v2.py --mode data-status

# Configurar Telegram (genera .env)
python main_v2.py --mode setup-telegram

# Ver historial de decisiones
python main_v2.py --mode history

# Scheduler automático (09:15, días hábiles)
python scheduler.py

# Ver crontab equivalente
python scheduler.py --crontab
```

### Dashboard Next.js

```bash
cd dashboard

# Desarrollo
npm run dev    # → http://localhost:3001

# Producción
npm run build
npm start
```

---

## ⚙️ Configuración Telegram

```bash
# 1. Crear bot con @BotFather → obtener token
# 2. Escribirle al bot para obtener chat_id:
#    https://api.telegram.org/bot{TOKEN}/getUpdates

# 3. Crear .env en ipsa_agent/
python main_v2.py --mode setup-telegram

# 4. Editar .env:
TELEGRAM_TOKEN=123456789:AAxxxxxx...
TELEGRAM_CHAT_ID=-1001234567890

# 5. Test
python -c "
from extensions.ext_telegram import TelegramAlerter
a = TelegramAlerter()
a.client.send_message('✅ IPSA Agent conectado!')
"
```

### Comandos del bot Telegram

| Comando | Acción |
|---------|--------|
| `/top5` | Ver Top 5 actual |
| `/macro` | USD/CLP, TPM, IPC |
| `/regime` | Régimen técnico + ML |
| `/portafolio` | Asignación porcentual |
| `/help` | Ayuda |

---

## 🤖 Modelo ML (XGBoost)

### Features (33 variables)
- **Retornos**: 1W, 1M, 3M, 6M, 12M + momentum residual
- **Volatilidad**: 21d, 63d, 126d + ratio vol corta/larga
- **RSI**: 7, 14, 28 días + normalizado
- **SMA position**: SMA20, SMA50, SMA200 + golden cross
- **MACD**: valor + histograma normalizados
- **Bollinger**: posición + ancho de bandas
- **Drawdown**: 1M, 3M, 6M
- **Volumen**: ratio vs media 21d
- **Fundamentales**: ROE, D/E, earnings growth, payout ratio, DY
- **Macro**: spread dividendos vs TPM, tasa libre de riesgo

### Modelos
- **ReturnPredictor**: XGBoost Regressor → retorno forward 21 días
- **RegimeClassifier**: XGBoost Classifier → P(BULL) sobre IPSA index

### Interpretación de métricas
- **Dir. Accuracy > 55%**: el modelo tiene valor predictivo real
- **R² > 0.05**: ajuste razonable dado el ruido de mercados
- **Nota**: con datos sintéticos Dir.Acc ~50% es esperado — con datos reales mejora

---

## 📊 Fuentes de Datos (Cascade)

| Prioridad | Fuente | Datos |
|-----------|--------|-------|
| 1 | Bolsa de Santiago | Precios EOD + en vivo |
| 2 | CMF Chile | Dividendos anunciados oficiales |
| 3 | BICE Inversiones | Cotizaciones intraday |
| 4 | Yahoo Finance | EOD histórico (fallback) |

> La Bolsa de Santiago requiere conexión desde Chile o proxy.
> Yahoo Finance funciona globalmente y cubre todos los tickers `.SN`.

---

## 🔗 Dashboard Next.js

### Variables de entorno (dashboard/)

```bash
# .env.local
NEXT_PUBLIC_AGENT_API=/api
REPORTS_DIR=/ruta/absoluta/a/ipsa_agent/reports
DATA_DIR=/ruta/absoluta/a/ipsa_agent/data
```

### Características del dashboard

- **Panel macro**: USD/CLP, TPM, IPC en tiempo real
- **Régimen de mercado**: técnico + ML con probabilidades
- **Top 5 table**: score, DY, spread, RSI, drawdown, predicción ML
- **Stock cards**: tesis, desglose de factores, timing de entrada, zona óptima
- **Portfolio chart**: pie chart con asignación Kelly
- **Score chart**: stacked bar desglosado por factor
- **Ranking completo**: universo IPSA con filtro de excluidas
- **Historial**: timeline de decisiones del agente
- **Auto-refresh**: ISR cada 5 minutos (Next.js `revalidate`)

---

## 🔧 Personalización

```python
# config.py — Ajustar parámetros clave

DEFAULT_RISK_FREE_RATE = 0.05  # TPM BCCh actual

# Pesos del score
WEIGHT_DIVIDEND = 0.40   # Prioridad dividendos vs TPM
WEIGHT_QUALITY  = 0.25   # ROE, D/E, earnings growth
WEIGHT_MOMENTUM = 0.20   # Técnico: RSI, SMA, MACD, retornos
WEIGHT_RISK     = 0.15   # Penalización por drawdown/volatilidad

# Kill conditions
MAX_DIVIDEND_YIELD = 0.15  # >15% = trampa de dividendos
MAX_PAYOUT_RATIO   = 0.90  # >90% = insostenible
MAX_DEBT_EQUITY    = 2.0   # >2x = apalancamiento alto

# Umbrales de señal
SCORE_HIGH_THRESHOLD   = 0.48  # COMPRAR
SCORE_MEDIUM_THRESHOLD = 0.35  # ESPERAR
```

---

## ⚠️ Disclaimer

Software educativo e informativo. No constituye asesoramiento financiero.
Las inversiones en valores conllevan riesgo de pérdida de capital.
Siempre consulta con un asesor financiero certificado (CMF) antes de invertir.
