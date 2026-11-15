"""Pruebas de la auditoría de D_volmom_L28: riesgo de cartera, simulador v2, holdout protegido y paper trading.
Datos sintéticos, sin red.   python3 tests/test_paper.py -v"""
import json, math, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
from radar.edge import data, features, strategies, sim, sim_v1, portfolio_risk as PR, ledger, stats
from radar.paper_trading import engine, storage as pstore, metrics as pmetrics, report, execution
import radar.paper_trading as paper_pkg
from test_edge import make_P, trend, setup, strat, N

EPS = 1e-9


def noisy(p0=100, g=0.001, sd=0.03, seed=0, n=N):
    r = np.random.default_rng(seed).normal(g, sd, n)
    return list(p0 * np.exp(np.cumsum(r)))


def panel(k=8, seed=1):
    paths = {"BTC": noisy(30000, 0.001, 0.02, seed)}
    for i in range(k):
        paths[f"A{i}"] = noisy(10 + i, 0.002, 0.04 + 0.005 * i, seed + i + 1)
    return make_P(paths)


def every_day_strat(P, syms, start=100, **kw):
    c = P["c"]
    ent = pd.DataFrame(False, index=c.index, columns=c.columns)
    ent.loc[c.index[start:], syms] = True
    sc = pd.DataFrame(np.arange(len(c.columns), 0, -1, dtype=float)[None, :].repeat(len(c), 0), index=c.index, columns=c.columns)
    return strategies.Strategy("T", "T", {}, entry=ent, score=sc, exit_sig=pd.DataFrame(False, index=c.index, columns=c.columns), **kw)


# ---------------------------------------------------------------------------------------------- covarianza
class TCovariance(unittest.TestCase):
    def test_ledoit_wolf_psd_and_shrinkage_range(self):
        X = np.random.default_rng(0).normal(0, 0.03, (90, 6))
        e = PR.estimate(X)
        self.assertTrue(e["ok"]); self.assertGreater(np.linalg.eigvalsh(e["cov"]).min(), 0)
        self.assertTrue(0 <= e["shrinkage"] <= 1)
        np.testing.assert_allclose(np.diag(e["corr"]), 1.0)
        np.testing.assert_allclose(e["vols"], X.std(0, ddof=1) * math.sqrt(365))

    def test_insufficient_common_observations(self):
        X = np.random.default_rng(0).normal(0, 0.03, (90, 3)); X[:40, 1] = np.nan
        e = PR.estimate(X)
        self.assertFalse(e["ok"]); self.assertIn("insuficientes", e["reason"])

    def test_perfectly_collinear_assets_become_positive_definite(self):
        x = np.random.default_rng(0).normal(0, 0.03, 90)
        e = PR.estimate(np.c_[x, x * 1.0000001, np.random.default_rng(1).normal(0, 0.03, 90)])
        if e["ok"]:
            self.assertGreater(np.linalg.eigvalsh(e["corr"]).min(), 0)
            self.assertLessEqual(e["cond"], PR.PARAMS["max_cond"])
        else:
            self.assertTrue("inestable" in e["reason"] or "definida" in e["reason"])

    def test_constant_series_rejected(self):
        X = np.random.default_rng(0).normal(0, 0.03, (90, 2)); X[:, 1] = 0.0
        self.assertFalse(PR.estimate(X)["ok"])

    def test_stablecoin_like_asset_rejected_individually(self):
        X = np.random.default_rng(0).normal(0, 0.03, (90, 3)); X[:, 2] = np.random.default_rng(2).normal(0, 0.0001, 90)
        cands = [{"key": "A", "ref_px": 10, "stop": 8}, {"key": "STABLE", "ref_px": 1, "stop": 0.9}]
        out = PR.plan_entries(10_000, [{"key": "H", "value": 500, "risk_usd": 20}], cands, X, False)
        self.assertIn("STABLE", out["rejected"]); self.assertIn("A", out["orders"])


