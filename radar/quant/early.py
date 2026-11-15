"""EARLY ENTRY DETECTOR: puntuación 0-100 de una moneda que podría estar preparando un movimiento alcista.

Siete familias de evidencia. Cada indicador pertenece a UNA sola familia para no contar dos veces el mismo
fenómeno (p. ej. el OBV solo cuenta en "volumen", la ruptura solo en "confirmación"):

  estructura (20)   compresión de volatilidad, mínimos crecientes, posición en el rango, cercanía a la resistencia
  volumen (20)      volumen relativo, aumento progresivo, OBV, volumen alcista vs bajista, precio sobre VWAP
  tendencia (15)    alineación EMA 9/20/50, pendiente de EMA50, posición frente a EMA200
  momentum (15)     RSI en zona de impulso sano, histograma MACD creciente, cambio a 10 días
  fuerza rel. (10)  rendimiento frente a BTC a 7 y 30 días
  liquidez (10)     volumen diario medio en USD; spread y profundidad del libro cuando se conocen
  ruptura (10)      cierre sobre la resistencia de 20/55 días con volumen y buen cierre de vela

Los pesos son configurables (config.EARLY_WEIGHTS) y se validan con radar/quant/validate.py.
"""
from __future__ import annotations
import math
from .features import val, chg, obv_slope, up_down_volume, close_location, rsi_divergence

DEFAULT_WEIGHTS = {"structure": 20, "volume": 20, "trend": 15, "momentum": 15,
                   "relative_strength": 10, "liquidity": 10, "breakout": 10}
FAMILY_LABEL = {"structure": "Acumulación y estructura", "volume": "Volumen", "trend": "Tendencia",
                "momentum": "Momentum", "relative_strength": "Fuerza relativa vs BTC", "liquidity": "Liquidez",
                "breakout": "Confirmación de ruptura"}
PHASES = ("PRE-EXPLOSION", "ACCUMULATION", "BREAKOUT", "MOMENTUM", "OVEREXTENDED", "DISTRIBUTION", "REJECTED")
PHASE_LABEL = {"PRE-EXPLOSION": "Pre-explosión", "ACCUMULATION": "Acumulación", "BREAKOUT": "Ruptura",
               "MOMENTUM": "Momentum", "OVEREXTENDED": "Sobreextendida", "DISTRIBUTION": "Distribución",
               "REJECTED": "Descartada"}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _lin(x, a, b):
    """0 en a, 1 en b (lineal, recortado)."""
    if x is None:
        return 0.0
    return _clamp((x - a) / (b - a)) if b != a else 0.0


# ------------------------------------------------------------------ familias
def structure(f, i):
    ev, s = [], 0.0
    rank = val(f.bbw_rank, i)
    if rank is not None:
        part = _lin(0.5 - rank, 0.0, 0.4)                   # percentil ≤ 10 % → 1
        s += 0.30 * part
        if rank <= 0.2:
            ev.append(f"Volatilidad comprimida (ancho de Bollinger en el percentil {rank * 100:.0f} de 120 días)")
    if i >= 30:
        m1, m2, m3 = min(f.l[i - 29:i - 19]), min(f.l[i - 19:i - 9]), min(f.l[i - 9:i + 1])
        if m1 < m2 < m3:
            s += 0.25; ev.append("Mínimos crecientes en los últimos 30 días")
        elif m2 <= m3 and m1 <= m3:
            s += 0.10
    hh, ll = val(f.hh90, i), val(f.ll90, i)
    if hh and ll and hh > ll:
        pos = (f.c[i] - ll) / (hh - ll)
        # la mejor zona para una entrada temprana: mitad superior del rango sin estar ya en el máximo
        s += 0.20 * (1 - abs(pos - 0.7) / 0.7) if pos <= 1 else 0
    res, a = val(f.hh20_prev, i), val(f.atr, i)
    if res and a:
        dist_atr = (res - f.c[i]) / a
        if 0 <= dist_atr <= 1.5:
            s += 0.25; ev.append(f"A {dist_atr:.1f} ATR de la resistencia de 20 días ({res:.6g})")
        elif -0.5 <= dist_atr < 0:
            s += 0.15
    return _clamp(s), ev


