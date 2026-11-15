"""Cuentas de usuario: registro, inicio de sesión, sesiones, CSRF, límites de intentos y registro de actividad.

  * Contraseñas con scrypt (sal aleatoria de 16 bytes, n=2^14, r=8, p=1) y comparación en tiempo constante.
  * Sesión: token aleatorio de 32 bytes en cookie HttpOnly + SameSite=Lax (+ Secure en HTTPS); en la base solo se
    guarda su SHA-256. Caduca a los 14 días. Se rota en cada inicio de sesión.
  * CSRF: token por sesión que el panel envía en la cabecera X-CSRF-Token en cada petición que cambia datos.
  * Bloqueo: 5 fallos seguidos bloquean la cuenta 15 min; además, límite por IP.
  * El plan de pago SOLO lo cambia billing.py tras un pago verificado con el proveedor (o un admin, registrado).
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from . import db

SESSION_DAYS = 14
LOCK_AFTER, LOCK_S = 5, 15 * 60
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)
PLANS = {
    "free": {"label": "Libre", "ranking_limit": 3, "telegram": False, "portfolio": False, "exits": False, "memes": False},
    "pro": {"label": "Pro", "ranking_limit": 20, "telegram": True, "portfolio": True, "exits": True, "memes": True},
    "elite": {"label": "Élite", "ranking_limit": 20, "telegram": True, "portfolio": True, "exits": True, "memes": True,
              "backtest": True},
}
_rate = {}


class AuthError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return f"scrypt$16384$8$1${salt.hex()}${h.hex()}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, h = stored.split("$")
        if algo != "scrypt":
            return False
        got = hashlib.scrypt(pw.encode("utf-8"), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p), dklen=len(h) // 2)
        return hmac.compare_digest(got.hex(), h)
    except Exception:
        return False


def rate_limited(key, limit, window_s):
    """True si `key` superó `limit` eventos en `window_s` segundos (y registra este evento)."""
    t = time.time()
    ev = [x for x in _rate.get(key, []) if t - x < window_s]
    blocked = len(ev) >= limit
    if not blocked:
        ev.append(t)
    _rate[key] = ev
    return blocked


def log(user_id, action, detail=None, ip=None):
    try:
        db.execute("INSERT INTO activity(id, user_id, at, action, detail, ip) VALUES (?, ?, ?, ?, ?, ?)",
                   (uuid.uuid4().hex, user_id, time.time(), action[:60],
                    json.dumps(detail, ensure_ascii=False, default=str)[:2000] if detail is not None else None, ip))
    except Exception:
        pass


def validate_credentials(email, pw):
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Correo no válido")
    if not isinstance(pw, str) or len(pw) < 10 or len(pw) > 200:
        raise AuthError("La contraseña debe tener entre 10 y 200 caracteres")
    if pw.lower() in (email, email.split("@")[0]) or len(set(pw)) < 5:
        raise AuthError("Contraseña demasiado débil")
    return email, pw


def register(email, pw, ip=None):
    if rate_limited(f"reg:{ip}", 5, 3600):
        raise AuthError("Demasiados registros desde esta conexión; intenta más tarde", 429)
    email, pw = validate_credentials(email, pw)
    if db.one("SELECT id FROM users WHERE email = ?", (email,)):
        raise AuthError("Ya existe una cuenta con ese correo", 409)
    uid = uuid.uuid4().hex
    admin = 1 if email == (os.environ.get("CRYPTO_RADAR_ADMIN_EMAIL") or "").strip().lower() else 0
    db.execute("INSERT INTO users(id, email, pw_hash, created_at, plan, is_admin) VALUES (?, ?, ?, ?, 'free', ?)",
               (uid, email, hash_password(pw), time.time(), admin))
    log(uid, "register", {"admin": bool(admin)}, ip)
    return get_user(uid)


def login(email, pw, ip=None, ua=None):
    email = (email or "").strip().lower()
    if rate_limited(f"login:{ip}", 20, 900):
        raise AuthError("Demasiados intentos desde esta conexión; espera 15 minutos", 429)
    u = db.one("SELECT * FROM users WHERE email = ?", (email,))
    if not u:
        verify_password(pw or "", "scrypt$16384$8$1$" + "00" * 16 + "$" + "00" * 32)   # mismo tiempo exista o no
        raise AuthError("Correo o contraseña incorrectos", 401)
    if u["locked_until"] and u["locked_until"] > time.time():
        raise AuthError("Cuenta bloqueada temporalmente por intentos fallidos; espera 15 minutos", 429)
    if u["disabled"]:
        raise AuthError("Cuenta desactivada", 403)
    if not verify_password(pw or "", u["pw_hash"]):
        fails = (u["failed_logins"] or 0) + 1
        db.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                   (0 if fails >= LOCK_AFTER else fails, time.time() + LOCK_S if fails >= LOCK_AFTER else None, u["id"]))
        log(u["id"], "login_failed", None, ip)
        raise AuthError("Correo o contraseña incorrectos", 401)
    db.execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (u["id"],))
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    db.execute("INSERT INTO sessions(token_hash, user_id, csrf, created_at, expires_at, ip, ua) VALUES (?, ?, ?, ?, ?, ?, ?)",
               (_th(token), u["id"], csrf, time.time(), time.time() + SESSION_DAYS * 86400, ip, (ua or "")[:200]))
    log(u["id"], "login", None, ip)
    return token, csrf, get_user(u["id"])


def _th(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session(token):
    if not token or len(token) > 100:
        return None
    s = db.one("SELECT * FROM sessions WHERE token_hash = ?", (_th(token),))
    if not s or s["expires_at"] < time.time():
        return None
    u = get_user(s["user_id"])
    if not u or u["disabled"]:
        return None
    return {"user": u, "csrf": s["csrf"]}


def logout(token):
    if token:
        db.execute("DELETE FROM sessions WHERE token_hash = ?", (_th(token),))


def logout_all(user_id):
    db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def change_password(user_id, old, new, ip=None):
    u = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not u or not verify_password(old or "", u["pw_hash"]):
        raise AuthError("La contraseña actual no es correcta", 401)
    validate_credentials(u["email"], new)
    db.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(new), user_id))
    logout_all(user_id)
    log(user_id, "password_changed", None, ip)


def get_user(uid):
    u = db.one("SELECT id, email, created_at, plan, plan_until, is_admin, telegram_chat_id, settings, disabled "
               "FROM users WHERE id = ?", (uid,))
    if not u:
        return None
    u["effective_plan"] = effective_plan(u)
    try:
        u["settings"] = json.loads(u["settings"] or "{}")
    except Exception:
        u["settings"] = {}
    return u


def effective_plan(u):
    """El plan pagado solo vale mientras plan_until esté en el futuro (fijado por un pago verificado)."""
    if u.get("is_admin"):
        return "elite"
    if u.get("plan") in ("pro", "elite") and (u.get("plan_until") or 0) > time.time():
        return u["plan"]
    return "free"


def features(u):
    return PLANS[effective_plan(u) if u else "free"]


def public(u):
    if not u:
        return None
    return {"email": u["email"], "plan": u["effective_plan"], "plan_label": PLANS[u["effective_plan"]]["label"],
            "plan_until": u.get("plan_until"), "is_admin": bool(u["is_admin"]),
            "telegram_linked": bool(u.get("telegram_chat_id")), "features": PLANS[u["effective_plan"]],
            "settings": u.get("settings") or {}}


USER_SETTINGS = {"capital_usd": float, "risk_per_trade_pct": float, "alerts_telegram": bool, "watchlist": list}


def save_user_settings(uid, new):
    u = get_user(uid)
    s = dict(u["settings"])
    for k, typ in USER_SETTINGS.items():
        if k not in new:
            continue
        v = new[k]
        try:
            if typ is float:
                v = float(v)
                if v != v or v < 0 or v > 1e9:
                    continue
                if k == "risk_per_trade_pct" and not 0.1 <= v <= 5:
                    continue
            elif typ is bool:
                v = bool(v) if isinstance(v, bool) else str(v).lower() in ("1", "true", "on", "si", "sí")
            elif typ is list:
                items = v if isinstance(v, list) else str(v).replace("\n", ",").split(",")
                v = [x for x in (re.sub(r"[^A-Z0-9]", "", str(i).upper())[:15] for i in items) if x][:50]
        except (TypeError, ValueError):
            continue
        s[k] = v
    db.execute("UPDATE users SET settings = ? WHERE id = ?", (json.dumps(s), uid))
    return s
