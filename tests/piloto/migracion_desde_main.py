"""¿Migra bien una base creada por la versión que está en producción? (R-11) Solo bases PostgreSQL TEMPORALES.

Uso:  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/migracion_desde_main.py [salida.json] [ref]
      ref por defecto: origin/main (2.0.0, lo que corre hoy en Render)

1. `git worktree` de la versión antigua en un directorio temporal (no cambia el repositorio de trabajo).
2. La versión antigua crea su esquema en una base temporal y escribe datos (documentos kv, usuario y actividad).
3. La versión nueva arranca sobre esa base: migraciones, verificación de esquema, archivado de las cuentas de 2.0.0
   (plataforma nueva), administrador, cifrado TOTP.
4. Se comprueba que las cuentas antiguas ya no están en la autenticación y sí en el archivo, que el esquema queda completo y que se puede repetir el
   arranque (migración idempotente). `preflight --db` sobre el resultado.
"""
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
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
DB = f"cr_mig_{secrets.token_hex(3)}"
R = {"pasos": []}


def url():
    return ADMIN_URL.rsplit("/", 1)[0] + "/" + DB


def pg(sql, db=None):
    import psycopg
    with psycopg.connect(url() if db else ADMIN_URL, autocommit=True) as c:
        cur = c.execute(sql)
        rows = cur.fetchall() if cur.description else None
    return [tuple(v.decode() if isinstance(v, bytes) else v for v in r) for r in rows or []]


def step(name, ok, detail=""):
    R["pasos"].append({"paso": name, "ok": bool(ok), "detalle": detail})
    print(f"[{'OK' if ok else 'FALLO'}] {name} · {detail}", flush=True)


def run(code_root, code, extra=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_", "TELEGRAM_"))}
    e.pop("RENDER", None)
    e.update({"DATABASE_URL": url(), "CRYPTO_RADAR_HOME": HOME})
    e.update(extra or {})
    return subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]);" + code, str(code_root)],
                          env=e, capture_output=True, text=True, timeout=600, cwd=HOME)


OLD = r"""
import json, time
from radar import db, storage
db.init()
storage.write("latest.json", {"verdict": "ESPERAR", "nota": "informe escrito por la versión antigua"})
storage.write("settings.json", {"scan_every_hours": 4})
db.execute("INSERT INTO users(id, email, pw_hash, created_at) VALUES ('viejo1', 'usuario.antiguo', 'scrypt$x', 1)", ())
db.execute("INSERT INTO activity(id, user_id, at, action) VALUES ('a1', 'viejo1', 1, 'antiguo')", ())
print(json.dumps({"ok": True}))
"""

NEW = r"""
import json
from radar import db, auth, storage
db.init()
adm = auth.ensure_admin()
r = auth.encrypt_totp_secrets()
print(json.dumps({"admin": adm["result"], "cifrado": r, "latest": storage.read("latest.json", {}),
                  "viejo": db.one("SELECT email, status, totp_enabled FROM users WHERE id = 'viejo1'", ()),
                  "archivo": db.one("SELECT data FROM legacy_archive WHERE source_table = 'users' AND source_id = 'viejo1'", ()),
                  "plataforma": db.platform_status()}))
"""


def main(out=None, ref="origin/main"):
    global HOME
    HOME = tempfile.mkdtemp(prefix="cr-mig-")
    wt = Path(tempfile.mkdtemp(prefix="cr-mig-wt-")) / "antigua"
    subprocess.run(["git", "-C", str(ROOT), "worktree", "add", "--detach", str(wt), ref], check=True, capture_output=True)
    ver = (wt / "radar" / "__init__.py").read_text().split('__version__ = "')[1].split('"')[0]
    R["version_antigua"] = {"ref": ref, "version": ver,
                            "commit": subprocess.run(["git", "-C", str(wt), "rev-parse", "--short", "HEAD"],
                                                     capture_output=True, text=True).stdout.strip()}
    pg(f"CREATE DATABASE {DB}")
    newenv = {"CRYPTO_RADAR_ACCOUNTS": "1", "CRYPTO_RADAR_ADMIN_USER": "jefe.mig", "CRYPTO_RADAR_ADMIN_PASSWORD":
              "clave del jefe de migracion 1", "CRYPTO_RADAR_TOTP_KEY": secrets.token_urlsafe(32),
              "CRYPTO_RADAR_BACKUP_KEY": secrets.token_urlsafe(32)}
    try:
        p = run(wt, OLD)
        cols0 = {t: c for t, c in pg("SELECT table_name, count(*) FROM information_schema.columns WHERE table_schema = "
                                      "current_schema() GROUP BY table_name", True)}
        step(f"La versión {ver} ({R['version_antigua']['commit']}) crea su esquema y escribe datos", p.returncode == 0,
             json.dumps(cols0) if p.returncode == 0 else p.stderr[-400:])
        t = time.time()
        p = run(ROOT, NEW, newenv)
        R["migracion_s"] = round(time.time() - t, 2)
        res = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else {}
        step("La versión nueva migra, verifica el esquema y crea el administrador", p.returncode == 0 and res.get("admin") == "creado",
             f"{R['migracion_s']} s; " + (json.dumps(res.get("cifrado")) if res else p.stderr[-600:]))
        arc = (res.get("archivo") or {}).get("data") or ""
        step("Plataforma nueva: la cuenta de 2.0.0 sale de la autenticación y queda archivada sin contraseña; los "
             "informes (kv) se conservan", res.get("latest", {}).get("nota", "").startswith("informe escrito") and
             res.get("viejo") is None and "usuario.antiguo" in arc and "scrypt" not in arc and
             (res.get("plataforma") or {}).get("initialized") == "archivada_2_0", json.dumps(res.get("plataforma")))
        cols1 = {t: c for t, c in pg("SELECT table_name, count(*) FROM information_schema.columns WHERE table_schema = "
                                      "current_schema() GROUP BY table_name", True)}
        step("Esquema nuevo completo", all(t in cols1 for t in ("rate_limits", "admin_enroll_tokens")) and cols1["users"] > cols0.get("users", 0),
             json.dumps(cols1))
        p = run(ROOT, NEW, newenv)
        res2 = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 else {}
        step("Segundo arranque: migración idempotente", p.returncode == 0 and res2.get("admin") == "verificado", res2.get("admin", p.stderr[-300:]))
        e = {k: v for k, v in os.environ.items() if not k.startswith("CRYPTO_RADAR_")}
        e.update(newenv); e.update({"DATABASE_URL": url(), "CRYPTO_RADAR_HOME": HOME})
        pf = subprocess.run([sys.executable, str(ROOT / "main.py"), "preflight", "--db"], env=e, capture_output=True,
                            text=True, timeout=120, cwd=HOME)
        dbl = [x for x in pf.stdout.splitlines() if any(k in x for k in ("Esquema", "Administrador en la base",
                                                                          "TOTP del administrador en la base", "Secretos TOTP"))]
        step("`preflight --db` tras migrar: esquema OK; TOTP del administrador pendiente (aviso esperado)",
             any(x.startswith("[APROBADO") and "Esquema" in x for x in dbl), " | ".join(dbl))
    finally:
        try:
            pg(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        except Exception:
            pass
        subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(wt)], capture_output=True)
        shutil.rmtree(HOME, ignore_errors=True)
    R["resumen"] = f"{sum(p['ok'] for p in R['pasos'])} de {len(R['pasos'])} pasos OK"
    print(R["resumen"])
    if out:
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    return 0 if all(p["ok"] for p in R["pasos"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None, sys.argv[2] if len(sys.argv) > 2 else "origin/main"))
