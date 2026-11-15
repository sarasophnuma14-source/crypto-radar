"""Validación del entorno (fase 6) con PostgreSQL TEMPORAL. No toca Render, Neon ni bases reales.

Uso:  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/entorno.py [salida.json]

1. Python, dependencias fijadas e importación de todos los módulos.
2. Migraciones reales: crea el esquema con el código de `main` (2.0.0, 9176b36) y con el del PR #3 (2d72a2b),
   guarda un usuario con ese código y arranca el código actual encima: columnas nuevas añadidas, datos intactos,
   la contraseña antigua sigue valiendo.
3. Servidor real (`server.serve`) sobre PostgreSQL:
   - /healthz responde;
   - PostgreSQL corta todas las conexiones de la app (como Neon al suspenderse): ¿cuántas peticiones fallan después?
   - la base deja de aceptar conexiones: ¿qué devuelve /healthz? y al volver, ¿se recupera solo?
4. Registros del servidor: no deben aparecer la contraseña del administrador ni la de la base.
"""
import http.client
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
TAG = secrets.token_hex(3)
ADMIN_PW = "clave secreta del jefe ENTORNO-" + TAG
R = {"pasos": []}


def step(name, ok, detail=""):
    R["pasos"].append({"paso": name, "ok": bool(ok), "detalle": detail})
    print(f"[{'OK' if ok else 'FALLO'}] {name} {detail}", flush=True)


def pg(sql, dbname=None):
    import psycopg
    u = ADMIN_URL if not dbname else ADMIN_URL.rsplit("/", 1)[0] + "/" + dbname
    with psycopg.connect(u, autocommit=True) as c:
        c.execute("SET client_encoding TO 'UTF8'")
        cur = c.execute(sql)
        dec = lambda v: v.decode() if isinstance(v, bytes) else v
        return [tuple(dec(x) for x in r) for r in cur.fetchall()] if cur.description else None


def url(db):
    return ADMIN_URL.rsplit("/", 1)[0] + "/" + db


def env_for(db, home=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_", "TELEGRAM_"))}
    e.update({"DATABASE_URL": url(db), "CRYPTO_RADAR_ACCOUNTS": "1", "CRYPTO_RADAR_ADMIN_USER": "jefe.entorno",
              "CRYPTO_RADAR_ADMIN_PASSWORD": ADMIN_PW, "CRYPTO_RADAR_ADMIN_TOTP": "optional",
              "CRYPTO_RADAR_DATA": tempfile.mkdtemp(prefix="cr-env-")})
    if home:
        e["CRYPTO_RADAR_HOME"] = home
    return e


def run(code, root, db, extra=None):
    e = env_for(db); e.update(extra or {})
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]);" + code, str(root)],
                       capture_output=True, text=True, env=e, timeout=300)
    return r


