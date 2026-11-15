"""SIMULADOR V1 CONGELADO: es el código exacto con el que se ejecutó el holdout registrado (commit 8868070).
No modificar: sirve para reproducir ese resultado. Las correcciones están en sim.py (v2).

Simulador diario de cartera spot (PREREGISTRO §4). Señal al cierre de D, ejecución desde la apertura de D+1."""
import math
import numpy as np
import pandas as pd

RISK = {"capital": 10_000.0, "risk_pct": 0.5, "max_pos_pct": 15.0, "max_positions": 5, "max_open_risk_pct": 3.0,
        "adv_cap_pct": 1.0, "bear_mult": 0.5, "vol_target": 0.40, "chase_atr": 1.0}
SCEN = {"base": (1.0, 0.10), "elevated": (2.0, 0.10), "stress": (3.0, 0.30)}   # (multiplicador de costes, descuento de retirada)


def cost_rate(adv, mult):
    """Coste por lado (fracción): comisión + medio spread + deslizamiento por tramo de liquidez."""
    if adv is None or not math.isfinite(adv):
        adv = 0
    base = 0.0010 + (0.0002 + 0.0005 if adv > 50e6 else 0.0005 + 0.0015 if adv > 5e6 else 0.0015 + 0.0030)
    return base * mult


