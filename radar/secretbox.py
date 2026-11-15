"""Cifrado autenticado de secretos pequeños (semillas TOTP) con la librería estándar.

Construcción (docs/PROTECCION_SECRETOS.md), «encrypt-then-MAC»:
  * de la clave maestra se derivan dos subclaves independientes con HMAC-SHA256 (cifrado y autenticación);
  * flujo de cifrado = HMAC-SHA256(k_enc, nonce ‖ contador) por bloques de 32 bytes (PRF en modo contador);
  * etiqueta = HMAC-SHA256(k_mac, versión ‖ id de clave ‖ contexto ‖ nonce ‖ texto cifrado), comparada en tiempo
    constante. El contexto (p. ej. el id del usuario) impide copiar un secreto cifrado de una fila a otra.
  * nonce aleatorio de 16 bytes por cifrado.

Formato guardado:  enc1:<id de clave, 8 hex>:<base64url(nonce ‖ cifrado ‖ etiqueta)>

Claves: CRYPTO_RADAR_TOTP_KEY (actual, 32+ caracteres) y, durante una rotación, CRYPTO_RADAR_TOTP_KEY_OLD (solo para
descifrar). Es una clave distinta de CRYPTO_RADAR_BACKUP_KEY y de cualquier otra.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import os
import secrets

PREFIX = "enc1"
ENV, ENV_OLD = "CRYPTO_RADAR_TOTP_KEY", "CRYPTO_RADAR_TOTP_KEY_OLD"


class SecretError(Exception):
    pass


def _material(name):
    k = (os.environ.get(name) or "").strip()
    if k and len(k) < 32:
        raise SecretError(f"{name} debe tener al menos 32 caracteres")
    return k.encode() if k else None


def key_id(master: bytes) -> str:
    return hashlib.sha256(b"crypto-radar/key-id|" + master).hexdigest()[:8]


def _subkeys(master: bytes):
    return (hmac.new(master, b"crypto-radar/totp/enc", hashlib.sha256).digest(),
            hmac.new(master, b"crypto-radar/totp/mac", hashlib.sha256).digest())


def _stream(k_enc: bytes, nonce: bytes, n: int) -> bytes:
    out, i = b"", 0
    while len(out) < n:
        out += hmac.new(k_enc, nonce + i.to_bytes(8, "big"), hashlib.sha256).digest()
        i += 1
    return out[:n]


def _tag(k_mac, kid, context, nonce, ct):
    msg = b"|".join([PREFIX.encode(), kid.encode(), context.encode(), nonce, ct])
    return hmac.new(k_mac, msg, hashlib.sha256).digest()


def current_key():
    return _material(ENV)


def keys():
    """Claves disponibles para descifrar: {id: clave}. La actual primero."""
    out = {}
    for name in (ENV, ENV_OLD):
        k = _material(name)
        if k:
            out.setdefault(key_id(k), k)
    return out


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX + ":")


def encrypt(plaintext: str, context: str, master: bytes | None = None) -> str:
    master = master or current_key()
    if not master:
        raise SecretError(f"Falta {ENV}: no se puede cifrar")
    k_enc, k_mac = _subkeys(master)
    kid = key_id(master)
    nonce = secrets.token_bytes(16)
    pt = plaintext.encode()
    ct = bytes(a ^ b for a, b in zip(pt, _stream(k_enc, nonce, len(pt))))
    blob = nonce + ct + _tag(k_mac, kid, context, nonce, ct)
    return f"{PREFIX}:{kid}:{base64.urlsafe_b64encode(blob).decode().rstrip('=')}"


def decrypt(value: str, context: str) -> str:
    try:
        prefix, kid, b64 = value.split(":", 2)
        blob = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    except (ValueError, AttributeError) as e:
        raise SecretError("Secreto cifrado con formato no válido") from e
    if prefix != PREFIX or len(blob) < 16 + 32:
        raise SecretError("Secreto cifrado con formato no válido")
    master = keys().get(kid)
    if not master:
        raise SecretError(f"El secreto se cifró con otra clave (id {kid}); define esa clave en {ENV} o {ENV_OLD}")
    k_enc, k_mac = _subkeys(master)
    nonce, ct, tag = blob[:16], blob[16:-32], blob[-32:]
    if not hmac.compare_digest(_tag(k_mac, kid, context, nonce, ct), tag):
        raise SecretError("Secreto cifrado alterado o de otra fila (etiqueta inválida)")
    return bytes(a ^ b for a, b in zip(ct, _stream(k_enc, nonce, len(ct)))).decode()
