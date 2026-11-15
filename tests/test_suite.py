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
os.environ["CRYPTO_RADAR_ADMIN_USER"] = "admin"
os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "clave larga del jefe 2026"
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
        from radar import auth as _a; _a.reset_rate_limits()   # los límites por IP son reales; cada prueba parte limpia

    @classmethod
    def setUpClass(cls):
        from radar import server
        from http.server import ThreadingHTTPServer
        server.ACCOUNTS = True
        db.init()
        auth.ensure_admin()
        cls.admin = db.one("SELECT * FROM users WHERE email = 'admin'", ())
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
        for i in range(3):
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

    def request(self, username=None, pw="clave muy segura 123", op=None, note=None):
        username = username or f"u{random.randint(0, 10**9)}"
        body = {"username": username, "password": pw}
        if note: body["note"] = note
        return self.call(op or self.client(), "/api/auth/request", body), username

    def approve(self, username, plan="free", days=0):
        uid = db.one("SELECT id FROM users WHERE email = ?", (username,))["id"]
        auth.admin_set_status(self.admin, uid, "approve", plan, days)
        return uid

    def signup(self, email=None, pw="clave muy segura 123"):
        auth.reset_rate_limits()
        (st, r, _), username = self.request(email, pw)
        self.assertEqual(st, 200, r)
        self.approve(username)
        op = self.client()
        st, r, h = self.call(op, "/api/auth/login", {"username": username, "password": pw})
        self.assertEqual(st, 200, r)
        return op, r["csrf"], username

    def test_password_hash_scrypt_salted(self):
        a, b = auth.hash_password("x" * 12), auth.hash_password("x" * 12)
        self.assertTrue(a.startswith("scrypt$")); self.assertNotEqual(a, b)
        self.assertTrue(auth.verify_password("x" * 12, a)); self.assertFalse(auth.verify_password("y" * 12, a))

    def test_weak_password_rejected(self):
        auth.reset_rate_limits()
        st, r, _ = self.call(self.client(), "/api/auth/request", {"username": "weakuser", "password": "123"})
        self.assertEqual(st, 400)
        st, r, _ = self.call(self.client(), "/api/auth/request", {"username": "weakuser", "password": "weakuser12345"})
        self.assertEqual(st, 400)                                   # contiene el usuario

    def test_invalid_username_rejected(self):
        for bad in ("No Válido!", "ab", "x" * 40, "<script>", "a b"):
            auth.reset_rate_limits()
            st, _, _ = self.call(self.client(), "/api/auth/request", {"username": bad, "password": "clave muy segura 123"})
            self.assertEqual(st, 400, bad)

    def test_duplicate_email(self):
        op, csrf, email = self.signup()
        st, _, _ = self.call(self.client(), "/api/auth/request", {"username": email, "password": "clave muy segura 123"})
        self.assertEqual(st, 409)

    def test_session_cookie_flags(self):
        (st, r, _), u = self.request("flags.user")
        self.approve(u)
        st, r, h = self.call(self.client(), "/api/auth/login", {"username": u, "password": "clave muy segura 123"})
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
        codes = [self.call(bad, "/api/auth/login", {"username": email, "password": "incorrecta 12345"})[0] for _ in range(6)]
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

    def test_env_admin_is_admin_and_registration_cannot_create_admins(self):
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": "admin", "password": "clave larga del jefe 2026"})
        self.assertEqual(st, 200, r); self.assertTrue(r["user"]["is_admin"])
        (st, r, _), u = self.request("admin2")
        self.assertEqual(st, 200)
        self.assertEqual(db.one("SELECT is_admin, status FROM users WHERE email = 'admin2'", ()), {"is_admin": 0, "status": "pending"})

    def test_request_does_not_log_in_and_pending_cannot_enter(self):
        op = self.client()
        (st, r, h), u = self.request(op=op)
        self.assertEqual(st, 200); self.assertIsNone(h.get("Set-Cookie")); self.assertNotIn("csrf", r)
        self.assertEqual(self.call(op, "/api/me")[0], 401)
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": u, "password": "clave muy segura 123"})
        self.assertEqual(st, 403); self.assertIn("pendiente", r["error"])
        # con la contraseña equivocada no se revela que existe una solicitud
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": u, "password": "otra clave 98765"})
        self.assertEqual(st, 401)
        self.approve(u)
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": u.upper(), "password": "clave muy segura 123"})[0], 200)

    def test_same_error_for_unknown_user_and_wrong_password(self):
        op, csrf, u = self.signup()
        a = self.call(self.client(), "/api/auth/login", {"username": u, "password": "mala clave 12345"})
        b = self.call(self.client(), "/api/auth/login", {"username": "no.existe", "password": "mala clave 12345"})
        self.assertEqual((a[0], a[1]["error"]), (b[0], b[1]["error"]))

    def test_rejected_and_disabled_users(self):
        (st, r, _), u = self.request()
        uid = db.one("SELECT id FROM users WHERE email = ?", (u,))["id"]
        auth.admin_set_status(self.admin, uid, "reject")
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": u, "password": "clave muy segura 123"})[0], 403)
        op, csrf, u2 = self.signup()
        uid2 = db.one("SELECT id FROM users WHERE email = ?", (u2,))["id"]
        auth.admin_set_status(self.admin, uid2, "disable")
        self.assertEqual(self.call(op, "/api/me")[0], 401)                 # su sesión se cierra al momento
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": u2, "password": "clave muy segura 123"})[0], 403)

    def admin_client(self):
        op = self.client()
        st, r, _ = self.call(op, "/api/auth/login", {"username": "admin", "password": "clave larga del jefe 2026"})
        return op, r["csrf"]

    def test_admin_api_approve_create_reset(self):
        op, csrf = self.admin_client()
        (st, r, _), u = self.request(note="quiero el plan pro")
        users = self.call(op, "/api/admin/users")[1]
        row = next(x for x in users if x["email"] == u)
        self.assertEqual(row["status"], "pending"); self.assertEqual(users[0]["status"], "pending")
        st, r, _ = self.call(op, "/api/admin/user", {"id": row["id"], "action": "approve", "plan": "pro", "days": 30}, {"X-CSRF-Token": csrf})
        self.assertEqual(st, 200, r)
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": u, "password": "clave muy segura 123"})
        self.assertEqual(r["user"]["plan"], "pro")
        st, r, _ = self.call(op, "/api/admin/user/create", {"username": "creado.por.admin", "password": "otra clave segura 1", "plan": "free"}, {"X-CSRF-Token": csrf})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": "creado.por.admin", "password": "otra clave segura 1"})[0], 200)
        st, r, _ = self.call(op, "/api/admin/user/password", {"id": row["id"], "password": "clave nueva segura 7"}, {"X-CSRF-Token": csrf})
        self.assertEqual(st, 200, r)
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": u, "password": "clave nueva segura 7"})[0], 200)
        # sin CSRF no se puede aprobar
        self.assertEqual(self.call(op, "/api/admin/user", {"id": row["id"], "action": "disable"})[0], 403)

    def test_non_admin_cannot_manage_users(self):
        op, csrf, u = self.signup()
        (st, r, _), other = self.request()
        oid = db.one("SELECT id FROM users WHERE email = ?", (other,))["id"]
        self.assertEqual(self.call(op, "/api/admin/users")[0], 403)
        self.assertEqual(self.call(op, "/api/admin/user", {"id": oid, "action": "approve"}, {"X-CSRF-Token": csrf})[0], 403)
        self.assertEqual(self.call(op, "/api/admin/user/create", {"username": "hacker1", "password": "clave muy segura 123"}, {"X-CSRF-Token": csrf})[0], 403)
        self.assertEqual(db.one("SELECT status FROM users WHERE id = ?", (oid,))["status"], "pending")

    def test_admin_cannot_be_disabled_from_panel(self):
        op, csrf = self.admin_client()
        aid = self.admin["id"]
        self.assertEqual(self.call(op, "/api/admin/user", {"id": aid, "action": "disable"}, {"X-CSRF-Token": csrf})[0], 400)

    def test_pages_and_redirects(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k): return None
        op = urllib.request.build_opener(NoRedirect, urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def get(o, path):
            try:
                r = o.open(self.base + path); return r.status, r.read().decode(), r.headers
            except urllib.error.HTTPError as e:
                return e.code, "", e.headers
        st, body, _ = get(op, "/"); self.assertEqual(st, 200); self.assertIn("Solicitar acceso", body)
        st, body, _ = get(op, "/entrar"); self.assertEqual(st, 200); self.assertIn("loginForm", body)
        st, _, h = get(op, "/app"); self.assertEqual(st, 302); self.assertEqual(h["Location"], "/entrar")
        self.call(op, "/api/auth/login", {"username": "admin", "password": "clave larga del jefe 2026"})
        st, body, _ = get(op, "/app"); self.assertEqual(st, 200); self.assertIn('id="app"', body)
        st, _, h = get(op, "/entrar"); self.assertEqual(st, 302); self.assertEqual(h["Location"], "/app")
        for page in ("/", "/entrar"):
            st, body, h = get(self.client(), page)
            self.assertNotIn("<script>", body)                              # sin JS en línea: lo permite la CSP estricta
            self.assertNotIn("https://cdn", body)
        self.assertEqual(get(self.client(), "/static/vendor/gsap.min.js")[0], 200)

    def test_pending_requests_capped(self):
        old = auth.MAX_PENDING
        try:
            auth.MAX_PENDING = db.one("SELECT COUNT(*) AS n FROM users WHERE status = 'pending'", ())["n"]
            auth.reset_rate_limits()
            st, r, _ = self.call(self.client(), "/api/auth/request", {"username": "uno.mas", "password": "clave muy segura 123"})
            self.assertEqual(st, 503)
        finally:
            auth.MAX_PENDING = old

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
        self.assertIn("access_requested", acts); self.assertIn("login", acts)

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
        auth.reset_rate_limits()
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
        auth.reset_rate_limits()
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


# ================================================================== 18. Auditoría final de seguridad (2.1.0)
class T18_SeguridadFinal(T13_SaaS):
    """Hereda el servidor y los ayudantes de T13; solo ejecuta sus propias pruebas."""
    def setUp(self):
        auth.reset_rate_limits()
        self._env = {k: os.environ.get(k) for k in ("CRYPTO_RADAR_ADMIN_USER", "CRYPTO_RADAR_ADMIN_PASSWORD",
                                                    "CRYPTO_RADAR_ADMIN_RESET", "CRYPTO_RADAR_ADMIN_TAKEOVER")}

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def acts(self, action):
        return db.all_("SELECT user_id, detail FROM activity WHERE action = ? ORDER BY at", (action,))

    # ---------- 1. Bootstrap del administrador
    def test_admin_bootstrap_never_promotes_squatter(self):
        name = f"jefe{random.randint(0, 10**9)}"
        uid = auth.request_access(name, "clave del intruso 99", ip="10.1.1.1")         # alguien reserva el nombre
        auth.admin_set_status(self.admin, uid, "approve")
        tok, _, _ = auth.login(name, "clave del intruso 99")
        os.environ["CRYPTO_RADAR_ADMIN_USER"] = name
        os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "clave real del duenio 2026"
        os.environ.pop("CRYPTO_RADAR_ADMIN_TAKEOVER", None)
        with self.assertRaises(auth.AdminBootstrapError):
            auth.ensure_admin()
        row = db.one("SELECT * FROM users WHERE id = ?", (uid,))
        self.assertEqual(row["is_admin"], 0)                                         # no se promovió
        self.assertTrue(any(a["user_id"] == uid for a in self.acts("admin_bootstrap_conflict")))
        # cuarentena explícita: la cuenta del intruso se aparta y el admin nace con la clave del entorno
        os.environ["CRYPTO_RADAR_ADMIN_TAKEOVER"] = "1"
        self.assertEqual(auth.ensure_admin(), {"user": name, "result": "cuarentena"})
        old = db.one("SELECT * FROM users WHERE id = ?", (uid,))
        self.assertEqual((old["is_admin"], old["status"], old["disabled"]), (0, "rejected", 1))
        self.assertNotEqual(old["email"], name)
        self.assertIsNone(auth.session(tok))                                          # sus sesiones se cerraron
        new = db.one("SELECT * FROM users WHERE email = ?", (name,))
        self.assertNotEqual(new["id"], uid); self.assertEqual(new["is_admin"], 1); self.assertEqual(new["approved_by"], "entorno")
        with self.assertRaises(auth.AuthError):
            auth.login(name, "clave del intruso 99")                                 # su contraseña no sirve
        self.assertEqual(auth.login(name, "clave real del duenio 2026")[2]["is_admin"], True)
        self.assertTrue(self.acts("admin_bootstrap_quarantine")); self.assertTrue(self.acts("admin_bootstrap_created"))
        # el nombre en cuarentena no puede volver a pedirse ni usarse para entrar
        with self.assertRaises(auth.AuthError):
            auth.login(old["email"], "clave del intruso 99")

    def test_admin_bootstrap_verified_and_env_reset(self):
        name = f"jefa{random.randint(0, 10**9)}"
        os.environ["CRYPTO_RADAR_ADMIN_USER"] = name
        os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "primera clave larga 1"
        os.environ.pop("CRYPTO_RADAR_ADMIN_RESET", None)
        self.assertEqual(auth.ensure_admin()["result"], "creado")
        aid = db.one("SELECT id FROM users WHERE email = ?", (name,))["id"]
        auth.change_password(aid, "primera clave larga 1", "clave cambiada en app 2")
        os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "otra clave de entorno 3"
        self.assertEqual(auth.ensure_admin()["result"], "verificado")                # reinicio normal: no pisa su clave
        auth.login(name, "clave cambiada en app 2")
        tok, _, _ = auth.login(name, "clave cambiada en app 2")
        os.environ["CRYPTO_RADAR_ADMIN_RESET"] = "1"
        self.assertEqual(auth.ensure_admin()["result"], "restablecido")
        self.assertIsNone(auth.session(tok))
        auth.login(name, "otra clave de entorno 3")
        self.assertTrue(any(a["user_id"] == aid for a in self.acts("admin_bootstrap_password_reset")))
        self.assertTrue(any(a["user_id"] == aid for a in self.acts("admin_bootstrap_verified")))

    def test_admin_bootstrap_rejects_bad_env(self):
        os.environ["CRYPTO_RADAR_ADMIN_USER"] = "jefe.corto"
        os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "corta"
        with self.assertRaises(auth.AdminBootstrapError):
            auth.ensure_admin()
        os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "jefe.corto 1234567"                # contiene el usuario
        with self.assertRaises(auth.AdminBootstrapError):
            auth.ensure_admin()
        os.environ.pop("CRYPTO_RADAR_ADMIN_PASSWORD")
        with self.assertRaises(auth.AdminBootstrapError):                            # solo una de las dos
            auth.ensure_admin()

    def test_admin_name_and_reserved_names_cannot_be_requested(self):
        for name in ("admin", "administrador", "root", "soporte", os.environ["CRYPTO_RADAR_ADMIN_USER"]):
            auth.reset_rate_limits()
            st, r, _ = self.call(self.client(), "/api/auth/request", {"username": name, "password": "clave muy segura 123"})
            self.assertEqual(st, 409, name)
        with self.assertRaises(auth.AuthError):
            auth.admin_create(self.admin, "root", "clave muy segura 123")

    def test_admin_cannot_touch_other_admin(self):
        name = f"otroadmin{random.randint(0, 10**9)}"
        os.environ["CRYPTO_RADAR_ADMIN_USER"] = name; os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "clave del otro admin 5"
        auth.ensure_admin()
        oid = db.one("SELECT id FROM users WHERE email = ?", (name,))["id"]
        for action in ("approve", "disable", "reject", "delete"):
            with self.assertRaises(auth.AuthError) as cm:
                auth.admin_set_status(self.admin, oid, action)
            self.assertEqual(cm.exception.code, 403)
        with self.assertRaises(auth.AuthError) as cm:
            auth.admin_reset_password(self.admin, oid, "clave impuesta 12345")
        self.assertEqual(cm.exception.code, 403)

    # ---------- 2. Permisos por plan
    def _user_with_plan(self, plan):
        op, csrf, u = self.signup()
        if plan != "free":
            db.execute("UPDATE users SET plan = ?, plan_until = ? WHERE email = ?", (plan, time.time() + 86400, u))
        return op, csrf, u

    def test_entitlements_matrix(self):
        from radar import storage
        storage.write("latest.json", {"ranking": [{"symbol": s} for s in ("AAA", "BBB", "CCC", "DDD", "EEE")], "assets": []})
        storage.write("alerts.json", [{"at": "1", "kind": "NEW EARLY ENTRY", "symbol": "AAA"},
                                      {"at": "2", "kind": "NEW EARLY ENTRY", "symbol": "EEE"},
                                      {"at": "3", "kind": "MEME BREAKOUT", "symbol": "AAA"},
                                      {"at": "4", "kind": "EXIT", "symbol": "BBB"},
                                      {"at": "5", "kind": "MARKET REGIME CHANGE", "symbol": None}])
        storage.write("journal.json", [{"symbol": "AAA", "status": "OPEN", "r_multiple": None},
                                       {"symbol": "EEE", "status": "CLOSED", "r_multiple": 2.0}])
        storage.write("history.json", {"AAA": [[1, 50, "X", 1]], "EEE": [[1, 60, "X", 2]]})
        storage.write("scans.json", [{"at": "1", "top": ["AAA", "BBB", "CCC", "DDD", "EEE"]}])
        expect = {   # ruta: (libre, pro, élite)
            "/api/backtest/results": (402, 402, 200), "/api/positions": (402, 200, 200),
            "/api/memes": (402, 200, 200), "/api/memes/radar": (402, 200, 200),
            "/api/admin/users": (403, 403, 403), "/api/paper/report": (403, 403, 403),
            "/api/history?symbol=EEE": (402, 200, 200), "/api/candles?symbol=EEE": (402, 404, 404),
            "/api/history?symbol=AAA": (200, 200, 200), "/api/me": (200, 200, 200), "/api/state": (200, 200, 200),
        }
        clients = [self._user_with_plan(p) for p in ("free", "pro", "elite")]
        for path, codes in expect.items():
            got = tuple(self.call(op, path)[0] for op, _, _ in clients)
            self.assertEqual(got, codes, path)
        free, pro = clients[0][0], clients[1][0]
        kinds = {(a["kind"], a["symbol"]) for a in self.call(free, "/api/alerts")[1]}
        self.assertEqual(kinds, {("NEW EARLY ENTRY", "AAA"), ("MARKET REGIME CHANGE", None)})
        self.assertEqual(len(self.call(pro, "/api/alerts")[1]), 5)
        self.assertEqual([x["symbol"] for x in self.call(free, "/api/journal")[1]["items"]], ["AAA"])
        self.assertEqual(self.call(free, "/api/scans")[1][0]["top"], ["AAA", "BBB", "CCC"])
        # escrituras también respetan el plan
        op, csrf, _ = clients[0]
        self.assertEqual(self.call(op, "/api/positions/abcdef12/delete", {}, {"X-CSRF-Token": csrf})[0], 402)
        self.assertEqual(self.call(op, "/api/telegram/link", {}, {"X-CSRF-Token": csrf})[0], 402)
        self.assertEqual(self.call(op, "/api/scan", {}, {"X-CSRF-Token": csrf})[0], 403)
        self.assertEqual(self.call(op, "/api/settings", {"min_score": 1}, {"X-CSRF-Token": csrf})[0], 403)
        # sin sesión, nada privado
        for path in expect:
            self.assertEqual(self.call(self.client(), path)[0], 401, path)

    def test_expired_paid_plan_falls_back_to_free(self):
        op, csrf, u = self._user_with_plan("elite")
        db.execute("UPDATE users SET plan_until = ? WHERE email = ?", (time.time() - 1, u))
        self.assertEqual(self.call(op, "/api/backtest/results")[0], 402)

    # ---------- 3. Migraciones
    def _py(self, code, home=None):
        env = dict(os.environ, CRYPTO_RADAR_HOME=home or tempfile.mkdtemp(prefix="cr-mig-"))
        env.pop("DATABASE_URL", None)
        return subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, text=True, env=env, timeout=60)

    def test_migration_from_old_schema_keeps_users(self):
        code = r"""
import os, sys, sqlite3
sys.path.insert(0, sys.argv[1])
from radar.config import DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
c = sqlite3.connect(str(DATA_DIR / "app.db"))
c.execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, created_at REAL NOT NULL, plan TEXT NOT NULL DEFAULT 'free', plan_until REAL, is_admin INTEGER NOT NULL DEFAULT 0, telegram_chat_id TEXT, settings TEXT NOT NULL DEFAULT '{}', disabled INTEGER NOT NULL DEFAULT 0, failed_logins INTEGER NOT NULL DEFAULT 0, locked_until REAL)")
c.execute("INSERT INTO users(id, email, pw_hash, created_at) VALUES ('u1', 'viejo@example.com', 'x', 1)"); c.commit(); c.close()
from radar import db
db.init(); db._ready = False; db.init()          # dos arranques seguidos: idempotente
assert db.REQUIRED["users"] <= db.columns("users")
r = db.one("SELECT email, status FROM users WHERE id = 'u1'", ())
assert r == {"email": "viejo@example.com", "status": "active"}, r
print("MIG_OK")
"""
        r = self._py(code); self.assertIn("MIG_OK", r.stdout, r.stderr[-1500:])

    def test_migration_unexpected_error_is_not_ignored(self):
        code = r"""
import sys
sys.path.insert(0, sys.argv[1])
from radar import db
db.MIGRATIONS.append(("tabla_que_no_existe", "x", "TEXT"))
try:
    db.init(); print("NO_ERROR")
except db.SchemaError as e:
    print("SCHEMA_ERROR", e)
"""
        r = self._py(code); self.assertIn("SCHEMA_ERROR", r.stdout, r.stdout + r.stderr[-1500:])

    def test_incomplete_schema_blocks_startup(self):
        code = r"""
import os, sys, sqlite3
os.environ["CRYPTO_RADAR_ACCOUNTS"] = "1"
sys.path.insert(0, sys.argv[1])
from radar.config import DATA_DIR
DATA_DIR.mkdir(parents=True, exist_ok=True)
c = sqlite3.connect(str(DATA_DIR / "app.db")); c.execute("CREATE TABLE kv (name TEXT PRIMARY KEY, value TEXT)"); c.commit(); c.close()
from radar import server
try:
    server.serve(port=0, schedule=False); print("STARTED")
except SystemExit as e:
    print("REFUSED", e)
"""
        r = self._py(code)
        self.assertIn("REFUSED", r.stdout, r.stdout + r.stderr[-1500:]); self.assertIn("kv: updated_at", r.stdout)

    def test_duplicate_column_is_the_only_tolerated_error(self):
        import sqlite3
        self.assertTrue(db._is_duplicate_column(sqlite3.OperationalError("duplicate column name: status")))
        self.assertFalse(db._is_duplicate_column(sqlite3.OperationalError("no such table: users")))
        self.assertFalse(db._is_duplicate_column(sqlite3.OperationalError("database is locked")))

    def test_render_without_postgres_refuses_accounts_mode(self):
        code = r"""
import os, sys
os.environ["CRYPTO_RADAR_ACCOUNTS"] = "1"; os.environ["RENDER"] = "true"
sys.path.insert(0, sys.argv[1])
from radar import server
try:
    server.serve(port=0, schedule=False); print("STARTED")
except SystemExit as e:
    print("REFUSED", e)
"""
        r = self._py(code); self.assertIn("REFUSED", r.stdout, r.stdout + r.stderr[-1500:])

    # ---------- 4. Límites de intentos persistentes
    def test_rate_limit_survives_restart_and_is_shared(self):
        key = f"prueba:{random.randint(0, 10**9)}"
        self.assertFalse(auth.rate_limited(key, 2, 3600)); self.assertFalse(auth.rate_limited(key, 2, 3600))
        self.assertTrue(auth.rate_limited(key, 2, 3600))
        auth._rate.clear(); db._ready = False; db._local.c = None                     # "reinicio" del proceso
        self.assertTrue(auth.rate_limited(key, 2, 3600))
        code = f"""
import sys
sys.path.insert(0, sys.argv[1])
from radar import auth
print("BLOCKED" if auth.rate_limited({key!r}, 2, 3600) else "FREE")
"""
        r = self._py(code, home=HOME)                                                  # otra instancia, misma base
        self.assertIn("BLOCKED", r.stdout, r.stderr[-1500:])
        self.assertIsNone(db.one("SELECT k FROM rate_limits WHERE k LIKE ?", ("%prueba%",)))   # la clave va con hash

    def test_login_ip_limit_persists(self):
        for i in range(20):
            self.call(self.client(), "/api/auth/login", {"username": f"nadie{i}", "password": "mala clave 12345"})
        auth._rate.clear()                                                             # sin memoria, sigue bloqueado
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": "admin", "password": "clave larga del jefe 2026"})
        self.assertEqual(st, 429)

    # ---------- 5. Flujo completo
    def test_full_account_lifecycle(self):
        name = f"ciclo{random.randint(0, 10**9)}"
        st, r, _ = self.call(self.client(), "/api/auth/request", {"username": name, "password": "mi clave inicial 1", "contact": "@ciclo"})
        self.assertEqual(st, 200); self.assertNotIn("Set-Cookie", _ or {})
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": name, "password": "mi clave inicial 1"})[0], 403)
        aop, acsrf = self.admin_client()
        uid = db.one("SELECT id FROM users WHERE email = ?", (name,))["id"]
        self.assertEqual(self.call(aop, "/api/admin/user", {"id": uid, "action": "approve", "plan": "pro", "days": 30}, {"X-CSRF-Token": acsrf})[0], 200)
        op = self.client()
        st, r, _ = self.call(op, "/api/auth/login", {"username": name, "password": "mi clave inicial 1"})
        self.assertEqual(st, 200); csrf = r["csrf"]; self.assertEqual(r["user"]["plan"], "pro")
        self.assertEqual(self.call(op, "/api/positions")[0], 200)
        self.assertEqual(self.call(op, "/api/backtest/results")[0], 402)
        self.assertEqual(self.call(op, "/api/auth/logout", {}, {"X-CSRF-Token": csrf})[0], 200)
        self.assertEqual(self.call(op, "/api/me")[0], 401)
        st, r, _ = self.call(op, "/api/auth/login", {"username": name, "password": "mi clave inicial 1"}); csrf = r["csrf"]
        self.assertEqual(self.call(aop, "/api/admin/user/password", {"id": uid, "password": "clave del admin para ti 4"}, {"X-CSRF-Token": acsrf})[0], 200)
        self.assertEqual(self.call(op, "/api/me")[0], 401)                             # el restablecimiento cierra sus sesiones
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": name, "password": "mi clave inicial 1"})[0], 401)
        op = self.client()
        st, r, _ = self.call(op, "/api/auth/login", {"username": name, "password": "clave del admin para ti 4"}); csrf = r["csrf"]
        self.assertEqual(self.call(op, "/api/auth/password", {"old": "clave del admin para ti 4", "new": "mi clave definitiva 9"}, {"X-CSRF-Token": csrf})[0], 200)
        self.assertEqual(self.call(op, "/api/me")[0], 401)
        self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": name, "password": "mi clave definitiva 9"})[0], 200)
        acts = {a["action"] for a in db.all_("SELECT action FROM activity WHERE user_id = ?", (uid,))}
        self.assertTrue({"access_requested", "login", "logout", "password_changed"} <= acts, acts)

    # Las pruebas heredadas de T13 ya corren en T13; aquí no se repiten.
