"""Motor único de análisis por activo: el MISMO código produce las señales del escáner en vivo y del backtest."""
from __future__ import annotations
import datetime as dt
from . import early, manipulation, plan as plan_mod, exits, quality as quality_mod
from .features import val, chg
from .regime import POLICY

MANIP_BLOCK = 60      # riesgo de manipulación desde el que no se recomienda entrar


def action_for(ev, pl, manip, regime_name, settings):
    pol = POLICY.get(regime_name, POLICY["NEUTRAL"])
    phase, score, p = ev["phase"], ev["score"], pl.get("_price")
    min_rr = float(settings.get("min_risk_reward", 2.5))
    if phase == "REJECTED":
        return "DESCARTAR", "Condiciones inadecuadas o datos insuficientes"
    if phase == "OVEREXTENDED":
        return "NO PERSEGUIR", "El movimiento ya está muy avanzado"
    if phase == "DISTRIBUTION":
        return "EVITAR", "Señales de distribución"
    if manip["risk"] >= MANIP_BLOCK:
        return "EVITAR", f"Riesgo de manipulación {manip['level'].lower()} ({manip['risk']})"
    if phase not in pol["phases"]:
        return "VIGILAR", f"En régimen {regime_name} no se compran fases {ev['phase_label'].lower()}"
    if score < pol["min_score"]:
        return ("VIGILAR", f"Puntaje {score:.0f} bajo el mínimo {pol['min_score']} del régimen") if score >= pol["min_score"] - 12 \
            else ("DESCARTAR", f"Puntaje {score:.0f} muy bajo para el régimen")
    if pl["rr"] < min_rr:
        return "VIGILAR", f"Riesgo/beneficio {pl['rr']:.1f} < {min_rr:g}"
    if p <= pl["entry_high"]:
        return "COMPRAR EN ZONA", "Precio dentro de la zona de entrada"
    if phase in ("PRE-EXPLOSION", "ACCUMULATION") and pl.get("trigger_breakout"):
        return "ESPERAR RUPTURA", f"Entrar si cierra sobre {pl['trigger_breakout']:.6g} o en retroceso a la zona"
    return "ESPERAR RETROCESO", "Precio sobre la zona: esperar retroceso"


def analyze(symbol, f, i, btc_f=None, btc_i=None, regime=None, settings=None, market=None, book=None,
            book_prev=None, position=None, check_quality=True, now_ms=None, weights=None):
    settings = settings or {}
    regime_name = (regime or {}).get("regime", "NEUTRAL")
    q = None
    if check_quality:
        k = {key: f[key][:i + 1] for key in ("t", "o", "h", "l", "c", "v")}
        q = quality_mod.check(k, now_ms=now_ms or (f.t[i] + quality_mod.DAY_MS))
    ev = early.evaluate(f, i, btc_f, btc_i, weights=weights, book=book, quality=q)
    mc = (market or {}).get("market_cap")
    man = manipulation.evaluate(f, i, market_cap=mc, book=book, book_prev=book_prev)
    pl = plan_mod.build(f, i, ev["phase"], settings)
    pl["_price"] = f.c[i]
    act, why = action_for(ev, pl, man, regime_name, settings)
    pl.pop("_price")
    pol = POLICY.get(regime_name, POLICY["NEUTRAL"])
    pl["position_usd"] *= pol["size_mult"]
    avg = val(f.vol_avg20_prev, i)
    out = {
        "symbol": symbol, "bar_time": f.t[i],
        "bar_date": dt.datetime.fromtimestamp(f.t[i] / 1000, dt.timezone.utc).strftime("%Y-%m-%d"),
        "price": f.c[i], "score": ev["score"], "raw_score": ev["raw_score"], "phase": ev["phase"],
        "phase_label": ev["phase_label"], "phase_reasons": ev["phase_reasons"], "families": ev["families"],
        "coverage": ev["coverage"], "manipulation": man, "plan": pl, "action": act, "action_reason": why,
        "regime": regime_name, "quality": q,
        "metrics": {"rel_volume": (f.v[i] / avg) if avg else None, "chg_24h": chg(f, i, 1), "chg_7d": chg(f, i, 7),
                    "chg_30d": chg(f, i, 30), "rs_btc_30d": (chg(f, i, 30) - chg(btc_f, btc_i, 30))
                    if btc_f is not None and chg(f, i, 30) is not None and chg(btc_f, btc_i, 30) is not None else None,
                    "avg_volume_usd": avg, "rsi": val(f.rsi, i), "atr_pct": (val(f.atr, i) or 0) / f.c[i] * 100,
                    "liquidity": ev["families"]["liquidity"]["score"]},
    }
    if position:
        out["exit"] = exits.decide(f, i, position, regime_name, settings.get("exit_partials"))
    return out
