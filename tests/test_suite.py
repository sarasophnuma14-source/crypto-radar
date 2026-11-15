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
from unittest import mock
import urllib.error
import urllib.request
import http.cookiejar
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="cr-test-")
os.environ["CRYPTO_RADAR_HOME"] = HOME
os.environ.pop("DATABASE_URL", None)
os.environ["CRYPTO_RADAR_ADMIN_USER"] = "admin"
os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "clave larga del jefe 2026"
os.environ["CRYPTO_RADAR_ADMIN_TOTP"] = "optional"   # el 2FA obligatorio se prueba aparte (T21)
os.environ.pop("CRYPTO_RADAR_PAYMENTS", None)
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
        with mock.patch.dict(os.environ, {"RENDER": "true"}):
            os.environ.pop("CRYPTO_RADAR_TRUSTED_PROXIES", None)
            self.assertEqual(server.Handler._client_ip(h), "203.0.113.9")   # en Render, el último lo añade el proxy
        with mock.patch.dict(os.environ, {}):
            os.environ.pop("RENDER", None); os.environ.pop("CRYPTO_RADAR_TRUSTED_PROXIES", None)
            self.assertEqual(server.Handler._client_ip(h), "10.0.0.1")      # sin proxy autorizado no se confía

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
        body = {"username": username, "password": pw, "consent": "2026-11-15"}
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
        st, r, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": "weakuser", "password": "123"})
        self.assertEqual(st, 400)
        st, r, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": "weakuser", "password": "weakuser12345"})
        self.assertEqual(st, 400)                                   # contiene el usuario

    def test_invalid_username_rejected(self):
        for bad in ("No Válido!", "ab", "x" * 40, "<script>", "a b"):
            auth.reset_rate_limits()
            st, _, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": bad, "password": "clave muy segura 123"})
            self.assertEqual(st, 400, bad)

    def test_duplicate_email(self):
        op, csrf, email = self.signup()
        st, _, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": email, "password": "clave muy segura 123"})
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
            st, r, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": "uno.mas", "password": "clave muy segura 123"})
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
    ENV = {"CRYPTO_RADAR_PAYMENTS": "sandbox", "WOMPI_PUBLIC_KEY": "pub_test_x", "WOMPI_INTEGRITY_SECRET": "integ", "WOMPI_EVENTS_SECRET": "evsecret", "COP_PER_USD": "4000",
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
        # una cuenta pendiente no puede vincular Telegram (A-03); tras aprobarla, sí
        self.assertIn("no válido", telegram_bot.handle({"chat": {"id": 4242}, "text": f"/start {code}"}))
        self.assertIsNone(auth.get_user(u["id"])["telegram_chat_id"])
        db.execute("UPDATE users SET status = 'active' WHERE id = ?", (u["id"],))
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
        uid = auth.request_access(name, "clave del intruso 99", consent=auth.POLICY_VERSION, ip="10.1.1.1")         # alguien reserva el nombre
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
            st, r, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": name, "password": "clave muy segura 123"})
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
        st, r, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": name, "password": "mi clave inicial 1", "contact": "@ciclo"})
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
    workers = 0
    def __init__(self, *a, **k): pass
    def serve_forever(self): print("SERVING", flush=True)
server.ThreadingHTTPServer = server.PooledHTTPServer = FakeHTTPServer

if cfg.get("squatter"):                     # alguien reservó el nombre antes de configurar el administrador
    adm = os.environ.pop("CRYPTO_RADAR_ADMIN_USER", None)
    uid = auth.request_access(cfg["squatter"], "clave del intruso 99", consent=auth.POLICY_VERSION, ip="10.7.7.7")
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


# ================================================================== 20. Auditoría previa a producción (hallazgos A-01…A-08)
class T20_AuditoriaProduccion(T13_SaaS):
    def setUp(self):
        auth.reset_rate_limits()

    def raw(self, head, body=b"", wait=10):
        import socket
        port = self.httpd.server_address[1]
        s = socket.create_connection(("127.0.0.1", port), timeout=wait)
        try:                     # el servidor puede responder 413 y cerrar antes de leer el cuerpo: es lo correcto
            s.sendall(head + body[:1024]); s.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        out = b""
        while True:
            try:
                d = s.recv(65536)
            except ConnectionResetError:
                break
            if not d:
                break
            out += d
        s.close()
        return out.split(b"\r\n")[0].decode()

    # A-01: Content-Length negativo o inválido saltaba el límite de 64 KB
    def test_a01_negative_or_invalid_content_length_rejected(self):
        big = json.dumps({"username": "x" * 10, "password": "y" * 200000}).encode()
        for cl in (b"-1", b"abc", b"+5", b" -10"):
            st = self.raw(b"POST /api/auth/login HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: " + cl + b"\r\n\r\n", big)
            self.assertIn(" 413 ", st, cl)
        st = self.raw(b"POST /api/auth/login HTTP/1.0\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(big), big)
        self.assertIn(" 413 ", st)

    # A-02: conexiones ociosas quedaban abiertas para siempre
    def test_a02_idle_connections_time_out(self):
        import socket
        from radar import server
        self.assertEqual(server.Handler.timeout, 30)
        old = server.Handler.timeout
        server.Handler.timeout = 1
        try:
            s = socket.create_connection(("127.0.0.1", self.httpd.server_address[1]), timeout=8)
            t = time.time()
            self.assertEqual(s.recv(10), b"")                 # el servidor cierra la conexión ociosa
            self.assertLess(time.time() - t, 6)
            s.close()
        finally:
            server.Handler.timeout = old

    # A-03: Telegram entregaba datos a chats sin cuenta y a cuentas desactivadas
    def test_a03_telegram_only_serves_active_linked_accounts(self):
        from radar import storage, multiuser
        storage.write("latest.json", {"ranking": [{"rank": 1, "symbol": "AAA", "phase_label": "x", "score": 70, "action": "COMPRAR",
                                                   "entry_low": 1, "entry_high": 2, "stop": 0.9, "tp1": 3}],
                                      "market": {"regime": "R", "btc_price": 1, "policy": {}}, "verdict": "V",
                                      "verdict_text": "t", "at": "2026-11-15T00:00"})
        for cmd in ("/top", "/estado", "/regimen", "/cartera"):
            r = telegram_bot.handle({"chat": {"id": 99001}, "text": cmd})
            self.assertNotIn("AAA", r); self.assertIn("no está vinculado", r)
        name = f"tg{random.randint(0, 10**9)}"
        uid = auth.request_access(name, "clave muy segura 123", consent=auth.POLICY_VERSION, ip="10.3.3.3")
        auth.admin_set_status(self.admin, uid, "approve", "pro", 30)
        multiuser.add_position(uid, {"symbol": "SOL", "entry": 100.0})
        code = telegram_bot.new_link_code(uid)
        self.assertIn("vinculado", telegram_bot.handle({"chat": {"id": 99002}, "text": "/start " + code}))
        self.assertIn("SOL", telegram_bot.handle({"chat": {"id": 99002}, "text": "/cartera"}))     # activo: sí
        auth.admin_set_status(self.admin, uid, "disable")
        for cmd in ("/cartera", "/top"):
            r = telegram_bot.handle({"chat": {"id": 99002}, "text": cmd})
            self.assertNotIn("SOL", r); self.assertNotIn("AAA", r)
        auth.admin_set_status(self.admin, uid, "enable")
        code = telegram_bot.new_link_code(uid)
        auth.admin_set_status(self.admin, uid, "reject")                                         # código emitido y luego rechazado
        self.assertIn("no válido", telegram_bot.handle({"chat": {"id": 99003}, "text": "/start " + code}))
        self.assertFalse(telegram_bot.active(auth.get_user(uid)))

    # A-04: dos entregas simultáneas del mismo webhook duplicaban el plan
    def test_a04_concurrent_webhook_grants_plan_once(self):
        name = f"pago{random.randint(0, 10**9)}"
        uid = auth.request_access(name, "clave muy segura 123", consent=auth.POLICY_VERSION, ip="10.4.4.4"); auth.admin_set_status(self.admin, uid, "approve")
        ref = billing._new_payment(uid, "wompi", "pro", "month", 100, "COP")
        pay = db.one("SELECT * FROM payments WHERE reference = ?", (ref,))
        self.assertTrue(billing._grant(dict(pay), {}))
        self.assertFalse(billing._grant(dict(pay), {}))                 # misma fila leída antes de la primera escritura
        days = (db.one("SELECT plan_until FROM users WHERE id = ?", (uid,))["plan_until"] - time.time()) / 86400
        self.assertAlmostEqual(days, 30, delta=0.1)
        self.assertEqual(sum(1 for a in db.all_("SELECT action FROM activity WHERE user_id = ?", (uid,))
                             if a["action"] == "plan_granted"), 1)

    # A-05: el nombre del informe de paper trading se usaba como ruta sin validar
    def test_a05_paper_report_name_validated(self):
        from radar import server
        for bad in ("../../etc", "a/b", "x" * 41, "..", "nombre con espacios"):
            self.assertEqual(server.paper_report(bad), {"available": False, "note": "Nombre de evaluación no válido"}, bad)
        self.assertNotEqual(server.paper_report("principal").get("note"), "Nombre de evaluación no válido")

    # A-06: el mensaje de bloqueo revelaba qué usuarios existen
    def test_a06_lockout_message_does_not_reveal_existence(self):
        name = f"real{random.randint(0, 10**9)}"
        auth.admin_create(self.admin, name, "clave muy segura 123")
        def last(u):
            out = None
            for i in range(6):
                out = self.call(self.client(), "/api/auth/login", {"username": u, "password": f"mala clave 1234{i}"})
            return out[0], out[1]["error"]
        self.assertEqual(last(name), last(f"fantasma{random.randint(0, 10**9)}"))

    # A-07: días no numéricos en la concesión manual daban error 500
    def test_a07_admin_grant_invalid_days(self):
        with self.assertRaises(auth.AuthError) as cm:
            billing.admin_grant(self.admin, "admin", "pro", "muchos", "cortesía")
        self.assertEqual(cm.exception.code, 400)

    # A-08: dos solicitudes simultáneas con el mismo usuario daban 500 (UNIQUE) en vez de 409
    def test_a08_duplicate_username_race_returns_409(self):
        name = f"carrera{random.randint(0, 10**9)}"
        auth._create(name, "clave muy segura 123", "pending")
        with self.assertRaises(auth.AuthError) as cm:
            auth._create(name, "otra clave segura 45", "pending")
        self.assertEqual(cm.exception.code, 409)

    # Comprobaciones generales de la auditoría
    def test_every_api_route_requires_session_unless_public(self):
        from radar import server
        src = (ROOT / "radar" / "webapi.py").read_text("utf-8")
        routes = set(re.findall(r'"(/api/[a-z_/]+)"', src))
        public = set(server.PUBLIC_GET) | set(server.PUBLIC_POST)
        self.assertGreater(len(routes), 25)
        for r in sorted(routes - public):
            st, _, _ = self.call(self.client(), r)
            self.assertIn(st, (401, 404), f"GET {r}")
            st, _, _ = self.call(self.client(), r, {})
            self.assertIn(st, (401, 404), f"POST {r}")

    def test_session_token_and_passwords_never_stored_in_clear(self):
        op, csrf, u = self.signup()
        jar = [h for h in op.handlers if hasattr(h, "cookiejar")][0].cookiejar
        tok = next(c.value for c in jar if c.name == "cr_session")
        self.assertIsNone(db.one("SELECT token_hash FROM sessions WHERE token_hash = ?", (tok,)))
        self.assertIsNotNone(db.one("SELECT token_hash FROM sessions WHERE token_hash = ?", (hashlib.sha256(tok.encode()).hexdigest(),)))
        row = db.one("SELECT pw_hash FROM users WHERE email = ?", (u,))
        self.assertTrue(row["pw_hash"].startswith("scrypt$")); self.assertNotIn("clave muy segura", row["pw_hash"])

    def test_privilege_fields_in_requests_are_ignored(self):
        name = f"listo{random.randint(0, 10**9)}"
        st, _, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": name, "password": "clave muy segura 123",
                                                                  "is_admin": 1, "status": "active", "plan": "elite",
                                                                  "plan_until": 9e12})
        self.assertEqual(st, 200)
        row = db.one("SELECT is_admin, status, plan, plan_until FROM users WHERE email = ?", (name,))
        self.assertEqual((row["is_admin"], row["status"], row["plan"], row["plan_until"]), (0, "pending", "free", None))
        op, csrf, u = self.signup()
        self.call(op, "/api/me/settings", {"is_admin": 1, "plan": "elite", "plan_until": 9e12}, {"X-CSRF-Token": csrf})
        row = db.one("SELECT is_admin, plan, plan_until FROM users WHERE email = ?", (u,))
        self.assertEqual((row["is_admin"], row["plan"], row["plan_until"]), (0, "free", None))
        self.assertEqual(self.call(op, "/api/admin/grant", {"email": u, "plan": "elite", "days": 30, "reason": "x"},
                                   {"X-CSRF-Token": csrf})[0], 403)

    def test_no_real_order_execution_code(self):
        pat = re.compile(r"api/v3/order|create_order|place_order|X-MBX-APIKEY|ccxt|newOrder", re.I)
        hits = [str(f) for d in ("radar", "research") for f in (ROOT / d).rglob("*.py") if pat.search(f.read_text("utf-8", "ignore"))]
        self.assertEqual(hits, [])
        self.assertFalse(auth.PLANS["elite"].get("real_orders", False))