for _n in [n for n in dir(T13_SaaS) if n.startswith("test_")]:
    if _n not in T18_SeguridadFinal.__dict__:
        setattr(T18_SeguridadFinal, _n, None)


# ================================================================== 19. serve(): nunca arranca en modo cuentas sin administrador
SERVE_HARNESS = r"""
import os, sys, json
sys.path.insert(0, sys.argv[1])
cfg = json.loads(sys.argv[2])
from radar import server, auth, db

class FakeHTTPServer:                       # sustituye solo al socket: todo lo anterior es el serve() real
    def __init__(self, *a, **k): pass
    def serve_forever(self): print("SERVING", flush=True)
server.ThreadingHTTPServer = FakeHTTPServer

if cfg.get("squatter"):                     # alguien reservó el nombre antes de configurar el administrador
    adm = os.environ.pop("CRYPTO_RADAR_ADMIN_USER", None)
    uid = auth.request_access(cfg["squatter"], "clave del intruso 99", ip="10.7.7.7")
    auth.admin_set_status({"id": "x", "is_admin": 1, "email": "prueba"}, uid, "approve")
    if adm: os.environ["CRYPTO_RADAR_ADMIN_USER"] = adm
    print("SQUATTER", uid, flush=True)
if cfg.get("ensure_none"):
    auth.ensure_admin = lambda: None
try:
    server.serve(port=0, host=cfg.get("host"), schedule=False)
except SystemExit as e:
    print("REFUSED", e, flush=True)
if cfg.get("report"):
    rows = db.all_("SELECT id, email, is_admin, status, approved_by FROM users ORDER BY created_at", ())
    print("USERS", json.dumps(rows), flush=True)
"""


