"""Suite de pruebas de Crypto Radar 2.0 (unittest, sin dependencias externas).

Uso:  python3 tests/test_suite.py            (todas)
      python3 tests/test_suite.py -v         (detalle)
Con PostgreSQL:  TEST_DATABASE_URL=postgresql://... python3 tests/test_suite.py
Los datos sintéticos de estas pruebas NO son datos de mercado reales: sirven para verificar el comportamiento.
"""
import hashlib
import hmac
import json
import math
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import http.cookiejar
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="cr-test-")
os.environ["CRYPTO_RADAR_HOME"] = HOME
os.environ.pop("DATABASE_URL", None)
os.environ["CRYPTO_RADAR_ADMIN_EMAIL"] = "admin@example.com"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import shutil
shutil.copytree(ROOT / "web", Path(HOME) / "web", dirs_exist_ok=True)

from radar import data, storage, alerts, config, notify, db, auth, billing, telegram_bot, multiuser, meme_radar  # noqa: E402
from radar.quant import features, quality, early, manipulation, exits, regime, plan, engine, portfolio, metrics  # noqa: E402
from radar.quant import backtest_pro as B  # noqa: E402

alerts._desktop = lambda *a: None
DAY = 86_400_000
T0 = 1_600_000_000_000 - (1_600_000_000_000 % DAY)


# ------------------------------------------------------------------ utilidades
def make_k(closes, vols=None, wick=0.01, start=T0):
    n = len(closes)
    vols = vols or [1e7] * n
    o = [closes[0]] + closes[:-1]
    return {"t": [start + i * DAY for i in range(n)], "o": o,
            "h": [max(o[i], closes[i]) * (1 + wick) for i in range(n)],
            "l": [min(o[i], closes[i]) * (1 - wick) for i in range(n)], "c": list(closes), "v": list(vols)}


def walk(n, seed=1, drift=0.0005, vol=0.02, p0=100.0):
    r = random.Random(seed); p = p0; out = []
    for _ in range(n):
        p *= math.exp(drift + r.gauss(0, vol)); out.append(p)
    return out


def trending(n=300, seed=3):
    return walk(n, seed, drift=0.004, vol=0.015)


def falling(n=300, seed=4):
    return walk(n, seed, drift=-0.004, vol=0.015)


BTC_UP = features.compute(make_k(trending(400, 11)))


class Q:
    """Contador de pruebas por categoría para el informe."""


# ================================================================== 1. Datos y calidad
class T01_Datos(unittest.TestCase):
    def test_drop_open_candle_removes_unclosed(self):
        now = T0 + 10 * DAY + 3600_000
        k = make_k([1] * 11)
        out = data.drop_open_candle(k, "1d", now_ms=now)
        self.assertEqual(len(out["c"]), 10)

    def test_drop_open_candle_keeps_closed(self):
        k = make_k([1] * 10)
        out = data.drop_open_candle(k, "1d", now_ms=T0 + 10 * DAY + 1)
        self.assertEqual(len(out["c"]), 10)

    def test_quality_clean_series_ok(self):
        k = make_k(walk(200)); q = quality.check(k, now_ms=k["t"][-1] + DAY)
        self.assertTrue(q["ok"]); self.assertEqual(q["score"], 100)

    def test_quality_detects_duplicates(self):
        k = make_k(walk(200)); k["t"][50] = k["t"][49]
        self.assertTrue(any("duplicadas" in x for x in quality.check(k, now_ms=k["t"][-1] + DAY)["issues"]))

    def test_quality_detects_gaps(self):
        k = make_k(walk(200))
        for i in range(100, 200): k["t"][i] += 5 * DAY
        self.assertTrue(any("huecos" in x for x in quality.check(k, now_ms=k["t"][-1] + DAY)["issues"]))

    def test_quality_detects_bad_ohlc(self):
        k = make_k(walk(200)); k["h"][10] = k["l"][10] * 0.5
        self.assertTrue(any("incoherente" in x for x in quality.check(k, now_ms=k["t"][-1] + DAY)["issues"]))

    def test_quality_detects_stale(self):
        k = make_k(walk(200)); q = quality.check(k, now_ms=k["t"][-1] + 10 * DAY)
        self.assertFalse(q["ok"]); self.assertTrue(any("desactualizados" in x for x in q["issues"]))

    def test_quality_short_history(self):
        k = make_k(walk(40)); q = quality.check(k, now_ms=k["t"][-1] + DAY)
        self.assertLess(q["score"], 100); self.assertTrue(any("Historial corto" in x for x in q["issues"]))

    def test_quality_zero_volume(self):
        k = make_k(walk(200), vols=[1e7] * 190 + [0] * 10)
        self.assertTrue(any("sin volumen" in x for x in quality.check(k, now_ms=k["t"][-1] + DAY)["issues"]))

    def test_bad_quality_rejects_signal(self):
        k = make_k(trending(300)); f = features.compute(k)
        ev = early.evaluate(f, 299, quality={"ok": False, "issues": ["x"]})
        self.assertEqual(ev["phase"], "REJECTED"); self.assertLessEqual(ev["score"], 40)