# ---------------------------------------------------------------------------------------------- control de volatilidad
class TVolControl(unittest.TestCase):
    def setUp(self):
        self.X = np.random.default_rng(3).normal(0, 0.05, (90, 5))
        self.cands = [{"key": f"C{i}", "ref_px": 10.0, "stop": 9.5} for i in range(5)]   # 5 % de distancia al stop

    def test_portfolio_vol_within_target_and_limits(self):
        out = PR.plan_entries(10_000, [], self.cands, self.X, False)
        e = PR.estimate(self.X)
        w = np.array([out["orders"].get(c["key"], 0) / 10_000 for c in self.cands])
        self.assertLessEqual(PR.portfolio_vol(w, e["cov"]), PR.PARAMS["target_vol"] + 1e-6)
        for c in self.cands:
            v = out["orders"].get(c["key"], 0)
            self.assertLessEqual(v, 1500 + EPS)                                         # 15 %
            self.assertLessEqual(v / c["ref_px"] * (c["ref_px"] - c["stop"]), 50 + EPS)  # 0,5 % de riesgo
        risk = sum(v / 10 * 0.5 for v in out["orders"].values())
        self.assertLessEqual(risk, 300 + EPS)                                             # 3 % abierto

    def test_bear_market_halves_risk(self):
        a = PR.plan_entries(10_000, [], self.cands[:1], self.X[:, :1], False)["orders"]["C0"]
        b = PR.plan_entries(10_000, [], self.cands[:1], self.X[:, :1], True)["orders"]["C0"]
        self.assertAlmostEqual(b, a / 2, places=6)

    def test_realized_vol_brake_blocks_entries(self):
        eq = list(10_000 * np.exp(np.cumsum(np.random.default_rng(0).normal(0, 0.08, 40))))   # ~150 % anual
        out = PR.plan_entries(10_000, [], self.cands, self.X, False, equity_curve=eq)
        self.assertEqual(out["orders"], {}); self.assertTrue(all("freno" in v for v in out["rejected"].values()))

    def test_unreliable_risk_means_no_entry(self):
        X = self.X.copy(); X[:50] = np.nan
        out = PR.plan_entries(10_000, [], self.cands, X, False)
        self.assertEqual(out["orders"], {})

    def test_target_binds_with_high_vol_assets(self):
        X = np.random.default_rng(4).normal(0, 0.12, (90, 1))                         # ~230 % anual
        out = PR.plan_entries(10_000, [], [{"key": "X", "ref_px": 10, "stop": 9.9}], X, False)
        v = out["orders"]["X"] / 10_000
        self.assertAlmostEqual(v, 0.40 / 5 / (X.std(ddof=1) * math.sqrt(365)), places=6)


