"""Rutas del modo SaaS (CRYPTO_RADAR_ACCOUNTS=1): cuentas, sesión, planes, pagos, datos por usuario y administración.

Seguridad: sesión por cookie HttpOnly, token CSRF obligatorio en cada POST autenticado (cabecera X-CSRF-Token),
mismo origen y JSON en los POST del navegador, límites de intentos, validación de entradas y aislamiento por usuario.
Los datos de mercado (escaneo) son comunes; el plan decide cuánto se muestra.
"""
from __future__ import annotations
import hmac
import os
import json
import re
from urllib.parse import urlparse, parse_qs
from . import auth, billing, db, storage, multiuser, telegram_bot, memes, scanner
from .server import COOKIE, LEGAL_PAGES, PUBLIC_GET, PUBLIC_POST, _f, backtest_results, next_scan_time, now, __version__

SYMBOL_RE = re.compile(r"^[A-Z0-9]{1,15}$")


def _filter_report(rep, feats):
    if not rep:
        return rep
    rep = dict(rep)
    lim = feats["ranking_limit"]
    rep["ranking"] = (rep.get("ranking") or [])[:lim]
    if lim < 20:
        rep["early"] = (rep.get("early") or [])[:lim]
        rep["breakouts"] = (rep.get("breakouts") or [])[:lim]
        keep = {r["symbol"] for r in rep["ranking"]}
        # Plan Libre: análisis completo solo de las monedas de su top; del resto, datos de mercado básicos
        rep["assets"] = [a if a["symbol"] in keep else
                         {k: a.get(k) for k in ("symbol", "name", "price", "market_cap", "phase", "phase_label", "cap_bucket")}
                         | {"locked": True} for a in (rep.get("assets") or [])]
        rep["locked"] = True
    return rep


# Permisos de cada ruta GET autenticada (revisados en tests/test_suite.py: test_entitlements_matrix).
#   todos      · /api/me, /api/state (filtrado por plan), /api/alerts, /api/journal, /api/scans, /api/candles,
#                /api/history (con plan Libre solo de las monedas de su top), /api/activity, /api/billing/payments,
#                /api/settings (los suyos; el admin ve los del sistema)
#   pro        · /api/positions, /api/memes, /api/memes/radar
#   elite      · /api/backtest/results
#   admin      · /api/admin/users, /api/paper/report (experimental, nunca se muestra como recomendación)
#                Toda acción de administración exige además TOTP activo (auth.admin_ok), salvo CRYPTO_RADAR_ADMIN_TOTP=optional
UPGRADE_PRO = "Disponible en el plan Pro"
UPGRADE_ELITE = "El backtest está disponible en el plan Élite"


def _allowed_symbols(feats):
    """None = todas las monedas; si no, solo las del top que su plan muestra."""
    if feats["ranking_limit"] >= 20:
        return None
    rep = storage.read("latest.json", {}) or {}
    return {r.get("symbol") for r in (rep.get("ranking") or [])[:feats["ranking_limit"]]}


def _filter_alerts(alerts, feats):
    allowed = _allowed_symbols(feats)
    out = []
    for a in alerts:
        kind = str(a.get("kind") or "")
        if kind.startswith("MEME") and not feats.get("memes"):
            continue
        if kind == "EXIT" and not feats.get("exits"):
            continue
        if allowed is not None and a.get("symbol") and a["symbol"] not in allowed:
            continue
        out.append(a)
    return out


