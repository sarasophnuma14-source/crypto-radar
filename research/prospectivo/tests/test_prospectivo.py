"""Pruebas sin red del módulo prospectivo. Uso: python research/prospectivo/tests/test_prospectivo.py"""
import io, json, math, sys, tempfile, unittest, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from prospectivo import CORTE_PROSPECTIVO, PRUEBAS_PREVIAS  # noqa: E402
from prospectivo import registro as R, guardia as G, datos as D, costes as K, motor as MO  # noqa: E402
from prospectivo import metricas as M, validacion as V, diario as DI, clasificacion as CL  # noqa: E402


def reloj_fijo(ts):
    return lambda: ts


def hip(hid="H1", codigo="estrategia.py", **kw):
    h = {"id": hid, "linea": "momentum_intradia", "hipotesis": "x", "autor": "Claude", "datos": "binance 1h",
         "universo": "top10", "reglas_entrada": "a", "reglas_salida": "b", "parametros": {"L": [24, 48], "u": [0.0]},
         "modelo_costes": "taker binance_spot", "frecuencia": "1h", "metrica_principal": "sharpe_exceso_efectivo",
         "criterios": {}, "puntos_control_dias": [90, 183, 365], "codigo": codigo}
    h.update(kw); return h


def zip_csv(texto, nombre="x.csv"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(nombre, texto)
    return b.getvalue()


def mercado(n=400, activos=("BTC", "ETH", "SOL"), semilla=3, deriva=0.0, perps=(), seg=3600, vol=0.01):
    rng = np.random.default_rng(semilla)
    idx = pd.date_range("2026-11-16", periods=n, freq=f"{seg}s", tz="UTC")
    r = rng.normal(deriva, vol, (n, len(activos)))
    c = pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=idx, columns=list(activos))
    o = c.shift(1).fillna(100.0)
    nt = pd.DataFrame(1e9, index=idx, columns=list(activos))
    return MO.Mercado(open=o, close=c, notional=nt, segundos_barra=seg, perpetuos=tuple(perps))


class TestRegistro(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); (self.d / "estrategia.py").write_text("print(1)\n")
        self.reg = R.Registro(self.d / "registro.jsonl", root=self.d, reloj=reloj_fijo("2026-11-20T00:00:00+00:00"))

    def test_alta_y_campos(self):
        rec = self.reg.registrar(hip())
        self.assertEqual(rec["payload"]["n_pruebas"], 2)
        self.assertEqual(self.reg.hipotesis("H1")["inicio_prospectivo"], "2026-11-20T00:00:00+00:00")
        with self.assertRaises(R.RegistroError):
            self.reg.registrar(hip())                         # duplicada
        h = hip("H2"); del h["reglas_salida"]
        with self.assertRaises(R.RegistroError):
            self.reg.registrar(h)
        with self.assertRaises(R.RegistroError):
            self.reg.registrar(hip("H3", codigo="no_existe.py"))
        with self.assertRaises(R.RegistroError):
            self.reg.registrar(hip("H4", puntos_control_dias=[183, 90]))

    def test_cadena_detecta_manipulacion(self):
        self.reg.registrar(hip()); self.reg.mirar("H1", 90, {"x": 1})
        ls = self.reg.path.read_text().splitlines()
        j = json.loads(ls[0]); j["payload"]["parametros"] = {"L": [24]}
        self.reg.path.write_text("\n".join([json.dumps(j)] + ls[1:]) + "\n")
        with self.assertRaises(R.RegistroError):
            self.reg.verify()
        with self.assertRaises(R.RegistroError):
            self.reg.mirar("H1", 100, {})

    def test_borrar_linea_rompe_cadena(self):
        self.reg.registrar(hip()); self.reg.mirar("H1", 90, {}); self.reg.mirar("H1", 183, {})
        ls = self.reg.path.read_text().splitlines()
        self.reg.path.write_text("\n".join([ls[0], ls[2]]) + "\n")
        with self.assertRaises(R.RegistroError):
            self.reg.verify()

    def test_enmienda_reinicia_reloj_y_suma_pruebas(self):
        self.reg.registrar(hip())
        self.reg.reloj = reloj_fijo("2026-12-01T00:00:00+00:00")
        self.reg.enmendar("H1", {"parametros": {"L": [12, 24, 48]}}, "más horizontes")
        h = self.reg.hipotesis("H1")
        self.assertEqual(h["inicio_prospectivo"], "2026-12-01T00:00:00+00:00")
        self.assertEqual(h["n_pruebas_acumuladas"], 5); self.assertEqual(h["enmiendas"], 1)
        self.assertEqual(self.reg.total_pruebas(), PRUEBAS_PREVIAS + 5)

    def test_reloj_no_antes_del_corte(self):
        reg = R.Registro(self.d / "r2.jsonl", root=self.d, reloj=reloj_fijo("2026-01-01T00:00:00+00:00"))
        reg.registrar(hip())
        self.assertEqual(reg.hipotesis("H1")["inicio_prospectivo"], CORTE_PROSPECTIVO)

    def test_codigo_cambiado_sin_enmienda(self):
        self.reg.registrar(hip()); self.assertTrue(self.reg.comprobar_codigo("H1"))
        (self.d / "estrategia.py").write_text("print(2)\n")
        with self.assertRaises(R.RegistroError):
            self.reg.comprobar_codigo("H1")

    def test_cierre_unico(self):
        self.reg.registrar(hip()); self.reg.cerrar("H1", "RECHAZADA", ["x"])
        with self.assertRaises(R.RegistroError):
            self.reg.cerrar("H1", "APROBADA", [])
        with self.assertRaises(R.RegistroError):
            self.reg.enmendar("H1", {"universo": "top20"}, "x")
        with self.assertRaises(R.RegistroError):
            self.reg.cerrar("H9", "GANADORA", [])

    def test_rejilla_infinita(self):
        with self.assertRaises(R.RegistroError):
            R.n_pruebas({"L": "cualquiera"})
        self.assertEqual(R.n_pruebas({}), 1)


