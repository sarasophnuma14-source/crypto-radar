"""Verificación REAL contra Neon (rama verificacion-2-1) de la 2.1: arranque y migraciones desde cero, tablas,
índices y restricciones, persistencia tras reinicio, reconexión tras cortar conexiones, copia, verificación y
restauración, y privilegios mínimos. Variables: DATABASE_URL (radar_app), OWNER_URL, BACKUP_URL, RESTORE_URL.
No imprime secretos. Las credenciales del administrador son TEMPORALES y la rama se borra al terminar."""
import http.client, json, os, secrets, subprocess, sys, tempfile, time
ROOT = os.getcwd(); PY = sys.executable; R = []
ADMIN_PW = "verif-" + secrets.token_urlsafe(16)
data = tempfile.mkdtemp(prefix="verif21_")
env = dict(os.environ, CRYPTO_RADAR_ACCOUNTS="1", CRYPTO_RADAR_HOST="127.0.0.1", PORT="8099",
           CRYPTO_RADAR_ADMIN_USER="verificador21", CRYPTO_RADAR_ADMIN_PASSWORD=ADMIN_PW, CRYPTO_RADAR_ADMIN_TOTP="required",
           CRYPTO_RADAR_TOTP_KEY=secrets.token_urlsafe(32), CRYPTO_RADAR_PAYMENTS="off", MALLOC_ARENA_MAX="2",
           KEEPALIVE="0", CRYPTO_RADAR_DATA=data, CRYPTO_RADAR_BACKUP_KEY=secrets.token_urlsafe(32))
for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
    env.pop(k, None)

def paso(nombre, ok, detalle=""):
    R.append({"paso": nombre, "ok": bool(ok), "detalle": detalle}); print(("OK  " if ok else "FALLA ") + nombre, "·", detalle, flush=True)

def sql(url, q):
    r = subprocess.run(["psql", url, "-AtX", "-v", "ON_ERROR_STOP=1", "-c", q], capture_output=True, text=True, timeout=90)
    return r.returncode, (r.stdout.strip() or r.stderr.strip().splitlines()[-1] if (r.stdout or r.stderr) else "")

def get(path):
    try:
        c = http.client.HTTPConnection("127.0.0.1", 8099, timeout=30); c.request("GET", path); r = c.getresponse()
        return r.status, r.read().decode()[:300]
    except Exception as e:
        return 0, type(e).__name__

def arrancar(log):
    f = open(log, "w"); p = subprocess.Popen([PY, "main.py", "serve"], env=env, stdout=f, stderr=subprocess.STDOUT)
    for _ in range(120):
        if get("/healthz")[0] == 200:
            return p
        if p.poll() is not None:
            break
        time.sleep(1)
    return p

def parar(p):
    p.terminate()
    try:
        p.wait(20)
    except Exception:
        p.kill()

O, A, B, T = os.environ["OWNER_URL"], os.environ["DATABASE_URL"], os.environ["BACKUP_URL"], os.environ["RESTORE_URL"]
rc, out = sql(O, "select count(*) from pg_tables where schemaname in ('app','public')"); paso("base vacía antes de migrar", out == "0", f"tablas={out}")
t0 = time.time(); p = arrancar(f"{data}/serve1.log"); st, body = get("/healthz")
paso("primer arranque y migraciones desde cero", st == 200, f"/healthz {st} en {time.time()-t0:.1f} s")
log1 = open(f"{data}/serve1.log").read()
paso("registro de arranque", "2.1" in log1, " | ".join(l for l in log1.splitlines() if any(w in l for w in ("Plataforma", "Administrador", "esquema", "base de datos")))[:400])
rc, out = sql(O, "select schemaname, count(*) from pg_tables where schemaname in ('app','public') group by 1 order by 1"); paso("tablas en el esquema app y ninguna en public", "app|" in out and "public|" not in out, out.replace("\n", "; "))
rc, out = sql(O, "select count(*) from pg_indexes where schemaname='app'"); paso("índices", rc == 0 and int(out) > 0, f"índices={out}")
rc, out = sql(O, "select contype, count(*) from pg_constraint c join pg_namespace n on n.oid=c.connamespace where nspname='app' group by 1 order by 1"); paso("restricciones (p=PK, u=única, f=FK, c=check)", rc == 0 and "p|" in out, out.replace("\n", "; "))
rc, out = sql(O, "select k||'='||v from app.platform_meta order by k"); paso("platform_meta", "platform=2.1" in out and "initialized=nueva" in out, out.replace("\n", "; "))
rc, out = sql(O, "select (select count(*) from app.users), (select count(*) from app.users where is_admin=1), (select count(*) from app.legacy_archive)"); paso("1 usuario, 1 administrador, 0 archivados", out == "1|1|0", out)
rc, out = sql(O, "select usename, ssl from pg_stat_ssl s join pg_stat_activity a using(pid) where usename='radar_app' limit 1"); paso("sesión de la app como radar_app", "radar_app" in out, out + " (ssl=f es el tramo interno; el transporte es wss/TLS en esta prueba y sslmode=require en Render)")
r = subprocess.run([PY, "main.py", "preflight", "--db"], env=env, capture_output=True, text=True, timeout=120)
bl = [l for l in r.stdout.splitlines() if "BLOQUEANTE" in l]
esperados = [l for l in bl if "sslmode=disable" in l or "privacidad" in l]
paso("preflight --db: solo bloqueantes conocidos (TLS del puente de prueba y texto legal G-16)", len(bl) == len(esperados),
     " | ".join(x.strip() for x in bl)[:400])
