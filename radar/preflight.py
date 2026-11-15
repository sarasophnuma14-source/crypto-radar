"""Revisión previa a producción (Render + Neon). Solo lee variables de entorno y archivos; no cambia nada.

Con --db también se conecta a DATABASE_URL en modo SOLO LECTURA para comprobar el esquema y el administrador.
Nunca muestra contraseñas, claves ni la URL completa de la base.
Salida: 0 si no hay fallos (puede haber avisos), 1 si hay algún fallo.
"""
from __future__ import annotations
import os
import re
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_WORDS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "DATABASE_URL", "PUBLIC_KEY")


def _e(k):
    return (os.environ.get(k) or "").strip()


def check_env():
    out = []

    def add(level, name, detail):
        out.append((level, name, detail))

    add("ok" if _e("CRYPTO_RADAR_ACCOUNTS") == "1" else "fail", "Modo cuentas",
        "CRYPTO_RADAR_ACCOUNTS=1" if _e("CRYPTO_RADAR_ACCOUNTS") == "1" else "CRYPTO_RADAR_ACCOUNTS no es 1")

    url = _e("DATABASE_URL")
    if not url.startswith(("postgres://", "postgresql://")):
        add("fail", "Base de datos", "DATABASE_URL no es PostgreSQL (el disco de Render se borra en cada despliegue)")
    else:
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        ssl = (q.get("sslmode") or [""])[0]
        host = urllib.parse.urlsplit(url).hostname or ""
        add("ok" if ssl in ("require", "verify-ca", "verify-full") else "fail", "TLS con la base",
            f"sslmode={ssl or '(sin definir)'}")
        if host.endswith(".neon.tech"):
            add("ok" if "-pooler." in host else "warn", "Conexión Neon",
                "usa el endpoint con pooler" if "-pooler." in host else
                "endpoint directo; con varias instancias conviene el endpoint -pooler")
    if _e("CRYPTO_RADAR_ALLOW_SQLITE"):
        add("fail", "SQLite forzado", "CRYPTO_RADAR_ALLOW_SQLITE está definido; quítalo en producción")

    user, pw = _e("CRYPTO_RADAR_ADMIN_USER"), os.environ.get("CRYPTO_RADAR_ADMIN_PASSWORD") or ""
    if not user or not pw.strip():
        add("fail", "Administrador", "faltan CRYPTO_RADAR_ADMIN_USER o CRYPTO_RADAR_ADMIN_PASSWORD")
    elif len(pw) < 12 or user.lower() in pw.lower():
        add("fail", "Administrador", "la contraseña tiene menos de 12 caracteres o contiene el usuario")
    else:
        add("ok", "Administrador", "usuario y contraseña definidos (no se muestran)")
    for k in ("CRYPTO_RADAR_ADMIN_RESET", "CRYPTO_RADAR_ADMIN_TAKEOVER"):
        if _e(k):
            add("fail", "Variables de recuperación", f"{k} sigue definida; quítala después de usarla")
    totp_mode = (_e("CRYPTO_RADAR_ADMIN_TOTP") or "required").lower()
    add("ok" if totp_mode != "optional" else "fail", "TOTP del administrador",
        "obligatorio" if totp_mode != "optional" else "CRYPTO_RADAR_ADMIN_TOTP=optional desactiva el segundo factor")

    mode = (_e("CRYPTO_RADAR_PAYMENTS") or "off").lower()
    if mode not in ("off", "sandbox", "live"):
        add("warn", "Pagos", f"valor desconocido '{mode}': se trata como off")
        mode = "off"
    if mode == "live":
        add("fail", "Pagos", "CRYPTO_RADAR_PAYMENTS=live activa cobros reales; no está autorizado en esta fase")
    elif mode == "sandbox":
        pub = _e("WOMPI_PUBLIC_KEY")
        if pub and not pub.startswith("pub_test_"):
            add("fail", "Pagos", "modo sandbox con una clave pública de Wompi que no es de pruebas")
        else:
            add("warn", "Pagos", "modo sandbox: solo transacciones de prueba (no usar con clientes reales)")
    else:
        add("ok", "Pagos", "desactivados (off)")

    for page in ("privacidad.html", "aviso-de-riesgo.html"):
        txt = (ROOT / "web" / page).read_text(encoding="utf-8")
        pend = len(re.findall(r'class="todo"', txt)) + ("Borrador pendiente" in txt)
        add("fail" if pend else "ok", f"Texto legal {page}",
            f"{pend} marcas pendientes (COMPLETAR / borrador sin revisión legal)" if pend else "completo")

    want = _render_python()
    have = ".".join(map(str, sys.version_info[:3]))
    if want and want.rsplit(".", 1)[0] != have.rsplit(".", 1)[0]:
        add("warn", "Versión de Python", f"render.yaml pide {want}; esta revisión corre con {have}")
    add(*_render_yaml_secrets())
    return out


