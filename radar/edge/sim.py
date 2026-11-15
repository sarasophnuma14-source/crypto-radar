"""Simulador diario de cartera spot, VERSIÓN 2 (corregida tras la auditoría, AUDITORIA_D_VOLMOM.md §4).

El holdout registrado se ejecutó con la versión 1, que se conserva sin cambios en sim_v1.py. Este simulador NO se ha
usado para elegir parámetros: la estrategia y sus parámetros son los congelados en selection_frozen.json.

Correcciones respecto a v1:
  B2  el tamaño por volatilidad respeta el 0,5 % de riesgo por operación (en v1 lo ignoraba)
  B3  el objetivo de volatilidad se aplica a la cartera con la matriz de covarianzas (portfolio_risk)
  B4  tamaño, límite del 15 % y riesgo se calculan con el precio real de ejecución (apertura + costes)
  B5  retirada detectada sin mirar el futuro: 3 días seguidos sin vela ⇒ venta al último cierre × (1 − descuento)
  B6  un activo sin cotización se valora al último cierre conocido, nunca al precio de entrada
  B7  el riesgo abierto usa la última marca de cada posición (precio de entrada si se abrió ese día)
  B9  los costes de una ejecución en D usan el ADV hasta D−1 (v1 usaba el ADV que incluye el propio día D)
  B10 la decisión de tamaño se toma al cierre de D con el capital de D y se vuelve a acotar en la apertura de D+1

Orden de cada día t: (1) retiradas, (2) salidas pendientes a la apertura, (3) entradas pendientes a la apertura,
(4) stops intradía (también el día de entrada; con hueco se ejecuta a la apertura), (5) cierre: marca, capital,
señales y plan de órdenes para t+1. El estado está indexado por símbolo y fecha para poder guardarse (paper trading).
"""
import math
import numpy as np
import pandas as pd
from radar.edge import portfolio_risk as PR

RISK = {"capital": 10_000.0, "risk_pct": 0.5, "max_pos_pct": 15.0, "max_positions": 5, "max_open_risk_pct": 3.0,
        "adv_cap_pct": 1.0, "bear_mult": 0.5, "vol_target": 0.40, "chase_atr": 1.0, "min_order": 20.0,
        "delist_missing_days": 3}
SCEN = {"base": (1.0, 0.10), "elevated": (2.0, 0.10), "stress": (3.0, 0.30)}   # (multiplicador de costes, descuento de retirada)


def cost_rate(adv, mult):
    """Coste por lado (fracción): comisión + medio spread + deslizamiento por tramo de liquidez."""
    if adv is None or not math.isfinite(adv):
        adv = 0
    base = 0.0010 + (0.0002 + 0.0005 if adv > 50e6 else 0.0005 + 0.0015 if adv > 5e6 else 0.0015 + 0.0030)
    return base * mult


def new_state(capital):
    return {"cash": capital, "pos": {}, "pend_in": [], "pend_out": {}, "last_px": {}, "missing": {}, "eq_hist": [],
            "fees": 0.0, "trades": [], "events": []}


