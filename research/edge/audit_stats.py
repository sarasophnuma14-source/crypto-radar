"""Fase 5 de la auditoría de D_volmom_L28: estadística ampliada.

  python3 research/edge/audit_stats.py

A) Re-análisis del holdout REGISTRADO (simulador v1, ejecutado una vez el 2026-11-15T03:55Z). No se vuelve a simular
   nada sobre el holdout para esta parte: se usan las curvas y operaciones guardadas en research/edge/results/.
B) Simulador v2 corregido: Desarrollo, Validación y, solo como EXPLORATORIO, el periodo del holdout ya visto. Queda en
   el registro (ledger) como `exploratory`. No es evidencia independiente y no se usa para cambiar parámetros.
Salida: research/edge/audit/estadistica_auditoria.json y CSV de curvas/operaciones v2."""
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1"); os.environ.setdefault("OMP_NUM_THREADS", "1")
import json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from radar.edge import data, features, strategies, sim, metrics, manip, stats, ledger
from radar.paper_trading.metrics import acceptance

RES = ROOT / "research" / "edge" / "results"
OUT = ROOT / "research" / "edge" / "audit"; OUT.mkdir(parents=True, exist_ok=True)
DEV = ("2020-01-01", "2022-12-31"); VAL = ("2023-01-01", "2024-06-30"); HOLD = ("2024-07-01", "2026-11-14")
SUB = {"2024-S2": ("2024-07-01", "2024-12-31"), "2025": ("2025-01-01", "2025-12-31"), "2026": ("2026-01-01", "2026-11-14")}
NAME = "D_volmom_L28"
BLOCKS = (10, 20, 30, 60)


def _js(o):
    if isinstance(o, (np.floating, np.integer, np.bool_)):
        return o.item()
    return str(o)


def regime_split(r, bear):
    """Rendimientos diarios por régimen de BTC (régimen conocido al cierre del día anterior)."""
    b = bear.shift(1).reindex(r.index).fillna(False).astype(bool)
    out = {}
    for lab, mask in (("BTC alcista (≥ SMA200)", ~b), ("BTC bajista (< SMA200)", b)):
        x = r[mask]
        out[lab] = {"days": int(len(x)), "mean_daily_pct": round(float(x.mean()) * 100, 4) if len(x) else None,
                    "sharpe": round(metrics.sharpe(x), 3), "cum_pct": round(float((1 + x).prod() - 1) * 100, 2)}
    return out


def monthly(eq):
    m = eq.resample("ME").last()
    base = pd.concat([pd.Series([eq.iloc[0]], index=[eq.index[0] - pd.Timedelta(days=1)]), m])
    return {d.strftime("%Y-%m"): round(float(v) * 100, 2) for d, v in (base.pct_change().dropna()).items()}


def risk_audit_v1(P, F):
    """Cuánto arriesgaba de verdad cada operación de D en el holdout registrado (B2)."""
    tr = pd.read_csv(RES / "holdout_operaciones.csv")
    tr = tr[tr.strategy == NAME].copy()
    curve = pd.read_csv(RES / "holdout_curvas.csv", index_col=0, parse_dates=True)[NAME]
    tr["risk_usd"] = tr.pnl_usd / tr.R
    eq_prev = curve.shift(1).fillna(10_000.0)
    tr["eq_entry"] = [eq_prev.loc[pd.Timestamp(d)] for d in tr.entry_date]
    tr["risk_pct"] = tr.risk_usd / tr.eq_entry * 100
    tr["size_pct"] = tr.cost_usd / tr.eq_entry * 100
    return {"trades": int(len(tr)), "over_0_5pct": int((tr.risk_pct > 0.5 + 1e-9).sum()),
            "risk_pct_mean": round(float(tr.risk_pct.mean()), 3), "risk_pct_median": round(float(tr.risk_pct.median()), 3),
            "risk_pct_max": round(float(tr.risk_pct.max()), 3), "size_pct_median": round(float(tr.size_pct.median()), 2),
            "size_pct_max": round(float(tr.size_pct.max()), 2),
            "realized_vol_ann": round(float(curve.pct_change().dropna().std() * math.sqrt(365)), 4)}


