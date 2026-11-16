"""2.1.0 como plataforma NUEVA: nada de la 2.0.0 sirve para entrar (docs/REGISTRO_USUARIOS_PILOTO.md §1).

Servidor real (`main.py serve`) sobre una base TEMPORAL con datos escritos con el esquema exacto de la 2.0.0:
un administrador antiguo, un cliente con plan pagado, una sesión abierta, un código de Telegram, un pago aprobado,
una posición y actividad. Nunca usa bases reales ni envía nada a internet.

Uso:  python tests/piloto/plataforma_nueva.py [salida.json]                       (SQLite)
      PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/plataforma_nueva.py salida.json
      (con PostgreSQL además: arranque simultáneo de 4 procesos sobre la base heredada)
"""
import hashlib
import http.client
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
PG_ADMIN = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
R = {"pasos": []}
NOW = time.time()
OLD_ADMIN, OLD_ADMIN_PW = "jefe.antiguo", "clave antigua del jefe 1"
OLD_USER, OLD_USER_PW = "cliente.antiguo", "clave antigua del cliente 1"
OLD_TOKEN, OLD_TG = "token-de-sesion-antigua-del-cliente-2-0", "ABC12345"
ADMIN, ADMIN_PW = "jefe.piloto", "clave del jefe del piloto 2026"
ENROLL = secrets.token_urlsafe(32)
TOTP_KEY = secrets.token_urlsafe(32)