# reconexión: cortar todas las conexiones de la app (como una suspensión de Neon)
rc, out = sql(O, "select count(pg_terminate_backend(pid)) from pg_stat_activity where usename='radar_app'")
fallos = sum(get("/healthz")[0] != 200 for _ in range(10)); paso("reconexión tras cortar conexiones", fallos <= 1, f"conexiones cortadas={out}; peticiones fallidas después={fallos}/10")
# persistencia: reinicio del servicio
parar(p); p = arrancar(f"{data}/serve2.log"); st, _ = get("/healthz")
rc, out = sql(O, "select (select count(*) from app.users), (select v from app.platform_meta where k='initialized')")
paso("persistencia tras reiniciar", st == 200 and out == "1|nueva", f"/healthz {st}; usuarios|inicialización = {out}")
parar(p)
# copia con el rol de solo lectura, verificación y restauración en una base aparte
benv = dict(env, DATABASE_URL=B); bdir = f"{data}/copias"
r = subprocess.run([PY, "main.py", "backup", "create", "--out", bdir], env=benv, capture_output=True, text=True, timeout=600)
paso("copia con radar_backup (solo lectura)", r.returncode == 0, " | ".join(r.stdout.strip().splitlines()[-3:])[:300])
cop = sorted(os.listdir(bdir))[-1] if os.path.isdir(bdir) and os.listdir(bdir) else ""
r = subprocess.run([PY, "main.py", "backup", "verify", f"{bdir}/{cop}"], env=benv, capture_output=True, text=True, timeout=300)
paso("verificación de la copia", r.returncode == 0, " | ".join(r.stdout.strip().splitlines()[-2:])[:300])
sql(O, "create database restaurada")
r = subprocess.run([PY, "main.py", "backup", "restore", f"{bdir}/{cop}", "--target", T], env=benv, capture_output=True, text=True, timeout=600)
paso("restauración en una base aparte", r.returncode == 0, " | ".join((r.stdout + r.stderr).strip().splitlines()[-2:])[:300])
rc, out = sql(T, "select (select count(*) from app.users), (select count(*) from app.platform_meta)")
paso("datos restaurados", rc == 0 and out.startswith("1|"), f"usuarios|meta = {out}")
rc, out = sql(B, "insert into app.platform_meta(k,v) values('x','y')"); paso("radar_backup no puede escribir", rc != 0, out[-80:])
rc, out = sql(A, "create database otra"); paso("radar_app no puede crear bases", rc != 0, out[-80:])
rc, out = sql(A, "create table public.intrusa(id int)"); paso("radar_app no puede crear en public", rc != 0, out[-80:])
logs = open(f"{data}/serve1.log").read() + open(f"{data}/serve2.log").read()
fugas = [n for n, v in (("contraseña admin", ADMIN_PW), ("clave TOTP", env["CRYPTO_RADAR_TOTP_KEY"])) if v in logs] + \
        [n for n, u in (("URL app", A), ("URL backup", B)) if u.split("@")[0].split(":")[-1] in logs]
paso("registros sin secretos", not fugas, ", ".join(fugas) or "ninguna contraseña ni URL en los registros")
json.dump(R, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
print(f"{sum(r['ok'] for r in R)}/{len(R)} pasos OK")
