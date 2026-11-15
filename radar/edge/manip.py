"""Riesgo de manipulación 0-100 con OHLCV diario. Es una sospecha algorítmica, nunca una prueba.
Libro de órdenes histórico y concentración de holders: N/D (no hay fuente histórica verificable)."""
import numpy as np


def score(P, F):
    o, h, l, c, v = (P[k] for k in "ohlcv")
    med60 = v.rolling(60, min_periods=30).median()
    vr = v / med60
    s = (np.clip((vr.rolling(10, min_periods=1).max() - 3) / 7, 0, 1) * 30).fillna(0)   # volumen anormal (últimos 10 días)
    vertical = ((F["ret7"] > 0.5) & (F["adv30"] < 10e6)).astype(float) * 25          # subida vertical con poca liquidez
    spike_up = ((vr >= 5) & (c / c.shift(1) - 1 > 0.15))
    hi10 = h.rolling(10, min_periods=1).max()
    reversal = (spike_up.rolling(10, min_periods=1).max() > 0) & (c / hi10 < 0.7)
    rng = (h - l).replace(0, np.nan)
    wick = ((h - np.maximum(o, c)) / rng).rolling(10, min_periods=5).mean()
    thin_range = ((h - l) > 3 * F["atr"]) & (v < med60)
    tot = s + vertical + reversal.astype(float) * 25 + (wick > 0.5).astype(float) * 10 + thin_range.astype(float) * 10
    return tot.clip(0, 100)
