"""Base de datos: PostgreSQL si hay DATABASE_URL (producción, p. ej. Neon), SQLite local si no.

Tablas: users, sessions, activity, positions, payments, telegram_links y kv (documentos JSON del sistema:
último informe, alertas, diario... para que sobrevivan a los reinicios del disco efímero de Render).
Todas las consultas usan parámetros (nunca se concatena texto del usuario en el SQL).
"""
from __future__ import annotations
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
]


# Columnas añadidas después de crear la tabla: (tabla, columna, tipo). Solo se añaden si faltan.
MIGRATIONS = [
    ("users", "status", "TEXT NOT NULL DEFAULT 'active'"),     # pending | active | rejected
    ("users", "contact", "TEXT"),
    ("users", "request_note", "TEXT"),
    ("users", "approved_at", "DOUBLE PRECISION"),
    ("users", "approved_by", "TEXT"),
]

# Esquema mínimo que el servidor necesita para arrancar. Si falta algo, no arranca.
REQUIRED = {
    "users": {"id", "email", "pw_hash", "created_at", "plan", "plan_until", "is_admin", "telegram_chat_id", "settings",
              "disabled", "failed_logins", "locked_until", "status", "contact", "request_note", "approved_at", "approved_by"},
    "sessions": {"token_hash", "user_id", "csrf", "created_at", "expires_at", "ip", "ua"},
    "activity": {"id", "user_id", "at", "action", "detail", "ip"},
    "positions": {"id", "user_id", "status", "data", "updated_at"},
    "payments": {"id", "user_id", "provider", "reference", "plan", "period", "amount_cents", "currency", "status",
                 "verified", "raw", "created_at", "updated_at"},
    "telegram_links": {"code", "user_id", "expires_at"},
    "kv": {"name", "value", "updated_at"},
    "rate_limits": {"k", "n", "expires_at"},
}


class SchemaError(RuntimeError):
    pass


def _is_duplicate_column(e):
    """Único error de migración tolerado: la columna ya existe (p. ej. otra instancia la añadió a la vez)."""
    if type(e).__name__ == "DuplicateColumn":                                   # psycopg
        return True
    return isinstance(e, sqlite3.OperationalError) and "duplicate column name" in str(e).lower()


def _connect():
    if IS_PG:
        import psycopg   # pip install "psycopg[binary]"
        c = psycopg.connect(URL, autocommit=True)
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
        t = typ if IS_PG else typ.replace("DOUBLE PRECISION", "REAL")
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


def init():
    global _ready
    with _init_lock:
        if _ready:
            return
        c = conn()
        for stmt in SCHEMA:
            s = stmt if IS_PG else stmt.replace("DOUBLE PRECISION", "REAL").replace("BIGINT", "INTEGER")
            c.execute(s)
        if not IS_PG:
            c.commit()
        migrate()
        verify_schema()
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
            # conexión caída (Neon cierra las inactivas): reconectar una vez
            if attempt == 0 and IS_PG and "closed" in str(e).lower():
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


def upsert_kv(name, value):
    v = json.dumps(value, ensure_ascii=False, default=str)
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


def backend():
    return "postgresql" if IS_PG else "sqlite"
