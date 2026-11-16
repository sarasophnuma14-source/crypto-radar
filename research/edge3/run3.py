"""Ejecución de la ronda v3 (PREREGISTRO_V3). Fases:
  python research/edge3/run3.py devval     desarrollo, validación, walk-forward, PBO, selección congelada
  python research/edge3/run3.py holdout    UNA ejecución del holdout (crea HOLDOUT_V3.lock; se niega si ya existe)
Resultados en research/edge3/results/. Semillas fijas; todo determinista con los mismos datos."""
from __future__ import annotations
import gzip, hashlib, json, math, sys, time
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from radar.edge import data as D, stats as S1  # noqa: E402  (solo lectura)
import engine as E, stats3 as S3, strategies3 as ST  # noqa: E402

DEV = ("2020-01-01", "2023-06-30"); VAL = ("2023-07-01", "2025-03-31"); HOLD = ("2025-04-01", "2026-11-14")
SUB = (("2023-07-01", "2024-06-30"), ("2024-07-01", "2025-03-31"))
OUT = HERE / "results"; LOCK = HERE / "HOLDOUT_V3.lock"
N_TRIALS = 58


def code_hash():
    h = hashlib.sha256()
    for f in ("engine.py", "strategies3.py", "stats3.py", "run3.py", "PREREGISTRO_V3.md"):
        h.update((HERE / f).read_bytes())
    return h.hexdigest()


def load():
    P = D.drop_stables(D.build())
    fz = json.load(gzip.open(ROOT / "data/research/funding/perp_funding_klines.json.gz", "rt"))
    inv = {v: k for k, v in fz["map"].items()}
    nov = ROOT / "data/research/funding/perp_klines_2026-11.json.gz"
    if nov.exists():                                   # velas diarias de 2026-11 (el funding de noviembre falta: 0)
        for perp, rows in json.load(gzip.open(nov, "rt"))["klines"].items():
            fz["klines"].setdefault(perp, []).extend(rows)
    f, po, pc = {}, {}, {}
    for perp, rows in fz["funding"].items():
        if rows and perp in inv:
            s = pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows], unit="ms"))
            f[inv[perp]] = s.groupby(s.index.normalize()).sum()
    for perp, rows in fz["klines"].items():
        if rows and perp in inv:
            ix = pd.to_datetime([r[0] for r in rows], unit="ms").normalize()
            po[inv[perp]] = pd.Series([r[1] for r in rows], index=ix); pc[inv[perp]] = pd.Series([r[4] for r in rows], index=ix)
    idx = P["c"].index
    fund = {k: pd.DataFrame(v).sort_index().loc[lambda d: ~d.index.duplicated()].reindex(idx) for k, v in
            (("f", f), ("po", po), ("pc", pc))}
    # el funding solo cuenta donde hay perpetuo con precio (antes del listado: NaN, no 0)
    fund["f"] = fund["f"].where(fund["pc"].notna())
    return P, fund


def weights_for(x, name):
    fam, fn = ST.CONFIGS[name]
    out = fn(x)
    if fam == "F3":
        W, band = out; return {"W": W, "band": band}
    if name.startswith("F6_carry"):
        W, H = out; return {"W": W, "H": H}
    return {"W": out}


def run_cfg(P, fund, spec, start, end, **kw):
    W = spec["W"]
    cap = 1.0 if W.shape[1] == 1 else 0.20
    extra = {}
    if "H" in spec:
        cols = list(W.columns)
        extra = dict(hedge=spec["H"], perp_o=fund["po"].reindex(columns=cols), perp_c=fund["pc"].reindex(columns=cols),
                     funding=fund["f"].reindex(columns=cols).fillna(0.0))
    return E.run(P, W, start=start, end=end, cap=cap, band=spec.get("band", 0.0), **extra, **kw)


