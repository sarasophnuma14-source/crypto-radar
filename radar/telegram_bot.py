"""Bot de Telegram para cuentas de usuario (modo SaaS).

  * Vincular: en el panel el usuario pide un código de 8 caracteres (válido 15 min) y envía «/start CODIGO» al bot.
  * Comandos: /estado /top /regimen /cartera /alertas on|off /baja /ayuda
  * Reparto: las alertas de mercado se envían a cada usuario vinculado cuyo plan incluye Telegram y que las tenga activas.
Funciona con long polling (getUpdates), sin webhook ni dominio propio. Token global en TELEGRAM_BOT_TOKEN.
"""
from __future__ import annotations
import json
import os
import secrets
import threading
import time
import traceback
import urllib.parse
import urllib.request
from . import db, auth, storage, notify
from .data import _context

MARKET_KINDS = {"PRE-EXPLOSION", "BREAKOUT CONFIRMATION", "ENTRY ZONE REACHED", "MARKET REGIME CHANGE", "RISK",
                "DISTRIBUTION DETECTED", "DAILY SUMMARY", "WEEKLY SUMMARY", "MEME BREAKOUT"}
HELP = ("Comandos:\n/estado – veredicto y régimen actual\n/top – 5 mejores oportunidades tempranas\n"
        "/regimen – régimen de mercado y reglas\n/cartera – tus posiciones y decisión de salida\n"
        "/alertas on | off – activar o pausar alertas\n/baja – desvincular este chat\n\n" + notify.DISCLAIMER)


def token():
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def api(method, params, timeout=35):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token()}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=timeout, context=_context()) as r:
        return json.loads(r.read())


def send(chat_id, text):
    try:
        return api("sendMessage", {"chat_id": chat_id, "text": text[:4000], "disable_web_page_preview": "true"}, 15).get("ok")
    except Exception:
        return False


def new_link_code(user_id):
    code = secrets.token_hex(4).upper()
    db.execute("DELETE FROM telegram_links WHERE user_id = ? OR expires_at < ?", (user_id, time.time()))
    db.execute("INSERT INTO telegram_links(code, user_id, expires_at) VALUES (?, ?, ?)", (code, user_id, time.time() + 900))
    return code


def _user_by_chat(chat_id):
    r = db.one("SELECT id FROM users WHERE telegram_chat_id = ?", (str(chat_id),))
    return auth.get_user(r["id"]) if r else None