class Engine:
    """Motor de un día. `P`, `F`: paneles (fecha × símbolo). `strat`: Strategy con entry/score/exit_sig."""

    def __init__(self, P, F, strat, scen="base", manip=None, manip_max=None, risk=None, rparams=None):
        self.R = dict(RISK, **(risk or {}))
        self.cm, self.haircut = SCEN[scen]
        self.strat = strat
        self.dates = P["c"].index
        self.syms = list(P["c"].columns); self.sidx = {s: j for j, s in enumerate(self.syms)}
        self.O, self.H, self.L, self.C = (P[k].to_numpy() for k in "ohlc")
        self.ATR, self.ADV = F["atr"].to_numpy(), F["adv30"].to_numpy()
        self.ENT, self.EXS, self.SC = strat.entry.to_numpy(), strat.exit_sig.to_numpy(), strat.score.to_numpy()
        self.BEAR = F["btc_bear"].to_numpy(); self.BR7 = F["btc_ret7"].to_numpy()
        self.MAN = manip.to_numpy() if manip is not None else None
        self.manip_max = manip_max
        with np.errstate(divide="ignore", invalid="ignore"):
            self.LR = np.log(self.C[1:] / self.C[:-1])
        self.LR = np.vstack([np.full((1, self.C.shape[1]), np.nan), self.LR])
        self.rp = dict(PR.PARAMS)
        self.rp.update(risk_pct=self.R["risk_pct"], max_pos_pct=self.R["max_pos_pct"], max_positions=self.R["max_positions"],
                       max_open_risk_pct=self.R["max_open_risk_pct"], target_vol=self.R["vol_target"],
                       bear_mult=self.R["bear_mult"])
        self.rp.update(rparams or {})

    # ------------------------------------------------------------------ utilidades
    def _f(self, A, t, j):
        x = A[t, j] if t >= 0 else np.nan
        return float(x) if np.isfinite(x) else None

    def _ev(self, S, t, kind, sym=None, **kw):
        S["events"].append({"date": self.dates[t].date().isoformat(), "type": kind, "symbol": sym, **kw})

    def mark(self, S, sym):
        p = S["pos"][sym]
        return S["last_px"].get(sym, p["entry_open"])

    def equity(self, S):
        return S["cash"] + sum(p["qty"] * self.mark(S, s) for s, p in S["pos"].items())

    def _close(self, S, sym, t, px, reason):
        p = S["pos"].pop(sym); j = self.sidx[sym]
        adv = self._f(self.ADV, t - 1, j) or p["adv"]
        rate = cost_rate(adv, self.cm)
        fill = px * (1 - rate)
        fee = p["qty"] * px * rate
        S["cash"] += p["qty"] * fill; S["fees"] += fee
        pnl = p["qty"] * fill - p["cost"]
        tr = {"symbol": sym, "family": self.strat.family, "strategy": self.strat.name, "signal_date": p["signal_date"],
              "entry_date": p["entry_date"], "exit_date": self.dates[t].date().isoformat(),
              "entry_open": p["entry_open"], "entry_px": p["entry"], "exit_ref_px": px, "exit_px": fill, "qty": p["qty"],
              "cost_usd": p["cost"], "proceeds_usd": p["qty"] * fill, "pnl_usd": pnl,
              "R": pnl / p["risk_usd"] if p["risk_usd"] else None, "risk_usd": p["risk_usd"],
              "risk_pct_equity": p["risk_pct_equity"], "stop": p["stop"],
              "days": (self.dates[t] - pd.Timestamp(p["entry_date"])).days, "exit_reason": reason,
              "bear_at_entry": bool(p["bear"]), "manip_at_entry": p["manip"],
              "fees_usd": p["fee_in"] + fee, "fee_in_usd": p["fee_in"], "fee_out_usd": fee}
        S["trades"].append(tr)
        self._ev(S, t, "exit", sym, reason=reason, px=fill, pnl_usd=pnl)
        S["pend_out"].pop(sym, None)
        return tr

    # ------------------------------------------------------------------ un día completo
    def step(self, S, t, is_last=False):
        R, st = self.R, self.strat
        O, H, L, C = self.O, self.H, self.L, self.C
        # 1) retiradas (solo con información hasta D): n días seguidos sin vela
        for sym in list(S["pos"]):
            if S["missing"].get(sym, 0) >= R["delist_missing_days"]:
                self._close(S, sym, t, S["last_px"].get(sym, S["pos"][sym]["entry_open"]) * (1 - self.haircut), "Retirada")
        # 2) salidas pendientes a la apertura
        for sym in list(S["pend_out"]):
            if sym not in S["pos"]:
                S["pend_out"].pop(sym); continue
            o = self._f(O, t, self.sidx[sym])
            if o is not None:
                self._close(S, sym, t, o, S["pend_out"][sym])
        # 3) entradas pendientes a la apertura (cada orden consume efectivo y riesgo al llenarse: no hay doble uso)
        eq0 = S["eq_hist"][-1] if S["eq_hist"] else S["cash"]
        for od in S["pend_in"]:
            sym = od["symbol"]; j = self.sidx.get(sym)
            if j is None or sym in S["pos"]:
                continue
            if len(S["pos"]) >= R["max_positions"]:
                self._ev(S, t, "order_cancelled", sym, reason="máximo de posiciones"); continue
            o = self._f(O, t, j)
            if o is None:
                self._ev(S, t, "order_cancelled", sym, reason="sin apertura (sin dato)"); continue
            if o > od["sig_close"] + R["chase_atr"] * od["sig_atr"]:
                self._ev(S, t, "order_cancelled", sym, reason="hueco al alza > 1 ATR", open=o); continue
            stop = o - st.stop_atr * od["sig_atr"]
            if stop <= 0:
                self._ev(S, t, "order_cancelled", sym, reason="stop ≤ 0"); continue
            adv = self._f(self.ADV, t - 1, j) or 0.0
            rate = cost_rate(adv, self.cm)
            px = o * (1 + rate)                                               # precio real de ejecución
            rps = px - stop
            risk_pct = R["risk_pct"] * (R["bear_mult"] if od["bear"] else 1.0)
            open_risk = sum(p["qty"] * max(0.0, self.mark(S, s) - p["stop"]) for s, p in S["pos"].items())
            room = eq0 * R["max_open_risk_pct"] / 100 - open_risk
            gross = sum(p["qty"] * self.mark(S, s) for s, p in S["pos"].items())
            caps = {"objetivo": od["value"] / px,
                    "15 % por activo": eq0 * R["max_pos_pct"] / 100 / px,
                    "riesgo por operación": eq0 * risk_pct / 100 / rps,
                    "riesgo abierto": max(0.0, room) / rps,
                    "liquidez 1 % ADV": adv * R["adv_cap_pct"] / 100 / px,
                    "sin apalancamiento": max(0.0, eq0 - gross) / px,
                    "efectivo": max(0.0, S["cash"]) / px}
            lim = min(caps, key=caps.get); qty = caps[lim]
            if qty * px < R["min_order"]:
                self._ev(S, t, "order_cancelled", sym, reason=f"tamaño < {R['min_order']:.0f} USD ({lim})"); continue
            cost = qty * px; fee = qty * o * rate
            S["cash"] -= cost; S["fees"] += fee
            S["pos"][sym] = {"signal_date": od["signal_date"], "entry_date": self.dates[t].date().isoformat(),
                             "entry_open": o, "entry": px, "qty": qty, "cost": cost, "stop": stop, "risk_usd": qty * rps,
                             "risk_pct_equity": qty * rps / eq0 * 100, "adv": adv, "bear": bool(od["bear"]),
                             "fee_in": fee, "manip": od.get("manip"), "partial": lim != "objetivo",
                             "limit": lim}
            S["last_px"][sym] = o
            S["missing"][sym] = 0
            self._ev(S, t, "fill", sym, px=px, qty=qty, value=cost, stop=stop, limit=lim,
                     risk_pct_equity=round(qty * rps / eq0 * 100, 4),
                     open_risk_after_pct=(open_risk + qty * rps) / eq0 * 100, gross_after_pct=(gross + cost) / eq0 * 100)
        S["pend_in"] = []
        # 4) stops intradía
        for sym in list(S["pos"]):
            p = S["pos"][sym]; j = self.sidx[sym]
            lo, o = self._f(L, t, j), self._f(O, t, j)
            if lo is not None and lo <= p["stop"]:
                today = p["entry_date"] == self.dates[t].date().isoformat()
                px = p["stop"] if (today or o is None or o > p["stop"]) else o
                self._close(S, sym, t, px, "Stop el día de entrada" if today else "Stop")
        # 5) cierre: marcas, trailing, capital
        for sym, p in S["pos"].items():
            c = self._f(C, t, self.sidx[sym])
            if c is not None:
                S["last_px"][sym] = c; S["missing"][sym] = 0
                if st.trail_atr:
                    a = self._f(self.ATR, t, self.sidx[sym])
                    if a:
                        p["stop"] = max(p["stop"], c - st.trail_atr * a)
            else:
                S["missing"][sym] = S["missing"].get(sym, 0) + 1
        eq = self.equity(S)
        S["eq_hist"].append(eq)
        gross = sum(p["qty"] * self.mark(S, s) for s, p in S["pos"].items())
        row = {"date": self.dates[t].date().isoformat(), "equity": eq, "cash": S["cash"], "exposure": gross / eq if eq > 0 else 0,
               "positions": len(S["pos"]), "stale_marks": sum(1 for s in S["pos"] if S["missing"].get(s, 0) > 0),
               "open_risk_usd": sum(p["qty"] * max(0.0, self.mark(S, s) - p["stop"]) for s, p in S["pos"].items())}
        if is_last:
            return row
        self.plan(S, t)
        return row

    # ------------------------------------------------------------------ señales al cierre de t → órdenes para t+1
    def plan(self, S, t):
        R, st = self.R, self.strat
        nxt = self.dates[t] + pd.Timedelta(days=1)
        weekday_ok = (not st.weekly) or nxt.weekday() == 0
        crash = st.crash_exit and np.isfinite(self.BR7[t]) and self.BR7[t] < -0.15
        for sym, p in S["pos"].items():
            j = self.sidx[sym]
            if crash:
                S["pend_out"][sym] = "Salida por caída de BTC"
            elif st.max_days and (self.dates[t] - pd.Timestamp(p["entry_date"])).days >= st.max_days:
                S["pend_out"][sym] = "Salida por tiempo"
            elif weekday_ok and self.EXS[t, j]:
                S["pend_out"][sym] = "Señal de salida"
        if crash or not weekday_ok:
            return
        cand = np.flatnonzero(self.ENT[t] & np.isfinite(self.SC[t]))
        cand = sorted((j for j in cand if self.syms[j] not in S["pos"]), key=lambda j: -self.SC[t, j])
        for j in cand:
            self._ev(S, t, "signal", self.syms[j], score=float(self.SC[t, j]))
        if self.MAN is not None and self.manip_max is not None:
            keep = []
            for j in cand:
                if np.isfinite(self.MAN[t, j]) and self.MAN[t, j] >= self.manip_max:
                    self._ev(S, t, "rejected", self.syms[j], reason="riesgo de manipulación")
                else:
                    keep.append(j)
            cand = keep
        staying = [s for s in S["pos"] if s not in S["pend_out"]]
        free = R["max_positions"] - len(staying)
        for j in cand[max(0, free):]:
            self._ev(S, t, "rejected", self.syms[j], reason="sin hueco: máximo de posiciones")
        cand = cand[:max(0, free)]
        if not cand:
            return
        eq = S["eq_hist"][-1]
        bear = bool(self.BEAR[t])
        good = []
        for j in cand:
            a = self._f(self.ATR, t, j); c = self._f(self.C, t, j)
            if not a or not c or a <= 0:
                self._ev(S, t, "rejected", self.syms[j], reason="sin ATR o cierre"); continue
            good.append(j)
        if not good:
            return
        ref = {j: self.C[t, j] * (1 + cost_rate(self._f(self.ADV, t, j), self.cm)) for j in good}
        if st.sizing == "vol":
            cols = [self.sidx[s] for s in staying] + good
            w0 = max(0, t - self.rp["cov_window"] + 1)
            rets = self.LR[w0:t + 1, cols]
            held = [{"key": s, "value": S["pos"][s]["qty"] * self.mark(S, s),
                     "risk_usd": S["pos"][s]["qty"] * max(0.0, self.mark(S, s) - S["pos"][s]["stop"])} for s in staying]
            cands = [{"key": self.syms[j], "ref_px": ref[j], "stop": self.C[t, j] - st.stop_atr * self.ATR[t, j]} for j in good]
            plan = PR.plan_entries(eq, held, cands, rets, bear, S["eq_hist"], self.rp)
            for k, why in plan["rejected"].items():
                self._ev(S, t, "rejected", k, reason=why)
            values = plan["orders"]
        else:
            risk_pct = R["risk_pct"] * (R["bear_mult"] if bear else 1.0)
            values = {self.syms[j]: eq * risk_pct / 100 * ref[j] / (st.stop_atr * self.ATR[t, j]) for j in good}
        for j in good:
            sym = self.syms[j]
            if sym not in values:
                continue
            S["pend_in"].append({"symbol": sym, "signal_date": self.dates[t].date().isoformat(), "sig_close": float(self.C[t, j]),
                                 "sig_atr": float(self.ATR[t, j]), "value": float(values[sym]), "bear": bear,
                                 "manip": self._f(self.MAN, t, j) if self.MAN is not None else None})
            self._ev(S, t, "order", sym, value=round(float(values[sym]), 2))


