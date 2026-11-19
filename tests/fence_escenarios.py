"""Escenarios de fencing en un proceso limpio, para tests/test_fiabilidad.py (clase FencingGeneracion).

Uso: DATABASE_URL=... python3 tests/fence_escenarios.py <escenario>
Imprime una línea JSON con lo observado. Los escenarios usan las funciones reales de radar/leader.py y radar/db.py.
"""
import json
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import db, leader  # noqa: E402
import psycopg  # noqa: E402

URL = os.environ["DATABASE_URL"]
out = {}


def admin():
    return psycopg.connect(URL, autocommit=True)


def kv(a):
    r = a.execute("SELECT value FROM kv WHERE name = 'fence_test'").fetchone()
    return json.loads(r[0]) if r else None


def epoch(a):
    return a.execute("SELECT generation FROM leader_epoch WHERE id = 1").fetchone()[0]


def write(gen, payload):
    tok = db.FENCE.set(gen)
    try:
        db.upsert_kv("fence_test", payload)
        return "ok"
    except db.StaleLeader:
        return "rechazada"
    finally:
        db.FENCE.reset(tok)


def become_leader():
    c = leader._try_acquire(leader._pg()[1])
    assert c is not None, "no se obtuvo el candado"
    leader._state.update(conn=c, leader=True, since=time.time(), generation=c.generation)
    return c


def new_leader_elsewhere(a):
    """Otra instancia toma el relevo: mismo UPDATE que radar/leader.py al adquirir el candado."""
    return a.execute("UPDATE leader_epoch SET generation = generation + 1, holder = 'otra' WHERE id = 1 "
                     "RETURNING generation").fetchone()[0]


def escritura_tardia():
    """4. El líder antiguo está a mitad de un trabajo (dentro de leader.job()) cuando otra instancia toma el relevo y
    escribe su resultado. La escritura tardía del antiguo se rechaza, el resultado nuevo se conserva y el antiguo deja de
    considerarse líder."""
    a = admin()
    db.init()
    become_leader()
    old = leader.generation()
    with leader.job() as ok:
        out["job_ok"] = ok
        out["fase1"] = write(db.FENCE.get(), {"worker": "viejo", "gen": old, "phase": 1})
        newg = new_leader_elsewhere(a)
        out["nuevo"] = write(newg, {"worker": "nuevo", "gen": newg, "phase": 1})
        from radar import storage
        try:
            storage.write("fence_test", {"worker": "viejo", "gen": old, "phase": 2})   # la escritura tardía
            out["tardia"] = "ok"
        except db.StaleLeader:
            out["tardia"] = "rechazada"
            raise                                       # como haría el escáner si no la capturase: job() la absorbe
    out.update(old=old, new=newg, kv=kv(a), sigue_lider=leader.is_leader(), epoch=epoch(a))


def generacion_vencida():
    """5. Sobrescritura directa con una generación vencida, con una inexistente y con la vigente."""
    a = admin()
    db.init()
    become_leader()
    g = leader.generation()
    out["vigente"] = write(g, {"worker": "w", "gen": g, "phase": 1})
    before = kv(a)
    out["anterior"] = write(g - 1, {"worker": "w", "gen": g - 1, "phase": 9})
    out["futura"] = write(g + 1, {"worker": "w", "gen": g + 1, "phase": 9})
    out.update(gen=g, before=before, after=kv(a))


def caida_conexion(avanza):
    """7. La conexión de la escritura se corta DENTRO de la transacción (entre la comprobación y el INSERT).
    avanza=False: nadie tomó el relevo; el reintento en otra conexión vuelve a comprobar y escribe una sola vez.
    avanza=True: mientras tanto otra instancia tomó el relevo; el reintento se rechaza y no queda nada escrito."""
    a = admin()
    db.init()
    become_leader()
    g = leader.generation()
    out["v1"] = write(g, {"worker": "w", "gen": g, "phase": 1})
    calls = []

    def hook(c):
        calls.append(c.info.backend_pid)
        if len(calls) == 1:
            if avanza:
                # el UPDATE del nuevo líder espera al FOR SHARE: se lanza en otro hilo y avanza al cortarse la sesión
                threading.Thread(target=lambda: out.__setitem__("nuevo", new_leader_elsewhere(admin())), daemon=True).start()
                time.sleep(0.5)
            a.execute("SELECT pg_terminate_backend(%s)", (c.info.backend_pid,))
            time.sleep(0.3)
    db.FENCE_HOOK = hook
    try:
        out["v2"] = write(g, {"worker": "w", "gen": g, "phase": 2})
    except Exception as e:
        out["v2"] = f"error {type(e).__name__}"
    db.FENCE_HOOK = None
    time.sleep(0.5)
    out.update(gen=g, intentos=len(calls), pids_distintos=len(set(calls)), kv=kv(a), epoch=epoch(a))


if __name__ == "__main__":
    sc = sys.argv[1]
    {"escritura_tardia": escritura_tardia, "generacion_vencida": generacion_vencida,
     "caida_conexion": lambda: caida_conexion(False), "caida_conexion_relevo": lambda: caida_conexion(True)}[sc]()
    print(json.dumps(out, default=str), flush=True)
