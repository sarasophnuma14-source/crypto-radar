"""Memecoins: entrar al COMIENZO del impulso (o justo antes), asegurar ganancia rápida y salir.

Señal (al cierre del día d, compra en la apertura de d+1):
  * modo "ruptura":   volumen del día ≥ V × media de 20 días  Y  cierre > máximo de los N días previos.
  * modo "anticipada": volumen ≥ V × media, vela verde, pero el cierre aún 0–10 % por DEBAJO del máximo de N días
                       (acumulación antes de romper).
  * filtro opcional: BTC sobre su media de 50 días.
Salida (lo primero que ocurra): stop -SL %, toma de ganancia +TP %, o T días. Si el mismo día toca stop y objetivo,
se asume el stop (peor caso). Tamaño fijo 10 % del capital por operación, máximo 8 a la vez.
"""
import itertools, json, sys
from pathlib import Path
import numpy as np
import pandas as pd
import lab

MEMES = ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "BOME", "MEME", "1000SATS", "1000CAT", "1000CHEEMS",
         "1MBABYDOGE", "NEIRO", "TURBO", "PEOPLE", "PNUT", "ACT", "TRUMP", "PENGU", "DOGS", "BROCCOLI714",
         "MUBARAK", "币安人生", "TST", "GIGGLE", "BANANAS31"]


def simulate(P, D, mode="ruptura", vmult=3, n=20, tp=0.3, sl=0.12, hold=10, btc_sma=0, size=0.10, max_pos=8,
             start="2021-01-01", close_pos=0.0, max_gain=0.0, partial=0.0, partial_frac=0.5):
    """close_pos: el cierre debe estar en la parte alta de la vela (0.75 = último 25 %).
    max_gain: no entrar si la vela de señal ya subió más que esto (evita perseguir).
    partial: vender `partial_frac` al +partial y mover el stop a la entrada (protege la operación)."""
    syms = [s for s in MEMES if s in P["c"].columns]
    c, o, h, l, v = (P[k][syms] for k in "cohlv")
    vavg = v.rolling(20, min_periods=15).mean().shift(1)
    hh = h.rolling(n).max().shift(1)
    vol_ok = (v >= vmult * vavg) & (D["vol30"][syms] >= 2e6) & (D["age"][syms] >= 25)
    green = c > o
    if mode == "ruptura":
        sig = vol_ok & (c > hh)
    else:
        sig = vol_ok & green & (c <= hh) & (c >= hh * 0.90)
    if close_pos:
        rng = (h - l).replace(0, np.nan)
        sig = sig & (((c - l) / rng) >= close_pos)
    if max_gain:
        sig = sig & ((c / c.shift(1) - 1) <= max_gain)
    if btc_sma:
        b = P["c"]["BTC"]; sig = sig & (b > b.rolling(btc_sma).mean()).values[:, None]
    slip = D["slip"][syms]
    dates = c.index[c.index >= start]
    cash, pos, eq, trades = 1.0, {}, [], []
    for i in range(len(dates) - 1):
        d, nd = dates[i], dates[i + 1]
        # gestionar abiertas durante nd
        for s in list(pos):
            p = pos[s]; op, hi, lo, cl = o.at[nd, s], h.at[nd, s], l.at[nd, s], c.at[nd, s]
            p["days"] += 1
            exit_px = why = None
            if np.isnan(cl):
                exit_px, why = p["last"], "sin datos"
            elif lo <= p["stop"]:
                exit_px, why = min(op, p["stop"]), ("stop en entrada" if p.get("half") else "stop")
            elif partial and not p.get("half") and hi >= p["cost"] * (1 + partial):
                # toma parcial: vende una parte al objetivo corto y sube el stop a la entrada
                ppx = max(op, p["cost"] * (1 + partial)) * (1 - slip.at[d, s]); qq = p["q"] * partial_frac
                cash += qq * ppx * (1 - lab.FEE); p["q"] -= qq; p["half"] = True
                p["realized"] = qq * ppx * (1 - lab.FEE); p["stop"] = max(p["stop"], p["cost"])
                if lo <= p["stop"]:
                    exit_px, why = p["stop"], "stop en entrada"
                elif hi >= p["tp"]:
                    exit_px, why = p["tp"], "objetivo"
                elif p["days"] >= hold:
                    exit_px, why = cl, "tiempo"
            elif hi >= p["tp"]:
                exit_px, why = max(op, p["tp"]), "objetivo"
            elif p["days"] >= hold:
                exit_px, why = cl, "tiempo"
            if exit_px is not None:
                px = exit_px * (1 - slip.at[d, s])
                cash += p["q"] * px * (1 - lab.FEE)
                got = p.get("realized", 0.0) + p["q"] * px * (1 - lab.FEE)
                pnl = got / p["q0"] / p["cost"] - 1
                trades.append({**p["info"], "salida": nd, "precio_salida": round(px, 10), "motivo": why,
                               "parcial": bool(p.get("half")), "dias": p["days"], "pnl_pct": round(pnl * 100, 2)})
                del pos[s]
            else:
                p["last"] = cl
        val = cash + sum(p["q"] * p["last"] for p in pos.values())
        eq.append((nd, val))
        # nuevas entradas: señal al cierre de nd, compra en la apertura de nd+1
        if i + 2 >= len(dates) or len(pos) >= max_pos:
            continue
        n2 = dates[i + 2]
        row = sig.loc[nd]
        for s in row[row].index:
            if s in pos or len(pos) >= max_pos:
                continue
            op = o.at[n2, s]
            if np.isnan(op):
                continue
            px = op * (1 + slip.at[nd, s])
            spend = min(val * size, cash)
            if spend < val * 0.02:
                break
            q = spend / (px * (1 + lab.FEE)); cash -= spend
            pos[s] = {"q": q, "q0": q, "cost": px * (1 + lab.FEE), "last": op, "days": 0,
                      "stop": px * (1 - sl), "tp": px * (1 + tp),
                      "info": {"simbolo": s, "señal": nd, "entrada": n2, "precio_entrada": round(px, 10),
                               "stop": round(px * (1 - sl), 10), "objetivo": round(px * (1 + tp), 10)}}
    return pd.Series(dict(eq)).sort_index(), pd.DataFrame(trades)


GRID = dict(mode=("ruptura", "anticipada"), vmult=(2, 3, 5), n=(7, 20), tp=(0.15, 0.3, 0.6), sl=(0.08, 0.15),
            hold=(5, 15), btc_sma=(0, 50))


def search(P, D):
    res = []
    keys = list(GRID)
    for vals in itertools.product(*GRID.values()):
        prm = dict(zip(keys, vals))
        eq, tr = simulate(P, D, **prm)
        res.append({"params": prm, "diseño": lab.stats(eq, *lab.DESIGN, tr if len(tr) else None)})
    return res


if __name__ == "__main__":
    P = lab.load_panel(sys.argv[1]); D = lab.derived(P)
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    res = search(P, D)
    (out / "memes_diseño.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float))
    print(len(res))