def volume(f, i):
    ev, s = [], 0.0
    avg = val(f.vol_avg20_prev, i)
    rel = f.v[i] / avg if avg else None
    if rel is not None:
        if 1.3 <= rel <= 4:
            s += 0.25; ev.append(f"Volumen {rel:.1f}× su promedio de 20 días")
        elif 4 < rel <= 8:
            s += 0.12; ev.append(f"Volumen muy alto ({rel:.1f}×): revisar riesgo de manipulación")
        elif 1.0 <= rel < 1.3:
            s += 0.08
    a5, a10, a20 = val(f.vol_avg5, i), val(f.vol_avg10, i), avg
    if a5 and a10 and a20 and a5 > a10 > a20:
        s += 0.20; ev.append("Volumen en aumento progresivo (5 > 10 > 20 días)")
    ob = obv_slope(f, i, 20)
    s += 0.25 * _lin(ob, 0.0, 0.25)
    if ob > 0.08:
        ev.append("OBV en ascenso: entra capital")
    udr = up_down_volume(f, i, 20)
    s += 0.15 * _lin(udr, 1.0, 1.8)
    if udr >= 1.3:
        ev.append(f"Volumen de días alcistas {udr:.1f}× el de días bajistas")
    vw = val(f.vwap20, i)
    if vw and f.c[i] > vw:
        s += 0.15
    return _clamp(s), ev


def trend(f, i):
    ev, s = [], 0.0
    e9, e20, e50, e200 = val(f.ema9, i), val(f.ema20, i), val(f.ema50, i), val(f.ema200, i)
    p = f.c[i]
    if e9 and e20 and e50:
        if e9 > e20 > e50:
            s += 0.35; ev.append("EMA 9 > 20 > 50 alineadas al alza")
        elif e9 > e20:
            s += 0.15
    if e50 and p > e50:
        s += 0.20
    if e50 and i >= 10 and f.ema50[i - 10]:
        sl = (e50 / f.ema50[i - 10] - 1) * 100
        s += 0.20 * _lin(sl, -1.0, 4.0)
    if e200:
        if p > e200:
            s += 0.25; ev.append("Sobre la EMA 200")
        elif p > e200 * 0.9:
            s += 0.10
    else:
        s += 0.10                                            # historial corto: sin EMA200, neutro
    return _clamp(s), ev


def momentum(f, i):
    ev, s = [], 0.0
    r = val(f.rsi, i)
    if r is not None:
        if 52 <= r <= 68:
            s += 0.40; ev.append(f"RSI en zona de impulso sano ({r:.0f})")
        elif 45 <= r < 52 or 68 < r <= 74:
            s += 0.20
        if i >= 5 and f.rsi[i - 5] is not None and r > f.rsi[i - 5] + 3:
            s += 0.10
    mh = [val(f.macd_hist, j) for j in range(i - 2, i + 1)]
    if None not in mh:
        if mh[2] > 0 and mh[2] > mh[1]:
            s += 0.30; ev.append("MACD positivo y acelerando")
        elif mh[2] > mh[1] > mh[0]:
            s += 0.20; ev.append("MACD mejorando")
    roc = chg(f, i, 10)
    if roc is not None:
        s += 0.20 * _lin(roc, 0, 15) * (1 if roc <= 35 else 0.3)
    return _clamp(s), ev


def relative_strength(f, i, btc_f=None, btc_i=None):
    if btc_f is None or btc_i is None:
        return None, ["Sin referencia de BTC"]
    ev, s, parts = [], 0.0, 0
    for days, w in ((7, 0.4), (30, 0.6)):
        a, b = chg(f, i, days), chg(btc_f, btc_i, days)
        if a is None or b is None:
            continue
        d = a - b
        s += w * _lin(d, -5, 15); parts += 1
        if days == 30 and d > 5:
            ev.append(f"Supera a BTC por {d:.0f} puntos en 30 días")
    return (_clamp(s) if parts else None), ev