# ---------------------------------------------------------------------------------------------- simulador v2
class TSimV2(unittest.TestCase):
    def setUp(self):
        self.P = panel(); self.F, self.U = setup(self.P)

    def run_(self, s, capital=10_000.0, **kw):
        return sim.simulate(self.P, self.F, s, self.P["c"].index[0], self.P["c"].index[-1], risk={"capital": capital},
                            keep_events=True, **kw)

    def test_limits_hold_every_day(self):
        s = every_day_strat(self.P, [f"A{i}" for i in range(8)], sizing="vol")
        r = self.run_(s)
        cv = r["curve"]
        self.assertTrue((cv["positions"] <= 5).all())
        self.assertTrue((cv["exposure"] <= 1 + EPS).all())
        self.assertTrue((cv["cash"] >= -EPS).all())
        self.assertTrue(all(t["risk_pct_equity"] <= 0.5 + 1e-6 for t in r["trades"]))
        fills = [e for e in r["events"] if e["type"] == "fill"]
        self.assertTrue(fills)
        # el riesgo abierto (distancia al stop con la marca actual) se limita en cada entrada; luego puede crecer con
        # las ganancias latentes, y entonces simplemente no se abren posiciones nuevas
        self.assertTrue(all(f["open_risk_after_pct"] <= 3.0 + 1e-6 for f in fills))
        self.assertTrue(all(f["gross_after_pct"] <= 100.0 + 1e-6 for f in fills))

    def test_size_uses_real_execution_price_and_costs(self):
        s = every_day_strat(self.P, ["A0"], sizing="vol")
        r = self.run_(s)
        t = r["trades"][0]
        rate = sim.cost_rate(50e6, 1.0)
        self.assertAlmostEqual(t["entry_px"], t["entry_open"] * (1 + rate), places=9)
        self.assertAlmostEqual(t["exit_px"], t["exit_ref_px"] * (1 - rate), places=9)
        self.assertAlmostEqual(t["pnl_usd"], t["proceeds_usd"] - t["cost_usd"], places=6)
        self.assertAlmostEqual(t["cost_usd"], t["qty"] * t["entry_px"], places=6)

    def test_insufficient_capital(self):
        s = every_day_strat(self.P, [f"A{i}" for i in range(8)], sizing="vol")
        r = self.run_(s, capital=100.0)
        self.assertEqual(r["trades"], [])
        self.assertTrue(any("< 20 USD" in (e.get("reason") or "") for e in r["events"]))
        self.assertTrue((r["curve"]["cash"] >= 0).all())

    def test_simultaneous_orders_no_double_use_of_cash(self):
        s = every_day_strat(self.P, [f"A{i}" for i in range(8)], sizing="risk")
        r = self.run_(s, capital=1000.0)
        by_day = {}
        for e in r["events"]:
            if e["type"] == "fill":
                by_day.setdefault(e["date"], []).append(e["value"])
        multi = [v for v in by_day.values() if len(v) > 1]
        self.assertTrue(multi)
        self.assertTrue((r["curve"]["cash"] >= -EPS).all())
        self.assertTrue(all(sum(v) <= 1000 * 1.6 for v in multi))

    def test_no_lookahead_future_data_does_not_change_past(self):
        s = every_day_strat(self.P, [f"A{i}" for i in range(8)], sizing="vol")
        cut = 200
        a = sim.simulate(self.P, self.F, s, self.P["c"].index[0], self.P["c"].index[-1])
        P2 = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in self.P.items()}
        for k in "ohlc":
            P2[k].iloc[cut + 1:] = P2[k].iloc[cut + 1:] * 3.0                       # futuro distinto
        F2 = features.compute(P2)
        s2 = every_day_strat(P2, [f"A{i}" for i in range(8)], sizing="vol")
        b = sim.simulate(P2, F2, s2, P2["c"].index[0], P2["c"].index[-1])
        ea, eb = a["curve"]["equity"].iloc[:cut - 1], b["curve"]["equity"].iloc[:cut - 1]
        np.testing.assert_allclose(ea.values, eb.values)
        for k in ("atr", "vol28", "adv30", "sma28"):
            pd.testing.assert_frame_equal(self.F[k].iloc[:cut + 1], F2[k].iloc[:cut + 1])

    def test_reproducible(self):
        s = every_day_strat(self.P, [f"A{i}" for i in range(8)], sizing="vol")
        a = sim.simulate(self.P, self.F, s, self.P["c"].index[0], self.P["c"].index[-1])
        b = sim.simulate(self.P, self.F, s, self.P["c"].index[0], self.P["c"].index[-1])
        self.assertEqual(a["trades"], b["trades"]); pd.testing.assert_frame_equal(a["curve"], b["curve"])


