"""Métricas calculadas SOLO desde el libro de operaciones y la curva diaria de capital (verificables)."""
from __future__ import annotations
import datetime as dt
import math


def _days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def drawdown_stats(curve):
    """curve: [(fecha, capital)]. Máximo drawdown y la recuperación más larga (días desde un máximo hasta superarlo)."""
    peak, peak_d, mdd, longest, under_since = None, None, 0.0, 0, None
    for d, v in curve:
        if peak is None or v >= peak:
            if under_since:
                longest = max(longest, _days(under_since, d))
                under_since = None
            peak, peak_d = v, d
        else:
            mdd = min(mdd, v / peak - 1)
            under_since = under_since or peak_d
    still_under = _days(under_since, curve[-1][0]) if under_since else 0
    return mdd * 100, longest, still_under


def compute(trades, curve, capital, fees, exposure_series=None, benchmark=None):
    """trades: dicts con pnl_usd, R, regime, cap_bucket, strategy/phase. curve: [(fecha, capital)]."""
    n = len(trades)
    final = curve[-1][1] if curve else capital
    days = _days(curve[0][0], curve[-1][0]) if len(curve) > 1 else 0
    yrs = days / 365.25 if days else 0
    rets = [curve[k][1] / curve[k - 1][1] - 1 for k in range(1, len(curve)) if curve[k - 1][1]]
    mean = sum(rets) / len(rets) if rets else 0
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)) if len(rets) > 1 else 0
    neg = [r for r in rets if r < 0]
    dsd = math.sqrt(sum(r * r for r in neg) / len(rets)) if rets else 0
    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    gw, gl = sum(t["pnl_usd"] for t in wins), -sum(t["pnl_usd"] for t in losses)
    rs = [t["R"] for t in trades if t.get("R") is not None]
    mdd, rec, under = drawdown_stats(curve) if curve else (0, 0, 0)

    def group(key):
        out = {}
        for t in trades:
            g = out.setdefault(t.get(key) or "N/D", {"trades": 0, "pnl_usd": 0.0, "wins": 0})
            g["trades"] += 1; g["pnl_usd"] += t["pnl_usd"]; g["wins"] += t["pnl_usd"] > 0
        for g in out.values():
            g["pnl_usd"] = round(g["pnl_usd"], 2); g["win_rate_pct"] = round(g["wins"] / g["trades"] * 100, 1)
        return out
    m = {
        "capital_initial": capital, "capital_final": round(final, 2),
        "total_return_pct": round((final / capital - 1) * 100, 2),
        "cagr_pct": round(((final / capital) ** (1 / yrs) - 1) * 100, 2) if yrs > 0 and final > 0 else None,
        "trades": n, "win_rate_pct": round(len(wins) / n * 100, 1) if n else None,
        "profit_factor": round(gw / gl, 2) if gl > 0 else None,
        "expectancy_usd": round((gw - gl) / n, 2) if n else None,
        "avg_R": round(sum(rs) / len(rs), 3) if rs else None,
        "sharpe": round(mean / sd * math.sqrt(365), 2) if sd else None,
        "sortino": round(mean / dsd * math.sqrt(365), 2) if dsd else None,
        "max_drawdown_pct": round(mdd, 2), "longest_recovery_days": rec, "days_under_water_at_end": under,
        "avg_exposure_pct": round(sum(exposure_series) / len(exposure_series), 1) if exposure_series else None,
        "fees_usd": round(fees, 2), "days": days,
        "by_regime": group("regime"), "by_cap_bucket": group("cap_bucket"), "by_phase": group("phase"),
        "by_exit": group("exit_reason"),
    }
    if benchmark:
        bmdd, _, _ = drawdown_stats(benchmark)
        m["btc_buy_hold_pct"] = round((benchmark[-1][1] / benchmark[0][1] - 1) * 100, 2)
        m["btc_max_drawdown_pct"] = round(bmdd, 2)
    return m
