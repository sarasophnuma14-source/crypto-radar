"""Motor de backtest por pesos objetivo (PREREGISTRO_V3 §4). Diario, sin apalancamiento.

Convención temporal (sin anticipación):
  * `weights` (fecha × activo): la fila t se calcula SOLO con datos hasta el cierre de t.
  * Se ejecuta a la apertura de t + 1 + lag (lag 0 por defecto; 1 en la prueba de latencia). Nunca al máximo ni al
    mínimo de la vela.
  * Fila con algún valor finito = rebalancear ese día (NaN dentro de la fila = 0). Fila toda NaN = mantener.
Cobertura con perpetuo (F6a): `hedge` (fecha × activo, 0..1) es la fracción del nocional spot cubierta con un corto en
el perpetuo; usa la apertura y el cierre reales del perpetuo y cobra/paga el funding diario real (`funding`, suma de las
tasas de 8 h de ese día UTC). El margen del corto (50 % del nocional) se aparta del efectivo y no rinde.
"""
from __future__ import annotations
import math
import numpy as np
import pandas as pd

TIERS = ((50e6, 0.0002, 0.0005), (5e6, 0.0005, 0.0015), (-1.0, 0.0015, 0.0030))  # (ADV >, medio spread, deslizamiento)
SCEN = {"BASE": 1.0, "ELEVADO": 2.0, "ESTRES": 3.0}
SPOT_FEE, PERP_FEE, MAKER_FEE = 0.001, 0.0005, 0.0002


def slip_rate(adv, notional):
    """Medio spread + deslizamiento + impacto por lado (sin comisión)."""
    a = adv if adv == adv else 0.0
    hs, sl = next((h, s) for lo, h, s in TIERS if a > lo)
    return hs + sl + 0.001 * math.sqrt(max(notional, 0.0) / max(a * 0.01, 1.0))