class TestGuardia(unittest.TestCase):
    def test_ventanas(self):
        self.assertIn("holdout_v3", G.ventana_consumida("2025-06-01", "2025-07-01"))
        self.assertEqual(G.ventana_consumida("2026-11-17", "2027-02-01"), [])

    def test_prospectivo(self):
        idx = pd.date_range("2026-11-10", periods=10, freq="D", tz="UTC")
        with self.assertRaises(G.GuardiaError):
            G.exigir_prospectivo(idx, "2026-11-20T00:00:00+00:00")
        df = pd.DataFrame({"x": range(10)}, index=idx)
        self.assertTrue(G.exigir_prospectivo(G.recortar_prospectivo(df, "2026-11-12").index, "2026-11-12"))

    def test_anticipacion(self):
        idx = pd.date_range("2026-01-01", periods=200, freq="h")
        df = pd.DataFrame({"c": np.random.default_rng(0).normal(size=200).cumsum()}, index=idx)
        self.assertTrue(G.prueba_anticipacion(lambda d: d["c"].rolling(10).mean(), df))
        with self.assertRaises(G.GuardiaError):
            G.prueba_anticipacion(lambda d: d["c"].shift(-1), df)                # mira el futuro
        with self.assertRaises(G.GuardiaError):
            G.prueba_anticipacion(lambda d: d["c"] - d["c"].mean(), df)           # media de toda la muestra

    def test_fugas(self):
        t = pd.Series(pd.to_datetime(["2026-11-20 10:00", "2026-11-20 11:00"], utc=True))
        self.assertTrue(G.comprobar_fugas(t - pd.Timedelta(seconds=1), t))
        with self.assertRaises(G.GuardiaError):
            G.comprobar_fugas(t + pd.Timedelta(seconds=1), t)

    def test_supervivencia(self):
        idx = pd.date_range("2026-01-01", periods=10, freq="D")
        U = pd.DataFrame({"A": True, "B": [False] * 5 + [True] * 5}, index=idx)
        self.assertTrue(G.comprobar_supervivencia(U, {"B": "2026-01-06"}))
        with self.assertRaises(G.GuardiaError):
            G.comprobar_supervivencia(U, {"B": "2026-01-08"})
        with self.assertRaises(G.GuardiaError):
            G.comprobar_supervivencia(U, {}, {"A": "2026-01-05"})               # elegible tras deslistado
        with self.assertRaises(G.GuardiaError):
            G.comprobar_supervivencia(U, {}, {"Z": "2026-01-05"})               # deslistado omitido


