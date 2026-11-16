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
    def setUp(self):
        health._reset_probe()          # una comprobación colgada de otra prueba no debe contar para esta

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
        """Todo trabajo de fondo que escribe resultados corre dentro de `with leader.job()` (fencing por generación)."""
        import ast
        src = (ROOT / "radar" / "server.py").read_text("utf-8")
        self.assertIn("if not leader.is_leader():", src[src.index("def scheduler"):src.index("def _f(")])
        tree = ast.parse(src)

        def calls_inside_job(fn_name):
            fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == fn_name)
            inside, outside = set(), set()

            def visit(node, guarded):
                if isinstance(node, ast.With) and any(
                        isinstance(i.context_expr, ast.Call) and ast.unparse(i.context_expr.func) == "leader.job"
                        for i in node.items):
                    guarded = True
                if isinstance(node, ast.Call):
                    (inside if guarded else outside).add(ast.unparse(node.func))
                for ch in ast.iter_child_nodes(node):
                    visit(ch, guarded)
            visit(fn, False)
            return inside, outside

        ins, outs = calls_inside_job("scheduler")
        for f in ("memes.run", "scanner.run_scan", "scanner.price_watch"):
            self.assertIn(f, ins, f"{f} debe ejecutarse dentro de leader.job()")
            self.assertNotIn(f, outs, f"{f} no puede ejecutarse fuera de leader.job()")
        ins, outs = calls_inside_job("paper_scheduler")
        for f in ("engine.step_live", "engine.init", "report.write"):
            self.assertIn(f, ins)
            self.assertNotIn(f, outs)
        ins, outs = calls_inside_job("_manual")
        self.assertIn("scanner.run_scan", ins)
        self.assertNotIn("scanner.run_scan", outs)
        tg = (ROOT / "radar" / "telegram_bot.py").read_text("utf-8")
        self.assertIn("if not leader.is_leader():", tg[tg.index("def poll_forever"):])


