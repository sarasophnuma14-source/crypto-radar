"""Ensayo del PROCEDIMIENTO de copia inicial (R-10) con las mismas órdenes que se usarán en producción, sobre bases
PostgreSQL TEMPORALES. Nunca toca una base real.

Uso:  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/backup_inicial.py [salida.json]
      USUARIOS=200 ACTIVIDAD=20000   tamaño de la base de ensayo (por defecto, un piloto con margen)
      LATENCIA_MS=10                 además, restaura a través de un proxy TCP local que retrasa cada envío 10 ms
                                     en cada sentido (≈20 ms de ida y vuelta, como hasta una base remota)

Pasos (docs/PLAN_BACKUP_RECUPERACION.md):
 1. base de origen poblada con la app: administrador con TOTP cifrado, usuarios, sesiones, posiciones, actividad e
    informe de mercado real en tamaño (escaneo sintético de 40 activos);
 2. `main.py backup create` sin clave → debe negarse;
 3. `main.py backup create` con CRYPTO_RADAR_BACKUP_KEY → copia firmada; `verify` (hashes + HMAC + restauración de
    prueba en SQLite);
 4. `main.py backup restore --target <base vacía>`; `compare` contra la restaurada; `preflight --db` sobre ella;
 5. el servidor arranca sobre la restaurada y el administrador entra con contraseña + TOTP;
 6. con otra CRYPTO_RADAR_TOTP_KEY el TOTP no se puede leer (la clave hay que guardarla aparte);
 7. lo escrito después de la copia se pierde (RPO).
Mide el tiempo de cada orden y el tamaño de la copia.
"""
import http.client
import json
import os
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
TAG = secrets.token_hex(3)
SRC, DST = f"cr_bk0_src_{TAG}", f"cr_bk0_dst_{TAG}"
USER, PW = "jefe.copia", "clave del jefe de la copia 1"
TOTP_KEY, BACKUP_KEY = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
N_USERS = int(os.environ.get("USUARIOS", "200"))
N_ACT = int(os.environ.get("ACTIVIDAD", "20000"))
R = {"tamano": {"usuarios": N_USERS, "actividad_extra": N_ACT}, "pasos": [], "tiempos_s": {}}


def url(db):
    return ADMIN_URL.rsplit("/", 1)[0] + "/" + db


def pg(sql, db=None):
    import psycopg
    with psycopg.connect(url(db) if db else ADMIN_URL, autocommit=True) as c:
        cur = c.execute(sql)
        rows = cur.fetchall() if cur.description else None
    return [tuple(v.decode() if isinstance(v, bytes) else v for v in r) for r in rows or []]


def step(name, ok, detail=""):
    R["pasos"].append({"paso": name, "ok": bool(ok), "detalle": detail})
    print(f"[{'OK' if ok else 'FALLO'}] {name} · {detail}", flush=True)


def env(db, extra=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_", "TELEGRAM_"))}
    e.pop("RENDER", None)
    e.update({"DATABASE_URL": url(db), "CRYPTO_RADAR_ACCOUNTS": "1", "CRYPTO_RADAR_ADMIN_USER": USER,
              "CRYPTO_RADAR_ADMIN_PASSWORD": PW, "CRYPTO_RADAR_ADMIN_TOTP": "required", "CRYPTO_RADAR_HOME": HOME,
              "CRYPTO_RADAR_TOTP_KEY": TOTP_KEY, "CRYPTO_RADAR_BACKUP_KEY": BACKUP_KEY, "CRYPTO_RADAR_HOST": "127.0.0.1"})
    e.update(extra or {})
    return {k: v for k, v in e.items() if v is not None}


def cli(db, *args, extra=None, key=None):
    t = time.time()
    p = subprocess.run([sys.executable, str(ROOT / "main.py"), *args], env=env(db, extra), capture_output=True, text=True,
                       cwd=HOME, timeout=1800)
    if key:
        R["tiempos_s"][key] = round(time.time() - t, 2)
    return p


POPULATE = r"""
import json, random, sys, time
sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + "/tests")
import fake_market; fake_market.install()
from radar import auth, db, multiuser, scanner, totp, alerts
alerts._desktop = lambda *a: None
n_users, n_act = int(sys.argv[2]), int(sys.argv[3])
db.init(); auth.ensure_admin()
admin = db.one("SELECT * FROM users WHERE email = ?", (sys.argv[4],))
tok, _ = auth.new_enroll_token()
sec = auth.totp_setup(admin["id"], sys.argv[5], enroll_token=tok)["secret"]
auth.totp_enable(admin["id"], totp.code(sec), enroll_token=tok)
admin = auth.get_user(admin["id"])
plans = ["free", "pro", "elite"]
for i in range(n_users):
    auth.reset_rate_limits()
    uid = auth.request_access(f"piloto{i:04d}", "clave de piloto 2026 x", ip=f"10.3.{i // 250}.{i % 250}", consent=auth.POLICY_VERSION)
    auth.admin_set_status(admin, uid, "approve", plans[i % 3], 30)
    if i % 3:
        multiuser.add_position(uid, {"symbol": "BTC", "entry": 60000.0 + i, "qty": 0.01, "notes": "ensayo"})
    if i < 30:
        auth.reset_rate_limits(); auth.login(f"piloto{i:04d}", "clave de piloto 2026 x", ip="10.4.0.1")
rows = [(f"act{i:07d}", None, time.time() - i, "ensayo_carga", json.dumps({"i": i}), "10.0.0.1") for i in range(n_act)]
c = db.conn()
with c.cursor() as cur:
    cur.executemany("INSERT INTO activity(id, user_id, at, action, detail, ip) VALUES (%s, %s, %s, %s, %s, %s)", rows)
scanner.run_scan()
n = {t: db.one(f"SELECT COUNT(*) AS n FROM {t}", ())["n"] for t in ("users", "sessions", "positions", "activity", "kv")}
print(json.dumps({"filas": n, "secret": sec}))
"""


def login_admin(db, code, extra=None):
    port = __import__("random").randint(20000, 40000)
    p = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "serve", str(port)], env=env(db, extra),
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=HOME)
    log = []
    try:
        t = time.time()
        while time.time() - t < 120:
            ln = p.stdout.readline()
            if not ln:
                break
            log.append(ln.rstrip())
            if "hilos; Ctrl+C" in ln:
                break
        boot = round(time.time() - t, 2)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
        c.request("POST", "/api/auth/login", json.dumps({"username": USER, "password": PW, "code": code}).encode(),
                  {"Content-Type": "application/json"})
        st = c.getresponse().status
        return st, boot, log
    finally:
        p.terminate(); p.wait(10)