class TestDatos(unittest.TestCase):
    def test_url(self):
        self.assertEqual(D.url_binance("klines", "BTCUSDT", "2026-11-15", "1h"),
                         "https://data.binance.vision/data/spot/daily/klines/BTCUSDT/1h/BTCUSDT-1h-2026-11-15.zip")
        self.assertIn("futures/um/monthly/fundingRate", D.url_binance("fundingRate", "BTCUSDT", "2026-10", mercado="um",
                                                                      periodo="monthly"))
        with self.assertRaises(D.DatosError):
            D.url_binance("bookDepth", "BTCUSDT", "2026-11-15")

    def test_klines_ms_y_us(self):
        ms = 1763251200000
        f1 = f"{ms},100,110,90,105,10,{ms+3599999},1050,7,4,420,0\n"
        f2 = f"{ms*1000+3600*10**6},105,106,104,105.5,5,{ms*1000+7199999999},527,3,2,210,0\n"
        a = D.parse_klines_binance(zip_csv(f1), "BTCUSDT", "1h")
        b = D.parse_klines_binance(zip_csv(f2), "BTCUSDT", "1h")
        self.assertEqual(a.index[0], pd.Timestamp(ms, unit="ms", tz="UTC"))
        self.assertEqual(b.index[0] - a.index[0], pd.Timedelta(hours=1))
        self.assertEqual(a["available_at"].iloc[0], a.index[0] + pd.Timedelta(hours=1) + D.LATENCIA_PUBLICACION)
        self.assertEqual(a["taker_buy_volume"].iloc[0], 4.0)
        cab = "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
        self.assertEqual(len(D.parse_klines_binance(zip_csv(cab + f1), "BTCUSDT", "1h", "um")), 1)

    def test_aggtrades_y_ofi(self):
        t0 = 1763251200000
        txt = "".join(f"{i},{100+i*0.01},1,{i},{i},{t0+i*60000},{'True' if i % 4 == 0 else 'False'},True\n" for i in range(120))
        tr = D.parse_aggtrades_binance(zip_csv(txt))
        ofi = D.desequilibrio_flujo(tr, "1h")
        self.assertEqual(len(ofi), 2)
        self.assertTrue(0.4 < ofi["ofi"].iloc[0] < 0.6)                              # 75 % compra ⇒ ≈ 0,5
        self.assertTrue((ofi["available_at"] > ofi.index + pd.Timedelta("1h")).all())

    def test_funding_bookdepth_metrics(self):
        f = D.parse_funding_binance(zip_csv("calc_time,funding_interval_hours,last_funding_rate\n1763251200000,8,0.0001\n"), "BTCUSDT")
        self.assertAlmostEqual(f["funding"].iloc[0], 1e-4)
        bd = D.parse_bookdepth_binance(zip_csv("timestamp,percentage,depth,notional\n2026-11-15 00:00:08,-1,10,3000\n"
                                               "2026-11-15 00:00:08,1,5,1000\n"))
        self.assertAlmostEqual(bd["desequilibrio_1pct"].iloc[0], 0.5)
        mt = D.parse_metrics_binance(zip_csv("create_time,symbol,sum_open_interest,sum_open_interest_value\n"
                                             "2026-11-15 00:05:00,BTCUSDT,1000,9e7\n"))
        self.assertEqual(mt["sum_open_interest"].iloc[0], 1000)

    def test_otros_exchanges(self):
        cb = D.parse_coinbase(json.dumps([[1763254800, 99, 101, 100, 100.5, 3], [1763251200, 98, 100, 99, 100, 2]]), "BTC-USD", 3600)
        self.assertTrue(cb.index.is_monotonic_increasing); self.assertEqual(cb["open"].iloc[0], 99)
        kr = D.parse_kraken(json.dumps({"error": [], "result": {"XXBTZUSD": [
            [1763251200, "1", "2", "0.5", "1.5", "1.2", "10", 5], [1763254800, "1.5", "2", "1", "1.8", "1.6", "4", 2]],
            "last": 1763254800}}), "XBTUSD", 60)
        self.assertEqual(len(kr), 1)                                                     # barra en curso descartada
        ok = D.parse_okx(json.dumps({"code": "0", "data": [
            ["1763254800000", "2", "3", "1", "2.5", "10", "1", "25", "0"],
            ["1763251200000", "1", "2", "0.5", "2", "10", "1", "20", "1"]]}), "BTC-USDT", 3600)
        self.assertEqual(len(ok), 1)                                                     # no confirmada descartada
        with self.assertRaises(D.DatosError):
            D.parse_okx(json.dumps({"code": "50011", "msg": "rate"}), "BTC-USDT", 3600)

    def test_fred_y_libro(self):
        rf = D.parse_fred("observation_date,DTB3\n2026-11-02,4.00\n2026-11-03,.\n2026-11-04,3.65\n")
        self.assertEqual(rf.index[0], pd.Timestamp("2026-11-03"))                       # publicado con retraso
        self.assertAlmostEqual((1 + rf.iloc[0]) ** 365 - 1, 0.04, places=10)
        self.assertAlmostEqual(rf.loc["2026-11-04"], rf.loc["2026-11-03"])                # festivo: arrastra
        s = D.parse_depth_snapshot(json.dumps({"bids": [["99.9", "10"], ["99", "100"]], "asks": [["100.1", "5"], ["101", "100"]]}))
        self.assertAlmostEqual(s["spread_rel"], 0.002)
        self.assertGreater(s["desequilibrio_0.001"], 0)

    def test_universo_point_in_time(self):
        idx = pd.date_range("2026-01-01", periods=30, freq="D")
        a = pd.DataFrame({"close": 1.0, "volume": 1e6, "quote_volume": 1e6}, index=idx)
        b = a.copy(); b.iloc[:10] = np.nan                                               # listado el día 10
        c = a.copy(); c.iloc[20:] = np.nan                                               # deslistado el día 20
        U = D.universo_point_in_time({"A": a, "B": b, "C": c}, 5, 5e5, 5)
        self.assertFalse(U["B"].iloc[12]); self.assertTrue(U["B"].iloc[15])
        self.assertTrue(U["C"].iloc[19]); self.assertFalse(U["C"].iloc[25])
        self.assertTrue(G.comprobar_supervivencia(U, {"B": idx[10]}, {"C": idx[20]}))


