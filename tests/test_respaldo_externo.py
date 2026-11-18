"""Respaldos independientes (radar/respaldo_externo.py, auditoría correctiva H5).

    python3 tests/test_respaldo_externo.py                                  # sin PostgreSQL: firma, retención, S3 simulado
    TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/crtest python3 tests/test_respaldo_externo.py
        # además: copia de una base PostgreSQL 16 real → cifrado age → destino externo → simulacro de restauración en
        # una base PostgreSQL 16 vacía (las bases se crean y se borran en la prueba)
Necesita el programa «age» (y «age-keygen») en el PATH para las pruebas de cifrado.
"""
import hashlib
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CRYPTO_RADAR_HOME", tempfile.mkdtemp(prefix="cr-offsite-home-"))
from radar import respaldo_externo as rx  # noqa: E402

KEY = "clave de firma de copias para pruebas 0123456789"
HAS_AGE = bool(shutil.which("age") and shutil.which("age-keygen"))
PG = os.environ.get("TEST_DATABASE_URL")


def keypair(d):
    p = Path(d) / f"id-{uuid.uuid4().hex[:6]}.txt"
    subprocess.run(["age-keygen", "-o", str(p)], check=True, capture_output=True)
    pub = next(ln.split(": ")[1] for ln in p.read_text().splitlines() if ln.startswith("# public key: "))
    return p, pub


class Recorder(http.server.BaseHTTPRequestHandler):
    """Servicio de latidos de prueba: registra las rutas que recibe."""
    hits = []

    def _ok(self):
        Recorder.hits.append(self.path)
        self.send_response(200); self.end_headers(); self.wfile.write(b"OK")

    do_GET = do_POST = _ok

    def log_message(self, *a):
        pass


def serve(handler):
    s = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s, f"http://127.0.0.1:{s.server_address[1]}"


class FakeS3(http.server.BaseHTTPRequestHandler):
    """S3 mínimo (ruta /bucket/clave) que COMPRUEBA la firma SigV4 de cada petición, como haría el proveedor."""
    store, secret, bad = {}, "SECRETO-DE-PRUEBA", []

    def _check(self, body):
        h = {k.lower(): v for k, v in self.headers.items()}
        auth = h.get("authorization", "")
        signed = auth.split("SignedHeaders=")[1].split(",")[0].split(";")
        url = f"http://{h['host']}{self.path}"
        if hashlib.sha256(body).hexdigest() != h.get("x-amz-content-sha256"):
            FakeS3.bad.append("payload"); return False
        mine = rx.sigv4_headers(self.command, url, {k: h[k] for k in signed if k not in ("host", "x-amz-date", "x-amz-content-sha256")},
                                h["x-amz-content-sha256"], "AK", FakeS3.secret, "us-east-1", h["x-amz-date"])
        if mine["authorization"] != auth:
            FakeS3.bad.append(self.path); return False
        return True

    def _reply(self, code, body=b""):
        self.send_response(code); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_PUT(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if not self._check(body):
            return self._reply(403)
        FakeS3.store[urllib.parse.unquote(self.path.split("/", 2)[2])] = body
        self._reply(200)

    def do_GET(self):
        if not self._check(b""):
            return self._reply(403)
        u = urllib.parse.urlsplit(self.path)
        parts = u.path.split("/", 2)
        if len(parts) < 3 or not parts[2]:
            q = dict(urllib.parse.parse_qsl(u.query))
            keys = sorted(k for k in FakeS3.store if k.startswith(q.get("prefix", "")))
            xml = '<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">' + \
                  "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys) + "</ListBucketResult>"
            return self._reply(200, xml.encode())
        k = urllib.parse.unquote(parts[2])
        return self._reply(200, FakeS3.store[k]) if k in FakeS3.store else self._reply(404)

    def do_DELETE(self):
        if not self._check(b""):
            return self._reply(403)
        FakeS3.store.pop(urllib.parse.unquote(self.path.split("/", 2)[2]), None)
        self._reply(204)

    def log_message(self, *a):
        pass


class Firma(unittest.TestCase):
    def test_ejemplos_publicados_por_aws(self):
        """Vectores de la documentación de AWS (Signature V4 para S3): GET de objeto y lista con parámetros."""
        empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        ak, sk = "AKIAIOSFODNN7EXAMPLE", "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        h = rx.sigv4_headers("GET", "https://examplebucket.s3.amazonaws.com/test.txt", {"Range": "bytes=0-9"}, empty,
                             ak, sk, "us-east-1", "20130524T000000Z")
        self.assertTrue(h["authorization"].endswith("Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"))
        h = rx.sigv4_headers("GET", "https://examplebucket.s3.amazonaws.com/?max-keys=2&prefix=J", {}, empty,
                             ak, sk, "us-east-1", "20130524T000000Z")
        self.assertTrue(h["authorization"].endswith("Signature=34b48302e7b5fa45bde8084f4b7868a86f0a534bc59db6670ed5711ef69dc6f7"))