def run(P, weights, *, capital=10_000.0, lag=0, scenario="BASE", maker=False, max_part=0.01, cap=0.20, start=None,
        end=None, hedge=None, perp_o=None, perp_c=None, funding=None, delist_haircut=None, band=0.0):
    mult = SCEN[scenario]
    haircut = delist_haircut if delist_haircut is not None else (0.30 if scenario == "ESTRES" else 0.10)
    used = (weights.fillna(0.0) != 0).any(axis=0)
    weights = weights.loc[:, used] if used.any() else weights.iloc[:, :1]
    if hedge is not None:
        hedge = hedge.reindex(columns=weights.columns)
    cols = list(weights.columns)
    O, C, V = (P[k].reindex(columns=cols) for k in ("o", "c", "v"))
    idx = C.index
    ADV = V.rolling(30, min_periods=10).mean().shift(1).values         # conocido antes de la apertura
    lastv = C.apply(lambda s: s.last_valid_index())
    pos = {d: i for i, d in enumerate(idx)}
    LV = np.array([pos[x] if x is not None and x == x else -1 for x in lastv])
    W = weights.reindex(idx).shift(1 + lag).values
    hedged = hedge is not None
    if hedged:
        H = hedge.reindex(idx).reindex(columns=cols).shift(1 + lag).values
        PO = perp_o.reindex(idx).reindex(columns=cols).values
        PC = perp_c.reindex(idx).reindex(columns=cols).values
        FU = funding.reindex(idx).reindex(columns=cols).fillna(0.0).values
    Oa, Ca = O.values, C.values
    s = idx[0] if start is None else pd.Timestamp(start)
    e = idx[-1] if end is None else pd.Timestamp(end)
    days = [d for d in idx if s <= d <= e]
    n = len(cols)
    units = np.zeros(n); punits = np.zeros(n); cash = capital; margin = 0.0
    last = np.full(n, np.nan); plast = np.full(n, np.nan); pending = np.full(n, np.nan)
    epi = np.zeros(n); inpos = np.zeros(n, bool); asset_pnl = np.zeros(n)
    episodes, eq, ex = [], [], []
    tot = {"fees": 0.0, "slippage": 0.0, "funding": 0.0, "turnover": 0.0, "delist_loss": 0.0}

    def book(j, x):
        asset_pnl[j] += x; epi[j] += x

    for d in days:
        i = pos[d]; o, c = Oa[i], Ca[i]
        # 1) hueco cierre previo → apertura
        po = np.where(np.isfinite(o), o, last)
        g = units * np.nan_to_num(po - last)
        for j in np.nonzero(g)[0]:
            book(j, g[j])
        last = np.where(np.isfinite(po), po, last)
        # 2) retirada definitiva
        for j in np.nonzero((LV < i) & (units > 0))[0]:
            loss = units[j] * last[j] * haircut
            cash += units[j] * last[j] - loss; book(j, -loss); tot["delist_loss"] += loss
            units[j] = 0.0; pending[j] = np.nan
        # 3) objetivo del día
        equity = cash + margin + (units * np.nan_to_num(last)).sum()
        if np.isfinite(W[i]).any():
            w = np.clip(np.nan_to_num(W[i]), 0.0, cap)
            lim = 1.0 / 1.5 if hedged else 1.0
            if w.sum() > lim:
                w *= lim / w.sum()
            pending = np.where(LV >= i, w * equity, np.nan)
        # 4) órdenes spot a la apertura (parciales si superan el 1 % del volumen)
        if np.isfinite(pending).any():
            dv = pending - units * o
            done0 = np.isfinite(pending) & np.isfinite(o) & (np.abs(dv) < 1.0)
            pending[done0] = np.nan
            for j in np.nonzero(np.isfinite(pending) & np.isfinite(o))[0]:
                cur = units[j] * o[j]; delta = pending[j] - cur
                if band > 0 and cur > 0 and pending[j] > 0 and abs(delta) < band * pending[j]:
                    pending[j] = np.nan; continue
                if abs(delta) < 1.0:
                    pending[j] = np.nan; continue
                lim_n = np.nan_to_num(ADV[i][j]) * max_part
                q = math.copysign(min(abs(delta), lim_n), delta)
                if abs(q) < 1e-9:
                    continue
                fee = abs(q) * (MAKER_FEE if maker else SPOT_FEE) * mult
                sl = 0.0 if maker else abs(q) * slip_rate(ADV[i][j], abs(q)) * mult
                units[j] += q / o[j]; cash -= q + fee + sl
                book(j, -(fee + sl)); tot["fees"] += fee; tot["slippage"] += sl; tot["turnover"] += abs(q)
                if abs(q) >= abs(delta) - 1e-9:
                    pending[j] = np.nan
                if units[j] * o[j] < 1e-6:
                    units[j] = 0.0
        # 5) perpetuo: PnL del corto, funding y ajuste a la apertura
        if hedged:
            ppo = np.where(np.isfinite(PO[i]), PO[i], plast); ppc = np.where(np.isfinite(PC[i]), PC[i], ppo)
            gp = -punits * np.nan_to_num(ppo - plast)
            fund = punits * np.nan_to_num(plast) * FU[i]
            for j in np.nonzero(gp + fund)[0]:
                book(j, gp[j] + fund[j])
            cash += gp.sum() + fund.sum(); tot["funding"] += fund.sum()
            hf = np.nan_to_num(H[i]) if np.isfinite(H[i]).any() else None
            for j in np.nonzero((units > 0) | (punits != 0))[0]:
                ref = ppo[j]
                if not (ref == ref and ref > 0):
                    continue
                want = (hf[j] * units[j] * np.nan_to_num(o[j], nan=last[j]) / ref) if hf is not None else (punits[j] if units[j] > 0 else 0.0)
                dq = want - punits[j]
                if abs(dq * ref) < 1.0:
                    continue
                notion = abs(dq) * ref
                fee = notion * (MAKER_FEE if maker else PERP_FEE) * mult
                sl = 0.0 if maker else 0.5 * notion * slip_rate(ADV[i][j], notion) * mult
                cash -= fee + sl; book(j, -(fee + sl)); tot["fees"] += fee; tot["slippage"] += sl; tot["turnover"] += notion
                punits[j] = want
            gc = -punits * np.nan_to_num(ppc - ppo)
            for j in np.nonzero(gc)[0]:
                book(j, gc[j])
            cash += gc.sum()
            plast = np.where(np.isfinite(ppc), ppc, plast)
            newm = 0.5 * (punits * np.nan_to_num(plast)).sum()
            cash -= newm - margin; margin = newm
        # 6) apertura → cierre
        pc = np.where(np.isfinite(c), c, last)
        g = units * np.nan_to_num(pc - last)
        for j in np.nonzero(g)[0]:
            book(j, g[j])
        last = np.where(np.isfinite(pc), pc, last)
        equity = cash + margin + (units * np.nan_to_num(last)).sum()
        eq.append(equity); ex.append((units * np.nan_to_num(last)).sum() / equity if equity > 0 else 0.0)
        held = units > 0
        for j in np.nonzero(held & ~inpos)[0]:
            inpos[j] = True
        for j in np.nonzero(~held & inpos & (punits == 0))[0]:
            episodes.append((cols[j], float(epi[j]))); inpos[j] = False; epi[j] = 0.0
    for j in np.nonzero(inpos)[0]:                                   # episodios abiertos al final: a valor de mercado
        episodes.append((cols[j], float(epi[j])))
    return {"curve": pd.Series(eq, index=pd.DatetimeIndex(days), name="equity"),
            "exposure": pd.Series(ex, index=pd.DatetimeIndex(days)), "episodes": episodes,
            "asset_pnl": pd.Series(asset_pnl, index=cols), "capital": capital, **tot}
