"""Simulacro de recuperación ante desastre en PostgreSQL TEMPORAL (nunca usa bases reales).

Uso:  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/simulacro_recuperacion.py [salida.json]

1. Crea una base temporal `cr_drill_src_*` y la llena con la propia app: administrador, 40 usuarios en los tres planes,
   sesiones, posiciones, pagos de Wompi confirmados por webhook (sandbox con proveedor simulado), vínculos de Telegram.
2. Crea una copia firmada (HMAC) y la verifica.
3. Altera copias de 5 maneras distintas: cada una debe detectarse.
4. Restaura la copia válida en otra base vacía y compara tabla por tabla y campo por campo.
5. Desastre: escribe un usuario más DESPUÉS de la copia (para medir la pérdida), borra la base de origen y la recupera
   desde la copia en una base nueva. Arranca la app sobre ella: inicio de sesión, planes, posiciones y reintento de
   webhook (no debe conceder dos veces).
6. Borra solo las bases temporales que creó.
"""
import json
import os
import random
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
TAG = secrets.token_hex(3)
DBS = {k: f"cr_drill_{k}_{TAG}" for k in ("src", "dst", "new")}
PW = "clave del simulacro 2026"


def url(name):
    return ADMIN_URL.rsplit("/", 1)[0] + "/" + name


def admin_exec(sql):
    import psycopg
    with psycopg.connect(ADMIN_URL, autocommit=True) as c:
        c.execute(sql)


def child(code, dburl, extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_"))}
    env.update({"DATABASE_URL": dburl, "CRYPTO_RADAR_DATA": tempfile.mkdtemp(prefix="cr-drill-"), "CRYPTO_RADAR_ACCOUNTS": "1",
                "CRYPTO_RADAR_ADMIN_USER": "jefe.drill", "CRYPTO_RADAR_ADMIN_PASSWORD": "clave del jefe del simulacro 1",
                "CRYPTO_RADAR_ADMIN_TOTP": "optional", "CRYPTO_RADAR_PAYMENTS": "sandbox", "WOMPI_PUBLIC_KEY": "pub_test_drill",
                "WOMPI_INTEGRITY_SECRET": "test_integrity_drill", "WOMPI_EVENTS_SECRET": "test_events_drill", "COP_PER_USD": "4000",
                "NOWPAYMENTS_API_KEY": "sandbox", "NOWPAYMENTS_IPN_SECRET": "sandbox"})
    env.update(extra or {})
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]);" + code, str(ROOT)],
                       capture_output=True, text=True, env=env, timeout=600)
    if r.returncode:
        raise RuntimeError(r.stderr[-3000:])
    return json.loads(r.stdout.strip().splitlines()[-1])


POPULATE = r"""
import hashlib, json, random, time
from radar import auth, billing, db, multiuser, telegram_bot
db.init(); auth.ensure_admin(); admin = db.one("SELECT * FROM users WHERE email = ?", ("jefe.drill",))
plans = ["free", "pro", "elite"]; users = []
for i in range(40):
    auth.reset_rate_limits()
    uid = auth.request_access(f"cliente{i:02d}", "clave del simulacro 2026", contact=f"@c{i}", note="ñandú ✓ <b>",
                              ip=f"10.1.0.{i}", consent=auth.POLICY_VERSION)
    plan = plans[i % 3]
    auth.admin_set_status(admin, uid, "approve", plan, 30 if plan != "free" else 0)
    auth.reset_rate_limits()
    auth.login(f"cliente{i:02d}", "clave del simulacro 2026", ip=f"10.2.0.{i}")
    if plan != "free":
        for s in ("BTC", "ETH"):
            multiuser.add_position(uid, {"symbol": s, "entry": 100.0 + i, "qty": 0.5, "notes": "simulacro"})
    users.append(uid)
for uid in users[:10]:                                     # pagos confirmados con el proveedor simulado
    u = auth.get_user(uid)
    r = billing.checkout(u, "pro", "month", "wompi", "https://piloto.example")
    pay = db.one("SELECT * FROM payments WHERE reference = ?", (r["reference"],))
    tid = "tx-" + pay["reference"]; ts = 1763200000
    chk = hashlib.sha256(f"{tid}APPROVED{pay['amount_cents']}{ts}test_events_drill".encode()).hexdigest()
    ev = {"event": "transaction.updated", "timestamp": ts, "signature": {"properties": ["transaction.id",
          "transaction.status", "transaction.amount_in_cents"], "checksum": chk},
          "data": {"transaction": {"id": tid, "status": "APPROVED", "amount_in_cents": pay["amount_cents"], "reference": pay["reference"]}}}
    real = {"data": {"status": "APPROVED", "reference": pay["reference"], "amount_in_cents": pay["amount_cents"], "currency": "COP"}}
    assert billing.wompi_webhook(ev, fetch=lambda t: real)[0] == 200
for uid in users[10:15]:
    telegram_bot.new_link_code(uid)
db.upsert_kv("latest.json", {"verdict": "ESPERAR", "nota": "simulacro"})
n = {t: db.one(f"SELECT COUNT(*) AS n FROM {t}", ())["n"] for t in ("users", "sessions", "positions", "payments", "activity", "telegram_links", "kv")}
print(json.dumps(n))
"""

