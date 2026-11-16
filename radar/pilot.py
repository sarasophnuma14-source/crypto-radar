"""Piloto cerrado y comprobaciones de seguridad que impiden arrancar (docs/CONFIGURACION_RENDER_NEON.md).

`startup_errors()` revisa SOLO variables de entorno y se ejecuta antes de abrir la base: si devuelve algo, el servidor
no arranca. Los mensajes nombran la variable, nunca su valor.

Piloto cerrado (CRYPTO_RADAR_PILOT, por defecto «cerrado»):
  * registro solo por solicitud, con aprobación del administrador (siempre es así en modo cuentas);
  * pagos: «live» prohibido; en Render, cualquier modo distinto de «off» también (con tarjetas de prueba del sandbox
    alguien obtendría un plan sin pagar);
  * la interfaz muestra el aviso de piloto cerrado.
"""
from __future__ import annotations
import os
from urllib.parse import parse_qs, urlsplit

MIN_KEY = 32


def _e(k):
    return (os.environ.get(k) or "").strip()


def closed() -> bool:
    return _e("CRYPTO_RADAR_PILOT").lower() not in ("abierto", "0", "off", "no")


def on_render() -> bool:
    return bool(os.environ.get("RENDER"))


def startup_errors(accounts: bool) -> list[str]:
    """Errores BLOQUEANTES de configuración. Lista vacía = se puede arrancar."""
    errs = []
    pay = _e("CRYPTO_RADAR_PAYMENTS").lower() or "off"
    if pay not in ("off", "sandbox", "live"):
        errs.append("CRYPTO_RADAR_PAYMENTS no es off, sandbox ni live")
    if closed() and pay == "live":
        errs.append("CRYPTO_RADAR_PAYMENTS=live durante el piloto cerrado: los cobros reales están prohibidos")
    if closed() and on_render() and pay == "sandbox":
        errs.append("CRYPTO_RADAR_PAYMENTS debe ser off en Render durante el piloto (el sandbox concedería planes "
                    "con tarjetas de prueba); prueba los proveedores en local (docs/CONFIGURACION_RENDER_NEON.md §6)")
    if not accounts:
        return errs
    totp, bkey, old = _e("CRYPTO_RADAR_TOTP_KEY"), _e("CRYPTO_RADAR_BACKUP_KEY"), _e("CRYPTO_RADAR_TOTP_KEY_OLD")
    for name, v in (("CRYPTO_RADAR_TOTP_KEY", totp), ("CRYPTO_RADAR_BACKUP_KEY", bkey), ("CRYPTO_RADAR_TOTP_KEY_OLD", old)):
        if v and len(v) < MIN_KEY:
            errs.append(f"{name} debe tener al menos {MIN_KEY} caracteres")
    if totp and bkey and totp == bkey:
        errs.append("CRYPTO_RADAR_TOTP_KEY y CRYPTO_RADAR_BACKUP_KEY son iguales: deben ser claves independientes")
    if totp and old and totp == old:
        errs.append("CRYPTO_RADAR_TOTP_KEY_OLD es igual a la clave actual")
    if on_render():
        if not totp:
            errs.append("Falta CRYPTO_RADAR_TOTP_KEY: los secretos TOTP no se guardan sin cifrar en producción")
        if (_e("CRYPTO_RADAR_ADMIN_TOTP").lower() or "required") == "optional":
            errs.append("CRYPTO_RADAR_ADMIN_TOTP=optional en Render: el TOTP del administrador es obligatorio")
        url = _e("DATABASE_URL")
        if url.startswith(("postgres://", "postgresql://")):
            q = {k.lower(): v[-1] for k, v in parse_qs(urlsplit(url).query).items()}
            if q.get("sslmode", "") in ("", "disable", "allow", "prefer"):
                errs.append("DATABASE_URL sin sslmode=require (o verify-full): la conexión con la base debe ir cifrada")
        if _e("CRYPTO_RADAR_ALLOW_SQLITE") == "1":
            errs.append("CRYPTO_RADAR_ALLOW_SQLITE=1 en Render: las cuentas se perderían en cada reinicio")
    return errs


def startup_warnings() -> list[str]:
    """Variables de un solo uso que no deben quedarse puestas (no impiden arrancar)."""
    w = []
    for k, why in (("CRYPTO_RADAR_ADMIN_RESET", "restablece la contraseña y el TOTP del administrador en cada arranque"),
                   ("CRYPTO_RADAR_ADMIN_TAKEOVER", "solo sirve para un arranque con conflicto de nombre"),
                   ("CRYPTO_RADAR_PLATFORM_ADOPT", "solo sirve para marcar una vez una base 2.1 sin marca")):
        if _e(k) == "1":
            w.append(f"{k}=1 sigue definida: {why}. Bórrala")
    return w