def handle(msg):
    """Procesa un mensaje entrante y devuelve la respuesta (o None)."""
    chat = str((msg.get("chat") or {}).get("id") or "")
    text = (msg.get("text") or "").strip()
    if not chat or not text.startswith("/"):
        return None
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    arg = arg.strip()
    if cmd == "/start":
        if not arg:
            return "Hola. Para recibir alertas, abre Crypto Radar → Alertas → «Vincular Telegram» y envía aquí «/start CÓDIGO».\n\n" + HELP
        row = db.one("SELECT * FROM telegram_links WHERE code = ?", (arg.upper()[:12],))
        if not row or row["expires_at"] < time.time():
            return "Código no válido o vencido. Genera uno nuevo en el panel."
        db.execute("UPDATE users SET telegram_chat_id = NULL WHERE telegram_chat_id = ?", (chat,))
        db.execute("UPDATE users SET telegram_chat_id = ? WHERE id = ?", (chat, row["user_id"]))
        db.execute("DELETE FROM telegram_links WHERE code = ?", (row["code"],))
        auth.log(row["user_id"], "telegram_linked", None)
        u = auth.get_user(row["user_id"])
        extra = "" if auth.features(u)["telegram"] else "\nTu plan actual (Libre) no incluye alertas automáticas; los comandos sí funcionan."
        return "✅ Chat vinculado a tu cuenta." + extra + "\n\n" + HELP
    u = _user_by_chat(chat)
    rep = storage.read("latest.json", {}) or {}
    if cmd == "/ayuda" or cmd == "/help":
        return HELP
    if cmd == "/estado":
        if not rep:
            return "Aún no hay un escaneo completo."
        m = rep["market"]
        return (f"{rep['verdict']}\n{rep['verdict_text']}\nRégimen {m.get('regime_label', m['regime'])} · BTC {notify.fmt(m['btc_price'])}\n"
                f"Último escaneo: {rep['at'][:16].replace('T', ' ')} UTC")
    if cmd == "/top":
        if not rep:
            return "Aún no hay un escaneo completo."
        lim = auth.features(u)["ranking_limit"] if u else 3
        rows = rep.get("ranking", [])[:min(5, lim)]
        if not rows:
            return "Ninguna oportunidad cumple las reglas del régimen actual."
        out = [f"{r['rank']}. {r['symbol']} · {r['phase_label']} · {r['score']:.0f} · {r['action']}\n"
               f"   zona {notify.fmt(r['entry_low'])}–{notify.fmt(r['entry_high'])} · stop {notify.fmt(r['stop'])} · TP1 {notify.fmt(r['tp1'])}"
               for r in rows]
        if lim < 5:
            out.append("(Plan Libre: top 3. Pro muestra el ranking completo.)")
        return "\n".join(out)
    if cmd == "/regimen":
        if not rep:
            return "Aún no hay un escaneo completo."
        m = rep["market"]; pol = m.get("policy") or {}
        return (f"Régimen {m.get('regime_label', m['regime'])}\n" + "\n".join(f"• {x}" for x in m.get("regime_reasons", [])[:4]) +
                f"\nReglas: puntaje mínimo {pol.get('min_score')}, altcoins máx. {pol.get('max_alt_exposure')}%, tamaño x{pol.get('size_mult')}")
    if not u:
        return "Este chat no está vinculado. Genera un código en el panel y envía «/start CÓDIGO»."
    if cmd == "/cartera":
        from . import multiuser
        ps = multiuser.list_positions(u["id"], "OPEN")
        if not ps:
            return "No tienes posiciones abiertas registradas."
        return "\n".join(f"{p['symbol']} · entrada {notify.fmt(p['entry'])} · {notify.pct(p.get('pnl_pct'))} · "
                         f"{(p.get('exit') or {}).get('decision', 'MANTENER')}" for p in ps[:15])
    if cmd == "/alertas":
        on = arg.lower() not in ("off", "no", "0")
        auth.save_user_settings(u["id"], {"alerts_telegram": on})
        return "🔔 Alertas activadas." if on else "🔕 Alertas pausadas. Envía /alertas on para reactivarlas."
    if cmd == "/baja":
        db.execute("UPDATE users SET telegram_chat_id = NULL WHERE id = ?", (u["id"],))
        auth.log(u["id"], "telegram_unlinked", None)
        return "Chat desvinculado. Ya no recibirás alertas aquí."
    return "Comando no reconocido.\n\n" + HELP


def fanout(kind, text):
    """Envía una alerta de mercado a los usuarios con plan que incluye Telegram y alertas activas."""
    if not token() or kind not in MARKET_KINDS:
        return 0
    n = 0
    for r in db.all_("SELECT id FROM users WHERE telegram_chat_id IS NOT NULL AND disabled = 0", ()):
        u = auth.get_user(r["id"])
        if not u or not auth.features(u)["telegram"] or u["settings"].get("alerts_telegram") is False:
            continue
        if send(u["telegram_chat_id"], text):
            n += 1
        time.sleep(0.05)          # Telegram: ~30 mensajes/s como máximo
    return n


def poll_forever():
    if not token():
        return
    offset = 0
    while True:
        try:
            r = api("getUpdates", {"offset": offset, "timeout": 30, "allowed_updates": json.dumps(["message"])}, 40)
            for up in r.get("result", []):
                offset = up["update_id"] + 1
                msg = up.get("message") or {}
                try:
                    reply = handle(msg)
                except Exception:
                    traceback.print_exc(); reply = "Error interno; inténtalo más tarde."
                if reply:
                    send(msg["chat"]["id"], reply)
        except Exception:
            time.sleep(10)


def start():
    if token():
        threading.Thread(target=poll_forever, daemon=True).start()
