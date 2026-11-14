"""Backtest de las reglas técnicas sobre velas diarias históricas de Binance.
Solo usa la parte técnica/volumen/R:R (los fundamentales históricos no están disponibles gratis).
Simulación: entrada cuando el sistema diría COMPRAR EN ZONA; 40% en TP1 (stop a entrada), 35% TP2, 25% TP3."""
from __future__ import annotations
from . import data
from .analysis import analyze

WINDOW = 400


def run(symbol, quote="USDT", days=1000, min_score=70, settings=None, d1=None):
    settings = settings or {"min_risk_reward": 3.0, "capital_usd": 1000, "risk_per_trade_pct": 1, "max_position_pct": 100}
    if d1 is None:
        d1 = data.klines(symbol.upper() + quote, "1d", min(days, 1000))
    n = len(d1["c"])
    if n < 260:
        return {"symbol": symbol, "error": "Historial insuficiente (se necesitan 260+ días)"}
    trades, open_t = [], None
    i = 220
    while i < n - 1:
        if open_t is None:
            sl = {k: v[max(0, i + 1 - WINDOW):i + 1] for k, v in d1.items()}
            a = analyze(symbol, sl, None, None, None, {}, settings, "LATERAL")
            if a["action"] == "COMPRAR EN ZONA" and a["score"] >= min_score:
                pl = a["plan"]
                open_t = {"entry_i": i, "date": d1["t"][i], "entry": d1["c"][i], "stop": pl["stop"], "tp1": pl["tp1"],
                          "tp2": pl["tp2"], "tp3": pl["tp3"], "score": a["score"], "phase": a["phase"],
                          "cur_stop": pl["stop"], "left": 1.0, "R_real": 0.0, "hits": []}
        else:
            t = open_t
            R = t["entry"] - t["stop"]
            hi, lo = d1["h"][i], d1["l"][i]
            if lo <= t["cur_stop"]:
                t["R_real"] += t["left"] * (t["cur_stop"] - t["entry"]) / R
                t["left"] = 0; t["hits"].append("stop")
            else:
                for tp, w in (("tp1", .40), ("tp2", .35), ("tp3", .25)):
                    if tp not in t["hits"] and hi >= t[tp]:
                        t["R_real"] += w * (t[tp] - t["entry"]) / R; t["left"] -= w; t["hits"].append(tp)
                        if tp == "tp1": t["cur_stop"] = t["entry"]
                        if tp == "tp2": t["cur_stop"] = t["tp1"]
            if t["left"] <= 1e-9 or i - t["entry_i"] >= 90:
                if t["left"] > 0:
                    t["R_real"] += t["left"] * (d1["c"][i] - t["entry"]) / R
                t["exit_i"], t["days"] = i, i - t["entry_i"]
                t["R_real"] = round(t["R_real"], 2)
                trades.append({k: t[k] for k in ("date", "entry", "stop", "tp1", "tp2", "tp3", "score", "phase", "hits", "R_real", "days")})
                open_t = None
        i += 1
    rs = [t["R_real"] for t in trades]
    wins = [r for r in rs if r > 0]
    eq, peak, mdd, risk = 1.0, 1.0, 0.0, 0.01
    curve = []
    for t in trades:
        eq *= 1 + t["R_real"] * risk
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
        curve.append([t["date"], round((eq - 1) * 100, 2)])
    bh = (d1["c"][-1] / d1["c"][220] - 1) * 100
    gross_win = sum(wins); gross_loss = -sum(r for r in rs if r < 0)
    return {
        "symbol": symbol.upper(), "days": n - 220, "trades": len(trades),
        "win_rate": round(len(wins) / len(rs) * 100, 1) if rs else None,
        "avg_R": round(sum(rs) / len(rs), 2) if rs else None,
        "total_R": round(sum(rs), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else None,
        "return_pct_1pct_risk": round((eq - 1) * 100, 2), "max_drawdown_pct": round(mdd * 100, 2),
        "buy_hold_pct": round(bh, 1), "equity": curve, "list": trades[-50:],
        "note": "Arriesgando 1% del capital por operación. Resultados pasados no garantizan resultados futuros.",
    }