def handle(h, method):
    u = urlparse(h.path)
    p = u.path
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    ip = h._client_ip()
    token = h._cookie(COOKIE)
    sess = auth.session(token) if token else None
    user = sess["user"] if sess else None

    if method == "GET":
        if p.startswith("/static/"):
            return h._get_single(skip_auth=True)
        if p in ("/", "/index.html"):
            return h._static("landing.html")                 # web de ventas (pública)
        if p == "/entrar":
            return h._redirect("/app") if user else h._static("entrar.html")
        if p in LEGAL_PAGES:
            return h._static(LEGAL_PAGES[p])
        if p == "/app":
            return h._static("index.html") if user else h._redirect("/entrar")
        if p in ("/healthz", "/livez", "/readyz"):
            return h._get_single(skip_auth=True)
        if p == "/api/public/status":
            # Público: sin veredicto ni régimen (son salidas de un motor no validado y no deben circular como
            # recomendación fuera del panel; hallazgo A-7 de docs/AUDITORIA_INTEGRAL_CRYPTO_RADAR.md).
            rep = storage.read("latest.json", {}) or {}
            return h._send(200, {"version": __version__, "last_scan": rep.get("at"), "access": "approval",
                                 "accounts": True, "billing": billing.status(),
                                 "sales_url": os.environ.get("SALES_URL")})
        if p == "/api/billing/status":
            return h._send(200, billing.status())
        if not user:
            return h._send(401, {"error": "inicia sesión"})
        feats = auth.features(user)
        if p == "/api/me":
            return h._send(200, {"user": auth.public(user), "csrf": sess["csrf"]})
        if p == "/api/state":
            rep = _filter_report(storage.read("latest.json", {}) or {}, feats)
            return h._send(200, {"report": rep, "status": {k: scanner.status.get(k) for k in ("scanning", "progress", "last_watch")},
                                 "next_scan": next_scan_time().isoformat(), "version": __version__,
                                 "server_time": now().isoformat(), "user": auth.public(user)})
        if p == "/api/positions":
            if not feats["portfolio"]:
                return h._send(402, {"error": "La cartera está disponible en el plan Pro"})
            return h._send(200, multiuser.list_positions(user["id"]))
        if p == "/api/memes":
            if not feats["memes"]:
                return h._send(402, {"error": "El radar de memecoins está disponible en el plan Pro"})
            return h._send(200, memes.state())
        if p == "/api/backtest/results":
            if not feats.get("backtest"):
                return h._send(402, {"error": UPGRADE_ELITE})
            return h._send(200, backtest_results())
        if p == "/api/paper/report":
            if not auth.admin_ok(user):
                return h._send(403, {"error": "solo administradores"})
            from .server import paper_report
            return h._send(200, paper_report(q.get("name")))
        if p == "/api/alerts":
            al = list(reversed(storage.read("alerts.json", []) or []))
            return h._send(200, _filter_alerts(al, feats)[:300])
        if p == "/api/journal":
            from .server import journal_payload
            allowed = _allowed_symbols(feats)
            j = storage.read("journal.json", []) or []
            if allowed is not None:
                j = [x for x in j if x.get("symbol") in allowed]
            return h._send(200, journal_payload(j))
        if p == "/api/scans":
            lim = feats["ranking_limit"]
            rows = list(reversed(storage.read("scans.json", []) or []))[:100]
            return h._send(200, [r | {"top": (r.get("top") or [])[:lim]} for r in rows])
        if p in ("/api/candles", "/api/history"):
            allowed = _allowed_symbols(feats)
            if allowed is not None and q.get("symbol", "").upper() not in allowed:
                return h._send(402, {"error": "En el plan Libre el detalle está disponible para las monedas de tu top. " + UPGRADE_PRO})
        if p == "/api/activity":
            rows = db.all_("SELECT at, action, detail, ip FROM activity WHERE user_id = ? ORDER BY at DESC LIMIT 100", (user["id"],))
            return h._send(200, rows)
        if p == "/api/billing/payments":
            rows = db.all_("SELECT reference, provider, plan, period, amount_cents, currency, status, verified, created_at "
                           "FROM payments WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (user["id"],))
            return h._send(200, rows)
        if p == "/api/admin/users":
            if not auth.admin_ok(user):
                return h._send(403, {"error": "solo administradores"})
            return h._send(200, auth.admin_list())
        if p == "/api/settings":
            if not auth.admin_ok(user):
                return h._send(200, auth.public(user)["settings"])
        if p in ("/api/candles", "/api/history", "/api/settings", "/api/memes/radar"):
            if p == "/api/memes/radar" and not feats["memes"]:
                return h._send(402, {"error": "El radar de memecoins está disponible en el plan Pro"})
            return h._get_single(skip_auth=True)
        return h._send(404, {"error": "ruta desconocida"})

    # ---------------------------------------------------------------- POST
    if not h._same_origin():
        return h._send(403, {"error": "origen no permitido"})
    if p == "/api/billing/nowpayments/ipn":
        raw = h._body()
        if raw is None:
            return h._send(413, {"error": "petición demasiado grande"})
        code, msg = billing.nowpayments_ipn(raw, h.headers.get("x-nowpayments-sig"))
        return h._send(code, {"result": msg})
    b = h._body()
    if b is None:
        return h._send(413, {"error": "petición demasiado grande"})
    try:
        if p == "/api/billing/wompi/webhook":
            code, msg = billing.wompi_webhook(b)
            return h._send(code, {"result": msg})
        if p in ("/api/auth/request", "/api/auth/register"):
            # no hay registro abierto: la cuenta queda pendiente hasta que el administrador la apruebe
            auth.request_access(b.get("username") or b.get("email"), b.get("password"), b.get("contact"), b.get("note"), ip,
                                b.get("consent"))
            return h._send(200, {"ok": True, "msg": "Solicitud enviada. Podrás entrar cuando el administrador la apruebe."})
        if p == "/api/auth/login":
            tok, csrf, usr = auth.login(b.get("username") or b.get("email"), b.get("password"), ip, h.headers.get("User-Agent"),
                                        b.get("code"))
            if token:
                auth.logout(token)            # rotación: la sesión anterior deja de valer
            return h._send_cookie(200, {"user": auth.public(usr), "csrf": csrf}, tok, auth.SESSION_DAYS * 86400)
        if not user:
            return h._send(401, {"error": "inicia sesión"})
        if not hmac.compare_digest(str(h.headers.get("X-CSRF-Token") or ""), sess["csrf"]):
            return h._send(403, {"error": "token CSRF inválido; recarga la página"})
        feats = auth.features(user)
        if p == "/api/auth/logout":
            auth.logout(token); auth.log(user["id"], "logout", None, ip)
            return h._send_cookie(200, {"ok": True}, "", 0)
        if p == "/api/auth/logout_all":
            auth.logout_all(user["id"]); auth.log(user["id"], "logout_all", None, ip)
            return h._send_cookie(200, {"ok": True}, "", 0)
        if p == "/api/auth/password":
            auth.change_password(user["id"], b.get("old"), b.get("new"), ip)
            return h._send_cookie(200, {"ok": True, "msg": "Contraseña cambiada; vuelve a iniciar sesión"}, "", 0)
        if p == "/api/auth/totp/setup":
            return h._send(200, auth.totp_setup(user["id"], b.get("password"), ip, b.get("enroll_token")))
        if p == "/api/auth/totp/enable":
            auth.totp_enable(user["id"], b.get("code"), ip, b.get("enroll_token"))
            return h._send_cookie(200, {"ok": True, "msg": "Verificación en dos pasos activada. Vuelve a entrar con el siguiente código que muestre la app (el actual ya se usó)"}, "", 0)
        if p == "/api/auth/totp/disable":
            auth.totp_disable(user["id"], b.get("password"), b.get("code"), ip)
            return h._send(200, {"ok": True})
        if p == "/api/me/settings":
            return h._send(200, {"settings": auth.save_user_settings(user["id"], b)})
        if p == "/api/telegram/link":
            if not feats["telegram"]:
                return h._send(402, {"error": "Las alertas por Telegram están disponibles en el plan Pro"})
            if not telegram_bot.token():
                return h._send(503, {"error": "El bot de Telegram no está configurado en el servidor"})
            return h._send(200, {"code": telegram_bot.new_link_code(user["id"])})
        if p == "/api/billing/checkout":
            base = (h.headers.get("Origin") or "").rstrip("/") or ("https://" + (h.headers.get("Host") or ""))
            r = billing.checkout(user, str(b.get("plan")), str(b.get("period")), str(b.get("provider")), base)
            return h._send(200, r)
        if p == "/api/positions":
            if not feats["portfolio"]:
                return h._send(402, {"error": "La cartera está disponible en el plan Pro"})
            sym = str(b.get("symbol", "")).upper().strip()
            entry = _f(b.get("entry"))
            if not SYMBOL_RE.match(sym) or not entry or entry <= 0:
                return h._send(400, {"error": "símbolo y precio de entrada válidos son obligatorios"})
            plan = next((r["plan"] for r in ((storage.read("latest.json", {}) or {}).get("assets") or [])
                         if r["symbol"] == sym and r.get("plan")), {})
            clean = {"symbol": sym, "entry": entry, "qty": _f(b.get("qty"), 0), "stop": _f(b.get("stop")),
                     "tp1": _f(b.get("tp1")), "tp2": _f(b.get("tp2")), "tp3": _f(b.get("tp3")),
                     "notes": str(b.get("notes", ""))[:300], "paper": bool(b.get("paper", True))}
            return h._send(200, multiuser.add_position(user["id"], clean, plan))
        if p.startswith("/api/positions/"):
            if not feats["portfolio"]:
                return h._send(402, {"error": "La cartera está disponible en el plan Pro"})
            parts = p.split("/")
            if len(parts) < 5 or not re.match(r"^[a-f0-9]{8,32}$", parts[3]):
                return h._send(400, {"error": "ruta no válida"})
            clean = {k: _f(b.get(k)) for k in ("price", "stop", "tp1", "tp2", "tp3", "qty")}
            multiuser.act(user["id"], parts[3], parts[4], clean)
            return h._send(200, {"ok": True})
        if p == "/api/admin/user":
            auth.admin_set_status(user, b.get("id"), str(b.get("action")), str(b.get("plan") or "free"), b.get("days", 0), ip)
            return h._send(200, {"ok": True})
        if p == "/api/admin/user/create":
            auth.admin_create(user, b.get("username"), b.get("password"), str(b.get("plan") or "free"), b.get("days", 0), ip)
            return h._send(200, {"ok": True})
        if p == "/api/admin/user/password":
            auth.admin_reset_password(user, b.get("id"), b.get("password"), ip)
            return h._send(200, {"ok": True})
        if p == "/api/admin/grant":
            billing.admin_grant(user, b.get("email"), b.get("plan"), b.get("days", 0), b.get("reason", ""))
            return h._send(200, {"ok": True})
        if p in ("/api/scan", "/api/settings", "/api/telegram/test", "/api/memes/check"):
            if not auth.admin_ok(user):
                return h._send(403, {"error": "solo administradores"})
            auth.log(user["id"], "admin_" + p.rsplit("/", 1)[-1], None, ip)
            return h._post_single(skip_auth=True, body=b)
        return h._send(404, {"error": "ruta desconocida"})
    except auth.AuthError as e:
        return h._send(e.code, {"error": str(e), **getattr(e, "extra", {})})
