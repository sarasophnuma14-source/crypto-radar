"""Prueba a ciegas 2025→hoy de las configuraciones elegidas ANTES con datos 2021–2024. Se corre una sola vez."""
import json, sys
from pathlib import Path
import lab

PICKS = [  # elegidas por Sharpe promedio con sus vecinos en 2021–2024 (estabilidad, no el máximo aislado)
    ("Tendencia BTC (media simple)", {"n": 100}),
    ("Ruptura + stop ATR", {"n": 100, "atr_k": 2.0, "filtro_btc_sma": 100}),
    ("Rotación por momentum", {"ventana": 14, "top": 10, "filtro_btc_sma": 100, "vol_min": 2e7}),
    ("Reversión RSI(2)", {"rsi_bajo": 5, "top_liquidez": 5}),
]
WINNER = "Combinada 50 % BTC tendencia + 50 % rupturas"   # decidida antes de mirar 2025→hoy

if __name__ == "__main__":
    P = lab.load_panel(sys.argv[1]); D = lab.derived(P); out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    w = "2020-06-01"; rows = {}; curves = {}
    for fam, params in PICKS:
        eq, tr = lab.rebuild(P, D, fam, params, w)
        trn = tr if len(tr) else None
        rows[fam] = {"params": params, "diseño_2021_2024": lab.stats(eq, *lab.DESIGN, trn),
                     "prueba_2025_hoy": lab.stats(eq, *lab.HOLDOUT, trn), "total": lab.stats(eq, lab.DESIGN[0], lab.HOLDOUT[1], trn)}
        curves[fam] = eq
        if fam == "Ruptura + stop ATR":
            tr.to_csv(out / "operaciones_rupturas.csv", index=False)
    combo = lab.blend([curves["Tendencia BTC (media simple)"], curves["Ruptura + stop ATR"]], [0.5, 0.5])
    curves[WINNER] = combo
    rows[WINNER] = {"params": {"peso_btc": 0.5, "peso_rupturas": 0.5}, "diseño_2021_2024": lab.stats(combo, *lab.DESIGN),
                    "prueba_2025_hoy": lab.stats(combo, *lab.HOLDOUT), "total": lab.stats(combo, lab.DESIGN[0], lab.HOLDOUT[1])}
    btc = P["c"]["BTC"].dropna()
    rows["BTC comprar y mantener"] = {"diseño_2021_2024": lab.stats(btc, *lab.DESIGN), "prueba_2025_hoy": lab.stats(btc, *lab.HOLDOUT),
                                      "total": lab.stats(btc, lab.DESIGN[0], lab.HOLDOUT[1])}
    curves["BTC comprar y mantener"] = btc / btc.loc[btc.index >= w].iloc[0]
    import pandas as pd
    pd.concat(curves, axis=1).loc[lab.DESIGN[0]:].to_csv(out / "curvas.csv")
    (out / "prueba_ciega.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=float))
    print(json.dumps(rows, ensure_ascii=False, indent=1, default=float))
