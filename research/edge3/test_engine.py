"""Pruebas del motor v3 (PREREGISTRO_V3 §4): anticipación, costes, ejecución parcial, retiradas, contabilidad, perpetuo.
Uso: python research/edge3/test_engine.py"""
import sys, unittest
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine as E  # noqa: E402


def panel(n=60, assets=("A", "B"), seed=1, vol=1e9):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    P = {k: {} for k in "ohlcv"}
    for a in assets:
        c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
        o = np.r_[c[0], c[:-1]] * np.exp(rng.normal(0, 0.01, n))
        P["o"][a], P["c"][a] = o, c
        P["h"][a], P["l"][a] = np.maximum(o, c) * 1.02, np.minimum(o, c) * 0.98
        P["v"][a] = np.full(n, vol)
    return {k: pd.DataFrame(v, index=idx) for k, v in P.items()}


class T(unittest.TestCase):
    def test_lookahead_detected(self):
        """Un oráculo que conoce el retorno del día siguiente gana; con la misma señal desplazada (legal) no."""
        P = panel(400, ("A",), seed=3)
        fut = P["c"]["A"].shift(-1) / P["o"]["A"].shift(-1)   # retorno apertura→cierre de mañana (prohibido)
        cheat = pd.DataFrame({"A": (fut > 1).astype(float)}).fillna(0.0)
        r1 = E.run(P, cheat, maker=True)["curve"].iloc[-1]
        legal = cheat.shift(1).fillna(0.0)                      # la misma información, ya conocida
        r2 = E.run(P, legal, maker=True)["curve"].iloc[-1]
        self.assertGreater(r1, 2 * r2)                          # el oráculo gana mucho más que la señal legal
        self.assertGreater(r1, 20_000)

    def test_execution_at_next_open(self):
        P = panel(30, ("A",))
        w = pd.DataFrame({"A": [np.nan] * 30}, index=P["c"].index); w.iloc[13] = 1.0
        res = E.run(P, w, maker=True, cap=1.0)
        eq = res["curve"]
        self.assertAlmostEqual(eq.iloc[13], 10_000, places=6)  # el día de la señal no hay posición
        d = P["o"]["A"].iloc[14]; c = P["c"]["A"].iloc[14]
        self.assertAlmostEqual(eq.iloc[14], 10_000 * (1 - 0.0002) * c / d, delta=2.0)  # compra a la apertura de t+1

    def test_costs_round_trip(self):
        P = panel(30, ("A",))
        for k in "oc":
            P[k]["A"] = 100.0
        w = pd.DataFrame({"A": [np.nan] * 30}, index=P["c"].index); w.iloc[12] = 1.0; w.iloc[20] = 0.0
        res = E.run(P, w, cap=1.0)
        rate = 0.001 + 0.0002 + 0.0005 + 0.001 * np.sqrt(10_000 / (1e9 * 0.01))
        self.assertAlmostEqual(res["curve"].iloc[-1], 10_000 * (1 - rate) - 10_000 * (1 - rate) * rate, delta=1.0)
        self.assertEqual(len(res["episodes"]), 1)
        self.assertAlmostEqual(res["episodes"][0][1], res["curve"].iloc[-1] - 10_000, delta=0.01)

    def test_partial_fill(self):
        P = panel(30, ("A",), vol=200_000)                       # 1 % del volumen = 2 000 USD
        w = pd.DataFrame({"A": [np.nan] * 30}, index=P["c"].index); w.iloc[12] = 1.0
        res = E.run(P, w, cap=1.0)
        ex = res["exposure"]
        self.assertLess(ex.iloc[13], 0.3); self.assertGreater(ex.iloc[19], 0.9)

    def test_delisting_haircut(self):
        P = panel(30, ("A",))
        for k in "ohlcv":
            P[k].iloc[20:, 0] = np.nan
        w = pd.DataFrame({"A": [np.nan] * 30}, index=P["c"].index); w.iloc[12] = 1.0
        res = E.run(P, w, maker=True, cap=1.0)
        self.assertGreater(res["delist_loss"], 0)
        self.assertEqual(res["exposure"].iloc[-1], 0.0)

    def test_accounting_identity(self):
        P = panel(200, ("A", "B", "C"), seed=5)
        rng = np.random.default_rng(0)
        w = pd.DataFrame(rng.random((200, 3)) / 3, index=P["c"].index, columns=list("ABC"))
        w.iloc[::3] = np.nan
        res = E.run(P, w)
        self.assertAlmostEqual(res["asset_pnl"].sum(), res["curve"].iloc[-1] - 10_000, delta=0.01)

    def test_perp_hedge_neutral(self):
        """Con perpetuo = spot y funding constante, el resultado ≈ funding − costes (sin riesgo de precio)."""
        P = panel(100, ("A",), seed=7)
        f = pd.DataFrame({"A": 0.0003}, index=P["c"].index)
        w = pd.DataFrame({"A": [np.nan] * 100}, index=P["c"].index); w.iloc[12] = 1 / 1.5
        h = pd.DataFrame({"A": [np.nan] * 100}, index=P["c"].index); h.iloc[12] = 1.0
        res = E.run(P, w, cap=1.0, hedge=h, perp_o=P["o"], perp_c=P["c"], funding=f, maker=True)
        eq = res["curve"]
        self.assertGreater(res["funding"], 0)
        r = eq.pct_change().dropna()
        self.assertLess(r.iloc[16:].std(), 0.002)               # sin exposición direccional
        self.assertAlmostEqual(res["asset_pnl"].sum(), eq.iloc[-1] - 10_000, delta=0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
