"""
IPSA Agent — Extension 3: Alertas Telegram
Bot que envía el reporte diario, stop loss y cambios de Top 5.

Setup:
1. Crear bot con @BotFather en Telegram → obtener TELEGRAM_TOKEN
2. Iniciar conversación con el bot → obtener TELEGRAM_CHAT_ID
3. Configurar en .env o variables de entorno

Uso:
    from extensions.ext_telegram import TelegramAlerter
    alerter = TelegramAlerter(token=TOKEN, chat_id=CHAT_ID)
    alerter.send_daily_report(top5, macro, regime)
"""

import logging
import os
import textwrap
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────
#  CLIENTE TELEGRAM BASE
# ─────────────────────────────────────────────────────────────────

class TelegramClient:
    """Cliente liviano para la API de Telegram Bot."""

    BASE_URL = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token: str, default_chat_id: str = ""):
        self.token   = token
        self.chat_id = default_chat_id
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "IPSA-Agent/1.0"

    def _url(self, method: str) -> str:
        return self.BASE_URL.format(token=self.token, method=method)

    def send_message(
        self,
        text:      str,
        chat_id:   str = "",
        parse_mode: str = "HTML",
        disable_preview: bool = True,
    ) -> bool:
        """Envía mensaje de texto."""
        target = chat_id or self.chat_id
        if not target or not self.token:
            logger.warning("[TG] Token o chat_id no configurados")
            return False

        # Telegram tiene límite de 4096 chars por mensaje
        chunks = _split_message(text, 4096)
        success = True
        for chunk in chunks:
            try:
                resp = self._session.post(
                    self._url("sendMessage"),
                    json={
                        "chat_id":                  target,
                        "text":                     chunk,
                        "parse_mode":               parse_mode,
                        "disable_web_page_preview": disable_preview,
                    },
                    timeout=15,
                )
                if not resp.json().get("ok"):
                    logger.warning(f"[TG] Error API: {resp.json()}")
                    success = False
            except Exception as e:
                logger.error(f"[TG] Error send_message: {e}")
                success = False
        return success

    def send_document(
        self,
        file_path: str,
        caption:   str = "",
        chat_id:   str = "",
    ) -> bool:
        """Envía archivo (PDF, HTML, etc.)."""
        target = chat_id or self.chat_id
        if not os.path.exists(file_path):
            logger.warning(f"[TG] Archivo no existe: {file_path}")
            return False
        try:
            with open(file_path, "rb") as f:
                resp = self._session.post(
                    self._url("sendDocument"),
                    data={"chat_id": target, "caption": caption[:1024]},
                    files={"document": f},
                    timeout=60,
                )
            return resp.json().get("ok", False)
        except Exception as e:
            logger.error(f"[TG] Error send_document: {e}")
            return False

    def send_photo(self, image_path: str, caption: str = "", chat_id: str = "") -> bool:
        """Envía imagen."""
        target = chat_id or self.chat_id
        try:
            with open(image_path, "rb") as f:
                resp = self._session.post(
                    self._url("sendPhoto"),
                    data={"chat_id": target, "caption": caption[:1024]},
                    files={"photo": f},
                    timeout=30,
                )
            return resp.json().get("ok", False)
        except Exception as e:
            logger.error(f"[TG] Error send_photo: {e}")
            return False

    def test_connection(self) -> bool:
        """Verifica que el token sea válido."""
        try:
            resp = self._session.get(self._url("getMe"), timeout=10)
            data = resp.json()
            if data.get("ok"):
                bot_name = data["result"].get("username")
                logger.info(f"[TG] Conectado como @{bot_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"[TG] Error conexión: {e}")
            return False

    def get_updates(self, offset: int = 0) -> List[Dict]:
        """Obtiene mensajes entrantes (para implementar comandos)."""
        try:
            resp = self._session.get(
                self._url("getUpdates"),
                params={"offset": offset, "timeout": 5},
                timeout=15,
            )
            return resp.json().get("result", [])
        except Exception:
            return []


# ─────────────────────────────────────────────────────────────────
#  FORMATEADORES DE MENSAJES
# ─────────────────────────────────────────────────────────────────

def format_daily_report(
    top5:      pd.DataFrame,
    macro:     Dict,
    regime:    Dict,
    changes:   Dict,
    date_str:  str,
    ml_preds:  Optional[Dict] = None,
) -> str:
    """Genera el mensaje HTML del reporte diario para Telegram."""

    usdclp  = macro.get("usdclp")
    rfr     = (macro.get("risk_free_rate") or 0) * 100
    infl    = (macro.get("inflation") or 0) * 100
    regime_ = regime.get("regime", "NEUTRAL")
    mom3m   = regime.get("ipsa_momentum_3m")

    regime_emoji = {"BULL": "🐂", "BEAR": "🐻", "NEUTRAL": "⚖️"}.get(regime_, "⚖️")
    regime_ml    = ""
    if ml_preds:
        r_ml = ml_preds.get("__regime__", {})
        if r_ml:
            regime_ml = (
                f"\n🤖 <b>Régimen ML:</b> {r_ml.get('regime_ml','N/D')} "
                f"(P(BULL)={r_ml.get('regime_prob_bull',0.5):.0%})"
            )

    lines = [
        f"🇨🇱 <b>IPSA Agent — {date_str}</b>",
        "",
        "📊 <b>CONTEXTO MACRO</b>",
        f"├ USD/CLP: <b>{usdclp:,.2f}</b>" if usdclp else "├ USD/CLP: N/D",
        f"├ TPM: <b>{rfr:.2f}%</b>",
        f"├ IPC: <b>{infl:.2f}%</b>",
        f"└ Régimen: {regime_emoji} <b>{regime_}</b>"
        + (f" ({mom3m:+.1f}%)" if mom3m is not None else "")
        + regime_ml,
    ]

    # Alerta cambios
    if changes.get("changed"):
        new_e = ", ".join(changes.get("new_entries", []))
        exits = ", ".join(changes.get("exits", []))
        lines += [
            "",
            "🚨 <b>CAMBIO EN TOP 5</b>",
            f"├ ➕ Entran: {new_e or 'ninguno'}",
            f"└ ➖ Salen: {exits or 'ninguno'}",
        ]

    lines += ["", "🔥 <b>TOP 5 HOY</b>", ""]

    for i, row in top5.iterrows():
        ticker = row.get("ticker", "")
        name   = row.get("name", ticker)
        score  = row.get("score", 0)
        dy     = (row.get("dividend_yield") or 0) * 100
        spread = (row.get("spread") or 0) * 100
        rsi    = row.get("rsi") or 0
        dd     = row.get("max_drawdown") or 0
        signal = row.get("signal", "")
        price  = row.get("current_price") or 0
        sl     = row.get("stop_loss") or 0
        weight = row.get("weight_pct") or 0

        sig_emoji = "🟢" if "COMPRAR" in signal else "🟡" if "ESPERAR" in signal else "🔴"

        ml_line = ""
        if ml_preds and ticker in ml_preds:
            mp = ml_preds[ticker]
            ml_line = (
                f"\n    🤖 ML: {mp.get('predicted_return_21d',0):+.1f}% "
                f"({mp.get('confidence','?')}) — {mp.get('direction','?')}"
            )

        lines += [
            f"{i+1}. <b>{ticker}</b> — {sig_emoji} {signal}",
            f"   Score: <code>{score:.4f}</code> | DY: {dy:.1f}% | Spread: {spread:+.1f}%",
            f"   RSI: {rsi:.0f} | DD6M: {dd:.1f}% | Peso: {weight:.0f}%",
            f"   💰 Precio: <b>CLP ${price:,.0f}</b> | StopLoss: ${sl:,.0f}"
            + ml_line,
            "",
        ]

    lines += [
        "⚖️ <b>ASIGNACIÓN</b>",
    ]
    for i, row in top5.iterrows():
        w = row.get("weight_pct") or 0
        bar = "▓" * int(w / 5)
        lines.append(f"  {row.get('ticker',''):<14} {w:.0f}%  {bar}")

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "<i>IPSA Agent v2.0 — Solo informativo</i>",
    ]

    return "\n".join(lines)


