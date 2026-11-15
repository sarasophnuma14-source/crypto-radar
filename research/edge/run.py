"""Ejecuta el protocolo pre-registrado (research/edge/PREREGISTRO.md).

  python3 research/edge/run.py devval     # Desarrollo + Validación, congela la selección
  python3 research/edge/run.py holdout    # Holdout final: UNA sola vez (se niega si ya existe el candado)
Resultados en data/research/edge/ (JSON y CSV)."""
import csv, datetime as dt, json, sys, time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from radar.edge import data, features, strategies, sim, metrics, manip, stats

OUT = ROOT / "data" / "research" / "edge"; OUT.mkdir(parents=True, exist_ok=True)
DEV = ("2020-01-01", "2022-12-31"); VAL = ("2023-01-01", "2024-06-30"); HOLD = ("2024-07-01", "2026-11-14")
SUB = {"2024-S2": ("2024-07-01", "2024-12-31"), "2025": ("2025-01-01", "2025-12-31"), "2026": ("2026-01-01", "2026-11-14")}
T0 = time.time()


def _js(o):
    return o.item() if hasattr(o, "item") else str(o)


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def load():
    P = data.build(); F = features.compute(P); U = features.universe(F)
    S = strategies.build_all(P, F, U); M = manip.score(P, F)
    return P, F, U, S, M


def write_trades(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def devval():
    P, F, U, S, M = load()
    res = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "dev": {}, "val": {}, "selection": {}}
    trades = []
    for s in S:
        for per, rng in (("dev", DEV), ("val", VAL)):
            r = sim.simulate(P, F, s, *rng, "base", manip=M)
            m = metrics.summarize(r); m["elevated"] = metrics.summarize(sim.simulate(P, F, s, *rng, "elevated"))
            res[per][s.name] = m
            trades += [dict(t, period=per, scenario="base") for t in r["trades"]]
        log(s.name, "dev", res["dev"][s.name]["sharpe"], "val", res["val"][s.name]["sharpe"])
    for fam in "ABCDE":
        cands = [s.name for s in S if s.family == fam and res["dev"][s.name]["trades"] >= 30]
        if not cands:
            res["selection"][fam] = {"chosen": None, "reason": "ninguna con ≥ 30 operaciones en Desarrollo"}; continue
        best = max(cands, key=lambda n: res["dev"][n]["sharpe"])
        v = res["val"][best]
        ok = v["net_return_pct"] > 0 and (v["profit_factor"] or 0) > 1.15 and v["sharpe"] > 0.75
        res["selection"][fam] = {"chosen": best, "dev_sharpe": res["dev"][best]["sharpe"], "val": {k: v[k] for k in
                                 ("net_return_pct", "profit_factor", "sharpe", "trades", "max_drawdown_pct")},
                                 "passes_validation": ok}
    # filtro de manipulación en Validación (solo las que pasan)
    res["manip_val"] = {}
    for fam, sel in res["selection"].items():
        if sel.get("passes_validation"):
            s = next(x for x in S if x.name == sel["chosen"])
            r = sim.simulate(P, F, s, *VAL, "base", manip=M, manip_max=60)
            res["manip_val"][s.name] = {"sin_filtro": res["val"][s.name]["sharpe"], "con_filtro": metrics.summarize(r)["sharpe"],
                                        "con_filtro_ret": metrics.summarize(r)["net_return_pct"], "sin_filtro_ret": res["val"][s.name]["net_return_pct"]}
    res["benchmarks"] = {"dev": metrics.benchmarks(P, F, U, *DEV), "val": metrics.benchmarks(P, F, U, *VAL)}
    (OUT / "devval_results.json").write_text(json.dumps(res, indent=1, default=_js))
    (OUT / "selection_frozen.json").write_text(json.dumps({"frozen_at": res["generated"], "selection": res["selection"]}, indent=1, default=_js))
    write_trades(OUT / "devval_trades.csv", trades)
    log("selección congelada:", json.dumps(res["selection"], default=_js, ensure_ascii=False))


