"""Pruebas de salud (liveness/readiness) e instancia única del trabajo de fondo.

Uso:  python3 tests/test_fiabilidad.py
Con PostgreSQL (prueba real del candado entre dos conexiones):
      TEST_DATABASE_URL=postgresql://... python3 tests/test_fiabilidad.py
"""
import datetime as dt
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

os.environ["CRYPTO_RADAR_HOME"] = tempfile.mkdtemp(prefix="cr-fiab-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("CRYPTO_RADAR_ACCOUNTS", None)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar import health, leader, storage, server  # noqa: E402

STATUS = {"scanning": False, "progress": "", "last_error": None}


class FakeStore:
    def __init__(self, at):
        self.at = at
        self.reads = 0

    def read(self, name, default=None):
        self.reads += 1
        return {"at": self.at, "sources": {"klines": "Binance (70 activos)"}} if self.at else default

    def read_fields(self, name, keys):
        doc = self.read(name, {}) or {}
        return {k: doc.get(k) for k in keys}


def iso(hours_ago):
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)).isoformat()


def ready(store, uses_db=False, sched=False, **kw):
    health.invalidate()
    return health.readiness(storage=store, scanner_status=kw.pop("status", STATUS), scan_every_hours=4,
                            uses_db=uses_db, scheduler_expected=sched, version="t", **kw)


class Salud(unittest.TestCase):
    def test_liveness_no_toca_dependencias(self):
        with mock.patch("radar.db.one", side_effect=AssertionError("no debe consultar la base")):
            self.assertEqual(health.liveness("x"), (200, {"ok": True, "version": "x"}))

    def test_ok_con_escaneo_reciente(self):
        code, b = ready(FakeStore(iso(1)))
        self.assertEqual((code, b["status"], b["ok"]), (200, "ok", True))
        self.assertTrue(b["checks"]["scan"]["ok"])

    def test_escaneo_atrasado_es_degradado_no_503(self):
        code, b = ready(FakeStore(iso(10)))          # 4 h × 2 + 1 = 9 h de margen
        self.assertEqual((code, b["status"]), (200, "degradado"))

    def test_sin_escaneos_es_degradado(self):
        code, b = ready(FakeStore(None))
        self.assertEqual((code, b["status"]), (200, "degradado"))

    def test_base_caida_da_503_sin_detalles(self):
        secreto = "postgresql://radar_app:CLAVE_SECRETA_123@ep-x.neon.tech/radar"
        with mock.patch("radar.db.one", side_effect=RuntimeError("fallo en " + secreto)):
            code, b = ready(FakeStore(iso(1)), uses_db=True)
        self.assertEqual((code, b["status"], b["ok"]), (503, "fallo", False))
        txt = json.dumps(b)
        for x in ("CLAVE_SECRETA", "ep-x", "radar_app", "RuntimeError", "Traceback"):
            self.assertNotIn(x, txt)
        self.assertEqual(b["checks"]["database"], {"ok": False, "error": "sin respuesta"})

    def test_base_colgada_responde_en_tiempo_limite(self):
        with mock.patch("radar.db.one", side_effect=lambda *a, **k: time.sleep(6)):
            t0 = time.time()
            code, b = ready(FakeStore(iso(1)), uses_db=True)
        self.assertEqual(code, 503)
        self.assertLess(time.time() - t0, health.DB_TIMEOUT_S + 1)

    def test_base_sana_mide_latencia(self):
        with mock.patch("radar.db.one", return_value={"ok": 1}):
            code, b = ready(FakeStore(iso(1)), uses_db=True)
        self.assertEqual(code, 200)
        self.assertTrue(b["checks"]["database"]["ok"])
        self.assertIsInstance(b["checks"]["database"]["ms"], int)

    def test_planificador_mudo_da_503_y_arranque_tiene_gracia(self):
        health._beats.pop("scheduler", None)
        self.assertEqual(ready(FakeStore(iso(1)), sched=True)[0], 200)            # recién arrancado
        with mock.patch.object(health, "_START", time.time() - 3600):
            self.assertEqual(ready(FakeStore(iso(1)), sched=True)[0], 503)        # nunca latió
        health._beats["scheduler"] = time.time() - 400
        self.assertEqual(ready(FakeStore(iso(1)), sched=True)[0], 503)            # dejó de latir
        health.beat("scheduler")
        self.assertEqual(ready(FakeStore(iso(1)), sched=True)[0], 200)

    def test_resumen_cacheado(self):
        st = FakeStore(iso(1))
        health.invalidate()
        for _ in range(5):
            health.readiness(storage=st, scanner_status=STATUS, scan_every_hours=4, uses_db=False,
                             scheduler_expected=False, version="t")
        self.assertEqual(st.reads, 1)

    def test_compatibilidad_campos_anteriores(self):
        _, b = ready(FakeStore(iso(1)), status={"scanning": True, "progress": "50%", "last_error": "x" * 500})
        for k in ("ok", "scanning", "progress", "last_scan", "last_error", "sources"):
            self.assertIn(k, b)
        self.assertEqual(len(b["last_error"]), 300)


