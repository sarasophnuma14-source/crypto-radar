"""Laboratorio de estrategias (spot, solo largo o efectivo, sin apalancamiento).

Metodología anti-autoengaño:
  * Señal al cierre del día d, ejecución al precio de apertura de d+1 (en Binance la
    apertura diaria = cierre anterior, así que se usa retorno cierre→cierre desplazado).
  * Costos: comisión 0,10 % + deslizamiento según liquidez (0,05 % / 0,15 % / 0,30 %).
  * Universo en cada fecha = solo monedas con historial y volumen suficiente ESE día
    (incluye monedas que luego fueron pausadas/retiradas si siguen en la lista de Binance).
  * Se elige la configuración usando SOLO el periodo de diseño (2021–2024).
    El periodo 2025→hoy se mira una única vez al final, sin volver a ajustar.
"""
import gzip, itertools, json, math, sys
from pathlib import Path

import numpy as np
import pandas as pd

FEE = 0.001
DESIGN = ("2021-01-01", "2024-12-31")
HOLDOUT = ("2025-01-01", "2100-01-01")


# ---------------------------------------------------------------- datos
def load_panel(path):
    with gzip.open(path, "rt") as g:
        raw = json.load(g)
    frames = {k: {} for k in "ohlcv"}
    status = {}
    for sym, h in raw.items():
        idx = pd.to_datetime(h["t"], unit="ms").normalize()
        for k in "ohlcv":
            frames[k][sym] = pd.Series(h[k], index=idx)
        status[sym] = h.get("status", "TRADING")
    P = {k: pd.DataFrame(v).sort_index() for k, v in frames.items()}
    full = pd.date_range(P["c"].index.min(), P["c"].index.max(), freq="D")
    P = {k: v.reindex(full) for k, v in P.items()}
    P["status"] = status
    return P


def derived(P):
    c = P["c"]
    D = {}
    D["ret"] = c.pct_change(fill_method=None)
    D["vol30"] = P["v"].rolling(30, min_periods=20).mean()
    D["age"] = c.notna().cumsum()
    # deslizamiento por liquidez (fracción por lado)
    v = D["vol30"]
    D["slip"] = pd.DataFrame(np.where(v > 1e8, 0.0005, np.where(v > 2e7, 0.0015, 0.003)), index=c.index, columns=c.columns)
    return D