class TestCostes(unittest.TestCase):
    def test_componentes_y_estres(self):
        m = K.ModeloCostes("binance_spot", semispread=0.0001, deslizamiento=0.0, impacto_k=0.0)
        self.assertAlmostEqual(m.coste_unitario("BTC", 1e4, 1e9, 0.01), 0.0011)
        m2 = K.ModeloCostes("binance_spot", semispread=0.0001, deslizamiento=0.0, impacto_k=0.0, multiplicador=2)
        self.assertAlmostEqual(m2.coste_unitario("BTC", 1e4, 1e9, 0.01), 0.0022)
        mi = K.ModeloCostes("binance_spot", semispread=0.0, deslizamiento=0.0, impacto_k=1.0)
        self.assertAlmostEqual(mi.coste_unitario("X", 1e4, 1e6, 0.02) - 0.001, 0.02 * math.sqrt(0.01))
        self.assertEqual(K.ModeloCostes("coinbase").comision(), 0.006)
        self.assertEqual(K.ModeloCostes(nivel={"BTC": "btc_eth"}).semi("BTC"), 0.00005)

    def test_funding(self):
        pos = pd.DataFrame({"BTC": [1000.0, -1000.0]}); tasa = pd.DataFrame({"BTC": [0.001, 0.001]})
        self.assertEqual(list(K.funding_pagado(pos, tasa)), [1.0, -1.0])


