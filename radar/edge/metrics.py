"""Métricas calculadas SOLO desde el registro de operaciones y la curva diaria (PREREGISTRO §7 y prompt §7)."""
import math
import numpy as np
import pandas as pd


def daily_returns(curve):
    return curve["equity"].pct_change().dropna()


def sharpe(r):
    return float(r.mean() / r.std() * math.sqrt(365)) if len(r) > 2 and r.std() > 0 else 0.0


def sortino(r):
    d = r[r < 0]
    dd = math.sqrt((d ** 2).sum() / len(r)) if len(r) else 0
    return float(r.mean() / dd * math.sqrt(365)) if dd > 0 else 0.0


def max_dd(eq):
    return float((eq / eq.cummax() - 1).min() * 100) if len(eq) else 0.0


def summarize(res, capital=10_000.0):
    tr = pd.DataFrame(res["trades"]); cv = res["curve"]
    eq = cv["equity"] if len(cv) else pd.Series([capital])
    r = daily_returns(cv) if len(cv) > 1 else pd.Series(dtype=float)
    days = max(1, len(cv))
    total = eq.iloc[-1] / capital - 1
    cagr = (eq.iloc[-1] / capital) ** (365 / days) - 1 if eq.iloc[-1] > 0 else -1
    mdd = max_dd(eq)
    n = len(tr)
    wins = tr[tr.pnl_usd > 0] if n else tr
    losses = tr[tr.pnl_usd <= 0] if n else tr
    gp, gl = (wins.pnl_usd.sum() if n else 0), (-losses.pnl_usd.sum() if n else 0)
    traded = ((tr.cost_usd + tr.exit_px * tr.qty).sum()) if n else 0
    yearly = {}
    if len(eq) > 1:
        for y, s in eq.groupby(eq.index.year):
            first = eq[eq.index < s.index[0]]
            base = first.iloc[-1] if len(first) else capital
            yearly[str(y)] = round((s.iloc[-1] / base - 1) * 100, 2)
    top5 = tr.nlargest(5, "pnl_usd").pnl_usd.sum() if n else 0
    out = {
        "net_return_pct": round(total * 100, 2), "cagr_pct": round(cagr * 100, 2),
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "sharpe": round(sharpe(r), 3), "sortino": round(sortino(r), 3),
        "calmar": round(cagr * 100 / abs(mdd), 3) if mdd < 0 else None,
        "max_drawdown_pct": round(mdd, 2),
        "expectancy_usd": round(tr.pnl_usd.mean(), 2) if n else None,
        "expectancy_R": round(tr.R.dropna().mean(), 3) if n and tr.R.notna().any() else None,
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else None,
        "avg_win_usd": round(wins.pnl_usd.mean(), 2) if len(wins) else None,
        "avg_loss_usd": round(losses.pnl_usd.mean(), 2) if len(losses) else None,
        "trades": n,
        "turnover_x_per_year": round(traded / eq.mean() * 365 / days, 2) if n else 0,
        "avg_exposure_pct": round(cv["exposure"].mean() * 100, 1) if len(cv) else 0,
        "costs_usd": round(res["fees"], 2),
        "avg_days_held": round(tr.days.mean(), 1) if n else None,
        "net_without_top5_usd": round(tr.pnl_usd.sum() - top5, 2) if n else 0,
        "yearly_pct": yearly,
        "by_regime": ({("BTC bajista" if k else "BTC alcista"): {"trades": int(len(g)), "pnl_usd": round(g.pnl_usd.sum(), 2)}
                       for k, g in tr.groupby("bear_at_entry")} if n else {}),
        "by_exit": ({k: {"trades": int(len(g)), "pnl_usd": round(g.pnl_usd.sum(), 2)} for k, g in tr.groupby("exit_reason")}
                    if n else {}),
    }
    return out


def benchmarks(P, F, U, start, end, capital=10_000.0):
    c = P["c"].loc[start:end]
    out = {}
    for s in ("BTC", "ETH"):
        x = c[s].dropna()
        eq = x / x.iloc[0] * capital
        r = eq.pct_change().dropna()
        out[f"{s} comprar y mantener"] = {"net_return_pct": round((eq.iloc[-1] / capital - 1) * 100, 2),
                                         "cagr_pct": round(((eq.iloc[-1] / capital) ** (365 / len(eq)) - 1) * 100, 2),
                                         "sharpe": round(sharpe(r), 3), "max_drawdown_pct": round(max_dd(eq), 2)}
    # equiponderada: top 50 por volumen del universo, rebalanceo mensual, 0,2 % de coste por rebalanceo
    adv = F["adv30"].where(U).loc[start:end]
    rets = P["c"].pct_change(fill_method=None).loc[start:end]
    eq, val, members = [], capital, None
    for d in rets.index:
        if members is None or d.day == 1:
            prev = adv.index[adv.index < d]
            row = adv.loc[prev[-1]] if len(prev) else adv.loc[d]
            members = row.dropna().nlargest(50).index
            val *= (1 - 0.002)
        rr = rets.loc[d, members].dropna()
        val *= 1 + (rr.clip(lower=-1).mean() if len(rr) else 0)
        eq.append(val)
    eq = pd.Series(eq, index=rets.index)
    out["Equiponderada top 50"] = {"net_return_pct": round((eq.iloc[-1] / capital - 1) * 100, 2),
                                   "cagr_pct": round(((eq.iloc[-1] / capital) ** (365 / len(eq)) - 1) * 100, 2),
                                   "sharpe": round(sharpe(eq.pct_change().dropna()), 3), "max_drawdown_pct": round(max_dd(eq), 2)}
    out["Efectivo"] = {"net_return_pct": 0.0, "cagr_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0}
    return out