def latency_proxy(delay_ms):
    """Proxy TCP local 127.0.0.1:<puerto> → PostgreSQL que retrasa cada bloque de datos `delay_ms` en cada sentido."""
    import asyncio, threading, urllib.parse
    target = urllib.parse.urlsplit(ADMIN_URL)
    ready, box = threading.Event(), {}

    async def pipe(r, w):
        try:
            while data := await r.read(65536):
                await asyncio.sleep(delay_ms / 1000)
                w.write(data); await w.drain()
        except Exception:
            pass
        finally:
            w.close()

    async def handle(r1, w1):
        r2, w2 = await asyncio.open_connection(target.hostname, target.port or 5432)
        await asyncio.gather(pipe(r1, w2), pipe(r2, w1))

    async def serve():
        srv = await asyncio.start_server(handle, "127.0.0.1", 0)
        box["port"] = srv.sockets[0].getsockname()[1]; ready.set()
        async with srv:
            await srv.serve_forever()

    threading.Thread(target=lambda: asyncio.run(serve()), daemon=True).start()
    ready.wait(10)
    u = urllib.parse.urlsplit(ADMIN_URL)
    return lambda db: urllib.parse.urlunsplit((u.scheme, f"{u.username}@127.0.0.1:{box['port']}", "/" + db, u.query, ""))


