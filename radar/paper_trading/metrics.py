"""Métricas del paper trading (solo desde el diario guardado) y criterios de aceptación de la Fase 8.

Los criterios son FILTROS MÍNIMOS, no garantías: cumplirlos no asegura beneficios futuros.
"""
import math
import numpy as np
import pandas as pd

BTC_KEY = "BTC comprar y mantener"


def _sharpe(r):
    return float(r.mean() / r.std() * math.sqrt(365)) if len(r) > 2 and r.std() > 0 else 0.0


def _sortino(r):
    d = r[r < 0]
    dd = math.sqrt((d ** 2).sum() / len(r)) if len(r) else 0
    return float(r.mean() / dd * math.sqrt(365)) if dd > 0 else 0.0


def _mdd(eq):
    return float((eq / eq.cummax() - 1).min() * 100) if len(eq) else 0.0


def acceptance(m, elevated=None, stress=None, sub=None, p_adj=None, sharpe_ci_low=None, bench=None, prospective=True,
               days=None, min_days=183):
    """m: dict con net_return_pct, sharpe, profit_factor, max_drawdown_pct, expectancy_usd, trades."""
    sub = sub or {}
    btc = (bench or {}).get(BTC_KEY, {})
    pf = m.get("profit_factor") or 0
    checks = {
        "retorno_neto_positivo": (m.get("net_return_pct") or 0) > 0,
        "sharpe_mayor_0_75": (m.get("sharpe") or 0) > 0.75,
        "profit_factor_mayor_1_15": pf > 1.15,
        "drawdown_controlado_max_25": (m.get("max_drawdown_pct") or -100) >= -25,
        "expectativa_positiva": (m.get("expectancy_usd") or 0) > 0,
        "subperiodos_estables": bool(sub) and sum(1 for v in sub.values() if v is not None and v > 0) >= math.ceil(2 * len(sub) / 3),
        "robusto_a_costes_x2": bool(elevated) and (elevated.get("net_return_pct") or 0) > 0 and (elevated.get("profit_factor") or 0) > 1.0,
        "evidencia_estadistica": p_adj is not None and p_adj < 0.05 and sharpe_ci_low is not None and sharpe_ci_low > 0,
        "mejor_que_efectivo": (m.get("net_return_pct") or 0) > 0,
        "mejor_que_btc_ajustado_a_riesgo": bool(btc) and (m.get("sharpe") or 0) > (btc.get("sharpe") or 0),
        "resultados_prospectivos_reproducibles": bool(prospective) and (days or 0) >= min_days,
        "operaciones_suficientes_30": (m.get("trades") or 0) >= 30,
    }
    info = {"costes_x3": {k: (stress or {}).get(k) for k in ("net_return_pct", "profit_factor")} if stress else None}
    ok = all(checks.values())
    return {"checks": checks, "passed": sum(checks.values()), "total": len(checks),
            "verdict": "CUMPLE LOS FILTROS MÍNIMOS (no es una garantía)" if ok else "NO CUMPLE: no hay evidencia suficiente de ventaja",
            "info": info}


