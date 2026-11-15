"""Motor de paper trading de D_volmom_L28.

  python3 main.py paper init  [nombre]        crea la evaluación (congela la especificación) y descarga velas
  python3 main.py paper step  [nombre]        procesa los días cerrados pendientes (ejecutar a diario tras 00:00 UTC)
  python3 main.py paper report [nombre]       métricas, comparación con BTC y efectivo, criterios de aceptación
  python3 main.py paper replay <desde> <hasta> [nombre]   recorrido HISTÓRICO con el mismo motor (no es prospectivo)

Reglas:
- Estrategia EXACTA D_volmom_L28 (selection_frozen.json) con el simulador v2 y portfolio_risk. Sin parámetros nuevos.
- La especificación y el hash del código que decide (estrategia, indicadores, simulador, riesgo, datos) se congelan en
  `init`. Si el código cambia, `step` se niega a seguir: hay que abrir otra evaluación con otro nombre.
- Solo velas cerradas; la señal se calcula al cierre de D y se ejecuta en la apertura de D+1.
- Si faltan datos de un día (BTC sin vela o < 90 % de los símbolos del día anterior), el día no se procesa.
- Duración mínima 183 días antes de evaluar los criterios.
- Sin órdenes reales: ver execution.place_real_order.
"""
import datetime as dt, hashlib, json, os
from pathlib import Path
import numpy as np
import pandas as pd

from radar.edge import data as edata, features, strategies, sim, portfolio_risk as PR
from radar.paper_trading import REAL_ORDERS_ENABLED, storage as pstore, execution

ROOT = Path(__file__).resolve().parents[2]
NAME = "D_volmom_L28"
UNIVERSE = {"size": 150, "min_adv": 2e6, "min_bars": 120}
CODE_FILES = ["radar/edge/strategies.py", "radar/edge/features.py", "radar/edge/sim.py", "radar/edge/portfolio_risk.py",
              "radar/edge/data.py"]
MIN_DAYS = 183
KEEP_EQ = 60


def code_hash():
    h = hashlib.sha256()
    for f in CODE_FILES:
        h.update(f.encode()); h.update((ROOT / f).read_bytes())
    return h.hexdigest()


def frozen_selection():
    sel = json.loads((ROOT / "research" / "edge" / "selection_frozen.json").read_text())["selection"]["D"]
    assert sel["chosen"] == NAME, "la selección congelada de la familia D no es D_volmom_L28"
    return sel


def make_spec(start_date, mode, capital=10_000.0):
    spec = {"strategy": NAME, "family": "D", "params": {"L": 28, "entry": "top 5 por ret28/vol28 con ret28 > 0 y cierre > SMA28",
                                                        "exit": "sale del top 10 (lunes)", "stop_atr": 3.0,
                                                        "crash_exit": "BTC 7 días < −15 %", "weekly": True},
            "frozen_selection": frozen_selection(), "simulator": "v2", "risk": dict(sim.RISK, capital=capital),
            "risk_model": PR.PARAMS, "universe": UNIVERSE, "scenario": "base", "costs": "comisión 0,10 % + medio spread + "
            "deslizamiento por tramo de ADV (sim.cost_rate)", "data_source": "Binance spot USDT 1d (data-api.binance.vision)",
            "stables_excluded": sorted(edata.STABLE_EXTRA), "start_date": start_date, "min_duration_days": MIN_DAYS,
            "mode": mode, "real_orders": False, "code_files": CODE_FILES, "code_hash": code_hash(),
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}
    spec["spec_hash"] = hashlib.sha256(json.dumps({k: v for k, v in spec.items() if k != "created_at"}, sort_keys=True,
                                                  default=str).encode()).hexdigest()
    return spec


def check_spec(spec):
    if spec["code_hash"] != code_hash():
        raise SystemExit("El código que decide las señales cambió desde el inicio de esta evaluación "
                         f"({spec['code_hash'][:12]} → {code_hash()[:12]}). Seguir invalidaría el paper trading: "
                         "abre una evaluación nueva con otro nombre.")
    if spec["risk"] != dict(sim.RISK, capital=spec["risk"]["capital"]) or spec["risk_model"] != PR.PARAMS:
        raise SystemExit("Los parámetros de riesgo no coinciden con los congelados. No se continúa.")
    assert not spec.get("real_orders") and REAL_ORDERS_ENABLED is False


def build(P):
    F = features.compute(P)
    U = features.universe(F, **UNIVERSE)
    strat = next(s for s in strategies.build_all(P, F, U) if s.name == NAME)
    return F, U, strat


def data_complete(P, t):
    C = P["c"]
    if "BTC" not in C or not np.isfinite(C["BTC"].iloc[t]):
        return False, "BTC sin vela cerrada"
    if t == 0:
        return True, None
    n_prev, n_now = int(C.iloc[t - 1].notna().sum()), int(C.iloc[t].notna().sum())
    if n_prev and n_now < 0.9 * n_prev:
        return False, f"solo {n_now} de {n_prev} símbolos con vela"
    return True, None


