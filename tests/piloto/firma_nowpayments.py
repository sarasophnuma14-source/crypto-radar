"""¿Acepta la app IPN legítimas de NOWPayments? NOWPayments firma con HMAC-SHA512 el JSON ordenado tal como lo
serializa JavaScript (JSON.stringify: UTF-8 sin escapar y números como 1e-7). Este script firma así unos cuerpos
reales de ejemplo y comprueba si billing.nowpayments_signature_ok los acepta. Uso: python tests/piloto/firma_nowpayments.py"""
import hashlib, hmac, json, math, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from radar import billing


def js_stringify(o):
    """Serialización equivalente a JSON.stringify con claves ordenadas (como hace NOWPayments)."""
    if isinstance(o, dict):
        return "{" + ",".join(json.dumps(k, ensure_ascii=False) + ":" + js_stringify(o[k]) for k in sorted(o)) + "}"
    if isinstance(o, list):
        return "[" + ",".join(js_stringify(x) for x in o) + "]"
    if isinstance(o, bool) or o is None:
        return json.dumps(o)
    if isinstance(o, float):
        if o.is_integer() and abs(o) < 1e21:
            return str(int(o))
        return re.sub(r"e([+-])0*(\d)", r"e\1\2", repr(o))
    if isinstance(o, int):
        return str(o)
    return json.dumps(o, ensure_ascii=False)


SECRET = "ipn-secret-de-prueba"
casos = {
    "ascii, enteros": {"payment_id": 5, "order_id": "CR-1", "payment_status": "finished", "price_amount": 39, "price_currency": "usd"},
    "decimales": {"payment_id": 6, "order_id": "CR-2", "payment_status": "finished", "price_amount": 39.5, "actually_paid": 0.00061234},
    "texto con tilde": {"payment_id": 7, "order_id": "CR-3", "payment_status": "finished", "order_description": "Suscripción Élite"},
    "número muy pequeño": {"payment_id": 8, "order_id": "CR-4", "payment_status": "finished", "actually_paid": 1e-07},
}
fallos = 0
for nombre, body in casos.items():
    sig = hmac.new(SECRET.encode(), js_stringify(body).encode(), hashlib.sha512).hexdigest()
    parsed = json.loads(json.dumps(body, ensure_ascii=False))       # lo que recibe el servidor tras json.loads
    ok = billing.nowpayments_signature_ok(parsed, sig, SECRET)
    fallos += not ok
    print(f"  {nombre:<20} {'aceptada' if ok else 'RECHAZADA (falso negativo)'}")
print(f"RESULTADO: {len(casos) - fallos}/{len(casos)} IPN legítimas aceptadas")
sys.exit(1 if fallos else 0)