# ---------------------------------------------------------------- métricas
def stats(eq, frm, to, trades=None):
    e = eq[(eq.index >= frm) & (eq.index <= to)]
    if len(e) < 10:
        return None
    r = e.pct_change().dropna()
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    tot = e.iloc[-1] / e.iloc[0] - 1
    cagr = (e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else 0
    dd = (e / e.cummax() - 1).min()
    sharpe = r.mean() / r.std() * math.sqrt(365) if r.std() > 0 else 0
    out = {"retorno_pct": round(tot * 100, 1), "cagr_pct": round(cagr * 100, 1), "max_dd_pct": round(dd * 100, 1),
           "sharpe": round(sharpe, 2), "calmar": round(cagr / abs(dd), 2) if dd < 0 else 0}
    if trades is not None:
        tr = trades[(trades["entrada"] >= frm) & (trades["entrada"] <= to)]
        out["operaciones"] = int(len(tr))
        if len(tr):
            w = tr[tr["pnl_pct"] > 0]["pnl_pct"].sum(); l = -tr[tr["pnl_pct"] <= 0]["pnl_pct"].sum()
            out["acierto_pct"] = round((tr["pnl_pct"] > 0).mean() * 100, 1)
            out["profit_factor"] = round(w / l, 2) if l > 0 else 99.0
    return out


# ---------------------------------------------------------------- motor por pesos (rotación / tendencia)
def run_weights(W, P, D, start):
    """W: DataFrame de pesos objetivo decididos al cierre de cada día (filas suman ≤1).
    Devuelve curva de capital (1.0 inicial) y lista de operaciones (aprox. por tramos)."""
    W = W.loc[W.index >= start].fillna(0.0)
    ret = D["ret"].reindex(W.index).fillna(0.0)
    slip = D["slip"].reindex(W.index)
    held = W.shift(1).fillna(0.0)                     # lo decidido ayer se gana hoy
    gross = (held * ret).sum(axis=1)
    # deriva de pesos dentro del día para medir rotación real
    drift = held * (1 + ret)
    drift = drift.div((1 + gross).replace(0, 1), axis=0)
    turn = (W - drift.shift(0)).abs()
    turn.iloc[0] = W.iloc[0].abs()
    cost = (turn * (FEE + slip.fillna(0.003))).sum(axis=1)
    net = gross - cost.shift(1).fillna(0.0)            # el costo se paga al ejecutar (día siguiente)
    eq = (1 + net).cumprod()
    # operaciones: tramos continuos con peso > 0
    rows = []
    Wb = W > 0
    for sym in W.columns[Wb.any()]:
        s = Wb[sym].values; idx = W.index
        i = 0
        while i < len(s):
            if s[i]:
                j = i
                while j + 1 < len(s) and s[j + 1]:
                    j += 1
                seg = ret[sym].iloc[i + 1: j + 2]
                pnl = float((1 + seg).prod() - 1) - 2 * (FEE + 0.0015)
                rows.append({"simbolo": sym, "señal": idx[i], "entrada": idx[min(i + 1, len(idx) - 1)],
                             "salida": idx[min(j + 1, len(idx) - 1)], "pnl_pct": pnl * 100})
                i = j + 1
            else:
                i += 1
    return eq, pd.DataFrame(rows, columns=["simbolo", "señal", "entrada", "salida", "pnl_pct"])


# ---------------------------------------------------------------- familias
def btc_filter(P, n):
    c = P["c"]["BTC"]
    if not n:
        return pd.Series(True, index=c.index)
    return c > c.rolling(n).mean()


def strat_btc_trend(P, D, n=None, fast=None, slow=None, asset="BTC"):
    c = P["c"][asset]
    if fast:
        sig = c.ewm(span=fast, adjust=False).mean() > c.ewm(span=slow, adjust=False).mean()
    else:
        sig = c > c.rolling(n).mean()
    W = pd.DataFrame(0.0, index=c.index, columns=P["c"].columns)
    W[asset] = sig.astype(float)
    return W


def strat_rotation(P, D, look=30, top=5, reb=7, regime=100, min_vol=2e7, min_age=60, abs_mom=True, skip=0):
    c = P["c"]
    mom = c.shift(skip) / c.shift(skip + look) - 1
    ok = (D["vol30"] >= min_vol) & (D["age"] >= max(min_age, look + 5)) & c.notna()
    mom = mom.where(ok)
    reg = btc_filter(P, regime)
    W = pd.DataFrame(np.nan, index=c.index, columns=c.columns)
    dates = c.index
    for k in range(0, len(dates), reb):
        d = dates[k]
        row = pd.Series(0.0, index=c.columns)
        if reg.get(d, False):
            m = mom.loc[d].dropna()
            if abs_mom:
                m = m[m > 0]
            pick = m.nlargest(top).index
            if len(pick):
                row[pick] = 1.0 / top          # posiciones vacías quedan en efectivo
        W.loc[d] = row
    W = W.ffill().fillna(0.0)
    # si la moneda deja de cotizar, ese peso pasa a efectivo
    W = W.where(c.notna(), 0.0)
    # salida diaria por régimen (no esperar al rebalanceo si BTC pierde la media)
    W = W.mul(reg.astype(float), axis=0)
    return W


def strat_breakout(P, D, n=55, atr_k=3.0, regime=100, min_vol=2e7, risk=0.01, max_pos=10, max_w=0.15, start=None):
    """Ruptura de máximo de N días + stop dinámico de k·ATR (tortuga). Simulación por eventos."""
    c, h, l, o = P["c"], P["h"], P["l"], P["o"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()]).groupby(level=0).max()
    atr = tr.reindex(c.index).rolling(20).mean()
    hh = h.rolling(n).max().shift(1)
    reg = btc_filter(P, regime)
    ok = (D["vol30"] >= min_vol) & (D["age"] >= n + 20)
    sig = (c > hh) & ok
    slipdf = D["slip"]
    dates = c.index if start is None else c.index[c.index >= start]
    cash, pos, eqs, trades = 1.0, {}, [], []
    for i, d in enumerate(dates[:-1]):
        nd = dates[i + 1]
        # 1) gestionar posiciones abiertas en el día nd (stop intradía)
        for sym in list(pos):
            p = pos[sym]
            lo, op, cl = l.at[nd, sym], o.at[nd, sym], c.at[nd, sym]
            if np.isnan(cl):           # dejó de cotizar: salir al último cierre conocido
                px = p["last"] * (1 - slipdf.at[d, sym])
                cash += p["q"] * px * (1 - FEE)
                trades.append({**p["info"], "salida": nd, "precio_salida": px, "motivo": "deslistado",
                               "pnl_pct": (px * (1 - FEE) / p["cost"] - 1) * 100}); del pos[sym]; continue
            if lo <= p["stop"]:
                px = min(op, p["stop"]) * (1 - slipdf.at[d, sym])
                cash += p["q"] * px * (1 - FEE)
                trades.append({**p["info"], "salida": nd, "precio_salida": px, "motivo": "stop",
                               "pnl_pct": (px * (1 - FEE) / p["cost"] - 1) * 100}); del pos[sym]; continue
            p["last"] = cl
            a = atr.at[nd, sym]
            if not np.isnan(a):
                p["stop"] = max(p["stop"], cl - atr_k * a)
        # 2) valor de cartera al cierre de nd
        val = cash + sum(p["q"] * p["last"] for p in pos.values())
        eqs.append((nd, val))
        # 3) salida por régimen: si BTC pierde la media, cerrar todo en la apertura siguiente
        if not reg.get(nd, False) and pos and i + 2 < len(dates):
            n2 = dates[i + 2]
            for sym in list(pos):
                p = pos[sym]; op = o.at[n2, sym]
                px = (op if not np.isnan(op) else p["last"]) * (1 - slipdf.at[nd, sym])
                cash += p["q"] * px * (1 - FEE)
                trades.append({**p["info"], "salida": n2, "precio_salida": px, "motivo": "régimen",
                               "pnl_pct": (px * (1 - FEE) / p["cost"] - 1) * 100}); del pos[sym]
            continue
        # 4) nuevas entradas (señal al cierre de nd, compra en apertura de nd+1)
        if i + 2 >= len(dates) or not reg.get(nd, False) or len(pos) >= max_pos:
            continue
        n2 = dates[i + 2]
        cands = sig.loc[nd]
        cands = cands[cands].index.difference(list(pos))
        if not len(cands):
            continue
        # prioridad: mayor fuerza relativa (distancia al máximo en ATR)
        strength = ((c.loc[nd, cands] - hh.loc[nd, cands]) / atr.loc[nd, cands]).sort_values(ascending=False)
        for sym in strength.index:
            if len(pos) >= max_pos:
                break
            op, a = o.at[n2, sym], atr.at[nd, sym]
            if np.isnan(op) or np.isnan(a) or a <= 0:
                continue
            px = op * (1 + slipdf.at[nd, sym])
            stop = px - atr_k * a
            per_unit = px - stop
            q = min(val * risk / per_unit, val * max_w / px, cash / (px * (1 + FEE)))
            if q * px < val * 0.01:
                continue
            cost = q * px * (1 + FEE)
            cash -= cost
            pos[sym] = {"q": q, "stop": stop, "last": op, "cost": px * (1 + FEE),
                        "info": {"simbolo": sym, "señal": nd, "entrada": n2, "precio_entrada": px, "stop_inicial": stop}}
    eq = pd.Series(dict(eqs)).sort_index()
    return eq, pd.DataFrame(trades)


