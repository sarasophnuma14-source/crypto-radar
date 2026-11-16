"""Servidor local del panel + planificador en segundo plano (escaneo cada N horas, vigilancia de precio cada 15 min)."""
from __future__ import annotations
import datetime as dt
import base64
import hmac
import ipaddress
import json
import mimetypes
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")
import os
import queue
import re
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from http.cookies import SimpleCookie
from . import storage, scanner, alerts, memes, health, leader, __version__
from .config import WEB_DIR, ROOT, ACCOUNTS, load_settings, save_settings

COOKIE = "cr_session"
LEGAL_PAGES = {"/privacidad": "privacidad.html", "/aviso-de-riesgo": "aviso-de-riesgo.html"}
PUBLIC_GET = ("/", "/index.html", "/entrar", "/app", "/healthz", "/livez", "/readyz", "/api/public/status", "/api/billing/status") + tuple(LEGAL_PAGES)
PUBLIC_POST = ("/api/auth/register", "/api/auth/request", "/api/auth/login", "/api/billing/wompi/webhook", "/api/billing/nowpayments/ipn")

WATCH_EVERY_S = 15 * 60
MEME_EVERY_S = 60 * 60   # memecoins: revisar cada hora (la señal sale al cierre diario 00:00 UTC)


def now():
    return dt.datetime.now(dt.timezone.utc)


def next_scan_time():
    s = load_settings()
    # Solo la fecha, extraída en la base: el planificador pregunta cada 30 s y antes descargaba el informe entero
    last = storage.read_fields("latest.json", ["at"]).get("at")
    if not last:
        # sin escaneos previos: escanear ya (fecha en el pasado; antes devolvía now() y la
        # comparación now() >= now() fallaba por microsegundos, así que nunca arrancaba)
        return now() - dt.timedelta(seconds=1)
    return dt.datetime.fromisoformat(last) + dt.timedelta(hours=float(s["scan_every_hours"]))


def keepalive():
    """En Render gratis el servicio se duerme tras 15 min sin visitas: se visita a sí mismo cada 10 min."""
    import urllib.request
    url = (os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not url:
        return
    while True:
        time.sleep(600)
        try:
            urllib.request.urlopen(url + "/healthz", timeout=20).read()
        except Exception:
            pass


_SCHED = {"on": False}
HEALTH_PATHS = ("/healthz", "/livez", "/readyz")


def scheduler():
    last_watch = 0.0
    last_meme = 0.0
    while True:
        health.beat("scheduler")
        if not leader.is_leader():          # otra instancia (p. ej. la anterior durante un despliegue) hace el trabajo
            time.sleep(30)
            continue
        try:
            if time.time() - last_meme >= MEME_EVERY_S and load_settings().get("meme_strategy", True) and not scanner.status["scanning"]:
                last_meme = time.time()
                memes.run()
            if now() >= next_scan_time() and not scanner.status["scanning"]:
                print(f"[{now():%Y-%m-%d %H:%M}] Escaneo programado…", flush=True)
                scanner.run_scan()
                health.invalidate()
                print(f"[{now():%Y-%m-%d %H:%M}] Escaneo terminado. {scanner.status['last_error'] or ''}", flush=True)
                if scanner.status["last_error"]:
                    # reintento en 20 min si falló (p. ej. sin internet al despertar el Mac)
                    time.sleep(20 * 60)
                    continue
            if time.time() - last_watch >= WATCH_EVERY_S and not scanner.status["scanning"]:
                last_watch = time.time()
                scanner.price_watch()
        except Exception:
            traceback.print_exc()
        time.sleep(30)


def _f(v, default=None):
    """Número finito o `default` (rechaza nan, inf y texto)."""
    try:
        x = float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default
    if x is None or x != x or x in (float("inf"), float("-inf")):
        return default
    return x


MAX_BODY = 64 * 1024
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Content-Security-Policy": ("default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline' "
                                "https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; "
                                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
                                "form-action 'self'; object-src 'none'"),
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
_auth_fail = {}          # ip -> [marcas de tiempo de intentos fallidos]
AUTH_MAX_FAILS, AUTH_WINDOW_S = 10, 15 * 60


def _too_many_fails(ip):
    t = time.time()
    fails = [x for x in _auth_fail.get(ip, []) if t - x < AUTH_WINDOW_S]
    _auth_fail[ip] = fails
    return len(fails) >= AUTH_MAX_FAILS


