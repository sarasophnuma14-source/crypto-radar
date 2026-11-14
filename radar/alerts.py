"""Alertas: panel, notificación de escritorio (macOS/Linux/Windows) y Telegram opcional."""
from __future__ import annotations
import datetime as dt
import json
import platform
import shutil
import subprocess
import urllib.parse
import urllib.request
from . import storage
from .data import _context

ICONS = {
    "NEW EARLY ENTRY": "🟢", "BREAKOUT CONFIRMATION": "🚀", "ENTRY ZONE REACHED": "🎯",
    "STOP LOSS WARNING": "⚠️", "STOP LOSS HIT": "🛑", "TAKE PROFIT REACHED": "💰",
    "DISTRIBUTION DETECTED": "🟠", "BEARISH REVERSAL": "🔻", "MARKET REGIME CHANGE": "🌐", "SYSTEM": "ℹ️",
    "MEME BREAKOUT": "🐸", "MEME STOP": "🛑", "MEME TARGET": "💰", "MEME TIME EXIT": "⏱️",
}
LABELS = {
    "NEW EARLY ENTRY": "Nueva entrada temprana", "BREAKOUT CONFIRMATION": "Ruptura confirmada",
    "ENTRY ZONE REACHED": "Precio en zona de entrada", "STOP LOSS WARNING": "Cerca del stop loss",
    "STOP LOSS HIT": "Stop loss tocado", "TAKE PROFIT REACHED": "Take profit alcanzado",
    "DISTRIBUTION DETECTED": "Distribución detectada", "BEARISH REVERSAL": "Giro bajista",
    "MARKET REGIME CHANGE": "Cambio de régimen de mercado", "SYSTEM": "Sistema",
    "MEME BREAKOUT": "Memecoin: ruptura con volumen", "MEME STOP": "Memecoin: stop tocado",
    "MEME TARGET": "Memecoin: objetivo +60% alcanzado", "MEME TIME EXIT": "Memecoin: salida por tiempo (5 días)",
}


def _desktop(title, body):
    try:
        sysname = platform.system()
        if sysname == "Darwin":
            script = 'display notification %s with title %s sound name "Glass"' % (json.dumps(body), json.dumps(title))
            subprocess.run(["osascript", "-e", script], timeout=10, capture_output=True)
        elif sysname == "Linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], timeout=10)
        elif sysname == "Windows":
            ps = ("[reflection.assembly]::loadwithpartialname('System.Windows.Forms')|Out-Null;"
                  "$n=New-Object System.Windows.Forms.NotifyIcon;$n.Icon=[System.Drawing.SystemIcons]::Information;"
                  f"$n.Visible=$true;$n.ShowBalloonTip(8000,'{title}','{body}',0);Start-Sleep 9")
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
    except Exception:
        pass


def telegram(settings, text):
    tok, chat = settings.get("telegram_bot_token"), settings.get("telegram_chat_id")
    if not tok or not chat:
        return False, "Telegram no configurado"
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text, "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/sendMessage", data=data)
        with urllib.request.urlopen(req, timeout=15, context=_context()) as r:
            ok = json.loads(r.read()).get("ok", False)
        return ok, "enviado" if ok else "Telegram rechazó el mensaje"
    except Exception as e:
        return False, str(e)


def emit(settings, kind, symbol, message, extra=None, dedupe_hours=12):
    """Registra la alerta y la envía. Evita repetir la misma alerta (tipo+símbolo) en `dedupe_hours`."""
    now = dt.datetime.now(dt.timezone.utc)
    hist = storage.read("alerts.json", []) or []
    for a in reversed(hist[-300:]):
        if a["kind"] == kind and a["symbol"] == symbol:
            if (now - dt.datetime.fromisoformat(a["at"])).total_seconds() < dedupe_hours * 3600:
                return None
            break
    alert = {"at": now.isoformat(), "kind": kind, "label": LABELS.get(kind, kind), "symbol": symbol,
             "message": message, "extra": extra or {}}
    storage.append_list("alerts.json", [alert], keep=1500)
    title = f"{ICONS.get(kind, '')} {symbol} · {LABELS.get(kind, kind)}"
    if settings.get("desktop_notifications", True):
        _desktop("Crypto Radar", f"{title}: {message}")
    telegram(settings, f"{title}\n{message}\n\nCrypto Radar · solo análisis, no es asesoría financiera.")
    return alert
