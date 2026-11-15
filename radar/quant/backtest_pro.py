"""BACKTEST PROFESIONAL: simulación diaria de cartera, causal y conservadora.

Reglas de ejecución (todas verificables en el registro de operaciones):
  * La señal se calcula con la vela CERRADA del día D. Nada se ejecuta en D.
  * Órdenes límite (zona de entrada) o stop-buy (ruptura) válidas `order_expiry_days`, desde la vela D+1.
    Límite: llena si el mínimo toca el precio, a min(apertura, límite). Stop-buy: a max(apertura, disparo).
  * Costos por lado: comisión + deslizamiento + medio spread.
  * Vela de entrada: si toca el stop se sale ese mismo día (pesimista) y no se cuentan objetivos.
  * Vela ambigua (toca stop y objetivo): primero el stop, y se marca.
  * Hueco bajo el stop: se sale a la apertura (peor que el stop).
  * Objetivos parciales TP1/TP2/TP3 (33 % / 33 % / resto); tras TP1 el stop sube a la entrada.
  * Las decisiones de Exit Intelligence (al cierre) se ejecutan a la apertura siguiente.
  * Caja real, posiciones simultáneas, límites del Smart Portfolio y del régimen; valoración diaria a mercado.
  * Universo en el tiempo: las N monedas con más volumen medio de 30 días ESE día (sin mirar el futuro).
"""
from __future__ import annotations
import datetime as dt
import math
from . import features, engine, early, exits, regime as regime_mod, portfolio, metrics
from .features import val, chg

DAY_MS = 86_400_000
BUY_ACTIONS = ("COMPRAR EN ZONA", "ESPERAR RETROCESO", "ESPERAR RUPTURA")
DEFAULTS = {
    "capital": 10_000.0, "fee_pct": 0.10, "slippage_pct": 0.10, "spread_pct": 0.10,
    "order_expiry_days": 3, "universe_size": 150, "min_bars": 120, "min_avg_volume_usd": 1_000_000,
    "min_score_offset": 0, "min_risk_reward": 2.5, "partials": (0.33, 0.33), "use_exit_intelligence": True,
    "limits": {}, "max_hold_days": None,
    "dd_cooldown_days": 30,   # tras tocar la protección por drawdown: pausa y luego el máximo se reinicia al capital actual
}
NOT_ALT = {"BTC"}


def day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def bucket(avg_vol):
    if avg_vol is None:
        return "N/D"
    return "Liquidez alta (>50 M$/día)" if avg_vol >= 50e6 else "Liquidez media (5-50 M$/día)" if avg_vol >= 5e6 \
        else "Liquidez baja (<5 M$/día)"


class Market:
    """Panel histórico con indicadores precalculados (una sola vez) y el índice de fechas común."""

    def __init__(self, panel, log=None):
        self.f, self.idx = {}, {}
        panel = {s: k for s, k in panel.items() if len(k.get("c", [])) >= 30}
        for n, (sym, k) in enumerate(panel.items()):
            self.f[sym] = features.compute(k)
            self.idx[sym] = {t: i for i, t in enumerate(k["t"])}
            if log and n % 100 == 0:
                log(f"indicadores {n}/{len(panel)}")
        self.days = sorted({t for k in panel.values() for t in k["t"]})
        self.btc = self.f["BTC"]
        self.eth = self.f.get("ETH")
        self.vol30 = {}
        for sym, f in self.f.items():   # volumen medio de 30 días hasta i (incluido), para el universo
            v, s, out = f.v, 0.0, []
            for i in range(len(v)):
                s += v[i]
                if i >= 30:
                    s -= v[i - 30]
                out.append(s / min(i + 1, 30))
            self.vol30[sym] = out

    def i(self, sym, t):
        return self.idx[sym].get(t)


def universe(mk, t, size, min_bars, min_vol):
    rows = []
    for sym, f in mk.f.items():
        i = mk.i(sym, t)
        if i is None or i < min_bars:
            continue
        v = mk.vol30[sym][i]
        if v >= min_vol:
            rows.append((v, sym, i))
    rows.sort(reverse=True)
    return [(s, i) for _, s, i in rows[:size]]


