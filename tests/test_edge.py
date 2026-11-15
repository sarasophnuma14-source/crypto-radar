"""Pruebas del laboratorio de ventaja (radar/edge). Datos sintéticos, sin red.
python3 tests/test_edge.py -v"""
import json, math, sys, tempfile, unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from radar.edge import data, features, strategies, sim, metrics, manip, stats

N = 300


def make_P(paths, vols=None, start="2022-01-01"):
    idx = pd.date_range(start, periods=N, freq="D")
    P = {k: {} for k in "ohlcv"}
    for s, c in paths.items():
        c = pd.Series(c, index=idx[:len(c)]).reindex(idx)
        o = c.shift(1).fillna(c)
        P["o"][s], P["c"][s] = o, c
        P["h"][s] = np.maximum(o, c) * 1.01
        P["l"][s] = np.minimum(o, c) * 0.99
        P["v"][s] = pd.Series((vols or {}).get(s, 50e6), index=idx).where(c.notna())
    P = {k: pd.DataFrame(v) for k, v in P.items()}
    P["status"] = {s: "TRADING" for s in paths}
    return P


def trend(p0=100, g=0.002, n=N):
    return list(p0 * np.exp(g * np.arange(n)))


def setup(P):
    F = features.compute(P); U = features.universe(F, size=150, min_adv=1e6, min_bars=30)
    return F, U


def strat(P, entry_day, name="T", **kw):
    c = P["c"]
    ent = pd.DataFrame(False, index=c.index, columns=c.columns)
    for s, d in entry_day.items():
        ent.loc[c.index[d], s] = True
    s = strategies.Strategy(name, "T", {}, entry=ent, score=pd.DataFrame(1.0, index=c.index, columns=c.columns),
                            exit_sig=pd.DataFrame(False, index=c.index, columns=c.columns), **kw)
    return s


class TEdgeData(unittest.TestCase):
    def test_split_gaps_creates_two_assets(self):
        t = [i * 864e5 for i in range(10)] + [(30 + i) * 864e5 for i in range(10)]
        raw = {"X": {k: list(range(1, 21)) for k in "ohlcv"} | {"t": t, "status": "TRADING"}}
        out = data.split_gaps(raw)
        self.assertEqual(set(out), {"X", "X~old1"}); self.assertEqual(len(out["X~old1"]["t"]), 10)

    def test_no_split_without_gap(self):
        raw = {"X": {k: [1.0] * 5 for k in "ohlcv"} | {"t": [i * 864e5 for i in range(5)]}}
        self.assertEqual(list(data.split_gaps(raw)), ["X"])

    def test_stock_tokens_excluded(self):
        self.assertTrue(data._is_stock_token("AMCB", {"status": "DELISTED", "t": [1.79e12] * 10}))
        self.assertFalse(data._is_stock_token("NBT", {"status": "DELISTED", "t": [1.65e12] * 300}))


class TEdgeFeatures(unittest.TestCase):
    def test_causal_truncation(self):
        P = make_P({"BTC": trend(), "A": list(100 + np.sin(np.arange(N) / 7) * 10 + np.arange(N) * 0.1)})
        F = features.compute(P)
        Pt = {k: (v.iloc[:200] if isinstance(v, pd.DataFrame) else v) for k, v in P.items()}
        Ft = features.compute(Pt)
        for key in ("atr", "ret28", "hi55", "lo27", "bbw_pct", "vratio", "rs28", "sma200", "wk_above10"):
            a, b = F[key].iloc[:200]["A"], Ft[key]["A"]
            pd.testing.assert_series_equal(a, b, check_names=False, obj=key)

    def test_donchian_excludes_today(self):
        P = make_P({"BTC": trend(), "A": [100.0] * 100 + [120.0] + [100.0] * (N - 101)})
        F = features.compute(P)
        self.assertEqual(F["hi20"]["A"].iloc[100], 101.0)     # máximo previo, sin la vela de hoy

    def test_weekly_only_after_week_closes(self):
        P = make_P({"BTC": trend(), "A": trend()})
        F = features.compute(P)
        first = F["wk_above10"]["A"].first_valid_index()
        self.assertEqual(first.weekday(), 6)                # domingo: cierre de la semana

    def test_universe_point_in_time(self):
        P = make_P({"BTC": trend(), "A": trend()}, vols={"A": 1e5})
        F, U = setup(P)
        self.assertFalse(U["A"].any())