def ensemble(results, how, start, end):
    """F8: combinación de las curvas de los componentes (capital rebalanceado a diario a los pesos objetivo; el coste de
    ese reparto entre componentes no se modela: es una aproximación declarada)."""
    rs = pd.DataFrame({k: r["curve"].pct_change() for k, r in results.items()}).fillna(0.0)
    if how == "igual":
        w = pd.DataFrame(1 / len(rs.columns), index=rs.index, columns=rs.columns)
    else:
        iv = 1 / rs.rolling(60, min_periods=20).std().shift(1)
        w = iv.div(iv.sum(axis=1), axis=0).fillna(1 / len(rs.columns))
    r = (w * rs).sum(axis=1)
    cap = 10_000.0
    curve = cap * (1 + r).cumprod()
    eps = [(a, p * (1 / len(results))) for res in results.values() for a, p in res["episodes"]]
    tot = {k: sum(res[k] for res in results.values()) / len(results) for k in ("fees", "slippage", "funding", "turnover", "delist_loss")}
    expo = pd.DataFrame({k: v["exposure"] for k, v in results.items()}).mean(axis=1)
    ap = sum(res["asset_pnl"].reindex(sorted(set().union(*[set(v["asset_pnl"].index) for v in results.values()]))).fillna(0.0)
             for res in results.values()) / len(results)
    return {"curve": curve, "exposure": expo, "episodes": eps, "asset_pnl": ap, "capital": cap, **tot}


def all_runs(P, fund, specs, start, end, **kw):
    res = {}
    for name in ST.CONFIGS:
        if name.startswith("F8"):
            continue
        res[name] = run_cfg(P, fund, specs[name], start, end, **kw)
    parts = {k: res[k] for k in ST.F8_PARTS}
    res["F8_conjunto_igual"] = ensemble(parts, "igual", start, end)
    res["F8_conjunto_invvol"] = ensemble(parts, "invvol", start, end)
    return res


def lookahead_audit(P, fund, x_full, specs, dates=("2022-06-30", "2024-03-31")):
    """Recalcula cada estrategia con el panel CORTADO en la fecha d y compara la fila d con la del panel completo."""
    bad = {}
    for d in dates:
        Pc = {k: (P[k].loc[:d] if isinstance(P[k], pd.DataFrame) else P[k]) for k in P}
        fc = {k: v.loc[:d] for k, v in fund.items()}
        xc = ST.Ctx(Pc, fc)
        for name, (fam, fn) in ST.CONFIGS.items():
            if fn is None:
                continue
            a = weights_for(xc, name)["W"].loc[d].fillna(0.0)
            b = specs[name]["W"].loc[d].reindex(a.index).fillna(0.0)
            if not np.allclose(a.values, b.values, atol=1e-9):
                bad[f"{name}@{d}"] = float(np.abs(a - b).max())
    return bad


