"""Indicadores causales: el valor en la fecha D solo usa velas cerradas hasta D."""
import numpy as np
import pandas as pd


def compute(P, btc="BTC"):
    o, h, l, c, v = (P[k] for k in "ohlcv")
    F = {}
    prev = c.shift(1)
    tr = np.maximum(h - l, np.maximum((h - prev).abs(), (l - prev).abs()))
    F["atr"] = tr.rolling(14, min_periods=14).mean()
    F["adv30"] = v.rolling(30, min_periods=30).mean()
    F["bars"] = c.notna().cumsum()
    lr = np.log(c / prev)
    F["vol28"] = lr.rolling(28, min_periods=20).std() * np.sqrt(365)
    for L in (7, 28, 56, 84):
        F[f"ret{L}"] = c / c.shift(L) - 1
    for L in (28, 56, 84, 200):
        F[f"sma{L}"] = c.rolling(L, min_periods=L).mean()
    for N in (20, 55, 90, 365):
        F[f"hi{N}"] = h.rolling(N, min_periods=N).max().shift(1)
    for M in (10, 27, 45):
        F[f"lo{M}"] = l.rolling(M, min_periods=M).min().shift(1)
    sd20 = c.rolling(20, min_periods=20).std(); m20 = c.rolling(20, min_periods=20).mean()
    bbw = 4 * sd20 / m20
    F["bbw_pct"] = bbw.rolling(120, min_periods=120).rank(pct=True)
    F["vratio"] = v.rolling(10, min_periods=10).mean() / v.rolling(60, min_periods=60).mean()
    F["rs28"] = F["ret28"].sub(F["ret28"][btc], axis=0)
    F["dist_hi365"] = c / F["hi365"]
    # semanal (semana cerrada el domingo; disponible desde ese cierre)
    wc = c.resample("W-SUN").last()
    for W in (10, 20):
        F[f"wk_above{W}"] = (wc > wc.rolling(W, min_periods=W).mean()).astype(float).where(wc.notna()) \
            .reindex(c.index, method="ffill")
    F["btc_wk20"] = F["wk_above20"][btc]
    F["btc_bear"] = (c[btc] < F["sma200"][btc])
    F["btc_ret7"] = F["ret7"][btc]
    return F


def universe(F, size=150, min_adv=2e6, min_bars=120):
    adv = F["adv30"].where((F["bars"] >= min_bars) & (F["adv30"] >= min_adv))
    rk = adv.rank(axis=1, ascending=False, method="first")
    return rk <= size