def simulate(P, F, strat, start, end, scen="base", U=None, manip=None, manip_max=None, risk=None):
    R = dict(RISK, **(risk or {}))
    cm, haircut = SCEN[scen]
    dates = P["c"].index
    i0, i1 = dates.searchsorted(pd.Timestamp(start)), dates.searchsorted(pd.Timestamp(end), side="right") - 1
    syms = list(P["c"].columns); sidx = {s: j for j, s in enumerate(syms)}
    O, H, L, C = (P[k].to_numpy() for k in "ohlc")
    ATR, ADV, VOL = F["atr"].to_numpy(), F["adv30"].to_numpy(), F["vol28"].to_numpy()
    ENT, EXS, SC = strat.entry.to_numpy(), strat.exit_sig.to_numpy(), strat.score.to_numpy()
    BEAR = F["btc_bear"].to_numpy(); BR7 = F["btc_ret7"].to_numpy()
    MAN = manip.to_numpy() if manip is not None else None
    lastv = np.array([P["c"][s].last_valid_index() for s in syms])
    lastix = np.array([dates.get_loc(x) if x is not None else -1 for x in lastv])
    end_all = len(dates) - 1
    cash = R["capital"]; pos = {}; pend_in = []; pend_out = set(); trades = []; curve = []; fees = 0.0
    last_px = {}

    def equity(t):
        val = 0.0
        for j, p in pos.items():
            px = C[t, j] if np.isfinite(C[t, j]) else last_px.get(j, p["entry"])
            val += p["qty"] * px
        return cash + val

    def close(j, t, px, reason):
        nonlocal cash, fees
        p = pos.pop(j)
        rate = cost_rate(ADV[t, j] if np.isfinite(ADV[t, j]) else p["adv"], cm)
        fill = px * (1 - rate)
        cash += p["qty"] * fill; fees += p["qty"] * px * rate
        pnl = p["qty"] * fill - p["cost"]
        trades.append({"symbol": syms[j], "family": strat.family, "strategy": strat.name,
                       "entry_date": dates[p["t"]].date().isoformat(), "exit_date": dates[t].date().isoformat(),
                       "entry_px": p["entry"], "exit_px": fill, "qty": p["qty"], "cost_usd": p["cost"],
                       "pnl_usd": pnl, "R": pnl / p["risk_usd"] if p["risk_usd"] else None,
                       "days": t - p["t"], "exit_reason": reason, "bear_at_entry": bool(p["bear"]),
                       "manip_at_entry": p["manip"], "fees_usd": p["fee_in"] + p["qty"] * px * rate})

    eq_prev = cash
    for t in range(i0, i1 + 1):
        # 1) retiradas: el día siguiente a la última vela se vende al último cierre con descuento
        for j in [j for j in pos if lastix[j] < t and lastix[j] < end_all - 3]:
            close(j, t, C[lastix[j], j] * (1 - haircut), "Retirada")
        # 2) salidas por señal a la apertura
        for j in list(pend_out):
            if j in pos and np.isfinite(O[t, j]):
                close(j, t, O[t, j], "Señal de salida"); pend_out.discard(j)
            elif j not in pos:
                pend_out.discard(j)
        # 3) entradas a la apertura
        eq = eq_prev
        mult = R["bear_mult"] if BEAR[t - 1] else 1.0
        for (j, sig_c, sig_atr) in pend_in:
            if len(pos) >= R["max_positions"] or j in pos:
                continue
            o = O[t, j]
            if not np.isfinite(o) or not np.isfinite(sig_atr) or sig_atr <= 0:
                continue
            if o > sig_c + R["chase_atr"] * sig_atr:
                continue                                                   # orden cancelada: hueco al alza
            stop = o - strat.stop_atr * sig_atr
            if stop <= 0:
                continue
            rps = o - stop
            if strat.sizing == "vol":
                v = VOL[t - 1, j]
                if not np.isfinite(v) or v <= 0:
                    continue
                value = eq * min(R["max_pos_pct"] / 100, R["vol_target"] / R["max_positions"] / v) * mult
                qty = value / o
            else:
                qty = eq * R["risk_pct"] / 100 * mult / rps
            open_risk = sum(p["qty"] * max(0.0, (C[t - 1, k] if np.isfinite(C[t - 1, k]) else p["entry"]) - p["stop"])
                            for k, p in pos.items())
            room = eq * R["max_open_risk_pct"] / 100 - open_risk
            if room <= 0:
                continue
            qty = min(qty, room / rps, eq * R["max_pos_pct"] / 100 / o,
                      (ADV[t - 1, j] * R["adv_cap_pct"] / 100) / o if np.isfinite(ADV[t - 1, j]) else 0)
            rate = cost_rate(ADV[t - 1, j], cm)
            px = o * (1 + rate)
            qty = min(qty, cash / px)
            if qty * px < 20:                                              # orden mínima
                continue
            cash -= qty * px; fees += qty * o * rate
            pos[j] = {"t": t, "entry": px, "qty": qty, "cost": qty * px, "stop": stop, "risk_usd": qty * rps,
                      "adv": ADV[t - 1, j], "bear": BEAR[t - 1], "fee_in": qty * o * rate,
                      "manip": float(MAN[t - 1, j]) if MAN is not None and np.isfinite(MAN[t - 1, j]) else None}
        pend_in = []
        # 4) stops intradía (también el día de entrada; hueco = apertura)
        for j in list(pos):
            p = pos[j]
            lo, o = L[t, j], O[t, j]
            if np.isfinite(lo) and lo <= p["stop"]:
                px = p["stop"] if (p["t"] == t or not np.isfinite(o) or o > p["stop"]) else o
                close(j, t, px, "Stop" if p["t"] != t else "Stop el día de entrada")
        # 5) cierre: valoración, trailing, salidas por tiempo/señal, crash
        for j, p in pos.items():
            if np.isfinite(C[t, j]):
                last_px[j] = C[t, j]
                if strat.trail_atr and np.isfinite(ATR[t, j]):
                    p["stop"] = max(p["stop"], C[t, j] - strat.trail_atr * ATR[t, j])
        eq_prev = equity(t)
        exposure = (eq_prev - cash) / eq_prev if eq_prev > 0 else 0
        curve.append((dates[t], eq_prev, exposure))
        if t == i1:
            break
        weekday_ok = (not strat.weekly) or dates[t + 1].weekday() == 0
        crash = strat.crash_exit and np.isfinite(BR7[t]) and BR7[t] < -0.15
        for j, p in pos.items():
            if crash or (strat.max_days and t - p["t"] >= strat.max_days) or (weekday_ok and EXS[t, j]):
                pend_out.add(j)
        if crash or not weekday_ok:
            continue
        free = R["max_positions"] - (len(pos) - len(pend_out))
        if free <= 0:
            continue
        row = ENT[t]
        cand = np.flatnonzero(row & np.isfinite(SC[t]))
        if MAN is not None and manip_max is not None:
            cand = [j for j in cand if not (np.isfinite(MAN[t, j]) and MAN[t, j] >= manip_max)]
        cand = sorted((j for j in cand if j not in pos), key=lambda j: -SC[t, j])[:free]
        pend_in = [(j, C[t, j], ATR[t, j]) for j in cand]
    # cierre a mercado al final del periodo
    for j in list(pos):
        px = C[i1, j] if np.isfinite(C[i1, j]) else last_px.get(j, pos[j]["entry"])
        close(j, i1, px, "Fin del periodo")
    eqs = pd.DataFrame(curve, columns=["date", "equity", "exposure"]).set_index("date")
    if len(eqs):
        eqs.iloc[-1, 0] = cash
    return {"trades": trades, "curve": eqs, "fees": fees, "strategy": strat.name, "family": strat.family,
            "scenario": scen, "start": str(dates[i0].date()), "end": str(dates[i1].date())}