class Handler(BaseHTTPRequestHandler):
    server_version = "CryptoRadar/" + __version__
    timeout = 30            # conexiones lentas u ociosas se cierran (antes quedaban abiertas para siempre)

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if self._secure():
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, loc):
        self.send_response(302)
        self.send_header("Location", loc)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        self.end_headers()

    def _client_ip(self):
        return client_ip(self.client_address[0], self.headers.get("X-Forwarded-For", ""))

    def _same_origin(self):
        """Defensa CSRF: las peticiones que cambian datos deben venir de esta misma web y en JSON."""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if self._content_length() != 0 and ctype != "application/json":
            return False
        origin = self.headers.get("Origin") or self.headers.get("Referer") or ""
        if not origin:
            return True          # clientes no navegador (curl, pruebas); los navegadores siempre envían Origin en POST
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or ""
        return urlparse(origin).netloc == host

    def _content_length(self):
        """Longitud declarada; None si es inválida o negativa (read(-1) leería sin límite hasta cerrar)."""
        raw = (self.headers.get("Content-Length") or "0").strip()
        if not raw.isdigit():
            return None
        return int(raw)

    def _body(self):
        n = self._content_length()
        if n is None or n > MAX_BODY:
            return None
        if not n:
            return {}
        try:
            b = json.loads(self.rfile.read(n).decode("utf-8"))
            return b if isinstance(b, dict) else {}
        except Exception:
            return {}

    def _static(self, rel):
        p = (WEB_DIR / rel).resolve()
        if not str(p).startswith(str(WEB_DIR.resolve())) or not p.is_file():
            return self._send(404, {"error": "no encontrado"})
        self._send(200, p.read_bytes(), (mimetypes.guess_type(str(p))[0] or "application/octet-stream") + "; charset=utf-8")

    def _authorized(self):
        pw = os.environ.get("CRYPTO_RADAR_PASSWORD")
        if not pw or urlparse(self.path).path in HEALTH_PATHS:
            return True
        ip = self._client_ip()
        if _too_many_fails(ip):
            self._send(429, {"error": "demasiados intentos; espera 15 minutos"})
            return False
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                user_pw = base64.b64decode(h[6:]).decode("utf-8")
                if hmac.compare_digest(user_pw.split(":", 1)[-1].encode(), pw.encode()):
                    return True
            except Exception:
                pass
            _auth_fail.setdefault(ip, []).append(time.time())
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Crypto Radar"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    # ------------------------------------------------------------ entrada común y errores
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        t0 = time.time()
        try:
            if ACCOUNTS:
                from . import webapi
                webapi.handle(self, method)
            elif method == "GET":
                self._get_single()
            else:
                self._post_single()
        except Exception:
            traceback.print_exc()
            try:
                self._send(500, {"error": "error interno; quedó registrado"})
            except Exception:
                pass
        finally:
            if self.path.startswith("/api/") and (time.time() - t0) > 2:
                print(f"[lento] {method} {self.path.split('?')[0]} {time.time() - t0:.1f}s", flush=True)

    def _cookie(self, name):
        try:
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return c[name].value if name in c else None
        except Exception:
            return None

    def _secure(self):
        return (self.headers.get("X-Forwarded-Proto") == "https") or bool(os.environ.get("RENDER"))

    def _send_cookie(self, code, body, token, max_age):
        body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in SECURITY_HEADERS.items():
            self.send_header(k, v)
        if self._secure():
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        flags = "; HttpOnly; SameSite=Lax; Path=/" + ("; Secure" if self._secure() else "")
        self.send_header("Set-Cookie", f"{COOKIE}={token or ''}; Max-Age={max_age}{flags}")
        self.end_headers()
        self.wfile.write(body)

    # ------------------------------------------------------------ modo de un solo usuario (local / contraseña única)
    def _get_single(self, skip_auth=False):
        if not skip_auth and not self._authorized():
            return
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if p == "/livez":
            code, body = health.liveness(__version__)
            return self._send(code, body)
        if p in ("/healthz", "/readyz"):
            # readiness: 503 si la base o el planificador no sirven; "degradado" (200) si el escaneo va atrasado.
            # Solo campos públicos, sin secretos ni trazas (radar/health.py).
            code, body = health.readiness(storage=storage, scanner_status=scanner.status,
                                          scan_every_hours=load_settings()["scan_every_hours"],
                                          uses_db=storage.USE_DB, scheduler_expected=_SCHED["on"], version=__version__)
            return self._send(code, body)
        if p in ("/", "/index.html", "/app"):
            return self._static("index.html")
        if p == "/entrar":
            return self._redirect("/app")
        if p in LEGAL_PAGES:
            return self._static(LEGAL_PAGES[p])
        if p.startswith("/static/"):
            return self._static(p[len("/static/"):])
        if p == "/api/state":
            rep = storage.read("latest.json", {}) or {}
            return self._send(200, {"report": rep, "status": scanner.status, "next_scan": next_scan_time().isoformat(),
                                    "version": __version__, "server_time": now().isoformat()})
        if p == "/api/alerts":
            return self._send(200, list(reversed(storage.read("alerts.json", []) or []))[:300])
        if p == "/api/positions":
            return self._send(200, storage.read("positions.json", []) or [])
        if p == "/api/memes":
            return self._send(200, memes.state())
        if p == "/api/journal":
            return self._send(200, journal_payload(storage.read("journal.json", []) or []))
        if p == "/api/candles":
            c = (storage.read("candles.json", {}) or {}).get(q.get("symbol", "").upper())
            return self._send(200 if c else 404, c or {"error": "sin velas guardadas"})
        if p == "/api/history":
            return self._send(200, (storage.read("history.json", {}) or {}).get(q.get("symbol", "").upper(), []))
        if p == "/api/scans":
            return self._send(200, list(reversed(storage.read("scans.json", []) or []))[:100])
        if p == "/api/backtest/results":
            return self._send(200, backtest_results())
        if p == "/api/paper/report":
            return self._send(200, paper_report(q.get("name")))
        if p == "/api/public/status":
            return self._send(200, {"version": __version__, "accounts": False, "sales_url": os.environ.get("SALES_URL")})
        if p == "/api/memes/radar":
            from . import meme_radar
            return self._send(200, meme_radar.state())
        # /api/backtest se retiró del panel: el backtest solo corre en local (python -m radar.backtest).
        return self._send(404, {"error": "ruta desconocida"})

    def _post_single(self, skip_auth=False, body=None):
        if not skip_auth and not self._authorized():
            return
        p = urlparse(self.path).path
        if not self._same_origin():
            return self._send(403, {"error": "origen no permitido"})
        b = self._body() if body is None else body
        if b is None:
            return self._send(413, {"error": "petición demasiado grande"})
        if p == "/api/memes/check":
            if memes.status["checking"]:
                return self._send(200, {"ok": False, "msg": "Ya se están revisando las memecoins"})
            threading.Thread(target=memes.run, daemon=True).start()
            return self._send(200, {"ok": True})
        if p == "/api/scan":
            if scanner.status["scanning"]:
                return self._send(200, {"ok": False, "msg": "Ya hay un escaneo en curso"})
            threading.Thread(target=scanner.run_scan, daemon=True).start()
            return self._send(200, {"ok": True})
        if p == "/api/settings":
            if str(b.get("telegram_bot_token", "")).startswith("•••"):
                b.pop("telegram_bot_token")
            return self._send(200, save_settings(b))
        if p == "/api/telegram/test":
            ok, msg = alerts.telegram(load_settings(), "✅ Crypto Radar conectado. Aquí recibirás las alertas.")
            return self._send(200, {"ok": ok, "msg": msg})
        if p == "/api/positions":
            sym = str(b.get("symbol", "")).upper().strip()
            entry = _f(b.get("entry"))
            if not sym or not entry:
                return self._send(400, {"error": "símbolo y precio de entrada son obligatorios"})
            plan = {}
            for r in ((storage.read("latest.json", {}) or {}).get("assets") or []):
                if r["symbol"] == sym:
                    plan = r["plan"]
            pos = {"id": uuid.uuid4().hex[:8], "symbol": sym, "entry": entry, "qty": _f(b.get("qty"), 0),
                   "stop": _f(b.get("stop"), plan.get("stop")), "tp1": _f(b.get("tp1"), plan.get("tp1")),
                   "tp2": _f(b.get("tp2"), plan.get("tp2")), "tp3": _f(b.get("tp3"), plan.get("tp3")),
                   "notes": str(b.get("notes", ""))[:300], "opened_at": now().isoformat(), "status": "OPEN", "hits": [],
                   "paper": bool(b.get("paper", True))}
            items = storage.read("positions.json", []) or []
            items.append(pos)
            storage.write("positions.json", items)
            return self._send(200, pos)
        if p.startswith("/api/positions/"):
            parts = p.split("/")
            pid, action = parts[3], (parts[4] if len(parts) > 4 else "")
            items = storage.read("positions.json", []) or []
            for x in items:
                if x["id"] == pid:
                    if action == "close":
                        x["status"] = "CLOSED"
                        x["exit_price"] = _f(b.get("price"), x.get("last_price"))
                        x["closed_at"] = now().isoformat()
                        if x["exit_price"]:
                            x["pnl_pct"] = (x["exit_price"] / x["entry"] - 1) * 100
                    elif action == "delete":
                        items.remove(x)
                    elif action == "update":
                        for k in ("stop", "tp1", "tp2", "tp3", "qty"):
                            if k in b:
                                x[k] = _f(b[k], x.get(k))
                    storage.write("positions.json", items)
                    return self._send(200, {"ok": True})
            return self._send(404, {"error": "posición no encontrada"})
        return self._send(404, {"error": "ruta desconocida"})


