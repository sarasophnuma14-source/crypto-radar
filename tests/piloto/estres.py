"""Prueba de estrés integral LOCAL (nunca contra producción): usuarios + escaneo + Telegram simulado a la vez.

Uso:
  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/estres.py [salida.json]

Variables (todas opcionales):
  NIVELES=10,50,100        usuarios simultáneos de cada tramo (cada tramo usa usuarios nuevos)
  DURACION_S=90            duración de la actividad del panel en cada tramo
  ESCANEO_EN_S=5           segundos tras la ráfaga de inicios de sesión en que el administrador lanza un escaneo
                           (POST /api/scan, el mismo camino que el botón del panel); -1 = sin escaneo
  REPETIR_ESCANEO=0        1 = al terminar un escaneo se lanza otro tras PAUSA_ESCANEO_S (resistencia)
  PAUSA_ESCANEO_S=15
  TELEGRAM_POR_S=2         comandos de Telegram simulados por segundo (/estado, /top, /cartera…); 0 = sin Telegram
  DIFUSION_CADA_S=30       cada cuánto se difunde una alerta de mercado a todos los chats vinculados (fanout)
  CAOS=                    p. ej. "cortar@20,reiniciar@45": a los N s del tramo, pg_terminate_backend de todas las
                           conexiones de la app, o reinicio real de PostgreSQL con PG_RESTART_CMD
  ESCANEO_REAL=0           1 = datos de mercado reales (red) en vez de sintéticos
  ESCANEO_FRIO=0           1 = cada escaneo sintético regenera sus series (≈25 s de CPU en Python): peor caso
  CRYPTO_RADAR_SCANNER=    se pasa tal cual al servidor (p. ej. «proceso» para el escáner en proceso aparte)
  MALLOC_ARENA_MAX         se hereda del entorno
  LIMITE_CPU=0.1           emula la CPU de un plan de Render (fracción de un núcleo, cgroup v1 cpu.cfs_quota_us);
  LIMITE_MEM_MB=512        y su memoria (memory.limit_in_bytes). Necesita root. El servidor entra en el cgroup
                           después de la preparación (los escaneos iniciales corren sin límite)

Qué hace:
- Crea una base PostgreSQL temporal y arranca el servidor real (`server.serve`) en otro proceso, con el sondeo de
  Telegram real (`telegram_bot.poll_forever`) pero con la API de Telegram sustituida por un simulador local: ningún
  mensaje sale a internet. Cada usuario tiene un chat vinculado.
- Dentro del servidor, un hilo «sonda» duerme 5 ms en bucle y mide cuánto se retrasa al despertar: es el tiempo que
  un hilo cualquiera (por ejemplo un trabajador HTTP) espera para volver a ejecutar Python (GIL).
- Mide latencia HTTP separando las peticiones hechas DURANTE un escaneo de las hechas FUERA, CPU, memoria (VmRSS y
  VmHWM), duración de cada escaneo, errores, conexiones y bloqueos de PostgreSQL y la latencia de respuesta del bot.
- Al terminar borra la base temporal.
"""
import http.client
import json
import os
import random
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
PG_LOG = os.environ.get("PG_LOG", "/var/tmp/crypto-radar-pg/log")
DB = f"cr_estres_{secrets.token_hex(3)}"
PW = "clave de estres segura 1"
ADMIN, ADMIN_PW = "jefe.estres", "clave del jefe de estres 1"
LEVELS = [int(x) for x in os.environ.get("NIVELES", "10,50,100").split(",")]
DURATION = float(os.environ.get("DURACION_S", "90"))
THINK = float(os.environ.get("PAUSA_S", "1.0"))
SCAN_AT = float(os.environ.get("ESCANEO_EN_S", "5"))
REPEAT = os.environ.get("REPETIR_ESCANEO") == "1"
SCAN_GAP = float(os.environ.get("PAUSA_ESCANEO_S", "15"))
TG_RATE = float(os.environ.get("TELEGRAM_POR_S", "2"))
FANOUT_EVERY = float(os.environ.get("DIFUSION_CADA_S", "30"))
CHAOS = [(a, float(b)) for a, b in (x.split("@") for x in os.environ.get("CAOS", "").split(",") if x)]
REAL = os.environ.get("ESCANEO_REAL") == "1"