class TExecutionEdgeCases(unittest.TestCase):
    def test_gap_below_stop_fills_at_open(self):
        c = trend(); c[160:] = [x * 0.5 for x in c[160:]]
        P = make_P({"BTC": trend(30000), "X": c}); F, U = setup(P)
        P["o"].loc[P["o"].index[160], "X"] = c[160]
        s = strat(P, {"X": 100}, stop_atr=3)
        r = sim.simulate(P, F, s, P["c"].index[0], P["c"].index[-1])
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "Stop")
        self.assertAlmostEqual(t["exit_ref_px"], P["o"]["X"].iloc[160], places=9)
        self.assertLess(t["exit_ref_px"], t["stop"])

    def test_intraday_stop_at_stop_price(self):
        P = make_P({"BTC": trend(30000), "X": trend()}); F, U = setup(P)
        d = P["l"].index[130]; P["l"].loc[d, "X"] = P["l"].loc[d, "X"] * 0.5
        s = strat(P, {"X": 100}, stop_atr=3)
        t = sim.simulate(P, F, s, P["c"].index[0], P["c"].index[-1])["trades"][0]
        self.assertEqual(t["exit_reason"], "Stop"); self.assertAlmostEqual(t["exit_ref_px"], t["stop"], places=9)

    def test_gap_up_cancels_order(self):
        P = make_P({"BTC": trend(30000), "X": trend()}); F, U = setup(P)
        d = P["o"].index[101]; P["o"].loc[d, "X"] = P["c"]["X"].iloc[100] * 1.5
        r = sim.simulate(P, F, strat(P, {"X": 100}), P["c"].index[0], P["c"].index[-1], keep_events=True)
        self.assertEqual(r["trades"], [])
        self.assertTrue(any(e["type"] == "order_cancelled" and "hueco" in e["reason"] for e in r["events"]))

    def test_delisting_detected_without_future_knowledge(self):
        x = trend(); x = x[:150] + [np.nan] * (N - 150)
        P = make_P({"BTC": trend(30000), "X": x}); F, U = setup(P)
        r = sim.simulate(P, F, strat(P, {"X": 100}), P["c"].index[0], P["c"].index[-1])
        t = r["trades"][0]
        self.assertEqual(t["exit_reason"], "Retirada")
        self.assertEqual(t["exit_date"], P["c"].index[153].date().isoformat())          # 3 días sin vela
        self.assertAlmostEqual(t["exit_ref_px"], x[149] * 0.9, places=9)

    def test_missing_candle_valued_at_last_close_not_entry(self):
        x = trend(); x[140] = np.nan
        P = make_P({"BTC": trend(30000), "X": x}); F, U = setup(P)
        for k in "ohl":
            P[k].loc[P[k].index[140], "X"] = np.nan
        r = sim.simulate(P, F, strat(P, {"X": 100}), P["c"].index[0], P["c"].index[-1])
        cv = r["curve"]; d139, d140 = P["c"].index[139], P["c"].index[140]
        self.assertAlmostEqual(cv.loc[d140, "equity"], cv.loc[d139, "equity"], places=6)
        self.assertEqual(cv.loc[d140, "stale_marks"], 1)

    def test_v1_frozen_still_runs(self):
        P = make_P({"BTC": trend(30000), "X": trend()}); F, U = setup(P)
        r = sim_v1.simulate(P, F, strat(P, {"X": 100}), P["c"].index[0], P["c"].index[-1])
        self.assertEqual(len(r["trades"]), 1)


