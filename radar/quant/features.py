"""Series de indicadores precalculadas y causales.

`compute(k)` recibe velas cerradas {t,o,h,l,c,v} (v = volumen en USDT) y devuelve un objeto `F` con listas del
mismo largo. Cada valor F.x[i] depende solo de las velas 0..i: no hay mirada al futuro. Los pivotes se
registran en el índice en que quedan CONFIRMADOS (j + right), nunca antes.
"""
from __future__ import annotations
import math
from .. import indicators as ind


class F(dict):
    """Diccionario de series con acceso por atributo (F.c, F.ema20, ...)."""
    __getattr__ = dict.__getitem__

    @property
    def n(self):
        return len(self["c"])


def _rolling(values, w, fn, exclude_current=False):
    out = [None] * len(values)
    for i in range(len(values)):
        a, b = (i - w, i) if exclude_current else (i - w + 1, i + 1)
        if a < 0:
            continue
        seg = [x for x in values[a:b] if x is not None]
        if len(seg) == w:
            out[i] = fn(seg)
    return out


def _mean(x):
    return sum(x) / len(x)


def _pct_rank(values, w):
    """Percentil (0-1) del valor actual dentro de los últimos w valores (incluido)."""
    out = [None] * len(values)
    for i in range(len(values)):
        if i < w - 1 or values[i] is None:
            continue
        seg = [x for x in values[i - w + 1:i + 1] if x is not None]
        if len(seg) < w * 0.8:
            continue
        cur = values[i]
        out[i] = sum(1 for x in seg if x <= cur) / len(seg)
    return out


def _causal_pivots(h, l, left=3, right=3):
    """Listas por índice de confirmación: piv_hi[i] = precio del último máximo pivote confirmado hasta i."""
    n = len(h)
    hi_conf, lo_conf = [[] for _ in range(n)], [[] for _ in range(n)]
    for j in range(left, n - right):
        if all(h[j] >= h[k] for k in range(j - left, j + right + 1)):
            hi_conf[j + right].append((j, h[j]))
        if all(l[j] <= l[k] for k in range(j - left, j + right + 1)):
            lo_conf[j + right].append((j, l[j]))
    return hi_conf, lo_conf


def compute(k):
    c, h, l, o, v = k["c"], k["h"], k["l"], k["o"], k["v"]
    n = len(c)
    f = F(t=k["t"], o=o, h=h, l=l, c=c, v=v)
    f["ema9"], f["ema20"], f["ema50"], f["ema200"] = ind.ema(c, 9), ind.ema(c, 20), ind.ema(c, 50), ind.ema(c, 200)
    f["rsi"] = ind.rsi(c, 14)
    _, _, f["macd_hist"] = ind.macd(c)
    f["atr"] = ind.atr(h, l, c, 14)
    _, _, _, bbw = ind.bollinger(c, 20, 2.0)
    f["bbw"] = bbw
    f["bbw_rank"] = _pct_rank(bbw, 120)
    f["obv"] = ind.obv(c, v)
    f["vwap20"] = ind.rolling_vwap(h, l, c, v, 20)
    f["vol_avg20_prev"] = _rolling(v, 20, _mean, exclude_current=True)   # promedio de los 20 días ANTERIORES
    f["vol_avg5"] = _rolling(v, 5, _mean)
    f["vol_avg10"] = _rolling(v, 10, _mean)
    f["hh20_prev"] = _rolling(h, 20, max, exclude_current=True)          # resistencia: máximo de los 20 días previos
    f["ll20_prev"] = _rolling(l, 20, min, exclude_current=True)
    f["hh55_prev"] = _rolling(h, 55, max, exclude_current=True)
    f["hh90"] = _rolling(h, 90, max)
    f["ll90"] = _rolling(l, 90, min)
    f["hh30"] = _rolling(h, 30, max)
    f["ll30"] = _rolling(l, 30, min)
    f["piv_hi"], f["piv_lo"] = _causal_pivots(h, l, 3, 3)
    # rendimiento diario y volatilidad realizada de 20 días (para régimen y manipulación)
    ret = [None] + [(c[i] / c[i - 1] - 1) if c[i - 1] else None for i in range(1, n)]
    f["ret"] = ret
    f["rv20"] = _rolling(ret, 20, lambda s: math.sqrt(sum(x * x for x in s) / len(s)))
    return f


def val(series, i, default=None):
    if i < 0 or i >= len(series):
        return default
    x = series[i]
    return default if x is None else x


def chg(f, i, days):
    if i - days < 0 or not f.c[i - days]:
        return None
    return (f.c[i] / f.c[i - days] - 1) * 100


def pivots_until(f, i, kind="hi", lookback=365):
    """Pivotes (índice, precio) confirmados hasta i, con el pivote dentro de los últimos `lookback` días."""
    src = f.piv_hi if kind == "hi" else f.piv_lo
    out = []
    for j in range(max(0, i - lookback - 3), i + 1):
        out.extend(p for p in src[j] if p[0] >= i - lookback)
    return out


def obv_slope(f, i, w=20):
    """Pendiente del OBV en w días normalizada por el volumen del periodo (-1..1 aprox.)."""
    if i - w < 0:
        return 0.0
    vol = sum(f.v[i - w + 1:i + 1]) or 1.0
    return (f.obv[i] - f.obv[i - w]) / vol


def up_down_volume(f, i, w=20):
    up = dn = 0.0
    for j in range(max(1, i - w + 1), i + 1):
        if f.c[j] >= f.c[j - 1]:
            up += f.v[j]
        else:
            dn += f.v[j]
    return up / dn if dn else (2.0 if up else 1.0)


def close_location(f, i):
    """Dónde cerró la vela dentro de su rango: 1 = en el máximo, 0 = en el mínimo."""
    rng = f.h[i] - f.l[i]
    return (f.c[i] - f.l[i]) / rng if rng > 0 else 0.5


def rsi_divergence(f, i, kind="bearish", lookback=45):
    """Divergencia entre los dos últimos pivotes CONFIRMADOS de precio y el RSI en esos puntos."""
    piv = pivots_until(f, i, "hi" if kind == "bearish" else "lo", lookback)
    if len(piv) < 2:
        return False
    (j1, p1), (j2, p2) = piv[-2], piv[-1]
    r1, r2 = f.rsi[j1], f.rsi[j2]
    if r1 is None or r2 is None or i - j2 > 12:
        return False
    if kind == "bearish":
        return p2 > p1 and r2 < r1 - 3
    return p2 < p1 and r2 > r1 + 3