def strat_meanrev(P, D, rsi_n=2, buy_below=10, exit_sma=5, trend=200, max_days=10, top_liq=15, max_pos=5):
    c = P["c"]
    delta = c.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / rsi_n, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(alpha=1 / rsi_n, adjust=False).mean()
    rsi = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    trend_ok = c > c.rolling(trend).mean()
    liq_rank = D["vol30"].rank(axis=1, ascending=False)
    elig = (liq_rank <= top_liq) & trend_ok & (D["age"] >= trend)
    entry = elig & (rsi < buy_below)
    ex = c > c.rolling(exit_sma).mean()
    W = pd.DataFrame(0.0, index=c.index, columns=c.columns)
    held, since = set(), {}
    for d in c.index:
        for s in list(held):
            since[s] += 1
            if ex.at[d, s] or since[s] >= max_days or np.isnan(c.at[d, s]):
                held.discard(s)
        if len(held) < max_pos:
            cands = entry.loc[d]
            for s in rsi.loc[d, cands[cands].index].sort_values().index:
                if len(held) >= max_pos:
                    break
                if s not in held:
                    held.add(s); since[s] = 0
        for s in held:
            W.at[d, s] = 1.0 / max_pos
    return W


# ---------------------------------------------------------------- búsqueda
def grid(P, D, warm="2020-06-01", log=print):
    res = []
    def add(fam, params, eq, trades=None):
        r = {"familia": fam, "params": params, "diseño": stats(eq, *DESIGN, trades)}
        res.append(r)
        return r

    for n in (20, 50, 100, 150, 200):
        add("Tendencia BTC (media simple)", {"n": n}, *run_weights(strat_btc_trend(P, D, n=n), P, D, warm))
    for f, s in ((10, 30), (20, 50), (20, 100), (50, 200)):
        add("Tendencia BTC (cruce EMAs)", {"rápida": f, "lenta": s}, *run_weights(strat_btc_trend(P, D, fast=f, slow=s), P, D, warm))
    log("tendencia BTC lista")
    for look, top, regime, mv in itertools.product((14, 30, 60, 90), (3, 5, 10), (0, 50, 100, 200), (5e6, 2e7)):
        W = strat_rotation(P, D, look=look, top=top, regime=regime, min_vol=mv)
        add("Rotación por momentum", {"ventana": look, "top": top, "filtro_btc_sma": regime, "vol_min": mv}, *run_weights(W, P, D, warm))
    log("rotación lista")
    for n, k, regime in itertools.product((20, 55, 100), (2.0, 3.0, 4.0), (0, 100, 200)):
        eq, tr = strat_breakout(P, D, n=n, atr_k=k, regime=regime, start=warm)
        add("Ruptura + stop ATR", {"n": n, "atr_k": k, "filtro_btc_sma": regime}, eq, tr)
    log("rupturas listas")
    for bb, top in itertools.product((5, 10, 20), (5, 15)):
        W = strat_meanrev(P, D, buy_below=bb, top_liq=top)
        add("Reversión RSI(2)", {"rsi_bajo": bb, "top_liquidez": top}, *run_weights(W, P, D, warm))
    log("reversión lista")
    return res