class TEdgeSim(unittest.TestCase):
    def setUp(self):
        self.P = make_P({"BTC": trend(), "A": trend(10, 0.003), "B": trend(20, 0.003)})
        self.F, self.U = setup(self.P)

    def run_s(self, s, scen="base", P=None):
        P = P or self.P
        F = features.compute(P) if P is not self.P else self.F
        return sim.simulate(P, F, s, P["c"].index[60], P["c"].index[-1], scen)

    def test_entry_next_open_with_cost(self):
        r = self.run_s(strat(self.P, {"A": 100}))
        t = r["trades"][0]
        self.assertEqual(t["entry_date"], self.P["c"].index[101].date().isoformat())
        o = self.P["o"]["A"].iloc[101]
        self.assertAlmostEqual(t["entry_px"], o * (1 + sim.cost_rate(self.F["adv30"]["A"].iloc[100], 1)), places=9)

    def test_costs_scale_with_scenario(self):
        self.assertAlmostEqual(sim.cost_rate(60e6, 2), 2 * sim.cost_rate(60e6, 1))
        self.assertGreater(sim.cost_rate(1e6, 1), sim.cost_rate(60e6, 1))

    def test_stop_gap_fills_at_open(self):
        c = trend(10, 0.003); c[150:] = [x * 0.5 for x in c[150:]]
        P = make_P({"BTC": trend(), "A": c, "B": trend()})
        d = P["c"].index[150]; P["o"].loc[d, "A"] = P["c"]["A"].iloc[150]; P["h"].loc[d, "A"] = P["c"]["A"].iloc[150] * 1.01
        r = self.run_s(strat(P, {"A": 120}), P=P)
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "Stop")
        rate = sim.cost_rate(features.compute(P)["adv30"]["A"].iloc[150], 1)
        self.assertAlmostEqual(t["exit_px"], P["o"]["A"].iloc[150] * (1 - rate), places=9)

    def test_stop_checked_on_entry_day(self):
        P = make_P({"BTC": trend(), "A": trend(10, 0.003), "B": trend()})
        P["l"].loc[P["c"].index[101], "A"] = P["o"]["A"].iloc[101] * 0.5
        r = self.run_s(strat(P, {"A": 100}), P=P)
        self.assertEqual(r["trades"][0]["exit_reason"], "Stop el día de entrada")

    def test_chase_cancelled(self):
        P = make_P({"BTC": trend(), "A": trend(10, 0.003), "B": trend()})
        P["o"].loc[P["c"].index[101], "A"] = P["c"]["A"].iloc[100] * 1.5
        P["h"].loc[P["c"].index[101], "A"] = P["c"]["A"].iloc[100] * 1.6
        r = self.run_s(strat(P, {"A": 100}), P=P)
        self.assertEqual(len(r["trades"]), 0)

    def test_risk_sizing_half_percent(self):
        r = self.run_s(strat(self.P, {"A": 100}))
        t = r["trades"][0]
        atr = self.F["atr"]["A"].iloc[100]
        self.assertLessEqual(t["qty"] * 3 * atr, 10_000 * 0.005 * 1.0001)

    def test_liquidity_cap(self):
        P = make_P({"BTC": trend(), "A": trend(10, 0.003), "B": trend()}, vols={"A": 2e6})
        F = features.compute(P)
        s = strat(P, {"A": 100}, stop_atr=0.01)
        r = sim.simulate(P, F, s, P["c"].index[60], P["c"].index[-1], "base")
        t = r["trades"][0]
        self.assertLessEqual(t["qty"] * P["o"]["A"].iloc[101], F["adv30"]["A"].iloc[100] * 0.01 * 1.0001)

    def test_max_positions(self):
        syms = {f"S{i}": trend(10 + i, 0.003) for i in range(8)}
        P = make_P({"BTC": trend(), **syms})
        s = strat(P, {k: 100 for k in syms})
        r = self.run_s(s, P=P)
        self.assertLessEqual(len(r["trades"]), 5)

    def test_open_risk_cap(self):
        syms = {f"S{i}": trend(10 + i, 0.003) for i in range(5)}
        P = make_P({"BTC": trend(), **syms})
        F = features.compute(P)
        r = sim.simulate(P, F, strat(P, {k: 100 for k in syms}), P["c"].index[60], P["c"].index[-1], "base",
                         risk={"risk_pct": 2.0})
        risk = sum(t["qty"] * 3 * F["atr"][t["symbol"]].iloc[100] for t in r["trades"])
        self.assertLessEqual(risk, 10_000 * 0.03 * 1.01)

    def test_delisting_haircut(self):
        c = trend(10, 0.003)[:200]
        P = make_P({"BTC": trend(), "A": c, "B": trend()})
        r = self.run_s(strat(P, {"A": 150}, stop_atr=20), P=P)
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "Retirada")
        self.assertLess(t["exit_px"], P["c"]["A"].iloc[199] * 0.9 + 1e-9)

    def test_weekly_entries_only_monday(self):
        c = self.P["c"]
        ent = pd.DataFrame(True, index=c.index, columns=c.columns)
        s = strategies.Strategy("W", "T", {}, entry=ent, score=pd.DataFrame(1.0, index=c.index, columns=c.columns),
                                exit_sig=pd.DataFrame(False, index=c.index, columns=c.columns), weekly=True)
        r = self.run_s(s)
        self.assertTrue(r["trades"])
        self.assertTrue(all(pd.Timestamp(t["entry_date"]).weekday() == 0 for t in r["trades"]))

    def test_end_of_period_closes(self):
        r = self.run_s(strat(self.P, {"A": 100}, stop_atr=20))
        self.assertEqual(r["trades"][-1]["exit_reason"], "Fin del periodo")

    def test_cash_never_negative_and_equity_consistent(self):
        syms = {f"S{i}": trend(10 + i, 0.002 + i * 0.0005) for i in range(6)}
        P = make_P({"BTC": trend(), **syms})
        r = self.run_s(strat(P, {k: 90 + i for i, k in enumerate(syms)}), P=P)
        pnl = sum(t["pnl_usd"] for t in r["trades"])
        self.assertAlmostEqual(r["curve"]["equity"].iloc[-1], 10_000 + pnl, places=6)

    def test_23_preregistered_configs(self):
        S = strategies.build_all(self.P, self.F, self.U)
        self.assertEqual(len(S), 23)
        self.assertEqual(sorted({s.family for s in S}), list("ABCDE"))