# ---------------------------------------------------------------------------------------------- holdout y registro
class THoldoutProtection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = mock.patch.object(ledger, "LEDGER", Path(self.tmp.name) / "ledger.jsonl"); self.p.start()

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup()

    def test_chain_detects_edits(self):
        ledger.append("final_holdout", x=1); ledger.append("reproduction", x=2); ledger.append("exploratory", x=3)
        self.assertTrue(ledger.verify())
        lines = ledger.LEDGER.read_text().splitlines()
        lines[0] = lines[0].replace('"x": 1', '"x": 9')
        ledger.LEDGER.write_text("\n".join(lines) + "\n")
        self.assertFalse(ledger.verify())

    def test_deleting_a_line_is_detected(self):
        for i in range(3):
            ledger.append("exploratory", i=i)
        lines = ledger.LEDGER.read_text().splitlines()
        ledger.LEDGER.write_text("\n".join([lines[0], lines[2]]) + "\n")
        self.assertFalse(ledger.verify())

    def test_holdout_refuses_and_logs_attempt(self):
        sys.path.insert(0, str(ROOT / "research" / "edge"))
        import run
        ledger.append("final_holdout", period=["2024-07-01", "2026-11-14"])
        with mock.patch.object(run, "load", side_effect=AssertionError("no debería cargar datos")):
            with self.assertRaises(SystemExit):
                run.holdout()
        kinds = [e["kind"] for e in ledger.entries()]
        self.assertEqual(kinds, ["final_holdout", "holdout_attempt_refused"])
        self.assertTrue(ledger.verify())

    def test_no_force_option_in_runner(self):
        self.assertNotIn("force", (ROOT / "research" / "edge" / "run.py").read_text())

    def test_entries_have_ids_hashes_and_time(self):
        e = ledger.append("exploratory", params={"a": 1})
        for k in ("run_id", "at", "code_hash", "data_hash", "git_commit", "prev_hash"):
            self.assertIn(k, e)

    def test_repo_ledger_has_single_final_holdout(self):
        real = ROOT / "research" / "edge" / "ledger" / "ledger.jsonl"
        es = [json.loads(l) for l in real.read_text().splitlines() if l.strip()]
        self.assertEqual(sum(e["kind"] == "final_holdout" for e in es), 1)


# ---------------------------------------------------------------------------------------------- estadística
class TStats(unittest.TestCase):
    def test_circular_block_shapes_and_contiguity(self):
        r = np.arange(100.0)
        B = stats.circular_block_bootstrap(r, n_boot=10, block=10)
        self.assertEqual(B.shape, (10, 100))
        d = np.diff(B[0][:10]) % 100
        self.assertTrue(np.all(d == 1))

    def test_bootstrap_detects_strong_and_null_signal(self):
        rng = np.random.default_rng(0)
        self.assertLess(stats.bootstrap_test(rng.normal(0.005, 0.02, 600), "circular", 20)["p_value"], 0.01)
        self.assertGreater(stats.bootstrap_test(rng.normal(-0.001, 0.02, 600), "stationary", 20)["p_value"], 0.5)

    def test_corrections(self):
        p = {"a": 0.01, "b": 0.02, "c": 0.5}
        self.assertEqual(stats.bonferroni(p), {"a": 0.03, "b": 0.06, "c": 1.0})
        h = stats.holm(p); self.assertEqual(h["a"], 0.03); self.assertEqual(h["b"], 0.04)

    def test_acceptance_rejects_negative_holdout(self):
        a = pmetrics.acceptance({"net_return_pct": -22.93, "sharpe": -0.935, "profit_factor": 0.68, "max_drawdown_pct": -34.2,
                                 "expectancy_usd": -13.9, "trades": 165})
        self.assertIn("NO CUMPLE", a["verdict"])


