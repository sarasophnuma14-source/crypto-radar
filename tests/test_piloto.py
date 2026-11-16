"""Instrumentación, métricas por cohorte y encuestas del piloto (radar/piloto.py).

    python3 tests/test_piloto.py
    TEST_DATABASE_URL=postgresql://... python3 tests/test_piloto.py     # idempotencia también en PostgreSQL 16
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

os.environ["CRYPTO_RADAR_HOME"] = tempfile.mkdtemp(prefix="cr-piloto-")
os.environ["CRYPTO_RADAR_DATA"] = tempfile.mkdtemp(prefix="cr-piloto-data-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("CRYPTO_RADAR_PILOT_METRICS", None)
os.environ.pop("CRYPTO_RADAR_PILOT_SURVEYS", None)
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from radar import db, piloto  # noqa: E402

DAY = 86400
T0 = dt.datetime(2026, 12, 1, 12, tzinfo=dt.timezone.utc).timestamp()      # martes, semana ISO 49
ON = {"CRYPTO_RADAR_PILOT_METRICS": "1"}
ONS = {"CRYPTO_RADAR_PILOT_METRICS": "1", "CRYPTO_RADAR_PILOT_SURVEYS": "1"}


def user(uid, admin=0):
    return {"id": uid, "is_admin": admin}


def rows(uid=None):
    q = "SELECT id, user_id, at, action, detail, ip FROM activity" + (" WHERE user_id = ?" if uid else "")
    return db.all_(q, (uid,) if uid else ())


class Registro(unittest.TestCase):
    def setUp(self):
        db.init()
        db.execute("DELETE FROM activity", ())
        piloto.reset_cache()

    def test_apagado_por_defecto_no_escribe(self):
        self.assertFalse(piloto.enabled())
        self.assertFalse(piloto.record_daily(user("u1"), "visit"))
        self.assertFalse(piloto.record_client_event(user("u1"), {"event": "export_csv"}))
        self.assertEqual(rows(), [])

    def test_una_fila_por_usuario_evento_y_dia(self):
        with mock.patch.dict(os.environ, ON):
            for _ in range(5):
                piloto.record_daily(user("u1"), "visit", now=T0)
            piloto.reset_cache()                                   # otra instancia, sin caché: la base lo impide
            piloto.record_daily(user("u1"), "visit", now=T0 + 3600)
            piloto.record_daily(user("u1"), "visit", now=T0 + DAY)  # otro día UTC
            piloto.record_daily(user("u1"), "export_csv", now=T0)
        r = rows("u1")
        self.assertEqual(sorted(x["action"] for x in r), ["export_csv", "visit", "visit"])
        self.assertTrue(all(x["ip"] is None and x["detail"] is None for x in r), "sin IP ni contenido")

    def test_concurrencia_sin_duplicados(self):
        with mock.patch.dict(os.environ, ON):
            def go():
                piloto.reset_cache()
                piloto.record_daily(user("u2"), "tab:market", now=T0)
            ts = [threading.Thread(target=go) for _ in range(16)]
            [t.start() for t in ts]; [t.join() for t in ts]
        self.assertEqual(len(rows("u2")), 1)

    def test_admin_eventos_invalidos_y_pestanas_desconocidas(self):
        with mock.patch.dict(os.environ, ON):
            self.assertFalse(piloto.record_daily(user("adm", admin=1), "visit"))
            self.assertFalse(piloto.record_daily(user("u3"), "login"))           # login ya lo registra auth
            self.assertFalse(piloto.record_client_event(user("u3"), {"event": "tab", "tab": "<script>"}))
            self.assertFalse(piloto.record_client_event(user("u3"), {"event": "cualquiera"}))
            self.assertTrue(piloto.record_client_event(user("u3"), {"event": "tab", "tab": "portfolio"}))
        self.assertEqual([x["action"] for x in rows()], ["tab:portfolio"])

    def test_almacena_utc(self):
        late = dt.datetime(2026, 12, 1, 23, 30, tzinfo=dt.timezone(dt.timedelta(hours=-5))).timestamp()  # 04:30 UTC del 2
        self.assertEqual(piloto._day(late).isoformat(), "2026-12-02")


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "sin TEST_DATABASE_URL")
class RegistroPostgres(unittest.TestCase):
    def test_idempotente_en_postgres(self):
        code = r"""
import json, threading
from radar import db, piloto
db.init(); db.execute("DELETE FROM activity WHERE user_id = 'pgu'", ())
def go():
    piloto.reset_cache(); piloto.record_daily({"id": "pgu", "is_admin": 0}, "visit", now=1796126400)