class TEdgeMetricsStats(unittest.TestCase):
    def test_profit_factor_from_trades(self):
        res = {"trades": [{"pnl_usd": 30, "cost_usd": 100, "exit_px": 1, "qty": 130, "R": 1, "days": 3, "bear_at_entry": False, "exit_reason": "x"},
                          {"pnl_usd": -10, "cost_usd": 100, "exit_px": 1, "qty": 90, "R": -1, "days": 2, "bear_at_entry": True, "exit_reason": "y"}],
               "curve": pd.DataFrame({"equity": [10000, 10020], "exposure": [0, 0]}, index=pd.date_range("2024-01-01", periods=2)),
               "fees": 1.0}
        m = metrics.summarize(res)
        self.assertEqual(m["profit_factor"], 3.0); self.assertEqual(m["win_rate_pct"], 50.0)
        self.assertEqual(m["expectancy_usd"], 10.0); self.assertEqual(m["net_without_top5_usd"], 0)

    def test_bootstrap_detects_strong_mean(self):
        r = np.random.default_rng(1).normal(0.003, 0.01, 800)
        self.assertLess(stats.test_mean(r, 1000)["p_value"], 0.01)

    def test_bootstrap_no_false_positive_on_zero_mean(self):
        r = np.random.default_rng(2).normal(0.0, 0.01, 800); r -= r.mean()
        self.assertGreater(stats.test_mean(r, 1000)["p_value"], 0.3)

    def test_holm(self):
        adj = stats.holm({"a": 0.01, "b": 0.04, "c": 0.03})
        self.assertEqual(adj["a"], 0.03); self.assertEqual(adj["c"], 0.06); self.assertEqual(adj["b"], 0.06)

    def test_sharpe_annualized_365(self):
        r = pd.Series([0.01, -0.005] * 50)
        self.assertAlmostEqual(metrics.sharpe(r), r.mean() / r.std() * math.sqrt(365))


class TEdgeManip(unittest.TestCase):
    def test_score_bounded_and_flags_pump(self):
        c = [10.0] * 250 + [10 * 1.3 ** i for i in range(1, 6)] + [10 * 1.3 ** 5 * 0.5] * (N - 255)
        v = pd.Series([1e6] * N); v.iloc[250:255] = 20e6
        P = make_P({"BTC": trend(), "A": c, "B": trend()})
        P["v"]["A"] = v.values
        F = features.compute(P); M = manip.score(P, F)
        self.assertTrue(((M >= 0) & (M <= 100)).all().all())
        self.assertGreaterEqual(M["A"].iloc[254:262].max(), 60)
        self.assertLess(M["B"].iloc[100:].max(), 30)


class TEdgeProtocol(unittest.TestCase):
    def test_holdout_lock_refuses_second_run(self):
        sys.path.insert(0, str(ROOT / "research" / "edge"))
        import run as R
        with tempfile.TemporaryDirectory() as d:
            R.OUT = Path(d); (R.OUT / "HOLDOUT_EXECUTED.lock").write_text("2026-11-15")
            old = sys.argv; sys.argv = ["run.py", "holdout"]
            try:
                with self.assertRaises(SystemExit):
                    R.holdout()
            finally:
                sys.argv = old

    def test_splits_do_not_overlap(self):
        sys.path.insert(0, str(ROOT / "research" / "edge"))
        import run as R
        self.assertLess(R.DEV[1], R.VAL[0]); self.assertLess(R.VAL[1], R.HOLD[0])


if __name__ == "__main__":
    unittest.main()