def format_stop_loss_alert(
    ticker:        str,
    current_price: float,
    stop_loss:     float,
    entry_price:   float,
) -> str:
    """Mensaje de alerta cuando se activa un stop loss."""
    pnl = (current_price - entry_price) / entry_price * 100
    return (
        f"🚨 <b>STOP LOSS ACTIVADO</b>\n\n"
        f"Acción: <b>{ticker}</b>\n"
        f"Precio actual: <b>CLP ${current_price:,.0f}</b>\n"
        f"Stop loss: <b>CLP ${stop_loss:,.0f}</b>\n"
        f"Precio entrada: CLP ${entry_price:,.0f}\n"
        f"P&L: <b>{pnl:+.1f}%</b>\n\n"
        f"⚠️ Considera liquidar posición o ajustar stop."
    )


def format_regime_change_alert(old_regime: str, new_regime: str, confidence: str) -> str:
    """Alerta cuando cambia el régimen de mercado."""
    old_e = {"BULL": "🐂", "BEAR": "🐻", "NEUTRAL": "⚖️"}.get(old_regime, "")
    new_e = {"BULL": "🐂", "BEAR": "🐻", "NEUTRAL": "⚖️"}.get(new_regime, "")
    return (
        f"🔄 <b>CAMBIO DE RÉGIMEN IPSA</b>\n\n"
        f"{old_e} {old_regime} → {new_e} <b>{new_regime}</b>\n"
        f"Confianza: {confidence}\n\n"
        f"{'📈 Contexto favorable — aumentar exposición' if new_regime == 'BULL' else '📉 Contexto adverso — reducir exposición y ajustar stops'}"
    )