def req(port, method, path, body=None, cookie=None, csrf=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    h = {"Content-Type": "application/json"}
    if cookie: h["Cookie"] = cookie
    if csrf: h["X-CSRF-Token"] = csrf
    try:
        c.request(method, path, json.dumps(body).encode() if body is not None else None, h)
        r = c.getresponse(); data = r.read()
        return r.status, data, r.getheader("Set-Cookie")
    except Exception as e:
        return f"EXC:{type(e).__name__}", b"", None
    finally:
        c.close()


def main(out=None):
    if not ADMIN_URL:
        sys.exit("Define PG_ADMIN_URL (base de pruebas local)")
    created, trees = [], []
    try:
        # 1. Python y dependencias
        v = sys.version_info
        step("Python 3.12", (v.major, v.minor) == (3, 12), sys.version.split()[0])
        reqs = (ROOT / "requirements.txt").read_text()
        pins = [l for l in reqs.splitlines() if l and not l.startswith("#")]
        step("Dependencias fijadas con versión exacta", all("==" in l for l in pins), ", ".join(pins))
        import importlib, pkgutil
        sys.path.insert(0, str(ROOT))
        bad = []
        for m in pkgutil.walk_packages([str(ROOT / "radar")], "radar."):
            try:
                importlib.import_module(m.name)
            except Exception as e:
                bad.append(f"{m.name}: {type(e).__name__}")
        step("Todos los módulos de radar se importan", not bad, "; ".join(bad))

        # 2. Migraciones desde versiones anteriores
        for label, rev in (("main 2.0.0", "9176b36"), ("PR #3", "2d72a2b")):
            db = f"cr_env_mig_{rev}_{TAG}"; pg(f"CREATE DATABASE {db}"); created.append(db)
            tree = Path(tempfile.mkdtemp(prefix=f"cr-wt-{rev}-")) / "src"
            subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(tree), rev], check=True,
                           capture_output=True); trees.append(tree)
            old = run("from radar import db, auth; db.init(); auth.ensure_admin() if hasattr(auth, 'ensure_admin') else None; "
                      "u = (auth.register('viejo@example.com', 'clave antigua muy larga 1') if not hasattr(auth, 'request_access') "
                      "else auth.get_user(auth.request_access('viejo.usuario', 'clave antigua muy larga 1', ip='10.0.0.1'))); "
                      "print(sorted(db.columns('users')) if hasattr(db, 'columns') else 'ok')", tree, db)
            if old.returncode:
                step(f"Esquema creado con el código de {label}", False, old.stderr[-400:]); continue
            before = {r[0] for r in pg("SELECT column_name FROM information_schema.columns WHERE table_name='users'", db)}
            new = run("import json; from radar import db, auth; db.init(); auth.ensure_admin(); "
                      "u = db.one(\"SELECT email, pw_hash FROM users WHERE email IN ('viejo@example.com', 'viejo.usuario')\", ()); "
                      "ok = auth.verify_password('clave antigua muy larga 1', u['pw_hash']); "
                      "print(json.dumps({'email': u['email'], 'pw_ok': ok}))", ROOT, db)
            after = {r[0] for r in pg("SELECT column_name FROM information_schema.columns WHERE table_name='users'", db)}
            if new.returncode:
                step(f"Migración {label} → actual", False, new.stderr[-600:]); continue
            res = json.loads(new.stdout.strip().splitlines()[-1])
            step(f"Migración {label} → actual", res["pw_ok"],
                 f"{len(before)} → {len(after)} columnas en users (+{', '.join(sorted(after - before))}); usuario {res['email']} conservado")

        # 3. Servidor real sobre PostgreSQL
        db = f"cr_env_srv_{TAG}"; pg(f"CREATE DATABASE {db}"); created.append(db)
        s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
        home = tempfile.mkdtemp(prefix="cr-env-home-"); shutil.copytree(ROOT / "web", Path(home) / "web")
        logf = open(Path(home) / "server.log", "w+")
        e = env_for(db, home); e["CRYPTO_RADAR_HOST"] = "127.0.0.1"
        srv = subprocess.Popen([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); from radar import server; "
                                "server.serve(int(sys.argv[2]), schedule=False)", str(ROOT), str(port)],
                               env=e, stdout=logf, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if req(port, "GET", "/healthz")[0] == 200: break
                time.sleep(0.1)
            st, body, _ = req(port, "GET", "/healthz")
            step("Health check /healthz", st == 200, body.decode()[:120])
            st, body, ck = req(port, "POST", "/api/auth/login", {"username": "jefe.entorno", "password": ADMIN_PW})
            cookie, csrf = ck.split(";")[0], json.loads(body)["csrf"]
            ok = sum(req(port, "GET", "/api/me", cookie=cookie)[0] == 200 for _ in range(40))
            step("Sesión persistente en PostgreSQL", ok == 40, f"{ok}/40")
            killed = pg(f"SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity WHERE datname = '{db}' AND pid <> pg_backend_pid()")[0][0]
            res = [req(port, "GET", "/api/me", cookie=cookie)[0] for _ in range(40)]
            fails = sum(r != 200 for r in res)
            R["corte_conexiones"] = {"conexiones_cortadas": killed, "peticiones": 40, "fallidas": fails,
                                     "codigos": {str(x): res.count(x) for x in set(res)}}
            step("Tras cortar las conexiones (como Neon al suspender) las peticiones se recuperan", res[-10:].count(200) == 10,
                 f"{killed} conexiones cortadas; {fails}/40 peticiones fallaron antes de reconectar")
            pg(f"ALTER DATABASE {db} ALLOW_CONNECTIONS false")
            pg(f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{db}' AND pid <> pg_backend_pid()")
            hs = [req(port, "GET", "/healthz")[0] for _ in range(3)]
            lg = req(port, "GET", "/api/me", cookie=cookie)[0]
            R["base_caida"] = {"healthz": hs, "api_me": lg}
            step("Con la base caída /healthz deja de responder 200 (Render lo detecta)", all(h != 200 for h in hs), f"healthz {hs}, /api/me {lg}")
            pg(f"ALTER DATABASE {db} ALLOW_CONNECTIONS true")
            time.sleep(0.5)
            res = [req(port, "GET", "/api/me", cookie=cookie)[0] for _ in range(40)]
            step("Al volver la base, el servidor se recupera sin reiniciar", res[-10:].count(200) == 10,
                 f"{sum(r != 200 for r in res)}/40 fallidas hasta reconectar")
            R["recuperacion_base"] = {str(x): res.count(x) for x in set(res)}
        finally:
            srv.terminate(); srv.wait(10)
        logf.seek(0); log = logf.read()
        leaked = [x for x in (ADMIN_PW, "TEST_DATABASE_URL") if x in log]
        step("Los registros no muestran secretos", not leaked,
             f"{len(log.splitlines())} líneas; trazas de error: {log.count('Traceback')}")
        R["log_servidor_primeras_lineas"] = log.splitlines()[:5]
        R["log_trazas"] = log.count("Traceback")
    finally:
        for t in trees:
            subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(t)], capture_output=True)
        for d in created:
            try:
                pg(f"ALTER DATABASE {d} ALLOW_CONNECTIONS true"); pg(f"DROP DATABASE IF EXISTS {d} WITH (FORCE)")
            except Exception as e:
                print("no se pudo borrar", d, e)
    R["resultado"] = "TODO OK" if all(p["ok"] for p in R["pasos"]) else "HAY FALLOS"
    print("RESULTADO:", R["resultado"])
    if out:
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    return 0 if R["resultado"] == "TODO OK" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