class TestMotor(unittest.TestCase):
    def test_sin_operar_y_rf(self):
        m = mercado(); m.rf = pd.Series(0.0001, index=m.close.index)
        W = pd.DataFrame(0.0, index=m.close.index, columns=m.close.columns)
        res = MO.simular(m, W)
        self.assertAlmostEqual(res["curva"].iloc[-1], 1e5 * 1.0001 ** len(m.close), places=4)
        self.assertEqual(len(res["operaciones"]), 0)

    def test_latencia_y_sin_anticipacion(self):
        m = mercado(n=50)
        W = pd.DataFrame(np.nan, index=m.close.index, columns=m.close.columns); W.iloc[10] = [1.0, 0, 0]
        res = MO.simular(m, W, K.ModeloCostes(latencia_barras=1))
        self.assertEqual(res["operaciones"]["ts"].iloc[0], m.close.index[11])
        with self.assertRaises(ValueError):
            MO.simular(m, W, K.ModeloCostes(latencia_barras=0))
        # oráculo: pesos que conocen el retorno de la barra siguiente no deben ganar lo que ganaría un oráculo
        fut = (m.close.shift(-1) / m.close - 1)
        Wo = (fut.rank(axis=1, ascending=False) <= 1).astype(float)
        Wl = (fut.shift(1).rank(axis=1, ascending=False) <= 1).astype(float)           # misma regla, sin futuro
        r_o = MO.simular(m, Wo, K.ModeloCostes(impacto_k=0))["curva"].iloc[-1]
        r_l = MO.simular(m, Wl, K.ModeloCostes(impacto_k=0))["curva"].iloc[-1]
        self.assertLess(r_l, r_o)

    def test_contabilidad_costes(self):
        m = mercado(n=30, vol=0.0)
        W = pd.DataFrame(np.nan, index=m.close.index, columns=m.close.columns); W.iloc[5] = [1.0, 0, 0]; W.iloc[15] = 0.0
        mc = K.ModeloCostes(semispread=0.0, deslizamiento=0.0, impacto_k=0.0)
        res = MO.simular(m, W, mc)
        self.assertAlmostEqual(res["costes"]["comision"], 2 * 1e5 / 1.001 * 0.001, places=6)
        self.assertAlmostEqual(res["curva"].iloc[-1], 1e5 - res["costes"]["comision"], places=6)
        self.assertEqual(len(res["episodios"]), 1)

    def test_spot_no_corto_y_perp_funding(self):
        m = mercado(n=30, vol=0.0)
        W = pd.DataFrame(np.nan, index=m.close.index, columns=m.close.columns); W.iloc[2] = [-0.5, 0, 0]
        with self.assertRaises(ValueError):
            MO.simular(m, W)
        mp = mercado(n=30, vol=0.0, perps=("BTC",))
        mp.funding = pd.DataFrame(0.0, index=mp.close.index, columns=mp.close.columns); mp.funding["BTC"] = 0.0001
        res = MO.simular(mp, W, K.ModeloCostes(semispread=0.0, deslizamiento=0.0, impacto_k=0.0))
        self.assertLess(res["costes"]["funding"], 0)                                     # el corto cobra funding
        self.assertGreater(res["curva"].iloc[-1], 1e5 - 100)

    def test_participacion_y_deslistado(self):
        m = mercado(n=30, vol=0.0); m.notional[:] = 1e6
        W = pd.DataFrame(np.nan, index=m.close.index, columns=m.close.columns); W.iloc[2] = [1.0, 0, 0]
        res = MO.simular(m, W, K.ModeloCostes(participacion_max=0.01))
        self.assertLessEqual(res["operaciones"]["notional"].abs().max(), 1e4 + 1e-6)
        m2 = mercado(n=30, vol=0.0)
        m2.open.iloc[20:, 2] = np.nan; m2.close.iloc[20:, 2] = np.nan
        W2 = pd.DataFrame(np.nan, index=m2.close.index, columns=m2.close.columns); W2.iloc[2] = [0, 0, 0.5]
        res2 = MO.simular(m2, W2, K.ModeloCostes(semispread=0.0, deslizamiento=0.0, impacto_k=0.0), recorte_deslistado=0.5)
        self.assertGreater(res2["costes"]["deslistado"], 0.24 * 1e5)
        self.assertIn("deslistado", set(res2["operaciones"]["motivo"]))


