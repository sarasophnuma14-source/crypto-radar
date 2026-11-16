"""Instancia única para el trabajo de fondo (hallazgo M-2 de docs/AUDITORIA_INTEGRAL_CRYPTO_RADAR.md).

Durante un despliegue sin corte, Render mantiene dos instancias a la vez durante unos minutos. Sin coordinación, ambas
escanean (registros del 16-nov: escaneos a las 02:25 y 02:27), ambas hacen polling de Telegram (Telegram responde 409
a la segunda) y ambas podrían procesar el paper trading del día.

Con PostgreSQL, la instancia que obtiene un candado consultivo de sesión (pg_try_advisory_lock) en una conexión propia
es la «líder» y es la única que ejecuta escaneo, vigilancia de precio, memecoins, paper trading y polling de Telegram.
El candado se libera solo si el proceso muere o la conexión se cae; la otra instancia lo reintenta cada 15 s.
Sin PostgreSQL (uso local con SQLite o archivos) hay un solo proceso y siempre es líder.

El servidor web nunca espera por este candado: las peticiones se atienden en todas las instancias.
"""
from __future__ import annotations
import threading
import time

LOCK_ID = 7_315_002_101          # distinto del candado de inicialización de esquema (db.INIT_LOCK_ID)
RETRY_S = 15
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
    kw = {} if "connect_timeout" in url else {"connect_timeout": 10}
    c = psycopg.connect(url, autocommit=True, **kw)
    got = c.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]
    if not got:
        c.close()
        return None
    return c


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
                c.execute("SELECT 1")             # comprueba que la conexión (y con ella el candado) sigue viva
        except Exception as e:
            if _state["leader"]:
                print(f"Instancia líder: se perdió el candado ({type(e).__name__}); se reintenta", flush=True)
            with _lock:
                try:
                    if _state["conn"] is not None:
                        _state["conn"].close()
                except Exception:
                    pass
                _state.update(conn=None, leader=False, since=None)
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