def format_ml_predictions(ml_preds: Dict, top5_tickers: List[str]) -> str:
    """Resumen de predicciones ML para el Top 5."""
    lines = ["🤖 <b>PREDICCIONES ML (21 días)</b>", ""]
    for t in top5_tickers:
        pred = ml_preds.get(t)
        if pred:
            ret  = pred.get("predicted_return_21d", 0)
            conf = pred.get("confidence", "?")
            dir_ = pred.get("direction", "?")
            sig  = pred.get("signal_ml", "")
            emoji = "📈" if ret > 0 else "📉"
            lines.append(
                f"{emoji} <b>{t}</b>: {ret:+.1f}% ({conf}) — {sig}"
            )
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
#  ALERTER PRINCIPAL
# ─────────────────────────────────────────────────────────────────

class TelegramAlerter:
    """
    Gestor de alertas Telegram para el IPSA Agent.
    Centraliza el envío de reportes, alertas y notificaciones.
    """

    def __init__(
        self,
        token:   str = "",
        chat_id: str = "",
    ):
        # Fallback a variables de entorno
        self.token   = token or os.environ.get("TELEGRAM_TOKEN", "")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")
        self.client  = TelegramClient(self.token, self.chat_id)
        self.enabled = bool(self.token and self.chat_id)

        if not self.enabled:
            logger.warning(
                "[TG] Telegram no configurado. "
                "Set TELEGRAM_TOKEN y TELEGRAM_CHAT_ID en .env"
            )

    def send_daily_report(
        self,
        top5:      pd.DataFrame,
        macro:     Dict,
        regime:    Dict,
        changes:   Dict,
        date_str:  str,
        ml_preds:  Optional[Dict] = None,
        html_path: Optional[str]  = None,
    ) -> bool:
        """Envía el reporte diario completo."""
        if not self.enabled:
            return False

        msg = format_daily_report(top5, macro, regime, changes, date_str, ml_preds)
        ok  = self.client.send_message(msg)

        if ok and ml_preds:
            top5_tickers = top5["ticker"].tolist() if not top5.empty else []
            ml_msg = format_ml_predictions(ml_preds, top5_tickers)
            self.client.send_message(ml_msg)

        if ok and html_path and os.path.exists(html_path):
            self.client.send_document(
                html_path,
                caption=f"📄 Reporte completo IPSA — {date_str}",
            )

        return ok

    def send_stop_loss_alert(
        self,
        ticker:        str,
        current_price: float,
        stop_loss:     float,
        entry_price:   float,
    ) -> bool:
        """Alerta inmediata de stop loss activado."""
        if not self.enabled:
            return False
        msg = format_stop_loss_alert(ticker, current_price, stop_loss, entry_price)
        return self.client.send_message(msg)

    def send_top5_change_alert(self, changes: Dict) -> bool:
        """Alerta cuando el Top 5 cambia significativamente."""
        if not self.enabled or not changes.get("changed"):
            return False
        alert = changes.get("alert", "")
        if alert:
            return self.client.send_message(f"🚨 <b>{alert}</b>")
        return False

    def send_regime_change(
        self,
        old_regime: str,
        new_regime: str,
        confidence: str = "MEDIA",
    ) -> bool:
        """Alerta de cambio de régimen de mercado."""
        if not self.enabled or old_regime == new_regime:
            return False
        msg = format_regime_change_alert(old_regime, new_regime, confidence)
        return self.client.send_message(msg)

    def send_error_alert(self, error_msg: str) -> bool:
        """Notifica errores críticos del agente."""
        if not self.enabled:
            return False
        msg = f"⛔ <b>IPSA Agent ERROR</b>\n\n<code>{error_msg[:500]}</code>"
        return self.client.send_message(msg)

    def send_backtest_results(self, metrics: Dict) -> bool:
        """Envía resumen de backtesting."""
        if not self.enabled:
            return False
        lines = [
            "📈 <b>BACKTEST RESULTS</b>",
            "",
            f"Período: {metrics.get('start_date')} → {metrics.get('end_date')}",
            f"Retorno total:   <b>{metrics.get('total_return',0)*100:.1f}%</b>",
            f"Retorno anual:   {metrics.get('annual_return',0)*100:.1f}%",
            f"Sharpe Ratio:    {metrics.get('sharpe_ratio',0):.3f}",
            f"Max Drawdown:    {metrics.get('max_drawdown',0)*100:.1f}%",
            f"Win Rate:        {metrics.get('win_rate',0)*100:.1f}%",
            f"Alpha vs IPSA:   {metrics.get('alpha',0)*100:.1f}%",
        ]
        return self.client.send_message("\n".join(lines))

    def monitor_stop_losses(
        self,
        portfolio:     Dict[str, Dict],
        current_prices: Dict[str, float],
    ) -> List[str]:
        """
        Verifica si alguna posición del portafolio activó su stop loss.
        portfolio = {ticker: {'entry_price': X, 'stop_loss': Y}}
        Retorna lista de tickers con stop activado.
        """
        triggered = []
        for ticker, pos in portfolio.items():
            current = current_prices.get(ticker)
            sl      = pos.get("stop_loss")
            entry   = pos.get("entry_price")
            if current and sl and current <= sl:
                triggered.append(ticker)
                self.send_stop_loss_alert(ticker, current, sl, entry or sl)
        return triggered