SERVER = r"""
import os, sys, json, time, threading, queue, random, signal
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/tests")
REAL = os.environ.get("ESCANEO_REAL") == "1"
if not REAL:
    import fake_market; fake_market.install()
from radar import auth, db, scanner, server, alerts, telegram_bot
if not REAL and os.environ.get("ESCANEO_FRIO") == "1":
    # cada escaneo vuelve a generar las series sintéticas (≈25 s de CPU en Python puro): peor caso de competencia por el GIL
    _orig_scan = scanner.run_scan
    def _cold_scan(*a, **k):
        fake_market._cache.clear(); return _orig_scan(*a, **k)
    scanner.run_scan = _cold_scan
alerts._desktop = lambda *a: None
if os.environ.get("CRYPTO_RADAR_SCANNER") == "proceso":
    # PROTOTIPO de aislamiento (solo en esta prueba, no en la app): el escaneo corre en un proceso Python aparte que
    # escribe en la misma base (tabla kv) igual que el escaneo en hilo; el servidor solo refleja su estado.
    import subprocess
    CHILD = (
        "import os, sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/tests')\n"
        "real = os.environ.get('ESCANEO_REAL') == '1'\n"
        "if not real:\n    import fake_market; fake_market.install()\n"
        "from radar import scanner, alerts, telegram_bot\n"
        "alerts._desktop = lambda *a: None\n"
        "telegram_bot.api = lambda *a, **k: {'ok': True, 'result': {}}\n"
        "r = scanner.run_scan()\n"
        "print('ERROR' if not r else 'OK', scanner.status.get('last_error') or '', flush=True)\n")
    def _proc_scan(settings=None):
        if scanner.status["scanning"]:
            return None
        scanner.status.update(scanning=True, last_error=None, progress="Escaneo en proceso aparte…")
        try:
            p = subprocess.run([sys.executable, "-c", CHILD, sys.argv[1]], capture_output=True, text=True)
            if p.returncode or not p.stdout.startswith("OK"):
                scanner.status["last_error"] = (p.stdout + p.stderr)[-300:]
        finally:
            scanner.status.update(scanning=False, progress="")
        return True
    _first_scan = scanner.run_scan
    scanner.run_scan = _proc_scan
STATS = sys.argv[5]
S = {"probe": [], "tg_lat": [], "tg_cmds": 0, "tg_replies": 0, "tg_fanout_msgs": 0, "tg_fanouts": [], "scans": [],
     "tg_poll_errors": 0}
lock = threading.Lock()

# ---------- sonda de planificación: un hilo que duerme 5 ms y mide el retraso al despertar (GIL / CPU)
def probe():
    while True:
        t = time.perf_counter(); time.sleep(0.005); lag = (time.perf_counter() - t - 0.005) * 1000
        S["probe"].append((round(time.time(), 3), round(lag, 2), bool(scanner.status.get("scanning"))))
threading.Thread(target=probe, daemon=True, name="sonda").start()

# ---------- ventanas de escaneo vistas desde dentro del proceso
def scan_watch():
    on, t0 = False, 0
    while True:
        s = bool(scanner.status.get("scanning"))
        if s and not on: on, t0 = True, time.time()
        elif on and not s:
            on = False; S["scans"].append({"inicio": t0, "fin": time.time(), "s": round(time.time() - t0, 2),
                                            "error": scanner.status.get("last_error")})
        time.sleep(0.02)
threading.Thread(target=scan_watch, daemon=True).start()

# ---------- simulador de la API de Telegram (nada sale a internet)
updates, pending, uid_seq = queue.Queue(), {}, [0]
def fake_api(method, params, timeout=35):
    if method == "getUpdates":
        try:
            up = updates.get(timeout=1.0)
        except queue.Empty:
            return {"ok": True, "result": []}
        return {"ok": True, "result": [up]}
    if method == "sendMessage":
        time.sleep(0.03)                                    # ida y vuelta de red simulada
        chat = str(params["chat_id"]); now = time.time()
        with lock:
            if threading.current_thread().name == "tg-poll" and chat in pending:
                t0, scanning = pending.pop(chat)
                S["tg_lat"].append((round(t0, 3), round((now - t0) * 1000, 1), scanning)); S["tg_replies"] += 1
            else:
                S["tg_fanout_msgs"] += 1
        return {"ok": True, "result": {}}
    return {"ok": True, "result": True}
telegram_bot.api = fake_api

def tg_users(rate, chats):
    cmds = ["/estado", "/top", "/regimen", "/cartera", "/alertas on", "/ayuda"]
    rnd = random.Random(7)
    while rate > 0:
        time.sleep(rnd.expovariate(rate))
        chat = rnd.choice(chats)
        with lock:
            if chat in pending:
                continue
            uid_seq[0] += 1; pending[chat] = (time.time(), bool(scanner.status.get("scanning"))); S["tg_cmds"] += 1
        updates.put({"update_id": uid_seq[0], "message": {"chat": {"id": int(chat)}, "text": rnd.choice(cmds),
                                                          "from": {"id": int(chat)}}})

def fanouts(every):
    while every > 0:
        time.sleep(every)
        t = time.time(); n = telegram_bot.fanout("MARKET REGIME CHANGE", "Prueba de estrés: alerta simulada")
        S["tg_fanouts"].append({"t": round(t, 3), "s": round(time.time() - t, 2), "enviados": n,
                                "durante_escaneo": bool(scanner.status.get("scanning"))})

def dump(*_):
    tmp = STATS + ".tmp"
    with open(tmp, "w") as f:
        json.dump(S, f)
    os.replace(tmp, STATS)
signal.signal(signal.SIGUSR1, dump)

db.init(); auth.ensure_admin()
admin = db.one("SELECT * FROM users WHERE email = ?", (os.environ["CRYPTO_RADAR_ADMIN_USER"],))
_scan0 = globals().get("_first_scan", scanner.run_scan)
t = time.time(); rep = _scan0(); first = time.time() - t
if REAL:
    second = 0.0                                            # con datos reales no se repite (≈3 min y límites de la API)
else:
    t = time.time(); rep = scanner.run_scan(); second = time.time() - t
rep = rep if isinstance(rep, dict) else (__import__("radar.storage").storage.read("latest.json", {}) or {})
plans = ["free", "pro", "elite"]
chats = []
for i in range(int(sys.argv[3])):
    auth.reset_rate_limits()
    uid = auth.request_access(f"estres{i:03d}", sys.argv[4], ip=f"10.5.{i // 250}.{i % 250}", consent=auth.POLICY_VERSION)
    auth.admin_set_status(admin, uid, "approve", plans[i % 3], 30)
    db.execute("UPDATE users SET telegram_chat_id = ? WHERE id = ?", (str(900000 + i), uid)); chats.append(str(900000 + i))
auth.reset_rate_limits()
S["scans"].clear()
print("LISTO", len((rep or {}).get("assets", [])), round(first, 2), round(second, 2), flush=True)
_poll = telegram_bot.poll_forever
threading.Thread(target=_poll, daemon=True, name="tg-poll").start()
threading.Thread(target=tg_users, args=(float(os.environ.get("TELEGRAM_POR_S", "2")), chats), daemon=True).start()
threading.Thread(target=fanouts, args=(float(os.environ.get("DIFUSION_CADA_S", "30")),), daemon=True).start()
server.serve(int(sys.argv[2]), schedule=False)
"""


