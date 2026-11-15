"""Cuentas de usuario: registro, inicio de sesión, sesiones, CSRF, límites de intentos y registro de actividad.

  * Contraseñas con scrypt (sal aleatoria de 16 bytes, n=2^14, r=8, p=1) y comparación en tiempo constante.
  * Sesión: token aleatorio de 32 bytes en cookie HttpOnly + SameSite=Lax (+ Secure en HTTPS); en la base solo se
    guarda su SHA-256. Caduca a los 14 días. Se rota en cada inicio de sesión.
  * CSRF: token por sesión que el panel envía en la cabecera X-CSRF-Token en cada petición que cambia datos.
  * Bloqueo: 5 fallos seguidos bloquean la cuenta 15 min; además, límite por IP.
  * El plan de pago SOLO lo cambia billing.py tras un pago verificado con el proveedor (o un admin, registrado).
  * Acceso solo con aprobación: cualquiera puede SOLICITAR una cuenta (usuario y contraseña propios), pero queda
    "pendiente" y no puede entrar hasta que un administrador la apruebe. No hay registro abierto.
  * El administrador se crea desde variables de entorno (CRYPTO_RADAR_ADMIN_USER y CRYPTO_RADAR_ADMIN_PASSWORD),
    nunca por ser el primero en registrarse. Una cuenta normal que ya tenga ese nombre NUNCA se promueve: el
    servidor no arranca hasta que se elija otro nombre o se ponga esa cuenta en cuarentena
    (CRYPTO_RADAR_ADMIN_TAKEOVER=1), y el administrador nace siempre con la contraseña del entorno.
  * Límites de intentos guardados en la base (tabla rate_limits): sobreviven a reinicios y se comparten entre
    instancias que usen la misma base. Ventana fija; ver docs/SEGURIDAD.md para sus limitaciones.
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
from . import db, totp

SESSION_DAYS = 14
LOCK_AFTER, LOCK_S = 5, 15 * 60
# Inicio de sesión (docs/RATE_LIMITING.md). Ventana fija de 15 minutos para todos los contadores.
LOGIN_WINDOW_S = 15 * 60
LOGIN_IP_FAILS = 20          # intentos FALLIDOS por IP (antes: 20 intentos de cualquier tipo, aciertos incluidos)
LOGIN_IP_FAILS_SPRAY = 5     # fallidos por IP mientras hay un ataque repartido entre muchas IP (modo estricto)
LOGIN_SPRAY_GLOBAL = 200     # fallidos en todo el sitio dentro de la ventana que activan el modo estricto
LOGIN_IP_ATTEMPTS = 300      # tope de intentos de cualquier tipo por IP: protege la CPU (scrypt) de una inundación
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[a-z]{2,24}$", re.I)
USER_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
MAX_PENDING = 300
POLICY_VERSION = "2026-11-15"     # versión de /privacidad y /aviso-de-riesgo que acepta quien solicita acceso
RESERVED = {"admin", "administrador", "administrator", "root", "soporte", "support", "sistema", "system",
            "cryptoradar", "crypto-radar", "crypto.radar", "moderador", "staff"}
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
    def __init__(self, msg, code=400, **extra):
        super().__init__(msg)
        self.code = code
        self.extra = extra


def admin_totp_required():
    """Los administradores deben usar TOTP para cualquier acción de administración (salvo que se desactive a propósito)."""
    return (os.environ.get("CRYPTO_RADAR_ADMIN_TOTP") or "required").strip().lower() != "optional"


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


def _rate_mem(key, limit, window_s):
    t = time.time()
    ev = [x for x in _rate.get(key, []) if t - x < window_s]
    blocked = len(ev) >= limit
    if not blocked:
        ev.append(t)
    _rate[key] = ev
    return blocked


def _rate_key(key, window_s, t):
    bucket = int(t // window_s)
    return hashlib.sha256(f"{key}|{window_s}|{bucket}".encode()).hexdigest(), (bucket + 1) * window_s


def rate_bump(key, window_s, delta=1):
    """Suma `delta` (puede ser -1) al contador de `key` en la ventana actual y devuelve el valor resultante.

    Misma tabla y misma clave con hash que `rate_limited`. Si la base falla, usa el contador en memoria.
    """
    t = time.time()
    k, exp = _rate_key(key, window_s, t)
    try:
        db.execute("INSERT INTO rate_limits(k, n, expires_at) VALUES (?, ?, ?) "
                   "ON CONFLICT (k) DO UPDATE SET n = rate_limits.n + ?", (k, max(delta, 0), exp, delta))
        return (db.one("SELECT n FROM rate_limits WHERE k = ?", (k,)) or {}).get("n", 0)
    except Exception as e:
        print(f"AVISO: límite de intentos en memoria ({type(e).__name__})", flush=True)
        ev = [x for x in _rate.get(key, []) if t - x < window_s]
        if delta > 0:
            ev += [t] * delta
        elif ev:
            ev = ev[:delta] if len(ev) > -delta else []
        _rate[key] = ev
        return len(ev)


def rate_peek(key, window_s):
    """Valor actual del contador de `key` en la ventana actual, sin registrar nada."""
    t = time.time()
    k, _ = _rate_key(key, window_s, t)
    try:
        return (db.one("SELECT n FROM rate_limits WHERE k = ?", (k,)) or {}).get("n", 0)
    except Exception:
        return len([x for x in _rate.get(key, []) if t - x < window_s])


def rate_limited(key, limit, window_s):
    """True si `key` superó `limit` eventos en la ventana actual de `window_s` segundos (y registra este evento).

    Se guarda en la base (tabla rate_limits) con ventana fija: sobrevive a reinicios y vale para todas las
    instancias que compartan la base. Si la base falla, usa un contador en memoria (nunca deja pasar sin límite).
    """
    t = time.time()
    k, exp = _rate_key(key, window_s, t)
    try:
        db.execute("INSERT INTO rate_limits(k, n, expires_at) VALUES (?, 1, ?) "
                   "ON CONFLICT (k) DO UPDATE SET n = rate_limits.n + 1", (k, exp))
        n = (db.one("SELECT n FROM rate_limits WHERE k = ?", (k,)) or {}).get("n", 1)
        if secrets.randbelow(50) == 0:
            db.execute("DELETE FROM rate_limits WHERE expires_at < ?", (t,))
        return n > limit
    except Exception as e:
        print(f"AVISO: límite de intentos en memoria ({type(e).__name__})", flush=True)
        return _rate_mem(key, limit, window_s)


def reset_rate_limits():
    """Solo para pruebas y mantenimiento: borra todos los contadores."""
    _rate.clear()
    try:
        db.execute("DELETE FROM rate_limits", ())
    except Exception:
        pass


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
    try:
        db.execute("INSERT INTO users(id, email, pw_hash, created_at, plan, plan_until, is_admin, status, contact, "
                   "request_note, approved_at, approved_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (uid, username, hash_password(pw), time.time(), plan, plan_until, is_admin, status, contact, note,
                    time.time() if status == "active" else None, by))
    except Exception as e:     # dos solicitudes simultáneas con el mismo usuario: la base (UNIQUE) decide
        if db.one("SELECT id FROM users WHERE email = ?", (username,)):
            raise AuthError("Ese usuario no está disponible; elige otro", 409) from e
        raise
    return uid


def request_access(username, pw, contact=None, note=None, ip=None, consent=None):
    """Solicitud de cuenta: queda PENDIENTE hasta que un administrador la apruebe.

    `consent` debe ser POLICY_VERSION: la persona aceptó la política de tratamiento de datos y el aviso de riesgo.
    """
    if rate_limited(f"req:{ip}", 3, 3600) or rate_limited("req:global", 60, 3600):
        raise AuthError("Demasiadas solicitudes; intenta más tarde", 429)
    if consent != POLICY_VERSION:
        raise AuthError("Debes aceptar la política de tratamiento de datos y el aviso de riesgo", 400)
    username, pw = validate_credentials(username, pw)
    contact = re.sub(r"[\x00-\x1f]", "", str(contact or ""))[:120] or None
    note = re.sub(r"[\x00-\x1f]", " ", str(note or ""))[:300] or None
    if (db.one("SELECT COUNT(*) AS n FROM users WHERE status = 'pending'", ()) or {}).get("n", 0) >= MAX_PENDING:
        raise AuthError("No se aceptan más solicitudes por ahora", 503)
    if is_reserved(username) or db.one("SELECT id FROM users WHERE email = ?", (username,)):
        raise AuthError("Ese usuario no está disponible; elige otro", 409)
    uid = _create(username, pw, "pending", contact=contact, note=note)
    db.execute("UPDATE users SET consent_at = ?, consent_version = ? WHERE id = ?", (time.time(), POLICY_VERSION, uid))
    log(uid, "access_requested", {"contact": bool(contact), "consent_version": POLICY_VERSION}, ip)
    return uid


def register(email, pw, ip=None):
    """Compatibilidad: el registro abierto ya no existe; crea una solicitud PENDIENTE y devuelve ese usuario."""
    return get_user(request_access(email, pw, ip=ip, consent=POLICY_VERSION))


def is_reserved(username):
    """Nombres que nadie puede solicitar: los genéricos de administración y el del administrador del entorno."""
    u = norm_login(username)
    return u in RESERVED or u.split("@")[0] in RESERVED or u == norm_login(os.environ.get("CRYPTO_RADAR_ADMIN_USER"))


class AdminBootstrapError(SystemExit):
    pass


def ensure_admin():
    """Arranque seguro del administrador definido en el entorno.

    Devuelve {"user", "result"} o None si no hay administrador configurado. `result` es uno de:
      creado         · no existía; se crea con la contraseña del entorno
      verificado     · ya existe y ya era administrador; no se toca su contraseña
      restablecido   · ya era administrador y CRYPTO_RADAR_ADMIN_RESET=1: contraseña del entorno y sesiones cerradas
      cuarentena     · una cuenta NORMAL tenía ese nombre y CRYPTO_RADAR_ADMIN_TAKEOVER=1: esa cuenta se renombra,
                       se rechaza y se cierran sus sesiones; el administrador se crea nuevo con la contraseña del entorno
    Si una cuenta normal tiene ese nombre y no se pidió la cuarentena, lanza AdminBootstrapError: nunca se promueve
    una cuenta preexistente ni se conserva una contraseña elegida por otra persona.
    Cada resultado queda en el registro de actividad (admin_bootstrap_*).
    """
    raw_u = norm_login(os.environ.get("CRYPTO_RADAR_ADMIN_USER"))
    pw = os.environ.get("CRYPTO_RADAR_ADMIN_PASSWORD") or ""
    if not raw_u and not pw:
        return None
    if not raw_u or not pw:
        raise AdminBootstrapError("Define CRYPTO_RADAR_ADMIN_USER y CRYPTO_RADAR_ADMIN_PASSWORD (las dos).")
    try:
        u = validate_username(raw_u)
    except AuthError as e:
        raise AdminBootstrapError(f"CRYPTO_RADAR_ADMIN_USER no válido: {e}")
    if len(pw) < 12:
        raise AdminBootstrapError("CRYPTO_RADAR_ADMIN_PASSWORD debe tener al menos 12 caracteres")
    try:
        validate_password(u.split("@")[0], pw)
    except AuthError as e:
        raise AdminBootstrapError(f"CRYPTO_RADAR_ADMIN_PASSWORD rechazada: {e}")
    row = db.one("SELECT id, is_admin, status, approved_by, created_at FROM users WHERE email = ?", (u,))
    if row and row["is_admin"]:
        if os.environ.get("CRYPTO_RADAR_ADMIN_RESET") == "1":
            db.execute("UPDATE users SET pw_hash = ?, failed_logins = 0, locked_until = NULL, status = 'active', "
                       "disabled = 0, totp_enabled = 0, totp_secret = NULL, totp_last_step = NULL WHERE id = ?",
                       (hash_password(pw), row["id"]))
            logout_all(row["id"])
            log(row["id"], "admin_bootstrap_password_reset", {"user": u, "source": "entorno", "totp_reset": True})
            return {"user": u, "result": "restablecido"}
        log(row["id"], "admin_bootstrap_verified", {"user": u})
        return {"user": u, "result": "verificado"}
    result = "creado"
    if row:   # alguien reservó el nombre del administrador con una cuenta normal
        detail = {"user": u, "squatter_id": row["id"], "squatter_status": row["status"],
                  "squatter_created_at": row["created_at"]}
        log(row["id"], "admin_bootstrap_conflict", detail)
        if os.environ.get("CRYPTO_RADAR_ADMIN_TAKEOVER") != "1":
            raise AdminBootstrapError(
                f"Ya existe una cuenta normal llamada «{u}» (posible apropiación del nombre del administrador). "
                "Por seguridad no se promueve. Elige otro CRYPTO_RADAR_ADMIN_USER, o define "
                "CRYPTO_RADAR_ADMIN_TAKEOVER=1 para ponerla en cuarentena y crear el administrador.")
        quarantined = f"{u}~cuarentena~{row['id'][:12]}"      # no cumple el formato de usuario: nadie puede pedirlo
        db.execute("UPDATE users SET email = ?, status = 'rejected', disabled = 1, is_admin = 0 WHERE id = ?",
                   (quarantined, row["id"]))
        logout_all(row["id"])
        log(row["id"], "admin_bootstrap_quarantine", detail | {"renamed_to": quarantined})
        result = "cuarentena"
    uid = _create(u, pw, "active", is_admin=1, by="entorno")
    log(uid, "admin_bootstrap_created", {"user": u, "after_quarantine": result == "cuarentena"})
    return {"user": u, "result": result}


# ---------------------------------------------------------------- administración de cuentas
def _admin_target(admin, uid):
    if not admin_ok(admin):
        raise AuthError("solo administradores con verificación en dos pasos", 403)
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
    if t["is_admin"]:
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
    if not admin_ok(admin):
        raise AuthError("solo administradores con verificación en dos pasos", 403)
    username, pw = validate_credentials(username, pw)
    if is_reserved(username) or db.one("SELECT id FROM users WHERE email = ?", (username,)):
        raise AuthError("Ese usuario ya existe o está reservado", 409)
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
    if t["is_admin"]:
        raise AuthError("La contraseña de un administrador solo se cambia desde su propia cuenta o con "
                        "CRYPTO_RADAR_ADMIN_RESET", 403)
    validate_password(t["email"].split("@")[0], pw)
    db.execute("UPDATE users SET pw_hash = ?, failed_logins = 0, locked_until = NULL, totp_enabled = 0, totp_secret = NULL, "
               "totp_last_step = NULL WHERE id = ?", (hash_password(pw), uid))
    logout_all(uid)
    log(admin["id"], "admin_user_reset_password", {"user": t["email"], "totp_reset": True}, ip)


def admin_list():
    return db.all_("SELECT id, email, created_at, plan, plan_until, is_admin, disabled, status, contact, request_note, "
                   "approved_at, approved_by, telegram_chat_id IS NOT NULL AS telegram FROM users "
                   "ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC LIMIT 500", ())


def _fail(u, ip, what="login_failed"):
    fails = (u["failed_logins"] or 0) + 1
    db.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?",
               (0 if fails >= LOCK_AFTER else fails, time.time() + LOCK_S if fails >= LOCK_AFTER else None, u["id"]))
    log(u["id"], what, None, ip)


def _accept_totp(u, code_given):
    """True si el código vale; guarda el paso de forma atómica para que no se pueda reutilizar."""
    s = totp.match(u["totp_secret"] or "", code_given, u.get("totp_last_step"))
    if s is None:
        return False
    cur = db.execute("UPDATE users SET totp_last_step = ? WHERE id = ? AND (totp_last_step IS NULL OR totp_last_step < ?)",
                     (s, u["id"], s))
    return cur.rowcount == 1


def login(email, pw, ip=None, ua=None, code=None):
    """Inicio de sesión con protección combinada (docs/RATE_LIMITING.md):

    1. Tope de intentos por IP (LOGIN_IP_ATTEMPTS): frena inundaciones que solo buscan gastar CPU en scrypt.
    2. Intentos FALLIDOS por IP (LOGIN_IP_FAILS, o LOGIN_IP_FAILS_SPRAY en modo estricto): cada intento cuenta como
       fallido ANTES de comprobar la contraseña y se descuenta solo si la contraseña es correcta. Así, ni con
       peticiones simultáneas se superan los fallidos permitidos, y los usuarios legítimos detrás de la misma IP
       (oficina, CGNAT) no se bloquean entre sí al entrar bien.
    3. Modo estricto: si en la ventana hay más de LOGIN_SPRAY_GLOBAL fallos en todo el sitio (ataque repartido entre
       muchas IP), el límite de fallidos por IP baja a LOGIN_IP_FAILS_SPRAY.
    4. Por cuenta: LOCK_AFTER fallos bloquean la cuenta LOCK_S segundos (también para nombres que no existen).
    """
    email = norm_login(email)
    w = LOGIN_WINDOW_S
    if rate_limited(f"login:{ip}", LOGIN_IP_ATTEMPTS, w):
        raise AuthError("Demasiados intentos desde esta conexión; espera 15 minutos", 429)
    strict = rate_peek("loginfail:*", w) >= LOGIN_SPRAY_GLOBAL
    if rate_bump(f"loginfail:{ip}", w) > (LOGIN_IP_FAILS_SPRAY if strict else LOGIN_IP_FAILS):
        rate_bump("loginfail:*", w)
        raise AuthError("Demasiados intentos fallidos desde esta conexión; espera 15 minutos", 429)

    def failed():
        rate_bump("loginfail:*", w)          # el fallo por IP ya quedó contado arriba

    u = db.one("SELECT * FROM users WHERE email = ?", (email,))
    if not u:
        verify_password(pw or "", "scrypt$16384$8$1$" + "00" * 16 + "$" + "00" * 32)   # mismo tiempo exista o no
        failed()
        # mismo bloqueo aparente que una cuenta real tras LOCK_AFTER fallos: el 429 no revela si el usuario existe
        if rate_limited(f"lockname:{email}", LOCK_AFTER, LOCK_S):
            raise AuthError("Cuenta bloqueada temporalmente por intentos fallidos; espera 15 minutos", 429)
        raise AuthError("Usuario o contraseña incorrectos", 401)
    if u["locked_until"] and u["locked_until"] > time.time():
        failed()
        raise AuthError("Cuenta bloqueada temporalmente por intentos fallidos; espera 15 minutos", 429)
    if not verify_password(pw or "", u["pw_hash"]):
        failed()
        _fail(u, ip)
        raise AuthError("Usuario o contraseña incorrectos", 401)
    rate_bump(f"loginfail:{ip}", w, -1)      # contraseña correcta: no era un intento fallido
    # el estado solo se revela a quien conoce la contraseña
    status = u.get("status") or "active"
    if status == "pending":
        raise AuthError("Tu solicitud está pendiente de aprobación por el administrador", 403)
    if status != "active":
        raise AuthError("Tu solicitud no fue aprobada", 403)
    if u["disabled"]:
        raise AuthError("Cuenta desactivada por el administrador", 403)
    if u.get("totp_enabled"):
        if not code:
            raise AuthError("Escribe el código de 6 dígitos de tu app de autenticación", 401, totp_required=True)
        if not _accept_totp(u, code):
            rate_bump(f"loginfail:{ip}", w); failed()
            _fail(u, ip, "login_totp_failed")
            raise AuthError("Código de verificación incorrecto o ya usado", 401, totp_required=True)
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
    u = db.one("SELECT id, email, created_at, plan, plan_until, is_admin, telegram_chat_id, settings, disabled, status, "
               "totp_enabled FROM users WHERE id = ?", (uid,))
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
            "totp_enabled": bool(u.get("totp_enabled")),
            "totp_setup_required": bool(u["is_admin"]) and admin_totp_required() and not u.get("totp_enabled"),
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


# ---------------------------------------------------------------- verificación en dos pasos (TOTP)
def totp_setup(user_id, password, ip=None):
    """Genera un secreto nuevo (aún sin activar). Exige la contraseña actual."""
    u = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not u or not verify_password(password or "", u["pw_hash"]):
        raise AuthError("La contraseña actual no es correcta", 401)
    if u.get("totp_enabled"):
        raise AuthError("La verificación en dos pasos ya está activa", 409)
    secret = totp.new_secret()
    db.execute("UPDATE users SET totp_secret = ?, totp_last_step = NULL WHERE id = ?", (secret, user_id))
    log(user_id, "totp_setup_started", None, ip)
    return {"secret": secret, "uri": totp.uri(secret, u["email"])}


def totp_enable(user_id, code_given, ip=None):
    """Activa TOTP si el código coincide con el secreto pendiente. Cierra todas las sesiones (hay que volver a entrar)."""
    u = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not u or not u.get("totp_secret"):
        raise AuthError("Primero genera la clave de verificación", 400)
    if u.get("totp_enabled"):
        raise AuthError("La verificación en dos pasos ya está activa", 409)
    if not _accept_totp(u, code_given):
        raise AuthError("Código incorrecto: revisa la hora del teléfono y vuelve a intentarlo", 400)
    db.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (user_id,))
    logout_all(user_id)
    log(user_id, "totp_enabled", None, ip)


def totp_disable(user_id, password, code_given, ip=None):
    u = db.one("SELECT * FROM users WHERE id = ?", (user_id,))
    if not u or not u.get("totp_enabled"):
        raise AuthError("La verificación en dos pasos no está activa", 400)
    if u["is_admin"] and admin_totp_required():
        raise AuthError("Los administradores no pueden desactivarla. Para recuperarla usa CRYPTO_RADAR_ADMIN_RESET", 403)
    if not verify_password(password or "", u["pw_hash"]) or not _accept_totp(u, code_given):
        _fail(u, ip, "totp_disable_failed")
        raise AuthError("Contraseña o código incorrectos", 401)
    db.execute("UPDATE users SET totp_enabled = 0, totp_secret = NULL, totp_last_step = NULL WHERE id = ?", (user_id,))
    log(user_id, "totp_disabled", None, ip)


def admin_ok(user):
    """Puede ejecutar acciones de administración: es admin y, si se exige, tiene TOTP activo (validado al entrar)."""
    return bool(user and user.get("is_admin")) and (not admin_totp_required() or bool(user.get("totp_enabled")))
