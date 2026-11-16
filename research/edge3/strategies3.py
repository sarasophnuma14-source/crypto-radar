"""Las 35 configuraciones pre-registradas (PREREGISTRO_V3 §3). Cada función devuelve pesos objetivo (fecha × activo)
calculados SOLO con datos hasta el cierre de esa fecha; filas NaN = no rebalancear."""
from __future__ import annotations
import numpy as np
import pandas as pd

LOOKS_DC = (5, 10, 20, 30, 60, 90, 150, 250, 360)


class Ctx:
    def __init__(self, P, fund=None):
        self.P = P; self.C = P["c"]; self.V = P["v"]
        self.R = self.C.pct_change(fill_method=None)
        self.adv = self.V.rolling(30, min_periods=20).mean()
        self.hist = self.C.notna().cumsum()
        self.vol = {k: self.R.rolling(k, min_periods=int(k * 0.8)).std() * np.sqrt(365) for k in (7, 30, 60, 90)}
        b = self.C["BTC"]
        self.btc_up = (b > b.rolling(200, min_periods=200).mean())
        bv = self.vol[30]["BTC"]
        self.btc_vol_low = bv <= bv.expanding(365).median()
        self.fund = fund                      # dict: 'f' funding diario (fecha × activo), 'po', 'pc'
        self.mondays = self.C.index[self.C.index.dayofweek == 0]

    def universe(self, top, min_adv=5e6, min_hist=180, only=None):
        ok = (self.adv >= min_adv) & (self.hist >= min_hist) & self.C.notna()
        if only is not None:
            ok = ok & pd.DataFrame({c: c in only for c in ok.columns}, index=[0]).reindex(ok.index, method="ffill").fillna(False)
        rank = self.adv.where(ok).rank(axis=1, ascending=False)
        return rank <= top


def _sched(W, days):
    out = pd.DataFrame(np.nan, index=W.index, columns=W.columns)
    d = W.index.intersection(days)
    out.loc[d] = W.loc[d].fillna(0.0).values
    return out


def _riskpar(mask, vol, cap=0.20):
    iv = (1.0 / vol).where(mask & (vol > 0))
    w = iv.div(iv.sum(axis=1), axis=0)
    return w.clip(upper=cap).fillna(0.0)


def tsmom(x: Ctx, L, btc_filter, top=30, min_adv=5e6, exclude=None):
    U = x.universe(top, min_adv)
    sig = U & (x.C / x.C.shift(L) - 1 > 0)
    if exclude is not None:
        sig = sig & ~exclude
    W = _riskpar(sig, x.vol[60])
    if btc_filter:
        W = W.mul(x.btc_up.astype(float), axis=0)
    return _sched(W, x.mondays)


def xsmom(x: Ctx, L, volscale, top=50, k=10):
    U = x.universe(top)
    score = (x.C.shift(1) / x.C.shift(L + 1) - 1).where(U)
    rk = score.rank(axis=1, ascending=False)
    W = (rk <= k).astype(float).div(k).where(U, 0.0)
    if volscale:
        # vol de la propia cartera: retornos del día siguiente de la composición vigente (hasta t)
        wl = _sched(W, x.mondays).ffill().fillna(0.0)
        pr = (wl.shift(1) * x.R.fillna(0.0)).sum(axis=1)
        pv = pr.rolling(30, min_periods=20).std() * np.sqrt(365)
        scale = (0.40 / pv).clip(upper=1.0).fillna(1.0)
        W = W.mul(scale, axis=0)
    return _sched(W, x.mondays)