def pg(sql, dbname=None, fetch=True, timeout=5):
    import psycopg
    u = ADMIN_URL if not dbname else ADMIN_URL.rsplit("/", 1)[0] + "/" + dbname
    with psycopg.connect(u, autocommit=True, connect_timeout=timeout) as c:
        cur = c.execute(sql)
        rows = cur.fetchall() if fetch and cur.description else None
    if rows:
        rows = [tuple(v.decode() if isinstance(v, bytes) else v for v in r) for r in rows]
    return rows


def free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def proc_stats(pid):
    st = {}
    with open(f"/proc/{pid}/status") as f:
        for x in f:
            if x.startswith(("VmRSS", "VmHWM")):
                st[x.split(":")[0]] = int(x.split()[1]) / 1024
    with open(f"/proc/{pid}/stat") as f:
        parts = f.read().rsplit(")", 1)[1].split()
    return st["VmRSS"], (int(parts[11]) + int(parts[12])) / os.sysconf("SC_CLK_TCK"), int(parts[17]), st["VmHWM"]


def children_rss(pid):
    """RSS de los procesos hijos del servidor (escáner en proceso aparte, si existe)."""
    tot = 0.0
    try:
        for c in Path(f"/proc/{pid}/task/{pid}/children").read_text().split():
            try:
                tot += proc_stats(int(c))[0]
            except Exception:
                pass
    except Exception:
        pass
    return tot