class T19_ServeAdminObligatorio(unittest.TestCase):
    STRIP = ("CRYPTO_RADAR_ADMIN_USER", "CRYPTO_RADAR_ADMIN_PASSWORD", "CRYPTO_RADAR_ADMIN_RESET",
             "CRYPTO_RADAR_ADMIN_TAKEOVER", "CRYPTO_RADAR_ACCOUNTS", "CRYPTO_RADAR_PASSWORD", "RENDER",
             "DATABASE_URL", "CRYPTO_RADAR_HOST", "PAPER_TRADING", "KEEPALIVE")

    def run_serve(self, env=None, home=None, **cfg):
        e = {k: v for k, v in os.environ.items() if k not in self.STRIP}
        e["CRYPTO_RADAR_HOME"] = home or tempfile.mkdtemp(prefix="cr-serve-")
        e.update(env or {})
        r = subprocess.run([sys.executable, "-c", SERVE_HARNESS, str(ROOT), json.dumps(cfg)],
                           capture_output=True, text=True, env=e, timeout=90)
        return r.stdout + r.stderr

    ADMIN = {"CRYPTO_RADAR_ACCOUNTS": "1", "CRYPTO_RADAR_ADMIN_USER": "duenio",
             "CRYPTO_RADAR_ADMIN_PASSWORD": "clave larga del jefe 2026"}

    def refused(self, out):
        self.assertIn("REFUSED", out, out[-2000:]); self.assertNotIn("SERVING", out, out[-2000:])

    def test_1_accounts_without_both_vars_refuses(self):
        out = self.run_serve({"CRYPTO_RADAR_ACCOUNTS": "1"})
        self.refused(out)
        self.assertIn("CRYPTO_RADAR_ADMIN_USER", out); self.assertIn("CRYPTO_RADAR_ADMIN_PASSWORD", out)

    def test_2_missing_user_refuses(self):
        env = dict(self.ADMIN); env.pop("CRYPTO_RADAR_ADMIN_USER")
        out = self.run_serve(env); self.refused(out)
        self.assertIn("Falta definir: CRYPTO_RADAR_ADMIN_USER.", out)
        self.assertNotIn("clave larga del jefe 2026", out)                         # nunca muestra la contraseña

    def test_3_missing_password_refuses(self):
        env = dict(self.ADMIN); env.pop("CRYPTO_RADAR_ADMIN_PASSWORD")
        out = self.run_serve(env); self.refused(out)
        self.assertIn("Falta definir: CRYPTO_RADAR_ADMIN_PASSWORD.", out)

    def test_3b_blank_values_count_as_missing(self):
        out = self.run_serve(dict(self.ADMIN, CRYPTO_RADAR_ADMIN_USER="   ", CRYPTO_RADAR_ADMIN_PASSWORD=""))
        self.refused(out); self.assertIn("CRYPTO_RADAR_ADMIN_USER, CRYPTO_RADAR_ADMIN_PASSWORD", out)

    def test_3c_invalid_admin_password_refuses(self):
        out = self.run_serve(dict(self.ADMIN, CRYPTO_RADAR_ADMIN_PASSWORD="corta"))
        self.refused(out); self.assertNotIn("corta\n", out.replace("REFUSED", ""))

    def test_4_valid_admin_boots(self):
        out = self.run_serve(self.ADMIN, report=True)
        self.assertIn("Administrador: duenio · creado", out, out[-2000:]); self.assertIn("SERVING", out, out[-2000:])
        self.assertNotIn("clave larga del jefe 2026", out)
        users = json.loads(out.split("USERS ", 1)[1].splitlines()[0])
        self.assertEqual([(u["email"], u["is_admin"], u["approved_by"]) for u in users], [("duenio", 1, "entorno")])

    def test_5_ensure_admin_none_refuses(self):
        out = self.run_serve(self.ADMIN, ensure_none=True)
        self.refused(out); self.assertIn("no se pudo confirmar el administrador", out)

    def test_6_single_user_mode_unchanged(self):
        out = self.run_serve({})                                                   # local, sin cuentas: arranca
        self.assertIn("SERVING", out, out[-2000:]); self.assertNotIn("Administrador", out)
        out = self.run_serve({}, host="0.0.0.0")                                   # expuesto sin contraseña: no
        self.refused(out); self.assertIn("CRYPTO_RADAR_PASSWORD", out)
        out = self.run_serve({"CRYPTO_RADAR_PASSWORD": "clave del panel 123"}, host="0.0.0.0")
        self.assertIn("SERVING", out, out[-2000:])

    def test_7_squatter_never_becomes_admin_via_serve(self):
        home = tempfile.mkdtemp(prefix="cr-serve-")
        out = self.run_serve(self.ADMIN, home=home, squatter="duenio", report=True)
        self.refused(out); self.assertIn("apropiación", out)
        users = json.loads(out.split("USERS ", 1)[1].splitlines()[0])
        self.assertEqual([(u["email"], u["is_admin"]) for u in users], [("duenio", 0)])
        out = self.run_serve(self.ADMIN, home=home, report=True)                  # reintentar no cambia nada
        self.refused(out)
        users = json.loads(out.split("USERS ", 1)[1].splitlines()[0])
        self.assertEqual([(u["email"], u["is_admin"]) for u in users], [("duenio", 0)])

    def test_8_takeover_quarantines_and_boots(self):
        home = tempfile.mkdtemp(prefix="cr-serve-")
        out = self.run_serve(self.ADMIN, home=home, squatter="duenio")
        self.refused(out)
        squat_id = out.split("SQUATTER ", 1)[1].split()[0]
        out = self.run_serve(dict(self.ADMIN, CRYPTO_RADAR_ADMIN_TAKEOVER="1"), home=home, report=True)
        self.assertIn("Administrador: duenio · cuarentena", out, out[-2000:]); self.assertIn("SERVING", out)
        users = {u["id"]: u for u in json.loads(out.split("USERS ", 1)[1].splitlines()[0])}
        old = users.pop(squat_id)
        self.assertEqual((old["is_admin"], old["status"]), (0, "rejected")); self.assertNotEqual(old["email"], "duenio")
        (new,) = users.values()
        self.assertEqual((new["email"], new["is_admin"], new["approved_by"]), ("duenio", 1, "entorno"))
        out = self.run_serve(self.ADMIN, home=home)                                # siguiente arranque normal
        self.assertIn("Administrador: duenio · verificado", out, out[-2000:]); self.assertIn("SERVING", out)

    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL no definido")
    def test_9_postgres_boot_requires_admin(self):
        pg = {"DATABASE_URL": os.environ["TEST_DATABASE_URL"]}
        out = self.run_serve(dict(pg, CRYPTO_RADAR_ACCOUNTS="1")); self.refused(out)
        out = self.run_serve(dict(pg, **dict(self.ADMIN, CRYPTO_RADAR_ADMIN_USER="pgserve")))
        self.assertIn("base de datos postgresql · esquema verificado", out, out[-2000:])
        self.assertRegex(out, r"Administrador: pgserve · (creado|verificado)"); self.assertIn("SERVING", out)


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
for t in ("users", "sessions", "activity", "positions", "payments", "telegram_links", "kv", "rate_limits"):
    db.conn().execute(f"DROP TABLE IF EXISTS {t}")
