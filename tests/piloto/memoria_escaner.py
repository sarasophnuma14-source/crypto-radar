"""Memoria de un escaneo en un proceso Python propio (lo que costaría aislar el escáner en un proceso aparte).

Uso:  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/memoria_escaner.py [salida.json]
      ESCANEO_REAL=1 → también un escaneo con datos reales (red; ≈2-3 min)

Para cada caso arranca un proceso nuevo que importa la app, mide su memoria antes de escanear (VmRSS) y el pico
(VmHWM) al terminar. Usa una base PostgreSQL temporal que borra al final.
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
DB = f"cr_mem_{secrets.token_hex(3)}"

CHILD = r"""
import os, sys, json, time
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/tests")
def vm():
    d = {}
    for x in open("/proc/self/status"):
        if x.startswith(("VmRSS", "VmHWM")):
            d[x.split(":")[0]] = round(int(x.split()[1]) / 1024, 1)
    return d
real = sys.argv[2] == "real"
if not real:
    import fake_market; fake_market.install()
from radar import scanner, alerts, db
alerts._desktop = lambda *a: None
db.init()
before = vm()
t = time.time(); r = scanner.run_scan(); dur = time.time() - t
after = vm()
print(json.dumps({"datos": sys.argv[2], "activos": len((r or {}).get("assets", [])), "s": round(dur, 1),
                  "error": scanner.status.get("last_error"), "rss_mb_tras_importar": before["VmRSS"],
                  "pico_mb": after["VmHWM"], "rss_mb_al_terminar": after["VmRSS"]}))
"""


def pg(sql):
    import psycopg
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute(sql)


def main(out=None):
    if not ADMIN_URL:
        sys.exit("Define PG_ADMIN_URL (base de pruebas local)")
    pg(f"CREATE DATABASE {DB}")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "TELEGRAM_"))}
    env.update(DATABASE_URL=ADMIN_URL.rsplit("/", 1)[0] + "/" + DB, CRYPTO_RADAR_HOME=tempfile.mkdtemp(prefix="cr-mem-"))
    res = {"python": sys.version.split()[0], "malloc_arena_max": os.environ.get("MALLOC_ARENA_MAX"), "casos": []}
    try:
        cases = ["sinteticos", "sinteticos"] + (["real"] if os.environ.get("ESCANEO_REAL") == "1" else [])
        for c in cases:
            p = subprocess.run([sys.executable, "-c", CHILD, str(ROOT), c], env=env, capture_output=True, text=True,
                               timeout=900)
            line = [x for x in p.stdout.splitlines() if x.startswith("{")]
            r = json.loads(line[-1]) if line else {"datos": c, "error": (p.stdout + p.stderr)[-500:]}
            res["casos"].append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    finally:
        pg(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
    if out:
        Path(out).write_text(json.dumps(res, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
