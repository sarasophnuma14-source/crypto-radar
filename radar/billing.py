"""Pagos: Wompi (tarjeta/PSE/Nequi, en COP) y NOWPayments (USDT y otras cripto, en USD).

Regla de oro: el plan de pago SOLO se activa cuando el proveedor confirma el pago de forma verificable:
  1. La notificación (webhook) trae una firma válida con el secreto del comercio, Y
  2. se vuelve a consultar la transacción en la API del proveedor y coincide referencia, estado y monto.
Sin las claves configuradas los pagos quedan DESACTIVADOS (nunca hay pagos simulados ni acceso gratis).
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from . import db, auth
from .data import _context

PRICES_USD = {("pro", "month"): 19, ("pro", "year"): 190, ("elite", "month"): 39, ("elite", "year"): 390}
DAYS = {"month": 30, "year": 365}
# Modo de pagos (CRYPTO_RADAR_PAYMENTS):
#   off      (por defecto) pagos desactivados aunque existan claves. Nadie puede pagar ni activar planes por webhook.
#   sandbox  solo entornos de prueba: API sandbox de Wompi y NOWPayments, y solo claves de prueba (pub_test_/prv_test_).
#            Una clave de producción (pub_prod_/prv_prod_) desactiva el proveedor.
#   live     cobros reales. Debe activarlo a mano el responsable del negocio; nada en el código lo activa.
MODES = ("off", "sandbox", "live")
API = {"wompi": {"sandbox": "https://sandbox.wompi.co/v1", "live": "https://production.wompi.co/v1"},
       "nowpayments": {"sandbox": "https://api-sandbox.nowpayments.io/v1", "live": "https://api.nowpayments.io/v1"}}


def _env(k):
    return (os.environ.get(k) or "").strip()


def payments_mode():
    m = _env("CRYPTO_RADAR_PAYMENTS").lower() or "off"
    return m if m in MODES else "off"


def wompi_api():
    return API["wompi"]["live" if payments_mode() == "live" else "sandbox"]


def nowp_api():
    return API["nowpayments"]["live" if payments_mode() == "live" else "sandbox"]


def _wompi_keys_ok():
    if not all(_env(k) for k in ("WOMPI_PUBLIC_KEY", "WOMPI_INTEGRITY_SECRET", "WOMPI_EVENTS_SECRET", "COP_PER_USD")):
        return False
    pub = _env("WOMPI_PUBLIC_KEY")
    if payments_mode() == "sandbox":
        return pub.startswith("pub_test_")
    return pub.startswith("pub_prod_")


def wompi_enabled():
    return payments_mode() != "off" and _wompi_keys_ok()


def nowpayments_enabled():
    if payments_mode() == "off":
        return False
    return all(_env(k) for k in ("NOWPAYMENTS_API_KEY", "NOWPAYMENTS_IPN_SECRET"))


def status():
    return {"mode": payments_mode(), "wompi": wompi_enabled(), "crypto": nowpayments_enabled(),
            "prices_usd": {f"{p}_{per}": v for (p, per), v in PRICES_USD.items()}}


def _get_json(url, headers=None, data=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=20, context=_context()) as r:
        return json.loads(r.read())


def _new_payment(user_id, provider, plan, period, amount_cents, currency):
    ref = f"CR-{uuid.uuid4().hex[:20]}"
    t = time.time()
    db.execute("INSERT INTO payments(id, user_id, provider, reference, plan, period, amount_cents, currency, status, "
               "verified, raw, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', 0, NULL, ?, ?)",
               (uuid.uuid4().hex, user_id, provider, ref, plan, period, amount_cents, currency, t, t))
    return ref


def checkout(user, plan, period, provider, base_url):
    if (plan, period) not in PRICES_USD:
        raise auth.AuthError("Plan o periodo no válido")
    usd = PRICES_USD[(plan, period)]
    if provider == "wompi":
        if not wompi_enabled():
            raise auth.AuthError("Pagos con Wompi no configurados todavía", 503)
        cents = int(round(usd * float(_env("COP_PER_USD")))) * 100
        ref = _new_payment(user["id"], "wompi", plan, period, cents, "COP")
        sig = hashlib.sha256(f"{ref}{cents}COP{_env('WOMPI_INTEGRITY_SECRET')}".encode()).hexdigest()
        q = urllib.parse.urlencode({"public-key": _env("WOMPI_PUBLIC_KEY"), "currency": "COP", "amount-in-cents": cents,
                                    "reference": ref, "signature:integrity": sig,
                                    "redirect-url": base_url + "/?pago=" + ref})
        auth.log(user["id"], "checkout", {"provider": "wompi", "plan": plan, "period": period, "ref": ref})
        return {"url": "https://checkout.wompi.co/p/?" + q, "reference": ref}
    if provider == "crypto":
        if not nowpayments_enabled():
            raise auth.AuthError("Pagos con cripto no configurados todavía", 503)
        ref = _new_payment(user["id"], "nowpayments", plan, period, usd * 100, "USD")
        body = json.dumps({"price_amount": usd, "price_currency": "usd", "order_id": ref,
                           "order_description": f"Crypto Radar {plan} ({period})",
                           "ipn_callback_url": base_url + "/api/billing/nowpayments/ipn",
                           "success_url": base_url + "/?pago=" + ref, "cancel_url": base_url + "/"}).encode()
        r = _get_json(nowp_api() + "/invoice", {"x-api-key": _env("NOWPAYMENTS_API_KEY"),
                                               "Content-Type": "application/json"}, body, "POST")
        auth.log(user["id"], "checkout", {"provider": "crypto", "plan": plan, "period": period, "ref": ref})
        return {"url": r["invoice_url"], "reference": ref}
    raise auth.AuthError("Medio de pago no válido")


def _grant(pay, raw):
    """Marca el pago verificado y extiende el plan. Idempotente: un pago verificado no se aplica dos veces."""
    if pay["verified"]:
        return False
    cur = db.execute("UPDATE payments SET status = 'APPROVED', verified = 1, raw = ?, updated_at = ? WHERE reference = ? "
                     "AND verified = 0", (json.dumps(raw)[:8000], time.time(), pay["reference"]))
    if cur.rowcount != 1:      # otra entrega del mismo webhook ya lo marcó: no se extiende el plan dos veces
        return False
    u = db.one("SELECT plan, plan_until FROM users WHERE id = ?", (pay["user_id"],))
    base = max(time.time(), (u["plan_until"] or 0) if u and u["plan"] == pay["plan"] else 0)
    until = base + DAYS[pay["period"]] * 86400
    db.execute("UPDATE users SET plan = ?, plan_until = ? WHERE id = ?", (pay["plan"], until, pay["user_id"]))
    auth.log(pay["user_id"], "plan_granted", {"plan": pay["plan"], "until": until, "ref": pay["reference"],
                                              "provider": pay["provider"]})
    return True


def wompi_signature_ok(event, secret):
    try:
        sig = event["signature"]
        vals = []
        for prop in sig["properties"]:
            cur = event["data"]
            for part in prop.split("."):
                cur = cur[part]
            vals.append(str(cur))
        raw = "".join(vals) + str(event["timestamp"]) + secret
        return hmac.compare_digest(hashlib.sha256(raw.encode()).hexdigest().lower(), str(sig["checksum"]).lower())
    except Exception:
        return False


def wompi_webhook(event, fetch=None):
    """Devuelve (código HTTP, mensaje). `fetch` permite inyectar la consulta a la API en las pruebas."""
    if not wompi_enabled():
        return 503, "Wompi no configurado"
    if not wompi_signature_ok(event, _env("WOMPI_EVENTS_SECRET")):
        return 401, "firma inválida"
    tx = (event.get("data") or {}).get("transaction") or {}
    pay = db.one("SELECT * FROM payments WHERE reference = ? AND provider = 'wompi'", (str(tx.get("reference")),))
    if not pay:
        return 404, "referencia desconocida"
    if tx.get("status") != "APPROVED":
        db.execute("UPDATE payments SET status = ?, updated_at = ? WHERE reference = ? AND verified = 0",
                   (str(tx.get("status"))[:20], time.time(), pay["reference"]))
        return 200, "registrado sin activar"
    # verificación independiente con la API de Wompi
    fetch = fetch or (lambda tid: _get_json(f"{wompi_api()}/transactions/{urllib.parse.quote(str(tid))}"))
    try:
        real = fetch(tx.get("id")).get("data") or {}
    except Exception as e:
        return 502, f"no se pudo confirmar con Wompi: {e}"
    if not (real.get("status") == "APPROVED" and real.get("reference") == pay["reference"]
            and int(real.get("amount_in_cents") or -1) == int(pay["amount_cents"]) and real.get("currency") == "COP"):
        auth.log(pay["user_id"], "payment_mismatch", {"ref": pay["reference"], "real": {k: real.get(k) for k in
                                                       ("status", "reference", "amount_in_cents", "currency")}})
        return 409, "la transacción no coincide"
    _grant(pay, {"event": event.get("event"), "transaction_id": tx.get("id")})
    return 200, "plan activado"


def _js_json(o):
    """JSON con claves ordenadas tal como lo produce JSON.stringify (lo que firma NOWPayments): texto UTF-8 sin
    escapar, enteros sin «.0» y exponentes sin ceros (1e-7, no 1e-07)."""
    if isinstance(o, dict):
        return "{" + ",".join(json.dumps(str(k), ensure_ascii=False) + ":" + _js_json(o[k]) for k in sorted(o)) + "}"
    if isinstance(o, list):
        return "[" + ",".join(_js_json(x) for x in o) + "]"
    if o is None or isinstance(o, bool):
        return json.dumps(o)
    if isinstance(o, float):
        if o != o or o in (float("inf"), float("-inf")):
            return "null"
        if o.is_integer() and abs(o) < 1e21:
            return str(int(o))
        r = repr(o)
        if "e" in r:
            m, e = r.split("e")
            r = f"{m}e{e[0]}{e[1:].lstrip('0') or '0'}"
        return r
    if isinstance(o, int):
        return str(o)
    return json.dumps(o, ensure_ascii=False)


def nowpayments_signature_ok(body_obj, header_sig, secret):
    try:
        given = (header_sig or "").strip().lower()
        if not given or not secret:
            return False
        forms = {_js_json(body_obj), json.dumps(body_obj, sort_keys=True, separators=(",", ":"))}
        return any(hmac.compare_digest(hmac.new(secret.encode(), m.encode("utf-8"), hashlib.sha512).hexdigest(), given)
                   for m in forms)
    except Exception:
        return False


def nowpayments_ipn(body_obj, header_sig, fetch=None):
    if not nowpayments_enabled():
        return 503, "cripto no configurado"
    if not nowpayments_signature_ok(body_obj, header_sig, _env("NOWPAYMENTS_IPN_SECRET")):
        return 401, "firma inválida"
    pay = db.one("SELECT * FROM payments WHERE reference = ? AND provider = 'nowpayments'", (str(body_obj.get("order_id")),))
    if not pay:
        return 404, "referencia desconocida"
    if body_obj.get("payment_status") != "finished":
        db.execute("UPDATE payments SET status = ?, updated_at = ? WHERE reference = ? AND verified = 0",
                   (str(body_obj.get("payment_status"))[:20], time.time(), pay["reference"]))
        return 200, "registrado sin activar"
    fetch = fetch or (lambda pid: _get_json(f"{nowp_api()}/payment/{urllib.parse.quote(str(pid))}",
                                            {"x-api-key": _env("NOWPAYMENTS_API_KEY")}))
    try:
        real = fetch(body_obj.get("payment_id"))
    except Exception as e:
        return 502, f"no se pudo confirmar con NOWPayments: {e}"
    if not (real.get("payment_status") == "finished" and str(real.get("order_id")) == pay["reference"]
            and float(real.get("price_amount") or 0) * 100 >= pay["amount_cents"]
            and str(real.get("price_currency", "")).lower() == "usd"):
        auth.log(pay["user_id"], "payment_mismatch", {"ref": pay["reference"]})
        return 409, "el pago no coincide"
    _grant(pay, {"payment_id": body_obj.get("payment_id")})
    return 200, "plan activado"


def admin_grant(admin, email, plan, days, reason):
    """Concesión manual (cortesía, soporte): solo administradores y siempre queda en el registro de actividad."""
    if not auth.admin_ok(admin):
        raise auth.AuthError("Solo administradores con verificación en dos pasos", 403)
    try:
        days = int(days)
    except (TypeError, ValueError):
        raise auth.AuthError("Datos no válidos (plan, días 0-400 y motivo obligatorio)")
    if plan not in ("free", "pro", "elite") or not 0 <= days <= 400 or not str(reason).strip():
        raise auth.AuthError("Datos no válidos (plan, días 0-400 y motivo obligatorio)")
    u = db.one("SELECT id FROM users WHERE email = ?", (str(email).strip().lower(),))
    if not u:
        raise auth.AuthError("Usuario no encontrado", 404)
    until = time.time() + int(days) * 86400 if plan != "free" else None
    db.execute("UPDATE users SET plan = ?, plan_until = ? WHERE id = ?", (plan, until, u["id"]))
    auth.log(admin["id"], "admin_grant", {"user": u["id"], "plan": plan, "days": days, "reason": str(reason)[:200]})
    return True