class TestMetricas(unittest.TestCase):
    def test_basicas(self):
        r = pd.Series([0.01, -0.005, 0.02, -0.01, 0.0])
        m = M.metricas(r, barras_anio=365)
        self.assertAlmostEqual(m["retorno_total"], float(np.prod(1 + r) - 1))
        self.assertLess(m["max_dd"], 0)
        ep = pd.DataFrame({"retorno": [0.1, -0.05, 0.02], "pnl": [1, -1, 1]})
        m2 = M.metricas(r, barras_anio=365, episodios=ep)
        self.assertAlmostEqual(m2["factor_beneficio"], 0.12 / 0.05); self.assertEqual(m2["operaciones"], 3)

    def test_psr_dsr_mintrl_potencia(self):
        rng = np.random.default_rng(0); r = rng.normal(0.002, 0.01, 2000)
        self.assertGreater(M.psr(r), 0.99)
        self.assertLess(M.psr(rng.normal(0, 0.01, 2000)), 0.99)
        self.assertGreater(M.sr0_deflactado(100, 1.0), M.sr0_deflactado(10, 1.0))
        self.assertLess(M.dsr(r, 1000, 4.0)["dsr"], M.psr(r))
        self.assertAlmostEqual(M.anios_necesarios(1.0), (1.6449 + 0.8416) ** 2, places=1)
        self.assertTrue(5.5 < M.anios_necesarios(1.0) < 6.5); self.assertTrue(0.5 < M.anios_necesarios(3.0) < 0.9)
        self.assertEqual(M.min_trl(0.0), math.inf); self.assertGreater(M.min_trl(1.0), M.min_trl(2.0))

    def test_pbo(self):
        rng = np.random.default_rng(1)
        ruido = rng.normal(0, 0.01, (800, 20))
        self.assertGreater(M.pbo(ruido, S=8)["pbo"], 0.25)
        bueno = ruido.copy(); bueno[:, 0] += 0.004
        self.assertLess(M.pbo(bueno, S=8)["pbo"], 0.1)

    def test_bootstrap(self):
        rng = np.random.default_rng(2)
        self.assertLess(M.bootstrap_estacionario(rng.normal(0.003, 0.01, 1000), n=300)["p_valor"], 0.05)
        self.assertGreater(M.bootstrap_estacionario(rng.normal(0, 0.01, 1000), n=300)["p_valor"], 0.05)

    def test_holm_bh(self):
        p = {"a": 0.001, "b": 0.02, "c": 0.035, "d": 0.5}
        h = M.holm(p); self.assertTrue(h["a"]["rechaza_h0"]); self.assertFalse(h["b"]["rechaza_h0"])
        bh = M.benjamini_hochberg(p); self.assertTrue(bh["c"]["rechaza_h0"]); self.assertFalse(bh["d"]["rechaza_h0"])

    def test_obf(self):
        f = M.fronteras_obf([90, 183, 365])
        self.assertAlmostEqual(f[-1]["alfa_acumulado"], 0.05, places=9)
        self.assertGreater(f[0]["z_frontera"], f[-1]["z_frontera"])
        self.assertGreater(f[0]["z_frontera"], 3.0)                                       # mirar pronto cuesta caro


class TestValidacion(unittest.TestCase):
    def test_wf(self):
        p = V.walk_forward(100, 40, 20, embargo=2)
        self.assertEqual(len(p), 2)
        for tr, te in p:
            self.assertLess(tr.max() + 2, te.min())

    def test_purga_y_cpcv(self):
        for tr, te in V.kfold_purgado(100, 5, horizonte=3, embargo=2):
            self.assertTrue(((tr + 3 < te.min()) | (tr > te.max() + 2)).all())
        c = V.cpcv(120, 6, 2, horizonte=2, embargo=1)
        self.assertEqual(len(c), 15); self.assertTrue(V.sin_solape(c))


class TestDiario(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp()); (self.d / "estrategia.py").write_text("x=1\n")
        self.reg = R.Registro(self.d / "r.jsonl", root=self.d, reloj=reloj_fijo("2026-11-20T00:00:00+00:00"))
        self.reg.registrar(hip())

    def test_senales(self):
        di = DI.Diario(self.d / "d.jsonl", self.reg, reloj=reloj_fijo("2026-11-21T01:00:05+00:00"))
        r = di.senal("H1", "2026-11-21T00:00:00+00:00", "2026-11-21T01:00:02+00:00", "2026-11-21T02:00:00+00:00", {"BTC": 1})
        self.assertTrue(r["a_tiempo"])
        di.reloj = reloj_fijo("2026-11-21T03:00:00+00:00")
        r2 = di.senal("H1", "2026-11-21T01:00:00+00:00", "2026-11-21T02:00:02+00:00", "2026-11-21T03:00:00+00:00", {"BTC": 0})
        self.assertFalse(r2["a_tiempo"])                                                  # tardía: no cuenta
        W = di.pesos("H1", ["BTC", "ETH"]); self.assertEqual(len(W), 1)
        self.assertEqual(di.resumen("H1")["tardias"], 1)
        with self.assertRaises(DI.DiarioError):
            di.reloj = reloj_fijo("2026-11-21T00:30:00+00:00")
            di.senal("H1", "2026-11-21T00:00:00+00:00", "2026-11-21T01:00:02+00:00", "2026-11-21T02:00:00+00:00", {})
        with self.assertRaises(DI.DiarioError):
            di.senal("NO", "2026-11-21", "2026-11-21", "2026-11-22", {})

    def test_manipulacion(self):
        di = DI.Diario(self.d / "d.jsonl", self.reg, reloj=reloj_fijo("2026-11-21T01:00:05+00:00"))
        di.senal("H1", "2026-11-21T00:00:00+00:00", "2026-11-21T01:00:02+00:00", "2026-11-21T02:00:00+00:00", {"BTC": 1})
        t = di.path.read_text().replace('"BTC":1.0', '"BTC":0.5'); di.path.write_text(t)
        with self.assertRaises(DI.DiarioError):
            di.verify()