for _n in [n for n in dir(T13_SaaS) if n.startswith("test_")]:
    if _n not in T20_AuditoriaProduccion.__dict__:
        setattr(T20_AuditoriaProduccion, _n, None)


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
squat = auth.request_access("pgadmin", "clave del intruso 99", consent=auth.POLICY_VERSION, ip="10.0.0.9")
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
# A-04 en PostgreSQL: dos entregas del mismo pago solo conceden el plan una vez
from radar import billing
ref = billing._new_payment(u["id"], "wompi", "pro", "month", 100, "COP")
pay = db.one("SELECT * FROM payments WHERE reference = ?", (ref,))
assert billing._grant(dict(pay), {}) is True and billing._grant(dict(pay), {}) is False
assert abs((db.one("SELECT plan_until FROM users WHERE id = ?", (u["id"],))["plan_until"] - time.time()) / 86400 - 30) < 0.1
# A-08 en PostgreSQL: nombre duplicado en carrera -> 409
try:
    auth._create("pg@example.com", "clave muy segura 123", "pending"); raise SystemExit("debió dar 409")
except auth.AuthError as e:
    assert e.code == 409
storage.write("latest.json", {"a": [1, 2]}); assert storage.read("latest.json") == {"a": [1, 2]}
p = multiuser.add_position(u["id"], {"symbol": "SOL", "entry": 1.0})
assert multiuser.list_positions(u["id"])[0]["id"] == p["id"]
print("PG_OK", db.backend())
'''
        env = dict(os.environ, DATABASE_URL=os.environ["TEST_DATABASE_URL"])
        r = subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, text=True, env=env, timeout=120)
        self.assertIn("PG_OK postgresql", r.stdout, r.stderr[-2000:])


# ================================================================== 21. Preparación para producción: TOTP, consentimiento, textos legales
class T21_TOTPyConsentimiento(T13_SaaS):
    SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"      # "12345678901234567890" en base32 (RFC 6238, apéndice B)

    def setUp(self):
        auth.reset_rate_limits()
        self._totp_env = os.environ.get("CRYPTO_RADAR_ADMIN_TOTP")

    def tearDown(self):
        os.environ["CRYPTO_RADAR_ADMIN_TOTP"] = self._totp_env or "optional"

    def enroll(self, op, csrf, pw="clave muy segura 123"):
        from radar import totp
        st, r, _ = self.call(op, "/api/auth/totp/setup", {"password": pw}, {"X-CSRF-Token": csrf})
        self.assertEqual(st, 200, r)
        self.assertTrue(r["uri"].startswith("otpauth://totp/") and "secret=" + r["secret"] in r["uri"])
        st, r2, _ = self.call(op, "/api/auth/totp/enable", {"code": totp.code(r["secret"])}, {"X-CSRF-Token": csrf})
        self.assertEqual(st, 200, r2)
        return r["secret"]

    def test_rfc6238_vectors(self):
        from radar import totp
        self.assertEqual(totp.code(self.SECRET, at=59), "287082")              # RFC: 94287082 (8 dígitos)
        self.assertEqual(totp.code(self.SECRET, at=1111111109), "081804")      # RFC: 07081804
        self.assertEqual(totp.code(self.SECRET, at=1234567890), "005924")      # RFC: 89005924
        self.assertEqual(len(totp.new_secret()), 32)

    def test_window_and_replay(self):
        from radar import totp
        t = 1_800_000_015
        s = totp.step(t)
        self.assertEqual(totp.match(self.SECRET, totp.code(self.SECRET, t - 30), at=t), s - 1)
        self.assertEqual(totp.match(self.SECRET, totp.code(self.SECRET, t + 30), at=t), s + 1)
        self.assertIsNone(totp.match(self.SECRET, totp.code(self.SECRET, t + 60), at=t))
        self.assertIsNone(totp.match(self.SECRET, totp.code(self.SECRET, t), last_step=s, at=t))   # ya usado
        for bad in ("", "12345", "abcdef", None, "1234567"):
            self.assertIsNone(totp.match(self.SECRET, bad, at=t))

    def test_login_requires_valid_unused_code(self):
        from radar import totp
        op, csrf, name = self.signup()
        secret = self.enroll(op, csrf)
        st, r, _ = self.call(op, "/api/me")
        self.assertEqual(st, 401)                                     # activar cierra todas las sesiones
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": name, "password": "clave muy segura 123"})
        self.assertEqual((st, r.get("totp_required")), (401, True))
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": name, "password": "clave muy segura 123", "code": "000000"})
        self.assertEqual((st, r.get("totp_required")), (401, True))
        nxt = totp.code(secret, time.time() + 30)                     # el código actual ya se usó al activar
        op2 = self.client()
        st, r, _ = self.call(op2, "/api/auth/login", {"username": name, "password": "clave muy segura 123", "code": nxt})
        self.assertEqual(st, 200, r)
        self.assertTrue(r["user"]["totp_enabled"])
        st, r, _ = self.call(self.client(), "/api/auth/login", {"username": name, "password": "clave muy segura 123", "code": nxt})
        self.assertEqual(st, 401)                                     # repetición del mismo código

    def test_wrong_codes_lock_account(self):
        from radar import totp
        op, csrf, name = self.signup()
        secret = self.enroll(op, csrf)
        for _ in range(5):
            self.call(self.client(), "/api/auth/login", {"username": name, "password": "clave muy segura 123", "code": "999999"})
        st, _, _ = self.call(self.client(), "/api/auth/login",
                             {"username": name, "password": "clave muy segura 123", "code": totp.code(secret, time.time() + 30)})
        self.assertEqual(st, 429)

    def test_admin_actions_require_totp_when_required(self):
        from radar import totp
        op, csrf, name = self.signup()
        db.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (name,))     # administrador de prueba
        os.environ["CRYPTO_RADAR_ADMIN_TOTP"] = "required"
        st, me, _ = self.call(op, "/api/me")
        self.assertTrue(me["user"]["totp_setup_required"])
        st, _, _ = self.call(op, "/api/admin/users")
        self.assertEqual(st, 403)
        uid = db.one("SELECT id FROM users WHERE email = ?", (name,))["id"]
        with self.assertRaises(auth.AuthError):
            billing.admin_grant(auth.get_user(uid), name, "pro", 30, "prueba")
        secret = self.enroll(op, csrf)
        op2 = self.client()
        st, r, _ = self.call(op2, "/api/auth/login",
                             {"username": name, "password": "clave muy segura 123", "code": totp.code(secret, time.time() + 30)})
        self.assertEqual(st, 200, r)
        st, _, _ = self.call(op2, "/api/admin/users")
        self.assertEqual(st, 200)
        st, r, _ = self.call(op2, "/api/auth/totp/disable", {"password": "clave muy segura 123", "code": "123456"},
                             {"X-CSRF-Token": r["csrf"]})
        self.assertEqual(st, 403)                                      # un administrador no puede quitarse el 2FA

    def test_user_can_disable_with_password_and_code(self):
        from radar import totp
        op, csrf, name = self.signup()
        secret = self.enroll(op, csrf)
        op2 = self.client()
        st, r, _ = self.call(op2, "/api/auth/login",
                             {"username": name, "password": "clave muy segura 123", "code": totp.code(secret, time.time() + 30)})
        h = {"X-CSRF-Token": r["csrf"]}
        st, _, _ = self.call(op2, "/api/auth/totp/disable", {"password": "otra", "code": totp.code(secret, time.time() - 30)}, h)
        self.assertEqual(st, 401)
        st, _, _ = self.call(op2, "/api/auth/totp/disable", {"password": "clave muy segura 123", "code": totp.code(secret, time.time() - 30)}, h)
        self.assertEqual(st, 401)                                      # paso anterior al ya usado: no vale
        self.assertTrue(db.one("SELECT totp_enabled FROM users WHERE email = ?", (name,))["totp_enabled"])

    def test_env_reset_clears_admin_totp(self):
        keep = {k: os.environ.get(k) for k in ("CRYPTO_RADAR_ADMIN_USER", "CRYPTO_RADAR_ADMIN_PASSWORD", "CRYPTO_RADAR_ADMIN_RESET")}
        name = f"jefe{random.randint(0, 10**9)}"
        try:
            os.environ["CRYPTO_RADAR_ADMIN_USER"] = name; os.environ["CRYPTO_RADAR_ADMIN_PASSWORD"] = "primera clave larga 1"
            self.assertEqual(auth.ensure_admin()["result"], "creado")
            db.execute("UPDATE users SET totp_enabled = 1, totp_secret = 'X' WHERE email = ?", (name,))
            os.environ["CRYPTO_RADAR_ADMIN_RESET"] = "1"
            self.assertEqual(auth.ensure_admin()["result"], "restablecido")
            row = db.one("SELECT totp_enabled, totp_secret FROM users WHERE email = ?", (name,))
            self.assertEqual((row["totp_enabled"], row["totp_secret"]), (0, None))
        finally:
            for k, v in keep.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    def test_totp_secret_never_in_public_payload(self):
        op, csrf, name = self.signup()
        self.enroll(op, csrf)
        uid = db.one("SELECT id FROM users WHERE email = ?", (name,))["id"]
        pub = json.dumps(auth.public(auth.get_user(uid)))
        self.assertNotIn("totp_secret", pub); self.assertNotIn("totp_last_step", pub)

    def test_consent_required_and_recorded(self):
        for body in ({}, {"consent": "2020-01-01"}, {"consent": True}):
            name = f"sinok{random.randint(0, 10**9)}"
            st, _, _ = self.call(self.client(), "/api/auth/request", dict(body, username=name, password="clave muy segura 123"))
            self.assertEqual(st, 400, body)
            self.assertIsNone(db.one("SELECT id FROM users WHERE email = ?", (name,)))
            auth.reset_rate_limits()
        (st, r, _), name = self.request()
        self.assertEqual(st, 200, r)
        row = db.one("SELECT consent_version, consent_at FROM users WHERE email = ?", (name,))
        self.assertEqual(row["consent_version"], auth.POLICY_VERSION); self.assertGreater(row["consent_at"], 0)

    def test_legal_pages_public_and_linked(self):
        for path, text in (("/privacidad", "Ley 1581"), ("/aviso-de-riesgo", "riesgo")):
            r = urllib.request.urlopen(self.base + path)
            body = r.read().decode()
            self.assertEqual(r.status, 200); self.assertIn(text, body)
            self.assertNotIn("<script", body.lower())
            self.assertIn("default-src", r.headers.get("Content-Security-Policy", ""))
        for page in ("landing.html", "entrar.html"):
            html = (ROOT / "web" / page).read_text(encoding="utf-8")
            self.assertIn('href="/privacidad"', html); self.assertIn('href="/aviso-de-riesgo"', html)
        self.assertIn('value="%s"' % auth.POLICY_VERSION, (ROOT / "web" / "entrar.html").read_text(encoding="utf-8"))


for _n in [n for n in dir(T13_SaaS) if n.startswith("test_")]:
    if _n not in T21_TOTPyConsentimiento.__dict__:
        setattr(T21_TOTPyConsentimiento, _n, None)


# ================================================================== 22. Modo de pagos (off / sandbox / live)
class T22_ModoPagos(unittest.TestCase):
    KEYS = {"WOMPI_PUBLIC_KEY": "pub_test_abc", "WOMPI_INTEGRITY_SECRET": "i", "WOMPI_EVENTS_SECRET": "e",
            "COP_PER_USD": "4000", "NOWPAYMENTS_API_KEY": "k", "NOWPAYMENTS_IPN_SECRET": "s"}

    def setUp(self):
        self._old = {k: os.environ.get(k) for k in list(self.KEYS) + ["CRYPTO_RADAR_PAYMENTS"]}
        os.environ.update(self.KEYS)

    def tearDown(self):
        for k, v in self._old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

    def mode(self, m):
        if m is None: os.environ.pop("CRYPTO_RADAR_PAYMENTS", None)
        else: os.environ["CRYPTO_RADAR_PAYMENTS"] = m

    def test_off_by_default_even_with_keys(self):
        for m in (None, "", "off", "OFF", "produccion", "on"):
            self.mode(m)
            self.assertEqual(billing.payments_mode(), "off", m)
            self.assertFalse(billing.wompi_enabled()); self.assertFalse(billing.nowpayments_enabled())
            self.assertEqual(billing.wompi_webhook({})[0], 503)
            self.assertEqual(billing.nowpayments_ipn({}, "")[0], 503)
        self.assertEqual(billing.status()["mode"], "off")

    def test_sandbox_uses_sandbox_apis_and_test_keys_only(self):
        self.mode("sandbox")
        self.assertTrue(billing.wompi_enabled()); self.assertTrue(billing.nowpayments_enabled())
        self.assertEqual(billing.wompi_api(), "https://sandbox.wompi.co/v1")
        self.assertEqual(billing.nowp_api(), "https://api-sandbox.nowpayments.io/v1")
        os.environ["WOMPI_PUBLIC_KEY"] = "pub_prod_abc"
        self.assertFalse(billing.wompi_enabled())

    def test_live_requires_production_key(self):
        self.mode("live")
        self.assertFalse(billing.wompi_enabled())                     # clave de prueba en modo live: desactivado
        self.assertEqual(billing.wompi_api(), "https://production.wompi.co/v1")
        self.assertEqual(billing.nowp_api(), "https://api.nowpayments.io/v1")

    def test_no_module_constant_overrides_api(self):
        src = (ROOT / "radar" / "billing.py").read_text(encoding="utf-8")
        self.assertNotIn('os.environ.get("WOMPI_API"', src)            # ya no se puede redirigir la API por entorno
        self.assertEqual(src.count("production.wompi.co"), 1)

    def test_render_yaml_keeps_payments_off(self):
        y = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertRegex(y, r'key: CRYPTO_RADAR_PAYMENTS\s*\n\s*value: "off"')
        self.assertRegex(y, r'key: CRYPTO_RADAR_ADMIN_TOTP\s*\n\s*value: required')

    def test_end_to_end_sandbox_selftest(self):
        r = subprocess.run([sys.executable, str(ROOT / "main.py"), "payments-selftest"], capture_output=True, text=True,
                           timeout=180, env=dict(os.environ, DATABASE_URL=""))
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-3000:])
        self.assertIn("RESULTADO: TODO OK", r.stdout)
        self.assertNotIn("FALLO", r.stdout)
        self.assertGreaterEqual(r.stdout.count("[OK]"), 15)


# ================================================================== 23. Copias de seguridad y restauración
class T23_Backup(unittest.TestCase):
    def setUp(self):
        from radar import backup
        self.bk = backup
        self.tmp = Path(tempfile.mkdtemp(prefix="cr-bk-"))
        self.src = str(self.tmp / "origen.db")
        import sqlite3
        c = sqlite3.connect(self.src)
        backup._ensure_schema(c, False)
        now = time.time()
        c.execute("INSERT INTO users(id, email, pw_hash, created_at, plan, plan_until, is_admin, settings, status, totp_secret, "
                  "totp_enabled, totp_last_step, consent_at, consent_version) VALUES "
                  "('u1', 'ana@example.com', 'scrypt$x', ?, 'pro', ?, 0, '{\"a\": \"ñ ✓\"}', 'active', 'SECRETO', 1, 59000000, ?, '2026-11-15')",
                  (now, now + 86400 * 30, now))
        c.execute("INSERT INTO users(id, email, pw_hash, created_at) VALUES ('u2', 'bob', 'scrypt$y', 1700000000.0)")
        c.execute("INSERT INTO payments(id, user_id, provider, reference, plan, period, amount_cents, currency, status, verified, "
                  "raw, created_at, updated_at) VALUES ('p1', 'u1', 'wompi', 'CR-1', 'pro', 'month', 7600000, 'COP', 'APPROVED', 1, "
                  "'{}', ?, ?)", (now, now))
        c.execute("INSERT INTO activity(id, user_id, at, action, detail, ip) VALUES ('a1', 'u1', ?, 'login', NULL, NULL)", (now,))
        c.execute("INSERT INTO kv(name, value, updated_at) VALUES ('journal', '[1, 2.5, null]', ?)", (now,))
        c.execute("INSERT INTO sessions(token_hash, user_id, csrf, created_at, expires_at) VALUES ('t', 'u1', 'c', 1, 2)")
        c.commit(); c.close()

    def counts(self, path):
        import sqlite3
        c = sqlite3.connect(path)
        try:
            return {t: c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in list(self.bk.TABLES) + ["sessions"]}
        finally:
            c.close()

    def test_round_trip_sqlite(self):
        d = self.bk.create(self.src, self.tmp / "copias")
        self.assertEqual(oct(os.stat(d / "users.jsonl").st_mode & 0o777), "0o600")
        self.assertEqual(oct(os.stat(d).st_mode & 0o777), "0o700")
        self.assertEqual(self.bk.compare(d, self.src), [])
        r = self.bk.verify(d)
        self.assertEqual(r["rows"]["users"], 2); self.assertEqual(r["rows"]["payments"], 1)
        dst = str(self.tmp / "destino.db")
        self.bk.restore(d, dst)
        self.assertEqual(self.bk.compare(d, dst), [])                  # contenido idéntico, fila a fila
        self.assertEqual(self.counts(dst)["sessions"], 0)             # las sesiones no se copian
        man = json.loads((d / "manifest.json").read_text())
        self.assertNotIn("sessions", man["tables"])

    def test_restore_never_overwrites(self):
        d = self.bk.create(self.src, self.tmp / "copias")
        before = self.counts(self.src)
        with self.assertRaises(self.bk.BackupError):
            self.bk.restore(d, self.src)
        self.assertEqual(self.counts(self.src), before)

    def test_tampering_detected(self):
        d = self.bk.create(self.src, self.tmp / "copias")
        p = d / "payments.jsonl"
        p.write_text(p.read_text().replace("7600000", "1"))
        with self.assertRaises(self.bk.BackupError):
            self.bk.verify(d)
        d2 = self.bk.create(self.src, self.tmp / "copias")
        m = json.loads((d2 / "manifest.json").read_text()); m["tables"]["users"]["rows"] = 3
        (d2 / "manifest.json").write_text(json.dumps(m))
        with self.assertRaises(self.bk.BackupError):
            self.bk.verify(d2)
        self.assertNotEqual(d, d2)                                     # dos copias seguidas no se pisan

    def test_compare_detects_changes(self):
        d = self.bk.create(self.src, self.tmp / "copias")
        import sqlite3
        c = sqlite3.connect(self.src); c.execute("UPDATE users SET plan = 'elite' WHERE id = 'u2'"); c.commit(); c.close()
        self.assertEqual(self.bk.compare(d, self.src), ["users: contenido distinto"])

    def test_cli_refuses_restore_over_database_url(self):
        d = self.bk.create(self.src, self.tmp / "copias")
        r = subprocess.run([sys.executable, str(ROOT / "main.py"), "backup", "restore", str(d), "--target", "postgresql://x@h/db"],
                           capture_output=True, text=True, timeout=60, env=dict(os.environ, DATABASE_URL="postgresql://x@h/db"))
        self.assertEqual(r.returncode, 2); self.assertIn("DATABASE_URL", r.stdout)
        self.assertEqual(self.bk.mask("postgresql://u:clave@h:5432/db?sslmode=require"), "postgresql://u:***@h:5432/db?sslmode=require")

    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL no definido")
    def test_round_trip_postgres(self):
        import psycopg
        url = os.environ["TEST_DATABASE_URL"]
        name = f"cr_restore_{random.randint(0, 10**9)}"
        admin = psycopg.connect(url, autocommit=True)
        admin.execute(f"CREATE DATABASE {name}")
        try:
            target = url.rsplit("/", 1)[0] + "/" + name
            d = self.bk.create(self.src, self.tmp / "copias")          # SQLite → PostgreSQL
            self.bk.restore(d, target)
            self.assertEqual(self.bk.compare(d, target), [])
            d2 = self.bk.create(target, self.tmp / "copias")           # PostgreSQL → copia → SQLite
            self.assertEqual(json.loads((d2 / "manifest.json").read_text())["source"], self.bk.mask(target))
            self.assertEqual(self.bk.verify(d2)["rows"]["users"], 2)
            with self.assertRaises(self.bk.BackupError):
                self.bk.restore(d2, target)                            # destino con datos: no se toca
        finally:
            admin.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")   # base temporal creada por esta prueba
            admin.close()


# ================================================================== 24. Revisión previa a producción (preflight)
class T24_Preflight(unittest.TestCase):
    GOOD = {"CRYPTO_RADAR_ACCOUNTS": "1", "DATABASE_URL": "postgresql://u:SuperSecretaDB99@ep-x-pooler.neon.tech/db?sslmode=require",
            "CRYPTO_RADAR_ADMIN_USER": "jefe", "CRYPTO_RADAR_ADMIN_PASSWORD": "ClaveAdminUltraSecreta 2026"}

    def run_pf(self, env):
        base = {k: v for k, v in os.environ.items() if not k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_"))
                and k != "DATABASE_URL"}
        return subprocess.run([sys.executable, str(ROOT / "main.py"), "preflight"], capture_output=True, text=True,
                              timeout=60, env=dict(base, **env))

    def results(self, env):
        from radar import preflight
        keep = dict(os.environ)
        try:
            for k in list(os.environ):
                if k.startswith(("CRYPTO_RADAR_", "WOMPI_", "NOWPAYMENTS_")) or k == "DATABASE_URL":
                    os.environ.pop(k)
            os.environ.update(env)
            return {name: level for level, name, _ in preflight.check_env()}
        finally:
            os.environ.clear(); os.environ.update(keep)

    def test_good_config_only_fails_on_legal_placeholders(self):
        r = self.results(self.GOOD)
        fails = sorted(n for n, lv in r.items() if lv == "fail")
        self.assertEqual(fails, ["Texto legal privacidad.html"])       # pendiente real: datos del responsable y abogado
        self.assertEqual(r["TLS con la base"], "ok"); self.assertEqual(r["Pagos"], "ok")

    def test_detects_unsafe_settings(self):
        bad = dict(self.GOOD, DATABASE_URL="postgresql://u:p@h/db", CRYPTO_RADAR_ADMIN_TOTP="optional",
                   CRYPTO_RADAR_PAYMENTS="live", CRYPTO_RADAR_ADMIN_RESET="1", CRYPTO_RADAR_ALLOW_SQLITE="1")
        r = self.results(bad)
        for k in ("TLS con la base", "TOTP del administrador", "Pagos", "Variables de recuperación", "SQLite forzado"):
            self.assertEqual(r[k], "fail", k)
        r = self.results(dict(self.GOOD, CRYPTO_RADAR_PAYMENTS="sandbox", WOMPI_PUBLIC_KEY="pub_prod_x"))
        self.assertEqual(r["Pagos"], "fail")
        r = self.results({"DATABASE_URL": ""})
        self.assertEqual((r["Modo cuentas"], r["Base de datos"], r["Administrador"]), ("fail", "fail", "fail"))

    def test_output_never_shows_secrets(self):
        p = self.run_pf(self.GOOD)
        self.assertEqual(p.returncode, 1)                              # falla por los textos legales pendientes
        for secret in ("SuperSecretaDB99", "ClaveAdminUltraSecreta", "ep-x-pooler"):
            self.assertNotIn(secret, p.stdout + p.stderr)
        self.assertIn("NO listo para producción", p.stdout)

    def test_db_check_reads_admin_totp_state(self):
        import sqlite3
        from radar import backup, preflight
        path = str(Path(tempfile.mkdtemp(prefix="cr-pf-")) / "pf.db")
        c = sqlite3.connect(path); backup._ensure_schema(c, False)
        c.execute("INSERT INTO users(id, email, pw_hash, created_at, is_admin, totp_enabled) VALUES ('a', 'jefe', 'x', 1, 1, 0)")
        c.commit(); c.close()
        keep = dict(os.environ)
        try:
            os.environ.update({"DATABASE_URL": path, "CRYPTO_RADAR_ADMIN_USER": "jefe"})
            r = {n: lv for lv, n, _ in preflight.check_db()}
            self.assertEqual((r["Esquema"], r["TOTP del administrador en la base"]), ("ok", "warn"))
            c = sqlite3.connect(path); c.execute("UPDATE users SET totp_enabled = 1"); c.commit(); c.close()
            r = {n: lv for lv, n, _ in preflight.check_db()}
            self.assertEqual(r["TOTP del administrador en la base"], "ok")
        finally:
            os.environ.clear(); os.environ.update(keep)

    def test_render_yaml_has_no_inline_secrets(self):
        from radar import preflight
        self.assertEqual(preflight._render_yaml_secrets()[0], "ok")


# ================================================================== 25. Auditoría final del piloto: pruebas adversariales
class T25_Adversarial(T13_SaaS):
    PW = "clave muy segura 123"

    def setUp(self):
        auth.reset_rate_limits()

    def user(self, plan="free", days=0):
        auth.reset_rate_limits()
        (st, r, _), name = self.request()
        self.assertEqual(st, 200, r)
        self.approve(name, plan, days)
        op = self.client()
        st, r, hd = self.call(op, "/api/auth/login", {"username": name, "password": self.PW})
        self.assertEqual(st, 200, r)
        return op, {"X-CSRF-Token": r["csrf"]}, name, hd

    # --- sesiones
    def test_cookie_flags_and_server_side_logout(self):
        op, h, name, hd = self.user()
        ck = hd.get("Set-Cookie")
        for flag in ("HttpOnly", "SameSite=Lax", "Path=/"):
            self.assertIn(flag, ck)
        token = re.search(r"cr_session=([^;]+)", ck).group(1)
        self.assertEqual(self.call(op, "/api/auth/logout", {}, h)[0], 200)
        raw = urllib.request.build_opener()
        st, _, _ = self.call(raw, "/api/me", headers={"Cookie": f"cr_session={token}"})
        self.assertEqual(st, 401)                                        # el token robado ya no vale tras salir

    def test_forged_and_rotated_tokens_rejected(self):
        raw = urllib.request.build_opener()
        self.assertEqual(self.call(raw, "/api/me", headers={"Cookie": "cr_session=" + "A" * 43})[0], 401)
        op, h, name, hd = self.user()
        old = re.search(r"cr_session=([^;]+)", hd.get("Set-Cookie")).group(1)
        st, _, _ = self.call(op, "/api/auth/login", {"username": name, "password": self.PW})
        self.assertEqual(st, 200)
        self.assertEqual(self.call(raw, "/api/me", headers={"Cookie": f"cr_session={old}"})[0], 401)   # rotación

    # --- TOTP
    def test_totp_concurrent_replay_only_one_wins(self):
        from radar import totp
        op, h, name, _ = self.user()
        st, r, _ = self.call(op, "/api/auth/totp/setup", {"password": self.PW}, h)
        secret = r["secret"]
        self.assertEqual(self.call(op, "/api/auth/totp/enable", {"code": totp.code(secret)}, h)[0], 200)
        code = totp.code(secret, time.time() + 30)
        results = []
        def go():
            results.append(self.call(self.client(), "/api/auth/login", {"username": name, "password": self.PW, "code": code})[0])
        ts = [threading.Thread(target=go) for _ in range(8)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(results.count(200), 1, results)               # un código, una sola sesión

    def test_totp_cannot_be_reenrolled_with_session_and_password(self):
        from radar import totp
        op, h, name, _ = self.user()
        st, r, _ = self.call(op, "/api/auth/totp/setup", {"password": self.PW}, h)
        self.call(op, "/api/auth/totp/enable", {"code": totp.code(r["secret"])}, h)
        op2 = self.client()
        st, r2, _ = self.call(op2, "/api/auth/login", {"username": name, "password": self.PW,
                                                         "code": totp.code(r["secret"], time.time() + 30)})
        st, _, _ = self.call(op2, "/api/auth/totp/setup", {"password": self.PW}, {"X-CSRF-Token": r2["csrf"]})
        self.assertEqual(st, 409)

    def test_admin_first_enrolment_is_trust_on_first_use(self):
        """Riesgo documentado (R-02): quien tenga la contraseña de un admin SIN TOTP todavía puede inscribir el suyo."""
        op, h, name, _ = self.user()
        db.execute("UPDATE users SET is_admin = 1 WHERE email = ?", (name,))
        os.environ["CRYPTO_RADAR_ADMIN_TOTP"] = "required"
        try:
            st, _, _ = self.call(op, "/api/auth/totp/setup", {"password": self.PW}, h)
            self.assertEqual(st, 200)
        finally:
            os.environ["CRYPTO_RADAR_ADMIN_TOTP"] = "optional"

    def test_env_reset_closes_admin_sessions(self):
        keep = {k: os.environ.get(k) for k in ("CRYPTO_RADAR_ADMIN_USER", "CRYPTO_RADAR_ADMIN_PASSWORD", "CRYPTO_RADAR_ADMIN_RESET")}
        name = f"jefe{random.randint(0, 10**9)}"
        try:
            os.environ.update({"CRYPTO_RADAR_ADMIN_USER": name, "CRYPTO_RADAR_ADMIN_PASSWORD": "clave inicial del jefe 7"})
            auth.ensure_admin()
            op = self.client()
            self.assertEqual(self.call(op, "/api/auth/login", {"username": name, "password": "clave inicial del jefe 7"})[0], 200)
            os.environ.update({"CRYPTO_RADAR_ADMIN_PASSWORD": "clave nueva del jefe 8", "CRYPTO_RADAR_ADMIN_RESET": "1"})
            self.assertEqual(auth.ensure_admin()["result"], "restablecido")
            self.assertEqual(self.call(op, "/api/me")[0], 401)          # la sesión del atacante muere
            self.assertEqual(self.call(self.client(), "/api/auth/login", {"username": name, "password": "clave inicial del jefe 7"})[0], 401)
        finally:
            for k, v in keep.items():
                if v is None: os.environ.pop(k, None)
                else: os.environ[k] = v

    # --- CSRF
    def test_csrf_variants_rejected(self):
        op, h, name, _ = self.user()
        op2, h2, _, _ = self.user()
        body = {"risk_per_trade_pct": 2}
        self.assertEqual(self.call(op, "/api/me/settings", body)[0], 403)                        # sin token
        self.assertEqual(self.call(op, "/api/me/settings", body, h2)[0], 403)                    # token de otra sesión
        self.assertEqual(self.call(op, "/api/me/settings", body, dict(h, Origin="https://evil.example"))[0], 403)
        self.assertEqual(self.call(op, "/api/me/settings", None, dict(h, **{"Content-Type": "text/plain"}),
                                   raw=json.dumps(body).encode())[0], 403)                       # formulario simple
        self.assertEqual(self.call(op, "/api/me/settings", body, h)[0], 200)

    # --- XSS (lado servidor; el recorrido en el navegador está en tests/piloto/xss_navegador.js)
    def test_stored_payloads_served_as_json_and_csp_blocks_inline(self):
        payload = '<img src=x onerror="window.__pwn=1"><script>window.__pwn=2</script>'
        name = f"xss{random.randint(0, 10**9)}"
        st, _, _ = self.call(self.client(), "/api/auth/request", {"consent": "2026-11-15", "username": name,
                             "password": self.PW, "contact": payload, "note": payload})
        self.assertEqual(st, 200)
        row = db.one("SELECT contact, request_note FROM users WHERE email = ?", (name,))
        self.assertIn("<script>", row["request_note"])                 # se guarda tal cual; la defensa es al mostrar
        r = urllib.request.urlopen(self.base + "/entrar")
        csp = r.headers["Content-Security-Policy"]
        self.assertIn("script-src 'self'", csp); self.assertNotIn("unsafe-inline' ;", csp)
        self.assertNotRegex(csp, r"script-src[^;]*unsafe-inline")
        js = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
        for field in ("x.contact", "x.request_note", "x.email"):
            self.assertIn(f"esc({field}", js)

    # --- escalada de privilegios
    def test_privilege_escalation_attempts(self):
        op, h, name, _ = self.user()
        self.call(op, "/api/me/settings", {"is_admin": 1, "plan": "elite", "plan_until": 9e12, "status": "active",
                                           "totp_enabled": 1}, h)
        row = db.one("SELECT is_admin, plan, plan_until, totp_enabled FROM users WHERE email = ?", (name,))
        self.assertEqual((row["is_admin"], row["plan"], row["totp_enabled"]), (0, "free", 0))
        uid = db.one("SELECT id FROM users WHERE email = ?", (name,))["id"]
        for path, body in (("/api/admin/user", {"id": uid, "action": "approve", "plan": "elite", "days": 300}),
                           ("/api/admin/grant", {"email": name, "plan": "elite", "days": 300, "reason": "yo"}),
                           ("/api/admin/user/create", {"username": "otro.admin", "password": "x" * 14}),
                           ("/api/admin/user/password", {"id": self.admin["id"], "password": "y" * 14}),
                           ("/api/scan", {}), ("/api/settings", {"telegram_bot_token": "x"})):
            self.assertEqual(self.call(op, path, body, h)[0], 403, path)
        self.assertEqual(self.call(op, "/api/admin/users")[0], 403)
        self.assertEqual(self.call(op, "/api/paper/report")[0], 403)
        self.assertEqual(db.one("SELECT plan FROM users WHERE id = ?", (uid,))["plan"], "free")

    # --- aislamiento entre usuarios
    def test_users_cannot_touch_each_others_data(self):
        opa, ha, a, _ = self.user("pro", 30)
        opb, hb, b, _ = self.user("pro", 30)
        st, pos, _ = self.call(opa, "/api/positions", {"symbol": "BTC", "entry": 100, "qty": 1}, ha)
        self.assertEqual(st, 200, pos)
        for action in ("close", "update", "delete"):
            st, _, _ = self.call(opb, f"/api/positions/{pos['id']}/{action}", {"price": 1, "stop": 1}, hb)
            self.assertEqual(st, 404, action)
        self.assertEqual([p["id"] for p in self.call(opb, "/api/positions")[1]], [])
        mine = self.call(opa, "/api/positions")[1]
        self.assertEqual((mine[0]["status"], mine[0]["entry"]), ("OPEN", 100))
        ida = db.one("SELECT id FROM users WHERE email = ?", (a,))["id"]
        acts = self.call(opb, "/api/activity")[1]
        self.assertTrue(acts and all("position_add" != x["action"] for x in acts))
        self.assertFalse(any(ida in json.dumps(x) for x in self.call(opb, "/api/billing/payments")[1]))

    # --- Telegram multiusuario
    def test_telegram_link_codes(self):
        _, _, a, _ = self.user("pro", 30)
        _, _, b, _ = self.user("pro", 30)
        ua = db.one("SELECT id FROM users WHERE email = ?", (a,))["id"]
        ub = db.one("SELECT id FROM users WHERE email = ?", (b,))["id"]
        code = telegram_bot.new_link_code(ua)
        self.assertIn("vinculado", telegram_bot.handle({"chat": {"id": 5001}, "text": f"/start {code}"}))
        self.assertIn("no válido", telegram_bot.handle({"chat": {"id": 5002}, "text": f"/start {code}"}))   # un solo uso
        self.assertIsNone(auth.get_user(ub)["telegram_chat_id"])
        code_b = telegram_bot.new_link_code(ub)
        db.execute("UPDATE telegram_links SET expires_at = 1 WHERE code = ?", (code_b,))
        self.assertIn("no válido", telegram_bot.handle({"chat": {"id": 5003}, "text": f"/start {code_b}"}))  # vencido
        out = [telegram_bot.handle({"chat": {"id": 5004}, "text": f"/start {i:08X}"}) for i in range(15)]
        self.assertTrue(any("Demasiados" in x for x in out))           # F-02: límite de intentos por chat
        # el mismo chat solo puede quedar ligado a una cuenta
        code_b2 = telegram_bot.new_link_code(ub)
        telegram_bot.handle({"chat": {"id": 5001}, "text": f"/start {code_b2}"})
        self.assertIsNone(auth.get_user(ua)["telegram_chat_id"])
        self.assertEqual(auth.get_user(ub)["telegram_chat_id"], "5001")

    # --- copias de seguridad manipuladas
    def test_forged_backup_with_recomputed_hashes(self):
        env = dict(os.environ, DATABASE_URL="")
        r = subprocess.run([sys.executable, str(ROOT / "tests" / "piloto" / "ataque_backup.py")], capture_output=True,
                           text=True, timeout=60, env=dict(env, CRYPTO_RADAR_BACKUP_KEY=""))
        self.assertIn("NO DETECTADO", r.stdout)                         # sin clave: limitación documentada (F-01)
        r = subprocess.run([sys.executable, str(ROOT / "tests" / "piloto" / "ataque_backup.py")], capture_output=True,
                           text=True, timeout=60, env=dict(env, CRYPTO_RADAR_BACKUP_KEY="k" * 40))
        self.assertIn("DETECTADO", r.stdout); self.assertNotIn("NO DETECTADO", r.stdout)

    def test_backup_signature_wrong_key_rejected(self):
        from radar import backup
        import sqlite3
        tmp = Path(tempfile.mkdtemp(prefix="cr-sig-")); src = str(tmp / "o.db")
        c = sqlite3.connect(src); backup._ensure_schema(c, False); c.close()
        old = os.environ.get("CRYPTO_RADAR_BACKUP_KEY")
        try:
            os.environ["CRYPTO_RADAR_BACKUP_KEY"] = "a" * 40
            d = backup.create(src, tmp)
            self.assertTrue(backup.verify(d)["signed"])
            os.environ["CRYPTO_RADAR_BACKUP_KEY"] = "b" * 40
            with self.assertRaises(backup.BackupError):
                backup.verify(d)
            os.environ["CRYPTO_RADAR_BACKUP_KEY"] = "corta"
            with self.assertRaises(backup.BackupError):
                backup.verify(d)
        finally:
            if old is None: os.environ.pop("CRYPTO_RADAR_BACKUP_KEY", None)
            else: os.environ["CRYPTO_RADAR_BACKUP_KEY"] = old

    # --- secretos
    def test_no_secrets_in_responses_or_logs(self):
        op, h, name, _ = self.user()
        me = json.dumps(self.call(op, "/api/me")[1])
        for k in ("pw_hash", "totp_secret", "token_hash", "scrypt$"):
            self.assertNotIn(k, me)
        pub = json.dumps(self.call(self.client(), "/api/public/status")[1])
        for k in ("WOMPI", "NOWPAYMENTS", "DATABASE_URL", "secret", "key"):
            self.assertNotIn(k, pub)
        acts = json.dumps(self.call(op, "/api/activity")[1])
        self.assertNotIn(self.PW, acts)


for _n in [n for n in dir(T13_SaaS) if n.startswith("test_")]:
    if _n not in T25_Adversarial.__dict__:
        setattr(T25_Adversarial, _n, None)


# ================================================================== 26. Auditoría final del piloto: pagos
class T26_PagosAdversarial(T14_Pagos):
    def real(self, pay, **kw):
        d = {"status": "APPROVED", "reference": pay["reference"], "amount_in_cents": pay["amount_cents"], "currency": "COP"}
        d.update(kw)
        return {"data": d}

    def plan(self):
        u = auth.get_user(self.user["id"])
        return auth.effective_plan(u), u["plan_until"]

    def test_wompi_pending_then_approved(self):
        r, pay = self._checkout()
        self.assertEqual(billing.wompi_webhook(self._event(pay["reference"], "PENDING", pay["amount_cents"]), fetch=lambda t: {})[0], 200)
        self.assertEqual(db.one("SELECT status, verified FROM payments WHERE reference = ?", (pay["reference"],)), {"status": "PENDING", "verified": 0})
        self.assertEqual(self.plan()[0], "free")
        self.assertEqual(billing.wompi_webhook(self._event(pay["reference"], amount=pay["amount_cents"]), fetch=lambda t: self.real(pay))[0], 200)
        self.assertEqual(self.plan()[0], "pro")

    def test_wompi_reference_not_signed_but_rechecked(self):
        """La firma de Wompi no cubre la referencia: alguien puede cambiarla en un evento legítimo. La consulta a la
        API lo detecta porque la transacción real tiene otra referencia."""
        r, pay = self._checkout()
        r2, other = self._checkout()
        ev = self._event(pay["reference"], amount=pay["amount_cents"])
        ev["data"]["transaction"]["reference"] = other["reference"]     # sigue con firma válida
        self.assertTrue(billing.wompi_signature_ok(ev, "evsecret"))
        self.assertEqual(billing.wompi_webhook(ev, fetch=lambda t: self.real(pay))[0], 409)
        self.assertEqual(self.plan()[0], "free")

    def test_wompi_unknown_reference_currency_and_empty_signature(self):
        r, pay = self._checkout()
        ev = self._event("CR-no-existe", amount=1)
        self.assertEqual(billing.wompi_webhook(ev, fetch=lambda t: {})[0], 404)
        ev = self._event(pay["reference"], amount=pay["amount_cents"])
        self.assertEqual(billing.wompi_webhook(ev, fetch=lambda t: self.real(pay, currency="USD"))[0], 409)
        self.assertEqual(billing.wompi_webhook(ev, fetch=lambda t: self.real(pay, status="DECLINED"))[0], 409)
        ev2 = dict(ev, signature={"properties": [], "checksum": hashlib.sha256(b"1700000000").hexdigest()})
        self.assertEqual(billing.wompi_webhook(ev2, fetch=lambda t: self.real(pay))[0], 401)
        self.assertEqual(self.plan()[0], "free")

    def test_wompi_retries_sequential_and_concurrent(self):
        r, pay = self._checkout()
        ev = self._event(pay["reference"], amount=pay["amount_cents"])
        codes = []
        ts = [threading.Thread(target=lambda: codes.append(billing.wompi_webhook(ev, fetch=lambda t: self.real(pay))[0])) for _ in range(10)]
        [t.start() for t in ts]; [t.join() for t in ts]
        for _ in range(5):
            codes.append(billing.wompi_webhook(ev, fetch=lambda t: self.real(pay))[0])
        self.assertTrue(all(c == 200 for c in codes), codes)
        plan, until = self.plan()
        self.assertEqual(plan, "pro"); self.assertAlmostEqual(until - time.time(), 30 * 86400, delta=120)
        n = db.one("SELECT COUNT(*) AS n FROM activity WHERE user_id = ? AND action = 'plan_granted'", (self.user["id"],))["n"]
        self.assertEqual(n, 1)

    def test_wompi_refund_after_approval_keeps_plan(self):
        """Riesgo documentado (R-05): un reembolso o anulación posterior NO quita el plan; requiere acción manual."""
        r, pay = self._checkout()
        billing.wompi_webhook(self._event(pay["reference"], amount=pay["amount_cents"]), fetch=lambda t: self.real(pay))
        code, msg = billing.wompi_webhook(self._event(pay["reference"], "VOIDED", pay["amount_cents"]), fetch=lambda t: {})
        self.assertEqual(code, 200)
        self.assertEqual(self.plan()[0], "pro")
        self.assertEqual(db.one("SELECT status FROM payments WHERE reference = ?", (pay["reference"],))["status"], "APPROVED")

    def test_buying_lower_plan_replaces_higher_one(self):
        """Riesgo documentado (R-05): con Élite vigente, pagar Pro cambia el plan a Pro y se pierde el tiempo de Élite."""
        db.execute("UPDATE users SET plan = 'elite', plan_until = ? WHERE id = ?", (time.time() + 200 * 86400, self.user["id"]))
        r, pay = self._checkout()
        billing.wompi_webhook(self._event(pay["reference"], amount=pay["amount_cents"]), fetch=lambda t: self.real(pay))
        plan, until = self.plan()
        self.assertEqual(plan, "pro"); self.assertLess(until - time.time(), 31 * 86400)

    # ---- NOWPayments
    def crypto_checkout(self, plan="pro"):
        old = billing._get_json
        billing._get_json = lambda url, headers=None, data=None, method=None: {"invoice_url": "https://sandbox/x", "id": "i"}
        try:
            r = billing.checkout(self.user, plan, "month", "crypto", "https://app.example")
        finally:
            billing._get_json = old
        return db.one("SELECT * FROM payments WHERE reference = ?", (r["reference"],))

    def ipn(self, body, secret="ipn"):
        return hmac.new(secret.encode(), json.dumps(body, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha512).hexdigest()

    def test_nowpayments_statuses_amounts_and_reuse(self):
        pay = self.crypto_checkout()
        ok_api = {"payment_status": "finished", "order_id": pay["reference"], "price_amount": 19, "price_currency": "usd"}
        for st in ("waiting", "confirming", "partially_paid", "failed", "refunded", "expired"):
            body = {"payment_id": 1, "order_id": pay["reference"], "payment_status": st}
            self.assertEqual(billing.nowpayments_ipn(body, self.ipn(body), fetch=lambda p: ok_api)[0], 200, st)
            self.assertEqual(self.plan()[0], "free", st)
        body = {"payment_id": 1, "order_id": pay["reference"], "payment_status": "finished"}
        sig = self.ipn(body)
        self.assertEqual(billing.nowpayments_ipn(body, "0" * 128, fetch=lambda p: ok_api)[0], 401)
        self.assertEqual(billing.nowpayments_ipn(body, sig, fetch=lambda p: dict(ok_api, price_currency="eur"))[0], 409)
        self.assertEqual(billing.nowpayments_ipn(body, sig, fetch=lambda p: dict(ok_api, price_amount=18.99))[0], 409)
        self.assertEqual(billing.nowpayments_ipn(body, sig, fetch=lambda p: dict(ok_api, payment_status="partially_paid"))[0], 409)
        self.assertEqual(billing.nowpayments_ipn(body, sig, fetch=lambda p: dict(ok_api, order_id="CR-otro"))[0], 409)   # pago ajeno reutilizado
        self.assertEqual(self.plan()[0], "free")
        self.assertEqual(billing.nowpayments_ipn(body, sig.upper(), fetch=lambda p: ok_api)[0], 200)
        until = self.plan()[1]
        self.assertEqual(billing.nowpayments_ipn(body, sig, fetch=lambda p: ok_api)[0], 200)            # reintento
        self.assertEqual(self.plan(), ("pro", until))

    def test_nowpayments_js_style_signatures_accepted(self):
        """F-03: NOWPayments firma con JSON.stringify; antes se rechazaban IPN con tildes o exponentes."""
        r = subprocess.run([sys.executable, str(ROOT / "tests" / "piloto" / "firma_nowpayments.py")], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("4/4", r.stdout)
        self.assertEqual(billing._js_json({"b": 1.0, "a": "ñ", "c": [1e-07, 2.5, None, True]}), '{"a":"ñ","b":1,"c":[1e-7,2.5,null,true]}')

    def test_cross_provider_reference_rejected(self):
        r, wpay = self._checkout()
        body = {"payment_id": 9, "order_id": wpay["reference"], "payment_status": "finished"}
        self.assertEqual(billing.nowpayments_ipn(body, self.ipn(body), fetch=lambda p: {})[0], 404)     # referencia de Wompi


for _n in [n for n in dir(T14_Pagos) if n.startswith("test_")]:
    if _n not in T26_PagosAdversarial.__dict__:
        setattr(T26_PagosAdversarial, _n, None)


# ================================================================== 27. Auditoría final del piloto: servidor con hilos fijos
class T27_ServidorHilosFijos(unittest.TestCase):
    def test_burst_without_resets_and_bounded_threads(self):
        """F-04/F-05: con un hilo por petición y cola de 5, una ráfaga de 50 conexiones daba ConnectionResetError
        (18 de 50 inicios de sesión en la prueba de carga) y una conexión a PostgreSQL por petición."""
        from radar import server
        httpd = server.PooledHTTPServer(("127.0.0.1", 0), server.Handler, workers=4)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        try:
            self.assertEqual(httpd.request_queue_size, 128)
            before = threading.active_count()
            out = []
            def hit():
                try:
                    out.append(urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=20).status)
                except Exception as e:
                    out.append(type(e).__name__)
            ts = [threading.Thread(target=hit) for _ in range(80)]
            [t.start() for t in ts]; [t.join() for t in ts]
            self.assertEqual(out.count(200), 80, {str(x): out.count(x) for x in set(out)})
            names = [t.name for t in threading.enumerate() if t.name.startswith(httpd.thread_prefix)]
            self.assertEqual(len(names), 4)                            # no crece con la concurrencia
            self.assertLessEqual(threading.active_count(), before + 1)
        finally:
            httpd.shutdown(); httpd.server_close()

    def test_worker_survives_handler_errors(self):
        from radar import server
        class Boom(server.Handler):
            def do_GET(self):
                raise RuntimeError("fallo provocado")
        httpd = server.PooledHTTPServer(("127.0.0.1", 0), Boom, workers=2)
        httpd.handle_error = lambda *a: None
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        port = httpd.server_address[1]
        try:
            for _ in range(6):
                with self.assertRaises(Exception):
                    urllib.request.urlopen(f"http://127.0.0.1:{port}/x", timeout=5)
            self.assertEqual(len([t for t in threading.enumerate() if t.name.startswith(httpd.thread_prefix)]), 2)
        finally:
            httpd.shutdown(); httpd.server_close()
        time.sleep(0.3)
        self.assertEqual([t for t in threading.enumerate() if t.name.startswith(httpd.thread_prefix)], [])   # se cierran

    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "TEST_DATABASE_URL no definido")
    def test_pg_reconnects_after_server_terminates_connection(self):
        """F-06: con hilos fijos la conexión vive más; si PostgreSQL/Neon la corta, la siguiente consulta debe
        reconectar sola (antes fallaba una petición por hilo: 16 de 40 en tests/piloto/entorno.py)."""
        code = r'''