def compute(equity_rows, trades, spec):
    cap = spec["risk"]["capital"]
    if not equity_rows:
        return {"days": 0, "note": "sin días procesados"}
    eq = pd.DataFrame(equity_rows); eq.index = pd.to_datetime(eq["date"])
    e = eq["equity"]; r = e.pct_change().fillna(e.iloc[0] / cap - 1)
    days = len(e)
    total = e.iloc[-1] / cap - 1
    cagr = (e.iloc[-1] / cap) ** (365 / days) - 1 if days >= 30 and e.iloc[-1] > 0 else None
    tr = pd.DataFrame(trades)
    n = len(tr)
    wins = tr[tr.pnl_usd > 0] if n else tr; losses = tr[tr.pnl_usd <= 0] if n else tr
    gp = float(wins.pnl_usd.sum()) if n else 0.0; gl = float(-losses.pnl_usd.sum()) if n else 0.0
    btc = eq["btc_bh_equity"]; rb = btc.pct_change().fillna(0)
    costs = float(tr.fees_usd.sum()) if n else 0.0
    m = {
        "days": days, "start": eq["date"].iloc[0], "end": eq["date"].iloc[-1],
        "equity_usd": round(float(e.iloc[-1]), 2), "net_return_pct": round(total * 100, 2),
        "cagr_pct": round(cagr * 100, 2) if cagr is not None else None,
        "sharpe": round(_sharpe(r), 3), "sortino": round(_sortino(r), 3),
        "profit_factor": round(gp / gl, 3) if gl > 0 else None,
        "expectancy_usd": round(float(tr.pnl_usd.mean()), 2) if n else None,
        "expectancy_R": round(float(tr.R.dropna().mean()), 3) if n and tr.R.notna().any() else None,
        "max_drawdown_pct": round(_mdd(e), 2),
        "win_rate_pct": round(len(wins) / n * 100, 1) if n else None,
        "avg_win_usd": round(float(wins.pnl_usd.mean()), 2) if len(wins) else None,
        "avg_loss_usd": round(float(losses.pnl_usd.mean()), 2) if len(losses) else None,
        "trades": n, "open_positions": int(eq["positions"].iloc[-1]),
        "avg_exposure_pct": round(float(eq["exposure"].mean()) * 100, 2),
        "portfolio_vol_ann_pct": round(float(r.std() * math.sqrt(365)) * 100, 2) if days > 2 else None,
        "costs_usd": round(costs, 2),
        "monthly_pct": {},
        "by_regime_days": {}, "by_regime_trades": {},
        "vs": {"BTC comprar y mantener": {"net_return_pct": round((btc.iloc[-1] / cap - 1) * 100, 2), "sharpe": round(_sharpe(rb), 3),
                                          "max_drawdown_pct": round(_mdd(btc), 2)},
               "Efectivo": {"net_return_pct": 0.0, "sharpe": 0.0, "max_drawdown_pct": 0.0}},
    }
    mm = e.resample("ME").last()
    prev = pd.concat([pd.Series([cap], index=[e.index[0] - pd.Timedelta(days=1)]), mm])
    m["monthly_pct"] = {d.strftime("%Y-%m"): round(float(v) * 100, 2) for d, v in prev.pct_change().dropna().items()}
    bear = eq["btc_bear"].shift(1).fillna(False).astype(bool)
    for lab, mask in (("BTC alcista", ~bear), ("BTC bajista", bear)):
        x = r[mask]
        m["by_regime_days"][lab] = {"days": int(len(x)), "cum_pct": round(float((1 + x).prod() - 1) * 100, 2), "sharpe": round(_sharpe(x), 3)}
    if n:
        for k, g in tr.groupby("bear_at_entry"):
            m["by_regime_trades"]["BTC bajista" if k else "BTC alcista"] = {"trades": int(len(g)), "pnl_usd": round(float(g.pnl_usd.sum()), 2)}
    net = e.iloc[-1] - cap
    m["after_costs"] = ("GANA dinero después de costes" if net > 0 else "PIERDE dinero después de costes" if net < 0 else "sin cambio") + \
        f": {net:+.2f} USD (costes pagados {costs:.2f} USD)"
    m["acceptance"] = acceptance(m, bench={BTC_KEY: m["vs"][BTC_KEY]}, prospective=spec.get("mode") == "live", days=days,
                                 min_days=spec.get("min_duration_days", 183))
    if days < spec.get("min_duration_days", 183):
        m["acceptance"]["verdict"] = f"EN CURSO: {days} de {spec.get('min_duration_days', 183)} días mínimos; aún no se evalúa"
    m["acceptance"]["note"] = ("Los criterios de subperiodos, costes ×2 y evidencia estadística se evalúan al terminar el "
                               "periodo mínimo con research/edge/audit_stats.py sobre el diario; aquí quedan en False.")
    return m