class TestClasificacion(unittest.TestCase):
    def ev(self, deriva, dias, n_ops=60, semilla=0, vecinos=(1.5, 1.6, 1.4, 1.7)):
        rng = np.random.default_rng(semilla); n = dias
        r = pd.Series(rng.normal(deriva, 0.01, n), index=pd.date_range("2026-11-20", periods=n, freq="D"))
        ep = pd.DataFrame({"activo": [f"A{i % 6}" for i in range(n_ops)], "pnl": 1.0, "retorno": 0.01})
        return {"dias": dias, "retornos": r, "retornos_costes_x2": r - 0.0002, "retornos_btc": r * 0 + rng.normal(0, 0.03, n),
                "rf": None, "barras_anio": 365, "episodios": ep, "pnl_por_activo": {f"A{i}": 10.0 for i in range(6)},
                "sharpe_vecinos": list(vecinos), "var_sr": 0.5, "wf_historico_sharpe": 0.5, "guardias_ok": True}

    def h(self):
        return {"id": "H1", "puntos_control_dias": [90, 183, 365], "criterios": {}}

    def test_insuficiente_antes_del_punto(self):
        self.assertEqual(CL.clasificar(self.h(), self.ev(0.003, 60), 60, {"H1": 0.001})["clase"], "DATOS INSUFICIENTES")

    def test_guardia(self):
        e = self.ev(0.003, 365); e["guardias_ok"] = False
        self.assertEqual(CL.clasificar(self.h(), e, 60, {"H1": 0.001})["clase"], "RECHAZADA")

    def test_ruido_rechazado_al_final(self):
        r = CL.clasificar(self.h(), self.ev(0.0, 365, semilla=4), 60, {"H1": 0.4})
        self.assertEqual(r["clase"], "RECHAZADA")

    def test_futilidad(self):
        r = CL.clasificar(self.h(), self.ev(-0.002, 183), 60, {"H1": 0.9})
        self.assertEqual(r["clase"], "RECHAZADA"); self.assertIn("futilidad", r["motivos"][0])

    def test_aprobada_solo_con_todo(self):
        e = self.ev(0.004, 365, semilla=1, vecinos=(6.0, 6.5, 7.0, 5.5))
        r = CL.clasificar(self.h(), e, 60, {"H1": 1e-6, "H2": 0.5})
        self.assertEqual(r["clase"], "APROBADA", r["motivos"])
        e2 = dict(e, pnl_por_activo={"A0": 100.0, "A1": 1.0})                            # depende de un activo
        self.assertNotEqual(CL.clasificar(self.h(), e2, 60, {"H1": 1e-6})["clase"], "APROBADA")
        e3 = dict(e, sharpe_vecinos=[2.0, -0.5, -0.3, 0.1])                               # frágil a parámetros
        self.assertNotEqual(CL.clasificar(self.h(), e3, 60, {"H1": 1e-6})["clase"], "APROBADA")
        e4 = dict(e, episodios=e["episodios"].iloc[:10])                                  # pocas operaciones
        self.assertEqual(CL.clasificar(self.h(), e4, 60, {"H1": 1e-6})["clase"], "DATOS INSUFICIENTES")
        self.assertNotEqual(CL.clasificar(self.h(), dict(e, var_sr=4.0), 10 ** 9, {"H1": 1e-6})["clase"], "APROBADA")  # DSR con N enorme

    def test_registra_mirada_y_cierre(self):
        d = Path(tempfile.mkdtemp()); (d / "estrategia.py").write_text("x=1\n")
        reg = R.Registro(d / "r.jsonl", root=d, reloj=reloj_fijo("2026-11-20T00:00:00+00:00")); reg.registrar(hip())
        CL.evaluar_y_registrar(reg, "H1", self.ev(0.0, 365, semilla=4), {"H1": 0.4})
        self.assertEqual(len(reg.miradas("H1")), 1); self.assertTrue(reg.cerrada("H1")); self.assertTrue(reg.verify())


if __name__ == "__main__":
    unittest.main(verbosity=1)