def journal_payload(j):
    closed = [x for x in j if x["status"] == "CLOSED" and x["r_multiple"] is not None]
    wins = [x for x in closed if x["r_multiple"] > 0]
    stats = {"signals": len(j), "closed": len(closed), "open": sum(x["status"] == "OPEN" for x in j),
             "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
             "avg_R": round(sum(x["r_multiple"] for x in closed) / len(closed), 2) if closed else None,
             "total_R": round(sum(x["r_multiple"] for x in closed), 2) if closed else 0}
    return {"stats": stats, "items": list(reversed(j))[:300]}


def backtest_results():
    """Resultados del backtest profesional (archivo generado por research/backtest_pro_run.py, sin cifras inventadas)."""
    for f in (ROOT / "docs" / "backtest_results.json", ROOT / "data" / "research" / "backtest_pro_results.json"):
        if f.exists():
            try:
                return json.loads(f.read_text("utf-8"))
            except Exception:
                pass
    return {"available": False, "note": "Aún no hay resultados: ejecuta python3 research/backtest_pro_run.py"}


def paper_report(name=None):
    """Informe del paper trading (solo lectura del diario; sin órdenes reales)."""
    name = name or os.environ.get("PAPER_TRADING_NAME", "principal")
    if not re.match(r"^[A-Za-z0-9_-]{1,40}$", str(name)):
        return {"available": False, "note": "Nombre de evaluación no válido"}
    try:
        from .paper_trading import report
        return report.build(name or os.environ.get("PAPER_TRADING_NAME", "principal"))
    except Exception as e:
        return {"available": False, "note": f"Paper trading no disponible: {str(e)[:200]}"}