# Esquema de la 2.0.0 (origin/main 9176b36, radar/db.py), copiado literalmente
SCHEMA_2_0 = [
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
        plan TEXT NOT NULL DEFAULT 'free', plan_until DOUBLE PRECISION, is_admin INTEGER NOT NULL DEFAULT 0,
        telegram_chat_id TEXT, settings TEXT NOT NULL DEFAULT '{}', disabled INTEGER NOT NULL DEFAULT 0,
        failed_logins INTEGER NOT NULL DEFAULT 0, locked_until DOUBLE PRECISION)""",
    """CREATE TABLE IF NOT EXISTS sessions (
        token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL, csrf TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL,
        expires_at DOUBLE PRECISION NOT NULL, ip TEXT, ua TEXT)""",
    """CREATE TABLE IF NOT EXISTS activity (
        id TEXT PRIMARY KEY, user_id TEXT, at DOUBLE PRECISION NOT NULL, action TEXT NOT NULL, detail TEXT, ip TEXT)""",
    """CREATE TABLE IF NOT EXISTS positions (
        id TEXT PRIMARY KEY, user_id TEXT NOT NULL, status TEXT NOT NULL, data TEXT NOT NULL,
        updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY, user_id TEXT, provider TEXT NOT NULL, reference TEXT UNIQUE NOT NULL, plan TEXT,
        period TEXT, amount_cents BIGINT, currency TEXT, status TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0,
        raw TEXT, created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS telegram_links (
        code TEXT PRIMARY KEY, user_id TEXT NOT NULL, expires_at DOUBLE PRECISION NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS kv (
        name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)""",
]


def h20(pw):   # hash_password de la 2.0.0 (mismo formato que 2.1)
    salt = secrets.token_bytes(16)
    return f"scrypt$16384$8$1${salt.hex()}${hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32).hex()}"


LEGACY = [
    ("users", ("id", "email", "pw_hash", "created_at", "plan", "plan_until", "is_admin", "telegram_chat_id"),
     [("legadm" + "0" * 26, OLD_ADMIN, h20(OLD_ADMIN_PW), 1.0, "elite", NOW + 3e7, 1, "5550001"),
      ("leguser" + "0" * 25, OLD_USER, h20(OLD_USER_PW), 2.0, "pro", NOW + 3e7, 0, "5550002")]),
    ("sessions", ("token_hash", "user_id", "csrf", "created_at", "expires_at", "ip", "ua"),
     [(hashlib.sha256(OLD_TOKEN.encode()).hexdigest(), "leguser" + "0" * 25, "csrf-antiguo-2-0", NOW, NOW + 9e5, "10.0.0.1", "x")]),
    ("telegram_links", ("code", "user_id", "expires_at"), [(OLD_TG, "leguser" + "0" * 25, NOW + 9e5)]),
    ("payments", ("id", "user_id", "provider", "reference", "plan", "period", "amount_cents", "currency", "status",
                  "verified", "raw", "created_at", "updated_at"),
     [("pay1", "leguser" + "0" * 25, "wompi", "ref-2-0-pro", "pro", "year", 990000, "COP", "APPROVED", 1, "{}", NOW, NOW)]),
    ("positions", ("id", "user_id", "status", "data", "updated_at"), [("pos1", "leguser" + "0" * 25, "open", "{}", NOW)]),
    ("activity", ("id", "user_id", "at", "action", "detail", "ip"), [("act1", "leguser" + "0" * 25, NOW, "login", None, "10.0.0.1")]),
    ("kv", ("name", "value", "updated_at"), [("latest.json", json.dumps({"verdict": "ESPERAR", "nota": "informe 2.0"}), NOW)]),
]


def step(name, ok, detail=""):
    R["pasos"].append({"paso": name, "ok": bool(ok), "detalle": str(detail)[:400]})
    print(f"[{'OK' if ok else 'FALLO'}] {name} · {str(detail)[:200]}", flush=True)


class Base:
    def __init__(self, pg):
        self.pg = pg
        if pg:
            self.name = f"cr_plat_{secrets.token_hex(3)}"
            self._admin(f"CREATE DATABASE {self.name}")
            self.url = PG_ADMIN.rsplit("/", 1)[0] + "/" + self.name
        else:
            self.dir = Path(tempfile.mkdtemp(prefix="cr-plat-db-"))
            self.url = ""

    def _admin(self, sql):
        import psycopg
        with psycopg.connect(PG_ADMIN, autocommit=True) as c:
            c.execute(sql)

    def conn(self):
        if self.pg:
            import psycopg
            return psycopg.connect(self.url, autocommit=True)
        c = sqlite3.connect(str(self.dir / "app.db"), isolation_level=None)
        return c

    def q(self, sql, args=()):
        c = self.conn()
        try:
            cur = c.execute(sql.replace("?", "%s") if self.pg else sql, args)
            rows = cur.fetchall() if cur.description else None
            return None if rows is None else [tuple(v.decode() if isinstance(v, bytes) else v for v in r) for r in rows]
        finally:
            c.close()

    def load_legacy(self):
        c = self.conn()
        for s in SCHEMA_2_0:
            c.execute(s if self.pg else s.replace("DOUBLE PRECISION", "REAL").replace("BIGINT", "INTEGER"))
        ph = "%s" if self.pg else "?"
        for t, cols, rows in LEGACY:
            for r in rows:
                c.execute(f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join([ph] * len(cols))})", r)
        c.close()

    def drop(self):
        if self.pg:
            try:
                self._admin(f"DROP DATABASE IF EXISTS {self.name} WITH (FORCE)")
            except Exception:
                pass
        else:
            shutil.rmtree(self.dir, ignore_errors=True)


def env(base, home, extra=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_", "TELEGRAM_",
                                                                    "DATABASE_URL"))}
    e.pop("RENDER", None)
    e.update({"CRYPTO_RADAR_HOME": str(home), "CRYPTO_RADAR_ACCOUNTS": "1", "CRYPTO_RADAR_ADMIN_USER": ADMIN,
              "CRYPTO_RADAR_ADMIN_PASSWORD": ADMIN_PW, "CRYPTO_RADAR_ADMIN_TOTP": "required",
              "CRYPTO_RADAR_TOTP_KEY": TOTP_KEY, "CRYPTO_RADAR_HOST": "127.0.0.1"})
    if base.pg:
        e["DATABASE_URL"] = base.url
    else:
        e["CRYPTO_RADAR_DATA"] = str(base.dir)
    e.update(extra or {})
    return {k: v for k, v in e.items() if v is not None}


def free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Srv:
    def __init__(self, e, home):
        self.port = free_port()
        self.p = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "serve", str(self.port)], env=e,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(home))
        self.log, t = [], time.time()
        while time.time() - t < 90:
            line = self.p.stdout.readline()
            if not line:
                break
            self.log.append(line.rstrip())
            if "hilos; Ctrl+C" in line:
                return
        self.p.wait(10)

    def alive(self):
        return self.p.poll() is None

    def line(self, word):
        return next((x for x in self.log if word in x), "")

    def stop(self):
        if self.alive():
            self.p.terminate(); self.p.wait(10)


class Client:
    def __init__(self, port, cookie=None):
        self.port, self.cookie, self.csrf = port, cookie, None

    def call(self, path, body=None, method=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Content-Type": "application/json"}
        if self.cookie: h["Cookie"] = self.cookie
        if self.csrf: h["X-CSRF-Token"] = self.csrf
        c.request(method or ("POST" if body is not None else "GET"), path,
                  json.dumps(body).encode() if body is not None else None, h)
        r = c.getresponse(); raw = r.read()
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            data = {}
        ck = r.getheader("Set-Cookie")
        if ck and "cr_session=" in ck: self.cookie = ck.split(";")[0]
        if isinstance(data, dict) and data.get("csrf"): self.csrf = data["csrf"]
        c.close()
        return r.status, data

    def login(self, u, pw, code=None):
        b = {"username": u, "password": pw}
        if code: b["code"] = code
        return self.call("/api/auth/login", b)


def scenario(pg):
    from radar import totp
    tag = "PostgreSQL" if pg else "SQLite"
    base, home = Base(pg), Path(tempfile.mkdtemp(prefix="cr-plat-"))
    shutil.copytree(ROOT / "web", home / "web")
    try:
        base.load_legacy()
        s = Srv(env(base, home, {"CRYPTO_RADAR_ADMIN_ENROLL_TOKEN": ENROLL}), home)
        step(f"[{tag}] El servidor 2.1 arranca sobre una base con datos de la 2.0.0 y la archiva",
             s.alive() and "archivada_2_0" in s.line("Plataforma"), s.line("Plataforma"))
        users = base.q("SELECT email, is_admin FROM users")
        step(f"[{tag}] Solo queda el administrador nuevo; ninguna cuenta, sesión, código, pago ni posición de 2.0.0",
             users == [(ADMIN, 1)] and all(base.q(f"SELECT count(*) FROM {t}")[0][0] == 0 for t in
                                            ("sessions", "telegram_links", "payments", "positions")), users)
        arc = base.q("SELECT source_table, data FROM legacy_archive")
        blob = " ".join(d for _, d in arc)
        step(f"[{tag}] Lo histórico queda en legacy_archive, sin contraseñas, tokens de sesión ni códigos",
             sorted({t for t, _ in arc}) == ["activity", "payments", "positions", "sessions", "telegram_links", "users"]
             and "scrypt$" not in blob and "csrf-antiguo" not in blob and OLD_TG not in blob and "ref-2-0-pro" in blob,
             f"{len(arc)} filas archivadas")
        kv = base.q("SELECT value FROM kv WHERE name = 'latest.json'")
        step(f"[{tag}] Los documentos del sistema (kv: informes) se conservan", kv and "informe 2.0" in kv[0][0], "")
        st1, r1 = Client(s.port).login(OLD_ADMIN, OLD_ADMIN_PW)
        st2, r2 = Client(s.port).login(OLD_USER, OLD_USER_PW)
        step(f"[{tag}] El administrador y el cliente de 2.0.0 no pueden entrar (mismo mensaje que un usuario inexistente)",
             st1 == 401 and st2 == 401 and r1.get("error") == r2.get("error") == "Usuario o contraseña incorrectos",
             f"HTTP {st1} / {st2}")
        st, _ = Client(s.port, f"cr_session={OLD_TOKEN}").call("/api/me")
        step(f"[{tag}] La cookie de sesión de 2.0.0 se rechaza", st == 401, f"HTTP {st}")
        tg = subprocess.run([sys.executable, "-c", "import sys, json; sys.path.insert(0, sys.argv[1]); "
                             "from radar import telegram_bot as t; print(json.dumps([t.handle({'chat': {'id': 5550002}, "
                             "'text': '/estado'}), t.handle({'chat': {'id': 5550009}, 'text': '/start " + OLD_TG + "'})]))",
                             str(ROOT)], env=env(base, home), capture_output=True, text=True, timeout=60, cwd=str(home))
        out = json.loads(tg.stdout.strip().splitlines()[-1]) if tg.returncode == 0 else ["", ""]
        step(f"[{tag}] Telegram: el chat vinculado en 2.0.0 no recibe datos y el código antiguo no vincula",
             "no está vinculado" in out[0] and "no válido" in out[1], " | ".join(x[:50] for x in out) or tg.stderr[-200:])
        # un usuario nuevo que pide el nombre del cliente antiguo e intenta colar privilegios en la solicitud
        st, r = Client(s.port).call("/api/auth/request", {"username": OLD_USER, "password": "clave nueva del cliente 22",
                                                          "consent": "2026-11-15", "is_admin": 1, "plan": "elite",
                                                          "status": "active", "plan_until": 9e9})
        row = base.q("SELECT status, is_admin, plan, plan_until FROM users WHERE email = ?", (OLD_USER,))
        step(f"[{tag}] Registro nuevo desde cero: queda pendiente, sin rol de administrador ni plan heredado o inyectado",
             st == 200 and row == [("pending", 0, "free", None)], f"HTTP {st}; {row}")
        st, r = Client(s.port).login(OLD_USER, "clave nueva del cliente 22")
        step(f"[{tag}] Pendiente: no entra hasta que el administrador apruebe", st == 403, f"HTTP {st}: {r.get('error')}")
        # (3 solicitudes por IP y hora: aquí solo cabe una más; los nombres genéricos reservados se prueban en T30)
        st, _ = Client(s.port).call("/api/auth/request", {"username": ADMIN, "password": "clave del intruso 2026 x",
                                                          "consent": "2026-11-15"})
        step(f"[{tag}] Nadie puede pedir el nombre del administrador del entorno", st == 409, f"HTTP {st}")
        adm = Client(s.port)
        st, r = adm.login(ADMIN, ADMIN_PW)
        st2, _ = adm.call("/api/admin/users")
        step(f"[{tag}] Administrador sin TOTP: entra pero no administra", st == 200 and st2 == 403, f"HTTP {st} / {st2}")
        st, r = adm.call("/api/auth/totp/setup", {"password": ADMIN_PW, "enroll_token": ENROLL})
        sec = r.get("secret")
        st2, _ = adm.call("/api/auth/totp/enable", {"code": totp.code(sec or "A" * 32), "enroll_token": ENROLL})
        adm = Client(s.port)
        st3, _ = adm.login(ADMIN, ADMIN_PW, totp.code(sec or "A" * 32, time.time() + 30))
        st4, lst = adm.call("/api/admin/users")
        names = sorted(u.get("email") for u in lst) if isinstance(lst, list) else lst
        step(f"[{tag}] Con TOTP (código de alta de un solo uso) administra; la lista no muestra cuentas de 2.0.0",
             (st, st2, st3, st4) == (200, 200, 200, 200) and OLD_ADMIN not in names, f"{(st, st2, st3, st4)} · {names}")
        nid = base.q("SELECT id FROM users WHERE email = ?", (OLD_USER,))[0][0]
        st, _ = adm.call("/api/admin/user", {"id": nid, "action": "approve"})
        u = Client(s.port)
        st2, r = u.login(OLD_USER, "clave nueva del cliente 22")
        me = r.get("user") or {}
        st3, pays = u.call("/api/billing/payments")
        step(f"[{tag}] Aprobado: entra con plan Libre, sin el plan pagado ni los pagos de 2.0.0",
             st == 200 and st2 == 200 and me.get("plan") == "free" and not me.get("is_admin") and pays == [],
             f"plan {me.get('plan')}; pagos {pays}")
        other = base.q("SELECT id FROM users WHERE email = ?", (ADMIN,))[0][0]
        codes = [u.call("/api/admin/users")[0], u.call("/api/admin/user", {"id": nid, "action": "approve"})[0],
                 u.call("/api/admin/user/create", {"username": "colado1", "password": "clave del colado 2026"})[0],
                 u.call("/api/admin/grant", {"email": OLD_USER, "plan": "elite", "days": 30, "reason": "x"})[0],
                 u.call("/api/admin/user/password", {"id": other, "password": "clave robada 2026 xx"})[0],
                 u.call("/api/scan", {})[0], u.call("/api/settings", {"scan_every_hours": 1})[0]]
        step(f"[{tag}] Usuario normal: todas las rutas de administración responden 403", all(c == 403 for c in codes), codes)
        st, _ = adm.call("/api/admin/user/create", {"username": "otro.jefe", "password": "clave del otro jefe 2026"})
        n_adm = base.q("SELECT count(*) FROM users WHERE is_admin <> 0")[0][0]
        step(f"[{tag}] El administrador tampoco puede crear otro administrador", st == 200 and n_adm == 1, f"administradores: {n_adm}")
        s.stop()

        n_arc = base.q("SELECT count(*) FROM legacy_archive")[0][0]
        s = Srv(env(base, home), home)
        st, _ = Client(s.port).login(OLD_ADMIN, OLD_ADMIN_PW)
        step(f"[{tag}] Reinicio: la plataforma ya está marcada, nada se vuelve a archivar ni a importar, 2.0.0 sigue fuera",
             "verificada" not in s.line("Plataforma") and "archivada_2_0" in s.line("Plataforma") and
             base.q("SELECT count(*) FROM legacy_archive")[0][0] == n_arc and st == 401
             and "verificado" in s.line("Administrador:"), f"{s.line('Plataforma')} · {s.line('Administrador:')} · HTTP {st}")
        s.stop()
        s = Srv(env(base, home), home)
        n_adm = base.q("SELECT count(*) FROM users WHERE is_admin <> 0")[0][0]
        step(f"[{tag}] Segundo reinicio: un único administrador (inicialización idempotente)", s.alive() and n_adm == 1,
             f"administradores: {n_adm}")
        s.stop()
        s = Srv(env(base, home, {"CRYPTO_RADAR_ADMIN_USER": "jefe.relevo", "CRYPTO_RADAR_ADMIN_PASSWORD":
                                 "clave del jefe de relevo 2026"}), home)
        n_adm = base.q("SELECT email FROM users WHERE is_admin <> 0")
        st, _ = Client(s.port).login(ADMIN, ADMIN_PW, totp.code(sec or "A" * 32, time.time() + 30))
        step(f"[{tag}] Cambiar el administrador del entorno retira al anterior: nunca hay dos",
             n_adm == [("jefe.relevo",)] and st == 403 and "retirados" in s.line("Administrador:"),
             f"{s.line('Administrador:')} · antiguo: HTTP {st}")
        s.stop()

        # una base de 2.1 que perdió la marca no se archiva: el servidor se niega a arrancar
        base.q("DELETE FROM platform_meta")
        s = Srv(env(base, home), home)
        step(f"[{tag}] Base de 2.1 sin marca: no se archiva nada y el servidor no arranca", not s.alive() and
             base.q("SELECT count(*) FROM users")[0][0] >= 3, s.line("cuentas de 2.1")[:160])
        s = Srv(env(base, home, {"CRYPTO_RADAR_PLATFORM_ADOPT": "1", "CRYPTO_RADAR_ADMIN_USER": "jefe.relevo",
                                 "CRYPTO_RADAR_ADMIN_PASSWORD": "clave del jefe de relevo 2026"}), home)
        step(f"[{tag}] Con CRYPTO_RADAR_PLATFORM_ADOPT=1 se marca tal como está (y avisa de borrar la variable)",
             s.alive() and "adoptada" in s.line("Plataforma") and "PLATFORM_ADOPT" in s.line("AVISO"), s.line("Plataforma"))
        s.stop()
    finally:
        base.drop(); shutil.rmtree(home, ignore_errors=True)


def concurrent_pg():
    base, home = Base(True), Path(tempfile.mkdtemp(prefix="cr-plat-c-"))
    try:
        base.load_legacy()
        code = ("import sys, json; sys.path.insert(0, sys.argv[1]); from radar import db; db.init(); "
                "print(json.dumps(db.platform_status()))")
        ps = [subprocess.Popen([sys.executable, "-c", code, str(ROOT)], env=env(base, home), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, cwd=str(home)) for _ in range(4)]
        outs = [p.communicate(timeout=120) for p in ps]
        rcs = [p.returncode for p in ps]
        n = base.q("SELECT source_table, count(*) FROM legacy_archive GROUP BY source_table ORDER BY 1")
        meta = base.q("SELECT count(*) FROM platform_meta WHERE k = 'platform'")[0][0]
        step("[PostgreSQL] 4 procesos arrancan a la vez sobre la base heredada: se archiva UNA vez, sin errores",
             rcs == [0, 0, 0, 0] and meta == 1 and dict(n).get("users") == 2 and base.q("SELECT count(*) FROM users")[0][0] == 0,
             f"códigos {rcs}; archivo {n}; " + " ".join(e[-120:] for _, e in outs if e))
    finally:
        base.drop(); shutil.rmtree(home, ignore_errors=True)


def main(out=None):
    scenario(False)
    if PG_ADMIN:
        scenario(True)
        concurrent_pg()
    R["resumen"] = f"{sum(p['ok'] for p in R['pasos'])} de {len(R['pasos'])} pasos OK"
    print(R["resumen"])
    if out:
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    return 0 if all(p["ok"] for p in R["pasos"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
