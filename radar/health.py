"""Salud del servicio: liveness y readiness (hallazgo A-1 de docs/AUDITORIA_INTEGRAL_CRYPTO_RADAR.md).

  * /livez   · liveness: el proceso responde. No toca la base ni nada externo. Nunca falla si el servidor contesta.
  * /healthz · readiness (lo que debe usar Render como Health Check Path): 503 si una dependencia crítica no sirve
               (la base de datos no responde o el planificador lleva más de 5 min sin latir). Un escaneo atrasado
               NO da 503 (no se arregla reiniciando): devuelve 200 con "status": "degradado".
  * /readyz  · alias de /healthz.

La respuesta es pública: no incluye secretos, direcciones, usuarios, versiones de librerías ni trazas. Los errores se
resumen en una palabra ("sin respuesta", "error") y el detalle solo va al registro del servidor.
"""
from __future__ import annotations
import datetime as dt
import threading
import time

_beats = {}                 # nombre del hilo de fondo -> marca de tiempo del último latido
_cache = {"t": 0.0, "v": None}
_cache_lock = threading.Lock()
SCHEDULER_MAX_SILENCE_S = 300   # el planificador late cada 30 s; 5 min sin latir = colgado
SUMMARY_TTL_S = 60              # el resumen del último informe se relee como mucho una vez por minuto
DB_TIMEOUT_S = 3.0


def beat(name):
    _beats[name] = time.time()


def started(name):
    return name in _beats


def _report_summary(storage):
    """Campos públicos del último informe (los mismos que ya publicaba /healthz). Cacheado para no leer el
    documento completo de la base en cada comprobación de salud."""
    with _cache_lock:
        if _cache["v"] is not None and time.time() - _cache["t"] < SUMMARY_TTL_S:
            return _cache["v"]
    rep = storage.read_fields("latest.json", ["generated_at", "at", "sources"])   # sin descargar el informe
    v = {"last_scan": rep.get("generated_at") or rep.get("at"), "sources": rep.get("sources")}
    with _cache_lock:
        _cache.update(t=time.time(), v=v)
    return v


def invalidate():
    with _cache_lock:
        _cache.update(t=0.0, v=None)


def _check_db():
    """SELECT 1 con tiempo límite. Devuelve (ok, ms). Se ejecuta en un hilo aparte para no bloquear la petición si
    la conexión se queda colgada."""
    from . import db
    box = {}

    def run():
        t0 = time.time()
        try:
            r = db.one("SELECT 1 AS ok")
            box["ok"] = bool(r and r.get("ok") == 1)
        except Exception as e:                       # el detalle va al registro, nunca a la respuesta
            print(f"[salud] base de datos: {type(e).__name__}", flush=True)
            box["ok"] = False
        box["ms"] = round((time.time() - t0) * 1000)

    th = threading.Thread(target=run, daemon=True)
    th.start()
    th.join(DB_TIMEOUT_S)
    if th.is_alive():
        return False, None
    return box.get("ok", False), box.get("ms")


def liveness(version):
    return 200, {"ok": True, "version": version}


def readiness(*, storage, scanner_status, scan_every_hours, uses_db, scheduler_expected, version, now=None):
    now = now or time.time()
    checks = {}
    critical_fail = False

    if uses_db:
        ok, ms = _check_db()
        checks["database"] = {"ok": ok, "ms": ms} if ok else {"ok": False, "error": "sin respuesta"}
        critical_fail |= not ok

    if scheduler_expected:
        last = _beats.get("scheduler")
        alive = last is not None and now - last <= SCHEDULER_MAX_SILENCE_S
        # Recién arrancado (aún sin primer latido) no se considera caído durante los primeros 5 min.
        if last is None and now - _START < SCHEDULER_MAX_SILENCE_S:
            alive = True
        checks["scheduler"] = {"ok": alive}
        critical_fail |= not alive

    summary = {"last_scan": None, "sources": None}
    if not (uses_db and not checks["database"]["ok"]):
        try:
            summary = _report_summary(storage)
        except Exception as e:
            print(f"[salud] informe: {type(e).__name__}", flush=True)
    age_h = None
    if summary.get("last_scan"):
        try:
            t = dt.datetime.fromisoformat(str(summary["last_scan"]))
            age_h = round((now - t.timestamp()) / 3600, 2)
        except Exception:
            age_h = None
    stale_after = float(scan_every_hours) * 2 + 1          # dos ciclos perdidos más una hora de margen
    scan_ok = age_h is not None and age_h <= stale_after
    checks["scan"] = {"ok": scan_ok, "age_hours": age_h, "stale_after_hours": stale_after}

    status = "fallo" if critical_fail else ("ok" if scan_ok else "degradado")
    err = scanner_status.get("last_error")
    body = {"ok": not critical_fail, "status": status, "version": version, "checks": checks,
            # campos que ya publicaba /healthz (compatibilidad con la monitorización existente)
            "scanning": scanner_status.get("scanning"), "progress": scanner_status.get("progress"),
            "last_scan": summary.get("last_scan"), "last_error": (str(err)[:300] if err else None),
            "sources": summary.get("sources")}
    return (503 if critical_fail else 200), body


_START = time.time()
