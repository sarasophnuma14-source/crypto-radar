"""Evidencia de extremo a extremo del alta segura del administrador y del cifrado TOTP (R-02, R-08), con el servidor
REAL (`main.py serve`) sobre una base PostgreSQL TEMPORAL. Nunca usa bases reales ni envía nada a internet.

Uso:  PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/bootstrap_admin.py [salida.json]

Escenario: alguien conoce la contraseña del administrador ANTES de que este active su segundo factor.
"""
import http.client
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
ADMIN_URL = os.environ.get("PG_ADMIN_URL") or os.environ.get("TEST_DATABASE_URL")
DB = f"cr_boot_{secrets.token_hex(3)}"
USER, PW = "jefe.boot", "clave del jefe del bootstrap 1"
TOTP_KEY = secrets.token_urlsafe(32)
ENV_TOKEN = secrets.token_urlsafe(32)
R = {"pasos": []}


def step(name, ok, detail=""):
    R["pasos"].append({"paso": name, "ok": bool(ok), "detalle": detail})
    print(f"[{'OK' if ok else 'FALLO'}] {name} · {detail}", flush=True)


def pg(sql, db=None):
    import psycopg
    u = ADMIN_URL if not db else ADMIN_URL.rsplit("/", 1)[0] + "/" + db
    with psycopg.connect(u, autocommit=True) as c:
        cur = c.execute(sql)
        rows = cur.fetchall() if cur.description else None
    return [tuple(v.decode() if isinstance(v, bytes) else v for v in r) for r in rows or []]


def free_port():
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


def env(extra=None):
    e = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_", "TELEGRAM_"))}
    e.pop("RENDER", None)
    e.update({"DATABASE_URL": ADMIN_URL.rsplit("/", 1)[0] + "/" + DB, "CRYPTO_RADAR_ACCOUNTS": "1",
              "CRYPTO_RADAR_ADMIN_USER": USER, "CRYPTO_RADAR_ADMIN_PASSWORD": PW, "CRYPTO_RADAR_ADMIN_TOTP": "required",
              "CRYPTO_RADAR_HOME": HOME, "CRYPTO_RADAR_HOST": "127.0.0.1"})
    e.update(extra or {})
    return {k: v for k, v in e.items() if v is not None}


class Srv:
    def __init__(self, extra=None):
        self.port = free_port()
        self.p = subprocess.Popen([sys.executable, str(ROOT / "main.py"), "serve", str(self.port)], env=env(extra),
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=HOME)
        self.log = []
        t = time.time()
        while time.time() - t < 60:
            line = self.p.stdout.readline()
            if not line:
                break
            self.log.append(line.rstrip())
            if "hilos; Ctrl+C" in line:
                return
        self.p.wait(5)

    def alive(self):
        return self.p.poll() is None

    def stop(self):
        if self.alive():
            self.p.terminate(); self.p.wait(10)