def holdout():
    lock = OUT / "HOLDOUT_EXECUTED.lock"
    if lock.exists() and "--force" not in sys.argv:
        raise SystemExit("El holdout ya se ejecutó (" + lock.read_text().strip() + "). No se repite.")
    sel = json.loads((OUT / "selection_frozen.json").read_text())["selection"]
    lock.write_text(dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    P, F, U, S, M = load()
    res = {"generated": lock.read_text(), "frozen_selection": sel, "all": {}, "frozen": {}}
    trades, curves = [], {}
    for s in S:
        out = {}
        for sc in ("base", "elevated", "stress"):
            r = sim.simulate(P, F, s, *HOLD, sc, manip=M)
            out[sc] = metrics.summarize(r)
            if sc == "base":
                rb = r
        out["bootstrap"] = stats.test_mean(metrics.daily_returns(rb["curve"]).to_numpy())
        out["sub"] = {k: metrics.summarize(sim.simulate(P, F, s, *v, "base"))["net_return_pct"] for k, v in SUB.items()}
        res["all"][s.name] = out
        trades += [dict(t, period="holdout", scenario="base") for t in rb["trades"]]
        curves[s.name] = rb["curve"]["equity"]
        log(s.name, out["base"]["net_return_pct"], out["base"]["sharpe"], out["bootstrap"]["p_value"])
    frozen = {f: v["chosen"] for f, v in sel.items() if v.get("chosen") and v.get("passes_validation")}
    padj = stats.holm({n: res["all"][n]["bootstrap"]["p_value"] for n in frozen.values()}) if frozen else {}
    bonf = {n: min(1.0, v["bootstrap"]["p_value"] * len(S)) for n, v in res["all"].items()}
    U50 = features.universe(F, size=50)
    S50 = {s.name: s for s in strategies.build_all(P, F, U50)}
    for fam, name in frozen.items():
        a = res["all"][name]; b = a["base"]
        verdict_checks = {
            "1_retorno_neto_pos": b["net_return_pct"] > 0,
            "2_expectancy_pos": (b["expectancy_usd"] or 0) > 0,
            "3_pf_gt_1_15": (b["profit_factor"] or 0) > 1.15,
            "4_sharpe_gt_0_75": b["sharpe"] > 0.75,
            "5_dd_le_25": b["max_drawdown_pct"] >= -25,
            "6_consistencia": sum(x > 0 for x in a["sub"].values()) >= 2,
            "7_costes_elevados": a["elevated"]["net_return_pct"] > 0 and (a["elevated"]["profit_factor"] or 0) > 1.0,
            "8_sin_top5_y_30_ops": b["net_without_top5_usd"] > 0 and b["trades"] >= 30,
            "9_estadistica": padj.get(name, 1) < 0.05 and (a["bootstrap"]["sharpe_ci90"][0] or -1) > 0,
        }
        if b["trades"] < 30:
            verdict = "INSUFFICIENT DATA"
        elif all(verdict_checks.values()):
            verdict = "ACCEPTED"
        elif all(verdict_checks[k] for k in ("1_retorno_neto_pos", "2_expectancy_pos", "3_pf_gt_1_15", "4_sharpe_gt_0_75")):
            verdict = "PROMISING"
        else:
            verdict = "REJECTED"
        s = next(x for x in S if x.name == name)
        man = metrics.summarize(sim.simulate(P, F, s, *HOLD, "base", manip=M, manip_max=60))
        u50 = metrics.summarize(sim.simulate(P, F, S50[name], *HOLD, "base"))
        res["frozen"][fam] = {"strategy": name, "verdict": verdict, "checks": verdict_checks, "p_holm": padj.get(name),
                              "p_bonferroni_23": round(bonf[name], 4),
                              "manip_filter": {k: man[k] for k in ("net_return_pct", "sharpe", "profit_factor", "trades")},
                              "universe50": {k: u50[k] for k in ("net_return_pct", "sharpe", "profit_factor", "trades")}}
    for fam, v in sel.items():
        if fam not in res["frozen"]:
            res["frozen"][fam] = {"strategy": v.get("chosen"), "verdict": "REJECTED",
                                  "reason": "no pasó la Validación" if v.get("chosen") else v.get("reason")}
    res["benchmarks"] = metrics.benchmarks(P, F, U, *HOLD)
    # walk-forward anual (información): mejor Sharpe por familia en los 2 años previos
    wf = {}
    for fam in "ABCDE":
        rows = []
        for y in range(2022, 2027):
            tr_rng = (f"{y - 2}-01-01", f"{y - 1}-12-31"); te_rng = (f"{y}-01-01", f"{y}-12-31" if y < 2026 else HOLD[1])
            fs = [s for s in S if s.family == fam]
            sc = {s.name: metrics.summarize(sim.simulate(P, F, s, *tr_rng, "base")) for s in fs}
            ok = [n for n in sc if sc[n]["trades"] >= 15] or list(sc)
            best = max(ok, key=lambda n: sc[n]["sharpe"])
            te = metrics.summarize(sim.simulate(P, F, next(s for s in fs if s.name == best), *te_rng, "base"))
            rows.append({"year": y, "chosen": best, "test_return_pct": te["net_return_pct"], "test_sharpe": te["sharpe"],
                         "trades": te["trades"]})
        chain = 1.0
        for r_ in rows:
            chain *= 1 + r_["test_return_pct"] / 100
        wf[fam] = {"years": rows, "chained_pct": round((chain - 1) * 100, 2)}
        log("walk-forward", fam, wf[fam]["chained_pct"])
    res["walk_forward"] = wf
    (OUT / "holdout_results.json").write_text(json.dumps(res, indent=1, default=_js))
    write_trades(OUT / "holdout_trades.csv", trades)
    pd.DataFrame(curves).to_csv(OUT / "holdout_curves.csv")
    log("veredictos:", {f: v["verdict"] for f, v in res["frozen"].items()})


if __name__ == "__main__":
    {"devval": devval, "holdout": holdout}[sys.argv[1]]()
