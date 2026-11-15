"""Cuentas de usuario: registro, inicio de sesión, sesiones, CSRF, límites de intentos y registro de actividad.

  * Contraseñas con scrypt (sal aleatoria de 16 bytes, n=2^14, r=8, p=1) y comparación en tiempo constante.
  * Sesión: token aleatorio de 32 bytes en cookie HttpOnly + SameSite=Lax (+ Secure en HTTPS); en la base solo se
    guarda su SHA-256. Caduca a los 14 días. Se rota en cada inicio de sesión.
  * CSRF: token por sesión que el panel envía en la cabecera X-CSRF-Token en cada petición que cambia datos.
  * Bloqueo: 5 fallos seguidos bloquean la cuenta 15 min; además, límite por IP.
  * El plan de pago SOLO lo cambia billing.py tras un pago verificado con el proveedor (o un admin, registrado).
  * Acceso solo con aprobación: cualquiera puede SOLICITAR una cuenta (usuario y contraseña propios), pero queda
    "pendiente" y no puede entrar hasta que un administrador la apruebe. No hay registro abierto.
  * El primer administrador se crea desde variables de entorno (CRYPTO_RADAR_ADMIN_USER y
    CRYPTO_RADAR_ADMIN_PASSWORD), nunca por ser el primero en registrarse.
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
USER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MAX_PENDING = 300
COMMON_PW = {"1234567890", "contraseña", "contrasena", "password123", "qwertyuiop", "cryptoradar", "bitcoin123",
             "123456789a", "abcdefghij", "iloveyou12", "password12", "contraseña1"}
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


def norm_login(x):
    return (x or "").strip().lower()


def validate_username(u):
    u = norm_login(u)
    if not (USER_RE.match(u) or EMAIL_RE.match(u)):
        raise AuthError("Usuario no válido: 3 a 32 caracteres, letras minúsculas, números, punto, guion o guion bajo")
    return u


def validate_password(u, pw):
    if not isinstance(pw, str) or len(pw) < 10 or len(pw) > 200:
        raise AuthError("La contraseña debe tener entre 10 y 200 caracteres")
    low = pw.lower()
    if low in COMMON_PW or u in low or len(set(pw)) < 5:
        raise AuthError("Contraseña demasiado débil: evita tu usuario y combinaciones comunes")
    return pw


def validate_credentials(email, pw):
    u = validate_username(email)
    return u, validate_password(u.split("@")[0], pw)


def _create(username, pw, status, plan="free", plan_until=None, is_admin=0, contact=None, note=None, by=None):
    uid = uuid.uuid4().hex
    db.execute("INSERT INTO users(id, email, pw_hash, created_at, plan, plan_until, is_admin, status, contact, "
               "request_note, approved_at, approved_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (uid, username, hash_password(pw), time.time(), plan, plan_until, is_admin, status, contact, note,
                time.time() if status == "active" else None, by))
    return uid


def request_access(username, pw, contact=None, note=None, ip=None):
    """Solicitud de cuenta: queda PENDIENTE hasta que un administrador la apruebe."""
    if rate_limited(f"req:{ip}", 3, 3600) or rate_limited("req:global", 60, 3600):
        raise AuthError("Demasiadas solicitudes; intenta más tarde", 429)
    username, pw = validate_credentials(username, pw)
    contact = re.sub(r"[\x00-\x1f]", "", str(contact or ""))[:120] or None
    note = re.sub(r"[\x00-\x1f]", " ", str(note or ""))[:300] or None
    if (db.one("SELECT COUNT(*) AS n FROM users WHERE status = 'pending'", ()) or {}).get("n", 0) >= MAX_PENDING:
        raise AuthError("No se aceptan más solicitudes por ahora", 503)
    if db.one("SELECT id FROM users WHERE email = ?", (username,)):
        raise AuthError("Ese usuario no está disponible; elige otro", 409)
    uid = _create(username, pw, "pending", contact=contact, note=note)
    log(uid, "access_requested", {"contact": bool(contact)}, ip)
    return uid


def register(email, pw, ip=None):
    """Compatibilidad: el registro abierto ya no existe; crea una solicitud PENDIENTE y devuelve ese usuario."""
    return get_user(request_access(email, pw, ip=ip))


def ensure_admin():
    """Crea (o asegura) el administrador definido en el entorno. Devuelve su usuario o None si no está definido."""
    u = norm_login(os.environ.get("CRYPTO_RADAR_ADMIN_USER"))
    pw = os.environ.get("CRYPTO_RADAR_ADMIN_PASSWORD") or ""
    if not u or not pw:
        return None
    u = validate_username(u)
    if len(pw) < 12:
        raise SystemExit("CRYPTO_RADAR_ADMIN_PASSWORD debe tener al menos 12 caracteres")
    row = db.one("SELECT id FROM users WHERE email = ?", (u,))
    if not row:
        uid = _create(u, pw, "active", is_admin=1, by="entorno")
        log(uid, "admin_bootstrap", None, None)
        return u
    db.execute("UPDATE users SET is_admin = 1, status = 'active', disabled = 0 WHERE id = ?", (row["id"],))
    if os.environ.get("CRYPTO_RADAR_ADMIN_RESET") == "1":
        db.execute("UPDATE users SET pw_hash = ?, failed_logins = 0, locked_until = NULL WHERE id = ?",
                   (hash_password(pw), row["id"]))
        logout_all(row["id"]); log(row["id"], "admin_password_reset_env", None, None)
    return u


# ---------------------------------------------------------------- administración de cuentas
def _admin_target(admin, uid):
    if not admin or not admin.get("is_admin"):
        raise AuthError("solo administradores", 403)
    if not isinstance(uid, str) or not re.match(r"^[a-f0-9]{32}$", uid):
        raise AuthError("usuario no válido")
    t = db.one("SELECT id, email, is_admin, status FROM users WHERE id = ?", (uid,))
    if not t:
        raise AuthError("usuario no encontrado", 404)
    return t


def admin_set_status(admin, uid, action, plan="free", days=0, ip=None):
    t = _admin_target(admin, uid)
    if t["id"] == admin["id"]:
        raise AuthError("No puedes cambiar tu propia cuenta desde aquí")
    if t["is_admin"] and action != "approve":
        raise AuthError("No se puede modificar a otro administrador desde el panel", 403)
    if action == "approve":
        plan = plan if plan in PLANS else "free"
        try:
            days = max(0, min(3650, int(days or 0)))
        except (TypeError, ValueError):
            days = 0
        until = time.time() + days * 86400 if plan != "free" and days else None
        db.execute("UPDATE users SET status = 'active', disabled = 0, plan = ?, plan_until = ?, approved_at = ?, "
                   "approved_by = ? WHERE id = ?", (plan, until, time.time(), admin["email"], uid))
    elif action == "reject":
        db.execute("UPDATE users SET status = 'rejected', disabled = 1 WHERE id = ?", (uid,)); logout_all(uid)
    elif action == "disable":
        db.execute("UPDATE users SET disabled = 1 WHERE id = ?", (uid,)); logout_all(uid)
    elif action == "enable":
        if t["status"] != "active":
            raise AuthError("Primero aprueba la cuenta")
        db.execute("UPDATE users SET disabled = 0 WHERE id = ?", (uid,))
    elif action == "delete":
        logout_all(uid)
        db.execute("DELETE FROM users WHERE id = ?", (uid,))
    else:
        raise AuthError("acción no válida")
    log(admin["id"], "admin_user_" + action, {"user": t["email"], "plan": plan, "days": days}, ip)


def admin_create(admin, username, pw, plan="free", days=0, ip=None):
    if not admin or not admin.get("is_admin"):
        raise AuthError("solo administradores", 403)
    username, pw = validate_credentials(username, pw)
    if db.one("SELECT id FROM users WHERE email = ?", (username,)):
        raise AuthError("Ese usuario ya existe", 409)
    plan = plan if plan in PLANS else "free"
    try:
        days = max(0, min(3650, int(days or 0)))
    except (TypeError, ValueError):
        days = 0
    uid = _create(username, pw, "active", plan=plan, plan_until=time.time() + days * 86400 if plan != "free" and days else None,
                  by=admin["email"])
    log(admin["id"], "admin_user_create", {"user": username, "plan": plan, "days": days}, ip)
    return uid


def admin_reset_password(admin, uid, pw, ip=None):
    t = _admin_target(admin, uid)
    validate_password(t["email"].split("@")[0], pw)
    db.execute("UPDATE users SET pw_hash = ?, failed_logins = 0, locked_until = NULL WHERE id = ?", (hash_password(pw), uid))
    logout_all(uid)
    log(admin["id"], "admin_user_reset_password", {"user": t["email"]}, ip)


def admin_list():
    return db.all_("SELECT id, email, created_at, plan, plan_until, is_admin, disabled, status, contact, request_note, "
                   "approved_at, approved_by, telegram_chat_id IS NOT NULL AS telegram FROM users "
                   "ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC LIMIT 500", ())


def login(email, pw, ip=None, ua=None):
    email = norm_login(email)
    if rate_limited(f"login:{ip}", 20, 900):
        raise AuthError("Demasiados intentos desde esta conexión; espera 15 minutos", 429)
    u = db.one("SELECT * FROM users WHERE email = ?", (email,))
    if not u:
        verify_password(pw or "", "scrypt$16384$8$1$" + "00" * 16 + "$" + "00" * 32)   # mismo tiempo exista o no
        raise AuthError("Usuario o contraseña incorrectos", 401)
    if u["locked_until"] and u["locked_until"] > time.time():
        raise AuthError("Cuenta bloqueada temporalmente por intentos fallidos; espera 15 minutos", 429)
    if not verify_password(pw or "", u["pw_hash"]):
        fails = (u["failed_logins"] or 0) + 1
        db.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
                   (0 if fails >= LOCK_AFTER else fails, time.time() + LOCK_S if fails >= LOCK_AFTER else None, u["id"]))
        log(u["id"], "login_failed", None, ip)
        raise AuthError("Usuario o contraseña incorrectos", 401)
    # el estado solo se revela a quien conoce la contraseña
    status = u.get("status") or "active"
    if status == "pending":
        raise AuthError("Tu solicitud está pendiente de aprobación por el administrador", 403)
    if status != "active":
        raise AuthError("Tu solicitud no fue aprobada", 403)
    if u["disabled"]:
        raise AuthError("Cuenta desactivada por el administrador", 403)
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
    if not u or u["disabled"] or (u.get("status") or "active") != "active":
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
    validate_password(u["email"].split("@")[0], new)
    db.execute("UPDATE users SET pw_hash = ? WHERE id = ?", (hash_password(new), user_id))
    logout_all(user_id)
    log(user_id, "password_changed", None, ip)


def get_user(uid):
    u = db.one("SELECT id, email, created_at, plan, plan_until, is_admin, telegram_chat_id, settings, disabled, status "
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
    return {"email": u["email"], "username": u["email"], "plan": u["effective_plan"], "plan_label": PLANS[u["effective_plan"]]["label"],
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