def liquidity(f, i, book=None):
    """book (solo en vivo): {"spread_pct", "depth_usd_2pct"}; sin libro se usa el volumen medio."""
    ev = []
    avg = val(f.vol_avg20_prev, i) or (f.v[i] if f.v else 0)
    # escala logarítmica: 1 M USD/día → 0; 100 M → 1
    s = _lin(math.log10(avg) if avg > 0 else 0, 6.0, 8.0)
    if avg:
        ev.append(f"Volumen medio diario ${avg / 1e6:,.1f} M")
    if book:
        sp, depth = book.get("spread_pct"), book.get("depth_usd_2pct")
        if sp is not None:
            s = 0.6 * s + 0.2 * _lin(0.5 - sp, 0, 0.45)        # spread ≤ 0,05 % → 1; ≥ 0,5 % → 0
            ev.append(f"Spread {sp:.3f}%")
        if depth is not None:
            s += 0.2 * _lin(math.log10(depth) if depth > 0 else 0, 4.5, 6.5)
            ev.append(f"Profundidad ±2%: ${depth / 1e3:,.0f} mil")
    return _clamp(s), ev


def breakout(f, i):
    ev = []
    best = 0.0
    for back in (0, 1, 2):                                   # ruptura de hoy o de los 2 días anteriores
        j = i - back
        res20, res55 = val(f.hh20_prev, j), val(f.hh55_prev, j)
        avg = val(f.vol_avg20_prev, j)
        if not res20 or not avg:
            continue
        if f.c[j] > res20:
            rel = f.v[j] / avg
            s = 0.45 + (0.2 if res55 and f.c[j] > res55 else 0)
            s += 0.25 * _lin(rel, 1.2, 2.5)
            s += 0.10 * _lin(close_location(f, j), 0.5, 0.9)
            if back and f.c[i] < res20:                     # volvió a meterse bajo el nivel: no confirma
                s *= 0.3
            s *= (1.0, 0.9, 0.8)[back]
            if s > best:
                best = s
                ev = [f"Cierre sobre la resistencia de {'55' if res55 and f.c[j] > res55 else '20'} días "
                      f"({res20:.6g}) con volumen {rel:.1f}×" + (f", hace {back} día(s)" if back else "")]
    return _clamp(best), ev


# ------------------------------------------------------------------ extensión y distribución
def overextension(f, i):
    """Devuelve (sobreextendida: bool, motivos). No se priorizan monedas que ya subieron demasiado."""
    why = []
    e20, a, r = val(f.ema20, i), val(f.atr, i), val(f.rsi, i)
    if e20 and a and (f.c[i] - e20) / a >= 3.0:
        why.append(f"{(f.c[i] - e20) / a:.1f} ATR sobre la EMA 20")
    if r is not None and r >= 78:
        why.append(f"RSI {r:.0f}")
    c7, c30 = chg(f, i, 7), chg(f, i, 30)
    if c7 is not None and c7 >= 40:
        why.append(f"+{c7:.0f}% en 7 días")
    if c30 is not None and c30 >= 100:
        why.append(f"+{c30:.0f}% en 30 días")
    return bool(why), why


def distribution(f, i):
    """Evidencia de distribución cerca de máximos (se requieren al menos 2 señales)."""
    why = []
    hh, ll = val(f.hh90, i), val(f.ll90, i)
    pos = (f.c[i] - ll) / (hh - ll) if hh and ll and hh > ll else 0.5
    if pos < 0.65:
        return False, why
    if rsi_divergence(f, i, "bearish"):
        why.append("Divergencia bajista del RSI")
    if up_down_volume(f, i, 15) < 0.75:
        why.append("Más volumen en días bajistas que alcistas")
    res = val(f.hh20_prev, i)
    if res and max(f.h[i - 4:i + 1]) > res and f.c[i] < res * 0.98:
        why.append("Ruptura fallida en los últimos 5 días")
    if obv_slope(f, i, 15) < -0.05 and (chg(f, i, 15) or 0) > 0:
        why.append("OBV cae mientras el precio sube")
    upper_wicks = sum(1 for j in range(i - 4, i + 1) if f.h[j] > f.l[j] and (f.h[j] - max(f.o[j], f.c[j])) / (f.h[j] - f.l[j]) > 0.5)
    if upper_wicks >= 3:
        why.append("Mechas superiores largas repetidas (rechazo)")
    return len(why) >= 2, why


