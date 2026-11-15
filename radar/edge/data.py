"""Carga del panel histórico, limpieza y matrices alineadas por fecha (sin rellenar datos)."""
import gzip, json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "data" / "research"
GAP_DAYS = 7
EXCLUDE = {"WBTC", "WBETH", "BNSOL", "PAXG", "XAUT"}
# Auditoría (B11): dos monedas estables se colaron en el panel porque su ticker no contiene "USD": PAX (Paxos, 2020-21)
# y U (2026). build() se deja como estaba para que el holdout v1 sea reproducible; el simulador v2 y el paper trading
# las quitan con drop_stables().
STABLE_EXTRA = {"PAX", "U", "USD1", "RLUSD", "XUSD", "BFUSD", "USDE", "USDP", "TUSD", "FDUSD", "USDC", "EURI", "AEUR",
                "EUR", "PYUSD", "USDS", "USDD", "USDTB", "USDF", "USD0"}


def _is_stock_token(sym, rec):
    return rec.get("status") == "DELISTED" and sym.endswith("B") and len(rec["t"]) < 60 and rec["t"][0] > 1.78e12


def load_raw(include_delisted=True):
    raw = json.load(gzip.open(RESEARCH / "panel.json.gz", "rt"))
    if include_delisted and (RESEARCH / "panel_delisted.json.gz").exists():
        for k, v in json.load(gzip.open(RESEARCH / "panel_delisted.json.gz", "rt")).items():
            if k not in raw and not _is_stock_token(k, v):
                raw[k] = v
    return {k: v for k, v in raw.items() if k not in EXCLUDE}


def split_gaps(raw, log=None):
    """Una serie con un hueco > GAP_DAYS se parte: SYM (tramo antiguo, retirado) y SYM~2 (tramo nuevo)."""
    out = {}
    for s, v in raw.items():
        t = v["t"]; cuts = [0] + [i for i in range(1, len(t)) if (t[i] - t[i - 1]) / 864e5 > GAP_DAYS] + [len(t)]
        for j in range(len(cuts) - 1):
            a, b = cuts[j], cuts[j + 1]
            name = s if j == len(cuts) - 2 else f"{s}~old{j + 1}"
            out[name] = {k: v[k][a:b] for k in "tohlcv"}
            out[name]["status"] = v.get("status", "TRADING") if name == s else "SPLIT"
            if log is not None and len(cuts) > 2:
                log.append({"symbol": s, "part": name, "bars": b - a})
    return out


def build(include_delisted=True):
    """Devuelve dict con DataFrames (fecha × símbolo) o, h, l, c, v y metadatos."""
    log = []
    raw = split_gaps(load_raw(include_delisted), log)
    cols = {k: {} for k in "ohlcv"}
    for s, v in raw.items():
        idx = pd.to_datetime(v["t"], unit="ms").normalize()
        for k in "ohlcv":
            cols[k][s] = pd.Series(np.asarray(v[k], float), index=idx)
    P = {k: pd.DataFrame(d).sort_index() for k, d in cols.items()}
    full = pd.date_range(P["c"].index.min(), P["c"].index.max(), freq="D")
    P = {k: df[~df.index.duplicated()].reindex(full) for k, df in P.items()}
    for k in "ohlc":
        P[k] = P[k].where(P[k] > 0)
    P["status"] = {s: v.get("status") for s, v in raw.items()}
    P["split_log"] = log
    return P


def drop_stables(P):
    """Copia del panel sin monedas estables (usado por el simulador v2 y el paper trading)."""
    keep = [c for c in P["c"].columns if c.split("~")[0] not in STABLE_EXTRA]
    out = {k: P[k][keep] for k in "ohlcv"}
    out["status"] = {s: v for s, v in P["status"].items() if s in keep}
    out["split_log"] = P.get("split_log", [])
    return out


def panel_from_raw(raw):
    """Panel (fecha × símbolo) a partir de velas {sym: {t,o,h,l,c,v}}; misma limpieza que build() (huecos, ceros)."""
    raw = split_gaps({k: v for k, v in raw.items() if k not in EXCLUDE and v.get("t")})
    cols = {k: {} for k in "ohlcv"}
    for s, v in raw.items():
        idx = pd.to_datetime(v["t"], unit="ms").normalize()
        for k in "ohlcv":
            cols[k][s] = pd.Series(np.asarray(v[k], float), index=idx)
    P = {k: pd.DataFrame(d).sort_index() for k, d in cols.items()}
    full = pd.date_range(P["c"].index.min(), P["c"].index.max(), freq="D")
    P = {k: df[~df.index.duplicated()].reindex(full) for k, df in P.items()}
    for k in "ohlc":
        P[k] = P[k].where(P[k] > 0)
    P["status"] = {s: v.get("status") for s, v in raw.items()}
    P["split_log"] = []
    return drop_stables(P)
