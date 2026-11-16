"""Proceso de prueba para tests/test_fiabilidad.py (clase LiderMultiproceso): simula una instancia de Render.

Uso: DATABASE_URL=... python3 tests/lider_worker.py <nombre>
Elige líder con radar/leader.py y, cada 0,2 s, si es líder y confirm() lo confirma en la base, registra un «trabajo»
en la tabla leader_jobs. Las pruebas leen esa tabla para comprobar que nunca trabajan dos instancias a la vez.
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import leader  # noqa: E402
import psycopg  # noqa: E402

name = sys.argv[1]
w = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)
leader.start()
print("listo", flush=True)
while True:
    if leader.is_leader() and leader.confirm():
        w.execute("INSERT INTO leader_jobs(worker, at) VALUES (%s, clock_timestamp())", (name,))
    time.sleep(0.2)