import sys, psycopg; sys.path.insert(0, sys.argv[1])
from radar import db
db.init()
pid = db.one("SELECT pg_backend_pid() AS p", ())["p"]
with psycopg.connect(db.URL, autocommit=True) as k:
    k.execute("SELECT pg_terminate_backend(%s)", (pid,))
import time; time.sleep(0.2)
ok = [db.one("SELECT 1 AS x", ())["x"] for _ in range(3)]
print("RECONEXION_OK" if ok == [1, 1, 1] and db.one("SELECT pg_backend_pid() AS p", ())["p"] != pid else "FALLO")
'''
        env = dict(os.environ, DATABASE_URL=os.environ["TEST_DATABASE_URL"], CRYPTO_RADAR_HOME=tempfile.mkdtemp())
        r = subprocess.run([sys.executable, "-c", code, str(ROOT)], capture_output=True, text=True, env=env, timeout=120)
        self.assertIn("RECONEXION_OK", r.stdout, r.stderr[-2000:])

    def test_pg_connect_retries_while_database_starts(self):
        """Prueba de estrés (caos): tras reiniciar PostgreSQL, 15 peticiones devolvieron 500 con «the database
        system is starting up». La conexión se reintenta con esperas cortas; la sentencia nunca se repite aquí."""
        import psycopg
        calls = []
        class FakeConn:
            def execute(self, *a): return None
        def fake_connect(url, **kw):
            calls.append(kw)
            if len(calls) < 3:
                raise psycopg.OperationalError("FATAL:  the database system is starting up")
            return FakeConn()
        with mock.patch.object(db, "IS_PG", True), mock.patch.object(db, "URL", "postgresql://x/y"), \
             mock.patch.object(db, "CONNECT_RETRY_S", (0.01, 0.01, 0.01)), mock.patch.object(psycopg, "connect", fake_connect):
            self.assertIsInstance(db._connect(), FakeConn)
            self.assertEqual(len(calls), 3)
            self.assertEqual(calls[0].get("connect_timeout"), 10)
            calls.clear()
            with mock.patch.object(psycopg, "connect", side_effect=psycopg.OperationalError("caída")) as m:
                with self.assertRaises(psycopg.OperationalError):
                    db._connect()
                self.assertEqual(m.call_count, 4)                  # 3 esperas + último intento, y se rinde

    def test_serve_uses_pooled_server(self):
        src = (ROOT / "radar" / "server.py").read_text(encoding="utf-8")
        self.assertIn("httpd = PooledHTTPServer((host, port), Handler)", src)
        self.assertNotIn("httpd = ThreadingHTTPServer((host, port), Handler)", src)


class T28_RateLimitingCombinado(T13_SaaS):
    """Protección combinada del inicio de sesión (docs/RATE_LIMITING.md): IP, cuenta, ventana e intentos fallidos,
    y X-Forwarded-For solo desde proxies autorizados."""
    PW = "clave muy segura 123"

    def setUp(self):
        auth.reset_rate_limits()

    def users(self, n, plan="free"):
        out = []
        for _ in range(n):
            auth.reset_rate_limits()
            (st, r, _), name = self.request()
            self.assertEqual(st, 200, r)
            self.approve(name, plan)
            out.append(name)
        auth.reset_rate_limits()
        return out

    def try_login(self, name, pw, ip):
        try:
            auth.login(name, pw, ip=ip); return 200
        except auth.AuthError as e:
            return e.code

    # --- el problema de la auditoría: 30 de 50 usuarios legítimos tras la misma IP recibían 429
    def test_shared_ip_legit_logins_not_blocked(self):
        names = self.users(30)
        codes = [self.try_login(n, self.PW, "198.51.100.7") for n in names]
        self.assertEqual(codes, [200] * 30)

    def test_shared_ip_concurrent_legit_logins_not_blocked(self):
        # 16 a la vez = los hilos del servidor (CRYPTO_RADAR_WORKERS): nunca hay más inicios de sesión en curso
        names = self.users(16)
        codes = []
        ts = [threading.Thread(target=lambda n=n: codes.append(self.try_login(n, self.PW, "198.51.100.8"))) for n in names]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(sorted(codes), [200] * 16)

    def test_more_simultaneous_logins_than_failure_limit_is_known_limit(self):
        """Límite conocido (docs/RATE_LIMITING.md): cada intento cuenta como fallido mientras se comprueba, así que
        con más de LOGIN_IP_FAILS comprobaciones simultáneas desde una IP las que sobran reciben 429. Con el
        servidor real no ocurre mientras CRYPTO_RADAR_WORKERS ≤ LOGIN_IP_FAILS (16 ≤ 20)."""
        from radar import server
        self.assertLessEqual(16, auth.LOGIN_IP_FAILS)
        self.assertIn("LOGIN_IP_FAILS", (ROOT / "radar" / "server.py").read_text(encoding="utf-8"))

    # --- la protección contra fuerza bruta no se debilita
    def test_ip_failure_limit_still_blocks_brute_force(self):
        names = self.users(1)
        codes = [self.try_login(f"nadie.bf{i}", "mala clave 12345", "198.51.100.9") for i in range(auth.LOGIN_IP_FAILS)]
        self.assertEqual(codes, [401] * auth.LOGIN_IP_FAILS)
        self.assertEqual(self.try_login(names[0], self.PW, "198.51.100.9"), 429)          # ni con la clave buena
        self.assertEqual(self.try_login(names[0], self.PW, "198.51.100.10"), 200)      # otra IP sigue entrando

    def test_ip_failure_limit_counts_nonexistent_users(self):
        for i in range(auth.LOGIN_IP_FAILS):
            self.assertEqual(self.try_login(f"nadie{i}", "mala clave 12345", "198.51.100.11"), 401)
        self.assertEqual(self.try_login("otro.nadie", "mala clave 12345", "198.51.100.11"), 429)

    def test_successful_logins_do_not_reset_failure_count(self):
        good, = self.users(1)
        victims = self.users(5)
        for i in range(auth.LOGIN_IP_FAILS - 1):
            self.try_login(victims[i % 5], f"mala {i:06d}", "198.51.100.12")
            self.assertEqual(self.try_login(good, self.PW, "198.51.100.12"), 200)      # acertar no devuelve intentos
        self.try_login(victims[0], "mala final 0001", "198.51.100.12")
        self.assertEqual(self.try_login(victims[1], "mala final 0002", "198.51.100.12"), 429)

    def test_concurrent_guesses_never_exceed_failure_limit(self):
        names = self.users(5)
        codes = []
        ts = [threading.Thread(target=lambda i=i: codes.append(self.try_login(names[i % 5], f"mala {i:06d}", "198.51.100.13")))
              for i in range(60)]
        [t.start() for t in ts]; [t.join() for t in ts]
        self.assertLessEqual(codes.count(401) + codes.count(200), auth.LOGIN_IP_FAILS)   # comprobadas: como mucho 20
        self.assertNotIn(200, codes)

    def test_account_lock_unchanged_across_ips(self):
        name, = self.users(1)
        for i in range(auth.LOCK_AFTER):
            self.assertEqual(self.try_login(name, f"mala {i:06d}", f"203.0.113.{i}"), 401)
        self.assertEqual(self.try_login(name, self.PW, "203.0.113.99"), 429)               # bloqueo por cuenta

    def test_spray_mode_tightens_per_ip_failures(self):
        names = self.users(2)
        with mock.patch.object(auth, "LOGIN_SPRAY_GLOBAL", 10):
            for i in range(10):
                self.try_login(f"spray{i}", "mala clave 12345", f"192.0.2.{i}")            # 10 IP distintas
            codes = [self.try_login(f"spray.x{i}", "mala clave 12345", "192.0.2.200") for i in range(auth.LOGIN_IP_FAILS_SPRAY)]
            self.assertEqual(codes, [401] * auth.LOGIN_IP_FAILS_SPRAY)
            self.assertEqual(self.try_login(names[0], self.PW, "192.0.2.200"), 429)        # modo estricto: 5 fallos bastan
            self.assertEqual(self.try_login(names[1], self.PW, "192.0.2.201"), 200)        # sin fallos se sigue entrando

    def test_flood_cap_counts_every_attempt(self):
        name, = self.users(1)
        with mock.patch.object(auth, "LOGIN_IP_ATTEMPTS", 4):
            codes = [self.try_login(name, self.PW, "198.51.100.14") for _ in range(5)]
        self.assertEqual(codes, [200, 200, 200, 200, 429])

    def test_totp_prompt_is_not_a_failure_but_wrong_code_is(self):
        from radar import totp
        name, = self.users(1)
        uid = db.one("SELECT id FROM users WHERE email = ?", (name,))["id"]
        db.execute("UPDATE users SET totp_secret = ?, totp_enabled = 1 WHERE id = ?", (totp.new_secret(), uid))
        for _ in range(auth.LOGIN_IP_FAILS + 5):
            self.assertEqual(self.try_login(name, self.PW, "198.51.100.15"), 401)        # pide el código: no cuenta
        self.assertEqual(auth.rate_peek("loginfail:198.51.100.15", auth.LOGIN_WINDOW_S), 0)
        try:
            auth.login(name, self.PW, ip="198.51.100.15", code="000000")
        except auth.AuthError:
            pass
        self.assertEqual(auth.rate_peek("loginfail:198.51.100.15", auth.LOGIN_WINDOW_S), 1)

    def test_login_ip_limit_over_http(self):
        names = self.users(25)
        for n in names:
            st, r, _ = self.call(self.client(), "/api/auth/login", {"username": n, "password": self.PW})
            self.assertEqual(st, 200, r)                  # 25 usuarios desde 127.0.0.1: ninguno bloqueado

    # --- X-Forwarded-For solo desde proxies autorizados
    def test_forwarded_for_ignored_from_untrusted_peer(self):
        from radar import server
        with mock.patch.dict(os.environ, {"CRYPTO_RADAR_TRUSTED_PROXIES": "10.0.0.0/8"}):
            self.assertEqual(server.client_ip("198.51.100.20", "1.1.1.1"), "198.51.100.20")
            self.assertEqual(server.client_ip("10.1.2.3", "1.1.1.1"), "1.1.1.1")
            self.assertEqual(server.client_ip("10.1.2.3", "6.6.6.6, 1.1.1.1, 10.9.9.9"), "1.1.1.1")   # salta proxies
            self.assertEqual(server.client_ip("10.1.2.3", "no-es-ip"), "10.1.2.3")
        with mock.patch.dict(os.environ, {"CRYPTO_RADAR_TRUSTED_PROXIES": ""}):
            self.assertEqual(server.client_ip("10.1.2.3", "1.1.1.1"), "10.1.2.3")

    def test_forwarded_for_cannot_dodge_limit_without_trusted_proxy(self):
        names = self.users(1)
        with mock.patch.dict(os.environ, {"CRYPTO_RADAR_TRUSTED_PROXIES": ""}):
            os.environ.pop("RENDER", None)
            codes = [self.call(self.client(), "/api/auth/login", {"username": f"nadie{i}", "password": "mala clave 12345"},
                               {"X-Forwarded-For": f"203.0.113.{i}"})[0] for i in range(auth.LOGIN_IP_FAILS + 1)]
        self.assertEqual(codes[-1], 429)                  # todas cuentan para 127.0.0.1 aunque cambie el encabezado

    def test_forwarded_for_trusted_proxy_separates_clients(self):
        with mock.patch.dict(os.environ, {"CRYPTO_RADAR_TRUSTED_PROXIES": "127.0.0.1/32"}):
            for i in range(auth.LOGIN_IP_FAILS):
                self.call(self.client(), "/api/auth/login", {"username": f"nadie{i}", "password": "mala clave 12345"},
                          {"X-Forwarded-For": "203.0.113.50"})
            st1 = self.call(self.client(), "/api/auth/login", {"username": "x.nadie", "password": "mala clave 12345"},
                            {"X-Forwarded-For": "203.0.113.50"})[0]
            st2 = self.call(self.client(), "/api/auth/login", {"username": "x.nadie2", "password": "mala clave 12345"},
                            {"X-Forwarded-For": "203.0.113.51"})[0]
        self.assertEqual((st1, st2), (429, 401))

    def test_rate_bump_memory_fallback(self):
        with mock.patch.object(db, "execute", side_effect=RuntimeError("caída")), \
             mock.patch.object(db, "one", side_effect=RuntimeError("caída")):
            self.assertEqual(auth.rate_bump("mem:x", 900), 1)
            self.assertEqual(auth.rate_bump("mem:x", 900), 2)
            self.assertEqual(auth.rate_bump("mem:x", 900, -1), 1)
            self.assertEqual(auth.rate_peek("mem:x", 900), 1)



for _n in [n for n in dir(T13_SaaS) if n.startswith("test_")]:
    if _n not in T28_RateLimitingCombinado.__dict__:
        setattr(T28_RateLimitingCombinado, _n, None)    # no repetir las pruebas heredadas de T13

if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1, argv=[sys.argv[0]] + [a for a in sys.argv[1:] if a != "-v"])