AFTER_RESTORE = r"""
import hashlib, json, time
from radar import auth, billing, db, multiuser
t0 = time.time()
db.init()                                                   # migraciones + verificación de esquema sobre la base recuperada
res = {"schema_ok": True, "admin": auth.ensure_admin()["result"]}
tok, csrf, u = auth.login("cliente04", "clave del simulacro 2026", ip="10.9.9.9")
res["login_ok"] = bool(tok); res["plan_cliente04"] = auth.effective_plan(auth.get_user(u["id"]))
res["posiciones_cliente04"] = len(multiuser.list_positions(u["id"]))
try:
    auth.login("despues.de.copia", "clave del simulacro 2026", ip="10.9.9.8"); res["usuario_posterior"] = "presente"
except auth.AuthError:
    res["usuario_posterior"] = "perdido (escrito después de la copia)"
pay = db.one("SELECT * FROM payments WHERE verified = 1 ORDER BY reference LIMIT 1", ())
before = auth.get_user(pay["user_id"])["plan_until"]
tid = "tx-" + pay["reference"]; ts = 1763200000
chk = hashlib.sha256(f"{tid}APPROVED{pay['amount_cents']}{ts}test_events_drill".encode()).hexdigest()
ev = {"event": "transaction.updated", "timestamp": ts, "signature": {"properties": ["transaction.id", "transaction.status",
      "transaction.amount_in_cents"], "checksum": chk}, "data": {"transaction": {"id": tid, "status": "APPROVED",
      "amount_in_cents": pay["amount_cents"], "reference": pay["reference"]}}}
real = {"data": {"status": "APPROVED", "reference": pay["reference"], "amount_in_cents": pay["amount_cents"], "currency": "COP"}}
res["webhook_reintento"] = billing.wompi_webhook(ev, fetch=lambda t: real)[0]
res["plan_no_extendido"] = auth.get_user(pay["user_id"])["plan_until"] == before
res["sesiones_restauradas"] = db.one("SELECT COUNT(*) AS n FROM sessions WHERE ip <> '10.9.9.9'", ())["n"]
res["segundos_app"] = round(time.time() - t0, 2)
print(json.dumps(res))
"""


