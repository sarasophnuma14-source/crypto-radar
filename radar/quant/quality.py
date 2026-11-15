"""Control de calidad de datos por activo (0-100). Un activo con calidad < MIN_QUALITY no genera señales."""
from __future__ import annotations
import time

MIN_QUALITY = 60
DAY_MS = 86_400_000


def check(k, interval_ms=DAY_MS, now_ms=None, min_bars=120):
    """Devuelve {"score": 0-100, "issues": [...], "bars": n, "ok": bool}."""
    issues, score = [], 100.0
    t, o, h, l, c, v = k["t"], k["o"], k["h"], k["l"], k["c"], k["v"]
    n = len(c)
    if n < min_bars:
        issues.append(f"Historial corto: {n} velas (mínimo {min_bars})")
        score -= 45 if n < min_bars / 2 else 25
    if n == 0:
        return {"score": 0, "issues": ["Sin datos"], "bars": 0, "ok": False}
    dup = n - len(set(t))
    if dup:
        issues.append(f"{dup} velas duplicadas"); score -= min(30, dup * 5)
    gaps = sum(1 for i in range(1, n) if t[i] - t[i - 1] > interval_ms * 1.5)
    if gaps:
        issues.append(f"{gaps} huecos en la serie"); score -= min(30, gaps * 3)
    bad = sum(1 for i in range(n) if min(o[i], h[i], l[i], c[i]) <= 0 or h[i] < max(o[i], c[i]) - 1e-12
              or l[i] > min(o[i], c[i]) + 1e-12)
    if bad:
        issues.append(f"{bad} velas con OHLC incoherente o precio ≤ 0"); score -= min(40, bad * 10)
    recent = range(max(0, n - 60), n)
    zero = sum(1 for i in recent if v[i] <= 0)
    if zero:
        issues.append(f"{zero} días sin volumen en los últimos 60"); score -= min(30, zero * 3)
    jumps = sum(1 for i in range(max(1, n - 120), n) if c[i - 1] and abs(c[i] / c[i - 1] - 1) > 0.8)
    if jumps:
        issues.append(f"{jumps} saltos diarios de más de 80% (posible error o evento extremo)"); score -= min(20, jumps * 10)
    now_ms = now_ms or int(time.time() * 1000)
    age_bars = (now_ms - (t[-1] + interval_ms)) / interval_ms
    stale = age_bars > 2
    if stale:
        issues.append(f"Datos desactualizados: última vela cerrada hace {age_bars:.0f} periodos"); score -= 40
    score = max(0.0, score)
    # datos viejos nunca se analizan como si fueran actuales (moneda deslistada o fuente caída)
    return {"score": round(score), "issues": issues, "bars": n, "ok": score >= MIN_QUALITY and not stale}
