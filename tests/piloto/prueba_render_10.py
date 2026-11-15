"""Prueba corta en el entorno REAL (Render + Neon) con como mucho 10 usuarios (R-21). PREPARADA, NO EJECUTADA.

Solo debe lanzarla el responsable, después de desplegar y con su autorización. No crea cuentas, no paga, no toca
datos de nadie: cada usuario de prueba solo lee el panel (GET) tras iniciar sesión una vez.

Antes:
  1. En el panel de administración crea hasta 10 cuentas de prueba (plan Libre), p. ej. prueba01…prueba10, con una
     contraseña común solo para la prueba. Bórralas o desactívalas al terminar.
  2. export CR_BASE=https://<tu-servicio>.onrender.com  CR_PASSWORD='…'  (no la escribas en ningún archivo)

Uso:
  python tests/piloto/prueba_render_10.py --usuarios prueba01,prueba02,... [--minutos 5] [salida.json]
  python tests/piloto/prueba_render_10.py --simular             (ensayo local contra un servidor propio, sin red)

Mide: latencia de inicio de sesión y del panel (p50/p95/p99/máx.), códigos HTTP, /healthz (fuentes de datos, último
escaneo) antes y después, y si alguna petición tarda más de 2 s. Se detiene sola si los errores pasan del 5 %.
"""
import http.client
import json
import os
import random
import ssl
import sys
import threading
import time
import urllib.parse
from pathlib import Path

MAX_USERS = 10
PATHS = [("/api/state", .5), ("/api/me", .25), ("/api/alerts", .25)]


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs); k = (len(xs) - 1) * p / 100; f = int(k)
    return round(xs[f] + (xs[min(f + 1, len(xs) - 1)] - xs[f]) * (k - f), 1)


class Client:
    def __init__(self, base):
        u = urllib.parse.urlsplit(base)
        self.https, self.host, self.port = u.scheme == "https", u.hostname, u.port or (443 if u.scheme == "https" else 80)
        self.cookie = None

    def req(self, method, path, body=None):
        c = (http.client.HTTPSConnection(self.host, self.port, timeout=30, context=ssl.create_default_context())
             if self.https else http.client.HTTPConnection(self.host, self.port, timeout=30))
        h = {"Content-Type": "application/json", "User-Agent": "crypto-radar-prueba-piloto/1"}
        if self.cookie:
            h["Cookie"] = self.cookie
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


