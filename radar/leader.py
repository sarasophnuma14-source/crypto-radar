"""Instancia única para el trabajo de fondo (hallazgo M-2 de docs/AUDITORIA_INTEGRAL_CRYPTO_RADAR.md).

Durante un despliegue sin corte, Render mantiene dos instancias a la vez durante unos minutos. Sin coordinación, ambas
escanean (registros del 16-nov: escaneos a las 02:25 y 02:27), ambas hacen polling de Telegram (Telegram responde 409
a la segunda) y ambas podrían procesar el paper trading del día.

Con PostgreSQL, la instancia que obtiene un candado consultivo de sesión (pg_try_advisory_lock) en una conexión propia
es la «líder» y es la única que ejecuta escaneo, vigilancia de precio, memecoins, paper trading y polling de Telegram.
El candado se libera solo si el proceso muere o la conexión se cae; la otra instancia lo reintenta cada 15 s.
Sin PostgreSQL (uso local con SQLite o archivos) hay un solo proceso y siempre es líder.

El servidor web nunca espera por este candado: las peticiones se atienden en todas las instancias.

Un candado de sesión no tiene «lease» con caducidad: dura lo que dura la conexión. Para que una conexión colgada no deje
a dos instancias creyéndose líderes:
- la conexión del candado usa keepalives TCP y tcp_user_timeout (una red caída se detecta en unos 30 s);
- antes de cada trabajo, confirm() comprueba EN LA BASE (pg_locks) que esta conexión sigue teniendo el candado, con
  statement_timeout. Si no responde o ya no lo tiene, la instancia deja de ser líder antes de empezar el trabajo.
Si la base termina la sesión (pg_terminate_backend, reinicio o suspensión de Neon), el candado se libera y la otra
instancia lo toma en el siguiente intento.

FENCING POR GENERACIÓN (auditoría correctiva, hallazgo 3). Comprobar el candado antes de empezar no impide que una
instancia que lo perdió A MITAD de un trabajo escriba después. Por eso:
1. Cada adquisición incrementa en la base una generación monotónica (tabla leader_epoch, fila única) y la guarda.
2. Cada trabajo de fondo corre dentro de job(), que fija esa generación para el hilo (db.FENCE).
3. Toda escritura de resultados (db.upsert_kv, por donde pasan escaneo, memecoins, vigilancia y paper trading) se hace
   en UNA transacción que primero lee leader_epoch con FOR SHARE y solo escribe si la generación sigue siendo la suya.
   El incremento del nuevo líder (UPDATE) espera a que terminen esas transacciones y, una vez confirmado, toda escritura
   con la generación anterior se rechaza (StaleLeader) y se revierte. Una instancia antigua nunca sobrescribe el
   resultado de una nueva.
Las escrituras de las peticiones web (ajustes, cartera) no son trabajos de fondo y no llevan generación.

CONEXIONES (hallazgo 4, docs/ARQUITECTURA_CONEXIONES_NEON.md). El candado es de SESIÓN: no funciona a través del pooler
de Neon (PgBouncer en modo transacción). La conexión del líder usa CRYPTO_RADAR_LEADER_DATABASE_URL o, si no existe,
DATABASE_URL; si el host contiene «-pooler» se usa el endpoint directo equivalente (mismo host sin «-pooler»).
"""
from __future__ import annotations
import contextlib
import os
import socket
import threading
import time

LOCK_ID = 7_315_002_101          # distinto del candado de inicialización de esquema (db.INIT_LOCK_ID)
RETRY_S = float(os.environ.get("CRYPTO_RADAR_LEADER_RETRY_S", "15"))
CONFIRM_TIMEOUT_MS = 5000
_CONN_KW = {"connect_timeout": 10, "keepalives": 1, "keepalives_idle": 10, "keepalives_interval": 5,
            "keepalives_count": 3, "tcp_user_timeout": 20000,
            "options": f"-c statement_timeout={CONFIRM_TIMEOUT_MS}"}
_state = {"leader": False, "since": None, "conn": None, "started": False, "generation": None}
HOLDER = f"{socket.gethostname()[:40]}:{os.getpid()}"     # identifica la instancia en leader_epoch; sin datos personales
_lock = threading.Lock()


def _pg():
    from . import db
    return db.IS_PG, leader_url(db.URL)


def leader_url(app_url):
    """URL de la conexión del candado: nunca el pooler (los candados de sesión no sobreviven al modo transacción)."""
    url = (os.environ.get("CRYPTO_RADAR_LEADER_DATABASE_URL") or app_url or "").strip()
    return url.replace("-pooler.", ".", 1) if "-pooler." in url else url