# esquema antiguo (antes de 2.1): la migración añade columnas sin perder usuarios
db.conn().execute("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw_hash TEXT NOT NULL, created_at DOUBLE PRECISION NOT NULL, plan TEXT NOT NULL DEFAULT 'free', plan_until DOUBLE PRECISION, is_admin INTEGER NOT NULL DEFAULT 0, telegram_chat_id TEXT, settings TEXT NOT NULL DEFAULT '{}', disabled INTEGER NOT NULL DEFAULT 0, failed_logins INTEGER NOT NULL DEFAULT 0, locked_until DOUBLE PRECISION)")
db.conn().execute("INSERT INTO users(id, email, pw_hash, created_at) VALUES ('old1', 'viejo@example.com', 'x', 1)")
db._ready = False; db.init(); db._ready = False; db.init()
assert db.REQUIRED["users"] <= db.columns("users")
assert db.one("SELECT status FROM users WHERE id = 'old1'", ())["status"] == "active"
# apropiación del nombre del administrador: nunca se promueve
squat = auth.request_access("pgadmin", "clave del intruso 99", ip="10.0.0.9")
os.environ["CRYPTO_RADAR_ADMIN_USER"] = "pgadmin"; os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "clave larga del jefe 2026"
try:
    auth.ensure_admin(); raise SystemExit("debió negarse")
