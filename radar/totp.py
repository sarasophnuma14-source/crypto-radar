"""TOTP (RFC 6238, HMAC-SHA1, 30 s, 6 dígitos): compatible con Google Authenticator, Authy, 1Password, etc.

Solo librería estándar. Se acepta el paso actual y uno a cada lado (±30 s de desfase de reloj), y un código ya
usado no vale otra vez (protección contra repetición: se guarda el último paso aceptado).
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
import urllib.parse

STEP_S = 30
DIGITS = 6
WINDOW = 1          # pasos aceptados antes y después del actual


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    s = re.sub(r"\s", "", secret).upper()
    return base64.b32decode(s + "=" * (-len(s) % 8))


def hotp(secret: str, counter: int) -> str:
    mac = hmac.new(_key(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    n = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** DIGITS)
    return str(n).zfill(DIGITS)


def step(at: float | None = None) -> int:
    return int((time.time() if at is None else at) // STEP_S)


def code(secret: str, at: float | None = None) -> str:
    return hotp(secret, step(at))


def match(secret: str, given, last_step=None, at: float | None = None):
    """Devuelve el paso que coincide (para guardarlo como último usado) o None. Nunca acepta un paso ya usado."""
    given = re.sub(r"\s", "", str(given or ""))
    if not re.fullmatch(r"\d{%d}" % DIGITS, given):
        return None
    now = step(at)
    for s in range(now - WINDOW, now + WINDOW + 1):
        if last_step is not None and s <= int(last_step):
            continue
        if hmac.compare_digest(hotp(secret, s), given):
            return s
    return None


def uri(secret: str, account: str, issuer: str = "Crypto Radar") -> str:
    label = urllib.parse.quote(f"{issuer}:{account}")
    q = urllib.parse.urlencode({"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS,
                                "period": STEP_S})
    return f"otpauth://totp/{label}?{q}"
