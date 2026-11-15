"""Prueba de extremo a extremo de los pagos en modo SANDBOX, sin red y sin cobros.

Arranca la app en un proceso aparte con una base SQLite temporal, CRYPTO_RADAR_PAYMENTS=sandbox y claves de prueba
inventadas (prefijo pub_test_). La API del proveedor se sustituye por un simulador local que además comprueba que
TODA llamada vaya a las URL de sandbox (si alguna apuntara a producción, la prueba falla). Recorre por HTTP:

  Wompi:  checkout → webhook firmado → consulta a la API → plan Pro activo; repetición (idempotente);
          firma falsa (401); monto alterado (409); pago rechazado (no activa).
  Cripto: checkout (factura) → IPN firmada con HMAC-SHA512 → consulta → plan Élite; firma falsa (401).
  Modo off: con las mismas claves, checkout 503 y webhook 503.

No toca la base real (usa un directorio temporal) ni lee claves reales del entorno.
Uso: python main.py payments-selftest   → imprime cada paso y termina con código 0 si todo pasa.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FAKE = {"WOMPI_PUBLIC_KEY": "pub_test_selftest", "WOMPI_INTEGRITY_SECRET": "test_integrity_selftest",
        "WOMPI_EVENTS_SECRET": "test_events_selftest", "COP_PER_USD": "4000",
        "NOWPAYMENTS_API_KEY": "sandbox-selftest-key", "NOWPAYMENTS_IPN_SECRET": "sandbox-selftest-ipn"}


def _child():
    import http.cookiejar
    import threading
    import urllib.error
    import urllib.parse
    import urllib.request
    from http.server import ThreadingHTTPServer
    sys.path.insert(0, str(ROOT))
    from radar import auth, billing, db, server

    calls, txs, pays = [], {}, {}

    def fake_get_json(url, headers=None, data=None, method=None):
        calls.append(url)
        if not (url.startswith(billing.API["wompi"]["sandbox"]) or url.startswith(billing.API["nowpayments"]["sandbox"])):
            raise AssertionError(f"llamada fuera de sandbox: {url}")
        if "/transactions/" in url:
            return {"data": txs[url.rsplit("/", 1)[1]]}
        if url.endswith("/invoice"):
            body = json.loads(data)
            return {"id": "inv1", "invoice_url": "https://sandbox.nowpayments.io/payment/?iid=inv1",
                    "order_id": body["order_id"]}
        if "/payment/" in url:
            return pays[url.rsplit("/", 1)[1]]
        raise AssertionError(url)

    billing._get_json = fake_get_json
    server.ACCOUNTS = True
    db.init()
    auth.ensure_admin()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    ok = True

    def call(op, path, body, headers=None):
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        req = urllib.request.Request(base + path, data=json.dumps(body).encode(), headers=h, method="POST")
        try:
            r = op.open(req)
            return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def check(name, cond):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  [{'OK' if cond else 'FALLO'}] {name}")

    def plan(uid):
        return auth.effective_plan(auth.get_user(uid))

    pw = "clave de prueba sandbox 1"
    u = auth.register("comprador.sandbox@example.com", pw)
    admin = db.one("SELECT * FROM users WHERE email = ?", (os.environ["CRYPTO_RADAR_ADMIN_USER"],))
    db.execute("UPDATE users SET totp_enabled = 1 WHERE id = ?", (admin["id"],))   # solo en esta base temporal
    auth.admin_set_status(auth.get_user(admin["id"]), u["id"], "approve")
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    st, r = call(op, "/api/auth/login", {"username": u["email"], "password": pw})
    check("inicio de sesión del comprador de prueba", st == 200)
    csrf = {"X-CSRF-Token": r.get("csrf", "")}
    print(f"Modo de pagos: {billing.payments_mode()} · Wompi {billing.wompi_api()} · NOWPayments {billing.nowp_api()}")
    check("estado público informa modo sandbox", billing.status()["mode"] == "sandbox")

    # ---- Wompi
    st, r = call(op, "/api/billing/checkout", {"plan": "pro", "period": "month", "provider": "wompi"}, csrf)
    check("checkout Wompi crea referencia con clave de prueba", st == 200 and "pub_test_" in r.get("url", ""))
    ref = r.get("reference")
    pay = db.one("SELECT * FROM payments WHERE reference = ?", (ref,)) or {}

    def wompi_event(status, amount, secret=FAKE["WOMPI_EVENTS_SECRET"], tid="tx-sbx-1"):
        ts = 1763200000
        chk = hashlib.sha256(f"{tid}{status}{amount}{ts}{secret}".encode()).hexdigest()
        return {"event": "transaction.updated", "timestamp": ts,
                "data": {"transaction": {"id": tid, "status": status, "amount_in_cents": amount, "reference": ref,
                                         "currency": "COP"}},
                "signature": {"properties": ["transaction.id", "transaction.status", "transaction.amount_in_cents"],
                              "checksum": chk}}

    anon = urllib.request.build_opener()
    st, _ = call(anon, "/api/billing/wompi/webhook", wompi_event("APPROVED", pay.get("amount_cents"), secret="otra"))
    check("webhook con firma falsa → 401 y sin plan", st == 401 and plan(u["id"]) == "free")
    txs["tx-sbx-2"] = {"status": "APPROVED", "reference": ref, "amount_in_cents": 100, "currency": "COP"}
    st, _ = call(anon, "/api/billing/wompi/webhook", wompi_event("APPROVED", pay.get("amount_cents"), tid="tx-sbx-2"))
    check("monto distinto en la API → 409 y sin plan", st == 409 and plan(u["id"]) == "free")
    st, _ = call(anon, "/api/billing/wompi/webhook", wompi_event("DECLINED", pay.get("amount_cents"), tid="tx-sbx-3"))
    check("pago rechazado → se registra sin activar", st == 200 and plan(u["id"]) == "free")
    txs["tx-sbx-1"] = {"status": "APPROVED", "reference": ref, "amount_in_cents": pay.get("amount_cents"), "currency": "COP"}
    st, _ = call(anon, "/api/billing/wompi/webhook", wompi_event("APPROVED", pay.get("amount_cents")))
    check("webhook firmado + confirmación API → plan Pro", st == 200 and plan(u["id"]) == "pro")
    until = auth.get_user(u["id"])["plan_until"]
    call(anon, "/api/billing/wompi/webhook", wompi_event("APPROVED", pay.get("amount_cents")))
    check("webhook repetido no extiende el plan dos veces", auth.get_user(u["id"])["plan_until"] == until)

    # ---- NOWPayments
    st, r = call(op, "/api/billing/checkout", {"plan": "elite", "period": "month", "provider": "crypto"}, csrf)
    check("checkout cripto crea factura en sandbox", st == 200 and "sandbox" in r.get("url", ""))
    cref = r.get("reference")
    body = {"payment_id": 777, "order_id": cref, "payment_status": "finished", "price_amount": 39, "price_currency": "usd"}
    pays["777"] = dict(body)
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    bad = hmac.new(b"otra", raw, hashlib.sha512).hexdigest()
    st, _ = call(anon, "/api/billing/nowpayments/ipn", body, {"x-nowpayments-sig": bad})
    check("IPN con firma falsa → 401", st == 401 and plan(u["id"]) == "pro")
    sig = hmac.new(FAKE["NOWPAYMENTS_IPN_SECRET"].encode(), raw, hashlib.sha512).hexdigest()
    st, _ = call(anon, "/api/billing/nowpayments/ipn", body, {"x-nowpayments-sig": sig})
    check("IPN firmada + confirmación API → plan Élite", st == 200 and plan(u["id"]) == "elite")

    # ---- Modo off con las mismas claves
    os.environ["CRYPTO_RADAR_PAYMENTS"] = "off"
    st, _ = call(op, "/api/billing/checkout", {"plan": "pro", "period": "year", "provider": "wompi"}, csrf)
    check("modo off: checkout → 503", st == 503)
    st, _ = call(anon, "/api/billing/wompi/webhook", wompi_event("APPROVED", pay.get("amount_cents")))
    check("modo off: webhook → 503", st == 503)
    os.environ["CRYPTO_RADAR_PAYMENTS"] = "sandbox"
    os.environ["WOMPI_PUBLIC_KEY"] = "pub_prod_cualquiera"
    check("sandbox con clave de producción → Wompi desactivado", not billing.wompi_enabled())

    check("todas las llamadas al proveedor fueron a sandbox", all("sandbox" in c for c in calls) and len(calls) >= 3)
    httpd.shutdown()
    print("RESULTADO:", "TODO OK" if ok else "HAY FALLOS")
    return 0 if ok else 1


def cli():
    home = tempfile.mkdtemp(prefix="cr-pay-selftest-")
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("WOMPI_", "NOWPAYMENTS_", "CRYPTO_RADAR_", "TELEGRAM_")) and k not in ("DATABASE_URL", "COP_PER_USD")}
    env.update(FAKE)
    env.update({"CRYPTO_RADAR_HOME": home, "CRYPTO_RADAR_DATA": str(Path(home) / "data"), "CRYPTO_RADAR_ACCOUNTS": "1",
                "CRYPTO_RADAR_PAYMENTS": "sandbox", "CRYPTO_RADAR_ADMIN_USER": "admin.selftest",
                "CRYPTO_RADAR_ADMIN_PASSWORD": "clave temporal de la prueba 1"})
    Path(home, "data").mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); "
                        "from radar import payments_selftest as p; sys.exit(p._child())", str(ROOT)], env=env)
    return r.returncode


if __name__ == "__main__":
    sys.exit(cli())