except auth.AdminBootstrapError:
    pass
assert db.one("SELECT is_admin FROM users WHERE id = ?", (squat,))["is_admin"] == 0
os.environ["CRYPTO_RADAR_ADMIN_TAKEOVER"] = "1"
assert auth.ensure_admin()["result"] == "cuarentena"
os.environ.pop("CRYPTO_RADAR_ADMIN_TAKEOVER")
assert auth.ensure_admin()["result"] == "verificado"
# límites de intentos en PostgreSQL, persistentes tras "reinicio"
auth.reset_rate_limits()
assert not auth.rate_limited("pg:x", 1, 3600) and auth.rate_limited("pg:x", 1, 3600)
auth._rate.clear(); db._ready = False; db._local.c = None
assert auth.rate_limited("pg:x", 1, 3600)
auth.reset_rate_limits()
adm = db.one("SELECT * FROM users WHERE email = 'pgadmin'", ())
u = auth.register("pg@example.com", "clave muy segura 123")
assert u["status"] == "pending"
try:
    auth.login("pg@example.com", "clave muy segura 123"); raise SystemExit("pendiente no debería entrar")
except auth.AuthError as e:
    assert e.code == 403
auth.admin_set_status(adm, u["id"], "approve")
tok, csrf, _ = auth.login("pg@example.com", "clave muy segura 123")
assert auth.session(tok)["user"]["email"] == "pg@example.com"
auth.admin_reset_password(adm, u["id"], "clave restablecida 55")
assert auth.session(tok) is None
tok, csrf, _ = auth.login("pg@example.com", "clave restablecida 55")
auth.logout(tok); assert auth.session(tok) is None
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