class EstadoPublico(unittest.TestCase):
    def test_estado_publico_sin_veredicto_ni_regimen(self):
        src = (ROOT / "radar" / "webapi.py").read_text("utf-8")
        blk = src[src.index('if p == "/api/public/status":'):src.index('if p == "/api/billing/status":')]
        for k in ('"verdict"', '"regime"', '"regime_label"'):
            self.assertNotIn(k, blk)


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "sin TEST_DATABASE_URL")
class LiderMultiproceso(unittest.TestCase):
    """Dos procesos reales compiten por el candado sobre PostgreSQL 16 (como dos instancias de Render en un despliegue)."""

    def setUp(self):
        import psycopg
        self.url = os.environ["TEST_DATABASE_URL"]
        self.db = psycopg.connect(self.url, autocommit=True)
        self.db.execute("DROP TABLE IF EXISTS leader_jobs")
        self.db.execute("CREATE TABLE leader_jobs(worker TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)")
        self.procs = {}

    def tearDown(self):
        for p in self.procs.values():
            if p.poll() is None:
                p.kill()
            p.wait(10)
        self.db.execute("DROP TABLE IF EXISTS leader_jobs")
        self.db.close()

    def spawn(self, name):
        import subprocess
        env = dict(os.environ, DATABASE_URL=self.url, CRYPTO_RADAR_LEADER_RETRY_S="0.5",
                   CRYPTO_RADAR_HOME=tempfile.mkdtemp(prefix="cr-lider-"))
        p = subprocess.Popen([sys.executable, str(ROOT / "tests" / "lider_worker.py"), name], env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.assertEqual(p.stdout.readline().strip(), "listo")
        self.procs[name] = p
        return p

    def rows(self):
        return self.db.execute("SELECT worker, at FROM leader_jobs ORDER BY at").fetchall()

    def wait_for(self, worker, since=None, timeout=15):
        t0 = time.time()
        while time.time() - t0 < timeout:
            q = "SELECT count(*) FROM leader_jobs WHERE worker = %s" + (" AND at > %s" if since else "")
            if self.db.execute(q, (worker, since) if since else (worker,)).fetchone()[0] > 0:
                return True
            time.sleep(0.2)
        return False

    def holder_pid(self):
        r = self.db.execute("SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted "
                            "AND ((classid::bigint << 32) | objid::bigint) = %s", (leader.LOCK_ID,)).fetchone()
        return r and r[0]

    def assert_no_overlap(self, rows):
        """Cada cambio de líder es definitivo hasta el siguiente: nunca se intercalan trabajos de dos instancias."""
        runs = [w for i, (w, _) in enumerate(rows) if i == 0 or rows[i - 1][0] != w]
        # con dos instancias, el líder solo cambia por caída o corte: a lo sumo un relevo por evento provocado
        self.assertLessEqual(len(runs), 3, f"líderes intercalados: {runs}")
        return runs

    def test_dos_instancias_un_solo_lider(self):
        self.spawn("a"); self.spawn("b")
        time.sleep(4)
        workers = {w for w, _ in self.rows()}
        self.assertEqual(len(workers), 1, f"trabajaron {workers}")
        self.assertGreater(len(self.rows()), 5)

    def test_caida_del_lider_y_traspaso(self):
        self.spawn("a")
        self.assertTrue(self.wait_for("a"))
        self.spawn("b")
        time.sleep(2)
        self.assertEqual({w for w, _ in self.rows()}, {"a"}, "b no trabaja mientras a viva")
        self.procs["a"].kill(); self.procs["a"].wait(10)            # el líder muere sin cerrar nada (SIGKILL)
        t_kill = self.db.execute("SELECT clock_timestamp()").fetchone()[0]
        self.assertTrue(self.wait_for("b", since=t_kill), "b toma el relevo")
        rows = self.rows()
        self.assertFalse([1 for w, at in rows if w == "a" and at > t_kill], "a no trabaja después de morir")
        self.assertEqual(self.assert_no_overlap(rows), ["a", "b"])

    def test_sesion_terminada_en_la_base_equivale_a_lease_vencido(self):
        self.spawn("a")
        self.assertTrue(self.wait_for("a"))
        self.spawn("b")
        time.sleep(1)
        pid = self.holder_pid()
        self.assertIsNotNone(pid)
        self.db.execute("SELECT pg_terminate_backend(%s)", (pid,))  # red caída, reinicio o suspensión de Neon
        t_cut = self.db.execute("SELECT clock_timestamp()").fetchone()[0]
        deadline = time.time() + 15
        while time.time() < deadline:
            rows = self.rows()
            if any(at > t_cut for _, at in rows) and len({w for w, at in rows if at > t_cut}) >= 1:
                break
            time.sleep(0.3)
        time.sleep(2)
        rows = self.rows()
        after = [(w, at) for w, at in rows if at > t_cut]
        self.assertTrue(after, "alguien retoma el trabajo")
        self.assert_no_overlap(rows)
        # el proceso «a» sigue vivo: recuperación cuando el nuevo líder muere
        new = after[-1][0]
        if new != "a":
            self.procs[new].kill(); self.procs[new].wait(10)
            t2 = self.db.execute("SELECT clock_timestamp()").fetchone()[0]
            self.assertTrue(self.wait_for("a", since=t2), "la instancia que perdió la sesión vuelve a ser líder")
        self.assert_no_overlap(self.rows())

    def test_confirm_detecta_sesion_perdida_en_proceso(self):
        import psycopg
        os.environ["DATABASE_URL"] = self.url
        try:
            from radar import db as _db
            with mock.patch.object(_db, "IS_PG", True), mock.patch.object(_db, "URL", self.url):
                c = leader._try_acquire(self.url)
                self.assertIsNotNone(c)
                leader._state.update(conn=c, leader=True, since=time.time())
                self.assertTrue(leader.confirm())
                pid = c.execute("SELECT pg_backend_pid()").fetchone()[0]
                self.db.execute("SELECT pg_terminate_backend(%s)", (pid,))
                time.sleep(0.3)
                self.assertFalse(leader.confirm(), "con la sesión cortada ya no es líder")
                self.assertFalse(leader.is_leader())
        finally:
            os.environ.pop("DATABASE_URL", None)
            leader._state.update(conn=None, leader=False, since=None)


class ConexionesNeon(unittest.TestCase):
    """Auditoría correctiva H4 (docs/ARQUITECTURA_CONEXIONES_NEON.md)."""

    def test_el_lider_nunca_usa_el_pooler(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CRYPTO_RADAR_LEADER_DATABASE_URL", None)
            pooled = "postgresql://u:p@ep-abc-123-pooler.us-east-2.aws.neon.tech/db?sslmode=require"
            self.assertEqual(leader.leader_url(pooled),
                             "postgresql://u:p@ep-abc-123.us-east-2.aws.neon.tech/db?sslmode=require")
            direct = "postgresql://u:p@ep-abc-123.us-east-2.aws.neon.tech/db?sslmode=require"
            self.assertEqual(leader.leader_url(direct), direct)
            os.environ["CRYPTO_RADAR_LEADER_DATABASE_URL"] = "postgresql://l:p@ep-lider-pooler.neon.tech/db"
            self.assertEqual(leader.leader_url(pooled), "postgresql://l:p@ep-lider.neon.tech/db",
                             "la URL propia del líder también se corrige al directo")
            os.environ.pop("CRYPTO_RADAR_LEADER_DATABASE_URL")

    def test_salud_reutiliza_una_sola_conexion(self):
        """Cada comprobación de /healthz usaba un hilo nuevo y, por tanto, una conexión nueva a la base."""
        from radar import db
        health._reset_probe()
        seen = []
        with mock.patch.object(db, "one", lambda q, p=(): seen.append(threading.current_thread().name) or {"ok": 1}):
            for _ in range(5):
                self.assertEqual(health._check_db()[0], True)
        self.assertEqual(set(seen), {"salud-db"}, "siempre el mismo hilo (misma conexión por hilo de db.py)")
        before = threading.active_count()
        gate = threading.Event()
        with mock.patch.object(health, "DB_TIMEOUT_S", 0.2), \
                mock.patch.object(db, "one", lambda q, p=(): gate.wait(5) and {"ok": 1}):
            self.assertEqual(health._check_db(), (False, None))      # colgada
            self.assertEqual(health._check_db(), (False, None))      # no abre otra mientras sigue colgada
            self.assertLessEqual(threading.active_count(), before)
            gate.set()
            time.sleep(0.3)
        self.assertEqual(health._check_db()[0], True, "se recupera cuando la base vuelve")
        gate2 = threading.Event()
        with mock.patch.object(health, "DB_TIMEOUT_S", 0.2), mock.patch.object(health, "PROBE_ABANDON_S", 0.5), \
                mock.patch.object(db, "one", lambda q, p=(): gate2.wait(5) and {"ok": 1}):
            self.assertEqual(health._check_db(), (False, None))
            time.sleep(0.6)
            gate2.set()                                         # el hilo colgado se abandonó; el nuevo responde
            self.assertEqual(health._check_db()[0], True)

    def test_aviso_de_arranque_con_pooler_sin_mostrar_la_url(self):
        from radar import db
        w = db.endpoint_warning("postgresql://u:Secreta99@ep-x-pooler.neon.tech/db")
        self.assertIn("pooler", w)
        self.assertNotIn("Secreta99", w)
        self.assertIsNone(db.endpoint_warning("postgresql://u:p@ep-x.neon.tech/db"))
        src = (ROOT / "radar" / "server.py").read_text("utf-8")
        self.assertLess(src.index("db.endpoint_warning()"), src.index("db.init()  "), "el aviso sale antes de init()")


@unittest.skipUnless(os.environ.get("TEST_DATABASE_URL"), "sin TEST_DATABASE_URL")
class FencingGeneracion(unittest.TestCase):
    """Auditoría correctiva H3: fencing transaccional por generación (radar/leader.py, radar/db.py).

    Un disparador registra en fence_log cada escritura CONFIRMADA de kv «fence_test» junto con la generación vigente en
    leader_epoch DENTRO de la misma transacción. Invariantes que se comprueban en cada prueba:
    - toda escritura confirmada lleva la generación vigente al confirmarse (nadie escribe con una vencida);
    - en orden de confirmación, la generación nunca baja (una instancia antigua nunca sobrescribe a una nueva).
    Reinicio real de PostgreSQL: TEST_PG_RESTART_CMD (p. ej. «su postgres -c '/usr/lib/postgresql/16/bin/pg_ctl -D ... restart -m fast'»).
    """
    TRIGGER = """
        CREATE OR REPLACE FUNCTION fence_log_fn() RETURNS trigger AS $$
        BEGIN
          IF NEW.name = 'fence_test' THEN
            INSERT INTO fence_log(worker, gen, phase, n, epoch)
            SELECT NEW.value::jsonb->>'worker', (NEW.value::jsonb->>'gen')::bigint, (NEW.value::jsonb->>'phase')::int,
                   (NEW.value::jsonb->>'n')::int, (SELECT generation FROM leader_epoch WHERE id = 1);
          END IF;
          RETURN NEW;
        END $$ LANGUAGE plpgsql"""

    def setUp(self):
        self.url = os.environ["TEST_DATABASE_URL"]
        self.connect()
        for q in ("DROP TABLE IF EXISTS leader_jobs", "DROP TABLE IF EXISTS fence_log",
                  "CREATE TABLE leader_jobs(worker TEXT NOT NULL, at TIMESTAMPTZ NOT NULL)",
                  "CREATE TABLE fence_log(seq BIGSERIAL PRIMARY KEY, worker TEXT, gen BIGINT, phase INT, n INT, "
                  "epoch BIGINT, at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp())",
                  "CREATE TABLE IF NOT EXISTS kv (name TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at DOUBLE PRECISION NOT NULL)",
                  "CREATE TABLE IF NOT EXISTS leader_epoch (id INTEGER PRIMARY KEY, generation BIGINT NOT NULL, holder TEXT, "
                  "acquired_at DOUBLE PRECISION)",
                  "DELETE FROM kv WHERE name = 'fence_test'", self.TRIGGER,
                  "DROP TRIGGER IF EXISTS fence_log_t ON kv",
                  "CREATE TRIGGER fence_log_t AFTER INSERT OR UPDATE ON kv FOR EACH ROW EXECUTE FUNCTION fence_log_fn()"):
            self.db.execute(q)
        self.procs, self.logs, self.files = {}, {}, []

    def connect(self):
        import psycopg
        for _ in range(60):
            try:
                self.db = psycopg.connect(self.url, autocommit=True)
                return
            except psycopg.OperationalError:
                time.sleep(0.5)
        raise RuntimeError("PostgreSQL no vuelve")

    def q(self, sql, params=()):
        import psycopg
        for attempt in range(3):
            try:
                cur = self.db.execute(sql, params)
                return cur.fetchall() if cur.description else []
            except psycopg.OperationalError:
                if attempt == 2:
                    raise
                self.connect()

    def tearDown(self):
        for p in self.procs.values():
            if p.poll() is None:
                p.kill()
            p.wait(10)
        for f in self.files:
            f.close()
        for q in ("DROP TRIGGER IF EXISTS fence_log_t ON kv", "DROP TABLE IF EXISTS fence_log",
                  "DROP TABLE IF EXISTS leader_jobs", "DELETE FROM kv WHERE name = 'fence_test'"):
            self.q(q)
        self.db.close()

    def spawn(self, name, mode="rapido", lento_s="3"):
        import subprocess
        log = Path(tempfile.mkdtemp(prefix="cr-fence-")) / f"{name}.log"
        env = dict(os.environ, DATABASE_URL=self.url, CRYPTO_RADAR_LEADER_RETRY_S="0.5", LENTO_S=lento_s,
                   CRYPTO_RADAR_HOME=str(log.parent))
        f = open(log, "w")
        p = subprocess.Popen([sys.executable, str(ROOT / "tests" / "lider_worker.py"), name, mode], env=env,
                             stdout=f, stderr=subprocess.STDOUT, text=True)
        self.procs[name], self.logs[name] = p, log
        self.files.append(f)
        t0 = time.time()
        while "listo" not in log.read_text() and time.time() - t0 < 15:
            time.sleep(0.1)
        return p

    def out(self, name):
        return self.logs[name].read_text()

    def fence_log(self):
        return self.q("SELECT seq, worker, gen, phase, n, epoch FROM fence_log ORDER BY seq")

    def wait_log(self, cond, timeout=20):
        t0 = time.time()
        while time.time() - t0 < timeout:
            rows = self.fence_log()
            if cond(rows):
                return rows
            time.sleep(0.1)
        self.fail(f"condición no alcanzada; registro: {self.fence_log()[-10:]}")

    def holder_pid(self):
        r = self.q("SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted "
                   "AND ((classid::bigint << 32) | objid::bigint) = %s", (leader.LOCK_ID,))
        return r[0][0] if r else None

    def assert_invariants(self, rows):
        self.assertTrue(rows, "no hubo escrituras")
        bad = [r for r in rows if r[2] != r[5]]
        self.assertFalse(bad, f"escrituras confirmadas con generación distinta de la vigente: {bad}")
        gens = [r[2] for r in rows]
        self.assertEqual(gens, sorted(gens), "una generación antigua escribió después de una nueva")

    def run_scenario(self, name):
        import subprocess
        env = dict(os.environ, DATABASE_URL=self.url, CRYPTO_RADAR_HOME=tempfile.mkdtemp(prefix="cr-fence-"))
        r = subprocess.run([sys.executable, str(ROOT / "tests" / "fence_escenarios.py"), name], env=env,
                           capture_output=True, text=True, timeout=90)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return json.loads(r.stdout.strip().splitlines()[-1])

    # 1 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_1_dos_procesos_compitiendo(self):
        self.spawn("a"); self.spawn("b")
        time.sleep(4)
        rows = self.fence_log()
        self.assertGreater(len(rows), 5)
        self.assertEqual(len({r[1] for r in rows}), 1, "solo escribe una instancia")
        self.assertEqual(len({r[2] for r in rows}), 1, "sin relevos, una sola generación")
        self.assert_invariants(rows)

    # 2 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_2_perdida_del_candado_durante_un_escaneo(self):
        self.spawn("a", "lento", "3")
        rows = self.wait_log(lambda rs: any(r[1] == "a" and r[3] == 1 for r in rs))
        n_cut = [r for r in rows if r[1] == "a" and r[3] == 1][-1][4]
        self.spawn("b", "lento", "3")
        self.db.execute("SELECT pg_terminate_backend(%s)", (self.holder_pid(),))     # a pierde el candado a mitad
        rows = self.wait_log(lambda rs: any(r[2] > rows[-1][2] for r in rs))           # alguien escribe con generación nueva
        time.sleep(4)                                                                  # a despierta e intenta la fase 2
        rows = self.fence_log()
        self.assertFalse([r for r in rows if r[1] == "a" and r[3] == 2 and r[4] == n_cut],
                         "el escaneo interrumpido no puede escribir su fase 2")
        self.assertIn(f"rechazada gen={rows[0][2]} fase=2 n={n_cut}", self.out("a"))
        self.assert_invariants(rows)

    # 3 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_3_recuperacion_del_nuevo_lider(self):
        self.spawn("a")
        rows = self.wait_log(lambda rs: any(r[1] == "a" for r in rs))
        self.spawn("b")
        self.procs["a"].kill(); self.procs["a"].wait(10)                             # SIGKILL: sin cerrar nada
        g_a = max(r[2] for r in self.fence_log() if r[1] == "a")
        rows = self.wait_log(lambda rs: sum(1 for r in rs if r[1] == "b") >= 5)
        self.assertTrue(all(r[2] > g_a for r in rows if r[1] == "b"), "el nuevo líder escribe con generación mayor")
        self.assertEqual(json.loads(self.q("SELECT value FROM kv WHERE name = 'fence_test'")[0][0])["worker"], "b")
        self.assert_invariants(rows)

    # 4 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_4_escritura_tardia_del_lider_antiguo(self):
        r = self.run_scenario("escritura_tardia")
        self.assertTrue(r["job_ok"])
        self.assertEqual((r["fase1"], r["nuevo"], r["tardia"]), ("ok", "ok", "rechazada"))
        self.assertEqual(r["kv"], {"worker": "nuevo", "gen": r["new"], "phase": 1}, "se conserva el resultado nuevo")
        self.assertFalse(r["sigue_lider"], "tras el rechazo, la instancia antigua deja de ser líder")
        self.assert_invariants(self.fence_log())

    # 5 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_5_sobrescritura_con_generacion_vencida(self):
        r = self.run_scenario("generacion_vencida")
        self.assertEqual((r["vigente"], r["anterior"], r["futura"]), ("ok", "rechazada", "rechazada"))
        self.assertEqual(r["before"], r["after"], "el valor no cambia")
        rows = self.fence_log()
        self.assertEqual(len(rows), 1)
        self.assert_invariants(rows)

    # 6 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    @unittest.skipUnless(os.environ.get("TEST_PG_RESTART_CMD"), "sin TEST_PG_RESTART_CMD (reinicio real de PostgreSQL)")
    def test_6_reinicio_de_postgresql(self):
        import subprocess
        self.spawn("a", "lento", "1"); self.spawn("b", "lento", "1")
        rows = self.wait_log(lambda rs: len(rs) >= 3)
        g_before = max(r[2] for r in rows)
        seq_before = rows[-1][0]
        subprocess.run(os.environ["TEST_PG_RESTART_CMD"], shell=True, check=True, timeout=60,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.connect()
        rows = self.wait_log(lambda rs: sum(1 for r in rs if r[0] > seq_before) >= 3, timeout=40)
        after = [r for r in rows if r[0] > seq_before]
        self.assertTrue(all(r[2] > g_before for r in after), "tras el reinicio solo escribe una generación nueva")
        self.assert_invariants(rows)
        for p in self.procs.values():
            self.assertIsNone(p.poll(), "las instancias sobreviven al reinicio de la base")

    # 7 ────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def test_7_caida_de_conexion_durante_la_transaccion(self):
        r = self.run_scenario("caida_conexion")
        self.assertEqual((r["v1"], r["v2"]), ("ok", "ok"))
        self.assertEqual((r["intentos"], r["pids_distintos"]), (2, 2), "un reintento en una conexión nueva")
        self.assertEqual(r["kv"]["phase"], 2)
        rows = self.fence_log()
        self.assertEqual([x[3] for x in rows], [1, 2], "la transacción cortada no dejó nada; el reintento escribió una vez")
        self.assert_invariants(rows)
        self.db.execute("DELETE FROM fence_log")
        r = self.run_scenario("caida_conexion_relevo")
        self.assertEqual((r["v1"], r["v2"]), ("ok", "rechazada"), "si otro tomó el relevo, el reintento se rechaza")
        self.assertEqual(r["kv"]["phase"], 1)
        self.assertEqual(r["epoch"], r["gen"] + 1)
        self.assertEqual([x[3] for x in self.fence_log()], [1])


class AtribucionYLanding(unittest.TestCase):
    """R-02 y R-03 (atribución de fuentes) y la página pública de la 2.1 sin promesas falsas (C-1 de la auditoría)."""

    def test_atribuciones_visibles(self):
        html = (ROOT / "web" / "index.html").read_text("utf-8")
        js = (ROOT / "web" / "app.js").read_text("utf-8")
        self.assertIn('<a href="https://www.coingecko.com/"', html)
        self.assertIn("Data provided by CoinGecko", html)
        self.assertIn("https://alternative.me/crypto/fear-and-greed-index/", html)
        self.assertIn("ATTR_FG", js[js.index("function renderDash"):])            # junto al dato de sentimiento

    def test_landing_publica_honesta(self):
        import re
        html = (ROOT / "web" / "landing.html").read_text("utf-8")
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"<(style|script)[\s\S]*?</\1>", "", html)))
        self.assertIn("Crypto Radar es una plataforma de análisis y monitoreo de criptomonedas. Sus modelos se encuentran "
                      "en evaluación y no existe una ventaja estadística consistente demostrada. La información no garantiza "
                      "resultados financieros.", text)
        for bad in ("fundador", "cupos", "días de prueba", "sin tarjeta", "Tarjeta de cualquier país", "+31", "+18",
                    "US$19", "US$29", "US$39", "checkout"):
            self.assertNotIn(bad.lower(), text.lower(), bad)
        self.assertNotRegex(html, r"<script>(?!</script>)", "la CSP de la 2.1 bloquea scripts en línea")
        self.assertIn('<script src="/static/landing-piloto.js"></script>', html)
        self.assertIn('href="/entrar"', html)
        self.assertNotIn("<form", html.lower())


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