def _json_state(S):
    S = dict(S); S["eq_hist"] = S["eq_hist"][-KEEP_EQ:]; S["events"] = []; S["trades"] = []
    return json.loads(json.dumps(S, default=lambda o: o.item() if hasattr(o, "item") else str(o)))


def init(name, store=None, start_date=None, mode="live", capital=10_000.0):
    store = store or pstore.open_store(name)
    if store.read_json("spec.json"):
        raise SystemExit(f"La evaluación '{name}' ya existe; no se reinicia (usa otro nombre).")
    start_date = start_date or (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)).isoformat()
    spec = make_spec(start_date, mode, capital)
    store.write_json("spec.json", spec)
    store.write_json("state.json", dict(_json_state(sim.new_state(capital)), last_date=None))
    return spec


def process(store, P, until=None):
    """Procesa en orden los días cerrados posteriores al último procesado (y ≥ start_date). Devuelve las filas nuevas."""
    spec = store.read_json("spec.json"); check_spec(spec)
    S = store.read_json("state.json"); S.setdefault("events", []); S.setdefault("trades", [])
    F, U, strat = build(P)
    E = sim.Engine(P, F, strat, spec["scenario"], risk=spec["risk"], rparams=spec["risk_model"])
    dates = E.dates
    start = pd.Timestamp(spec["start_date"]); last = pd.Timestamp(S["last_date"]) if S.get("last_date") else None
    todo = [d for d in dates if d >= start and (last is None or d > last) and (until is None or d <= pd.Timestamp(until))]
    eq_rows = store.read_all("equity")
    btc0 = eq_rows[0]["btc_close"] if eq_rows else None
    out = []
    for d in todo:
        t = dates.get_loc(d)
        ok, why = data_complete(P, t)
        if not ok:
            store.append("events", [{"date": d.date().isoformat(), "type": "day_skipped", "symbol": None, "reason": why}])
            break
        if last is not None and (d - last).days > 1:
            gap = (d - last).days - 1
            store.append("events", [{"date": d.date().isoformat(), "type": "warning", "symbol": None,
                                     "reason": f"{gap} día(s) sin procesar antes de este; se continúa sin rellenar"}])
        row = E.step(S, t)
        btc = float(P["c"]["BTC"].iloc[t]); btc0 = btc0 or btc
        row.update({"btc_close": btc, "btc_bh_equity": spec["risk"]["capital"] * btc / btc0,
                    "cash_equity": spec["risk"]["capital"], "btc_bear": bool(F["btc_bear"].iloc[t]),
                    "universe_size": int(U.iloc[t].sum()), "processed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
        store.append("events", S["events"]); store.append("trades", S["trades"]); store.append("equity", [row])
        S["events"], S["trades"] = [], []
        S["last_date"] = d.date().isoformat(); last = d
        store.write_json("state.json", dict(_json_state(S), last_date=S["last_date"]))
        out.append(row)
    return out


def cache_path():
    from radar.config import DATA_DIR
    return Path(os.environ.get("PAPER_CANDLES", DATA_DIR / "paper" / "candles_1d.json.gz"))


def live_panel(held=(), log=print):
    cache = execution.CandleCache(cache_path())
    syms = execution.tradable_symbols() | set(held) | {"BTC", "ETH"}
    info = cache.update(syms, log=log)
    cache.save()
    raw = {s: v for s, v in cache.d.items() if s in syms}
    return edata.panel_from_raw(raw), info


def step_live(name, log=print):
    store = pstore.open_store(name)
    if not store.read_json("spec.json"):
        raise SystemExit(f"No existe la evaluación '{name}'. Créala con: python3 main.py paper init {name}")
    S = store.read_json("state.json")
    P, info = live_panel(held=S.get("pos", {}).keys(), log=log)
    if info["errors"]:
        store.append("events", [{"date": info["last_closed"], "type": "data_errors", "symbol": None,
                                 "reason": f"{len(info['errors'])} símbolos sin descarga", "detail": dict(list(info["errors"].items())[:20])}])
    rows = process(store, P)
    return {"processed_days": [r["date"] for r in rows], "last_closed": info["last_closed"],
            "download_errors": len(info["errors"]), "equity": rows[-1]["equity"] if rows else None}


def replay(name, start, end, store=None, P=None):
    """Recorrido histórico con el panel de investigación. Es una DEMOSTRACIÓN del motor y del diario, no evidencia."""
    store = store or pstore.open_store(name)
    if not store.read_json("spec.json"):
        init(name, store, start_date=start, mode="replay_historico (no prospectivo)")
    P = P if P is not None else edata.drop_stables(edata.build())
    return process(store, P, until=end)
