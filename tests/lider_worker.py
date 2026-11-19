"""Proceso de prueba para tests/test_fiabilidad.py: simula una instancia de Render.

Uso: DATABASE_URL=... python3 tests/lider_worker.py <nombre> [rapido|lento]
Elige líder con radar/leader.py y, en bucle, abre un trabajo protegido con leader.job():
- registra el trabajo en la tabla leader_jobs (para comprobar que nunca trabajan dos a la vez);
- escribe un resultado en kv («fence_test») con storage.write, que pasa por el fencing por generación.
Modo «lento»: cada trabajo escribe la fase 1, espera LENTO_S segundos y escribe la fase 2 (simula un escaneo largo).
Las escrituras rechazadas por generación vencida se imprimen como «rechazada <gen>».
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import db, leader, storage  # noqa: E402
import psycopg  # noqa: E402

name = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "rapido"
slow = float(os.environ.get("LENTO_S", "3"))
w = None


def log_job():
    global w
    for _ in range(2):
        try:
            if w is None or w.closed or w.broken:
                w = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
            w.execute("INSERT INTO leader_jobs(worker, at) VALUES (%s, clock_timestamp())", (name,))
            return
        except Exception:
            w = None


def write(phase, n):
    try:
        storage.write("fence_test", {"worker": name, "gen": db.FENCE.get(), "phase": phase, "n": n})
        return True
    except db.StaleLeader:
        print(f"rechazada gen={db.FENCE.get()} fase={phase} n={n}", flush=True)
        return False
    except Exception as e:                       # base reiniciándose: el trabajo falla sin escribir
        print(f"error {type(e).__name__}", flush=True)
        return False


leader.start()
print("listo", flush=True)
n = 0
while True:
    n += 1
    try:
        with leader.job() as ok:
            if ok:
                log_job()
                if write(1, n) and mode == "lento":
                    time.sleep(slow)
                    write(2, n)
    except Exception as e:
        print(f"error {type(e).__name__}", flush=True)
    time.sleep(0.2)
