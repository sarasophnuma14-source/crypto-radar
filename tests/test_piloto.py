"""Instrumentación, métricas por cohorte y encuestas del piloto (radar/piloto.py).

    python3 tests/test_piloto.py
    TEST_DATABASE_URL=postgresql://... python3 tests/test_piloto.py     # idempotencia también en PostgreSQL 16
    PILOTO_TODO_EN_PG=1 TEST_DATABASE_URL=postgresql://... python3 tests/test_piloto.py   # toda la suite en PostgreSQL
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
if os.environ.get("PILOTO_TODO_EN_PG") and os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]   # toda la suite sobre PostgreSQL 16 (base de pruebas)
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
        f = T0                                                       # aprobación
        L = [(f + 60, "login")]
        self.assertEqual(piloto.activation(L + [(f + 2 * DAY, "telegram_linked")], f), f + 2 * DAY)
        self.assertEqual(piloto.activation(L + [(f + 3 * DAY, "position_add")], f), f + 3 * DAY)
        self.assertIsNone(piloto.activation(L + [(f + 7 * DAY + 1, "telegram_linked")], f), "fuera de los 7 días")
        v = L + [(f, "visit"), (f + 3600, "visit"), (f + DAY, "visit")]
        self.assertIsNone(piloto.activation(v, f), "2 días distintos no bastan")
        self.assertEqual(piloto.activation(v + [(f + 4 * DAY, "visit")], f), f + 4 * DAY, "se activa el 3.er día")
        self.assertIsNone(piloto.activation([(f, "telegram_linked")], f), "sin inicio de sesión no hay activación")
        self.assertIsNone(piloto.activation(L + [(f, "telegram_linked")], None), "sin aprobación no hay ventana")

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
    return users, ev, [], {}


class Informe(unittest.TestCase):
    def test_cohortes_separadas_y_tasas_con_ic(self):
        now = T0 + 60 * DAY
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=now, data=synthetic(now))
        self.assertEqual([a for a in rep["avisos"] if "apagada" in a], [])
        self.assertEqual(rep["solicitudes"], {"total": 42, "aprobadas": 40, "rechazadas": 1, "pendientes": 1})
        self.assertEqual(sorted(rep["cohortes"]), ["2026-S49", "2026-S50", "2026-S51"], "por semana de aprobación")
        tot = rep["total"]
        a = tot["activacion"]
        n_act = sum(1 for i in range(40) if i % 10 != 9 and i % 4 in (0, 1))
        self.assertEqual((tot["aprobados"], tot["pendientes"], tot["elegibles"]), (40, 0, 40))
        self.assertEqual((tot["activados"], tot["no_activados"]), (n_act, 40 - n_act))
        self.assertEqual(tot["no_activados_sin_inicio_de_sesion"], 4, "los 4 que nunca entraron cuentan como no activados")
        self.assertEqual((a["numerador"], a["denominador"]), (n_act, 40), "activados ÷ aprobados elegibles")
        self.assertEqual(len(a["ic95"]), 2)
        for k in ("aprobados", "pendientes", "elegibles", "activados", "no_activados"):
            self.assertEqual(sum(c[k] for c in rep["cohortes"].values()), tot[k], f"cohortes y total cuadran en {k}")
        self.assertIn("insuficiente", rep["compuerta_b"]["lectura"])     # menos de 30 activados
        self.assertEqual(rep["canal_de_adquisicion"]["referido"], 20)
        txt = json.dumps(rep)
        self.assertNotIn("amigo", txt, "el informe no expone las notas de solicitud")
        self.assertNotIn('"s1"', txt, "el informe no expone identificadores de usuario")

    def test_retencion_pendiente_si_la_ventana_no_termino(self):
        now = T0 + 10 * DAY
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=now, data=synthetic(now))
        r30 = rep["total"]["retencion_30d"]
        self.assertEqual(r30["denominador"], 0)
        self.assertGreater(r30["pendientes"], 0)

    def test_aviso_si_esta_apagado(self):
        rep = piloto.report(now=T0, data=([], {}, [], {}))
        self.assertTrue(rep["avisos"] and "apagada" in rep["avisos"][0])
        self.assertFalse(rep["instrumentacion"]["metricas"])


class Encuestas(unittest.TestCase):
    def setUp(self):
        db.init()
        db.execute("DELETE FROM activity", ())
        db.execute("DELETE FROM survey_responses", ())
        piloto.reset_cache()
        self.users = {}

    def seed(self, uid, days_ago):
        """Aprobado hace `days_ago` días; entra y vincula Telegram enseguida (activado). Devuelve el usuario."""
        import time
        start = time.time() - days_ago * DAY
        db.execute("INSERT INTO activity(id, user_id, at, action) VALUES (?, ?, ?, 'login')", (uid + "l", uid, start + 30))
        db.execute("INSERT INTO activity(id, user_id, at, action) VALUES (?, ?, ?, 'telegram_linked')", (uid + "t", uid, start + 60))
        self.users[uid] = {"id": uid, "is_admin": 0, "approved_at": start}
        return self.users[uid]

    def test_apagadas_no_se_ofrecen(self):
        self.seed("e0", 15)
        self.assertIsNone(piloto.pending_survey(self.users["e0"]))
        with mock.patch.dict(os.environ, ON):                              # métricas sí, encuestas no
            self.assertIsNone(piloto.pending_survey(self.users["e0"]))
            with self.assertRaises(ValueError):
                piloto.answer(self.users["e0"], "dia14", {"utilidad": 4})

    def test_calendario_validacion_y_una_respuesta(self):
        self.seed("e1", 15)
        with mock.patch.dict(os.environ, ONS):
            p = piloto.pending_survey(self.users["e1"])
            self.assertEqual(p["id"], "dia14")
            with self.assertRaises(ValueError):
                piloto.answer(self.users["e1"], "dia14", {"utilidad": 9})          # fuera de escala
            with self.assertRaises(ValueError):
                piloto.answer(self.users["e1"], "dia30", {})                        # no le toca
            piloto.answer(self.users["e1"], "dia14", {"utilidad": 4, "falta": "x" * 900})
            self.assertIsNone(piloto.pending_survey(self.users["e1"]), "ya respondida")
            with self.assertRaises(ValueError):
                piloto.answer(self.users["e1"], "dia14", {"utilidad": 5})
        r = db.one("SELECT answers FROM survey_responses WHERE user_id = 'e1'", ())
        self.assertEqual(len(json.loads(r["answers"])["falta"]), 500)

    def test_dia30_omitir_y_resumen(self):
        self.seed("e2", 31)
        self.seed("e3", 31)
        with mock.patch.dict(os.environ, ONS):
            self.assertEqual(piloto.pending_survey(self.users["e2"])["id"], "dia30")
            piloto.answer(self.users["e2"], "dia30", {"vw_muy_barato": 3, "vw_barato": 7, "vw_caro": 18, "vw_muy_caro": 30,
                                                "pagaria": "probable_si", "periodo": "anual"})
            with self.assertRaises(ValueError):
                piloto.answer(self.users["e3"], "dia30", {"pagaria": "tal vez"})
            piloto.answer(self.users["e3"], "dia30", {}, skipped=True)
            s = piloto.survey_summary(db.all_("SELECT user_id, survey, answers, skipped, at FROM survey_responses", ()))
        self.assertEqual(s["dia30"]["respuestas"], 1)
        self.assertEqual(s["dia30"]["omitidas"], 1)
        self.assertEqual(s["dia30"]["intencion_entre_respondientes"]["numerador"], 1)
        self.assertNotIn("intencion_de_pago", s["dia30"], "la tasa de B5 no sale de la encuesta sola (H2)")
        self.assertEqual(s["dia30"]["periodo"]["anual"], 1)

    def test_texto_neutral_sin_pagos_ni_incentivos(self):
        txt = json.dumps(piloto.SURVEYS, ensure_ascii=False).lower()
        for bad in ("descuento", "premio", "regalo", "sorteo", "pagar ahora", "reserva con", "tarjeta"):
            self.assertNotIn(bad, txt)
        self.assertIn("no es una reserva ni un pago", txt)


def U(uid, approved_at, tg=None):
    return {"id": uid, "status": "active", "created_at": approved_at - DAY, "approved_at": approved_at,
            "request_note": None, "telegram_chat_id": tg, "is_admin": 0}


def state_of(users, ev, now, uid):
    """Estado de un usuario según el informe, deducido del total (cada caso se prueba con un único usuario)."""
    with mock.patch.dict(os.environ, ON):
        t = piloto.report(now=now, data=(users, ev, [], {}))["total"]
    if t["activados"]:
        return "activado", t
    return ("pendiente" if t["pendientes"] else "no_activado"), t


class ActivacionH1(unittest.TestCase):
    """Auditoría correctiva H1: denominador = aprobados elegibles; nadie sale sin motivo explícito."""
    A = T0

    def test_1_aprobado_que_nunca_inicia_sesion(self):
        st, t = state_of([U("u", self.A)], {}, self.A + 10 * DAY, "u")
        self.assertEqual(st, "no_activado")
        self.assertEqual((t["aprobados"], t["elegibles"], t["no_activados_sin_inicio_de_sesion"]), (1, 1, 1))
        self.assertEqual((t["activacion"]["numerador"], t["activacion"]["denominador"]), (0, 1))

    def test_2_inicia_sesion_sin_accion_de_activacion(self):
        ev = {"u": [(self.A + 60, "login"), (self.A + 60, "visit")]}
        st, t = state_of([U("u", self.A)], ev, self.A + 10 * DAY, "u")
        self.assertEqual(st, "no_activado")
        self.assertEqual((t["no_activados"], t["no_activados_sin_inicio_de_sesion"]), (1, 0))

    def test_3_vincula_telegram(self):
        ev = {"u": [(self.A + 60, "login"), (self.A + 2 * DAY, "telegram_linked")]}
        st, t = state_of([U("u", self.A)], ev, self.A + 10 * DAY, "u")
        self.assertEqual(st, "activado")
        self.assertEqual(t["activacion"]["tasa"], 1.0)

    def test_4_registra_una_posicion(self):
        ev = {"u": [(self.A + 60, "login"), (self.A + 6 * DAY, "position_add")]}
        self.assertEqual(state_of([U("u", self.A)], ev, self.A + 10 * DAY, "u")[0], "activado")
        ev = {"u": [(self.A + 60, "login"), (self.A + 7 * DAY + 60, "position_add")]}
        self.assertEqual(state_of([U("u", self.A)], ev, self.A + 10 * DAY, "u")[0], "no_activado", "fuera de la ventana")

    def test_5_visita_en_tres_dias_distintos(self):
        ev = {"u": [(self.A + 60, "login")] + [(self.A + d * DAY, "visit") for d in (0, 2, 5)]}
        self.assertEqual(state_of([U("u", self.A)], ev, self.A + 10 * DAY, "u")[0], "activado")
        ev = {"u": [(self.A + 60, "login")] + [(self.A + h * 3600, "visit") for h in (0, 1, 2, 3)]}
        self.assertEqual(state_of([U("u", self.A)], ev, self.A + 10 * DAY, "u")[0], "no_activado", "mismo día no cuenta")

    def test_6_aprobado_hace_menos_de_7_dias(self):
        st, t = state_of([U("u", self.A)], {}, self.A + 3 * DAY, "u")
        self.assertEqual(st, "pendiente")
        self.assertEqual((t["aprobados"], t["pendientes"], t["elegibles"]), (1, 1, 0))
        self.assertEqual((t["activacion"]["denominador"], t["activacion"]["pendientes"]), (0, 1))
        ev = {"u": [(self.A + 60, "login"), (self.A + DAY, "telegram_linked")]}
        st, t = state_of([U("u", self.A)], ev, self.A + 3 * DAY, "u")
        self.assertEqual((st, t["elegibles"]), ("activado", 1), "quien ya se activó cuenta aunque la ventana siga abierta")

    def test_7_aprobado_hace_mas_de_7_dias_sin_actividad(self):
        st, t = state_of([U("u", self.A)], {}, self.A + 7 * DAY + 1, "u")
        self.assertEqual(st, "no_activado")
        self.assertEqual(t["pendientes"], 0)

    def test_8_cohortes_con_fechas_distintas(self):
        users = [U("a1", T0), U("a2", T0 + DAY),                      # semana 49
                 U("b1", T0 + 7 * DAY), U("b2", T0 + 8 * DAY),        # semana 50
                 U("c1", T0 + 14 * DAY)]                              # semana 51, aún en ventana
        ev = {"a1": [(T0 + 60, "login"), (T0 + DAY, "telegram_linked")],
              "b2": [(T0 + 8 * DAY + 60, "login"), (T0 + 9 * DAY, "position_add")]}
        now = T0 + 17 * DAY
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=now, data=(users, ev, [], {"2026-S50": 1}))
        c = rep["cohortes"]
        self.assertEqual(sorted(c), ["2026-S49", "2026-S50", "2026-S51"])
        self.assertEqual((c["2026-S49"]["activados"], c["2026-S49"]["no_activados"], c["2026-S49"]["pendientes"]), (1, 1, 0))
        self.assertEqual((c["2026-S50"]["activados"], c["2026-S50"]["no_activados"]), (1, 1))
        self.assertEqual(c["2026-S50"]["bajas_por_supresion"], 1, "una baja explícita, contada aparte")
        self.assertEqual((c["2026-S51"]["pendientes"], c["2026-S51"]["elegibles"]), (1, 0))
        t = rep["total"]
        self.assertEqual((t["aprobados"], t["elegibles"], t["pendientes"], t["activados"], t["no_activados"]),
                         (5, 4, 1, 2, 2))
        for k in ("aprobados", "elegibles", "pendientes", "activados", "no_activados", "bajas_por_supresion"):
            self.assertEqual(sum(x[k] for x in c.values()), t[k], k)
        self.assertEqual(t["activacion"]["tasa"], 0.5)


def intent_population(n_elig, n_resp, n_yes, now_offset_days=80, skipped=0, extra_noneligible_yes=0):
    """n_elig activados con visita en los días 22–30; n_resp responden «pagaria» (n_yes con «sí»); `skipped` omiten."""
    users, ev, surveys = [], {}, []
    for i in range(n_elig + extra_noneligible_yes):
        uid = f"x{i}"
        users.append(U(uid, T0))
        e = [(T0 + 60, "login"), (T0 + DAY, "telegram_linked")]
        if i < n_elig:
            e.append((T0 + DAY + 25 * DAY, "visit"))                     # activo a 30 días
        ev[uid] = e
        if i < n_resp or i >= n_elig:
            ans = "seguro_si" if (i < n_yes or i >= n_elig) else "seguro_no"
            surveys.append({"user_id": uid, "survey": "dia30", "answers": json.dumps({"pagaria": ans}),
                            "skipped": 0, "at": T0 + 32 * DAY})
        elif i < n_resp + skipped:
            surveys.append({"user_id": uid, "survey": "dia30", "answers": "{}", "skipped": 1, "at": T0 + 32 * DAY})
    return users, ev, surveys, {}


class IntencionDePagoH2(unittest.TestCase):
    """Auditoría correctiva H2: B5 sobre elegibles a 30 días; la falta de respuesta no se convierte en «sí»."""

    def pi(self, *a, **k):
        now = T0 + k.pop("now_days", 80) * DAY
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=now, data=intent_population(*a, **k))
        return rep["total"]["intencion_de_pago"], rep["compuerta_b"]

    def test_participacion_total(self):
        p, g = self.pi(40, 40, 16)
        self.assertEqual((p["elegibles_30d"], p["respondieron"], p["no_respondieron"]), (40, 40, 0))
        self.assertEqual(p["tasa_sobre_elegibles"]["tasa"], 0.4)
        self.assertEqual(p["tasa_entre_respondientes"]["tasa"], 0.4)
        self.assertEqual(p["participacion"]["tasa"], 1.0)
        self.assertEqual(g["criterios"]["B5_intencion_de_pago"], "GO")
        self.assertIsNone(p["aviso"])

    def test_baja_participacion_no_infla_la_compuerta(self):
        p, g = self.pi(40, 10, 8)                                        # 80 % de «sí»… entre 10 de 40
        self.assertEqual(p["tasa_entre_respondientes"]["tasa"], 0.8)
        self.assertEqual(p["tasa_sobre_elegibles"]["tasa"], 0.2)
        self.assertEqual((p["respondieron"], p["no_respondieron"]), (10, 30))
        self.assertEqual(p["participacion"]["tasa"], 0.25)
        self.assertEqual(g["criterios"]["B5_intencion_de_pago"], "zona gris", "usa 20 %, no 80 %")
        self.assertIn("participación inferior al 50 %", p["aviso"])

    def test_omitir_cuenta_como_no_respuesta(self):
        p, g = self.pi(40, 20, 10, skipped=10)
        self.assertEqual((p["respondieron"], p["no_respondieron"]), (20, 20))
        self.assertEqual(p["tasa_sobre_elegibles"]["tasa"], 0.25)
        self.assertEqual(p["tasa_entre_respondientes"]["tasa"], 0.5)

    def test_sin_respuestas_no_es_senal(self):
        p, g = self.pi(40, 0, 0)
        self.assertEqual(p["tasa_sobre_elegibles"]["tasa"], 0.0)
        self.assertIsNone(p["tasa_entre_respondientes"]["tasa"])
        self.assertEqual(g["criterios"]["B5_intencion_de_pago"], "NO-GO")

    def test_ventana_abierta_queda_pendiente(self):
        p, _ = self.pi(40, 10, 5, now_days=35)                          # la encuesta del día 30 sigue abierta
        self.assertEqual((p["pendientes"], p["no_respondieron"]), (30, 0))
        self.assertEqual(p["tasa_sobre_elegibles"]["denominador"], 10)
        self.assertEqual(p["tasa_sobre_elegibles"]["pendientes"], 30)

    def test_respuestas_de_no_elegibles_no_cuentan(self):
        p, _ = self.pi(10, 0, 0, extra_noneligible_yes=5)
        self.assertEqual((p["elegibles_30d"], p["respuestas_si"], p["fuera_de_elegibles"]), (10, 0, 5))

    def test_varias_tasas_de_respuesta(self):
        for resp, yes, sobre, entre in ((40, 12, 0.3, 0.3), (30, 12, 0.3, 0.4), (20, 12, 0.3, 0.6), (12, 12, 0.3, 1.0)):
            p, g = self.pi(40, resp, yes)
            self.assertEqual(p["tasa_sobre_elegibles"]["tasa"], sobre)
            self.assertEqual(p["tasa_entre_respondientes"]["tasa"], entre)
            self.assertEqual(g["criterios"]["B5_intencion_de_pago"], "GO", "misma señal real, misma lectura")


class PrivacidadH7(unittest.TestCase):
    def setUp(self):
        db.init()
        for t in ("activity", "survey_responses", "users"):
            db.execute(f"DELETE FROM {t}", ())
        piloto.reset_cache()

    def test_texto_libre_sin_datos_de_contacto(self):
        t = piloto.redact("escríbeme a ana.perez+x@correo.com o al +57 300 123 4567, mi canal https://t.me/abc y @anaperez")
        for bad in ("ana.perez", "300 123", "t.me", "@anaperez"):
            self.assertNotIn(bad, t)
        self.assertIn("[correo eliminado]", t)
        self.assertEqual(piloto.redact("me sirve el radar de rupturas"), "me sirve el radar de rupturas")

    def test_informe_admin_solo_agregados(self):
        rows = [{"user_id": "u1", "survey": "dia14", "skipped": 0, "at": T0,
                 "answers": json.dumps({"utilidad": 4, "para_que": "texto privado único", "falta": "otra cosa"})}]
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=T0 + 30 * DAY, data=([U("u1", T0)], {"u1": [(T0 + 60, "login")]}, rows, {}))
        txt = json.dumps(rep, ensure_ascii=False)
        for bad in ("texto privado único", "otra cosa", '"u1"'):
            self.assertNotIn(bad, txt)

    def test_retirar_respuestas(self):
        import time
        now = time.time()
        db.execute("INSERT INTO survey_responses(id, user_id, survey, answers, skipped, at) VALUES (?, ?, ?, ?, ?, ?)",
                   ("r1", "u1", "dia30", json.dumps({"pagaria": "seguro_si", "reemplaza": "x"}), 0, now))
        self.assertEqual(piloto.withdraw({"id": "u1", "is_admin": 0}), 1)
        r = db.one("SELECT answers, skipped FROM survey_responses WHERE id = 'r1'", ())
        self.assertEqual((r["answers"], r["skipped"]), ("{}", 2))

    def test_supresion_de_cuenta_borra_y_deja_baja_anonima(self):
        db.execute("INSERT INTO users(id, email, pw_hash, created_at, approved_at) VALUES ('u9', 'nueve', 'x', ?, ?)",
                   (T0, T0))
        db.execute("INSERT INTO survey_responses(id, user_id, survey, answers, skipped, at) VALUES ('r9', 'u9', 'dia14', '{}', 0, ?)", (T0,))
        db.execute("INSERT INTO activity(id, user_id, at, action) VALUES ('v9', 'u9', ?, 'visit')", (T0,))
        db.execute("INSERT INTO activity(id, user_id, at, action) VALUES ('l9', 'u9', ?, 'login')", (T0,))
        from radar import storage
        storage.write("piloto_bajas", {})
        piloto.forget_user("u9")
        self.assertIsNone(db.one("SELECT id FROM survey_responses WHERE user_id = 'u9'", ()))
        self.assertIsNone(db.one("SELECT id FROM activity WHERE id = 'v9'", ()))
        self.assertIsNotNone(db.one("SELECT id FROM activity WHERE id = 'l9'", ()), "el registro de seguridad no es del piloto")
        self.assertEqual(storage.read("piloto_bajas"), {"2026-S49": 1})
        src = (ROOT / "radar" / "auth.py").read_text("utf-8")
        blk = src[src.index('elif action == "delete":'):]
        self.assertLess(blk.index("piloto.forget_user(uid)"), blk.index("DELETE FROM users"))

    def test_informe_real_desde_la_base(self):
        """report() sin datos inyectados: lee de la base (en PostgreSQL, el «%» del LIKE rompía la consulta)."""
        db.execute("INSERT INTO users(id, email, pw_hash, created_at, approved_at, status) VALUES ('q1', 'q1', 'x', ?, ?, 'active')",
                   (T0, T0))
        for i, (a, at) in enumerate((("login", T0 + 60), ("tab:dash", T0 + 60), ("telegram_linked", T0 + DAY))):
            db.execute("INSERT INTO activity(id, user_id, at, action) VALUES (?, 'q1', ?, ?)", (f"q{i}", at, a))
        with mock.patch.dict(os.environ, ON):
            rep = piloto.report(now=T0 + 10 * DAY)
        self.assertEqual((rep["total"]["aprobados"], rep["total"]["activados"]), (1, 1))
        self.assertEqual(rep["uso"]["pestanas_usuario_dia"], {"dash": 1})

    def test_politica_coherente_con_la_instrumentacion(self):
        pol = (ROOT / "web" / "privacidad.html").read_text("utf-8")
        for k in ("encuestas del piloto", "sin IP ni contenido", "sin correos, teléfonos ni enlaces",
                  "retirar tus respuestas", "nunca respuestas individuales"):
            self.assertIn(k, pol)
        api = (ROOT / "radar" / "webapi.py").read_text("utf-8")
        self.assertLess(api.index('return h._send(401, {"error": "inicia sesión"})'),
                        api.index('"/api/piloto/encuesta/retirar"'), "retirar exige sesión")

    def test_retencion_sin_definir_no_borra_nada(self):
        db.execute("INSERT INTO survey_responses(id, user_id, survey, answers, skipped, at) VALUES ('o1', 'u1', 'dia14', '{}', 0, ?)", (T0,))
        with mock.patch.dict(os.environ, {"CRYPTO_RADAR_PILOT_RETENTION_DAYS": ""}):
            self.assertEqual(piloto.purge(now=T0 + 400 * DAY)["borrado"], False)
        self.assertIsNotNone(db.one("SELECT id FROM survey_responses WHERE id = 'o1'", ()))
        with mock.patch.dict(os.environ, ON):
            self.assertTrue(any("Retención" in a for a in piloto.report(now=T0, data=([], {}, [], {}))["avisos"]))

    def test_retencion_definida_borra_solo_lo_antiguo_del_piloto(self):
        db.execute("INSERT INTO survey_responses(id, user_id, survey, answers, skipped, at) VALUES ('o1', 'u1', 'dia14', '{}', 0, ?)", (T0,))
        db.execute("INSERT INTO survey_responses(id, user_id, survey, answers, skipped, at) VALUES ('n1', 'u1', 'dia30', '{}', 0, ?)", (T0 + 300 * DAY,))
        for i, (a, at) in enumerate((("visit", T0), ("tab:dash", T0), ("login", T0), ("visit", T0 + 300 * DAY))):
            db.execute("INSERT INTO activity(id, user_id, at, action) VALUES (?, 'u1', ?, ?)", (f"a{i}", at, a))
        with mock.patch.dict(os.environ, {"CRYPTO_RADAR_PILOT_RETENTION_DAYS": "180"}):
            r = piloto.purge(now=T0 + 365 * DAY)
        self.assertEqual((r["respuestas"], r["eventos"]), (1, 2))
        left = {x["id"] for x in db.all_("SELECT id FROM activity", ())}
        self.assertEqual(left, {"a2", "a3"})


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1, argv=[sys.argv[0]] + [a for a in sys.argv[1:] if a != "-v"])
