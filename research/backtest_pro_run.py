"""Corre el backtest profesional completo sobre el panel histórico de Binance y escribe BACKTEST_REPORT.md.

  1. Base con parámetros por defecto: periodo completo, dentro de muestra (IS) y fuera de muestra (OOS).
  2. Calibración SOLO en IS (rejilla pequeña) y evaluación del elegido en OOS.
  3. Walk-forward anual: para cada año se eligen los parámetros con los 2 años previos y se prueba en ese año.
  4. Sensibilidad a costos, posiciones máximas, salidas parciales y Exit Intelligence.
  5. Validación de la puntuación: rendimiento futuro a 20 días por quintil y correlación por rangos (IC) por familia.
Uso: python3 research/backtest_pro_run.py [--universe 150]
"""
import argparse, csv, datetime as dt, glob, gzip, itertools, json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from radar.quant import backtest_pro as B

ap = argparse.ArgumentParser()
ap.add_argument("--universe", type=int, default=150)
ap.add_argument("--split", default="2024-01-01")
args = ap.parse_args()
OUT = ROOT / "data" / "research"
T0 = time.time()


def log(*a):
    print(f"[{time.time() - T0:6.0f}s]", *a, flush=True)


def ms(d):
    return int(dt.datetime.fromisoformat(d).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


gz = OUT / "panel.json.gz"
if gz.exists():
    panel = json.load(gzip.open(gz, "rt"))
else:
    panel = {os.path.basename(f)[:-5]: json.load(open(f)) for f in glob.glob(str(OUT / "cache" / "*.json"))}
log("monedas en el panel:", len(panel))
mk = B.Market(panel, log=log)
first, last = mk.days[0], mk.days[-1]
log("calculando señales del universo...")
sig, samples = B.precompute_signals(mk, cfg={"universe_size": args.universe}, log=log)
sig_days = sorted(sig)
START, SPLIT, END = sig_days[0], ms(args.split), sig_days[-1]
log("señales listas", B.day(START), "→", B.day(END))

KEYS = ["total_return_pct", "cagr_pct", "trades", "win_rate_pct", "profit_factor", "expectancy_usd", "avg_R",
        "sharpe", "sortino", "max_drawdown_pct", "longest_recovery_days", "avg_exposure_pct", "fees_usd",
        "btc_buy_hold_pct", "btc_max_drawdown_pct"]


def run(start, end, cfg=None):
    return B.simulate(mk, sig, start, end, cfg)


def objective(m):
    if (m["trades"] or 0) < 30 or m["sharpe"] is None:
        return -9e9
    return m["sharpe"]


GRID = {"min_score_offset": [-10, -5, 0, 5, 10], "use_exit_intelligence": [True, False],
        "order_expiry_days": [2, 4], "limits": [{"risk_per_trade_pct": 1.0}, {"risk_per_trade_pct": 0.75}]}
combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]


def calibrate(start, end):
    best, best_m = None, None
    rows = []
    for cfg in combos:
        m = run(start, end, cfg)["metrics"]
        rows.append((cfg, m))
        if best_m is None or objective(m) > objective(best_m):
            best, best_m = cfg, m
    return best, best_m, rows


res = {"generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "coins": len(panel),
       "period": [B.day(START), B.day(END)], "split": args.split, "universe_size": args.universe,
       "defaults": {k: v for k, v in B.DEFAULTS.items() if k != "limits"}}
base_full = run(START, END)
res["base_full"] = base_full["metrics"]
res["base_is"] = run(START, SPLIT - 1)["metrics"]
res["base_oos"] = run(SPLIT, END)["metrics"]
log("base listo", {k: res["base_full"][k] for k in ("total_return_pct", "trades", "profit_factor", "sharpe")})

best, best_m, rows = calibrate(START, SPLIT - 1)
res["calibration"] = {"best": best, "is": best_m, "oos": run(SPLIT, END, best)["metrics"],
                      "grid": [{"cfg": c, **{k: m[k] for k in ("total_return_pct", "trades", "profit_factor", "sharpe",
                                                               "max_drawdown_pct")}} for c, m in rows]}
log("calibración", best, "OOS sharpe", res["calibration"]["oos"]["sharpe"])

wf = []
years = sorted({B.day(t)[:4] for t in sig_days})
for y in years[2:]:
    ys, ye = ms(f"{y}-01-01"), ms(f"{int(y) + 1}-01-01") - 1
    ts = ms(f"{int(y) - 2}-01-01")
    b, bm, _ = calibrate(max(ts, START), ys - 1)
    tm = run(ys, min(ye, END), b)["metrics"]
    wf.append({"year": y, "chosen": b, "train_sharpe": bm["sharpe"], "test": {k: tm.get(k) for k in KEYS}})
    log("walk-forward", y, b, tm["total_return_pct"])
eq = 1.0
for w in wf:
    eq *= 1 + w["test"]["total_return_pct"] / 100
res["walk_forward"] = {"years": wf, "chained_return_pct": round((eq - 1) * 100, 2)}

SENS = {"Costos x2 (comisión 0,2 %, deslizamiento 0,2 %)": {"fee_pct": 0.2, "slippage_pct": 0.2},
        "Deslizamiento 0,3 %": {"slippage_pct": 0.3},
        "Sin costos (referencia, irreal)": {"fee_pct": 0, "slippage_pct": 0, "spread_pct": 0},
        "Máximo 3 posiciones": {"limits": {"max_positions": 3}},
        "Máximo 10 posiciones": {"limits": {"max_positions": 10, "max_open_risk_pct": 8}},
        "Sin objetivos parciales (solo stop/trailing/salida)": {"partials": ()},
        "Sin Exit Intelligence": {"use_exit_intelligence": False},
        "Puntaje mínimo +10": {"min_score_offset": 10},
        "Puntaje mínimo −10": {"min_score_offset": -10},
        "Riesgo por operación 2 %": {"limits": {"risk_per_trade_pct": 2.0, "max_open_risk_pct": 10}},
        "Órdenes válidas 1 día": {"order_expiry_days": 1}}
res["sensitivity"] = {k: {kk: v["metrics"].get(kk) for kk in KEYS} for k, v in
                      ((k, run(START, END, c)) for k, c in SENS.items())}
log("sensibilidad lista")
res["score_validation"] = {"is": B.score_validation([s for s in samples if s["t"] < SPLIT]),
                           "oos": B.score_validation([s for s in samples if s["t"] >= SPLIT])}
res["base_trades"] = len(base_full["trades"])
(OUT / "backtest_pro_results.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))
with open(OUT / "backtest_pro_trades.csv", "w", newline="") as fh:
    cols = [c for c in base_full["trades"][0] if c != "fills"] if base_full["trades"] else []
    w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore"); w.writeheader(); w.writerows(base_full["trades"])
with open(OUT / "backtest_pro_curve.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["date", "equity", "btc_buy_hold"])
    bm = dict(base_full["benchmark"])
    for d, v in base_full["curve"]:
        w.writerow([d, round(v, 2), round(bm.get(d, 0), 2)])
log("resultados en", OUT / "backtest_pro_results.json")
