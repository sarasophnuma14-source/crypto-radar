"""Plan de operación: zona de entrada, stop (invalidación) y objetivos TP1-TP3 según la fase.

Stop mínimo de 1,5 ATR: la auditoría mostró que stops de ~1 ATR se tocaban antes de TP1 en 2 de cada 3
operaciones. Los objetivos usan resistencias confirmadas (pivotes causales) y múltiplos de R.
"""
from __future__ import annotations
from .features import val, pivots_until

MIN_STOP_ATR = 1.5


def _cluster(levels, tol=0.02):
    out = []
    for lv in sorted(levels):
        if not out or lv > out[-1] * (1 + tol):
            out.append(lv)
    return out


def build(f, i, phase, settings=None):
    s = settings or {}
    p = f.c[i]
    a = val(f.atr, i) or p * 0.05
    e20, vw = val(f.ema20, i), val(f.vwap20, i)
    res = val(f.hh20_prev, i) or max(f.h[max(0, i - 20):i + 1])
    lows = [x[1] for x in pivots_until(f, i, "lo", 120)]
    highs = [x[1] for x in pivots_until(f, i, "hi", 365)]
    trigger = None
    if phase == "BREAKOUT":
        # comprar el retest del nivel roto, sin perseguir más de 0,5 ATR por encima
        lo_z = max(res, p - 1.0 * a) if res < p else p - 0.5 * a
        hi_z = min(p, lo_z + 0.75 * a)
        base = min(res, lo_z) - 0.5 * a
    elif phase in ("PRE-EXPLOSION", "ACCUMULATION"):
        supports = [x for x in (e20, vw) + tuple(lows) if x and p - 2.5 * a < x < p]
        sup = max(supports) if supports else p - 1.0 * a
        lo_z, hi_z = sup, min(p, sup + 0.75 * a)
        trigger = res * 1.003 if res and res > p else None   # entrada alternativa: confirmar la ruptura
        rng_lo = val(f.ll20_prev, i) or (p - 2 * a)
        base = min(rng_lo, sup - 0.5 * a) - 0.25 * a
    else:   # MOMENTUM y otras: retroceso a la EMA 20
        sup = e20 if e20 and e20 < p else p - 1.0 * a
        lo_z, hi_z = sup, min(p, sup + 0.5 * a)
        base = sup - 1.0 * a
    entry = (lo_z + hi_z) / 2
    swing = [x for x in lows if x < entry]
    stop = min(base, (max(swing) - 0.25 * a) if swing else base)
    stop = min(stop, entry - MIN_STOP_ATR * a)
    if stop <= 0:
        stop = entry * 0.8
    R = entry - stop
    targets = _cluster([x for x in highs if x > entry + 0.8 * R])
    measured = (res - (val(f.ll20_prev, i) or res)) if phase in ("BREAKOUT", "PRE-EXPLOSION") else 0

    def nxt(minv):
        return next((x for x in targets if x >= minv), None)
    tp1 = nxt(entry + 1.5 * R) or entry + 1.5 * R
    tp2 = nxt(max(tp1 * 1.02, entry + 3 * R)) or max(entry + 3 * R, (res + measured) if measured > 0 else 0)
    tp3 = nxt(max(tp2 * 1.03, entry + 5 * R)) or max(entry + 5 * R, tp2 + (tp2 - entry) * 0.5)
    rr = (tp2 - entry) / R if R > 0 else 0
    cap = float(s.get("capital_usd", 1000))
    risk_usd = cap * float(s.get("risk_per_trade_pct", 1)) / 100
    return {"entry_low": lo_z, "entry_high": hi_z, "entry": entry, "trigger_breakout": trigger,
            "stop": stop, "invalidation": stop, "tp1": tp1, "tp2": tp2, "tp3": tp3, "R": R,
            "risk_pct": R / entry * 100 if entry else None, "rr": rr, "rr_tp3": (tp3 - entry) / R if R > 0 else 0,
            "return_tp2_pct": (tp2 / entry - 1) * 100, "return_tp3_pct": (tp3 / entry - 1) * 100,
            "risk_usd": risk_usd, "position_usd": min(risk_usd / R * entry, cap * float(s.get("max_position_pct", 20)) / 100) if R > 0 else 0,
            "partials": "TP1: vender 33% y subir el stop a la entrada · TP2: vender 33% · TP3 o trailing de 3 ATR: el resto",
            # compatibilidad con el panel anterior
            "entry_ideal": lo_z, "entry_zone_high": hi_z, "entry_confirmation": trigger or hi_z, "entry_aggressive": p}