class Client:
    def __init__(self, port, name, ip=None):
        self.port, self.name, self.cookie, self.csrf, self.ip = port, name, None, None, ip

    def req(self, method, path, body=None, timeout=30):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        h = {"Content-Type": "application/json"}
        if self.ip:
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

    def login(self, pw):
        st, ms, data = self.req("POST", "/api/auth/login", {"username": self.name, "password": pw})
        if st == 200:
            self.csrf = json.loads(data)["csrf"]
        return st, ms


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs); k = (len(xs) - 1) * p / 100
    f = int(k); return round(xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f), 1)


def summarize(lat_codes):
    lat = [x[1] for x in lat_codes]
    by = {}
    for s in lat_codes:
        by[str(s[0])] = by.get(str(s[0]), 0) + 1
    return {"n": len(lat), "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99),
            "max_ms": round(max(lat), 1) if lat else None, "codigos": by}


def in_windows(t, wins):
    return any(a <= t <= b for a, b in wins)


def read_stats(srv, path):
    before = os.path.getmtime(path) if os.path.exists(path) else 0
    srv.send_signal(signal.SIGUSR1)
    for _ in range(100):
        time.sleep(0.1)
        if os.path.exists(path) and os.path.getmtime(path) != before:
            try:
                return json.loads(Path(path).read_text())
            except Exception:
                continue
    raise RuntimeError("el servidor no volcó sus estadísticas")


def chaos(action):
    if action == "cortar":
        r = pg(f"SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity WHERE datname = '{DB}' AND pid <> pg_backend_pid()")
        return {"accion": "pg_terminate_backend", "conexiones_cortadas": r[0][0]}
    if action == "reiniciar":
        cmd = os.environ.get("PG_RESTART_CMD")
        if not cmd:
            return {"accion": "reinicio", "error": "falta PG_RESTART_CMD"}
        t = time.time(); p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return {"accion": "reinicio de PostgreSQL", "s": round(time.time() - t, 2), "rc": p.returncode,
                "salida": (p.stdout + p.stderr)[-300:]}
    return {"accion": action, "error": "desconocida"}


CG = f"cr_estres_{secrets.token_hex(3)}"
CPU_LIMIT = float(os.environ.get("LIMITE_CPU") or 0)
MEM_LIMIT = int(os.environ.get("LIMITE_MEM_MB") or 0)


def cgroup_setup(pid):
    if not (CPU_LIMIT or MEM_LIMIT):
        return None
    info = {}
    if CPU_LIMIT:
        d = Path("/sys/fs/cgroup/cpu") / CG; d.mkdir()
        (d / "cpu.cfs_period_us").write_text("100000"); (d / "cpu.cfs_quota_us").write_text(str(int(CPU_LIMIT * 100000)))
        (d / "cgroup.procs").write_text(str(pid)); info["cpu_nucleos"] = CPU_LIMIT
    if MEM_LIMIT:
        d = Path("/sys/fs/cgroup/memory") / CG; d.mkdir()
        (d / "memory.limit_in_bytes").write_text(str(MEM_LIMIT * 1024 * 1024))
        (d / "cgroup.procs").write_text(str(pid)); info["memoria_mb"] = MEM_LIMIT
    return info


