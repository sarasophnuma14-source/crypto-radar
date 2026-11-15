"""Prueba de carga LOCAL (nunca contra producción) con 10, 50 y 100 usuarios simultáneos.

Uso:  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/carga.py [salida.json]

- Crea una base PostgreSQL temporal y arranca el servidor real (`server.serve`, sin planificador) en otro proceso.
- El informe de mercado sale de un escaneo con datos sintéticos (tests/fake_market.py): mismo tamaño que uno real.
- Cada nivel: todos los usuarios inician sesión a la vez (ráfaga de scrypt) y luego, durante 30 s, cada uno repite
  peticiones del panel con 1 s de pausa: /api/state 40 %, /api/me 20 %, /api/alerts 15 %, /api/positions 15 %,
  POST /api/me/settings 10 %.
- Mide latencia (p50/p95/p99/máx.), errores por código, memoria (VmRSS) y CPU del proceso servidor, conexiones a
  PostgreSQL, esperas por bloqueos (pg_locks sin conceder) y consultas lentas (> 50 ms, registro de PostgreSQL).
- Al terminar borra la base temporal.
"""
import http.client
import json
import os
import random
import secrets
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
PG_LOG = os.environ.get("PG_LOG", "/var/tmp/crypto-radar-pg/log")
DB = f"cr_carga_{secrets.token_hex(3)}"
PW = "clave de carga segura 1"
LEVELS = [int(x) for x in os.environ.get("NIVELES", "10,50,100").split(",")]
DURATION = float(os.environ.get("DURACION_S", "30"))
THINK = float(os.environ.get("PAUSA_S", "1.0"))

SERVER = r"""
import os, sys, json
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/tests")
import fake_market; fake_market.install()
from radar import auth, db, scanner, server, alerts
alerts._desktop = lambda *a: None
db.init(); auth.ensure_admin()
admin = db.one("SELECT * FROM users WHERE email = ?", ("jefe.carga",))
rep = scanner.run_scan()
plans = ["free", "pro", "elite"]
for i in range(int(sys.argv[3])):
    auth.reset_rate_limits()
    uid = auth.request_access(f"carga{i:03d}", sys.argv[4], ip=f"10.5.{i // 250}.{i % 250}", consent=auth.POLICY_VERSION)
    auth.admin_set_status(admin, uid, "approve", plans[i % 3], 30)
auth.reset_rate_limits()
print("LISTO", len(rep["assets"]), flush=True)
server.serve(int(sys.argv[2]), schedule=False)
"""


def pg(sql, dbname=None, fetch=True):
    import psycopg
    u = ADMIN_URL if not dbname else ADMIN_URL.rsplit("/", 1)[0] + "/" + dbname
    with psycopg.connect(u, autocommit=True) as c:
        cur = c.execute(sql)
        return cur.fetchall() if fetch and cur.description else None


def free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def proc_stats(pid):
    with open(f"/proc/{pid}/status") as f:
        rss = next(int(x.split()[1]) for x in f if x.startswith("VmRSS"))
    with open(f"/proc/{pid}/stat") as f:
        parts = f.read().rsplit(")", 1)[1].split()
    ticks = int(parts[11]) + int(parts[12])
    threads = int(parts[17])
    return rss / 1024, ticks / os.sysconf("SC_CLK_TCK"), threads


class Client:
    def __init__(self, port, name, ip=None):
        self.port, self.name, self.cookie, self.csrf, self.ip = port, name, None, None, ip

    def req(self, method, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Content-Type": "application/json"}
        if self.ip:                       # como el proxy de Render: cada usuario llega con su propia IP
            h["X-Forwarded-For"] = self.ip
        if self.cookie:
            h["Cookie"] = self.cookie
        if self.csrf and method == "POST":
            h["X-CSRF-Token"] = self.csrf
        t = time.perf_counter()
        try:
            c.request(method, path, json.dumps(body).encode() if body is not None else None, h)
            r = c.getresponse(); data = r.read(); st = r.status
            ck = r.getheader("Set-Cookie")
            if ck and "cr_session=" in ck:
                self.cookie = ck.split(";")[0]
        except Exception as e:
            st, data = f"EXC:{type(e).__name__}", b""
        finally:
            c.close()
        return st, (time.perf_counter() - t) * 1000, data


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs); k = (len(xs) - 1) * p / 100
    f = int(k); return round(xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f), 1)


