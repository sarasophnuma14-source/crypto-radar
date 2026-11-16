"""Auditoría de calidad de datos (PREREGISTRO_V3 §1). Solo lectura. Salida: research/edge3/results/auditoria_datos.json"""
import gzip, json, sys, time, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from radar.edge import data as D  # noqa: E402


def coinbase(product):
    """Velas diarias de Coinbase (USD) 2020-01-01 → 2026-11-14, en bloques de 300 días."""
    out = {}
    s = pd.Timestamp("2020-01-01")
    while s < pd.Timestamp("2026-11-15"):
        e = min(s + pd.Timedelta(days=299), pd.Timestamp("2026-11-14"))
        url = (f"https://api.exchange.coinbase.com/products/{product}/candles?granularity=86400"
               f"&start={s.date()}T00:00:00Z&end={e.date()}T00:00:00Z")
        req = urllib.request.Request(url, headers={"User-Agent": "research-client"})
        for k in range(3):
            try:
                rows = json.loads(urllib.request.urlopen(req, timeout=30).read()); break
            except Exception:
                time.sleep(2 + 2 * k); rows = []
        for t, lo, hi, op, cl, vo in rows:
            out[pd.Timestamp(t, unit="s")] = cl
        s = e + pd.Timedelta(days=1); time.sleep(0.4)
    return pd.Series(out).sort_index()


def main():
    raw = D.load_raw()
    rep = {"monedas_brutas": len(raw)}
    dup = off = ohlc = zero_v = 0; n_bars = 0
    for s, v in raw.items():
        t = np.asarray(v["t"], float); n_bars += len(t)
        dup += int(len(t) - len(np.unique(t)))
        off += int((t % 86_400_000 != 0).sum())
        o, h, l, c, vol = (np.asarray(v[k], float) for k in "ohlcv")
        ohlc += int(((h < np.maximum(o, c) - 1e-12) | (l > np.minimum(o, c) + 1e-12)).sum())
        zero_v += int((vol == 0).sum())
    rep.update(velas=n_bars, duplicadas=dup, fuera_de_medianoche_utc=off, incoherencias_ohlc=ohlc, volumen_cero=zero_v)
    P = D.drop_stables(D.build())
    C = P["c"]
    first, last = C.apply(lambda s: s.first_valid_index()), C.apply(lambda s: s.last_valid_index())
    gaps = 0
    for col in C.columns:
        s = C[col].loc[first[col]:last[col]]; gaps += int(s.isna().sum())
    R = C.pct_change(fill_method=None)
    rep.update(activos_panel=C.shape[1], dias=C.shape[0], desde=str(C.index[0].date()), hasta=str(C.index[-1].date()),
               velas_faltantes_internas_huecos_le_7d=gaps,
               retornos_diarios_mayores_100pct=int((R > 1).sum().sum()), retornos_menores_80pct=int((R < -0.8).sum().sum()),
               estado=pd.Series(P["status"]).value_counts().to_dict(),
               series_partidas=len(P.get("split_log", [])))
    # sesgo de supervivencia: activos del universo (top 50 por volumen) que después dejaron de cotizar
    adv = P["v"].rolling(30, min_periods=20).mean()
    end = C.index[-1]
    surv = {}
    for y in range(2020, 2027):
        d = pd.Timestamp(f"{y}-06-30") if y < 2026 else pd.Timestamp("2026-06-30")
        top = adv.loc[d].dropna().nlargest(50).index
        gone = [a for a in top if last[a] < end - pd.Timedelta(days=7)]
        surv[str(y)] = {"top50": len(top), "retiradas_despues": len(gone), "ejemplos": gone[:8]}
    rep["supervivencia_top50"] = surv
    # funding
    fz = json.load(gzip.open(ROOT / "data/research/funding/perp_funding_klines.json.gz", "rt"))
    cov = {}
    for perp, rows in fz["funding"].items():
        if not rows:
            continue
        t = np.array([r[0] for r in rows]); dt = np.diff(np.sort(t)) / 3.6e6
        cov[perp] = {"desde": str(pd.Timestamp(t.min(), unit="ms").date()), "registros": len(rows),
                     "huecos_mayores_9h": int((dt > 9).sum()), "intervalo_mediano_h": float(np.median(dt)) if len(dt) else None}
    rep["funding"] = {"perpetuos": len(cov), "con_huecos": sum(1 for v in cov.values() if v["huecos_mayores_9h"]),
                      "manifiesto_zips": len(fz["manifest"]), "ejemplo": {k: cov[k] for k in list(cov)[:5]},
                      "BTCUSDT": cov.get("BTCUSDT"), "ETHUSDT": cov.get("ETHUSDT")}
    # comparación con otro exchange
    cmp = {}
    for sym, prod in (("BTC", "BTC-USD"), ("ETH", "ETH-USD")):
        try:
            cb = coinbase(prod)
            j = pd.concat([C[sym], cb], axis=1, keys=["binance_usdt", "coinbase_usd"]).dropna()
            dif = (j.binance_usdt / j.coinbase_usd - 1).abs() * 100
            cmp[sym] = {"dias_comparados": len(j), "dif_mediana_pct": round(float(dif.median()), 4),
                        "dif_p99_pct": round(float(dif.quantile(0.99)), 4), "dif_max_pct": round(float(dif.max()), 4),
                        "fecha_dif_max": str(dif.idxmax().date())}
        except Exception as e:
            cmp[sym] = {"error": type(e).__name__}
    rep["comparacion_coinbase"] = cmp
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "auditoria_datos.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False, default=str))
    print(json.dumps(rep, indent=1, ensure_ascii=False, default=str)[:4000])


if __name__ == "__main__":
    main()