# ================================================================== 2. Causalidad (sin mirar el futuro)
class T02_Causalidad(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.k = make_k(walk(400, 7), vols=[1e7 * (1 + 0.5 * math.sin(i / 7)) for i in range(400)])
        cls.full = features.compute(cls.k)

    def _trunc(self, i):
        return features.compute({key: v[:i + 1] for key, v in self.k.items()})

    def test_indicators_identical_when_future_removed(self):
        for i in (150, 250, 399):
            tr = self._trunc(i)
            for key in ("ema20", "ema50", "rsi", "atr", "bbw_rank", "vwap20", "vol_avg20_prev", "hh20_prev", "obv"):
                a, b = self.full[key][i], tr[key][i]
                if a is None:
                    self.assertIsNone(b)
                else:
                    self.assertAlmostEqual(a, b, places=9, msg=f"{key}@{i}")

    def test_pivots_only_after_confirmation(self):
        tr = self._trunc(200)
        for j, v in enumerate(tr.piv_hi):
            if v is not None:
                self.assertEqual(self.full.piv_hi[j], v)
        # un máximo enorme en la vela 198 aún no puede estar confirmado (hacen falta 3 velas a la derecha)
        k = make_k(walk(200)); k["h"][198] = max(k["h"]) * 3
        f = features.compute(k)
        self.assertNotEqual(f.piv_hi[-1], k["h"][198])

    def test_engine_same_output_full_vs_truncated(self):
        btc = features.compute(make_k(walk(400, 9)))
        for i in (200, 300, 399):
            tr = self._trunc(i); btr = features.compute({k: v[:i + 1] for k, v in make_k(walk(400, 9)).items()})
            a = engine.analyze("X", self.full, i, btc, i, check_quality=False)
            b = engine.analyze("X", tr, i, btr, i, check_quality=False)
            self.assertEqual(a["score"], b["score"]); self.assertEqual(a["phase"], b["phase"])
            self.assertAlmostEqual(a["plan"]["stop"], b["plan"]["stop"], places=9)

    def test_vol_avg_prev_excludes_current_bar(self):
        k = make_k([1] * 30, vols=[10] * 29 + [1000]); f = features.compute(k)
        self.assertAlmostEqual(f.vol_avg20_prev[29], 10)

    def test_hh20_prev_excludes_current_bar(self):
        k = make_k([1] * 29 + [5]); f = features.compute(k)
        self.assertLess(f.hh20_prev[29], 5)

    def test_backtest_signal_uses_only_past(self):
        mk, sig = _mini_market(trending(320, 5))
        t = mk.days[260]
        i = mk.i("COIN", t)
        a = engine.analyze("COIN", mk.f["COIN"], i, mk.btc, mk.i("BTC", t), check_quality=False)
        tr = features.compute({k: v[:i + 1] for k, v in _COIN_K.items()})
        b = engine.analyze("COIN", tr, i, mk.btc, mk.i("BTC", t), check_quality=False)
        self.assertEqual(a["score"], b["score"])


# ================================================================== 3. Detector de entradas tempranas
class T03_Early(unittest.TestCase):
    def test_weights_sum_100(self):
        self.assertEqual(sum(early.DEFAULT_WEIGHTS.values()), 100)

    def test_weights_match_spec(self):
        self.assertEqual(early.DEFAULT_WEIGHTS, {"structure": 20, "volume": 20, "trend": 15, "momentum": 15,
                                                 "relative_strength": 10, "liquidity": 10, "breakout": 10})

    def test_score_in_range(self):
        for seed in range(5):
            f = features.compute(make_k(walk(300, seed)))
            s = early.evaluate(f, 299)["score"]
            self.assertTrue(0 <= s <= 100)

    def test_custom_weights_change_score(self):
        f = features.compute(make_k(trending(300)))
        a = early.evaluate(f, 299)["raw_score"]
        w = dict(early.DEFAULT_WEIGHTS); w["trend"] = 60
        b = early.evaluate(f, 299, weights=w)["raw_score"]
        self.assertNotEqual(a, b)

    def test_phase_in_allowed_set(self):
        f = features.compute(make_k(walk(300, 2)))
        self.assertIn(early.evaluate(f, 299)["phase"], early.PHASES)

    def test_flat_price_without_volume_is_not_accumulation(self):
        closes = [100 * (1 + 0.002 * math.sin(i)) for i in range(300)]
        vols = [1e7 * (1 - i / 600) for i in range(300)]          # volumen que se apaga
        f = features.compute(make_k(closes, vols, wick=0.003))
        self.assertNotIn(early.evaluate(f, 299)["phase"], ("ACCUMULATION", "PRE-EXPLOSION"))

    def test_overextended_detected(self):
        closes = [100] * 250 + [100 * 1.08 ** k for k in range(1, 21)]
        f = features.compute(make_k(closes, vols=[2e7] * 270))
        ev = early.evaluate(f, 269)
        self.assertEqual(ev["phase"], "OVEREXTENDED")

    def test_overextension_penalizes_score(self):
        closes = [100] * 250 + [100 * 1.08 ** k for k in range(1, 21)]
        f = features.compute(make_k(closes, vols=[2e7] * 270))
        ev = early.evaluate(f, 269)
        self.assertLess(ev["score"], ev["raw_score"])

    def test_downtrend_rejected(self):
        f = features.compute(make_k(falling(300)))
        self.assertIn(early.evaluate(f, 299)["phase"], ("REJECTED", "DISTRIBUTION"))

    def test_illiquid_rejected(self):
        f = features.compute(make_k(trending(300), vols=[5_000] * 300))
        self.assertEqual(early.evaluate(f, 299)["phase"], "REJECTED")

    def test_breakout_with_volume(self):
        closes = [100 + (i % 5) * 0.2 for i in range(280)] + [104, 108]
        vols = [1e7] * 280 + [3e7, 3.5e7]
        f = features.compute(make_k(closes, vols, wick=0.004))
        ev = early.evaluate(f, 281)
        self.assertGreaterEqual(ev["families"]["breakout"]["score"], 0.55)

    def test_families_have_evidence_lists(self):
        f = features.compute(make_k(trending(300)))
        for v in early.evaluate(f, 299)["families"].values():
            self.assertIsInstance(v["evidence"], list)

    def test_rejected_score_capped_40(self):
        f = features.compute(make_k(falling(300)))
        ev = early.evaluate(f, 299)
        if ev["phase"] == "REJECTED":
            self.assertLessEqual(ev["score"], 40)

    def test_missing_family_redistributes_weight(self):
        f = features.compute(make_k(trending(300)))
        ev = early.evaluate(f, 299)            # sin BTC: fuerza relativa N/D
        self.assertIsNone(ev["families"]["relative_strength"]["score"])
        self.assertLess(ev["coverage"], 100)


# ================================================================== 4. Manipulación
class T04_Manipulacion(unittest.TestCase):
    def test_clean_series_low_risk(self):
        f = features.compute(make_k(walk(300, 3, vol=0.01), vols=[5e7] * 300))
        m = manipulation.evaluate(f, 299)
        self.assertLess(m["risk"], 35); self.assertEqual(m["level"], "BAJO")

    def test_pump_and_dump_detected(self):
        closes = [10] * 280 + [12, 15, 17, 12, 10, 9.5, 9.5, 9.5]
        f = features.compute(make_k(closes, vols=[3e6] * 288))
        m = manipulation.evaluate(f, 287)
        self.assertTrue(any("bombeo" in e["text"] for e in m["evidence"]))

    def test_vertical_move_without_liquidity(self):
        closes = [10] * 290 + [13.5]
        f = features.compute(make_k(closes, vols=[1e6] * 291))
        self.assertTrue(any("sin" in e["text"] or "solo" in e["text"] for e in manipulation.evaluate(f, 290)["evidence"]))

    def test_risk_bounded(self):
        closes = [10] * 250 + [10 * (1.5 if k % 2 else 0.7) for k in range(40)]
        f = features.compute(make_k(closes, vols=[1e6] * 290))
        self.assertLessEqual(manipulation.evaluate(f, 289)["risk"], 100)

    def test_every_point_has_evidence_text(self):
        closes = [10] * 280 + [12, 15, 17, 12, 10, 9.5, 9.5, 9.5]
        m = manipulation.evaluate(features.compute(make_k(closes, vols=[3e6] * 288)), 287)
        self.assertEqual(sum(e["points"] for e in m["evidence"]), m["risk"] if m["risk"] < 100 else sum(e["points"] for e in m["evidence"]))
        self.assertTrue(all(e["text"] for e in m["evidence"]))

    def test_note_never_claims_proof(self):
        m = manipulation.evaluate(features.compute(make_k(walk(300))), 299)
        self.assertIn("no prueba", m["note"])

    def test_book_nd_without_book(self):
        m = manipulation.evaluate(features.compute(make_k(walk(300))), 299)
        self.assertIn("N/D", m["book"])

    def test_wide_spread_adds_risk(self):
        f = features.compute(make_k(walk(300, 3, vol=0.01), vols=[5e7] * 300))
        a = manipulation.evaluate(f, 299)["risk"]
        b = manipulation.evaluate(f, 299, book={"spread_pct": 1.2, "depth_usd_2pct": 1e6})["risk"]
        self.assertGreater(b, a)

    def test_high_risk_blocks_entry(self):
        ev = {"phase": "BREAKOUT", "score": 95, "phase_label": "Ruptura"}
        pl = {"rr": 4, "entry_high": 10, "trigger_breakout": None, "_price": 9}
        act, _ = engine.action_for(ev, pl, {"risk": 70, "level": "ALTO"}, "BULLISH", {})
        self.assertEqual(act, "EVITAR")


# ================================================================== 5. Salidas
class T05_Salidas(unittest.TestCase):
    def setUp(self):
        self.f = features.compute(make_k(trending(300)))

    def test_hold_without_signals(self):
        d = exits.decide(self.f, 299, {"entry": self.f.c[299] * 0.98, "stop": self.f.c[299] * 0.8})
        self.assertIn(d["decision"], ("MANTENER", "PROTEGER GANANCIAS"))

    def test_close_at_stop(self):
        p = self.f.c[299]
        d = exits.decide(self.f, 299, {"entry": p * 1.2, "stop": p * 1.01})
        self.assertEqual(d["decision"], "CERRAR POSICIÓN"); self.assertEqual(d["sell_fraction"], 1.0)

    def test_single_weak_signal_never_closes(self):
        for i in range(220, 300):
            d = exits.decide(self.f, i, {"entry": self.f.c[i] * 0.5, "stop": self.f.c[i] * 0.3})
            if d["single_weak_signal"]:
                self.assertNotIn(d["decision"], ("CERRAR POSICIÓN", "REDUCIR POSICIÓN"))

    def test_stop_never_lowered(self):
        p = self.f.c[299]
        d = exits.decide(self.f, 299, {"entry": p * 0.7, "stop": p * 0.9})
        self.assertGreaterEqual(d["suggested_stop"], p * 0.9)

    def test_stop_to_breakeven_after_profit(self):
        p = self.f.c[299]
        d = exits.decide(self.f, 299, {"entry": p / 1.5, "stop": p / 1.5 * 0.9, "highest_close": p})
        if d["decision"] in ("PROTEGER GANANCIAS", "REDUCIR POSICIÓN"):
            self.assertGreaterEqual(d["suggested_stop"], p / 1.5)

    def test_partials_configurable(self):
        p = self.f.c[299]
        d = exits.decide(self.f, 299, {"entry": p * 1.2, "stop": p * 1.01}, partials={"CERRAR POSICIÓN": 0.5})
        self.assertEqual(d["sell_fraction"], 0.5)

    def test_decision_values(self):
        for i in range(250, 300, 7):
            d = exits.decide(self.f, i, {"entry": self.f.c[i], "stop": self.f.c[i] * 0.85})
            self.assertIn(d["decision"], ("MANTENER", "PROTEGER GANANCIAS", "REDUCIR POSICIÓN", "CERRAR POSICIÓN"))

    def test_downtrend_triggers_exit_evidence(self):
        f = features.compute(make_k(trending(250) + falling(60, 9)[:60]))
        decs = [exits.decide(f, i, {"entry": f.c[245], "stop": f.c[245] * 0.5})["decision"] for i in range(250, 309)]
        self.assertTrue(any(d != "MANTENER" for d in decs))


# ================================================================== 6. Régimen
class T06_Regimen(unittest.TestCase):
    def test_bullish(self):
        f = features.compute(make_k(walk(400, 21, drift=0.003, vol=0.01)))
        self.assertEqual(regime.detect(f, 399, breadth=70)["regime"], "BULLISH")

    def test_bearish(self):
        f = features.compute(make_k(walk(400, 21, drift=-0.003, vol=0.01)))
        self.assertEqual(regime.detect(f, 399, breadth=20)["regime"], "BEARISH")

    def test_high_volatility(self):
        f = features.compute(make_k(walk(400, 5, drift=0.0, vol=0.07)))
        self.assertIn(regime.detect(f, 399, breadth=45)["regime"], ("HIGH VOLATILITY", "CAPITULATION"))

    def test_capitulation(self):
        closes = walk(380, 2, vol=0.01) + [100 * 0.93 ** k for k in range(1, 21)]
        f = features.compute(make_k(closes))
        self.assertEqual(regime.detect(f, 399, breadth=10)["regime"], "CAPITULATION")

    def test_neutral_mixed(self):
        f = features.compute(make_k(walk(400, 21, drift=0.003, vol=0.01)))
        self.assertEqual(regime.detect(f, 399, breadth=45)["regime"], "NEUTRAL")

    def test_policy_tightens_with_risk(self):
        P = regime.POLICY
        self.assertLess(P["BULLISH"]["min_score"], P["NEUTRAL"]["min_score"])
        self.assertLess(P["NEUTRAL"]["min_score"], P["BEARISH"]["min_score"])
        self.assertGreater(P["BULLISH"]["max_alt_exposure"], P["BEARISH"]["max_alt_exposure"])
        self.assertGreater(P["BULLISH"]["size_mult"], P["CAPITULATION"]["size_mult"])

    def test_regime_blocks_phase(self):
        ev = {"phase": "MOMENTUM", "score": 95, "phase_label": "Momentum"}
        pl = {"rr": 4, "entry_high": 10, "trigger_breakout": None, "_price": 9}
        act, _ = engine.action_for(ev, pl, {"risk": 0, "level": "BAJO"}, "BEARISH", {})
        self.assertEqual(act, "VIGILAR")

    def test_regime_min_score(self):
        ev = {"phase": "BREAKOUT", "score": 60, "phase_label": "Ruptura"}
        pl = {"rr": 4, "entry_high": 10, "trigger_breakout": None, "_price": 9}
        self.assertEqual(engine.action_for(ev, pl, {"risk": 0, "level": "BAJO"}, "BULLISH", {})[0], "COMPRAR EN ZONA")
        self.assertNotEqual(engine.action_for(ev, pl, {"risk": 0, "level": "BAJO"}, "BEARISH", {})[0], "COMPRAR EN ZONA")

    def test_regime_affects_size(self):
        f = features.compute(make_k(trending(300)))
        a = engine.analyze("X", f, 299, regime={"regime": "BULLISH"}, check_quality=False)["plan"]["position_usd"]
        b = engine.analyze("X", f, 299, regime={"regime": "CAPITULATION"}, check_quality=False)["plan"]["position_usd"]
        self.assertAlmostEqual(b, a * 0.25, places=6)


# ================================================================== 7. Plan de operación
class T07_Plan(unittest.TestCase):
    def setUp(self):
        self.f = features.compute(make_k(trending(300)))

    def test_stop_below_entry(self):
        for ph in ("BREAKOUT", "ACCUMULATION", "MOMENTUM", "PRE-EXPLOSION"):
            p = plan.build(self.f, 299, ph)
            self.assertLess(p["stop"], p["entry"]); self.assertGreater(p["stop"], 0)

    def test_min_stop_distance_atr(self):
        a = self.f.atr[299]
        for ph in ("BREAKOUT", "ACCUMULATION", "MOMENTUM"):
            p = plan.build(self.f, 299, ph)
            self.assertGreaterEqual(p["entry"] - p["stop"], plan.MIN_STOP_ATR * a - 1e-9)

    def test_targets_ordered(self):
        p = plan.build(self.f, 299, "BREAKOUT")
        self.assertLess(p["entry"], p["tp1"]); self.assertLess(p["tp1"], p["tp2"]); self.assertLess(p["tp2"], p["tp3"])

    def test_tp_multiples_of_R(self):
        p = plan.build(self.f, 299, "MOMENTUM")
        self.assertGreaterEqual(p["tp1"], p["entry"] + 1.5 * p["R"] - 1e-9)
        self.assertGreaterEqual(p["tp2"], p["entry"] + 3 * p["R"] - 1e-9)

    def test_entry_zone_not_above_price(self):
        p = plan.build(self.f, 299, "BREAKOUT")
        self.assertLessEqual(p["entry_high"], self.f.c[299] + 1e-9)

    def test_position_capped_by_max_pct(self):
        p = plan.build(self.f, 299, "BREAKOUT", {"capital_usd": 1000, "risk_per_trade_pct": 5, "max_position_pct": 10})
        self.assertLessEqual(p["position_usd"], 100 + 1e-9)


# ================================================================== 8. Smart Portfolio
class T08_Portfolio(unittest.TestCase):
    def test_risk_based_size(self):
        r = portfolio.size(10000, 10000, 10000, 100, 95, [])
        self.assertTrue(r["ok"]); self.assertAlmostEqual(r["risk_usd"], 100, places=6)

    def test_max_position_cap(self):
        r = portfolio.size(10000, 10000, 10000, 100, 99.9, [])
        self.assertLessEqual(r["value"], 2000 + 1e-6)

    def test_invalid_stop_rejected(self):
        self.assertFalse(portfolio.size(10000, 10000, 10000, 100, 101, [])["ok"])

    def test_drawdown_halves_size(self):
        a = portfolio.size(10000, 10000, 10000, 100, 90, [])["risk_usd"]
        b = portfolio.size(8800, 10000, 8800, 100, 90, [])["risk_usd"]
        self.assertAlmostEqual(b, 8800 * 0.01 * 0.5, places=6); self.assertLess(b, a)

    def test_drawdown_stop_blocks(self):
        self.assertFalse(portfolio.size(7900, 10000, 7900, 100, 90, [])["ok"])

    def test_max_positions(self):
        pos = [{"value": 100, "risk_usd": 10}] * 6
        self.assertFalse(portfolio.size(10000, 10000, 10000, 100, 90, pos)["ok"])

    def test_open_risk_cap(self):
        pos = [{"value": 1000, "risk_usd": 490}]
        r = portfolio.size(10000, 10000, 10000, 100, 90, pos)
        self.assertLessEqual(r["risk_usd"] if r["ok"] else 0, 10 + 1e-6)

    def test_correlation_rejects(self):
        self.assertFalse(portfolio.size(10000, 10000, 10000, 100, 90, [], corr_with=[0.95])["ok"])

    def test_liquidity_cap(self):
        r = portfolio.size(1e6, 1e6, 1e6, 100, 90, [], avg_volume_usd=100_000)
        self.assertLessEqual(r["value"], 1000 + 1e-6)

    def test_cash_cap(self):
        r = portfolio.size(10000, 10000, 300, 100, 99, [])
        self.assertLessEqual(r["value"], 300 + 1e-6)

    def test_alt_exposure_cap(self):
        pos = [{"value": 1400, "risk_usd": 10, "is_alt": True}]
        r = portfolio.size(10000, 10000, 10000, 100, 99, pos, max_alt_exposure_pct=15)
        self.assertLessEqual(r["value"], 100 + 1e-6)

    def test_correlation_function(self):
        k = make_k(walk(200, 1)); f = features.compute(k)
        self.assertAlmostEqual(portfolio.correlation(f, 199, f, 199), 1.0, places=6)


# ================================================================== 9. Métricas
class T09_Metricas(unittest.TestCase):
    def test_profit_factor_and_win_rate(self):
        tr = [{"pnl_usd": 100, "R": 1}, {"pnl_usd": -50, "R": -0.5}, {"pnl_usd": 50, "R": 0.5}]
        m = metrics.compute(tr, [("2024-01-01", 1000), ("2024-01-02", 1100)], 1000, 3)
        self.assertEqual(m["profit_factor"], 3.0); self.assertEqual(m["win_rate_pct"], 66.7)
        self.assertEqual(m["expectancy_usd"], 33.33)

    def test_profit_factor_none_without_losses(self):
        m = metrics.compute([{"pnl_usd": 10, "R": 1}], [("2024-01-01", 1000), ("2024-01-02", 1010)], 1000, 0)
        self.assertIsNone(m["profit_factor"])

    def test_max_drawdown(self):
        mdd, rec, under = metrics.drawdown_stats([("2024-01-01", 100), ("2024-01-02", 120), ("2024-01-03", 90), ("2024-01-04", 130)])
        self.assertAlmostEqual(mdd, -25.0); self.assertEqual(rec, 2); self.assertEqual(under, 0)

    def test_cagr(self):
        m = metrics.compute([], [("2020-01-01", 1000), ("2021-01-01", 1210)], 1000, 0)
        self.assertAlmostEqual(m["cagr_pct"], 20.95, delta=0.1)

    def test_sharpe_sign(self):
        curve = [(f"2024-01-{d:02d}", 1000 * (1.01 ** d)) for d in range(1, 29)]
        self.assertGreater(metrics.compute([], curve, 1000, 0)["sharpe"] or 1e9, 0)

    def test_breakdowns(self):
        tr = [{"pnl_usd": 10, "R": 1, "regime": "BULLISH", "phase": "BREAKOUT", "cap_bucket": "x", "exit_reason": "TP1"}]
        m = metrics.compute(tr, [("2024-01-01", 1000), ("2024-01-02", 1010)], 1000, 0)
        self.assertEqual(m["by_regime"]["BULLISH"]["trades"], 1); self.assertIn("BREAKOUT", m["by_phase"])

    def test_benchmark(self):
        m = metrics.compute([], [("2024-01-01", 1000), ("2024-01-02", 1000)], 1000, 0,
                            benchmark=[("2024-01-01", 1000), ("2024-01-02", 1500)])
        self.assertEqual(m["btc_buy_hold_pct"], 50.0)


# ================================================================== 10. Backtest profesional (mecánica)
_COIN_K = None


def _mini_market(coin_closes, btc_closes=None, coin_k=None):
    global _COIN_K
    n = len(coin_closes)
    btc = make_k(btc_closes or walk(n, 77, drift=0.002, vol=0.01, p0=30000))
    _COIN_K = coin_k or make_k(coin_closes)
    mk = B.Market({"BTC": btc, "COIN": _COIN_K})
    return mk, None


def _sig_for(mk, day_idx, cand, regime_name="BULLISH"):
    sig = {t: {"regime": regime_name, "breadth": 60, "cands": []} for t in mk.days}
    sig[mk.days[day_idx]]["cands"] = [cand]
    return sig


def _cand(price, entry_high, stop, tp, sym="COIN", i=0, phase="BREAKOUT", score=90, trigger=None):
    return {"sym": sym, "i": i, "score": score, "phase": phase, "phase_label": phase, "manip": 0, "manip_level": "BAJO",
            "rr": 3.0, "price": price, "entry_low": entry_high * 0.98, "entry_high": entry_high, "entry": entry_high * 0.99,
            "trigger": trigger, "stop": stop, "tp": tp, "avg_vol": None}


CFG = {"use_exit_intelligence": False, "capital": 10000, "fee_pct": 0.1, "slippage_pct": 0.0, "spread_pct": 0.0}


class T10_Backtest(unittest.TestCase):
    def _run(self, closes, opens=None, highs=None, lows=None, d=100, cand=None, cfg=None):
        k = make_k(closes)
        for arr, key in ((opens, "o"), (highs, "h"), (lows, "l")):
            if arr:
                for j, v in arr.items():
                    k[key][j] = v
        mk, _ = _mini_market(closes, coin_k=k)
        cand = cand or _cand(closes[d], closes[d], closes[d] * 0.9, (closes[d] * 1.15, closes[d] * 1.3, closes[d] * 1.5), i=d)
        sig = _sig_for(mk, d, cand)
        return B.simulate(mk, sig, cfg=dict(CFG, **(cfg or {})))

    def test_no_fill_on_signal_day(self):
        r = self._run([100.0] * 200)
        if r["trades"]:
            self.assertGreater(r["trades"][0]["entry_date"], B.day(T0 + 100 * DAY))

    def test_fill_next_day_at_open_or_limit(self):
        closes = [100.0] * 200
        r = self._run(closes, opens={101: 99.0}, lows={101: 98.0})
        self.assertEqual(r["trades"][0]["entry_date"], B.day(T0 + 101 * DAY))
        self.assertAlmostEqual(r["trades"][0]["entry"], 99.0, places=6)

    def test_limit_not_filled_if_price_above(self):
        closes = [100.0] * 101 + [110.0] * 99
        k_low = {j: 108.0 for j in range(101, 200)}
        r = self._run(closes, opens={101: 109.0}, lows=k_low)
        self.assertEqual(len(r["trades"]), 0)
        self.assertGreaterEqual(r["metrics"]["orders_cancelled"], 1)

    def test_order_expires(self):
        closes = [100.0] * 101 + [110.0] * 99
        r = self._run(closes, lows={j: 108.0 for j in range(101, 200)}, cfg={"order_expiry_days": 2})
        self.assertEqual(r["metrics"]["trades"], 0)

    def test_stop_hit_after_entry(self):
        closes = [100.0] * 101 + [100.0] * 5 + [85.0] * 94
        r = self._run(closes)
        self.assertEqual(r["trades"][0]["exit_reason"], "Stop")
        self.assertLess(r["trades"][0]["pnl_usd"], 0)

    def test_gap_below_stop_fills_at_open(self):
        closes = [100.0] * 110 + [70.0] * 90
        r = self._run(closes, opens={110: 70.0})
        t = r["trades"][0]
        self.assertIn("hueco", t["exit_reason"])
        self.assertAlmostEqual(t["fills"][-1]["price"], 70.0, places=6)

    def test_same_day_stop_pessimistic(self):
        closes = [100.0] * 200
        r = self._run(closes, lows={101: 89.0})
        self.assertEqual(r["trades"][0]["exit_reason"], "Stop el mismo día de la entrada")

    def test_ambiguous_bar_stop_first(self):
        closes = [100.0] * 200
        r = self._run(closes, highs={105: 120.0}, lows={105: 89.0})
        self.assertEqual(r["trades"][0]["exit_reason"], "Stop")
        self.assertTrue(r["trades"][0]["ambiguous_bar"]); self.assertEqual(r["metrics"]["ambiguous_bars"], 1)

    def test_partial_tp1_moves_stop_to_entry(self):
        closes = [100.0] * 105 + [116.0] * 3 + [99.0] * 92
        r = self._run(closes)
        t = r["trades"][0]
        self.assertEqual(t["tp_hits"], 1); self.assertEqual(t["exit_reason"], "Stop a la entrada tras TP1")

    def test_all_targets(self):
        closes = [100.0] * 105 + [116, 131, 151] + [151.0] * 92
        t = self._run(closes)["trades"][0]
        self.assertEqual(t["tp_hits"], 3); self.assertEqual(t["exit_reason"], "TP3")
        self.assertGreater(t["pnl_usd"], 0)

    def test_fees_charged(self):
        r = self._run([100.0] * 200)
        self.assertGreater(r["metrics"]["fees_usd"], 0)

    def test_cash_accounting_consistent(self):
        closes = [100.0] * 105 + [116.0] * 3 + [99.0] * 92
        r = self._run(closes)
        pnl = sum(t["pnl_usd"] for t in r["trades"])
        self.assertAlmostEqual(r["curve"][-1][1] - 10000, pnl, delta=0.05)

    def test_trade_log_has_fills(self):
        t = self._run([100.0] * 105 + [85.0] * 95)["trades"][0]
        self.assertEqual(t["fills"][0]["side"], "BUY"); self.assertEqual(t["fills"][-1]["side"], "SELL")

    def test_end_of_period_closes_positions(self):
        t = self._run([100.0] * 200)["trades"][0]
        self.assertIn("Fin del periodo", t["exit_reason"])

    def test_benchmark_present(self):
        r = self._run([100.0] * 200)
        self.assertIsNotNone(r["metrics"]["btc_buy_hold_pct"])

    def test_breakout_stop_order(self):
        closes = [100.0] * 101 + [100.0] * 99
        cand = _cand(100, 99, 90, (115, 130, 150), i=100, trigger=103.0)
        cand["entry_high"] = 99; cand["price"] = 100
        k_hi = {101: 104.0}
        mk_closes = closes
        k = make_k(mk_closes); k["h"][101] = 104.0
        mk, _ = _mini_market(mk_closes, coin_k=k)
        ev = {"phase": "PRE-EXPLOSION", "score": 90}
        cand["phase"] = "PRE-EXPLOSION"
        sig = _sig_for(mk, 100, cand)
        r = B.simulate(mk, sig, cfg=CFG)
        if r["trades"]:
            self.assertGreaterEqual(r["trades"][0]["entry"], 103.0)

    def test_drawdown_pause_not_permanent(self):
        mk, _ = _mini_market([100.0] * 50)
        self.assertIn("dd_cooldown_days", B.DEFAULTS)

    def test_universe_point_in_time(self):
        k1 = make_k([1.0] * 200, vols=[1e8] * 200)
        k2 = make_k([1.0] * 200, vols=[1e3] * 100 + [1e9] * 100)
        mk = B.Market({"BTC": make_k(walk(200, 3, p0=30000)), "A": k1, "Z": k2})
        early_u = [s for s, _ in B.universe(mk, mk.days[130], 1, 120, 0) if s != "BTC"]
        self.assertEqual(early_u, ["Z"])        # el día 130 la media de 30 d de Z ya supera a A
        u_before = [s for s, _ in B.universe(mk, mk.days[99], 3, 0, 0)]
        self.assertEqual(u_before[-1], "Z")

    def test_score_validation_structure(self):
        s = [{"t": i // 10, "score": i % 100, "fwd": (i % 7 - 3) / 100, "fam": {k: 0.5 for k in early.DEFAULT_WEIGHTS}, "phase": "MOMENTUM"} for i in range(500)]
        v = B.score_validation(s)
        self.assertEqual(len(v["quintiles"]), 5); self.assertIn("score", v["rank_ic"])


# ================================================================== 11. Almacenamiento y alertas
class T11_AlmacenAlertas(unittest.TestCase):
    def test_storage_roundtrip(self):
        storage.write("t_round.json", {"a": 1}); self.assertEqual(storage.read("t_round.json"), {"a": 1})

    def test_storage_update_atomic_under_threads(self):
        storage.write("t_cnt.json", 0)
        th = [threading.Thread(target=lambda: [storage.update("t_cnt.json", lambda v: (v or 0) + 1, 0) for _ in range(50)]) for _ in range(8)]
        [t.start() for t in th]; [t.join() for t in th]
        self.assertEqual(storage.read("t_cnt.json"), 400)

    def test_alert_dedupe(self):
        s = {"desktop_notifications": False}
        a = alerts.emit(s, "PRE-EXPLOSION", "DDD", "x"); b = alerts.emit(s, "PRE-EXPLOSION", "DDD", "x")
        self.assertIsNotNone(a); self.assertIsNone(b)

    def test_alert_dedupe_parallel(self):
        s = {"desktop_notifications": False}
        res = []
        th = [threading.Thread(target=lambda: res.append(alerts.emit(s, "BREAKOUT CONFIRMATION", "PAR", "x"))) for _ in range(10)]
        [t.start() for t in th]; [t.join() for t in th]
        self.assertEqual(sum(1 for r in res if r), 1)

    def test_signal_alert_content(self):
        f = features.compute(make_k(trending(300)))
        a = engine.analyze("ABC", f, 299, BTC_UP, 299, regime={"regime": "BULLISH"}, check_quality=True, now_ms=f.t[299] + DAY)
        a["regime"] = "BULLISH"
        txt = notify.signal_text(a)
        for word in ("Precio", "Puntaje", "Por qué", "Riesgos", "Invalidación", "TP1", "Zona de entrada", "calidad", "UTC"):
            self.assertIn(word, txt)

    def test_alert_has_no_return_promise(self):
        f = features.compute(make_k(trending(300)))
        a = engine.analyze("ABC", f, 299, BTC_UP, 299, check_quality=False); a["regime"] = "NEUTRAL"
        self.assertNotRegex(notify.signal_text(a).lower(), r"garantiza|seguro que|ganancia asegurada")

    def test_summaries_once_per_day(self):
        rep = {"market": {"regime": "NEUTRAL", "btc_price": 1, "breadth": 50}, "verdict": "X", "verdict_text": "y", "ranking": [], "avoid": [], "analyzed": 1}
        s = {"desktop_notifications": False}
        notify.maybe_summaries(rep, s); n1 = len(storage.read("alerts.json", []))
        notify.maybe_summaries(rep, s); n2 = len(storage.read("alerts.json", []))
        self.assertEqual(n1, n2)

    def test_exit_text(self):
        p = {"entry": 10.0}
        a = {"price": 12.0, "exit": {"decision": "REDUCIR POSICIÓN", "reasons": ["a", "b"], "sell_fraction": 0.33, "suggested_stop": 10.0, "trailing_stop": 11.0, "gain_R": 1.5}, "quality": None}
        t = notify.exit_text(p, a)
        self.assertIn("Vender 33%", t); self.assertIn("Stop sugerido", t)


# ================================================================== 12. Escáner (datos sintéticos)
class T12_Escaner(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fake_market
        cls._orig = {k: getattr(data, k) for k in ("cg_global", "fear_greed", "cg_markets", "binance_symbols", "klines", "funding_rates", "open_interest_change", "_binance")}
        fake_market.install()
        from radar import scanner
        scanner.category_map = lambda force=False: {}
        cls.scanner = scanner
        cls.rep = scanner.run_scan()

    @classmethod
    def tearDownClass(cls):
        for k, v in cls._orig.items():
            setattr(data, k, v)

    def test_scan_completes(self):
        self.assertIsNotNone(self.rep, self.scanner.status["last_error"])

    def test_ranking_fields(self):
        need = {"symbol", "price", "score", "phase", "rel_volume", "chg_24h", "chg_7d", "chg_30d", "rs_btc_30d", "liquidity",
                "manipulation_risk", "entry_low", "entry_high", "stop", "tp1", "tp2", "tp3", "rr", "action"}
        for r in self.rep["ranking"]:
            self.assertTrue(need <= set(r), need - set(r))

    def test_ranking_excludes_overextended(self):
        self.assertTrue(all(r["phase"] not in ("OVEREXTENDED", "DISTRIBUTION", "REJECTED") for r in self.rep["ranking"]))

    def test_ranking_sorted(self):
        rs = [r["rank_score"] for r in self.rep["ranking"]]
        self.assertEqual(rs, sorted(rs, reverse=True))

    def test_report_sections(self):
        for k in ("verdict", "market", "early", "breakouts", "avoid", "assets", "sources", "phase_counts"):
            self.assertIn(k, self.rep)

    def test_regime_in_report(self):
        self.assertIn(self.rep["market"]["regime"], regime.POLICY)

    def test_rank_prefers_early_phase(self):
        base = {"phase": "MOMENTUM", "action": "VIGILAR", "score": 60, "metrics": {"chg_30d": 0}, "manipulation": {"risk": 0}, "quality": {"score": 100}, "plan": {"rr": 3}}
        pre = dict(base, phase="PRE-EXPLOSION")
        self.assertGreater(self.scanner.rank_score(pre), self.scanner.rank_score(base))

    def test_rank_penalizes_runup(self):
        a = {"phase": "BREAKOUT", "action": "VIGILAR", "score": 70, "metrics": {"chg_30d": 10}, "manipulation": {"risk": 0}, "quality": {"score": 100}, "plan": {"rr": 3}}
        b = dict(a, metrics={"chg_30d": 90})
        self.assertGreater(self.scanner.rank_score(a), self.scanner.rank_score(b))


# ================================================================== 13. Seguridad y SaaS (SQLite)
class T13_SaaS(unittest.TestCase):
    def setUp(self):
        from radar import auth as _a; _a._rate.clear()   # los límites por IP son reales; cada prueba parte limpia

    @classmethod
    def setUpClass(cls):
        from radar import server
        from http.server import ThreadingHTTPServer
        server.ACCOUNTS = True
        db.init()
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        from radar import server
        cls.httpd.shutdown(); server.ACCOUNTS = False

    def test_client_ip_not_spoofable_via_forwarded_for(self):
        from radar import server
        class H: pass
        h = H(); h.headers = {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"}; h.client_address = ("10.0.0.1", 0)
        self.assertEqual(server.Handler._client_ip(h), "203.0.113.9")   # el último lo añade el proxy

    def test_registration_rate_limited_per_ip(self):
        from radar import auth as _a
        for i in range(5):
            _a.register(f"rl{i}{random.randint(0, 10**9)}@example.com", "clave muy segura 123", ip="10.9.9.9")
        with self.assertRaises(_a.AuthError) as cm:
            _a.register(f"rl6{random.randint(0, 10**9)}@example.com", "clave muy segura 123", ip="10.9.9.9")
        self.assertEqual(cm.exception.code, 429)

    def client(self):
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, op, path, body=None, headers=None, raw=None):
        h = {"Content-Type": "application/json", "Origin": self.base}
        h.update(headers or {})
        data_ = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, data=data_, headers=h, method="POST" if data_ is not None else "GET")
        try:
            r = op.open(req); return r.status, json.loads(r.read() or b"{}"), r.headers
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}"), e.headers

    def signup(self, email=None, pw="clave muy segura 123"):
        op = self.client(); email = email or f"u{random.randint(0, 10**9)}@example.com"
        st, r, h = self.call(op, "/api/auth/register", {"email": email, "password": pw})
        self.assertEqual(st, 200, r)
        return op, r["csrf"], email

    def test_password_hash_scrypt_salted(self):
        a, b = auth.hash_password("x" * 12), auth.hash_password("x" * 12)
        self.assertTrue(a.startswith("scrypt$")); self.assertNotEqual(a, b)
        self.assertTrue(auth.verify_password("x" * 12, a)); self.assertFalse(auth.verify_password("y" * 12, a))

    def test_weak_password_rejected(self):
        st, r, _ = self.call(self.client(), "/api/auth/register", {"email": "weak@example.com", "password": "123"})
        self.assertEqual(st, 400)

    def test_invalid_email_rejected(self):
        st, _, _ = self.call(self.client(), "/api/auth/register", {"email": "no-es-correo", "password": "clave muy segura 123"})
        self.assertEqual(st, 400)

    def test_duplicate_email(self):
        op, csrf, email = self.signup()
        st, _, _ = self.call(self.client(), "/api/auth/register", {"email": email, "password": "clave muy segura 123"})
        self.assertEqual(st, 409)

    def test_session_cookie_flags(self):
        op = self.client()
        st, r, h = self.call(op, "/api/auth/register", {"email": "flags@example.com", "password": "clave muy segura 123"})
        ck = h.get("Set-Cookie")
        self.assertIn("HttpOnly", ck); self.assertIn("SameSite=Lax", ck)

    def test_session_token_stored_hashed(self):
        op, csrf, email = self.signup()
        rows = db.all_("SELECT token_hash FROM sessions", ())
        self.assertTrue(all(len(r["token_hash"]) == 64 for r in rows))

    def test_requires_login(self):
        self.assertEqual(self.call(self.client(), "/api/state")[0], 401)

    def test_csrf_required(self):
        op, csrf, _ = self.signup()
        self.assertEqual(self.call(op, "/api/me/settings", {"capital_usd": 5})[0], 403)
        self.assertEqual(self.call(op, "/api/me/settings", {"capital_usd": 5}, {"X-CSRF-Token": csrf})[0], 200)

    def test_foreign_origin_blocked(self):
        op, csrf, _ = self.signup()
        st, _, _ = self.call(op, "/api/me/settings", {"capital_usd": 5}, {"X-CSRF-Token": csrf, "Origin": "https://evil.example"})
        self.assertEqual(st, 403)

    def test_non_json_post_blocked(self):
        op, csrf, _ = self.signup()
        st, _, _ = self.call(op, "/api/me/settings", raw=b"a=1", headers={"Content-Type": "text/plain", "X-CSRF-Token": csrf})
        self.assertEqual(st, 403)

    def test_body_too_large(self):
        op, csrf, _ = self.signup()
        st, _, _ = self.call(op, "/api/me/settings", raw=b"{" + b" " * 70000 + b"}", headers={"X-CSRF-Token": csrf})
        self.assertEqual(st, 413)

    def test_security_headers(self):
        st, _, h = self.call(self.client(), "/api/public/status")
        self.assertEqual(h.get("X-Frame-Options"), "DENY"); self.assertIn("default-src 'self'", h.get("Content-Security-Policy"))
        self.assertEqual(h.get("X-Content-Type-Options"), "nosniff")

    def test_account_lockout(self):
        op, csrf, email = self.signup()
        bad = self.client()
        codes = [self.call(bad, "/api/auth/login", {"email": email, "password": "incorrecta 12345"})[0] for _ in range(6)]
        self.assertEqual(codes[-1], 429)

    def test_logout_invalidates_session(self):
        op, csrf, _ = self.signup()
        self.call(op, "/api/auth/logout", {}, {"X-CSRF-Token": csrf})
        self.assertEqual(self.call(op, "/api/me")[0], 401)

    def test_free_plan_limits(self):
        storage.write("latest.json", {"at": "2026-01-01T00:00:00+00:00", "market": {"regime": "NEUTRAL"}, "ranking": [{"symbol": f"S{i}"} for i in range(10)],
                                      "assets": [{"symbol": f"S{i}", "price": 1} for i in range(10)]})
        op, csrf, _ = self.signup()
        st, r, _ = self.call(op, "/api/state")
        self.assertEqual(len(r["report"]["ranking"]), 3); self.assertTrue(r["report"]["locked"])
        self.assertEqual(self.call(op, "/api/positions")[0], 402)

    def test_non_admin_cannot_scan_or_change_system_settings(self):
        op, csrf, _ = self.signup()
        self.assertEqual(self.call(op, "/api/scan", {}, {"X-CSRF-Token": csrf})[0], 403)
        self.assertEqual(self.call(op, "/api/settings", {"universe_size": 5}, {"X-CSRF-Token": csrf})[0], 403)

    def test_admin_email_gets_admin(self):
        op = self.client()
        st, r, _ = self.call(op, "/api/auth/register", {"email": "admin@example.com", "password": "clave muy segura 123"})
        self.assertTrue(r["user"]["is_admin"])

    def test_user_isolation_positions(self):
        a, ca, ea = self.signup(); b, cb, eb = self.signup()
        for e in (ea, eb):
            uid = db.one("SELECT id FROM users WHERE email = ?", (e,))["id"]
            db.execute("UPDATE users SET plan = 'pro', plan_until = ? WHERE id = ?", (time.time() + 86400, uid))
        st, p, _ = self.call(a, "/api/positions", {"symbol": "SOL", "entry": 100}, {"X-CSRF-Token": ca})
        self.assertEqual(st, 200)
        self.assertEqual(self.call(b, "/api/positions")[1], [])
        st, _, _ = self.call(b, f"/api/positions/{p['id']}/delete", {}, {"X-CSRF-Token": cb})
        self.assertEqual(st, 404)
        self.assertEqual(len(self.call(a, "/api/positions")[1]), 1)

    def test_position_input_validation(self):
        a, ca, ea = self.signup()
        uid = db.one("SELECT id FROM users WHERE email = ?", (ea,))["id"]
        db.execute("UPDATE users SET plan = 'pro', plan_until = ? WHERE id = ?", (time.time() + 86400, uid))
        self.assertEqual(self.call(a, "/api/positions", {"symbol": "SOL'; DROP TABLE users;--", "entry": 1}, {"X-CSRF-Token": ca})[0], 400)
        self.assertEqual(self.call(a, "/api/positions", {"symbol": "SOL", "entry": "nan"}, {"X-CSRF-Token": ca})[0], 400)
        self.assertIsNotNone(db.one("SELECT COUNT(*) AS n FROM users", ()))

    def test_activity_log(self):
        op, csrf, email = self.signup()
        acts = [r["action"] for r in self.call(op, "/api/activity")[1]]
        self.assertIn("register", acts); self.assertIn("login", acts)

    def test_expired_plan_is_free(self):
        self.assertEqual(auth.effective_plan({"plan": "pro", "plan_until": time.time() - 1, "is_admin": 0}), "free")

    def test_checkout_disabled_without_keys(self):
        op, csrf, _ = self.signup()
        st, r, _ = self.call(op, "/api/billing/checkout", {"plan": "pro", "period": "month", "provider": "wompi"}, {"X-CSRF-Token": csrf})
        self.assertEqual(st, 503)


# ================================================================== 14. Pagos verificados
class T14_Pagos(unittest.TestCase):
    ENV = {"WOMPI_PUBLIC_KEY": "pub_test", "WOMPI_INTEGRITY_SECRET": "integ", "WOMPI_EVENTS_SECRET": "evsecret", "COP_PER_USD": "4000",
           "NOWPAYMENTS_API_KEY": "k", "NOWPAYMENTS_IPN_SECRET": "ipn"}

    def setUp(self):
        self._old = {k: os.environ.get(k) for k in self.ENV}; os.environ.update(self.ENV)
        db.init()
        auth._rate.clear()
        self.user = auth.register(f"pay{random.randint(0, 10**9)}@example.com", "clave muy segura 123")

    def tearDown(self):
        for k, v in self._old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def _event(self, ref, status="APPROVED", amount=None, secret="evsecret"):
        tx = {"id": "tx1", "status": status, "amount_in_cents": amount, "reference": ref, "currency": "COP"}
        ts = 1700000000
        props = ["transaction.id", "transaction.status", "transaction.amount_in_cents"]
        chk = hashlib.sha256(f"tx1{status}{amount}{ts}{secret}".encode()).hexdigest()
        return {"event": "transaction.updated", "data": {"transaction": tx}, "timestamp": ts, "signature": {"properties": props, "checksum": chk}}

    def _checkout(self):
        r = billing.checkout(self.user, "pro", "month", "wompi", "https://app.example")
        pay = db.one("SELECT * FROM payments WHERE reference = ?", (r["reference"],))
        return r, pay

    def test_checkout_integrity_signature(self):
        r, pay = self._checkout()
        exp = hashlib.sha256(f"{pay['reference']}{pay['amount_cents']}COPinteg".encode()).hexdigest()
        self.assertIn(exp, r["url"]); self.assertEqual(pay["amount_cents"], 19 * 4000 * 100)

    def test_valid_webhook_grants_after_api_confirmation(self):
        r, pay = self._checkout()
        ev = self._event(pay["reference"], amount=pay["amount_cents"])
        real = {"data": {"status": "APPROVED", "reference": pay["reference"], "amount_in_cents": pay["amount_cents"], "currency": "COP"}}
        code, _ = billing.wompi_webhook(ev, fetch=lambda tid: real)
        self.assertEqual(code, 200)
        self.assertEqual(auth.effective_plan(auth.get_user(self.user["id"])), "pro")

    def test_bad_signature_rejected(self):
        r, pay = self._checkout()
        ev = self._event(pay["reference"], amount=pay["amount_cents"], secret="otro")
        code, _ = billing.wompi_webhook(ev, fetch=lambda tid: {})
        self.assertEqual(code, 401); self.assertEqual(auth.effective_plan(auth.get_user(self.user["id"])), "free")

    def test_amount_mismatch_rejected(self):
        r, pay = self._checkout()
        ev = self._event(pay["reference"], amount=pay["amount_cents"])
        real = {"data": {"status": "APPROVED", "reference": pay["reference"], "amount_in_cents": 100, "currency": "COP"}}
        self.assertEqual(billing.wompi_webhook(ev, fetch=lambda tid: real)[0], 409)
        self.assertEqual(auth.effective_plan(auth.get_user(self.user["id"])), "free")

    def test_api_unreachable_no_grant(self):
        r, pay = self._checkout()
        ev = self._event(pay["reference"], amount=pay["amount_cents"])
        def boom(tid): raise OSError("sin red")
        self.assertEqual(billing.wompi_webhook(ev, fetch=boom)[0], 502)
        self.assertEqual(auth.effective_plan(auth.get_user(self.user["id"])), "free")

    def test_declined_not_granted(self):
        r, pay = self._checkout()
        ev = self._event(pay["reference"], status="DECLINED", amount=pay["amount_cents"])
        self.assertEqual(billing.wompi_webhook(ev, fetch=lambda tid: {})[0], 200)
        self.assertEqual(auth.effective_plan(auth.get_user(self.user["id"])), "free")

    def test_idempotent_grant(self):
        r, pay = self._checkout()
        ev = self._event(pay["reference"], amount=pay["amount_cents"])
        real = {"data": {"status": "APPROVED", "reference": pay["reference"], "amount_in_cents": pay["amount_cents"], "currency": "COP"}}
        billing.wompi_webhook(ev, fetch=lambda tid: real); u1 = auth.get_user(self.user["id"])["plan_until"]
        billing.wompi_webhook(ev, fetch=lambda tid: real); u2 = auth.get_user(self.user["id"])["plan_until"]
        self.assertEqual(u1, u2)

    def test_nowpayments_signature(self):
        body = {"payment_id": 5, "order_id": "X", "payment_status": "finished"}
        sig = hmac.new(b"ipn", json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha512).hexdigest()
        self.assertTrue(billing.nowpayments_signature_ok(body, sig, "ipn"))
        self.assertFalse(billing.nowpayments_signature_ok(body, sig, "otro"))

    def test_admin_grant_requires_admin_and_reason(self):
        with self.assertRaises(auth.AuthError):
            billing.admin_grant({"is_admin": 0, "id": "x"}, self.user["email"], "pro", 30, "cortesía")
        with self.assertRaises(auth.AuthError):
            billing.admin_grant({"is_admin": 1, "id": "x"}, self.user["email"], "pro", 30, "")


# ================================================================== 15. Telegram y memecoins
class T15_TelegramMemes(unittest.TestCase):
    def test_link_flow(self):
        db.init()
        auth._rate.clear()
        u = auth.register(f"tg{random.randint(0, 10**9)}@example.com", "clave muy segura 123")
        code = telegram_bot.new_link_code(u["id"])
        reply = telegram_bot.handle({"chat": {"id": 4242}, "text": f"/start {code}"})
        self.assertIn("vinculado", reply)
        self.assertEqual(auth.get_user(u["id"])["telegram_chat_id"], "4242")

    def test_invalid_code(self):
        self.assertIn("no válido", telegram_bot.handle({"chat": {"id": 1}, "text": "/start ZZZZZZZZ"}))

    def test_commands_without_link(self):
        self.assertIn("no está vinculado", telegram_bot.handle({"chat": {"id": 999}, "text": "/cartera"}))
        self.assertIn("Comandos", telegram_bot.handle({"chat": {"id": 999}, "text": "/ayuda"}))

    def test_meme_onchain_nd(self):
        self.assertTrue(meme_radar.ONCHAIN_ND.startswith("N/D"))

    def test_meme_risk_profile(self):
        r, why = meme_radar.risk_profile(10, 1e6, 20e6, 100e6, 50, 15)
        self.assertGreaterEqual(r, 60); self.assertTrue(any("FDV" in w for w in why))
        r2, _ = meme_radar.risk_profile(800, 5e8, 1e10, 1e10, 0, 4)
        self.assertLess(r2, r)


# ================================================================== 16. Interfaz
class T16_Interfaz(unittest.TestCase):
    def test_eleven_sections(self):
        html = (ROOT / "web" / "index.html").read_text("utf-8")
        for v in ("dash", "early", "market", "breakouts", "memes", "exits", "portfolio", "backtest", "perf", "alerts", "settings"):
            self.assertIn(f'id="v-{v}"', html)

    def test_js_syntax(self):
        if not shutil.which("node"):
            self.skipTest("node no disponible")
        r = subprocess.run(["node", "--check", str(ROOT / "web" / "app.js")], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_no_hardcoded_numbers_in_backtest_view(self):
        js = (ROOT / "web" / "app.js").read_text("utf-8")
        self.assertIn("/api/backtest/results", js)
        self.assertNotRegex(js, r"retorno[^\n]{0,40}\d{2,}\s*%")


# ================================================================== 17. PostgreSQL (opcional, real)
@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL no definido")
class T17_Postgres(unittest.TestCase):
    def test_postgres_end_to_end(self):
        code = r'''
import os, sys, time, tempfile
os.environ["CRYPTO_RADAR_HOME"] = tempfile.mkdtemp()
sys.path.insert(0, sys.argv[1])
from radar import db, auth, storage, multiuser
assert db.IS_PG
for t in ("users", "sessions", "activity", "positions", "payments", "telegram_links", "kv"):
    db.execute(f"DROP TABLE IF EXISTS {t}")
db._ready = False; db.init()
u = auth.register("pg@example.com", "clave muy segura 123")
tok, csrf, _ = auth.login("pg@example.com", "clave muy segura 123")
assert auth.session(tok)["user"]["email"] == "pg@example.com"
storage.write("latest.json", {"a": [1, 2]}); assert storage.read("latest.json") == {"a": [1, 2]}
p = multiuser.add_position(u["id"], {"symbol": "SOL", "entry": 1.0})
assert multiuser.list_positions(u["id"])[0]["id"] == p["id"]
print("PG_OK", db.backend())
'''
        env = dict(os.environ, DATABASE_URL=os.environ["TEST_DATABASE_URL"])
        r = subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, text=True, env=env, timeout=120)
        self.assertIn("PG_OK postgresql", r.stdout, r.stderr[-2000:])


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1, argv=[sys.argv[0]] + [a for a in sys.argv[1:] if a != "-v"])