# ---------------------------------------------------------------------------------------------- paper trading
class TPaper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.P = panel(10, seed=5)
        self.start = self.P["c"].index[120].date().isoformat()

    def tearDown(self):
        self.tmp.cleanup()

    def store(self, name="t"):
        return pstore.FileStore(Path(self.tmp.name) / name)

    def patch_strategy(self):
        """D_volmom_L28 real necesita 150 monedas: en datos sintéticos se usa el mismo constructor con universo pequeño."""
        orig = engine.UNIVERSE
        return mock.patch.object(engine, "UNIVERSE", {"size": 150, "min_adv": 1e6, "min_bars": 30})

    def test_persistence_and_incremental_equals_one_shot(self):
        with self.patch_strategy():
            a = self.store("a"); engine.init("a", a, start_date=self.start, mode="test")
            engine.process(a, self.P)
            b = self.store("b"); engine.init("b", b, start_date=self.start, mode="test")
            mid = self.P["c"].index[200].date().isoformat()
            engine.process(b, self.P, until=mid)
            b2 = pstore.FileStore(Path(self.tmp.name) / "b")                         # reabrir desde disco
            engine.process(b2, self.P)
        ea = [r["equity"] for r in a.read_all("equity")]; eb = [r["equity"] for r in b2.read_all("equity")]
        self.assertEqual(len(ea), len(eb)); np.testing.assert_allclose(ea, eb)
        self.assertEqual([t["pnl_usd"] for t in a.read_all("trades")], [t["pnl_usd"] for t in b2.read_all("trades")])
        for k in pstore.KINDS:
            self.assertTrue(pstore.verify_chain(a.read_all(k)))
        self.assertTrue(a.read_all("trades"), "la estrategia debería operar en el panel sintético")
        types = {e["type"] for e in a.read_all("events")}
        self.assertTrue({"signal", "order", "fill", "exit"} <= types)

    def test_matches_backtest_engine(self):
        with self.patch_strategy():
            st = self.store(); engine.init("t", st, start_date=self.start, mode="test")
            engine.process(st, self.P)
            F, U, s = engine.build(self.P)
        r = sim.simulate(self.P, F, s, self.start, self.P["c"].index[-1])
        np.testing.assert_allclose([x["equity"] for x in st.read_all("equity")][:-1], r["curve"]["equity"].values[:-1])

    def test_tampering_detected(self):
        st = self.store(); st.append("trades", [{"pnl_usd": -5}, {"pnl_usd": 3}])
        p = Path(self.tmp.name) / "t" / "trades.jsonl"
        p.write_text(p.read_text().replace('"pnl_usd": -5', '"pnl_usd": 5'))
        self.assertFalse(pstore.verify_chain(st.read_all("trades")))

    def test_spec_frozen_and_code_change_refused(self):
        st = self.store(); spec = engine.init("t", st, start_date=self.start, mode="test")
        self.assertEqual(spec["strategy"], "D_volmom_L28"); self.assertFalse(spec["real_orders"])
        with self.assertRaises(SystemExit):
            engine.init("t", st, start_date=self.start)
        with mock.patch.object(engine, "code_hash", return_value="otro"):
            with self.assertRaises(SystemExit):
                engine.process(st, self.P)

    def test_incomplete_day_not_processed(self):
        P = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in self.P.items()}
        d = P["c"].index[150]
        for k in "ohlc":
            P[k].loc[d, "BTC"] = np.nan
        with self.patch_strategy():
            st = self.store(); engine.init("t", st, start_date=self.start, mode="test")
            engine.process(st, P)
        self.assertEqual(st.read_json("state.json")["last_date"], P["c"].index[149].date().isoformat())
        self.assertEqual(st.read_all("events")[-1]["type"], "day_skipped")

    def test_report_and_metrics(self):
        with self.patch_strategy():
            st = self.store(); engine.init("t", st, start_date=self.start, mode="test")
            engine.process(st, self.P)
        rep = report.build("t", st)
        m = rep["metrics"]
        for k in ("net_return_pct", "sharpe", "sortino", "profit_factor", "expectancy_usd", "max_drawdown_pct", "win_rate_pct",
                  "avg_win_usd", "avg_loss_usd", "trades", "avg_exposure_pct", "portfolio_vol_ann_pct", "costs_usd",
                  "monthly_pct", "by_regime_days", "vs", "after_costs", "acceptance"):
            self.assertIn(k, m)
        self.assertIn("EN CURSO", m["acceptance"]["verdict"])                     # < 183 días
        self.assertIn("Efectivo", m["vs"]); self.assertIn("BTC comprar y mantener", m["vs"])
        self.assertTrue(all(rep["integrity"].values()))
        self.assertIn("sin órdenes reales", report.markdown(rep))

    def test_no_real_orders(self):
        self.assertFalse(paper_pkg.REAL_ORDERS_ENABLED)
        with self.assertRaises(RuntimeError):
            execution.place_real_order("BTCUSDT", "BUY", 1)
        src = "".join(p.read_text() for p in (ROOT / "radar" / "paper_trading").glob("*.py"))
        for bad in ("/api/v3/order", "X-MBX-APIKEY", "signature=", "api_secret"):
            self.assertNotIn(bad, src)


if __name__ == "__main__":
    unittest.main()