def donchian_ens(x: Ctx, universe="top20", band=0.0):
    if universe == "btc":
        cols = ["BTC"]; U = pd.DataFrame(True, index=x.C.index, columns=cols) & x.C[cols].notna()
    else:
        U = x.universe(20, min_adv=2e6, min_hist=365); cols = list(x.C.columns)
    C = x.C[cols]
    states = []
    for N in LOOKS_DC:
        hi = C.rolling(N, min_periods=N).max().shift(1); lo = C.rolling(N, min_periods=N).min().shift(1)
        mid = (hi + lo) / 2
        st = np.zeros(C.shape); stop = np.full(C.shape, np.nan)
        cv, hv, mv = C.values, hi.values, mid.values
        for t in range(1, len(C)):
            prev = st[t - 1]
            enter = (prev == 0) & (cv[t] > hv[t])
            stp = np.where(prev == 1, np.fmax(stop[t - 1], mv[t]), np.nan)
            stp = np.where(enter, mv[t], stp)
            keep = (prev == 1) & (cv[t] > stop[t - 1])
            st[t] = np.where(enter | keep, 1.0, 0.0)
            stop[t] = np.where(st[t] == 1, stp, np.nan)
        states.append(st)
    sig = pd.DataFrame(np.mean(states, axis=0), index=C.index, columns=cols)
    # Réplica de Zarattini, Pagani y Barbon (2025): cada moneda recibe 1/N del capital (N = 20 del universo) escalado a
    # una volatilidad objetivo del 25 % con apalancamiento máximo 2 por posición; la cartera, sin apalancamiento (≤ 1).
    # Corrección del 2026-11-16 tras la prueba de humo en DESARROLLO (antes: 25 %/vol sin dividir entre N; ver informe).
    lev = (0.25 / x.vol[90][cols]).clip(upper=1.0 if universe == "btc" else 2.0)
    size = lev if universe == "btc" else lev / 20.0
    W = (sig * size).where(U[cols].fillna(False), 0.0).fillna(0.0)
    tot = W.sum(axis=1)
    W = W.div(tot.where(tot > 1, 1.0), axis=0)
    return W, band


def meanrev(x: Ctx, k, btc_filter, top=50, n=5, hold=3):
    U = x.universe(top)
    score = (x.C / x.C.shift(k) - 1).where(U)
    pick = (score.rank(axis=1, ascending=True) <= n).astype(float) / n
    W = sum(pick.shift(h).fillna(0.0) for h in range(hold)) / hold   # cohortes solapadas
    if btc_filter:
        W = W.mul(x.btc_up.astype(float), axis=0)
    return W


def voltarget_btc(x: Ctx, sma_filter):
    w = (0.40 / x.vol[30]["BTC"]).clip(upper=1.0).fillna(0.0)
    if sma_filter:
        w = w * x.btc_up.astype(float)
    return pd.DataFrame({"BTC": w})