ts = [threading.Thread(target=go) for _ in range(12)]; [t.start() for t in ts]; [t.join() for t in ts]
print(json.dumps(db.one("SELECT COUNT(*) AS n FROM activity WHERE user_id = 'pgu'", ())))
db.execute("DELETE FROM activity WHERE user_id = 'pgu'", ())
"""
        env = dict(os.environ, DATABASE_URL=os.environ["TEST_DATABASE_URL"], CRYPTO_RADAR_PILOT_METRICS="1")
        out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr[-1500:])
        self.assertEqual(json.loads(out.stdout.strip().splitlines()[-1])["n"], 1)


class Definiciones(unittest.TestCase):
    def test_activacion(self):
        f = T0
        self.assertEqual(piloto.activation([(f + 2 * DAY, "telegram_linked")], f), f + 2 * DAY)
        self.assertEqual(piloto.activation([(f + 3 * DAY, "position_add")], f), f + 3 * DAY)
        self.assertIsNone(piloto.activation([(f + 7 * DAY + 1, "telegram_linked")], f), "fuera de los 7 días")
        v = [(f, "visit"), (f + 3600, "visit"), (f + DAY, "visit")]
        self.assertIsNone(piloto.activation(v, f), "2 días distintos no bastan")
        self.assertEqual(piloto.activation(v + [(f + 4 * DAY, "visit")], f), f + 4 * DAY, "se activa el 3.er día")
        self.assertIsNone(piloto.activation([(f, "telegram_linked")], None), "sin inicio de sesión no hay activación")

    def test_ventanas_de_retencion(self):
        a = dt.date(2026, 12, 1)
        d = lambda n: a + dt.timedelta(days=n)
        self.assertIsNone(piloto.retained([d(22)], a, 22, 30, d(29)), "ventana sin terminar: pendiente")
        self.assertTrue(piloto.retained([d(22)], a, 22, 30, d(30)))
        self.assertTrue(piloto.retained([d(30)], a, 22, 30, d(40)))
        self.assertFalse(piloto.retained([d(21), d(31)], a, 22, 30, d(40)))
        self.assertTrue(piloto.retained([d(52)], a, 52, 60, d(60)))

    def test_wilson(self):
        self.assertEqual(piloto.wilson(12, 30), [0.2459, 0.5768])
        self.assertIsNone(piloto.wilson(0, 0))
        r = piloto.rate(0, 0, pending=3)
        self.assertEqual((r["tasa"], r["ic95"], r["pendientes"]), (None, None, 3))

    def test_canal(self):
        self.assertEqual(piloto.channel("Me lo recomendó un amigo"), "referido")
        self.assertEqual(piloto.channel("Lo vi en Telegram"), "telegram")
        self.assertEqual(piloto.channel(""), "sin dato")
        self.assertEqual(piloto.channel("no sé"), "otro")

    def test_van_westendorp(self):
        rows = [(3, 6, 15, 25), (4, 8, 18, 30), (5, 9, 20, 35), (2, 5, 12, 22), (5, 10, 25, 40)]
        r = piloto.van_westendorp(rows)
        lo, hi = r["rango_aceptable"]
        self.assertLess(lo, hi)
        self.assertEqual(r["muestra"], 5)
        self.assertEqual(r["aviso"], "muestra pequeña: no interpretar")
        self.assertIsNone(piloto.van_westendorp([])["rango_aceptable"])


def synthetic(now):
    """3 cohortes semanales: 40 aprobados, distintas activaciones y visitas."""
    users, ev = [], {}
    for i in range(40):
        uid = f"s{i}"
        start = T0 + (i % 3) * 7 * DAY
        users.append({"id": uid, "status": "active", "created_at": start - DAY, "approved_at": start - 3600,
                      "request_note": "amigo" if i % 2 else "", "telegram_chat_id": None, "is_admin": 0})
        if i % 10 == 9:
            continue                                                       # aprobado que nunca entró
        e = [(start, "login"), (start, "visit")]
        if i % 4 == 0:
            e.append((start + DAY, "telegram_linked"))
        if i % 4 == 1:
            e += [(start + DAY, "visit"), (start + 2 * DAY, "visit")]
        if i % 2 == 0:
            e += [(start + DAY + 25 * DAY, "visit")]                       # dentro de 22–30 tras activarse
        ev[uid] = e
    users.append({"id": "p1", "status": "pending", "created_at": T0, "approved_at": None, "request_note": None,
                  "telegram_chat_id": None, "is_admin": 0})
    users.append({"id": "r1", "status": "rejected", "created_at": T0, "approved_at": None, "request_note": None,
                  "telegram_chat_id": None, "is_admin": 0})
    return users, ev, []


class Informe(unittest.TestCase):
    def test_cohortes_separadas_y_tasas_con_ic(self):
        now = T0 + 60 * DAY
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=now, data=synthetic(now))
        self.assertEqual(rep["avisos"], [])
        self.assertEqual(rep["solicitudes"], {"total": 42, "aprobadas": 40, "rechazadas": 1, "pendientes": 1})
        self.assertEqual(sorted(rep["cohortes"]), ["2026-S49", "2026-S50", "2026-S51", "sin inicio de sesión"])
        tot = rep["total"]
        a = tot["activacion"]
        self.assertEqual(a["sin_datos"], 4)                                # los 4 que nunca entraron
        self.assertEqual(a["denominador"], 36)
        self.assertEqual(a["numerador"], sum(1 for i in range(40) if i % 10 != 9 and i % 4 in (0, 1)))
        self.assertEqual(len(a["ic95"]), 2)
        n = sum(c["activacion"]["denominador"] for k, c in rep["cohortes"].items() if k != "sin inicio de sesión")
        self.assertEqual(n, 36, "la suma de cohortes coincide con el total: nadie se mezcla ni se pierde")
        self.assertIn("insuficiente", rep["compuerta_b"]["lectura"])     # menos de 30 activados
        self.assertEqual(rep["canal_de_adquisicion"]["referido"], 20)
        txt = json.dumps(rep)
        self.assertNotIn("amigo", txt, "el informe no expone las notas de solicitud")

    def test_retencion_pendiente_si_la_ventana_no_termino(self):
        now = T0 + 10 * DAY
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=now, data=synthetic(now))
        r30 = rep["total"]["retencion_30d"]
        self.assertEqual(r30["denominador"], 0)
        self.assertGreater(r30["pendientes"], 0)

    def test_aviso_si_esta_apagado(self):
        rep = piloto.report(now=T0, data=([], {}, []))
        self.assertTrue(rep["avisos"] and "apagada" in rep["avisos"][0])
        self.assertFalse(rep["instrumentacion"]["metricas"])


class Encuestas(unittest.TestCase):
    def setUp(self):
        db.init()
        db.execute("DELETE FROM activity", ())
        db.execute("DELETE FROM survey_responses", ())
        piloto.reset_cache()

    def seed(self, uid, days_ago):
        import time
        start = time.time() - days_ago * DAY
        db.execute("INSERT INTO activity(id, user_id, at, action) VALUES (?, ?, ?, 'login')", (uid + "l", uid, start))
        db.execute("INSERT INTO activity(id, user_id, at, action) VALUES (?, ?, ?, 'telegram_linked')", (uid + "t", uid, start + 60))

    def test_apagadas_no_se_ofrecen(self):
        self.seed("e0", 15)
        self.assertIsNone(piloto.pending_survey(user("e0")))
        with mock.patch.dict(os.environ, ON):                              # métricas sí, encuestas no
            self.assertIsNone(piloto.pending_survey(user("e0")))
            with self.assertRaises(ValueError):
                piloto.answer(user("e0"), "dia14", {"utilidad": 4})

    def test_calendario_validacion_y_una_respuesta(self):
        self.seed("e1", 15)
        with mock.patch.dict(os.environ, ONS):
            p = piloto.pending_survey(user("e1"))
            self.assertEqual(p["id"], "dia14")
            with self.assertRaises(ValueError):
                piloto.answer(user("e1"), "dia14", {"utilidad": 9})          # fuera de escala
            with self.assertRaises(ValueError):
                piloto.answer(user("e1"), "dia30", {})                        # no le toca
            piloto.answer(user("e1"), "dia14", {"utilidad": 4, "falta": "x" * 900})
            self.assertIsNone(piloto.pending_survey(user("e1")), "ya respondida")
            with self.assertRaises(ValueError):
                piloto.answer(user("e1"), "dia14", {"utilidad": 5})
        r = db.one("SELECT answers FROM survey_responses WHERE user_id = 'e1'", ())
        self.assertEqual(len(json.loads(r["answers"])["falta"]), 500)

    def test_dia30_omitir_y_resumen(self):
        self.seed("e2", 31)
        self.seed("e3", 31)
        with mock.patch.dict(os.environ, ONS):
            self.assertEqual(piloto.pending_survey(user("e2"))["id"], "dia30")
            piloto.answer(user("e2"), "dia30", {"vw_muy_barato": 3, "vw_barato": 7, "vw_caro": 18, "vw_muy_caro": 30,
                                                "pagaria": "probable_si", "periodo": "anual"})
            with self.assertRaises(ValueError):
                piloto.answer(user("e3"), "dia30", {"pagaria": "tal vez"})
            piloto.answer(user("e3"), "dia30", {}, skipped=True)
            s = piloto.survey_summary(db.all_("SELECT user_id, survey, answers, skipped, at FROM survey_responses", ()))
        self.assertEqual(s["dia30"]["respuestas"], 1)
        self.assertEqual(s["dia30"]["omitidas"], 1)
        self.assertEqual(s["dia30"]["intencion_de_pago"]["numerador"], 1)
        self.assertEqual(s["dia30"]["periodo"]["anual"], 1)

    def test_texto_neutral_sin_pagos_ni_incentivos(self):
        txt = json.dumps(piloto.SURVEYS, ensure_ascii=False).lower()
        for bad in ("descuento", "premio", "regalo", "sorteo", "pagar ahora", "reserva con", "tarjeta"):
            self.assertNotIn(bad, txt)
        self.assertIn("no es una reserva ni un pago", txt)


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1, argv=[sys.argv[0]] + [a for a in sys.argv[1:] if a != "-v"])