def simulate(P, F, strat, start, end, scen="base", U=None, manip=None, manip_max=None, risk=None, rparams=None,
             keep_events=False):
    E = Engine(P, F, strat, scen, manip, manip_max, risk, rparams)
    dates = E.dates
    i0, i1 = dates.searchsorted(pd.Timestamp(start)), dates.searchsorted(pd.Timestamp(end), side="right") - 1
    S = new_state(E.R["capital"])
    rows = []
    for t in range(max(i0, 1), i1 + 1):
        rows.append(E.step(S, t, is_last=(t == i1)))
    for sym in list(S["pos"]):                                               # cierre a mercado al final del periodo
        E._close(S, sym, i1, E.mark(S, sym), "Fin del periodo")
    cv = pd.DataFrame(rows).set_index(pd.to_datetime([r["date"] for r in rows]))
    if len(cv):
        cv.iloc[-1, cv.columns.get_loc("equity")] = S["cash"]
    return {"trades": S["trades"], "curve": cv[["equity", "exposure", "cash", "positions", "stale_marks", "open_risk_usd"]],
            "fees": S["fees"], "strategy": strat.name, "family": strat.family, "scenario": scen,
            "start": str(dates[i0].date()), "end": str(dates[i1].date()), "events": S["events"] if keep_events else None,
            "simulator": "v2"}