def _render_python():
    txt = (ROOT / "render.yaml").read_text(encoding="utf-8")
    m = re.search(r"key:\s*PYTHON_VERSION\s*\n\s*value:\s*\"?([\d.]+)", txt)
    return m.group(1) if m else None


def _render_yaml_secrets():
    """Ninguna variable secreta puede llevar un valor escrito en render.yaml (deben ser sync: false)."""
    txt = (ROOT / "render.yaml").read_text(encoding="utf-8")
    bad = [k for k, nxt in re.findall(r"-\s*key:\s*(\S+)\s*\n\s*(\S+):", txt)
           if any(w in k for w in SECRET_WORDS) and nxt != "sync"]
    return ("fail", "render.yaml", "secretos con valor escrito: " + ", ".join(bad)) if bad else \
        ("ok", "render.yaml", "todas las variables secretas son sync: false")


def check_db():
    """Solo lectura: esquema completo y administrador con TOTP activo."""
    from . import backup, db
    out = []
    url = _e("DATABASE_URL")
    if not url:
        return [("fail", "Conexión a la base", "DATABASE_URL vacío")]
    try:
        c, pg = backup._open(url)
    except Exception as e:
        return [("fail", "Conexión a la base", type(e).__name__)]
    try:
        if pg:
            c.execute("SET default_transaction_read_only = on")
        missing = {t: sorted(req - set(backup._columns(c, pg, t))) for t, req in db.REQUIRED.items()}
        missing = {t: m for t, m in missing.items() if m}
        out.append(("fail" if missing else "ok", "Esquema",
                    "faltan " + "; ".join(f"{t}: {', '.join(m)}" for t, m in missing.items()) if missing else
                    "todas las columnas requeridas existen"))
        if not missing:
            ph = "%s" if pg else "?"
            r = c.execute(f"SELECT is_admin, totp_enabled, disabled FROM users WHERE email = {ph}",
                          (_e("CRYPTO_RADAR_ADMIN_USER").lower(),)).fetchone()
            if not r:
                out.append(("warn", "Administrador en la base", "aún no existe; se crea en el primer arranque"))
            elif not r[0] or r[2]:
                out.append(("fail", "Administrador en la base", "existe pero no es administrador activo"))
            else:
                out.append(("ok" if r[1] else "warn", "TOTP del administrador en la base",
                            "activo" if r[1] else "pendiente: actívalo en Cuenta antes de abrir al público"))
    finally:
        c.close()
    return out


def cli(args=None):
    args = sys.argv[2:] if args is None else args
    res = check_env() + (check_db() if "--db" in args else [])
    sym = {"ok": "OK  ", "warn": "AVISO", "fail": "FALLO"}
    for level, name, detail in res:
        print(f"[{sym[level]}] {name}: {detail}")
    fails = sum(1 for r in res if r[0] == "fail")
    warns = sum(1 for r in res if r[0] == "warn")
    print(f"\n{fails} fallos, {warns} avisos. " + ("Listo para producción." if not fails else "NO listo para producción."))
    return 1 if fails else 0