def main(out_path=None):
    if not ADMIN_URL:
        sys.exit("Define PG_ADMIN_URL (una base de pruebas, nunca la de producción)")
    sys.path.insert(0, str(ROOT))
    from radar import backup
    os.environ["CRYPTO_RADAR_BACKUP_KEY"] = secrets.token_hex(24)
    R = {"bases_temporales": list(DBS.values()), "pasos": []}
    work = Path(tempfile.mkdtemp(prefix="cr-drill-copias-"))

    def step(name, ok, detail=""):
        R["pasos"].append({"paso": name, "ok": bool(ok), "detalle": detail})
        print(f"[{'OK' if ok else 'FALLO'}] {name} {detail}")

    try:
        admin_exec(f"CREATE DATABASE {DBS['src']}")
        counts = child(POPULATE, url(DBS["src"]))
        step("Base de origen poblada con la app", counts["users"] == 41, json.dumps(counts))
        R["origen"] = counts

        t = time.time(); d = backup.create(url(DBS["src"]), work); R["segundos_copia"] = round(time.time() - t, 2)
        v = backup.verify(d)
        step("Copia creada, firmada y verificada (restauración de prueba en SQLite)", v["signed"], json.dumps(v["rows"]))
        step("Copia idéntica al origen", backup.compare(d, url(DBS["src"])) == [])

        # --- alteraciones
        def tampered(fn, label):
            c = Path(shutil.copytree(d, work / f"alterada-{label}"))
            fn(c)
            try:
                backup.verify(c); step(f"Alteración detectada: {label}", False, "NO DETECTADA")
            except backup.BackupError as e:
                step(f"Alteración detectada: {label}", True, str(e)[:90])

        def edit_amount(c):
            p = c / "payments.jsonl"; p.write_text(p.read_text().replace('"amount_cents":7600000', '"amount_cents":100', 1))

        def drop_line(c):
            p = c / "users.jsonl"; p.write_text("".join(p.read_text().splitlines(True)[1:]))

        def forge(c):
            import hashlib
            p = c / "users.jsonl"
            rows = [json.loads(x) for x in p.read_text().splitlines()]
            for r in rows:
                if r["email"] == "cliente00":
                    r["is_admin"] = 1
            lines = [json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in rows]
            p.write_text("".join(x + "\n" for x in lines))
            m = json.loads((c / "manifest.json").read_text()); m["tables"]["users"]["sha256"] = backup._sha(lines)
            m.pop("manifest_sha256"); sig = m.pop("hmac_sha256")
            m["manifest_sha256"] = hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()
            m["hmac_sha256"] = sig                                   # conserva la firma vieja
            (c / "manifest.json").write_text(json.dumps(m))

        def strip_sig(c):
            m = json.loads((c / "manifest.json").read_text()); m.pop("hmac_sha256"); (c / "manifest.json").write_text(json.dumps(m))

        def swap_table(c):
            (c / "positions.jsonl").write_text((c / "kv.jsonl").read_text())

        tampered(edit_amount, "monto de un pago cambiado")
        tampered(drop_line, "usuario borrado")
        tampered(forge, "usuario elevado a admin con hashes recalculados")
        tampered(strip_sig, "firma eliminada")
        tampered(swap_table, "tabla sustituida")

        # --- restauración en base vacía
        admin_exec(f"CREATE DATABASE {DBS['dst']}")
        t = time.time(); rows = backup.restore(d, url(DBS["dst"])); R["segundos_restauracion"] = round(time.time() - t, 2)
        step("Restaurada en base vacía", rows["users"] == 41, json.dumps(rows))
        src_dump, dst_dump = (backup._dump(*backup._open(url(DBS[k]))) for k in ("src", "dst"))
        same = {t: src_dump[t][1] == dst_dump[t][1] for t in backup.TABLES}
        step("Registros idénticos campo por campo (usuarios, pagos, posiciones, actividad, Telegram, kv)", all(same.values()), json.dumps(same))
        import psycopg
        with psycopg.connect(url(DBS["dst"])) as c:
            ns = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        step("Sesiones NO restauradas (diseño: hay que volver a entrar)", ns == 0, f"origen {counts['sessions']} → destino {ns}")
        try:
            backup.restore(d, url(DBS["dst"])); step("Segunda restauración sobre base con datos rechazada", False)
        except backup.BackupError:
            step("Segunda restauración sobre base con datos rechazada", True)

        # --- desastre
        child("from radar import auth, db; db.init(); auth.reset_rate_limits(); "
              "uid = auth.request_access('despues.de.copia', 'clave del simulacro 2026', ip='10.3.3.3', consent=auth.POLICY_VERSION); "
              "print('{}')", url(DBS["src"]))
        t0 = time.time()
        admin_exec(f"DROP DATABASE {DBS['src']} WITH (FORCE)")
        step("Desastre: base de origen eliminada", True, DBS["src"])
        admin_exec(f"CREATE DATABASE {DBS['new']}")
        backup.verify(d)
        rows = backup.restore(d, url(DBS["new"]))
        res = child(AFTER_RESTORE, url(DBS["new"]))
        R["rto_segundos"] = round(time.time() - t0, 2)
        step("App arranca sobre la base recuperada (migraciones y esquema)", res["schema_ok"], f"admin: {res['admin']}")
        step("Inicio de sesión con la contraseña original", res["login_ok"])
        step("Plan y posiciones intactos", res["plan_cliente04"] == "pro" and res["posiciones_cliente04"] == 2,
             f"plan {res['plan_cliente04']}, posiciones {res['posiciones_cliente04']}")
        step("Reintento de webhook tras recuperar no concede dos veces", res["webhook_reintento"] == 200 and res["plan_no_extendido"])
        step("Pérdida de datos posterior a la copia (RPO) medida", res["usuario_posterior"].startswith("perdido"), res["usuario_posterior"])
        R["despues"] = res
    finally:
        for name in DBS.values():
            try:
                admin_exec(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
            except Exception as e:
                print("no se pudo borrar", name, e)
        shutil.rmtree(work, ignore_errors=True)
    R["resultado"] = "TODO OK" if all(p["ok"] for p in R["pasos"]) else "HAY FALLOS"
    print("RESULTADO:", R["resultado"], f"· RTO {R.get('rto_segundos')} s")
    if out_path:
        Path(out_path).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    return 0 if R["resultado"] == "TODO OK" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
