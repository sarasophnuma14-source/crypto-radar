"""EXIT INTELLIGENCE: decide qué hacer con una posición abierta.

Decisiones: MANTENER · PROTEGER GANANCIAS · REDUCIR POSICIÓN · CERRAR POSICIÓN.
Regla clave: una sola señal débil NUNCA cierra. Para reducir se necesitan varias familias de evidencia y para
cerrar, el stop o una combinación fuerte. Las salidas parciales son configurables.
"""
from __future__ import annotations
from .features import val, rsi_divergence, up_down_volume, pivots_until
from . import early

DEFAULT_PARTIALS = {"PROTEGER GANANCIAS": 0.0, "REDUCIR POSICIÓN": 0.33, "CERRAR POSICIÓN": 1.0}
TRAIL_ATR = 3.0


def signals(f, i, regime=None):
    """Familias de señales de salida presentes en i: [(familia, fuerza 1|2, texto)]."""
    out = []
    r, r5 = val(f.rsi, i), val(f.rsi, i - 5)
    if r is not None and r5 is not None and r5 >= 70 and r < 60:
        out.append(("momentum", 1, f"RSI cae de {r5:.0f} a {r:.0f}"))
    mh = [val(f.macd_hist, j) for j in range(i - 3, i + 1)]
    if None not in mh and mh[0] > mh[1] > mh[2] > mh[3]:
        out.append(("momentum", 1, "MACD perdiendo fuerza 3 días seguidos"))
    if rsi_divergence(f, i, "bearish"):
        out.append(("divergence", 2, "Divergencia bajista del RSI"))
    if up_down_volume(f, i, 10) < 0.7:
        out.append(("volume", 1, "Volumen predominante en días bajistas"))
    res = val(f.hh55_prev, i)
    rng = f.h[i] - f.l[i]
    if res and rng > 0 and f.h[i] >= res * 0.99 and (f.h[i] - max(f.o[i], f.c[i])) / rng > 0.55:
        out.append(("rejection", 1, "Rechazo en resistencia (mecha superior larga)"))
    lows = pivots_until(f, i - 1, "lo", 60)
    if lows and f.c[i] < lows[-1][1]:
        out.append(("structure", 2, f"Cierre bajo el último mínimo de estructura ({lows[-1][1]:.6g})"))
    vw, vw1 = val(f.vwap20, i), val(f.vwap20, i - 1)
    if vw and vw1 and f.c[i] < vw and f.c[i - 1] >= vw1:
        out.append(("vwap", 1, "Pierde el VWAP de 20 días"))
    e9, e20, e9p, e20p = val(f.ema9, i), val(f.ema20, i), val(f.ema9, i - 1), val(f.ema20, i - 1)
    if None not in (e9, e20, e9p, e20p) and e9 < e20 and e9p >= e20p:
        out.append(("ema", 1, "Cruce bajista EMA 9 / EMA 20"))
    ext, why = early.overextension(f, i)
    if ext:
        out.append(("overextension", 1, "Sobreextensión: " + ", ".join(why)))
    dist, dwhy = early.distribution(f, i)
    if dist:
        out.append(("distribution", 2, "Distribución: " + ", ".join(dwhy)))
    if regime in ("BEARISH", "CAPITULATION"):
        out.append(("market", 1, f"Mercado general en régimen {regime}"))
    return out


def decide(f, i, position, regime=None, partials=None):
    """position: {"entry", "stop", "highest_close"?, "hits"?}. Devuelve la decisión y el stop sugerido."""
    partials = partials or DEFAULT_PARTIALS
    p, a = f.c[i], val(f.atr, i) or 0
    entry, stop = position["entry"], position["stop"]
    R = entry - stop if entry > stop else None
    hi_close = max(position.get("highest_close") or entry, p)
    trail = hi_close - TRAIL_ATR * a if a else None
    sig = signals(f, i, regime)
    fams = {s[0] for s in sig}
    strength = sum(s[1] for s in sig)
    reasons = [s[2] for s in sig]
    gain_R = (p - entry) / R if R else 0
    if p <= stop:
        decision, why = "CERRAR POSICIÓN", ["Cierre en o bajo el stop"]
    elif trail and p < trail and gain_R > 1 and len(fams) >= 1:
        decision, why = "CERRAR POSICIÓN", [f"Trailing stop de {TRAIL_ATR:g} ATR perforado ({trail:.6g})"] + reasons
    elif ("structure" in fams and len(fams) >= 3) or len(fams) >= 4:
        decision, why = "CERRAR POSICIÓN", reasons
    elif len(fams) >= 3 or "distribution" in fams or ("overextension" in fams and len(fams) >= 2):
        decision, why = "REDUCIR POSICIÓN", reasons
    elif strength >= 2 or gain_R >= 2:
        decision, why = "PROTEGER GANANCIAS", reasons or [f"Ganancia de {gain_R:.1f} R: subir el stop"]
    else:
        decision, why = "MANTENER", reasons or ["Sin señales de salida relevantes"]
    # stop sugerido: nunca baja; en ganancia sube a la entrada y luego sigue al trailing
    new_stop = stop
    if decision in ("PROTEGER GANANCIAS", "REDUCIR POSICIÓN") and gain_R >= 1:
        new_stop = max(stop, entry)
    if trail and gain_R >= 2:
        new_stop = max(new_stop, trail)
    return {"decision": decision, "reasons": why, "sell_fraction": partials.get(decision, 0.0),
            "suggested_stop": new_stop, "trailing_stop": trail, "gain_R": round(gain_R, 2),
            "signal_families": sorted(fams), "single_weak_signal": len(sig) == 1 and sig[0][1] == 1}