def precompute_signals(mk, start=None, end=None, cfg=None, log=None, sample_every=5, horizon=20):
    """Una pasada por todos los días: régimen + análisis del universo. Devuelve:
    days: {t: {"regime", "regime_info", "cands": [...]}} y samples (para validar la puntuación)."""
    c = dict(DEFAULTS); c.update(cfg or {})
    out, samples = {}, []
    days = [t for t in mk.days if (start is None or t >= start) and (end is None or t <= end)]
    for n, t in enumerate(days):
        bi = mk.i("BTC", t)
        if bi is None or bi < 200:
            continue
        uni = universe(mk, t, c["universe_size"], c["min_bars"], c["min_avg_volume_usd"])
        above, rs = [], []
        for sym, i in uni:
            if sym in NOT_ALT:
                continue
            f = mk.f[sym]
            e50 = val(f.ema50, i)
            if e50 and i >= 50:
                above.append(f.c[i] > e50)
            c30, b30 = chg(f, i, 30), chg(mk.btc, bi, 30)
            if c30 is not None and b30 is not None:
                rs.append(c30 - b30)
        breadth = sum(above) / len(above) * 100 if above else None
        alt_rs = sorted(rs)[len(rs) // 2] if rs else None
        ei = mk.i("ETH", t) if mk.eth is not None else None
        reg = regime_mod.detect(mk.btc, bi, breadth, mk.eth, ei, alt_rs)
        cands = []
        for sym, i in uni:
            f = mk.f[sym]
            a = engine.analyze(sym, f, i, mk.btc, bi, regime=reg, settings={"min_risk_reward": c["min_risk_reward"]},
                               check_quality=False)
            pl, man = a["plan"], a["manipulation"]
            if n % sample_every == 0 and i + horizon < len(f.c):
                samples.append({"t": t, "sym": sym, "score": a["score"], "phase": a["phase"], "regime": reg["regime"],
                                "fwd": f.c[i + horizon] / f.c[i] - 1,
                                "fam": {k: v["score"] for k, v in a["families"].items()}})
            if a["phase"] not in regime_mod.ENTRY_PHASES or man["risk"] >= engine.MANIP_BLOCK:
                continue
            cands.append({"sym": sym, "i": i, "score": a["score"], "phase": a["phase"], "phase_label": a["phase_label"],
                          "manip": man["risk"], "manip_level": man["level"], "rr": pl["rr"], "price": f.c[i],
                          "entry_low": pl["entry_low"], "entry_high": pl["entry_high"], "entry": pl["entry"],
                          "trigger": pl["trigger_breakout"], "stop": pl["stop"],
                          "tp": (pl["tp1"], pl["tp2"], pl["tp3"]), "avg_vol": a["metrics"]["avg_volume_usd"]})
        out[t] = {"regime": reg["regime"], "breadth": breadth, "cands": cands}
        if log and n % 100 == 0:
            log(f"señales {day(t)} régimen {reg['regime']} universo {len(uni)} candidatas {len(cands)}")
    return out, samples


def _action(cd, regime_name, c, policy):
    ev = {"phase": cd["phase"], "score": cd["score"] - c["min_score_offset"], "phase_label": cd["phase_label"]}
    pl = {"rr": cd["rr"], "entry_high": cd["entry_high"], "trigger_breakout": cd["trigger"], "_price": cd["price"]}
    man = {"risk": cd["manip"], "level": cd["manip_level"]}
    return engine.action_for(ev, pl, man, regime_name, {"min_risk_reward": c["min_risk_reward"]}, policy)


def simulate(mk, sig, start=None, end=None, cfg=None, policy=None):
    """Simula la cartera sobre las señales precalculadas. Devuelve métricas, registro de operaciones y curva."""
    c = dict(DEFAULTS); c.update(cfg or {})
    pol = policy or regime_mod.POLICY
    L = dict(portfolio.DEFAULT_LIMITS); L.update(c["limits"])
    cost = (c["slippage_pct"] + c["spread_pct"] / 2) / 100
    fee = c["fee_pct"] / 100
    days = [t for t in mk.days if t in sig and (start is None or t >= start) and (end is None or t <= end)]
    cash, peak = c["capital"], c["capital"]
    pos, orders, trades, curve, expo, fills_log = {}, {}, [], [], [], []
    fees_total, ambiguous, cancelled, rejected = 0.0, 0, 0, {}
    pause_until, dd_pauses = None, 0
    btc0 = None
    bench = []

    def sell(p, frac, px, t, why):
        nonlocal cash, fees_total
        q = p["qty"] if frac >= 0.999 else p["qty"] * frac
        q = min(q, p["qty"])
        gross = q * px; f_ = gross * fee
        cash += gross - f_; fees_total += f_
        p["qty"] -= q; p["proceeds"] += gross - f_; p["fees"] += f_
        p["fills"].append({"date": day(t), "side": "SELL", "qty": q, "price": px, "reason": why})
        p["exit_reason"] = why

    def close_trade(sym, t):
        p = pos.pop(sym)
        pnl = p["proceeds"] - p["cost"]
        trades.append({"symbol": sym, "entry_date": p["entry_date"], "exit_date": day(t), "entry": p["entry"],
                       "stop_initial": p["init_stop"], "qty": p["qty0"], "cost_usd": round(p["cost"], 2),
                       "proceeds_usd": round(p["proceeds"], 2), "pnl_usd": round(pnl, 2),
                       "R": round(pnl / p["risk0"], 3) if p["risk0"] else None, "fees_usd": round(p["fees"], 2),
                       "regime": p["regime"], "phase": p["phase"], "score": p["score"], "cap_bucket": p["bucket"],
                       "exit_reason": (p["exit_reason"] or "").split(" — ")[0], "exit_detail": p["exit_reason"], "ambiguous_bar": p["ambiguous"], "tp_hits": p["tp_hit"],
                       "days_held": (dt.date.fromisoformat(day(t)) - dt.date.fromisoformat(p["entry_date"])).days,
                       "fills": p["fills"]})

    last_t = None
    for t in days:
        # 1) ejecuciones a la apertura y durante la vela de hoy
        for sym in list(pos):
            p = pos[sym]; i = mk.i(sym, t)
            f = mk.f[sym]
            if i is None:
                # sin vela hoy: si la serie terminó (retirada), salir al último cierre con un 10 % de castigo
                if p["last_i"] >= len(f.c) - 1:
                    sell(p, 1.0, f.c[p["last_i"]] * 0.9, t, "Retirada del mercado (último cierre −10 %)")
                    close_trade(sym, t)
                continue
            o, h, l = f.o[i], f.h[i], f.l[i]
            if p.get("pending_exit"):
                frac, why = p.pop("pending_exit")
                sell(p, frac, o * (1 - cost), t, why)
                if p["qty"] <= 1e-12:
                    close_trade(sym, t); continue
            tps = p["tp"]
            nxt_tp = tps[p["tp_hit"]] if p["tp_hit"] < 3 and c["partials"] else None
            if o <= p["stop"]:
                sell(p, 1.0, o * (1 - cost), t, "Stop (hueco en la apertura)"); close_trade(sym, t); continue
            if l <= p["stop"]:
                if nxt_tp and h >= nxt_tp:
                    ambiguous += 1; p["ambiguous"] = True
                why = "Stop a la entrada tras TP1" if p["tp_hit"] and p["stop"] >= p["entry"] else "Stop"
                sell(p, 1.0, p["stop"] * (1 - cost), t, why); close_trade(sym, t); continue
            while nxt_tp and h >= nxt_tp and p["qty"] > 0:
                k = p["tp_hit"]
                frac = c["partials"][k] / (1 - sum(c["partials"][:k])) if k < 2 else 1.0
                sell(p, frac, max(o, nxt_tp) * (1 - cost), t, f"TP{k + 1}")
                p["tp_hit"] += 1
                if p["tp_hit"] == 1:
                    p["stop"] = max(p["stop"], p["entry"])
                nxt_tp = tps[p["tp_hit"]] if p["tp_hit"] < 3 else None
            if p["qty"] <= 1e-12:
                close_trade(sym, t)

        for sym in list(orders):
            od = orders[sym]; i = mk.i(sym, t)
            if i is None:
                continue
            f = mk.f[sym]
            o, h, l = f.o[i], f.h[i], f.l[i]
            od["age"] += 1
            px = None
            if od["kind"] == "limit" and l <= od["price"]:
                px = min(o, od["price"]) * (1 + cost)
            elif od["kind"] == "stop" and h >= od["price"]:
                px = max(o, od["price"]) * (1 + cost)
            if px is None:
                if od["age"] >= c["order_expiry_days"]:
                    orders.pop(sym); cancelled += 1
                continue
            orders.pop(sym)
            if px <= od["stop"]:
                cancelled += 1; continue
            qty = od["value"] / od["price"]
            gross = qty * px
            if gross * (1 + fee) > cash:
                qty = cash / (px * (1 + fee)); gross = qty * px
            if gross < L["min_order_usd"]:
                cancelled += 1; continue
            f_ = gross * fee
            cash -= gross + f_; fees_total += f_
            p = {"qty": qty, "qty0": qty, "entry": px, "stop": od["stop"], "init_stop": od["stop"], "tp": od["tp"],
                 "tp_hit": 0, "risk0": qty * (px - od["stop"]), "cost": gross + f_, "proceeds": 0.0, "fees": f_,
                 "entry_date": day(t), "regime": od["regime"], "phase": od["phase"], "score": od["score"],
                 "bucket": od["bucket"], "highest_close": f.c[i], "reduced": False, "ambiguous": False,
                 "exit_reason": None, "last_i": i, "fills": [{"date": day(t), "side": "BUY", "qty": qty, "price": px,
                                                              "reason": od["why"]}]}
            pos[sym] = p
            if l <= p["stop"]:   # vela de entrada: el stop manda (pesimista)
                sell(p, 1.0, p["stop"] * (1 - cost), t, "Stop el mismo día de la entrada"); close_trade(sym, t)

        # 2) cierre: valoración a mercado
        inv = 0.0
        for sym, p in pos.items():
            i = mk.i(sym, t)
            if i is not None:
                p["last_i"] = i
            inv += p["qty"] * mk.f[sym].c[p["last_i"]]
        reserved = sum(od["value"] * (1 + fee) for od in orders.values())
        eq = cash + inv
        peak = max(peak, eq)
        # protección por drawdown sin bloqueo permanente: al tocar el límite se pausa N días y luego se toma
        # el capital de ese momento como nuevo máximo (si no, sin operaciones nunca se recuperaría)
        if pause_until is None and peak and (1 - eq / peak) * 100 >= L["dd_stop_pct"]:
            pause_until = t + c["dd_cooldown_days"] * DAY_MS; dd_pauses += 1
        elif pause_until is not None and t >= pause_until:
            pause_until = None; peak = eq
        curve.append((day(t), eq)); expo.append(inv / eq * 100 if eq else 0)
        bi = mk.i("BTC", t)
        if bi is not None:
            btc0 = btc0 or mk.btc.c[bi]
            bench.append((day(t), c["capital"] * mk.btc.c[bi] / btc0))
        reg = sig[t]["regime"]

        # 3) Exit Intelligence al cierre (se ejecuta mañana a la apertura)
        for sym, p in pos.items():
            i = mk.i(sym, t)
            if i is None:
                continue
            f = mk.f[sym]
            p["highest_close"] = max(p["highest_close"], f.c[i])
            if c["max_hold_days"] and (dt.date.fromisoformat(day(t)) - dt.date.fromisoformat(p["entry_date"])).days >= c["max_hold_days"]:
                p["pending_exit"] = (1.0, "Tiempo máximo de tenencia"); continue
            if not c["use_exit_intelligence"]:
                continue
            d = exits.decide(f, i, {"entry": p["entry"], "stop": p["stop"], "highest_close": p["highest_close"]}, reg)
            p["stop"] = max(p["stop"], d["suggested_stop"])
            if d["decision"] == "CERRAR POSICIÓN":
                p["pending_exit"] = (1.0, "Exit Intelligence: cerrar — " + "; ".join(d["reasons"][:2]))
            elif d["decision"] == "REDUCIR POSICIÓN" and not p["reduced"]:
                p["reduced"] = True
                p["pending_exit"] = (0.33, "Exit Intelligence: reducir — " + "; ".join(d["reasons"][:2]))

        # 4) señales nuevas: órdenes para mañana
        open_list = [{"value": p["qty"] * mk.f[s].c[p["last_i"]], "category": None, "is_alt": s not in NOT_ALT,
                      "risk_usd": max(0.0, p["qty"] * (mk.f[s].c[p["last_i"]] - p["stop"]))} for s, p in pos.items()]
        open_list += [{"value": od["value"], "risk_usd": od["risk_usd"], "category": None, "is_alt": s not in NOT_ALT}
                      for s, od in orders.items()]
        free_cash = cash - reserved
        for cd in sorted(sig[t]["cands"], key=lambda x: -x["score"]):
            sym = cd["sym"]
            if sym in pos or sym in orders:
                continue
            act, why = _action(cd, reg, c, pol)
            if act not in BUY_ACTIONS:
                continue
            kind, price = ("stop", cd["trigger"]) if act == "ESPERAR RUPTURA" else \
                ("limit", cd["entry_high"] if act == "COMPRAR EN ZONA" else cd["entry"])
            if not price or price <= cd["stop"]:
                continue
            corr = [portfolio.correlation(mk.f[sym], cd["i"], mk.f[s], mk.i(s, t)) for s in pos if mk.i(s, t) is not None]
            r = portfolio.size(eq, peak, free_cash, price, cd["stop"], open_list, L, pol[reg]["size_mult"], None,
                               cd["avg_vol"], pol[reg]["max_alt_exposure"], sym not in NOT_ALT, corr)
            if not r["ok"]:
                key = r["reasons"][-1].split(":")[0].split(" ")[0]
                rejected[key] = rejected.get(key, 0) + 1
                continue
            orders[sym] = {"kind": kind, "price": price, "stop": cd["stop"], "tp": cd["tp"], "value": r["value"],
                           "risk_usd": r["risk_usd"], "age": 0, "regime": reg, "phase": cd["phase"],
                           "score": cd["score"], "bucket": bucket(cd["avg_vol"]), "why": act}
            free_cash -= r["value"] * (1 + fee)
            open_list.append({"value": r["value"], "risk_usd": r["risk_usd"], "category": None,
                              "is_alt": sym not in NOT_ALT})
        last_t = t

    if last_t is not None:
        for sym in list(pos):
            p = pos[sym]
            sell(p, 1.0, mk.f[sym].c[p["last_i"]] * (1 - cost), last_t, "Fin del periodo (cierre a mercado)")
            close_trade(sym, last_t)
        if curve:
            curve[-1] = (curve[-1][0], cash)
    m = metrics.compute(trades, curve, c["capital"], fees_total, expo, bench)
    m.update({"drawdown_pauses": dd_pauses, "ambiguous_bars": ambiguous, "orders_cancelled": cancelled, "orders_rejected_by_limits": rejected})
    return {"metrics": m, "trades": trades, "curve": curve, "benchmark": bench, "config": {k: v for k, v in c.items()}}


def score_validation(samples):
    """¿La puntuación ordena el futuro? Rendimiento a 20 días por quintil de puntuación, exceso sobre la media
    del universo del mismo día, por fase y correlación por rangos (IC) de cada familia."""
    if not samples:
        return {}
    by_t = {}
    for s in samples:
        by_t.setdefault(s["t"], []).append(s["fwd"])
    mean_t = {t: sum(v) / len(v) for t, v in by_t.items()}
    for s in samples:
        s["ex"] = s["fwd"] - mean_t[s["t"]]
    ss = sorted(samples, key=lambda s: s["score"])
    q = []
    for k in range(5):
        part = ss[k * len(ss) // 5:(k + 1) * len(ss) // 5]
        if part:
            q.append({"quintile": k + 1, "score_min": part[0]["score"], "score_max": part[-1]["score"], "n": len(part),
                      "fwd20_mean_pct": round(sum(p["fwd"] for p in part) / len(part) * 100, 2),
                      "fwd20_median_pct": round(sorted(p["fwd"] for p in part)[len(part) // 2] * 100, 2),
                      "excess_mean_pct": round(sum(p["ex"] for p in part) / len(part) * 100, 2),
                      "hit_rate_pct": round(sum(p["ex"] > 0 for p in part) / len(part) * 100, 1)})
    phases = {}
    for s in samples:
        g = phases.setdefault(s["phase"], [])
        g.append(s["ex"])
    ph = {k: {"n": len(v), "excess_mean_pct": round(sum(v) / len(v) * 100, 2),
              "hit_rate_pct": round(sum(x > 0 for x in v) / len(v) * 100, 1)} for k, v in phases.items()}

    def ic(key):
        xs = [(s["fam"].get(key) if key != "score" else s["score"], s["ex"]) for s in samples]
        xs = [x for x in xs if x[0] is not None]
        if len(xs) < 50:
            return None
        def ranks(v):
            o = sorted(range(len(v)), key=lambda j: v[j]); r = [0] * len(v)
            for k, j in enumerate(o):
                r[j] = k
            return r
        a, b = ranks([x[0] for x in xs]), ranks([x[1] for x in xs])
        n = len(a); ma = mb = (n - 1) / 2
        cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
        va = math.sqrt(sum((x - ma) ** 2 for x in a)); vb = math.sqrt(sum((y - mb) ** 2 for y in b))
        return round(cov / (va * vb), 4) if va and vb else None
    fams = ["score"] + list(early.DEFAULT_WEIGHTS)
    return {"quintiles": q, "by_phase": ph, "rank_ic": {k: ic(k) for k in fams}, "samples": len(samples)}
