# IPSA Agent — Changelog

## v2.1.0 — 2026-04-01 (Hotfix + Mejoras)

### 🐛 Bug Fixes Críticos
- **FIX 1** `config.py`: Eliminados 5 tickers delisted (`SECURITY.SN`, `CONCHA.SN`, `SMCHILE.SN`, `NUEVAPOLAR.SN`, `HITES.SN`) que causaban timeouts de 60+ segundos
- **FIX 2** `report_generator.py`: `NaN`/`Infinity` en DataFrame ahora se convierten a `null` antes de serializar → el dashboard ya no falla con `SyntaxError: Unexpected token 'N'`
- **FIX 3** `ext_data_sources.py`: Retry exponencial en todas las peticiones HTTP; validación de JSON antes de parsear; múltiples endpoints BCS con fallback
- **FIX 4** `dashboard/lib/data.ts`: Lectura directa de archivo en SSR (Server Components) — elimina `TypeError: Invalid URL` en `next build`
- **FIX 5** `dashboard/api/route.ts`: Sanitización de `NaN`/`Infinity` en la API route antes de enviar JSON al cliente
- **FIX 6** `dashboard/page.tsx`: `dynamic = 'force-dynamic'` — evita build estático fallido; UI graceful cuando Top 5 está vacío
- **FIX 7** `scoring.py`: `compute_unified_score()` crasheaba con `TypeError` si algún factor era `None`

### ✨ Nuevas Funcionalidades
- **`price_cache.py`**: Caché local en Parquet — segunda ejecución en <30s en vez de 2-3 min
- **`health_server.py`**: Servidor HTTP en puerto 8765 con `/health`, `/status`, `/metrics`, `/last-report`
- **`tests.py`**: 49 tests unitarios e integración cubriendo: JSON, factores, kill conditions, score, caché, config, pipeline completo

### ⚙️ Mejoras de Configuración
- Kill conditions recalibradas: `DY < 18%`, `Payout < 95%`, `D/E < 2.5`, `RSI < 80`
- Señales ajustadas para datos reales: `COMPRAR >= 0.42`, `ESPERAR >= 0.28`

### 🖥️ Nuevos comandos CLI
```bash
python main_v2.py --mode test          # Ejecutar suite de tests
python main_v2.py --mode cache-status  # Ver estado del caché
python main_v2.py --mode cache-clear   # Limpiar caché
python main_v2.py --mode health        # Iniciar health server
python main_v2.py --no-cache           # Deshabilitar caché
```

---

## v2.0.0 — 2026-03-31 (Release inicial completo)
- Pipeline de 6 pasos con análisis cuantitativo completo
- XGBoost ReturnPredictor + RegimeClassifier
- Cascade de datos: BCS → CMF → Yahoo Finance
- Bot Telegram con alertas y comandos interactivos
- Dashboard Next.js 14 (dark theme, Recharts)
- Backtesting walk-forward con métricas Sharpe/Drawdown
- Scheduler automático (días hábiles chilenos)

## v1.0.0 — 2026-03-30 (MVP)
- Motor de análisis con 4 factores: Dividendos, Calidad, Momentum, Riesgo
- Score unificado con pesos configurables
- Kill conditions automáticas
- Reportes HTML dark + JSON