class Desactivado(unittest.TestCase):
    def test_nada_sin_activacion_explicita(self):
        for f in (lambda: rx.job(env={}), lambda: rx.drill("x", "y", env={}), lambda: rx.prune(env={})):
            r = f()
            self.assertEqual((r["ok"], r["desactivado"]), (False, True))
        r = rx.prune(env={"CRYPTO_RADAR_BACKUP_JOB": "1"})
        self.assertTrue(r["desactivado"], "la poda necesita además CRYPTO_RADAR_BACKUP_PRUNE=1")
        p = subprocess.run([sys.executable, str(ROOT / "main.py"), "offsite", "job"], capture_output=True, text=True,
                           env={k: v for k, v in os.environ.items() if not k.startswith("CRYPTO_RADAR_BACKUP")}, timeout=60)
        self.assertEqual(p.returncode, 3)
        self.assertIn('"desactivado": true', p.stdout)

    def test_sin_programacion_activa_en_el_repositorio(self):
        wf = ROOT / ".github" / "workflows"
        if wf.exists():
            for f in wf.iterdir():
                self.assertNotIn("offsite", f.read_text("utf-8"), f"{f.name} no debe programar respaldos")
        self.assertTrue((ROOT / "docs" / "plantillas" / "respaldo-externo.cron").exists())

    def test_rechaza_claves_privadas_como_destinatario(self):
        with self.assertRaises(rx.OffsiteError):
            rx.recipients({"CRYPTO_RADAR_BACKUP_AGE_RECIPIENTS": "AGE-SECRET-KEY-1QQQQ"})
        with self.assertRaises(rx.OffsiteError):
            rx.recipients({})


class Retencion(unittest.TestCase):
    def test_diaria_semanal_mensual(self):
        import datetime as dt
        t0 = dt.datetime(2026, 1, 1, 3, tzinfo=dt.timezone.utc)
        names = [f"crypto-radar/crypto-radar-{(t0 + dt.timedelta(days=i)).strftime('%Y%m%d-%H%M%S')}.tar.age"
                 for i in range(400)]
        keep, drop = rx.retention_plan(names, daily=14, weekly=8, monthly=12)
        self.assertIn(names[-1], keep, "la más reciente siempre")
        self.assertTrue(all(n in keep for n in names[-14:]), "los últimos 14 días")
        self.assertLessEqual(len(keep), 14 + 8 + 12)
        self.assertEqual(len(keep) + len(drop), 400)
        months = {rx.stamp_of(n).strftime("%Y%m") for n in keep}
        self.assertGreaterEqual(len(months), 12, "una por mes durante 12 meses")
        self.assertEqual(rx.retention_plan(names[:1]), ([names[0]], []))