def run(base, users, password, minutes):
    if len(users) > MAX_USERS:
        sys.exit(f"Como mucho {MAX_USERS} usuarios en esta prueba")
    R = {"base": base, "usuarios": len(users), "minutos": minutes, "inicio": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    probe = Client(base)
    st, ms, data = probe.req("GET", "/healthz")
    R["healthz_antes"] = {"codigo": st, "ms": round(ms, 1), "cuerpo": json.loads(data or b"{}") if st == 200 else None}
    logins, samples, stop = [], [], threading.Event()

    def user(name):
        c = Client(base)
        st, ms, _ = c.req("POST", "/api/auth/login", {"username": name, "password": password})
        logins.append((st, ms))
        if st != 200:
            return
        rnd = random.Random(name); end = time.time() + minutes * 60
        while time.time() < end and not stop.is_set():
            x, acc = rnd.random(), 0
            for p, w in PATHS:
                acc += w
                if x < acc:
                    break
            st, ms, _ = c.req("GET", p)
            samples.append((st, ms))
            bad = sum(1 for s, _ in samples if s != 200)
            if len(samples) > 40 and bad / len(samples) > 0.05:
                stop.set()
            time.sleep(1 + rnd.random())

    ts = [threading.Thread(target=user, args=(u,)) for u in users]
    [t.start() for t in ts]; [t.join() for t in ts]
    lat = [ms for s, ms in samples if s == 200]
    codes = {}
    for s, _ in samples:
        codes[str(s)] = codes.get(str(s), 0) + 1
    R["login"] = {"ok": sum(1 for s, _ in logins if s == 200), "de": len(logins),
                  "p95_ms": pct([ms for _, ms in logins], 95), "max_ms": round(max((ms for _, ms in logins), default=0), 1),
                  "codigos": sorted({str(s) for s, _ in logins})}
    R["panel"] = {"n": len(samples), "codigos": codes, "p50_ms": pct(lat, 50), "p95_ms": pct(lat, 95), "p99_ms": pct(lat, 99),
                  "max_ms": round(max(lat), 1) if lat else None, "mas_de_2s": sum(1 for x in lat if x > 2000)}
    R["detenida_por_errores"] = stop.is_set()
    st, ms, data = probe.req("GET", "/healthz")
    R["healthz_despues"] = {"codigo": st, "ms": round(ms, 1), "cuerpo": json.loads(data or b"{}") if st == 200 else None}
    ok = (not stop.is_set() and R["login"]["ok"] == len(users) and (R["panel"]["p95_ms"] or 1e9) < 1000
          and R["panel"]["mas_de_2s"] == 0)
    R["criterio"] = "p95 del panel < 1 s, ningún 5xx, ninguna petición > 2 s y todos los usuarios entran"
    R["resultado"] = "APROBADA" if ok else "NO APROBADA"
    return R


def simulate():
    """Ensayo local: arranca el servidor real sobre SQLite temporal, crea 10 usuarios y ejecuta 0,5 min."""
    import subprocess, tempfile, shutil, socket
    root = Path(__file__).resolve().parents[2]
    home = tempfile.mkdtemp(prefix="cr-r10-"); shutil.copytree(root / "web", Path(home) / "web")
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "DATABASE_URL"))}
    env.update({"CRYPTO_RADAR_HOME": home, "CRYPTO_RADAR_ACCOUNTS": "1", "CRYPTO_RADAR_ADMIN_USER": "jefe.r10",
                "CRYPTO_RADAR_ADMIN_PASSWORD": "clave del jefe r10 2026", "CRYPTO_RADAR_ADMIN_TOTP": "optional"})
    code = ("import sys; sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/tests');"
            "import fake_market; fake_market.install();"
            "from radar import auth, db, scanner, server; db.init(); auth.ensure_admin(); scanner.run_scan();"
            "a = auth.get_user(db.one('SELECT id FROM users WHERE email = ?', ('jefe.r10',))['id']);"
            "[auth.admin_create(a, f'prueba{i:02d}', 'clave de prueba r10 2026', 'free', 0, '127.0.0.1') for i in range(1, 11)];"
            "auth.reset_rate_limits(); print('LISTO', flush=True); server.serve(int(sys.argv[2]), schedule=False)")
    p = subprocess.Popen([sys.executable, "-c", code, str(root), str(port)], env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True)
    try:
        while "LISTO" not in (p.stdout.readline() or "LISTO"):
            pass
        time.sleep(1)
        return run(f"http://127.0.0.1:{port}", [f"prueba{i:02d}" for i in range(1, 11)], "clave de prueba r10 2026", 0.5)
    finally:
        p.terminate(); p.wait(10)


if __name__ == "__main__":
    a = sys.argv[1:]
    out = next((x for x in a if x.endswith(".json")), None)
    if "--simular" in a:
        R = simulate(); R["nota"] = "ENSAYO LOCAL (SQLite, sin red). No sustituye a la prueba real en Render + Neon."
    else:
        base, pw = os.environ.get("CR_BASE"), os.environ.get("CR_PASSWORD")
        if not base or not pw or "--usuarios" not in a:
            sys.exit(__doc__)
        users = [u for u in a[a.index("--usuarios") + 1].split(",") if u]
        mins = float(a[a.index("--minutos") + 1]) if "--minutos" in a else 5
        R = run(base.rstrip("/"), users, pw, mins)
    print(json.dumps({k: v for k, v in R.items() if not k.startswith("healthz")}, ensure_ascii=False, indent=1))
    if out:
        Path(out).write_text(json.dumps(R, indent=1, ensure_ascii=False))
    sys.exit(0 if R["resultado"] == "APROBADA" else 1)