def paper_scheduler():
    """Con PAPER_TRADING=1: procesa cada día, a las 00:20 UTC, el día que acaba de cerrar. Nunca envía órdenes."""
    from .paper_trading import engine, report
    name = os.environ.get("PAPER_TRADING_NAME", "principal")
    while True:
        n = dt.datetime.now(dt.timezone.utc)
        nxt = n.replace(hour=0, minute=20, second=0, microsecond=0)
        if nxt <= n:
            nxt += dt.timedelta(days=1)
        time.sleep((nxt - n).total_seconds())
        if not leader.is_leader():
            print("paper trading: otra instancia es la líder; este paso lo procesa ella", flush=True)
            continue
        try:
            from .paper_trading import storage as ps
            if not ps.open_store(name).read_json("spec.json"):
                engine.init(name)
            engine.step_live(name, log=None); report.write(name)
        except BaseException as e:                                         # SystemExit incluido: se registra y se sigue
            print("paper trading:", e, flush=True)


ADMIN_ENV = ("CRYPTO_RADAR_ADMIN_USER", "CRYPTO_RADAR_ADMIN_PASSWORD")


def trusted_proxies():
    """Redes de los proxies cuyo X-Forwarded-For se acepta (docs/RATE_LIMITING.md).

    CRYPTO_RADAR_TRUSTED_PROXIES: lista de redes separadas por comas (p. ej. «10.0.0.0/8,127.0.0.1»), o «*» para
    aceptar cualquier origen inmediato (solo si el servicio no es accesible sin pasar por el proxy).
    Sin la variable: en Render («*», porque el contenedor solo recibe tráfico a través de su proxy); fuera de Render,
    ninguno: X-Forwarded-For se ignora y cuenta la dirección real de la conexión.
    """
    raw = os.environ.get("CRYPTO_RADAR_TRUSTED_PROXIES")
    if raw is None:
        raw = "*" if os.environ.get("RENDER") else ""
    raw = raw.strip()
    if raw == "*":
        return "*"
    nets = []
    for part in raw.split(","):
        if part.strip():
            try:
                nets.append(ipaddress.ip_network(part.strip(), strict=False))
            except ValueError:
                print(f"AVISO: CRYPTO_RADAR_TRUSTED_PROXIES contiene un valor no válido: {part.strip()!r}", flush=True)
    return nets