class Client:
    def __init__(self, port):
        self.port, self.cookie, self.csrf = port, None, None

    def call(self, path, body=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Content-Type": "application/json"}
        if self.cookie: h["Cookie"] = self.cookie
        if self.csrf: h["X-CSRF-Token"] = self.csrf
        c.request("POST" if body is not None else "GET", path, json.dumps(body).encode() if body is not None else None, h)
        r = c.getresponse(); data = json.loads(r.read() or b"{}")
        ck = r.getheader("Set-Cookie")
        if ck and "cr_session=" in ck: self.cookie = ck.split(";")[0]
        if isinstance(data, dict) and data.get("csrf"): self.csrf = data["csrf"]
        c.close()
        return r.status, data

    def login(self, code=None):
        b = {"username": USER, "password": PW}
        if code: b["code"] = code
        return self.call("/api/auth/login", b)


def main(out=None):
    global HOME
    from radar import totp, secretbox
    HOME = tempfile.mkdtemp(prefix="cr-boot-")
    import shutil
    shutil.copytree(ROOT / "web", Path(HOME) / "web")
    pg(f"CREATE DATABASE {DB}")
    try:
        # 1. Render sin clave de cifrado: no arranca
        s = Srv({"RENDER": "true", "CRYPTO_RADAR_TRUSTED_PROXIES": "127.0.0.1/32"})
        step("En Render sin CRYPTO_RADAR_TOTP_KEY el servidor no arranca", not s.alive(),
             next((x for x in s.log if "TOTP_KEY" in x), "")[:160])
        s.stop()

        # 2. Arranque con clave de cifrado y código de alta en el entorno
        s = Srv({"CRYPTO_RADAR_TOTP_KEY": TOTP_KEY, "CRYPTO_RADAR_ADMIN_ENROLL_TOKEN": ENV_TOKEN})
        step("Arranca con clave TOTP y código de alta del entorno", s.alive(),
             next((x for x in s.log if "Código de alta" in x), ""))
        atk = Client(s.port)
        st, r = atk.login()
        step("El atacante entra con la contraseña (admin aún sin TOTP)", st == 200 and r["user"]["enroll_token_required"],
             f"HTTP {st}; el panel pide código de alta")
        st, r = atk.call("/api/auth/totp/setup", {"password": PW})
        step("Atacante: alta de TOTP sin código → rechazada", st == 403, f"HTTP {st}: {r.get('error', '')[:70]}")
        st, r = atk.call("/api/auth/totp/setup", {"password": PW, "enroll_token": secrets.token_urlsafe(32)})
        step("Atacante: alta con un código inventado → rechazada", st == 403, f"HTTP {st}")
        st, r = atk.call("/api/admin/users")
        step("Atacante: sin TOTP no puede administrar", st == 403, f"HTTP {st}")

        adm = Client(s.port); adm.login()
        st, r = adm.call("/api/auth/totp/setup", {"password": PW, "enroll_token": ENV_TOKEN})
        secret = r.get("secret")
        st2, r2 = adm.call("/api/auth/totp/enable", {"code": totp.code(secret), "enroll_token": ENV_TOKEN})
        step("Administrador legítimo: alta con el código → activada", st == 200 and st2 == 200, f"HTTP {st} / {st2}")
        raw = pg(f"SELECT totp_secret FROM users WHERE email = '{USER}'", DB)[0][0]
        step("El secreto TOTP está cifrado en PostgreSQL", secretbox.is_encrypted(raw) and secret not in raw,
             raw.split(":")[0] + ":" + raw.split(":")[1] + ":…")
        st, _ = atk.call("/api/me")
        step("La sesión del atacante muere al activar el TOTP", st == 401, f"HTTP {st}")
        st, r = Client(s.port).login()
        step("Sin código TOTP ya no se entra", st == 401 and r.get("totp_required"), f"HTTP {st}")
        c = Client(s.port)
        st, r = c.login(totp.code(secret, time.time() + 30))
        st3, _ = c.call("/api/admin/users")
        step("Con contraseña + TOTP: entra y administra", st == 200 and st3 == 200, f"HTTP {st} / {st3}")
        s.stop()

        # 3. Reinicio con el MISMO código de alta en el entorno: no revive
        s = Srv({"CRYPTO_RADAR_TOTP_KEY": TOTP_KEY, "CRYPTO_RADAR_ADMIN_ENROLL_TOKEN": ENV_TOKEN,
                 "CRYPTO_RADAR_ADMIN_RESET": "1"})
        line = next((x for x in s.log if "Código de alta" in x), "")
        step("Reinicio (con restablecimiento) y el mismo código en el entorno: figura como usado", "usado" in line, line)
        a = Client(s.port); a.login()
        st, r = a.call("/api/auth/totp/setup", {"password": PW, "enroll_token": ENV_TOKEN})
        step("Repetición del código ya usado → rechazada", st == 403, f"HTTP {st}")
        # 4. Recuperación: código nuevo desde la línea de órdenes
        p = subprocess.run([sys.executable, str(ROOT / "main.py"), "admin", "enroll-token", "10"], env=env(
            {"CRYPTO_RADAR_TOTP_KEY": TOTP_KEY}), capture_output=True, text=True, cwd=HOME, timeout=60)
        tok = next((x.strip() for x in p.stdout.splitlines() if x.startswith("  ")), "")
        step("`main.py admin enroll-token` genera un código nuevo (10 min)", p.returncode == 0 and len(tok) >= 30,
             "código de " + str(len(tok)) + " caracteres (no se guarda en la evidencia)")
        st, r = a.call("/api/auth/totp/setup", {"password": PW, "enroll_token": tok})
        sec2 = r.get("secret")
        st2, _ = a.call("/api/auth/totp/enable", {"code": totp.code(sec2), "enroll_token": tok})
        step("Recuperación tras perder el teléfono: alta nueva con el código nuevo", st == 200 and st2 == 200, f"HTTP {st} / {st2}")
        s.stop()

        # 5. Clave equivocada: no bloquea para siempre; con la clave anterior en _OLD se recupera y se recifra
        s = Srv({"CRYPTO_RADAR_TOTP_KEY": secrets.token_urlsafe(32)})
        err = next((x for x in s.log if "no se pueden descifrar" in x), "")
        st, _ = Client(s.port).login(totp.code(sec2, time.time() + 30))
        step("Con otra clave: el arranque avisa y el inicio de sesión da 503 (no cuenta como fallo)",
             bool(err) and st == 503, f"HTTP {st}")
        s.stop()
        new = secrets.token_urlsafe(32)
        s = Srv({"CRYPTO_RADAR_TOTP_KEY": new, "CRYPTO_RADAR_TOTP_KEY_OLD": TOTP_KEY})
        rot = next((x for x in s.log if "Secretos TOTP" in x), "")
        s.stop()
        s = Srv({"CRYPTO_RADAR_TOTP_KEY": new})
        st, _ = Client(s.port).login(totp.code(sec2, time.time() + 30))
        step("Rotación: con la clave antigua en _OLD se recifra; después basta la nueva", "1 con la clave nueva" in rot and st == 200,
             f"{rot} · HTTP {st}")
        s.stop()
    finally:
        try:
            pg(f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)")
        except Exception:
            pass
    R["resumen"] = f"{sum(p['ok'] for p in R['pasos'])} de {len(R['pasos'])} pasos OK"
    print(R["resumen"])
    if out:
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    return 0 if all(p["ok"] for p in R["pasos"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
