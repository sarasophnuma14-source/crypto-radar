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
"""
from __future__ import annotations
import os
import threading
import time

LOCK_ID = 7_315_002_101          # distinto del candado de inicialización de esquema (db.INIT_LOCK_ID)
RETRY_S = float(os.environ.get("CRYPTO_RADAR_LEADER_RETRY_S", "15"))
CONFIRM_TIMEOUT_MS = 5000
_CONN_KW = {"connect_timeout": 10, "keepalives": 1, "keepalives_idle": 10, "keepalives_interval": 5,
            "keepalives_count": 3, "tcp_user_timeout": 20000,
            "options": f"-c statement_timeout={CONFIRM_TIMEOUT_MS}"}
_state = {"leader": False, "since": None, "conn": None, "started": False}
_lock = threading.Lock()


def _pg():
    from . import db
    return db.IS_PG, db.URL


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
    return c


def _drop(reason):
    with _lock:
        was = _state["leader"]
        try:
            if _state["conn"] is not None:
                _state["conn"].close()
        except Exception:
            pass
        _state.update(conn=None, leader=False, since=None)
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
                        _state.update(conn=c, leader=True, since=time.time())
                    print("Instancia líder: ejecuta el escaneo, el paper trading y Telegram", flush=True)
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


def wait(poll_s=5):
    """Bloquea el hilo de fondo que la llama hasta que esta instancia sea líder."""
    while not is_leader():
        time.sleep(poll_s)
