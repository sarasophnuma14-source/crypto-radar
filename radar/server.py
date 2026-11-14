"""Servidor local del panel + planificador en segundo plano (escaneo cada N horas, vigilancia de precio cada 15 min)."""
from __future__ import annotations
import datetime as dt
import base64
import hmac
import json
import mimetypes
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")
import os
import threading
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from . import storage, scanner, alerts, memes, __version__
from .config import WEB_DIR, load_settings, save_settings

WATCH_EVERY_S = 15 * 60
MEME_EVERY_S = 60 * 60   # memecoins: revisar cada hora (la señal sale al cierre diario 00:00 UTC)


def now():
    return dt.datetime.now(dt.timezone.utc)


def next_scan_time():
    s = load_settings()
    last = (storage.read("latest.json", {}) or {}).get("at")
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


def scheduler():
    last_watch = 0.0
    last_meme = 0.0
    while True:
        try:
            if time.time() - last_meme >= MEME_EVERY_S and load_settings().get("meme_strategy", True) and not scanner.status["scanning"]:
                last_meme = time.time()
                memes.run()
            if now() >= next_scan_time() and not scanner.status["scanning"]:
                print(f"[{now():%Y-%m-%d %H:%M}] Escaneo programado…", flush=True)
                scanner.run_scan()
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
    try:
        return float(v) if v not in (None, "") else default
    except (TypeError, ValueError):
        return default


class Handler(BaseHTTPRequestHandler):
    server_version = "CryptoRadar/" + __version__

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if not isinstance(body, (bytes, bytearray)):
            body = json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception:
            return {}

    def _static(self, rel):
        p = (WEB_DIR / rel).resolve()
        if not str(p).startswith(str(WEB_DIR.resolve())) or not p.is_file():
            return self._send(404, {"error": "no encontrado"})
        self._send(200, p.read_bytes(), (mimetypes.guess_type(str(p))[0] or "application/octet-stream") + "; charset=utf-8")

    def _authorized(self):
        pw = os.environ.get("CRYPTO_RADAR_PASSWORD")
        if not pw or self.path == "/healthz":
            return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                user_pw = base64.b64decode(h[6:]).decode("utf-8")
                if hmac.compare_digest(user_pw.split(":", 1)[-1], pw):
                    return True
            except Exception:
                pass
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="Crypto Radar"')
        self.send_header("Content-Length", "0")
        self.end_headers()
        return False

    def do_GET(self):
        if not self._authorized():
            return
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        p = u.path
        if p == "/healthz":
            # diagnóstico mínimo sin datos privados: si el escaneo corre, cuándo terminó y el último error
            rep = storage.read("latest.json", {}) or {}
            err = scanner.status.get("last_error")
            return self._send(200, {"ok": True, "scanning": scanner.status.get("scanning"),
                                    "progress": scanner.status.get("progress"),
                                    "last_scan": rep.get("generated_at") or rep.get("at"),
                                    "last_error": (str(err)[:300] if err else None),
                                    "sources": rep.get("sources")})
        if p in ("/", "/index.html"):
            return self._static("index.html")
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
            j = storage.read("journal.json", []) or []
            closed = [x for x in j if x["status"] == "CLOSED" and x["r_multiple"] is not None]
            wins = [x for x in closed if x["r_multiple"] > 0]
            stats = {"signals": len(j), "closed": len(closed), "open": sum(x["status"] == "OPEN" for x in j),
                     "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
                     "avg_R": round(sum(x["r_multiple"] for x in closed) / len(closed), 2) if closed else None,
                     "total_R": round(sum(x["r_multiple"] for x in closed), 2) if closed else 0}
            return self._send(200, {"stats": stats, "items": list(reversed(j))[:300]})
        if p == "/api/settings":
            s = load_settings()
            s.pop("meme_list", None)
            s["telegram_bot_token"] = ("•••" + s["telegram_bot_token"][-4:]) if s.get("telegram_bot_token") else ""
            return self._send(200, s)
        if p == "/api/candles":
            c = (storage.read("candles.json", {}) or {}).get(q.get("symbol", "").upper())
            return self._send(200 if c else 404, c or {"error": "sin velas guardadas"})
        if p == "/api/history":
            return self._send(200, (storage.read("history.json", {}) or {}).get(q.get("symbol", "").upper(), []))
        if p == "/api/scans":
            return self._send(200, list(reversed(storage.read("scans.json", []) or []))[:100])
        # /api/backtest se retiró del panel: el backtest solo corre en local (python -m radar.backtest).
        return self._send(404, {"error": "ruta desconocida"})

    def do_POST(self):
        if not self._authorized():
            return
        p = urlparse(self.path).path
        b = self._body()
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


def serve(port=None, host=None, schedule=True):
    s = load_settings()
    port = int(port or os.environ.get("PORT") or s["port"])
    host = host or os.environ.get("CRYPTO_RADAR_HOST", "127.0.0.1")
    if host != "127.0.0.1" and not os.environ.get("CRYPTO_RADAR_PASSWORD"):
        raise SystemExit("Por seguridad, define CRYPTO_RADAR_PASSWORD antes de exponer el panel a internet.")
    if schedule:
        threading.Thread(target=scheduler, daemon=True).start()
    if os.environ.get("KEEPALIVE") == "1":
        threading.Thread(target=keepalive, daemon=True).start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Crypto Radar {__version__} en http://localhost:{port}  (Ctrl+C para detener)", flush=True)
    httpd.serve_forever()
