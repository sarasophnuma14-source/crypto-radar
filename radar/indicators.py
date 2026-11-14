"""Indicadores técnicos en Python puro (sin dependencias)."""
from __future__ import annotations
import math


def ema(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    k = 2 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def sma(values, period):
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= period:
            s -= values[i - period]
        if i >= period - 1:
            out[i] = s / period
    return out


def rsi(closes, period=14):
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / period, losses / period
    out[period] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (period - 1) + max(d, 0)) / period
        al = (al * (period - 1) + max(-d, 0)) / period
        out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def macd(closes, fast=12, slow=26, signal=9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [None if a is None or b is None else a - b for a, b in zip(ef, es)]
    start = next((i for i, v in enumerate(line) if v is not None), None)
    sig = [None] * len(closes)
    if start is not None:
        s = ema(line[start:], signal)
        sig[start:] = s
    hist = [None if a is None or b is None else a - b for a, b in zip(line, sig)]
    return line, sig, hist


def atr(highs, lows, closes, period=14):
    trs = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        trs.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    out = [None] * len(closes)
    if len(trs) < period:
        return out
    prev = sum(trs[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(trs)):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def bollinger(closes, period=20, mult=2.0):
    mid = sma(closes, period)
    up, lo, width = [None] * len(closes), [None] * len(closes), [None] * len(closes)
    for i in range(period - 1, len(closes)):
        w = closes[i - period + 1:i + 1]
        m = mid[i]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / period)
        up[i], lo[i] = m + mult * sd, m - mult * sd
        width[i] = (up[i] - lo[i]) / m if m else None
    return mid, up, lo, width


def obv(closes, volumes):
    out = [0.0]
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out.append(out[-1] + volumes[i])
        elif closes[i] < closes[i - 1]:
            out.append(out[-1] - volumes[i])
        else:
            out.append(out[-1])
    return out


def rolling_vwap(highs, lows, closes, volumes, period=20):
    out = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        pv = vv = 0.0
        for j in range(i - period + 1, i + 1):
            tp = (highs[j] + lows[j] + closes[j]) / 3
            pv += tp * volumes[j]
            vv += volumes[j]
        out[i] = pv / vv if vv else None
    return out


def slope(values, n):
    """Pendiente relativa (%) de una regresión lineal sobre los últimos n valores."""
    w = [v for v in values[-n:] if v is not None]
    if len(w) < 3:
        return 0.0
    k = len(w)
    xm = (k - 1) / 2
    ym = sum(w) / k
    num = sum((i - xm) * (y - ym) for i, y in enumerate(w))
    den = sum((i - xm) ** 2 for i in range(k))
    b = num / den if den else 0
    scale = abs(ym) if ym else (max(abs(x) for x in w) or 1)
    return b * k / scale * 100


def pivots(highs, lows, left=3, right=3):
    """Devuelve (indices de máximos pivote, indices de mínimos pivote)."""
    ph, pl = [], []
    for i in range(left, len(highs) - right):
        h = highs[i]
        if all(h >= highs[j] for j in range(i - left, i + right + 1)):
            ph.append(i)
        lo = lows[i]
        if all(lo <= lows[j] for j in range(i - left, i + right + 1)):
            pl.append(i)
    return ph, pl


def divergence(closes, osc, lookback=40, kind="bearish"):
    """Detecta divergencias simples entre precio y un oscilador usando pivotes."""
    n = len(closes)
    if n < lookback + 5:
        return False
    seg = range(n - lookback, n)
    ph, pl = pivots(closes[n - lookback:], closes[n - lookback:], 2, 2)
    off = n - lookback
    if kind == "bearish":
        pts = [off + i for i in ph][-2:]
        if len(pts) == 2 and osc[pts[0]] is not None and osc[pts[1]] is not None:
            return closes[pts[1]] > closes[pts[0]] and osc[pts[1]] < osc[pts[0]] - 2 and pts[1] >= n - 12
    else:
        pts = [off + i for i in pl][-2:]
        if len(pts) == 2 and osc[pts[0]] is not None and osc[pts[1]] is not None:
            return closes[pts[1]] < closes[pts[0]] and osc[pts[1]] > osc[pts[0]] + 2 and pts[1] >= n - 12
    return False


def last(values, default=None):
    for v in reversed(values):
        if v is not None:
            return v
    return default