def cgroup_mem():
    d = Path("/sys/fs/cgroup/memory") / CG
    if not MEM_LIMIT or not d.exists():
        return None
    oom = dict(x.split() for x in (d / "memory.oom_control").read_text().splitlines())
    st = dict(x.split() for x in (d / "memory.stat").read_text().splitlines())
    return {"uso_max_mb": round(int((d / "memory.max_usage_in_bytes").read_text()) / 2**20, 1),
            "veces_en_el_limite": int((d / "memory.failcnt").read_text()),
            "procesos_matados_oom": int(oom.get("oom_kill", 0)),
            "rss_mb": round(int(st.get("rss", 0)) / 2**20, 1), "cache_mb": round(int(st.get("cache", 0)) / 2**20, 1)}


def cgroup_cleanup():
    for c in ("cpu", "memory"):
        d = Path("/sys/fs/cgroup") / c / CG
        if d.exists():
            for _ in range(20):
                try:
                    d.rmdir(); break
                except OSError:
                    time.sleep(0.5)


def run_level(port, srv, n, offset, stats_path, admin):
    pid = srv.pid
    clients = [Client(port, f"estres{(offset + i):03d}", f"10.77.{(offset + i) // 250}.{(offset + i) % 250}") for i in range(n)]
    logins, samples, stop = [], [], threading.Event()
    mon = {"rss": [], "cpu": [], "threads": [], "pg_conns": [], "pg_idle_tx": [], "lock_waits": 0, "lock_samples": 0,
           "pg_errors": 0, "hijos_rss": []}
    events, scan_reqs = [], []

    def monitor():
        while not stop.is_set():
            t = time.time()
            try:
                rss, cpu, th, _ = proc_stats(pid)
                mon["rss"].append((t, rss)); mon["cpu"].append((t, cpu)); mon["threads"].append(th)
                mon["hijos_rss"].append((t, children_rss(pid)))
            except Exception:
                pass
            try:
                r = pg(f"SELECT count(*), count(*) FILTER (WHERE state = 'idle in transaction'), "
                       f"(SELECT count(*) FROM pg_locks WHERE NOT granted) FROM pg_stat_activity WHERE datname = '{DB}'", timeout=2)
                mon["pg_conns"].append((t, r[0][0])); mon["pg_idle_tx"].append(r[0][1])
                mon["lock_samples"] += 1; mon["lock_waits"] += int(r[0][2] > 0)
            except Exception:
                mon["pg_errors"] += 1
            time.sleep(0.25)

    def user_loop(c, deadline):
        rnd = random.Random(c.name)
        while time.time() < deadline:
            x = rnd.random(); t = time.time()
            if x < .40: s = c.req("GET", "/api/state")
            elif x < .60: s = c.req("GET", "/api/me")
            elif x < .75: s = c.req("GET", "/api/alerts")
            elif x < .90: s = c.req("GET", "/api/positions")
            else: s = c.req("POST", "/api/me/settings", {"risk_per_trade_pct": round(rnd.uniform(0.5, 2), 2)})
            samples.append((t, s[0], s[1])); time.sleep(THINK)

    def scan_driver(start, deadline):
        if SCAN_AT < 0:
            return
        time.sleep(max(0, start + SCAN_AT - time.time()))
        while time.time() < deadline - 5:
            st, ms, data = admin.req("POST", "/api/scan", {})
            scan_reqs.append({"t": round(time.time() - start, 1), "codigo": st, "ms": round(ms, 1)})
            if not REPEAT:
                return
            time.sleep(1)
            while time.time() < deadline and json.loads(admin.req("GET", "/healthz")[2] or b"{}").get("scanning"):
                time.sleep(0.5)
            time.sleep(SCAN_GAP)

    def chaos_driver(start):
        for action, at in CHAOS:
            time.sleep(max(0, start + at - time.time()))
            e = chaos(action); e["t"] = round(time.time() - start, 1); e["t_abs"] = time.time(); events.append(e)

    sess0 = pg(f"SELECT sessions FROM pg_stat_database WHERE datname = '{DB}'")[0][0]
    _, cpu0, _, _ = proc_stats(pid); t0 = time.time()
    m = threading.Thread(target=monitor, daemon=True); m.start()
    out = []
    ts = [threading.Thread(target=lambda c=c: out.append(c.login(PW))) for c in clients]
    tl = time.time(); [t.start() for t in ts]; [t.join() for t in ts]; login_wall = time.time() - tl
    start = time.time(); deadline = start + DURATION
    ts = [threading.Thread(target=user_loop, args=(c, deadline)) for c in clients if c.csrf]
    ts.append(threading.Thread(target=scan_driver, args=(start, deadline)))
    if CHAOS:
        ts.append(threading.Thread(target=chaos_driver, args=(start,)))
    [t.start() for t in ts]; [t.join() for t in ts]
    # deja terminar un escaneo en curso para medir su duración completa (sin carga del panel)
    tail_deadline = time.time() + 240
    while time.time() < tail_deadline and json.loads(Client(port, "").req("GET", "/healthz")[2] or b"{}").get("scanning"):
        time.sleep(0.5)
    stop.set(); m.join()
    _, cpu1, _, hwm = proc_stats(pid); wall = time.time() - t0
    try:
        sess1 = pg(f"SELECT sessions FROM pg_stat_database WHERE datname = '{DB}'")[0][0]
    except Exception:
        sess1 = None
    time.sleep(2)
    idle = pg(f"SELECT state, count(*) FROM pg_stat_activity WHERE datname = '{DB}' GROUP BY state")
    S = read_stats(srv, stats_path)
    scans = [s for s in S["scans"] if s["inicio"] >= t0]
    wins = [(s["inicio"], s["fin"]) for s in scans]
    during = [(c, ms) for t, c, ms in samples if in_windows(t, wins)]
    outside = [(c, ms) for t, c, ms in samples if not in_windows(t, wins)]
    probe = [(t, lag, sc) for t, lag, sc in S["probe"] if t0 <= t <= time.time()]
    lag_scan = [lag for t, lag, sc in probe if sc]
    lag_idle = [lag for t, lag, sc in probe if not sc]
    tg = [(t, ms, sc) for t, ms, sc in S["tg_lat"] if t >= start]
    cpu_scan, cpu_idle = [], []
    for (ta, ca), (tb, cb) in zip(mon["cpu"], mon["cpu"][1:]):
        if tb > ta:
            (cpu_scan if in_windows((ta + tb) / 2, wins) else cpu_idle).append((cb - ca) / (tb - ta) * 100)
    rss_scan = [r for t, r in mon["rss"] if in_windows(t, wins)]
    allc = [(c, ms) for _, c, ms in samples]
    errors = {}
    for c, _ in allc:
        if str(c) not in ("200", "402"):
            errors[str(c)] = errors.get(str(c), 0) + 1
    err_t = sorted(round(t - start, 1) for t, c, _ in samples if str(c) not in ("200", "402"))
    res = {
        "usuarios": n,
        "login": summarize(out) | {"segundos_rafaga": round(login_wall, 2)},
        "panel_total": summarize(allc) | {"rps": round(len(allc) / DURATION, 1)},
        "panel_durante_escaneo": summarize(during),
        "panel_fuera_de_escaneo": summarize(outside),
        "errores": errors,
        "errores_segundos_desde_inicio": err_t[:50],
        "escaneos": [{"s": s["s"], "error": s["error"], "inicio_s": round(s["inicio"] - start, 1)} for s in scans],
        "peticiones_escaneo": scan_reqs,
        "sonda_retraso_ms": {"durante_escaneo": {"n": len(lag_scan), "p50": pct(lag_scan, 50), "p99": pct(lag_scan, 99),
                                                 "max": max(lag_scan) if lag_scan else None},
                             "fuera_de_escaneo": {"n": len(lag_idle), "p50": pct(lag_idle, 50), "p99": pct(lag_idle, 99),
                                                  "max": max(lag_idle) if lag_idle else None}},
        "telegram": {"comandos": len(tg),
                     "respuesta_durante_escaneo": summarize([(200, ms) for _, ms, sc in tg if sc]),
                     "respuesta_fuera_de_escaneo": summarize([(200, ms) for _, ms, sc in tg if not sc]),
                     "difusiones": [f for f in S["tg_fanouts"] if f["t"] >= start],
                     "mensajes_de_difusion_total_proceso": S["tg_fanout_msgs"]},
        "rss_mb_max": round(max(r for _, r in mon["rss"]), 1),
        "rss_mb_max_durante_escaneo": round(max(rss_scan), 1) if rss_scan else None,
        "rss_mb_final": round(mon["rss"][-1][1], 1),
        "vmhwm_mb_proceso": round(hwm, 1),
        "rss_mb_max_hijos": round(max((r for _, r in mon["hijos_rss"]), default=0), 1),
        "cpu_pct_medio": round((cpu1 - cpu0) / wall * 100, 1),
        "cpu_pct_medio_durante_escaneo": round(sum(cpu_scan) / len(cpu_scan), 1) if cpu_scan else None,
        "cpu_pct_medio_fuera_de_escaneo": round(sum(cpu_idle) / len(cpu_idle), 1) if cpu_idle else None,
        "hilos_max": max(mon["threads"]),
        "pg_conexiones_max": max((c for _, c in mon["pg_conns"]), default=0),
        "pg_conexiones_final": mon["pg_conns"][-1][1] if mon["pg_conns"] else None,
        "pg_conexiones_abiertas_en_el_tramo": (sess1 - sess0) if sess1 is not None else None,
        "pg_estado_conexiones_al_final": {str(k): v for k, v in (idle or [])},
        "pg_idle_in_transaction_max": max(mon["pg_idle_tx"] or [0]),
        "pg_muestras_con_esperas_por_bloqueo": f"{mon['lock_waits']}/{mon['lock_samples']}",
        "pg_muestras_sin_respuesta_del_monitor": mon["pg_errors"],
        "caos": [{k: v for k, v in e.items() if k != "t_abs"} for e in events],
        "cgroup_memoria": cgroup_mem(),
        "peticiones_http": len(samples) + len(out),
    }
    if events:
        # recuperación: primer segundo tras cada evento a partir del cual no vuelve a haber errores
        rec = []
        for e in events:
            ta = e["t_abs"]
            errs = [t for t, c, _ in samples if t >= ta and str(c) not in ("200", "402")]
            rec.append({"accion": e["accion"], "errores_tras_el_evento": len(errs),
                        "ultimo_error_s_tras_el_evento": round(max(errs) - ta, 2) if errs else 0})
        res["recuperacion"] = rec
    return res