# ------------------------------------------------------------------ puntuación y fase
def evaluate(f, i, btc_f=None, btc_i=None, weights=None, book=None, quality=None):
    """Puntuación 0-100, fase y evidencia en el índice i (vela cerrada)."""
    weights = weights or DEFAULT_WEIGHTS
    fam = {}
    for name, fn in (("structure", structure), ("volume", volume), ("trend", trend), ("momentum", momentum),
                     ("breakout", breakout)):
        fam[name] = fn(f, i)
    fam["relative_strength"] = relative_strength(f, i, btc_f, btc_i)
    fam["liquidity"] = liquidity(f, i, book)
    avail = {k: v for k, v in fam.items() if v[0] is not None}
    wsum = sum(weights[k] for k in avail)
    raw = sum(weights[k] * avail[k][0] for k in avail) / wsum * 100 if wsum else 0.0
    ext, ext_why = overextension(f, i)
    dist, dist_why = distribution(f, i)
    score = raw * (0.6 if ext else 1.0) * (0.7 if dist else 1.0)
    families = {k: {"label": FAMILY_LABEL[k], "weight": weights[k],
                    "score": None if v[0] is None else round(v[0], 3), "evidence": v[1]} for k, v in fam.items()}
    S = {k: (v[0] or 0.0) for k, v in fam.items()}
    phase, why = classify(f, i, S, ext, ext_why, dist, dist_why, quality)
    if phase == "REJECTED":
        score = min(score, 40.0)
    return {"score": round(score, 1), "raw_score": round(raw, 1), "phase": phase, "phase_label": PHASE_LABEL[phase],
            "phase_reasons": why, "families": families, "coverage": round(wsum / sum(weights.values()) * 100)}


def classify(f, i, S, ext, ext_why, dist, dist_why, quality=None):
    if quality is not None and not quality.get("ok", True):
        return "REJECTED", ["Calidad de datos insuficiente: " + "; ".join(quality.get("issues", [])[:2])]
    if S["liquidity"] < 0.15:
        return "REJECTED", ["Liquidez insuficiente"]
    if ext:
        return "OVEREXTENDED", ext_why
    if dist:
        return "DISTRIBUTION", dist_why
    e50, e200 = val(f.ema50, i), val(f.ema200, i)
    downtrend = e200 and e50 and f.c[i] < e50 < e200
    if S["breakout"] >= 0.55 and S["volume"] >= 0.35:
        return "BREAKOUT", ["Ruptura confirmada con volumen"]
    flat = abs(chg(f, i, 30) or 0) <= 25
    rank = val(f.bbw_rank, i)
    res, a = val(f.hh20_prev, i), val(f.atr, i)
    near_res = bool(res and a and 0 <= (res - f.c[i]) / a <= 1.5)
    rising_vol = (val(f.vol_avg5, i) or 0) > (val(f.vol_avg20_prev, i) or 1e18) * 1.15
    # Acumulación real exige DEMANDA (volumen/OBV), no solo un precio lateral
    accumulation = flat and not downtrend and S["structure"] >= 0.45 and S["volume"] >= 0.45
    if accumulation and rank is not None and rank <= 0.25 and near_res and rising_vol:
        return "PRE-EXPLOSION", ["Compresión de volatilidad junto a la resistencia con volumen creciente"]
    if accumulation:
        return "ACCUMULATION", ["Rango con mínimos firmes y entrada de volumen"]
    if S["trend"] >= 0.6 and S["momentum"] >= 0.45 and not downtrend:
        return "MOMENTUM", ["Tendencia alcista en desarrollo"]
    if downtrend:
        return "REJECTED", ["Tendencia bajista (precio bajo EMA50 < EMA200)"]
    return "REJECTED", ["Sin evidencia suficiente de acumulación, ruptura o tendencia"]