def generation():
    return _state["generation"] if is_leader() else None


def is_leader():
    is_pg, _ = _pg()
    if not is_pg:
        return True
    return _state["leader"]


def status():
    return {"leader": is_leader(), "since": _state["since"]}


def _try_acquire(url):
    import psycopg
    kw = {k: v for k, v in _CONN_KW.items() if k not in url}
    c = psycopg.connect(url, autocommit=True, **kw)
    got = c.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]
    if not got:
        c.close()
        return None
    try:
        # nueva generación, en la base y con el candado ya tomado: espera a que terminen las escrituras protegidas de
        # la generación anterior (FOR SHARE) y, desde que se confirma, invalida todas las que vengan después
        c.execute("CREATE TABLE IF NOT EXISTS leader_epoch (id INTEGER PRIMARY KEY, generation BIGINT NOT NULL, "
                  "holder TEXT, acquired_at DOUBLE PRECISION)")
        gen = c.execute("INSERT INTO leader_epoch(id, generation, holder, acquired_at) VALUES (1, 1, %s, %s) "
                        "ON CONFLICT (id) DO UPDATE SET generation = leader_epoch.generation + 1, holder = EXCLUDED.holder, "
                        "acquired_at = EXCLUDED.acquired_at RETURNING generation", (HOLDER, time.time())).fetchone()[0]
    except Exception:
        c.close()
        raise
    c.generation = int(gen)
    return c


def _drop(reason):
    with _lock:
        was = _state["leader"]
        try:
            if _state["conn"] is not None:
                _state["conn"].close()
        except Exception:
            pass
        _state.update(conn=None, leader=False, since=None, generation=None)
    if was:
        print(f"Instancia líder: se perdió el candado ({reason}); se reintenta", flush=True)


def confirm():
    """Comprobación de «fencing» justo antes de un trabajo: ¿esta conexión sigue teniendo el candado EN LA BASE?

    Sin PostgreSQL siempre es True. Si la consulta falla, tarda más de CONFIRM_TIMEOUT_MS o el candado ya no es de esta
    sesión, la instancia deja de ser líder y devuelve False: el trabajo no se ejecuta."""
    is_pg, _ = _pg()
    if not is_pg:
        return True
    c = _state["conn"]
    if c is None or not _state["leader"]:
        return False
    try:
        with _lock:
            held = c.execute(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND granted AND pid = pg_backend_pid() "
                "AND ((classid::bigint << 32) | objid::bigint) = %s", (LOCK_ID,)).fetchone()[0]
    except Exception as e:
        _drop(type(e).__name__)
        return False
    if not held:
        _drop("la base ya no lo registra")
        return False
    return True


def _loop():
    _, url = _pg()
    while True:
        try:
            c = _state["conn"]
            if c is None:
                c = _try_acquire(url)
                if c is not None:
                    with _lock:
                        _state.update(conn=c, leader=True, since=time.time(), generation=c.generation)
                    print(f"Instancia líder (generación {c.generation}): ejecuta el escaneo, el paper trading y Telegram",
                          flush=True)
            else:
                confirm()                         # comprueba en la base que el candado sigue siendo de esta sesión
        except Exception as e:
            _drop(type(e).__name__)
        time.sleep(RETRY_S)


def start():
    """Arranca la elección de líder (una vez por proceso). Sin PostgreSQL no hace nada: siempre es líder."""
    is_pg, _ = _pg()
    with _lock:
        if _state["started"] or not is_pg:
            return
        _state["started"] = True
    threading.Thread(target=_loop, daemon=True, name="leader").start()


@contextlib.contextmanager
def job():
    """Trabajo de fondo protegido. Rinde True si esta instancia puede trabajar; False si no es líder.

    Con PostgreSQL fija la generación del líder para este hilo: cada db.upsert_kv del trabajo se confirma contra
    leader_epoch en su propia transacción. Si la generación vence a mitad del trabajo, las escrituras siguientes fallan
    con db.StaleLeader (no se escribe nada) y la instancia deja de ser líder."""
    from . import db
    is_pg, _ = _pg()
    if not is_pg:
        yield True
        return
    if not (is_leader() and confirm()):
        yield False
        return
    gen = _state["generation"]
    token = db.FENCE.set(gen)
    try:
        yield True
    except db.StaleLeader:
        pass
    finally:
        db.FENCE.reset(token)
        if gen in db.STALE_SEEN:
            db.STALE_SEEN.discard(gen)
            if _state["generation"] == gen:
                _drop("generación vencida")


def wait(poll_s=5):
    """Bloquea el hilo de fondo que la llama hasta que esta instancia sea líder."""
    while not is_leader():
        time.sleep(poll_s)