def main(out=None):
    if not ADMIN_URL:
        sys.exit("Define PG_ADMIN_URL (base de pruebas local)")
    total = sum(LEVELS)
    pg(f"CREATE DATABASE {DB}", fetch=False)
    pg(f"ALTER DATABASE {DB} SET log_min_duration_statement = 50", fetch=False)
    log_start = os.path.getsize(PG_LOG) if os.path.exists(PG_LOG) else 0
    port = free_port()
    home = tempfile.mkdtemp(prefix="cr-estres-")
    stats_path = os.path.join(home, "estres_stats.json")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_", "TELEGRAM_"))}
    env.update({"DATABASE_URL": ADMIN_URL.rsplit("/", 1)[0] + "/" + DB, "CRYPTO_RADAR_ACCOUNTS": "1",
                "CRYPTO_RADAR_HOME": home, "CRYPTO_RADAR_ADMIN_USER": ADMIN,
                "CRYPTO_RADAR_ADMIN_PASSWORD": ADMIN_PW, "CRYPTO_RADAR_ADMIN_TOTP": "optional",
                "CRYPTO_RADAR_HOST": "127.0.0.1", "TELEGRAM_BOT_TOKEN": "simulado:no-sale-a-internet",
                "CRYPTO_RADAR_TRUSTED_PROXIES": "127.0.0.1/32", "TELEGRAM_POR_S": str(TG_RATE)})
    for k in ("CRYPTO_RADAR_SCANNER", "CRYPTO_RADAR_WORKERS"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    shutil.copytree(ROOT / "web", Path(home) / "web")
    srv = subprocess.Popen([sys.executable, "-c", SERVER, str(ROOT), str(port), str(total), PW, stats_path], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log_lines = []
    R = {"entorno": {"cpu": os.cpu_count(), "python": sys.version.split()[0],
                     "postgres": pg("SHOW server_version")[0][0], "duracion_s": DURATION, "pausa_s": THINK,
                     "escaneo_en_s": SCAN_AT, "repetir_escaneo": REPEAT, "telegram_por_s": TG_RATE,
                     "difusion_cada_s": FANOUT_EVERY, "caos": os.environ.get("CAOS", ""),
                     "datos": "reales" if REAL else "sinteticos",
                     "escaneo_frio": os.environ.get("ESCANEO_FRIO") == "1",
                     "malloc_arena_max": os.environ.get("MALLOC_ARENA_MAX"),
                     "escaner": os.environ.get("CRYPTO_RADAR_SCANNER") or "hilo (actual)"}, "niveles": []}
    try:
        t = time.time()
        while True:
            line = srv.stdout.readline()
            if not line:
                raise RuntimeError("el servidor terminó:\n" + "".join(log_lines[-40:]))
            if line.startswith("LISTO"):
                break
            log_lines.append(line)
        _, assets, first, second = line.split()
        R["entorno"].update({"activos_en_informe": int(assets), "escaneo_inicial_s": float(first),
                             "escaneo_en_reposo_s": float(second), "preparacion_s": round(time.time() - t, 1)})
        threading.Thread(target=lambda: [log_lines.append(x) for x in srv.stdout], daemon=True).start()
        for _ in range(100):
            if Client(port, "").req("GET", "/healthz")[0] == 200:
                break
            time.sleep(0.2)
        admin = Client(port, ADMIN, "10.99.0.1")
        st, _ = admin.login(ADMIN_PW)
        if st != 200:
            raise RuntimeError(f"no entra el administrador: {st}")
        rss0, _, _, _ = proc_stats(srv.pid); R["entorno"]["rss_mb_reposo"] = round(rss0, 1)
        R["entorno"]["limites_render_emulados"] = cgroup_setup(srv.pid)
        off = 0
        for n in LEVELS:
            r = run_level(port, srv, n, off, stats_path, admin); off += n
            R["niveles"].append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
        rss1, _, _, hwm = proc_stats(srv.pid)
        R["entorno"]["rss_mb_final"] = round(rss1, 1); R["entorno"]["vmhwm_mb"] = round(hwm, 1)
        R["consultas_lentas_por_sentencia"] = {}
        if os.path.exists(PG_LOG):
            with open(PG_LOG, errors="replace") as f:
                f.seek(log_start)
                for ln in f:
                    m = re.search(r"duration: ([\d.]+) ms\s+statement: (.*)", ln)
                    if m:
                        key = re.sub(r"\s+", " ", m.group(2))[:90]
                        d = R["consultas_lentas_por_sentencia"].setdefault(key, {"n": 0, "max_ms": 0})
                        d["n"] += 1; d["max_ms"] = max(d["max_ms"], float(m.group(1)))
        R["consultas_lentas_total"] = sum(v["n"] for v in R["consultas_lentas_por_sentencia"].values())
        R["trazas_en_registro_del_servidor"] = sum(1 for x in log_lines if x.startswith("Traceback"))
        R["registro_servidor_ultimas_lineas"] = [x.rstrip()[:200] for x in log_lines[-15:]]
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()
        for _ in range(30):
            try:
                pg(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)", fetch=False)
                break
            except Exception:
                time.sleep(1)
        shutil.rmtree(home, ignore_errors=True)
        cgroup_cleanup()
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    print(json.dumps(R["entorno"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