class SaludHTTP(unittest.TestCase):
    """Rutas reales del servidor en modo de un solo usuario con contraseña: salud sin autenticación."""

    @classmethod
    def setUpClass(cls):
        os.environ["CRYPTO_RADAR_PASSWORD"] = "clave de prueba larga"
        storage.write("latest.json", {"at": iso(1), "sources": {"x": "OK"}})
        health.invalidate()
        cls.httpd = server.PooledHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown(); cls.httpd.server_close()
        os.environ.pop("CRYPTO_RADAR_PASSWORD", None)

    def get(self, p):
        try:
            with urllib.request.urlopen(self.base + p, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, None

    def test_rutas_publicas(self):
        for p in ("/livez", "/healthz", "/readyz", "/healthz?x=1"):
            code, b = self.get(p)
            self.assertEqual(code, 200, p)
            self.assertTrue(b["ok"], p)
        self.assertEqual(self.get("/healthz")[1]["status"], "ok")

    def test_lo_demas_sigue_protegido(self):
        self.assertEqual(self.get("/api/state")[0], 401)


class Lider(unittest.TestCase):
    def test_sin_postgres_siempre_lider(self):
        self.assertTrue(leader.is_leader())
        leader.start()                                  # no arranca hilos sin PostgreSQL
        self.assertFalse(leader._state["started"])

    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "sin TEST_DATABASE_URL")
    def test_candado_exclusivo_y_traspaso_postgres(self):
        url = os.environ["TEST_DATABASE_URL"]
        a = leader._try_acquire(url)
        self.assertIsNotNone(a, "la primera instancia obtiene el candado")
        try:
            self.assertIsNone(leader._try_acquire(url), "la segunda instancia no lo obtiene mientras viva la primera")
        finally:
            a.close()                                   # la primera instancia muere
        b = leader._try_acquire(url)
        self.assertIsNotNone(b, "al morir la primera, la segunda lo obtiene")
        b.close()

    def test_trabajo_de_fondo_respeta_al_lider(self):
        src = (ROOT / "radar" / "server.py").read_text("utf-8")
        self.assertIn("if not leader.is_leader():", src[src.index("def scheduler"):src.index("def _f(")])
        self.assertIn("if not leader.is_leader():", src[src.index("def paper_scheduler"):src.index("ADMIN_ENV =")])
        tg = (ROOT / "radar" / "telegram_bot.py").read_text("utf-8")
        self.assertIn("if not leader.is_leader():", tg[tg.index("def poll_forever"):])


class EstadoPublico(unittest.TestCase):
    def test_estado_publico_sin_veredicto_ni_regimen(self):
        src = (ROOT / "radar" / "webapi.py").read_text("utf-8")
        blk = src[src.index('if p == "/api/public/status":'):src.index('if p == "/api/billing/status":')]
        for k in ('"verdict"', '"regime"', '"regime_label"'):
            self.assertNotIn(k, blk)


LECTOR = r"""
import json, sys
from radar import storage
big = {"at": "2026-11-16T02:27:00+00:00", "sources": {"klines": "Binance"}, "n": 3, "assets": ["x" * 500] * 400}
storage.write("latest.json", big)
print(json.dumps({"f": storage.read_fields("latest.json", ["at", "sources", "n", "falta"]),
                  "vacio": storage.read_fields("no-existe.json", ["at"])}))
"""


class LecturaParcial(unittest.TestCase):
    """El planificador consulta la fecha del último escaneo cada 30 s: debe extraerla en la base, no descargar el informe."""

    def run_backend(self, env_extra):
        import subprocess
        env = dict(os.environ, CRYPTO_RADAR_HOME=tempfile.mkdtemp(prefix="cr-rf-"),
                   CRYPTO_RADAR_DATA=tempfile.mkdtemp(prefix="cr-rf-data-"), **env_extra)
        env.pop("CRYPTO_RADAR_ACCOUNTS", None)
        out = subprocess.run([sys.executable, "-c", LECTOR], cwd=str(ROOT), env=env,
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-2000:])
        return json.loads(out.stdout.strip().splitlines()[-1])

    def check(self, r):
        self.assertEqual(r["f"], {"at": "2026-11-16T02:27:00+00:00", "sources": {"klines": "Binance"},
                                  "n": 3, "falta": None})
        self.assertEqual(r["vacio"], {"at": None})

    def test_archivos(self):
        self.check(self.run_backend({"DATABASE_URL": "", "CRYPTO_RADAR_STORAGE": "file"}))

    def test_sqlite(self):
        self.check(self.run_backend({"DATABASE_URL": "", "CRYPTO_RADAR_STORAGE": "db"}))

    @unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "sin TEST_DATABASE_URL")
    def test_postgres(self):
        self.check(self.run_backend({"DATABASE_URL": os.environ["TEST_DATABASE_URL"]}))

    def test_planificador_no_lee_el_informe_entero(self):
        with mock.patch.object(storage, "read", side_effect=AssertionError("lectura completa")), \
             mock.patch.object(storage, "read_fields", return_value={"at": None}) as rf:
            server.next_scan_time()
        rf.assert_called_once_with("latest.json", ["at"])


if __name__ == "__main__":
    unittest.main()