def devval():
    t0 = time.time()
    P, fund = load(); x = ST.Ctx(P, fund)
    specs = {n: weights_for(x, n) for n, (f, fn) in ST.CONFIGS.items() if fn is not None}
    print(f"pesos calculados en {time.time() - t0:.0f}s"); sys.stdout.flush()
    la = lookahead_audit(P, fund, x, specs)
    print("auditoría de anticipación:", "OK" if not la else la); sys.stdout.flush()
    if la:
        raise SystemExit("FUGA DE INFORMACIÓN: se detiene (regla 12)")
    dev = all_runs(P, fund, specs, *DEV); val = all_runs(P, fund, specs, *VAL)
    cont = all_runs(P, fund, specs, DEV[0], VAL[1])                 # continuo para walk-forward y PBO
    out = {"generado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "code_sha256": code_hash(), "configs": {}}
    for n in ST.CONFIGS:
        out["configs"][n] = {"familia": ST.CONFIGS[n][0], "desarrollo": S3.metrics(dev[n]), "validacion": S3.metrics(val[n]),
                             "sub_val": [S3.metrics(cont[n], a, b)["retorno_neto_pct"] for a, b in SUB]}
    # selección por familia
    sel = {}
    for fam in sorted({v[0] for v in ST.CONFIGS.values()}):
        names = [n for n in ST.CONFIGS if ST.CONFIGS[n][0] == fam]
        if fam == "F8":
            best = "F8_conjunto_igual"
        else:
            ok = [n for n in names if out["configs"][n]["desarrollo"]["episodios"] >= 30] or names
            best = max(ok, key=lambda n: out["configs"][n]["desarrollo"]["sharpe"])
        v = out["configs"][best]["validacion"]
        passes = v["sharpe"] > 0.5 and v["retorno_neto_pct"] > 0
        stab = sum(out["configs"][n]["validacion"]["sharpe"] > 0 for n in names) / len(names)
        R = pd.DataFrame({n: cont[n]["curve"].pct_change() for n in names})
        pbo = S3.pbo_cscv(R) if len(names) >= 4 else None
        sel[fam] = {"elegida": best, "pasa_validacion": bool(passes), "estabilidad_C11": round(stab, 3),
                    "C11": stab >= 0.5, "pbo": pbo, "C8": (pbo["pbo"] < 0.5) if pbo else None}
    # walk-forward: semestres 2021-07 → 2025-03, elige por Sharpe de los 18 meses previos
    wf = {}
    starts = pd.date_range("2021-07-01", "2025-01-01", freq="6MS")
    for fam in sel:
        names = [n for n in ST.CONFIGS if ST.CONFIGS[n][0] == fam]
        R = pd.DataFrame({n: cont[n]["curve"].pct_change() for n in names}).fillna(0.0)
        segs, picks = [], []
        for s in starts:
            e = min(s + pd.DateOffset(months=6) - pd.Timedelta(days=1), pd.Timestamp(VAL[1]))
            tr = R.loc[s - pd.DateOffset(months=18):s - pd.Timedelta(days=1)]
            pick = (tr.mean() / tr.std().replace(0, np.nan)).idxmax() if fam != "F8" else "F8_conjunto_igual"
            picks.append(pick); segs.append(R.loc[s:e, pick])
        r = pd.concat(segs)
        wf[fam] = {"sharpe_oos": round(S3.sharpe(r), 3), "retorno_oos_pct": round(float((1 + r).prod() - 1) * 100, 2),
                   "elecciones": picks}
    # varianza de los Sharpe (diarios) de desarrollo para el DSR
    srs = [cont[n]["curve"].loc[:DEV[1]].pct_change().dropna() for n in ST.CONFIGS]
    var_sr = float(np.var([r.mean() / r.std() for r in srs if r.std() > 0], ddof=1))
    frozen = {"seleccion": sel, "var_sr_desarrollo": var_sr, "n_trials": N_TRIALS, "code_sha256": code_hash(),
              "generado": out["generado"]}
    OUT.mkdir(exist_ok=True)
    (OUT / "devval_v3.json").write_text(json.dumps({**out, "walk_forward": wf, "auditoria_anticipacion": la}, indent=1, ensure_ascii=False))
    (OUT / "seleccion_congelada_v3.json").write_text(json.dumps(frozen, indent=1, ensure_ascii=False))
    pd.DataFrame({n: cont[n]["curve"] for n in ST.CONFIGS}).to_csv(OUT / "curvas_desarrollo_validacion.csv.gz")
    print(json.dumps({f: {k: v[k] for k in ("elegida", "pasa_validacion", "C11")} | {"pbo": (v["pbo"] or {}).get("pbo")}
                      for f, v in sel.items()}, indent=1, ensure_ascii=False))
    print("walk-forward:", json.dumps({f: (w["sharpe_oos"], w["retorno_oos_pct"]) for f, w in wf.items()}))
    print(f"total {time.time() - t0:.0f}s")


def benchmarks(P, start, end):
    """Comprar y mantener BTC/ETH y cartera equiponderada top 50 (mensual) con el mismo motor y costes; motor 2.0 y
    D_volmom v2 desde las curvas congeladas."""
    x = ST.Ctx(P)
    out = {}
    for a in ("BTC", "ETH"):
        w = pd.DataFrame({a: np.nan}, index=P["c"].index); w.loc[pd.Timestamp(start) - pd.Timedelta(days=1), a] = 1.0
        out[f"{a} comprar y mantener"] = S3.metrics(E.run(P, w, start=start, end=end, cap=1.0))
    U = x.universe(50)
    ew = U.astype(float).div(U.sum(axis=1).replace(0, np.nan), axis=0)
    me = P["c"].index[P["c"].index.is_month_end]
    out["Equiponderada top 50 (mensual)"] = S3.metrics(E.run(P, ST._sched(ew, me), start=start, end=end, cap=0.20))
    bdir = HERE / "benchmark"
    cr = pd.read_csv(bdir / "crypto_radar_2_0_curva.csv", index_col=0, parse_dates=True)["equity"]
    dv = pd.read_csv(bdir / "d_volmom_v2_curvas.csv", index_col=0, parse_dates=True)
    dvs = dv.bfill(axis=1).iloc[:, 0]  # columnas dev/val/holdout_exploratorio: cada fila tiene un solo valor
    for name, s in (("Crypto Radar actual (motor 2.0)", cr), ("D_volmom_L28 v2 (paper trading)", dvs)):
        seg = s.loc[start:end].dropna()
        if len(seg) < 30:
            out[name] = None; continue
        base = s.loc[:pd.Timestamp(start) - pd.Timedelta(days=1)].dropna()
        # D_volmom: las columnas son ejecuciones separadas; se encadenan los retornos diarios de cada una
        if name.startswith("D_volmom"):
            r = pd.concat([dv[c].pct_change(fill_method=None) for c in dv.columns], axis=1).sum(axis=1, min_count=1)
            r = r.loc[start:end].dropna()
        else:
            r = s.pct_change().loc[start:end].dropna()
        eq = (1 + r).cumprod()
        out[name] = {"retorno_neto_pct": round(float(eq.iloc[-1] - 1) * 100, 2), "sharpe": round(S3.sharpe(r), 3),
                     "max_dd_pct": round(float((eq / eq.cummax() - 1).min()) * 100, 2), "dias": len(r)}
    return out


def holdout():
    if LOCK.exists():
        raise SystemExit(f"El holdout v3 ya se ejecutó ({LOCK.read_text().strip()}). No se repite.")
    frozen = json.loads((OUT / "seleccion_congelada_v3.json").read_text())
    if frozen["code_sha256"] != code_hash():
        raise SystemExit("El código cambió desde la selección congelada: no se ejecuta el holdout.")
    sel_hash = hashlib.sha256((OUT / "seleccion_congelada_v3.json").read_bytes()).hexdigest()
    LOCK.write_text(json.dumps({"ejecutado": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "seleccion_sha256": sel_hash,
                                "code_sha256": frozen["code_sha256"]}) + "\n")
    dv = json.loads((OUT / "devval_v3.json").read_text())
    P, fund = load(); x = ST.Ctx(P, fund)
    specs = {n: weights_for(x, n) for n, (f, fn) in ST.CONFIGS.items() if fn is not None}
    H = all_runs(P, fund, specs, *HOLD)
    OOS = all_runs(P, fund, specs, VAL[0], HOLD[1])
    scen = {s: all_runs(P, fund, specs, *HOLD, scenario=s) for s in ("ELEVADO", "ESTRES")}
    lag1 = all_runs(P, fund, specs, *HOLD, lag=1)
    maker = all_runs(P, fund, specs, *HOLD, maker=True)
    big = all_runs(P, fund, specs, *HOLD, capital=1_000_000.0)
    bm_h = benchmarks(P, *HOLD); bm_oos = benchmarks(P, VAL[0], HOLD[1])
    sel = frozen["seleccion"]
    fams = {f: v["elegida"] for f, v in sel.items()}
    reach = [f for f, v in sel.items() if v["pasa_validacion"]]
    boots = {f: S1.bootstrap_test(H[n]["curve"].pct_change().dropna().values, "stationary", 20, 5000, 7, 0.10)
             for f, n in fams.items()}
    holm = S1.holm({f: boots[f]["p_value"] for f in reach}) if reach else {}
    bench_sh = [bm_h[k]["sharpe"] for k in ("BTC comprar y mantener", "Equiponderada top 50 (mensual)",
                                             "Crypto Radar actual (motor 2.0)") if bm_h.get(k)]
    verdict = {}
    for f, n in fams.items():
        m = S3.metrics(H[n]); ro = OOS[n]["curve"].pct_change().dropna()
        d58 = S3.dsr(ro, frozen["n_trials"], frozen["var_sr_desarrollo"]); d100 = S3.dsr(ro, 100, frozen["var_sr_desarrollo"])
        ap = H[n]["asset_pnl"]
        single = ap.shape[0] <= 1 or n.startswith(("F5_voltarget_btc", "F3_donchian_btc"))
        c = {
            "C1": m["retorno_neto_pct"] > 0,
            "C2": m["sharpe"] > 0.75 and all(m["sharpe"] > s for s in bench_sh),
            "C3": m["max_dd_pct"] >= -30,
            "C4": (m["profit_factor"] or 0) > 1.15 and m["episodios"] >= 30,
            "C5": S3.metrics(scen["ELEVADO"][n])["retorno_neto_pct"] > 0 and S3.metrics(scen["ESTRES"][n])["sharpe"] > 0,
            "C6": (f in holm and holm[f] < 0.05) and (boots[f]["sharpe_ci"][0] or -1) > 0,
            "C7": d58["dsr"] > 0.95,
            "C8": sel[f]["C8"],
            "C9": (not single) and float(ap.sum() - ap.max()) > 0,
            "C10": sum(r > 0 for r in dv["configs"][n]["sub_val"] + [m["retorno_neto_pct"]]) >= 2,
            "C11": sel[f]["C11"],
            "C12": S3.metrics(lag1[n])["retorno_neto_pct"] > 0,
        }
        passed = sum(1 for v in c.values() if v is True)
        applicable = sum(1 for v in c.values() if v is not None)
        if not sel[f]["pasa_validacion"]:
            label = "RECHAZADA (no pasó validación)"
        elif m["episodios"] < 30:
            label = "DATOS INSUFICIENTES"
        elif all(v in (True, None) for v in c.values()):
            label = "EDGE CANDIDATA"
        elif c["C1"] and c["C2"] and c["C3"] and passed >= 8:
            label = "PROMETEDORA"
        else:
            label = "RECHAZADA"
        verdict[f] = {"config": n, "holdout": m, "oos_val_mas_holdout": S3.metrics(OOS[n]),
                      "elevado": S3.metrics(scen["ELEVADO"][n]), "estres": S3.metrics(scen["ESTRES"][n]),
                      "latencia_1d": S3.metrics(lag1[n]), "maker": S3.metrics(maker[n]), "capital_1M": S3.metrics(big[n]),
                      "bootstrap": boots[f], "p_holm": holm.get(f), "dsr_N58": d58, "dsr_N100": d100,
                      "pnl_por_activo_top": ap.sort_values(ascending=False).head(5).round(2).to_dict(),
                      "pnl_por_activo_peor": ap.sort_values().head(5).round(2).to_dict(),
                      "criterios": c, "cumplidos": f"{passed}/{applicable}", "veredicto": label}
    allh = {n: S3.metrics(H[n]) for n in ST.CONFIGS}
    res = {"lock": json.loads(LOCK.read_text()), "familias": verdict, "benchmarks_holdout": bm_h, "benchmarks_oos": bm_oos,
           "todas_las_configuraciones_holdout_informativo": allh,
           "edge": any(v["veredicto"] == "EDGE CANDIDATA" for v in verdict.values())}
    (OUT / "holdout_v3.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=float))
    pd.DataFrame({n: H[n]["curve"] for n in ST.CONFIGS}).to_csv(OUT / "curvas_holdout.csv.gz")
    for f, v in verdict.items():
        print(f"{f} {v['config']:28s} {v['veredicto']:32s} {v['cumplidos']} ret {v['holdout']['retorno_neto_pct']:7.2f} "
              f"sh {v['holdout']['sharpe']:6.2f} dd {v['holdout']['max_dd_pct']:6.1f} dsr {v['dsr_N58']['dsr']}")
    print("EDGE:", res["edge"])


if __name__ == "__main__":
    {"devval": devval, "holdout": holdout}[sys.argv[1]]()