def voltarget_ew10(x: Ctx):
    U = x.universe(10)
    W = U.astype(float).div(U.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    wl = W.shift(1).fillna(0.0)
    pr = (wl * x.R.fillna(0.0)).sum(axis=1)
    pv = pr.rolling(30, min_periods=20).std() * np.sqrt(365)
    return W.mul((0.40 / pv).clip(upper=1.0).fillna(0.0), axis=0)


def volexp(x: Ctx):
    U = x.universe(30)
    entry = U & (x.vol[7] / x.vol[90] > 1.5) & (x.C / x.C.shift(7) > 1) & (x.C > x.C.rolling(20).max().shift(1))
    exitc = x.C < x.C.rolling(20).mean()
    state = np.zeros(x.C.shape); ev, xv, uv = entry.values, exitc.values, U.values
    for t in range(1, len(x.C)):
        state[t] = np.where(ev[t], 1.0, np.where((state[t - 1] == 1) & ~xv[t] & uv[t], 1.0, 0.0))
    sig = pd.DataFrame(state, index=x.C.index, columns=x.C.columns) > 0
    return _riskpar(sig, x.vol[60])


def carry(x: Ctx, thr, univ):
    f = x.fund["f"]; cols = [c for c in f.columns if c in x.C.columns]
    if univ == "btceth":
        cols = [c for c in cols if c in ("BTC", "ETH")]
    else:
        U = x.universe(10, min_adv=5e6).reindex(columns=cols).fillna(False)
    ann = f[cols].rolling(3, min_periods=3).mean() * 365
    state = np.zeros((len(x.C), len(cols))); a = ann.reindex(x.C.index).values
    for t in range(1, len(x.C)):
        on = np.where(state[t - 1] == 1, a[t] > 0, a[t] > thr)
        state[t] = np.where(np.isfinite(a[t]) & on, 1.0, 0.0)
    act = pd.DataFrame(state, index=x.C.index, columns=cols) > 0
    if univ != "btceth":
        act = act & U[cols]
    n = act.sum(axis=1).replace(0, np.nan)
    W = act.astype(float).div(n, axis=0).fillna(0.0) / 1.5          # 1,5 × nocional por el margen
    H = act.astype(float)
    return W, H


def funding_filter_tsmom(x: Ctx):
    f7 = x.fund["f"].rolling(7, min_periods=5).mean().reindex(index=x.C.index, columns=x.C.columns)
    U = x.universe(30)
    q = f7.where(U).rank(axis=1, pct=True)
    return tsmom(x, 90, True, exclude=(q > 0.8).fillna(False))


def funding_contra(x: Ctx):
    f7 = x.fund["f"].rolling(7, min_periods=5).mean().reindex(index=x.C.index, columns=x.C.columns)
    U = x.universe(30)
    pick = (f7.where(U).rank(axis=1, ascending=True) <= 5).astype(float) / 5
    return _sched(pick.mul(x.btc_up.astype(float), axis=0), x.mondays)


def adaptive(x: Ctx, kind):
    t = tsmom(x, 90, False).ffill().fillna(0.0)
    m = meanrev(x, 3, False)
    up, low = x.btc_up.astype(bool), x.btc_vol_low.fillna(False).astype(bool)
    if kind == "a":
        W = t.mul((up & low).astype(float), axis=0).add(m.mul((up & ~low).astype(float), axis=0), fill_value=0.0)
    else:
        W = t.mul(low.astype(float), axis=0)
    return W


CONFIGS = {}
for L in (30, 90, 180):
    for fl in (False, True):
        CONFIGS[f"F1_tsmom_L{L}_{'btc' if fl else 'sin'}"] = ("F1", lambda x, L=L, fl=fl: tsmom(x, L, fl))
CONFIGS["F1_tsmom_L90_btc_liq50M"] = ("F1", lambda x: tsmom(x, 90, True, top=20, min_adv=50e6))
for L in (7, 28, 90):
    for vs in (False, True):
        CONFIGS[f"F2_xsmom_L{L}_{'vol' if vs else 'sin'}"] = ("F2", lambda x, L=L, vs=vs: xsmom(x, L, vs))
for u in ("btc", "top20"):
    for b in (0.0, 0.25):
        CONFIGS[f"F3_donchian_{u}_{'banda' if b else 'diario'}"] = ("F3", lambda x, u=u, b=b: donchian_ens(x, u, b))
for k in (3, 7):
    for fl in (False, True):
        CONFIGS[f"F4_reversion_k{k}_{'btc' if fl else 'sin'}"] = ("F4", lambda x, k=k, fl=fl: meanrev(x, k, fl))
CONFIGS["F5_voltarget_btc_sin"] = ("F5", lambda x: voltarget_btc(x, False))
CONFIGS["F5_voltarget_btc_sma200"] = ("F5", lambda x: voltarget_btc(x, True))
CONFIGS["F5_voltarget_ew10"] = ("F5", voltarget_ew10)
CONFIGS["F5_volexpansion_top30"] = ("F5", volexp)
for thr in (0.0, 0.10):
    for u in ("btceth", "top10"):
        CONFIGS[f"F6_carry_{u}_thr{int(thr * 100)}"] = ("F6", lambda x, thr=thr, u=u: carry(x, thr, u))
CONFIGS["F6_tsmom_filtro_funding"] = ("F6", funding_filter_tsmom)
CONFIGS["F6_funding_contrario"] = ("F6", funding_contra)
CONFIGS["F7_adaptativo_a"] = ("F7", lambda x: adaptive(x, "a"))
CONFIGS["F7_adaptativo_b"] = ("F7", lambda x: adaptive(x, "b"))
CONFIGS["F8_conjunto_igual"] = ("F8", None)
CONFIGS["F8_conjunto_invvol"] = ("F8", None)
F8_PARTS = ("F1_tsmom_L90_btc", "F3_donchian_top20_diario", "F5_voltarget_btc_sin", "F6_carry_top10_thr10")
assert len(CONFIGS) == 35, len(CONFIGS)