def summarize(samples):
    lat = [s[1] for s in samples]
    by = {}
    for s in samples:
        by.setdefault(str(s[0]), 0); by[str(s[0])] += 1
    return {"n": len(samples), "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99),
            "max_ms": round(max(lat), 1) if lat else None, "codigos": by}


def mon_sessions(mon):
    """Conexiones que abrió el propio monitor (2 por muestra), para descontarlas."""
    return 2 * mon["lock_samples"]


def run_level(port, pid, n, offset):
    shared = os.environ.get("IP_COMPARTIDA") == "1"     # todos detrás de la misma IP (NAT/CGNAT)
    clients = [Client(port, f"carga{(offset + i):03d}", None if shared else f"10.77.{(offset + i) // 250}.{(offset + i) % 250}")
               for i in range(n)]
    logins, samples, stop = [], [], threading.Event()
    mon = {"rss": [], "threads": [], "pg_conns": [], "lock_waits": 0, "lock_samples": 0}

    def monitor():
        while not stop.is_set():
            rss, _, th = proc_stats(pid); mon["rss"].append(rss); mon["threads"].append(th)
            try:
                mon["pg_conns"].append(pg(f"SELECT count(*) FROM pg_stat_activity WHERE datname = '{DB}'")[0][0])
                w = pg("SELECT count(*) FROM pg_locks WHERE NOT granted")[0][0]
                mon["lock_samples"] += 1; mon["lock_waits"] += int(w > 0)
            except Exception:
                pass
            time.sleep(0.25)

    def login(c):
        st, ms, data = c.req("POST", "/api/auth/login", {"username": c.name, "password": PW})
        if st == 200:
            c.csrf = json.loads(data)["csrf"]
        logins.append((st, ms))

    def user_loop(c, deadline):
        rnd = random.Random(c.name)
        while time.time() < deadline:
            x = rnd.random()
            if x < .40: s = c.req("GET", "/api/state")
            elif x < .60: s = c.req("GET", "/api/me")
            elif x < .75: s = c.req("GET", "/api/alerts")
            elif x < .90: s = c.req("GET", "/api/positions")
            else: s = c.req("POST", "/api/me/settings", {"risk_per_trade_pct": round(rnd.uniform(0.5, 2), 2)})
            samples.append((s[0], s[1])); time.sleep(THINK)

    sess0 = pg(f"SELECT sessions FROM pg_stat_database WHERE datname = '{DB}'")[0][0]
    _, cpu0, _ = proc_stats(pid); t0 = time.time()
    m = threading.Thread(target=monitor, daemon=True); m.start()
    ts = [threading.Thread(target=login, args=(c,)) for c in clients]
    tl = time.time(); [t.start() for t in ts]; [t.join() for t in ts]; login_wall = time.time() - tl
    deadline = time.time() + DURATION
    ts = [threading.Thread(target=user_loop, args=(c, deadline)) for c in clients if c.csrf]
    [t.start() for t in ts]; [t.join() for t in ts]
    stop.set(); m.join()
    _, cpu1, _ = proc_stats(pid); wall = time.time() - t0
    sess1 = pg(f"SELECT sessions FROM pg_stat_database WHERE datname = '{DB}'")[0][0]
    s = summarize(samples)
    s["rps"] = round(s["n"] / DURATION, 1)
    plan402 = s["codigos"].get("402", 0)
    errors = {k: v for k, v in s["codigos"].items() if k not in ("200", "402")}
    return {"usuarios": n, "login": summarize([(a, b) for a, b in logins]) | {"segundos_rafaga": round(login_wall, 2)},
            "panel": s, "errores": errors, "respuestas_402_por_plan": plan402,
            "rss_mb_max": round(max(mon["rss"]), 1), "rss_mb_min": round(min(mon["rss"]), 1),
            "hilos_max": max(mon["threads"]), "cpu_pct_medio": round((cpu1 - cpu0) / wall * 100, 1),
            "pg_conexiones_max": max(mon["pg_conns"] or [0]),
            "pg_conexiones_abiertas": sess1 - sess0,
            "peticiones_http": len(samples) + len(logins),
            "muestras_con_esperas_por_bloqueo": f"{mon['lock_waits']}/{mon['lock_samples']}"}