@unittest.skipUnless(HAS_AGE, "sin age")
class CadenaCompleta(unittest.TestCase):
    """Copia → cifrado → destino → simulacro, con destino carpeta y con S3 simulado. Origen y destino del simulacro:
    PostgreSQL 16 si hay TEST_DATABASE_URL; si no, SQLite."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="cr-offsite-"))
        cls.id1, cls.pub1 = keypair(cls.tmp)          # clave del propietario
        cls.id2, cls.pub2 = keypair(cls.tmp)          # clave de recuperación (custodia separada)
        cls.idx, _ = keypair(cls.tmp)                 # una clave que NO es destinataria
        cls.hb, cls.hb_url = serve(Recorder)
        cls.dbs = []
        cls.src = cls.new_db("src", seed=True)

    @classmethod
    def tearDownClass(cls):
        cls.hb.shutdown()
        if PG:
            import psycopg
            with psycopg.connect(PG, autocommit=True) as c:
                for n in cls.dbs:
                    c.execute(f'DROP DATABASE IF EXISTS "{n}" WITH (FORCE)')
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @classmethod
    def new_db(cls, tag, seed=False):
        if PG:
            import psycopg
            name = f"cr_offsite_{tag}_{uuid.uuid4().hex[:8]}"
            with psycopg.connect(PG, autocommit=True) as c:
                c.execute(f'CREATE DATABASE "{name}"')
            cls.dbs.append(name)
            url = PG.rsplit("/", 1)[0] + "/" + name
        else:
            url = str(cls.tmp / f"{tag}-{uuid.uuid4().hex[:6]}.db")
        if seed:
            env = dict(os.environ, CRYPTO_RADAR_HOME=str(cls.tmp / "home"))
            code = ("import sys,time,json; from radar import db; db.init(); "
                    "[db.execute('INSERT INTO users(id,email,pw_hash,created_at) VALUES (?,?,?,?)',(f'u{i}',f'persona{i}@correo.test','h',time.time())) for i in range(25)]; "
                    "db.upsert_kv('latest.json', {'verdict':'x'*500})")
            if PG:
                env["DATABASE_URL"] = url
                (cls.tmp / "home").mkdir(exist_ok=True)
            else:
                env.pop("DATABASE_URL", None)
                env["CRYPTO_RADAR_DATA"] = str(Path(url).parent / ("data-" + Path(url).stem))
                url = str(Path(env["CRYPTO_RADAR_DATA"]) / "app.db")
                Path(env["CRYPTO_RADAR_DATA"]).mkdir(parents=True, exist_ok=True)
                env["CRYPTO_RADAR_ALLOW_SQLITE"] = "1"
            r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stderr
        return url

    def env(self, dest, **kw):
        e = {"CRYPTO_RADAR_BACKUP_JOB": "1", "CRYPTO_RADAR_BACKUP_DEST": dest,
             "CRYPTO_RADAR_BACKUP_AGE_RECIPIENTS": f"{self.pub1} {self.pub2}",
             "CRYPTO_RADAR_BACKUP_HEARTBEAT_URL": self.hb_url + "/copia",
             "CRYPTO_RADAR_BACKUP_DRILL_HEARTBEAT_URL": self.hb_url + "/simulacro"}
        e.update(kw)
        return e

    def setUp(self):
        Recorder.hits.clear()
        self._env = dict(os.environ)
        os.environ["CRYPTO_RADAR_BACKUP_KEY"] = KEY

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._env)

    def run_job(self, env):
        os.environ.update(env)
        return rx.job(env=env, source=self.src)

    def test_1_copia_cifrada_en_destino_externo_y_simulacro(self):
        dest = self.tmp / "externo-1"
        env = self.env(f"dir:{dest}")
        r = self.run_job(env)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["filas"]["users"], 25)
        self.assertEqual(Recorder.hits, ["/copia"], "latido de éxito")
        blob = (dest / r["objeto"]).read_bytes()
        self.assertTrue(blob.startswith(b"age-encryption.org/v1"))
        self.assertNotIn(b"persona1@correo.test", blob, "en el destino no hay datos en claro")
        side = json.loads((dest / (r["objeto"] + ".json")).read_text())
        self.assertNotIn("persona", json.dumps(side))
        self.assertEqual(side["sha256"], hashlib.sha256(blob).hexdigest())
        target = self.new_db("simulacro")
        d = rx.drill(target, self.id1, env=env)
        self.assertTrue(d["ok"], d)
        self.assertEqual(d["filas"]["users"], 25)
        self.assertFalse(d["vieja"])
        self.assertEqual(Recorder.hits, ["/copia", "/simulacro"])

    def test_2_recuperacion_con_la_segunda_clave_y_rechazo_de_una_ajena(self):
        dest = self.tmp / "externo-2"
        env = self.env(f"dir:{dest}")
        self.assertTrue(self.run_job(env)["ok"])
        self.assertTrue(rx.drill(self.new_db("rec"), self.id2, env=env)["ok"], "la clave de custodia también descifra")
        Recorder.hits.clear()
        bad = rx.drill(self.new_db("ajena"), self.idx, env=env)
        self.assertFalse(bad["ok"])
        self.assertIn("descifrar", bad["error"])
        self.assertEqual(Recorder.hits, ["/simulacro/fail"], "el fallo avisa")

    def test_3_alteracion_detectada(self):
        dest = self.tmp / "externo-3"
        env = self.env(f"dir:{dest}")
        r = self.run_job(env)
        p = dest / r["objeto"]
        b = bytearray(p.read_bytes()); b[-10] ^= 1; p.write_bytes(bytes(b))
        d = rx.drill(self.new_db("alterada"), self.id1, env=env)
        self.assertFalse(d["ok"])
        self.assertIn("sidecar", d["error"])
        sp = dest / (r["objeto"] + ".json")
        side = json.loads(sp.read_text()); side["sha256"] = hashlib.sha256(bytes(b)).hexdigest()
        sp.write_text(json.dumps(side))
        d = rx.drill(self.new_db("alterada2"), self.id1, env=env)
        self.assertIn("firma del sidecar", d["error"], "recalcular el hash sin la clave no basta")

    def test_4_fallo_de_la_copia_avisa(self):
        env = self.env(f"dir:{self.tmp / 'externo-4'}")
        os.environ.update(env)
        r = rx.job(env=env, source="postgresql://nadie@127.0.0.1:1/nada" if PG else str(self.tmp / "no" / "existe.db"))
        self.assertFalse(r["ok"])
        self.assertEqual(Recorder.hits, ["/copia/fail"])
        self.assertNotIn("nadie", json.dumps(r), "el aviso no incluye la URL de la base")

    def test_5_simulacro_nunca_sobre_produccion_ni_base_con_datos(self):
        env = self.env(f"dir:{self.tmp / 'externo-5'}")
        self.assertTrue(self.run_job(env)["ok"])
        d = rx.drill(self.src, self.id1, env=dict(env, DATABASE_URL=self.src))
        self.assertIn("producción", d["error"])
        d = rx.drill(self.src, self.id1, env=env)
        self.assertFalse(d["ok"])
        self.assertIn("no está vacío", d["error"])

    def test_6_copia_vieja_avisa(self):
        import time
        env = self.env(f"dir:{self.tmp / 'externo-6'}")
        self.assertTrue(self.run_job(env)["ok"])
        Recorder.hits.clear()
        d = rx.drill(self.new_db("vieja"), self.id1, env=env, now=time.time() + 3 * 86400)
        self.assertTrue(d["ok"] and d["vieja"])
        self.assertEqual(Recorder.hits, ["/simulacro/fail"], "una copia de más de 26 h es una alerta")

    def test_7_s3_compatible_con_firma_comprobada_y_poda(self):
        FakeS3.store.clear(); FakeS3.bad.clear()
        s3, url = serve(FakeS3)
        try:
            env = self.env("s3", CRYPTO_RADAR_BACKUP_S3_ENDPOINT=url, CRYPTO_RADAR_BACKUP_S3_BUCKET="copias",
                           CRYPTO_RADAR_BACKUP_S3_ACCESS_KEY="AK", CRYPTO_RADAR_BACKUP_S3_SECRET_KEY=FakeS3.secret)
            r = self.run_job(env)
            self.assertTrue(r["ok"], r)
            self.assertEqual(FakeS3.bad, [], "toda petición llegó con una firma SigV4 válida")
            self.assertIn(r["objeto"], FakeS3.store)
            self.assertTrue(rx.drill(self.new_db("s3"), self.id1, env=env)["ok"])
            old = "crypto-radar/crypto-radar-20200101-000000.tar.age"
            FakeS3.store[old] = b"x"; FakeS3.store[old + ".json"] = b"{}"
            p = rx.prune(env=dict(env, CRYPTO_RADAR_BACKUP_PRUNE="1", CRYPTO_RADAR_BACKUP_KEEP_DAILY="1",
                                  CRYPTO_RADAR_BACKUP_KEEP_WEEKLY="1", CRYPTO_RADAR_BACKUP_KEEP_MONTHLY="1"))
            self.assertEqual((p["borrar"], p["simulado"]), ([old], True))
            self.assertIn(old, FakeS3.store, "por defecto la poda solo simula")
            rx.prune(env=dict(env, CRYPTO_RADAR_BACKUP_PRUNE="1", CRYPTO_RADAR_BACKUP_KEEP_DAILY="1",
                              CRYPTO_RADAR_BACKUP_KEEP_WEEKLY="1", CRYPTO_RADAR_BACKUP_KEEP_MONTHLY="1"), dry_run=False)
            self.assertNotIn(old, FakeS3.store)
            self.assertIn(r["objeto"], FakeS3.store)
            bad = rx.S3Dest(url, "copias", "AK", "otra-clave")
            with self.assertRaises(rx.OffsiteError):
                bad.put("x", b"y")
        finally:
            s3.shutdown()


if __name__ == "__main__":
    unittest.main(verbosity=2 if "-v" in sys.argv else 1, argv=[sys.argv[0]] + [a for a in sys.argv[1:] if a != "-v"])
