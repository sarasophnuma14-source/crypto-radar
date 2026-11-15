"""Datos por usuario en modo SaaS: posiciones (cada usuario ve solo las suyas) y su Exit Intelligence tras cada escaneo."""
from __future__ import annotations
import json
import time
import uuid
from . import db, auth, notify
from .quant import exits

FIELDS = ("symbol", "entry", "qty", "stop", "tp1", "tp2", "tp3", "notes", "paper")


def list_positions(user_id, status=None):
    q = "SELECT data FROM positions WHERE user_id = ?" + (" AND status = ?" if status else "") + " ORDER BY updated_at DESC"
    rows = db.all_(q, (user_id, status) if status else (user_id,))
    return [json.loads(r["data"]) for r in rows]


def _save(user_id, p):
    p["updated"] = time.time()
    db.execute("UPDATE positions SET status = ?, data = ?, updated_at = ? WHERE id = ? AND user_id = ?",
               (p["status"], json.dumps(p, default=str), p["updated"], p["id"], user_id))


def add_position(user_id, b, plan=None):
    plan = plan or {}
    p = {"id": uuid.uuid4().hex[:10], "symbol": b["symbol"], "entry": b["entry"], "qty": b.get("qty") or 0,
         "stop": b.get("stop") or plan.get("stop"), "tp1": b.get("tp1") or plan.get("tp1"),
         "tp2": b.get("tp2") or plan.get("tp2"), "tp3": b.get("tp3") or plan.get("tp3"),
         "notes": str(b.get("notes", ""))[:300], "paper": bool(b.get("paper", True)), "status": "OPEN", "hits": [],
         "opened_at": time.time()}
    if len(list_positions(user_id, "OPEN")) >= 50:
        raise auth.AuthError("Máximo 50 posiciones abiertas")
    db.execute("INSERT INTO positions(id, user_id, status, data, updated_at) VALUES (?, ?, ?, ?, ?)",
               (p["id"], user_id, "OPEN", json.dumps(p), time.time()))
    auth.log(user_id, "position_add", {"symbol": p["symbol"]})
    return p


def get_position(user_id, pid):
    r = db.one("SELECT data FROM positions WHERE id = ? AND user_id = ?", (pid, user_id))   # aislamiento por usuario
    return json.loads(r["data"]) if r else None


def act(user_id, pid, action, b):
    p = get_position(user_id, pid)
    if not p:
        raise auth.AuthError("Posición no encontrada", 404)
    if action == "close":
        p["status"] = "CLOSED"; p["exit_price"] = b.get("price") or p.get("last_price"); p["closed_at"] = time.time()
        if p["exit_price"]:
            p["pnl_pct"] = (p["exit_price"] / p["entry"] - 1) * 100
        _save(user_id, p)
    elif action == "delete":
        db.execute("DELETE FROM positions WHERE id = ? AND user_id = ?", (pid, user_id))
    elif action == "update":
        for k in ("stop", "tp1", "tp2", "tp3", "qty"):
            if b.get(k) is not None:
                p[k] = b[k]
        _save(user_id, p)
    else:
        raise auth.AuthError("Acción no válida")
    auth.log(user_id, "position_" + action, {"id": pid})
    return True


def after_scan(report, feats, regime_name):
    """Tras cada escaneo: precio, P&L y decisión de salida para las posiciones abiertas de TODOS los usuarios.
    Solo avisa por Telegram a quien tenga plan con salidas y Telegram, y solo cuando la decisión cambia."""
    from . import telegram_bot
    rows = db.all_("SELECT user_id, data FROM positions WHERE status = 'OPEN'", ())
    for r in rows:
        p = json.loads(r["data"]); f = feats.get(p["symbol"])
        if f is None:
            continue
        i = len(f.c) - 1
        price = f.c[i]
        p["last_price"] = price
        p["pnl_pct"] = (price / p["entry"] - 1) * 100
        p["highest_close"] = max(p.get("highest_close") or p["entry"], price)
        stop = p.get("stop") or p["entry"] * 0.9
        d = exits.decide(f, i, {"entry": p["entry"], "stop": stop, "highest_close": p["highest_close"]}, regime_name)
        prev = (p.get("exit") or {}).get("decision")
        p["exit"] = d
        _save(r["user_id"], p)
        if d["decision"] != "MANTENER" and d["decision"] != prev:
            u = auth.get_user(r["user_id"])
            if u and u.get("telegram_chat_id") and auth.features(u)["exits"] and u["settings"].get("alerts_telegram") is not False:
                a = {"price": price, "exit": d, "quality": None}
                telegram_bot.send(u["telegram_chat_id"], f"🚪 {p['symbol']} · Decisión de salida\n" + notify.exit_text(p, a)
                                  + "\n\n" + notify.DISCLAIMER)