# ─────────────────────────────────────────────────────────────────
#  COMMAND HANDLER (Bot interactivo básico)
# ─────────────────────────────────────────────────────────────────

class TelegramCommandHandler:
    """
    Maneja comandos entrantes del bot.
    Permite consultar el Top 5 actual, régimen y portafolio vía Telegram.
    """

    COMMANDS = {
        "/top5":     "Ver Top 5 actual",
        "/macro":    "Ver datos macroeconómicos",
        "/portafolio": "Ver asignación actual",
        "/regime":   "Ver régimen de mercado",
        "/help":     "Mostrar ayuda",
    }

    def __init__(self, alerter: TelegramAlerter):
        self.alerter = alerter
        self.client  = alerter.client
        self._offset = 0
        self._state  = {}   # datos más recientes del agente

    def update_state(self, top5: pd.DataFrame, macro: Dict, regime: Dict):
        """Actualiza el estado interno con los datos más recientes."""
        self._state = {"top5": top5, "macro": macro, "regime": regime}

    def poll_and_handle(self):
        """Procesa mensajes entrantes. Llamar en loop o en cada ejecución."""
        updates = self.client.get_updates(offset=self._offset)
        for upd in updates:
            self._offset = upd["update_id"] + 1
            msg = upd.get("message", {})
            text = msg.get("text", "")
            chat_id = str(msg.get("chat", {}).get("id", ""))
            if text and chat_id:
                self._handle_command(text.strip(), chat_id)

    def _handle_command(self, cmd: str, chat_id: str):
        """Despacha comandos recibidos."""
        state = self._state
        if not state:
            self.client.send_message(
                "⏳ Agente aún no ha ejecutado análisis hoy.",
                chat_id=chat_id,
            )
            return

        if "/top5" in cmd:
            top5   = state.get("top5", pd.DataFrame())
            macro  = state.get("macro", {})
            regime = state.get("regime", {})
            msg = format_daily_report(
                top5, macro, regime, {"changed": False},
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
            self.client.send_message(msg, chat_id=chat_id)

        elif "/macro" in cmd:
            macro = state.get("macro", {})
            lines = [
                "📊 <b>MACRO ACTUAL</b>",
                f"USD/CLP: {macro.get('usdclp','N/D')}",
                f"TPM:     {(macro.get('risk_free_rate',0))*100:.2f}%",
                f"IPC:     {(macro.get('inflation',0))*100:.2f}%",
            ]
            self.client.send_message("\n".join(lines), chat_id=chat_id)

        elif "/regime" in cmd:
            r = state.get("regime", {})
            msg = (
                f"📈 Régimen: <b>{r.get('regime','N/D')}</b>\n"
                f"Confianza: {r.get('confidence','?')}\n"
                f"Momentum 3M: {r.get('ipsa_momentum_3m','?')}%"
            )
            self.client.send_message(msg, chat_id=chat_id)

        elif "/portafolio" in cmd:
            top5 = state.get("top5", pd.DataFrame())
            if top5.empty:
                self.client.send_message("Sin datos de portafolio.", chat_id=chat_id)
                return
            lines = ["⚖️ <b>ASIGNACIÓN ACTUAL</b>", ""]
            for _, row in top5.iterrows():
                w = row.get("weight_pct") or 0
                lines.append(f"• <b>{row['ticker']}</b>: {w:.0f}%")
            self.client.send_message("\n".join(lines), chat_id=chat_id)

        elif "/help" in cmd:
            lines = ["🤖 <b>IPSA Agent — Comandos</b>", ""]
            for c, d in self.COMMANDS.items():
                lines.append(f"  {c} — {d}")
            self.client.send_message("\n".join(lines), chat_id=chat_id)

        else:
            self.client.send_message(
                "Comando no reconocido. Usa /help",
                chat_id=chat_id,
            )


# ─────────────────────────────────────────────────────────────────
#  SETUP HELPER
# ─────────────────────────────────────────────────────────────────

def setup_telegram_env():
    """Genera el archivo .env con las variables necesarias."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), ".env"
    )
    if os.path.exists(env_path):
        print(f"⚠️  .env ya existe: {env_path}")
        return

    content = """# IPSA Agent - Variables de Entorno
# ─────────────────────────────────────────────────────────────
# Telegram Bot Configuration
# 1. Crear bot con @BotFather en Telegram
# 2. Escribirle al bot y obtener chat_id en https://api.telegram.org/bot{TOKEN}/getUpdates
TELEGRAM_TOKEN=
TELEGRAM_CHAT_ID=

# CMF Chile API Key (registrar en https://api.cmfchile.cl)
CMF_API_TOKEN=

# Configuración del agente
RISK_FREE_RATE=0.05
RUN_HOUR=9
RUN_MINUTE=15
"""
    with open(env_path, "w") as f:
        f.write(content)
    print(f"✅ .env creado en {env_path}")
    print("   Configura TELEGRAM_TOKEN y TELEGRAM_CHAT_ID antes de usar.")


# ─────────────────────────────────────────────────────────────────
#  UTILIDADES
# ─────────────────────────────────────────────────────────────────

def _split_message(text: str, max_length: int = 4096) -> List[str]:
    """Divide mensajes largos respetando el límite de Telegram."""
    if len(text) <= max_length:
        return [text]
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, max_length)
        if split_at == -1:
            split_at = max_length
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks
