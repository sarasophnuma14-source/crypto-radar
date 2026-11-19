"""Base de datos: PostgreSQL si hay DATABASE_URL (producción, p. ej. Neon), SQLite local si no.

Tablas: users, sessions, activity, positions, payments, telegram_links y kv (documentos JSON del sistema:
último informe, alertas, diario... para que sobrevivan a los reinicios del disco efímero de Render).
Todas las consultas usan parámetros (nunca se concatena texto del usuario en el SQL).
"""
from __future__ import annotations
import contextvars
import json
import os
import sqlite3
import threading
import time
from .config import DATA_DIR

URL = os.environ.get("DATABASE_URL", "").strip()
IS_PG = URL.startswith(("postgres://", "postgresql://"))
_local = threading.local()
_init_lock = threading.Lock()
_ready = False

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free', plan_until DOUBLE PRECISION, is_admin INTEGER NOT NULL DEFAULT 0,
        telegram_chat_id TEXT, settings TEXT NOT NULL DEFAULT '{}', disabled INTEGER NOT NULL DEFAULT 0,
        failed_logins INTEGER NOT NULL DEFAULT 0, locked_until DOUBLE PRECISION)""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, csrf TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
        expires_at DOUBLE PRECISION NOT NULL, ip TEXT, ua TEXT)""",
    "CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id)",
    """CREATE TABLE IF NOT EXISTS activity (
        id TEXT PRIMARY KEY, user_id TEXT, at DOUBLE PRECISION NOT NULL, action TEXT NOT NULL, detail TEXT, ip TEXT)""",
    "CREATE INDEX IF NOT EXISTS activity_user ON activity(user_id, at)",
    """CREATE TABLE IF NOT EXISTS positions (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS positions_user ON positions(user_id, status)",
    """CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, user_id TEXT, provider TEXT NOT NULL, reference TEXT UNIQUE NOT NULL, plan TEXT,
        period TEXT, amount_cents BIGINT, currency TEXT, status TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
        raw TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS telegram_links (
        code TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS kv (
        name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    # límites de intentos compartidos entre reinicios e instancias (la clave es un hash; no guarda IP en claro)
    """CREATE TABLE IF NOT EXISTS rate_limits (
        k TEXT PRIMARY KEY, n INTEGER NOT NULL, expires_at DOUBLE PRECISION NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS rate_limits_exp ON rate_limits(expires_at)",
    # códigos de un solo uso para el primer alta del segundo factor del administrador (docs/BOOTSTRAP_ADMIN.md);
    # solo se guarda el hash del código
    """CREATE TABLE IF NOT EXISTS admin_enroll_tokens (
        token_hash TEXT PRIMARY KEY, source TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
        expires_at DOUBLE PRECISION NOT NULL, used_at DOUBLE PRECISION, used_by TEXT)""",
    # generación del líder para el fencing de los trabajos de fondo (radar/leader.py); una sola fila
    """CREATE TABLE IF NOT EXISTS leader_epoch (
        id INTEGER PRIMARY KEY, generation BIGINT NOT NULL, holder TEXT, acquired_at DOUBLE PRECISION)""",
    # 2.1.0 empieza como plataforma NUEVA (docs/REGISTRO_USUARIOS_PILOTO.md §1): una marca única por base y un archivo
    # histórico de lo que hubiera de la 2.0.0, separado de la autenticación (ninguna consulta de acceso lo lee)
    """CREATE TABLE IF NOT EXISTS platform_meta (
        k TEXT PRIMARY KEY, v TEXT NOT NULL, at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS legacy_archive (
        id TEXT PRIMARY KEY, source_table TEXT NOT NULL, source_id TEXT, archived_at DOUBLE PRECISION NOT NULL,
        data TEXT NOT NULL)""",
]


# Columnas añadidas después de crear la tabla: (tabla, columna, tipo). Solo se añaden si faltan.
MIGRATIONS = [
    ("users", "status", "TEXT NOT NULL DEFAULT 'active'"),     # pending | active | rejected
    ("users", "contact", "TEXT"),
    ("users", "request_note", "TEXT"),
    ("users", "approved_at", "DOUBLE PRECISION"),
    ("users", "approved_by", "TEXT"),
    ("users", "totp_secret", "TEXT"),                          # verificación en dos pasos (RFC 6238)
    ("users", "totp_enabled", "INTEGER NOT NULL DEFAULT 0"),
    ("users", "totp_last_step", "BIGINT"),                     # último paso aceptado: un código no vale dos veces
    ("users", "consent_at", "DOUBLE PRECISION"),               # aceptación de la política de datos y del aviso de riesgo
    ("users", "consent_version", "TEXT"),
]

# Esquema mínimo que el servidor necesita para arrancar. Si falta algo, no arranca.
REQUIRED = {
    "users": {"id", "email", "pw_hash", "created_at", "plan", "plan_until", "is_admin", "telegram_chat_id", "settings",
              "disabled", "failed_logins", "locked_until", "status", "contact", "request_note", "approved_at", "approved_by",
              "totp_secret", "totp_enabled", "totp_last_step", "consent_at", "consent_version"},
    "sessions": {"token_hash", "user_id", "csrf", "created_at", "expires_at", "ip", "ua"},
    "activity": {"id", "user_id", "at", "action", "detail", "ip"},
    "positions": {"id", "user_id", "status", "data", "updated_at"},
    "payments": {"id", "user_id", "provider", "reference", "plan", "period", "amount_cents", "currency", "status",
                 "verified", "raw", "created_at", "updated_at"},
    "telegram_links": {"code", "user_id", "expires_at"},
    "kv": {"name", "value", "updated_at"},
    "rate_limits": {"k", "n", "expires_at"},
    "admin_enroll_tokens": {"token_hash", "source", "created_at", "expires_at", "used_at", "used_by"},
    "platform_meta": {"k", "v", "at"},
    "legacy_archive": {"id", "source_table", "source_id", "archived_at", "data"},
}

PLATFORM = "2.1"
INIT_LOCK_ID = 7_212_100          # bloqueo consultivo de PostgreSQL para el arranque (número fijo de esta aplicación)
# Tablas ligadas a cuentas: en una base heredada de la 2.0.0 se ARCHIVAN (no se heredan) al primer arranque de 2.1.
# (tabla, clave, columnas de credenciales que NO se guardan ni en el archivo: no tienen valor legal ni contable)
LEGACY_TABLES = (
    ("users", "id", ("pw_hash", "totp_secret", "totp_last_step")),
    ("sessions", "token_hash", ("token_hash", "csrf")),
    ("telegram_links", "code", ("code",)),
    ("positions", "id", ()),
    ("payments", "id", ()),
    ("activity", "id", ()),
)
EPHEMERAL_TABLES = ("rate_limits",)       # contadores de intentos: se vacían, no se archivan


class PlatformError(RuntimeError):
    pass


class SchemaError(RuntimeError):
    pass


def _is_duplicate_column(e):
    """Único error de migración tolerado: la columna ya existe (p. ej. otra instancia la añadió a la vez)."""
    if type(e).__name__ == "DuplicateColumn":                                   # psycopg
        return True
    return isinstance(e, sqlite3.OperationalError) and "duplicate column name" in str(e).lower()


CONNECT_RETRY_S = (0.25, 0.5, 1.0, 2.0)      # esperas entre intentos de conexión (≈3,75 s en total)


def _connect():
    if IS_PG:
        import psycopg   # pip install "psycopg[binary]"
        kw = {} if "connect_timeout" in URL else {"connect_timeout": 10}
        # Reintento corto al CONECTAR (nunca se repite una sentencia aquí): tras un reinicio de PostgreSQL o de la
        # computación de Neon, la base responde unos instantes «the database system is starting up». Sin reintento,
        # cada petición que llegaba en ese momento devolvía 500 (15 en la prueba de estrés, docs/AUDITORIA_ESTRES_INTEGRAL.md).
        for wait in CONNECT_RETRY_S + (None,):
            try:
                c = psycopg.connect(URL, autocommit=True, **kw)
                break
            except psycopg.OperationalError:
                if wait is None:
                    raise
                time.sleep(wait)
        c.execute("SET client_encoding TO 'UTF8'")   # bases SQL_ASCII devolverían bytes en vez de texto
        return c
    c = sqlite3.connect(str(DATA_DIR / "app.db"), timeout=30, check_same_thread=False)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def conn():
    c = getattr(_local, "c", None)
    if c is None:
        c = _local.c = _connect()
    return c


def _sql(q):
    return q.replace("?", "%s") if IS_PG else q


def columns(table):
    c = conn()
    if IS_PG:
        cur = c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
                        "AND table_name = %s", (table,))
        return {r[0] for r in cur.fetchall()}
    return {r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()}   # nombre de tabla fijo, no del usuario


def migrate():
    c = conn()
    for table, col, typ in MIGRATIONS:
        if col in columns(table):
            continue
        t = typ if IS_PG else typ.replace("DOUBLE PRECISION", "REAL").replace("BIGINT", "INTEGER")
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {t}")
        except Exception as e:
            if not _is_duplicate_column(e):
                raise SchemaError(f"No se pudo migrar {table}.{col}: {e}") from e
    if not IS_PG:
        c.commit()


def verify_schema():
    missing = {t: sorted(req - columns(t)) for t, req in REQUIRED.items()}
    missing = {t: m for t, m in missing.items() if m}
    if missing:
        raise SchemaError("Esquema de base de datos incompleto: " +
                          "; ".join(f"{t}: {', '.join(m)}" for t, m in missing.items()))


def _count(c, table):
    return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]     # nombres de tabla fijos, nunca del usuario


def _signs_of_2_1(c):
    """Huellas que la 2.0.0 nunca pudo dejar: si aparecen, la base es de 2.1 y NO se archiva nada."""
    q = ("SELECT COUNT(*) FROM users WHERE approved_at IS NOT NULL OR consent_at IS NOT NULL OR totp_enabled = 1 "
         "OR totp_secret IS NOT NULL OR status <> 'active'")
    return {"usuarios_2_1": c.execute(q).fetchone()[0], "codigos_de_alta": _count(c, "admin_enroll_tokens")}


def platform_status():
    """Estado de la marca de plataforma, sin cambiar nada (para preflight y para las pruebas)."""
    init()
    rows = all_("SELECT k, v, at FROM platform_meta", ())
    return {r["k"]: r["v"] for r in rows}


def init_platform(c=None):
    """Primer arranque de 2.1.0 sobre una base: la convierte en plataforma NUEVA, una sola vez (idempotente).

    * Base vacía: solo deja la marca `platform = 2.1`.
    * Base heredada de 2.0.0 (cuentas sin huellas de 2.1): en UNA transacción copia cada fila de las tablas de
      cuentas a `legacy_archive` (sin contraseñas, semillas TOTP, tokens de sesión ni códigos de Telegram), las borra
      de las tablas activas y deja la marca. Ninguna cuenta, sesión, token, plan o vínculo de 2.0.0 sigue valiendo.
    * Base de 2.1 sin marca (p. ej. una prueba anterior a este cambio): NO toca nada y se niega a arrancar, salvo que
      el responsable confirme `CRYPTO_RADAR_PLATFORM_ADOPT=1` (marca la base como 2.1 tal como está).
    Con varias instancias arrancando a la vez, un bloqueo de PostgreSQL (o BEGIN IMMEDIATE en SQLite) hace que solo
    una ejecute la conversión; las demás encuentran la marca.
    """
    c = c or conn()
    if c.execute("SELECT v FROM platform_meta WHERE k = 'platform'").fetchone():
        return {"result": "verificada"}
    ph = "%s" if IS_PG else "?"
    if IS_PG:
        c.execute("BEGIN")
        c.execute("LOCK TABLE platform_meta IN EXCLUSIVE MODE")
    else:
        c.execute("BEGIN IMMEDIATE")
    try:
        if c.execute("SELECT v FROM platform_meta WHERE k = 'platform'").fetchone():
            c.execute("ROLLBACK")
            return {"result": "verificada"}
        counts = {t: _count(c, t) for t, _, _ in LEGACY_TABLES}
        now = time.time()
        if not any(counts.values()):
            result, archived = "nueva", {}
        else:
            signs = _signs_of_2_1(c)
            if any(signs.values()):
                if os.environ.get("CRYPTO_RADAR_PLATFORM_ADOPT") != "1":
                    raise PlatformError(
                        "La base tiene cuentas de 2.1 pero no la marca de plataforma (" +
                        ", ".join(f"{k}: {v}" for k, v in signs.items()) + "). No se archiva nada. Si es correcto, "
                        "define CRYPTO_RADAR_PLATFORM_ADOPT=1 una vez para marcarla como 2.1 tal como está.")
                result, archived = "adoptada", {}
            else:
                result, archived = "archivada_2_0", {}
                for table, key, drop in LEGACY_TABLES:
                    cur = c.execute(f"SELECT * FROM {table}")
                    cols = [d[0] for d in cur.description]
                    rows = cur.fetchall()
                    for i, r in enumerate(rows):
                        rec = {k: v for k, v in zip(cols, r) if k not in drop}
                        src = None if key in drop else str(rec.get(key))
                        c.execute(f"INSERT INTO legacy_archive(id, source_table, source_id, archived_at, data) "
                                  f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                                  (f"2.0/{table}/{src if src is not None else i}", table, src, now,
                                   json.dumps(rec, ensure_ascii=False, default=str, sort_keys=True)))
                    c.execute(f"DELETE FROM {table}")
                    archived[table] = len(rows)
                for t in EPHEMERAL_TABLES:
                    c.execute(f"DELETE FROM {t}")
        meta = {"platform": PLATFORM, "initialized": result, "legacy_archived": json.dumps(archived, sort_keys=True)}
        for k, v in meta.items():
            c.execute(f"INSERT INTO platform_meta(k, v, at) VALUES ({ph}, {ph}, {ph})", (k, v, now))
        c.execute("COMMIT")
    except BaseException:
        c.execute("ROLLBACK")
        raise
    return {"result": result, "archived": archived}


def init():
    global _ready
    with _init_lock:
        if _ready:
            return
        c = conn()
        # Varias instancias arrancando a la vez (primer despliegue, despliegue sin corte de Render): en PostgreSQL,
        # «CREATE TABLE IF NOT EXISTS» simultáneos chocan en el catálogo (pg_type_typname_nsp_index). Un bloqueo
        # consultivo serializa la creación, la migración y la inicialización de la plataforma.
        if IS_PG:
            c.execute("SELECT pg_advisory_lock(%s)", (INIT_LOCK_ID,))
        try:
            for stmt in SCHEMA:
                s = stmt if IS_PG else stmt.replace("DOUBLE PRECISION", "REAL").replace("BIGINT", "INTEGER")
                c.execute(s)
            if not IS_PG:
                c.commit()
            migrate()
            verify_schema()
            init_platform(c)
        finally:
            if IS_PG:
                c.execute("SELECT pg_advisory_unlock(%s)", (INIT_LOCK_ID,))
        _ready = True


def execute(q, params=()):
    init()
    for attempt in range(2):
        try:
            c = conn()
            cur = c.execute(_sql(q), params)
            if not IS_PG:
                c.commit()
            return cur
        except Exception as e:
            # Conexión caída (Neon la cierra al suspender la base, o el servidor la terminó): reconectar una vez.
            # psycopg marca la conexión como `broken`; el primer error dice «terminating connection…», no «closed».
            # En ese caso la sentencia no llegó a ejecutarse, por eso repetirla es seguro.
            c0 = getattr(_local, "c", None)
            dead = c0 is not None and (getattr(c0, "broken", False) or getattr(c0, "closed", False))
            if attempt == 0 and IS_PG and (dead or "closed" in str(e).lower()):
                try:
                    c0.close()
                except Exception:
                    pass
                _local.c = None
                continue
            raise


def one(q, params=()):
    cur = execute(q, params)
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def all_(q, params=()):
    cur = execute(q, params)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


class StaleLeader(RuntimeError):
    """La generación del líder con la que se inició el trabajo ya no es la vigente: la escritura se rechaza."""


# Generación del líder fijada por leader.job() para el hilo actual (None fuera de un trabajo de fondo).
FENCE = contextvars.ContextVar("crypto_radar_fence", default=None)
FENCE_HOOK = None                     # solo pruebas: se llama entre la comprobación y la escritura
STALE_SEEN = set()                    # generaciones rechazadas (el escáner captura excepciones: leader.job() las mira aquí)


def _fenced_upsert(name, v, gen):
    """Comprueba la generación y escribe en la MISMA transacción (FOR SHARE bloquea el incremento del nuevo líder)."""
    for attempt in range(2):
        c = conn()
        try:
            with c.transaction():
                c.execute("SET LOCAL lock_timeout = '10s'")
                row = c.execute("SELECT generation FROM leader_epoch WHERE id = 1 FOR SHARE").fetchone()
                if row is None or int(row[0]) != int(gen):
                    STALE_SEEN.add(int(gen))
                    raise StaleLeader(f"generación {gen} vencida (vigente: {row[0] if row else '—'})")
                if FENCE_HOOK:
                    FENCE_HOOK(c)
                c.execute("INSERT INTO kv(name, value, updated_at) VALUES (%s, %s, %s) ON CONFLICT (name) DO UPDATE SET "
                          "value = EXCLUDED.value, updated_at = EXCLUDED.updated_at", (name, v, time.time()))
            return
        except StaleLeader:
            raise
        except Exception:
            # conexión caída antes o durante la transacción: PostgreSQL la revierte entera. Se reintenta una vez en
            # una conexión nueva, y la generación se vuelve a comprobar, así que el reintento nunca escribe con una vencida.
            dead = getattr(c, "broken", False) or getattr(c, "closed", False)
            if attempt == 0 and dead:
                try:
                    c.close()
                except Exception:
                    pass
                _local.c = None
                continue
            raise


def upsert_kv(name, value):
    v = json.dumps(value, ensure_ascii=False, default=str)
    gen = FENCE.get()
    if IS_PG and gen is not None:
        init()
        return _fenced_upsert(name, v, gen)
    if IS_PG:
        execute("INSERT INTO kv(name, value, updated_at) VALUES (?, ?, ?) ON CONFLICT (name) DO UPDATE SET "
                "value = EXCLUDED.value, updated_at = EXCLUDED.updated_at", (name, v, time.time()))
    else:
        execute("INSERT OR REPLACE INTO kv(name, value, updated_at) VALUES (?, ?, ?)", (name, v, time.time()))


def get_kv(name, default=None):
    r = one("SELECT value FROM kv WHERE name = ?", (name,))
    if not r:
        return default
    try:
        return json.loads(r["value"])
    except Exception:
        return default


def get_kv_fields(name, keys):
    """Solo algunas claves de primer nivel de un documento kv, extraídas EN la base.

    Evita descargar el documento entero (latest.json pesa cientos de KB) cuando solo hace falta su fecha:
    la transferencia de red de Neon cuenta para la cuota del plan (docs/UNIT_ECONOMICS.md §Neon).
    Devuelve {clave: valor}; las claves ausentes valen None. Los valores no escalares vuelven decodificados."""
    keys = [str(k) for k in keys]
    if IS_PG:
        cols = ", ".join(f"(value::jsonb) -> %s::text AS k{i}" for i in range(len(keys)))
        r = one(f"SELECT {cols} FROM kv WHERE name = %s".replace("%s", "?"), tuple(keys) + (name,))
    else:
        cols = ", ".join(f"json_extract(value, ?) AS k{i}" for i in range(len(keys)))
        r = one(f"SELECT {cols} FROM kv WHERE name = ?", tuple("$." + k for k in keys) + (name,))
    out = {k: None for k in keys}
    if not r:
        return out
    for i, k in enumerate(keys):
        v = r.get(f"k{i}")
        if isinstance(v, str) and IS_PG is False and v[:1] in "[{":
            try:
                v = json.loads(v)
            except Exception:
                pass
        out[k] = v
    return out


def endpoint_warning(url=None):
    """Aviso si DATABASE_URL apunta al pooler de Neon (docs/ARQUITECTURA_CONEXIONES_NEON.md). No cambia la URL."""
    from urllib.parse import urlsplit
    host = urlsplit(url if url is not None else URL).hostname or ""
    if "-pooler." in host:
        return ("AVISO: DATABASE_URL usa el pooler de Neon (PgBouncer, modo transacción). Esta app usa estado de sesión "
                "(SET al conectar y candado consultivo del arranque): usa el endpoint directo. El candado del líder ya "
                "usa el directo automáticamente.")
    return None


def backend():
    return "postgresql" if IS_PG else "sqlite"