def part_a(P, F):
    reg = json.loads((RES / "holdout_results.json").read_text())
    curves = pd.read_csv(RES / "holdout_curvas.csv", index_col=0, parse_dates=True)
    frozen = {f: v["strategy"] for f, v in reg["frozen"].items()}
    out = {"source": "holdout registrado (v1), sin re-simular", "frozen": frozen, "strategies": {}}
    pv = {}
    for fam, name in frozen.items():
        eq = curves[name].dropna(); r = eq.pct_change().dropna()
        sens = stats.block_sensitivity(r.to_numpy(), BLOCKS)
        pv[name] = max(x["p_value"] for x in sens)                     # el más conservador de los 8
        a = reg["all"][name]
        out["strategies"][name] = {
            "base": {k: a["base"][k] for k in ("net_return_pct", "cagr_pct", "sharpe", "sortino", "profit_factor",
                                               "max_drawdown_pct", "expectancy_usd", "win_rate_pct", "trades", "costs_usd")},
            "costs_x2": {k: a["elevated"][k] for k in ("net_return_pct", "sharpe", "profit_factor")},
            "costs_x3_haircut30": {k: a["stress"][k] for k in ("net_return_pct", "sharpe", "profit_factor")},
            "subperiods_pct": a["sub"], "yearly_pct": a["base"]["yearly_pct"],
            "bootstrap": sens, "regime": regime_split(r, F["btc_bear"]),
        }
    out["p_conservative"] = pv
    out["p_holm_5"] = stats.holm(pv)
    out["p_bonferroni_5"] = stats.bonferroni(pv)
    out["p_bonferroni_23"] = stats.bonferroni(pv, 23)
    out["benchmarks"] = reg["benchmarks"]
    out["risk_audit_D"] = risk_audit_v1(P, F)
    d = out["strategies"][NAME]
    out["acceptance_D"] = acceptance({**reg["all"][NAME]["base"], "net_without_top5_usd": reg["all"][NAME]["base"]["net_without_top5_usd"]},
                                     elevated=reg["all"][NAME]["elevated"], stress=reg["all"][NAME]["stress"],
                                     sub=d["subperiods_pct"], p_adj=out["p_holm_5"][NAME],
                                     sharpe_ci_low=min(x["sharpe_ci"][0] for x in d["bootstrap"] if x["sharpe_ci"][0] is not None),
                                     bench=reg["benchmarks"], prospective=False)
    return out


def part_b(P, F, U, S, M):
    s = next(x for x in S if x.name == NAME)
    out = {"source": "simulador v2 corregido; el periodo del holdout es EXPLORATORIO (ya visto)", "periods": {}}
    curves, trades = {}, []
    for per, rng in (("dev", DEV), ("val", VAL), ("holdout_exploratorio", HOLD)):
        runs = {sc: sim.simulate(P, F, s, *rng, sc, manip=M) for sc in ("base", "elevated", "stress")}
        b = runs["base"]; m = metrics.summarize(b)
        r = metrics.daily_returns(b["curve"])
        sub = ({k: metrics.summarize(sim.simulate(P, F, s, *v, "base", manip=M))["net_return_pct"] for k, v in SUB.items()}
               if per.startswith("holdout") else {y: v for y, v in m["yearly_pct"].items()})
        bench = metrics.benchmarks(P, F, U, *rng)
        sens = stats.block_sensitivity(r.to_numpy(), BLOCKS)
        out["periods"][per] = {
            "range": rng, "base": {k: m[k] for k in ("net_return_pct", "cagr_pct", "sharpe", "sortino", "profit_factor",
                                                    "max_drawdown_pct", "expectancy_usd", "expectancy_R", "win_rate_pct",
                                                    "avg_win_usd", "avg_loss_usd", "trades", "avg_exposure_pct", "costs_usd",
                                                    "net_without_top5_usd")},
            "realized_vol_ann": round(float(r.std() * math.sqrt(365)), 4),
            "max_trade_risk_pct": round(max(t["risk_pct_equity"] for t in b["trades"]), 4) if b["trades"] else None,
            "costs_x2": {k: metrics.summarize(runs["elevated"])[k] for k in ("net_return_pct", "sharpe", "profit_factor")},
            "costs_x3_haircut30": {k: metrics.summarize(runs["stress"])[k] for k in ("net_return_pct", "sharpe", "profit_factor")},
            "subperiods_pct": sub, "regime": regime_split(r, F["btc_bear"]), "monthly_pct": monthly(b["curve"]["equity"]),
            "bootstrap": sens, "benchmarks": bench}
        pc = max(x["p_value"] for x in sens)
        lo = [x["sharpe_ci"][0] for x in sens if x["sharpe_ci"][0] is not None]
        out["periods"][per]["acceptance"] = acceptance(
            m, elevated=metrics.summarize(runs["elevated"]), stress=metrics.summarize(runs["stress"]), sub=sub,
            p_adj=pc, sharpe_ci_low=min(lo) if lo else None, bench=bench, prospective=False)
        curves[per] = b["curve"]["equity"]
        trades += [dict(t, period=per) for t in b["trades"]]
    pd.DataFrame(curves).to_csv(OUT / "v2_curvas.csv")
    pd.DataFrame(trades).to_csv(OUT / "v2_operaciones.csv", index=False)
    return out


if __name__ == "__main__":
    P0 = data.build()
    F0 = features.compute(P0)
    A = part_a(P0, F0)
    P = data.drop_stables(P0); F = features.compute(P); U = features.universe(F)
    S = strategies.build_all(P, F, U); M = manip.score(P, F)
    B = part_b(P, F, U, S, M)
    e = ledger.append("exploratory", strategy=NAME, simulator="v2", periods={k: v["range"] for k, v in B["periods"].items()},
                      summary={k: v["base"] for k, v in B["periods"].items()},
                      note="EXPLORATORIO: re-análisis de auditoría con el simulador v2 corregido. El periodo 2024-07 → 2026-11 "
                           "ya se había visto; no es un holdout independiente ni sirve para elegir parámetros.")
    res = {"ledger_run_id": e["run_id"], "A_holdout_registrado_v1": A, "B_simulador_v2": B}
    (OUT / "estadistica_auditoria.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=_js))
    print(json.dumps({"A_D": A["strategies"][NAME]["base"], "A_p": A["p_holm_5"], "risk_v1": A["risk_audit_D"],
                      "B": {k: v["base"] for k, v in B["periods"].items()}}, indent=1, ensure_ascii=False, default=_js))