def _ip(v):
    try:
        return ipaddress.ip_address(v.strip())
    except ValueError:
        return None


def client_ip(peer, fwd, trusted=None):
    """IP del cliente. X-Forwarded-For solo vale si la conexión llega de un proxy autorizado.

    - Origen no autorizado: la dirección de la conexión (el encabezado lo puede escribir cualquiera).
    - «*»: el último valor (el que añade el proxy; los anteriores los escribe el cliente).
    - Lista de redes: se recorre la cadena de derecha a izquierda saltando proxies autorizados; la primera dirección
      que no es un proxy autorizado es el cliente.
    """
    trusted = trusted_proxies() if trusted is None else trusted
    p = _ip(peer or "")
    if not fwd or not trusted or p is None or (trusted != "*" and not any(p in n for n in trusted)):
        return peer or "?"
    chain = [x.strip() for x in fwd.split(",") if x.strip()]
    if trusted == "*":
        return str(_ip(chain[-1])) if chain and _ip(chain[-1]) else peer
    for v in reversed(chain):
        a = _ip(v)
        if a is None:
            return peer               # cadena manipulada: no se confía en nada a la izquierda
        if not any(a in n for n in trusted):
            return str(a)
    return str(_ip(chain[0])) if chain else peer


class PooledHTTPServer(ThreadingHTTPServer):
    """Servidor con un número FIJO de hilos de trabajo (CRYPTO_RADAR_WORKERS, por defecto 16).

    ThreadingHTTPServer crea un hilo por petición: cada hilo abría su propia conexión a PostgreSQL (una por petición,
    con TLS en Neon), la memoria crecía con la concurrencia y la cola de escucha de 5 conexiones provocaba conexiones
    rechazadas en ráfagas (auditoría del piloto, F-04/F-05). Con hilos fijos cada hilo reutiliza su conexión y la cola
    de escucha es de 128.
    """
    request_queue_size = 128
    daemon_threads = True

    def __init__(self, addr, handler, workers=None):
        super().__init__(addr, handler)
        n = int(workers or os.environ.get("CRYPTO_RADAR_WORKERS") or 16)
        self.workers = max(2, min(n, 128))
        from .auth import LOGIN_IP_FAILS
        if self.workers > LOGIN_IP_FAILS:
            # cada inicio de sesión cuenta como fallido mientras se comprueba (docs/RATE_LIMITING.md): con más hilos
            # que LOGIN_IP_FAILS, una ráfaga legítima desde una misma IP podría recibir 429
            print(f"AVISO: {self.workers} hilos > {LOGIN_IP_FAILS} fallidos por IP; usuarios tras una misma IP "
                  "podrían recibir 429 en ráfagas de inicio de sesión", flush=True)
        self._jobs = queue.Queue()
        self.thread_prefix = f"http-{id(self):x}-"
        for i in range(self.workers):
            threading.Thread(target=self._work, name=f"{self.thread_prefix}{i}", daemon=True).start()

    def _work(self):
        while True:
            job = self._jobs.get()
            if job is None:                 # server_close(): el hilo termina
                return
            request, client_address = job
            try:
                self.finish_request(request, client_address)
            except Exception:
                self.handle_error(request, client_address)
            finally:
                self.shutdown_request(request)

    def process_request(self, request, client_address):
        self._jobs.put((request, client_address))

    def server_close(self):
        super().server_close()
        for _ in range(self.workers):
            self._jobs.put(None)