def main(out=None):
    global HOME
    from radar import totp
    HOME = tempfile.mkdtemp(prefix="cr-bk0-")
    shutil.copytree(ROOT / "web", Path(HOME) / "web")
    copies = Path(HOME) / "copias"
    pg(f"CREATE DATABASE {SRC}")
    try:
        t = time.time()
        p = subprocess.run([sys.executable, "-c", POPULATE, str(ROOT), str(N_USERS), str(N_ACT), USER, PW],
                           env=env(SRC), capture_output=True, text=True, timeout=3600, cwd=HOME)
        if p.returncode:
            raise RuntimeError(p.stderr[-3000:])
        pop = json.loads(p.stdout.strip().splitlines()[-1]); secret = pop.pop("secret")
        R["origen"] = pop["filas"]; R["tiempos_s"]["poblar"] = round(time.time() - t, 1)
        R["origen_mb"] = round(int(pg(f"SELECT pg_database_size('{SRC}')")[0][0]) / 2**20, 1)
        step("Base de origen poblada con la app", pop["filas"]["users"] == N_USERS + 1, json.dumps(pop["filas"]))

        p = cli(SRC, "backup", "create", "--out", str(copies), extra={"CRYPTO_RADAR_BACKUP_KEY": ""})
        step("Copia sin CRYPTO_RADAR_BACKUP_KEY → se niega", p.returncode != 0 and not copies.exists(),
             (p.stdout + p.stderr).strip().splitlines()[-1][:120])

        p = cli(SRC, "backup", "create", "--out", str(copies), key="copia")
        d = next(copies.glob("crypto-radar-backup-*"), None)
        size = sum(f.stat().st_size for f in d.iterdir()) if d else 0
        R["copia_mb"] = round(size / 2**20, 2)
        step("`backup create` con clave: copia firmada e idéntica al origen",
             p.returncode == 0 and "idéntica" in p.stdout and "HMAC" in p.stdout, f"{R['copia_mb']} MB")
        users_txt = (d / "users.jsonl").read_text()
        step("La copia no contiene el secreto TOTP en claro", secret not in users_txt and "enc1:" in users_txt, "")
        tok_txt = (d / "admin_enroll_tokens.jsonl").read_text()
        step("La copia guarda los códigos de alta usados (solo su hash)", '"used_at":' in tok_txt and '"used_at":null' not in tok_txt, "")
        p = cli(SRC, "backup", "verify", str(d), key="verificar")
        step("`backup verify`: hashes + HMAC + restauración de prueba", p.returncode == 0 and "Firma HMAC verificada" in p.stdout,
             p.stdout.strip().splitlines()[0][:300] if p.stdout else p.stderr[-200:])
        p = cli(SRC, "backup", "verify", str(d), extra={"CRYPTO_RADAR_BACKUP_KEY": secrets.token_urlsafe(32)})
        step("`verify` con otra clave → rechazada", p.returncode != 0 and "HMAC" in p.stdout, p.stdout.strip()[:100])

        p = cli(SRC, "backup", "restore", str(d), "--target", url(SRC))
        step("`restore` sobre la base de DATABASE_URL → se niega", p.returncode != 0, p.stdout.strip()[:100])
        pg(f"CREATE DATABASE {DST}")
        p = cli(SRC, "backup", "restore", str(d), "--target", url(DST), key="restaurar")
        step("`restore` en una base PostgreSQL vacía", p.returncode == 0, p.stdout.strip()[:160])
        p = cli(SRC, "backup", "restore", str(d), "--target", url(DST))
        step("Segunda restauración sobre la base ya restaurada (no vacía) → se niega", p.returncode != 0 and "no está vacío" in p.stdout,
             p.stdout.strip()[:120])
        p = cli(DST, "backup", "compare", str(d), key="comparar")
        step("`compare` copia ↔ base restaurada: idénticas", p.returncode == 0 and "Idéntica" in p.stdout, p.stdout.strip())

        code = totp.code(secret, time.time() + 30)
        t = time.time()
        st, boot, log = login_admin(DST, code)
        R["tiempos_s"]["arranque_y_login"] = round(time.time() - t, 2)
        step("El servidor arranca sobre la restaurada y el administrador entra con contraseña + TOTP", st == 200,
             f"HTTP {st}; " + next((x for x in log if "Administrador:" in x), ""))
        p = cli(DST, "preflight", "--db", key="preflight")
        dbl = [x for x in p.stdout.splitlines() if any(k in x for k in ("Esquema", "TOTP del administrador en la base",
                                                                         "Secretos TOTP en la base"))]
        step("`preflight --db` sobre la restaurada: esquema, TOTP del administrador y secretos cifrados",
             len(dbl) == 3 and all(x.startswith("[OK") for x in dbl), " | ".join(dbl))
        st, _, _ = login_admin(DST, totp.code(secret, time.time() + 60), {"CRYPTO_RADAR_TOTP_KEY": secrets.token_urlsafe(32)})
        step("Con otra CRYPTO_RADAR_TOTP_KEY el TOTP no se puede leer (503): la clave se guarda aparte", st == 503, f"HTTP {st}")

        lat = float(os.environ.get("LATENCIA_MS") or 0)
        if lat:
            via = latency_proxy(lat)
            far = f"cr_bk0_far_{TAG}"; pg(f"CREATE DATABASE {far}")
            try:
                p = cli(SRC, "backup", "restore", str(d), "--target", via(far), key=f"restaurar_con_{int(lat)}ms_por_sentido")
                step(f"`restore` a través de un proxy con {lat:g} ms por sentido", p.returncode == 0, p.stdout.strip()[:120])
            finally:
                pg(f"DROP DATABASE IF EXISTS {far} WITH (FORCE)")
        pg(f"INSERT INTO users(id, email, pw_hash, created_at) VALUES ('despues', 'escrito.despues', 'x', 1)", SRC)
        n = pg("SELECT count(*) FROM users WHERE id = 'despues'", DST)[0][0]
        step("Lo escrito después de la copia no está en la restaurada (RPO = tiempo desde la última copia)", n == 0, "")
        R["rto_medido_s"] = round(R["tiempos_s"]["restaurar"] + R["tiempos_s"]["comparar"] + R["tiempos_s"]["arranque_y_login"], 2)
    finally:
        for db in (SRC, DST):
            try:
                pg(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")
            except Exception:
                pass
        shutil.rmtree(HOME, ignore_errors=True)
    R["resumen"] = f"{sum(p['ok'] for p in R['pasos'])} de {len(R['pasos'])} pasos OK"
    print(R["resumen"], json.dumps(R["tiempos_s"]), R.get("copia_mb"), "MB")
    if out:
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    return 0 if all(p["ok"] for p in R["pasos"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