def rebuild(P, D, fam, params, warm="2020-06-01"):
    if fam == "Tendencia BTC (media simple)":
        return run_weights(strat_btc_trend(P, D, n=params["n"]), P, D, warm)
    if fam == "Tendencia BTC (cruce EMAs)":
        return run_weights(strat_btc_trend(P, D, fast=params["rápida"], slow=params["lenta"]), P, D, warm)
    if fam == "Rotación por momentum":
        return run_weights(strat_rotation(P, D, look=params["ventana"], top=params["top"], regime=params["filtro_btc_sma"],
                                          min_vol=params["vol_min"]), P, D, warm)
    if fam == "Ruptura + stop ATR":
        return strat_breakout(P, D, n=params["n"], atr_k=params["atr_k"], regime=params["filtro_btc_sma"], start=warm)
    if fam == "Reversión RSI(2)":
        return run_weights(strat_meanrev(P, D, buy_below=params["rsi_bajo"], top_liq=params["top_liquidez"]), P, D, warm)
    raise ValueError(fam)




def study(panel_path, out_dir, log=print, holdout=False):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    P = load_panel(panel_path); D = derived(P)
    res = grid(P, D, log=log)
    res = [r for r in res if r["diseño"]]
    # elección SOLO con el periodo de diseño: mejor Sharpe por familia (con ≥20 operaciones si aplica)
    fams = {}
    for r in res:
        fams.setdefault(r["familia"], []).append(r)
    chosen = {}
    for f, rs in fams.items():
        ok = [r for r in rs if r["diseño"].get("operaciones", 99) >= 20] or rs
        best = max(ok, key=lambda r: r["diseño"]["sharpe"])
        sh = sorted(r["diseño"]["sharpe"] for r in rs)
        best["familia_sharpe_mediana"] = sh[len(sh) // 2]
        best["configs_probadas"] = len(rs)
        chosen[f] = best
    if not holdout:
        summary = {"configs_totales": len(res), "elegidas": chosen}
        (out / "diseño.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=float))
        (out / "todas_las_configs.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float))
        return summary
    # prueba a ciegas: una sola vez por familia
    for f, r in chosen.items():
        eq, tr = rebuild(P, D, f, r["params"])
        r["prueba_2025_hoy"] = stats(eq, *HOLDOUT, tr if len(tr) else None)
        r["total_2021_hoy"] = stats(eq, DESIGN[0], HOLDOUT[1], tr if len(tr) else None)
        slug = f.split(" ")[0].lower()
        eq.to_csv(out / f"curva_{slug}.csv", header=["capital"])
        if len(tr):
            tr.to_csv(out / f"operaciones_{slug}.csv", index=False)
    btc = P["c"]["BTC"].dropna()
    bench = {"BTC_comprar_mantener": {"diseño": stats(btc, *DESIGN), "prueba_2025_hoy": stats(btc, *HOLDOUT)}}
    summary = {"configs_totales": len(res), "elegidas": chosen, "referencia": bench,
               "periodos": {"diseño": DESIGN, "prueba": HOLDOUT}, "monedas": int(P["c"].shape[1])}
    (out / "resultados.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, default=float))
    (out / "todas_las_configs.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float))
    return summary


if __name__ == "__main__":
    s = study(sys.argv[1], sys.argv[2], holdout=len(sys.argv) > 3 and sys.argv[3] == "holdout")
    print(json.dumps({f: {k: r.get(k) for k in ("params", "diseño", "familia_sharpe_mediana", "prueba_2025_hoy")} for f, r in s["elegidas"].items()}, ensure_ascii=False, indent=1, default=float))


def vol_target(eq_btc_w, P, D, target=0.5, lb=30):
    """Escala la exposición de BTC para apuntar a una volatilidad anual fija (máx. 100 %, sin apalancamiento)."""
    r = D["ret"]["BTC"]
    vol = r.rolling(lb).std() * math.sqrt(365)
    scale = (target / vol).clip(upper=1.0).fillna(0)
    W = eq_btc_w.copy(); W["BTC"] = W["BTC"] * scale
    return W


def blend(curves, weights, monthly_cost=0.002):
    """Cartera que reparte el capital entre estrategias y se rebalancea cada mes (con costo)."""
    df = pd.concat(curves, axis=1).dropna()
    rets = df.pct_change().fillna(0)
    port = (rets * weights).sum(axis=1)
    month_start = df.index.to_series().dt.is_month_start
    port = port - month_start.astype(float) * monthly_cost * 0.25   # ~25 % del capital se mueve al rebalancear
    return (1 + port).cumprod()