def main(out=None):
    if not ADMIN_URL:
        sys.exit("Define PG_ADMIN_URL (base de pruebas local)")
    total = sum(LEVELS)
    pg(f"CREATE DATABASE {DB}", fetch=False)
    pg(f"ALTER DATABASE {DB} SET log_min_duration_statement = 50", fetch=False)
    log_start = os.path.getsize(PG_LOG) if os.path.exists(PG_LOG) else 0
    port = free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_", "TELEGRAM_"))}
    env.update({"DATABASE_URL": ADMIN_URL.rsplit("/", 1)[0] + "/" + DB, "CRYPTO_RADAR_ACCOUNTS": "1",
                "CRYPTO_RADAR_HOME": tempfile.mkdtemp(prefix="cr-carga-"), "CRYPTO_RADAR_ADMIN_USER": "jefe.carga",
                "CRYPTO_RADAR_ADMIN_PASSWORD": "clave del jefe de carga 1", "CRYPTO_RADAR_ADMIN_TOTP": "optional",
                "CRYPTO_RADAR_HOST": "127.0.0.1", "CRYPTO_RADAR_TRUSTED_PROXIES": "127.0.0.1/32"})
    import shutil
    shutil.copytree(ROOT / "web", Path(env["CRYPTO_RADAR_HOME"]) / "web")
    srv = subprocess.Popen([sys.executable, "-c", SERVER, str(ROOT), str(port), str(total), PW], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    R = {"entorno": {"cpu": os.cpu_count(), "python": sys.version.split()[0], "postgres": (lambda v: v.decode() if isinstance(v, bytes) else v)(pg("SHOW server_version")[0][0]),
                     "duracion_s": DURATION, "pausa_s": THINK}, "niveles": []}
    try:
        t = time.time()
        line = srv.stdout.readline()
        if not line.startswith("LISTO"):
            raise RuntimeError(line + srv.stdout.read()[-2000:])
        R["entorno"]["activos_en_informe"] = int(line.split()[1]); R["entorno"]["preparacion_s"] = round(time.time() - t, 1)
        for _ in range(50):
            try:
                if Client(port, "").req("GET", "/healthz")[0] == 200:
                    break
            except Exception:
                pass
            time.sleep(0.2)
        rss0, _, th0 = proc_stats(srv.pid); R["entorno"]["rss_mb_reposo"] = round(rss0, 1)
        off = 0
        for n in LEVELS:
            r = run_level(port, srv.pid, n, off); off += n
            R["niveles"].append(r)
            print(json.dumps(r, ensure_ascii=False))
        rss1, _, _ = proc_stats(srv.pid); R["entorno"]["rss_mb_final"] = round(rss1, 1)
        R["consultas_lentas_por_sentencia"] = {}
        if os.path.exists(PG_LOG):
            with open(PG_LOG, errors="replace") as f:
                f.seek(log_start)
                import re
                for ln in f:
                    m = re.search(r"duration: ([\d.]+) ms\s+statement: (.*)", ln)
                    if m:
                        key = re.sub(r"\s+", " ", m.group(2))[:90]
                        d = R["consultas_lentas_por_sentencia"].setdefault(key, {"n": 0, "max_ms": 0})
                        d["n"] += 1; d["max_ms"] = max(d["max_ms"], float(m.group(1)))
        R["consultas_lentas_total"] = sum(v["n"] for v in R["consultas_lentas_por_sentencia"].values())
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
        pg(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)", fetch=False)
    if out:
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    print(json.dumps({k: v for k, v in R.items() if k != "niveles"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