def serve(port=None, host=None, schedule=True):
    s = load_settings()
    port = int(port or os.environ.get("PORT") or s["port"])
    host = host or os.environ.get("CRYPTO_RADAR_HOST", "127.0.0.1")
    if host != "127.0.0.1" and not ACCOUNTS and not os.environ.get("CRYPTO_RADAR_PASSWORD"):
        raise SystemExit("Por seguridad, define CRYPTO_RADAR_PASSWORD (o activa cuentas con CRYPTO_RADAR_ACCOUNTS=1) "
                         "antes de exponer el panel a internet.")
    from . import pilot
    errs = pilot.startup_errors(ACCOUNTS)            # solo entorno, antes de abrir la base; nunca muestra valores
    if errs:
        raise SystemExit("No arranco: configuración de seguridad no válida:\n  - " + "\n  - ".join(errs))
    for w in pilot.startup_warnings():
        print("AVISO:", w, flush=True)
    if ACCOUNTS:
        # En modo cuentas el administrador es obligatorio: sin él nadie aprueba solicitudes ni gestiona usuarios,
        # y un servidor así no debe quedar expuesto. Se comprueba antes de tocar la base.
        missing = [k for k in ADMIN_ENV if not (os.environ.get(k) or "").strip()]
        if missing:
            raise SystemExit("No arranco: el modo cuentas (CRYPTO_RADAR_ACCOUNTS=1) exige administrador. "
                             "Falta definir: " + ", ".join(missing) + ".")
        from . import db, telegram_bot
        if os.environ.get("RENDER") and not db.IS_PG and os.environ.get("CRYPTO_RADAR_ALLOW_SQLITE") != "1":
            raise SystemExit("Modo cuentas en Render sin DATABASE_URL: el disco es efímero y se perderían cuentas, "
                             "sesiones, pagos y límites de intentos en cada reinicio. Configura PostgreSQL (p. ej. Neon) "
                             "en DATABASE_URL.")
        try:
            db.init()                                   # crea, migra y comprueba el esquema completo
        except (db.SchemaError, db.PlatformError) as e:
            raise SystemExit(f"No arranco: {e}")
        print(f"Modo cuentas activo · base de datos {db.backend()} · esquema verificado", flush=True)
        ps = db.platform_status()
        print(f"Plataforma {ps.get('platform')} · inicialización: {ps.get('initialized')} · archivado de 2.0.0: "
              f"{ps.get('legacy_archived')}" + (" · piloto cerrado" if pilot.closed() else ""), flush=True)
        from . import auth
        adm = auth.ensure_admin()                       # AdminBootstrapError (SystemExit) si el entorno no es válido
        if not adm or not adm.get("user"):
            raise SystemExit("No arranco: no se pudo confirmar el administrador del modo cuentas.")
        print(f"Administrador: {adm['user']} · {adm['result']}" +
              (f" · {adm['retirados']} administradores anteriores retirados" if adm.get("retirados") else ""), flush=True)
        st = auth.register_env_enroll_token()
        if st:
            print(f"Código de alta del administrador (CRYPTO_RADAR_ADMIN_ENROLL_TOKEN): {st}", flush=True)
        from . import secretbox
        try:
            key_ok = bool(secretbox.current_key())
        except secretbox.SecretError as e:
            raise SystemExit(f"No arranco: {e}")
        if key_ok:
            r = auth.encrypt_totp_secrets()
            if r["cifrados"] or r["recifrados"]:
                print(f"Secretos TOTP: {r['cifrados']} cifrados ahora, {r['recifrados']} con la clave nueva", flush=True)
        elif auth.totp_key_required():
            raise SystemExit("No arranco: falta CRYPTO_RADAR_TOTP_KEY (32+ caracteres). Los secretos TOTP no se guardan "
                             "sin cifrar en producción (docs/PROTECCION_SECRETOS.md).")
        ts = auth.totp_secrets_status()
        if ts["ilegibles"]:
            print(f"ERROR: {ts['ilegibles']} secretos TOTP no se pueden descifrar con las claves definidas: esos usuarios "
                  "no podrán entrar. Define la clave anterior en CRYPTO_RADAR_TOTP_KEY_OLD (docs/PROTECCION_SECRETOS.md).", flush=True)
        elif ts["en_claro"]:
            print(f"AVISO: {ts['en_claro']} secretos TOTP sin cifrar. Define CRYPTO_RADAR_TOTP_KEY.", flush=True)
        if schedule:
            telegram_bot.start()
    if schedule or os.environ.get("PAPER_TRADING") == "1":
        leader.start()                                  # instancia única para el trabajo de fondo (radar/leader.py)
    if schedule:
        _SCHED["on"] = True
        threading.Thread(target=scheduler, daemon=True).start()
    if os.environ.get("PAPER_TRADING") == "1":
        threading.Thread(target=paper_scheduler, daemon=True).start()
    if os.environ.get("KEEPALIVE") == "1":
        threading.Thread(target=keepalive, daemon=True).start()
    httpd = PooledHTTPServer((host, port), Handler)
    print(f"Crypto Radar {__version__} en http://localhost:{port}  ({httpd.workers} hilos; Ctrl+C para detener)", flush=True)
    httpd.serve_forever()
