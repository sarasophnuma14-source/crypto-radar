"""Respaldos independientes: copia automática, cifrado, integridad, almacenamiento externo, retención, simulacro de
restauración y alertas (auditoría correctiva H5; diseño en docs/RESPALDOS_INDEPENDIENTES.md).

DESACTIVADO por defecto: ninguna orden hace nada sin CRYPTO_RADAR_BACKUP_JOB=1 (y la poda, además, sin
CRYPTO_RADAR_BACKUP_PRUNE=1). No hay ningún cron, workflow ni servicio que lo ejecute: la plantilla de programación está en
docs/plantillas/ y el propietario decide dónde y cuándo activarla.

Cadena de la copia (job):
  1. backup.create   copia lógica firmada con HMAC (CRYPTO_RADAR_BACKUP_KEY), lectura REPEATABLE READ.
  2. backup.verify   firma + SHA-256 + restauración de prueba en SQLite temporal.
  3. cifrado         tar → age con 1 o más destinatarios PÚBLICOS (CRYPTO_RADAR_BACKUP_AGE_RECIPIENTS). En la máquina
                     que copia no hay ninguna clave privada: quien la comprometa no puede leer copias anteriores.
  4. subida          a un almacenamiento AJENO a GitHub, Render y Neon (S3 compatible: Backblaze B2, Cloudflare R2,
                     AWS S3 en otra cuenta…; o una carpeta, p. ej. un disco externo). La clave de subida solo debe
                     poder ESCRIBIR: la retención la aplica el proveedor (bloqueo de objetos / ciclo de vida) o la
                     poda manual con otra clave.
  5. relectura       se descarga lo subido y se compara su SHA-256 con el local.
  6. latido          GET a CRYPTO_RADAR_BACKUP_HEARTBEAT_URL si todo fue bien; GET a …/fail si algo falló. El servicio
                     de latidos (externo) avisa si llega un fallo O si NO llega nada en el plazo: así también se
                     detecta que la copia dejó de ejecutarse.

Simulacro (drill): descarga la última copia, comprueba SHA-256 y la firma del sidecar, descifra con una clave PRIVADA
(archivo de identidad age que solo existe en la máquina del simulacro), verifica, restaura en una base PostgreSQL VACÍA,
compara fila a fila y emite su propio latido. Informa la antigüedad de la copia.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import hmac
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from . import backup

SIDE_FORMAT = "crypto-radar-offsite/1"
NAME_RE = re.compile(r"crypto-radar-(\d{8}-\d{6})(?:-\d+)?\.tar\.age$")


class OffsiteError(Exception):
    pass


def _e(env, k, default=""):
    return (env.get(k) or default).strip()


# ──────────────────────────────────────────────────────────────────────────────────────────────── destinos
class DirDest:
    """Carpeta (disco externo, NAS). También es el destino de las pruebas."""

    def __init__(self, root):
        self.root = Path(root)

    def put(self, name, data: bytes):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(p)

    def get(self, name) -> bytes:
        p = self.root / name
        if not p.exists():
            raise OffsiteError(f"no existe {name}")
        return p.read_bytes()

    def list(self, prefix=""):
        if not self.root.exists():
            return []
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")
                      if p.is_file() and not p.name.endswith(".part") and str(p.relative_to(self.root)).startswith(prefix))

    def delete(self, name):
        (self.root / name).unlink()


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _hm(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sigv4_headers(method, url, headers, payload_sha, access_key, secret_key, region, amz_date, service="s3"):
    """Firma AWS Signature Version 4 (la que aceptan S3, B2, R2 y MinIO). Devuelve las cabeceras a enviar.

    Implementada con la biblioteca estándar (sin boto3); comprobada con el ejemplo publicado por AWS en
    tests/test_respaldo_externo.py."""
    u = urllib.parse.urlsplit(url)
    date = amz_date[:8]
    h = {k.lower(): str(v).strip() for k, v in headers.items()}
    h["host"] = u.netloc
    h["x-amz-content-sha256"] = payload_sha
    h["x-amz-date"] = amz_date
    signed = ";".join(sorted(h))
    canon_headers = "".join(f"{k}:{h[k]}\n" for k in sorted(h))
    q = urllib.parse.parse_qsl(u.query, keep_blank_values=True)
    canon_query = "&".join(f"{urllib.parse.quote(k, safe='-_.~')}={urllib.parse.quote(v, safe='-_.~')}"
                           for k, v in sorted(q))
    canon = "\n".join([method, u.path or "/", canon_query, canon_headers, signed, payload_sha])
    scope = f"{date}/{region}/{service}/aws4_request"
    sts = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canon.encode()).hexdigest()])
    k = _hm(("AWS4" + secret_key).encode(), date)
    for part in (region, service, "aws4_request"):
        k = _hm(k, part)
    sig = hmac.new(k, sts.encode(), hashlib.sha256).hexdigest()
    h["authorization"] = f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, SignedHeaders={signed}, Signature={sig}"
    return h


class S3Dest:
    """Almacenamiento S3 compatible con direcciones de tipo ruta: ENDPOINT/BUCKET/clave."""

    def __init__(self, endpoint, bucket, access_key, secret_key, region="us-east-1", timeout=120):
        if not endpoint.startswith("https://") and not endpoint.startswith("http://127.0.0.1"):
            raise OffsiteError("el endpoint S3 debe usar https")
        self.endpoint, self.bucket = endpoint.rstrip("/"), bucket
        self.ak, self.sk, self.region, self.timeout = access_key, secret_key, region, timeout

    def _req(self, method, key="", query=None, data=b""):
        path = "/" + self.bucket + ("/" + urllib.parse.quote(key, safe="/-_.~") if key else "")
        url = self.endpoint + path + ("?" + urllib.parse.urlencode(sorted(query.items()), quote_via=urllib.parse.quote)
                                      if query else "")
        amz = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        h = sigv4_headers(method, url, {}, _sha256(data), self.ak, self.sk, self.region, amz)
        h.pop("host")
        req = urllib.request.Request(url, data=data if method == "PUT" else None, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise OffsiteError(f"S3 {method} {key or '(lista)'}: HTTP {e.code}") from None

    def put(self, name, data):
        self._req("PUT", name, data=data)

    def get(self, name):
        return self._req("GET", name)

    def list(self, prefix=""):
        out, token = [], None
        while True:
            q = {"list-type": "2", "prefix": prefix}
            if token:
                q["continuation-token"] = token
            root = ET.fromstring(self._req("GET", query=q))
            ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
            out += [c.findtext(ns + "Key") for c in root.findall(ns + "Contents")]
            token = root.findtext(ns + "NextContinuationToken")
            if not token:
                return sorted(out)

    def delete(self, name):
        self._req("DELETE", name)


def destination(env):
    kind = _e(env, "CRYPTO_RADAR_BACKUP_DEST")
    if kind.startswith("dir:"):
        return DirDest(kind[4:])
    if kind == "s3":
        need = ("CRYPTO_RADAR_BACKUP_S3_ENDPOINT", "CRYPTO_RADAR_BACKUP_S3_BUCKET",
                "CRYPTO_RADAR_BACKUP_S3_ACCESS_KEY", "CRYPTO_RADAR_BACKUP_S3_SECRET_KEY")
        miss = [k for k in need if not _e(env, k)]
        if miss:
            raise OffsiteError("faltan " + ", ".join(miss))
        return S3Dest(*(_e(env, k) for k in need), region=_e(env, "CRYPTO_RADAR_BACKUP_S3_REGION", "us-east-1"))
    raise OffsiteError("CRYPTO_RADAR_BACKUP_DEST debe ser «s3» o «dir:/ruta»")


# ──────────────────────────────────────────────────────────────────────────────────────────────── cifrado
def _age():
    exe = shutil.which("age")
    if not exe:
        raise OffsiteError("falta el programa «age» (https://age-encryption.org)")
    return exe


def recipients(env):
    r = [x.strip() for x in re.split(r"[\s,]+", _e(env, "CRYPTO_RADAR_BACKUP_AGE_RECIPIENTS")) if x.strip()]
    if not r:
        raise OffsiteError("falta CRYPTO_RADAR_BACKUP_AGE_RECIPIENTS (claves PÚBLICAS age1…)")
    bad = [x for x in r if not re.fullmatch(r"age1[0-9a-z]{58}", x)]
    if bad:
        raise OffsiteError("destinatario age no válido (se esperan claves públicas age1…; nunca una clave privada)")
    return r


def encrypt_dir(d: Path, recips) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        for p in sorted(Path(d).iterdir()):
            tf.add(p, arcname=f"{Path(d).name}/{p.name}")
    args = [_age(), "--encrypt"] + sum((["-r", r] for r in recips), [])
    r = subprocess.run(args, input=buf.getvalue(), capture_output=True, timeout=600)
    if r.returncode:
        raise OffsiteError("age no pudo cifrar")
    return r.stdout


def decrypt_to(blob: bytes, identity_file, out: Path) -> Path:
    r = subprocess.run([_age(), "--decrypt", "-i", str(identity_file)], input=blob, capture_output=True, timeout=600)
    if r.returncode:
        raise OffsiteError("age no pudo descifrar (identidad incorrecta o archivo alterado)")
    with tarfile.open(fileobj=io.BytesIO(r.stdout), mode="r") as tf:
        members = tf.getmembers()
        for m in members:                                     # nada de rutas absolutas, «..» ni enlaces
            if not m.isreg() and not m.isdir() or m.name.startswith("/") or ".." in Path(m.name).parts:
                raise OffsiteError("contenido inesperado en la copia")
        tops = {Path(m.name).parts[0] for m in members}
        if len(tops) != 1:
            raise OffsiteError("contenido inesperado en la copia")
        tf.extractall(out, members=members, filter="data")
    return Path(out) / tops.pop()


# ──────────────────────────────────────────────────────────────────────────────────────────────── latido
def ping(url, ok=True, note=""):
    """Avisa al servicio de latidos externo. Nunca envía datos de la base: solo «ok» o «fail» y una línea corta."""
    if not url:
        return False
    target = url if ok else url.rstrip("/") + "/fail"
    try:
        req = urllib.request.Request(target, data=note[:200].encode() if note else None,
                                     method="POST" if note else "GET")
        with urllib.request.urlopen(req, timeout=15):
            return True
    except Exception:
        return False


def _sidecar(name, blob, man, key, created):
    body = {"format": SIDE_FORMAT, "object": name, "sha256": _sha256(blob), "bytes": len(blob),
            "created_utc": created, "backup_format": man.get("format"),
            "rows": {t: v["rows"] for t, v in man["tables"].items()}}
    body["hmac_sha256"] = hmac.new(key, json.dumps(body, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    return body


def _check_sidecar(side, key):
    body = {k: v for k, v in side.items() if k != "hmac_sha256"}
    good = hmac.new(key, json.dumps(body, sort_keys=True).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(good, side.get("hmac_sha256") or ""):
        raise OffsiteError("firma del sidecar inválida")


# ──────────────────────────────────────────────────────────────────────────────────────────────── órdenes
def enabled(env):
    return _e(env, "CRYPTO_RADAR_BACKUP_JOB") == "1"


def job(env=None, source=None) -> dict:
    """Copia completa hasta el almacenamiento externo. Devuelve el informe; latido ok o fail."""
    env = os.environ if env is None else env
    if not enabled(env):
        return {"ok": False, "desactivado": True, "motivo": "CRYPTO_RADAR_BACKUP_JOB no es 1"}
    hb = _e(env, "CRYPTO_RADAR_BACKUP_HEARTBEAT_URL")
    t0 = time.time()
    try:
        recips = recipients(env)
        dest = destination(env)
        key = backup._key()
        src = source or backup.default_source()
        prefix = _e(env, "CRYPTO_RADAR_BACKUP_PREFIX", "crypto-radar/")
        with tempfile.TemporaryDirectory(prefix="cr-offsite-") as tmp:
            d = backup.create(src, tmp)
            diff = backup.compare(d, src)
            ver = backup.verify(d)
            man, _ = backup._load(d)
            blob = encrypt_dir(d, recips)
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        name = f"{prefix}crypto-radar-{stamp}.tar.age"
        side = _sidecar(name, blob, man, key, man["created_utc"])
        dest.put(name, blob)
        dest.put(name + ".json", json.dumps(side, indent=1).encode())
        back = dest.get(name)
        if _sha256(back) != side["sha256"]:
            raise OffsiteError("lo leído del destino no coincide con lo subido")
        out = {"ok": True, "objeto": name, "bytes": len(blob), "sha256": side["sha256"], "filas": side["rows"],
               "escrituras_durante_la_copia": bool(diff), "verificada": bool(ver.get("signed")),
               "segundos": round(time.time() - t0, 2)}
        out["latido"] = ping(hb, True)
        return out
    except Exception as e:
        msg = f"{type(e).__name__}: {e}" if isinstance(e, (OffsiteError, backup.BackupError)) else type(e).__name__
        return {"ok": False, "error": msg, "latido": ping(hb, False, "copia fallida: " + msg)}


def latest(dest, prefix=""):
    names = [n for n in dest.list(prefix) if NAME_RE.search(n)]
    return names[-1] if names else None


def stamp_of(name):
    m = NAME_RE.search(name)
    return dt.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").replace(tzinfo=dt.timezone.utc) if m else None


def drill(target, identity_file, env=None, name=None, now=None) -> dict:
    """Simulacro de restauración en una base VACÍA. Nunca sobre DATABASE_URL."""
    env = os.environ if env is None else env
    if not enabled(env):
        return {"ok": False, "desactivado": True, "motivo": "CRYPTO_RADAR_BACKUP_JOB no es 1"}
    hb = _e(env, "CRYPTO_RADAR_BACKUP_DRILL_HEARTBEAT_URL")
    t0 = time.time()
    try:
        if (env.get("DATABASE_URL") or "").strip() == str(target).strip():
            raise OffsiteError("el destino del simulacro es la base de producción (DATABASE_URL)")
        dest = destination(env)
        key = backup._key()
        name = name or latest(dest, _e(env, "CRYPTO_RADAR_BACKUP_PREFIX", "crypto-radar/"))
        if not name:
            raise OffsiteError("no hay copias en el destino")
        blob = dest.get(name)
        side = json.loads(dest.get(name + ".json"))
        _check_sidecar(side, key)
        if side.get("object") != name or _sha256(blob) != side.get("sha256"):
            raise OffsiteError("el objeto no coincide con su sidecar (alterado o incompleto)")
        with tempfile.TemporaryDirectory(prefix="cr-drill-") as tmp:
            d = decrypt_to(blob, identity_file, Path(tmp))
            backup.verify(d)
            rows = backup.restore(d, target)
            diff = backup.compare(d, target)
        if diff:
            raise OffsiteError("la base restaurada no coincide: " + "; ".join(diff))
        age_h = round(((now or time.time()) - stamp_of(name).timestamp()) / 3600, 1)
        max_h = float(_e(env, "CRYPTO_RADAR_BACKUP_MAX_AGE_H", "26"))
        out = {"ok": True, "objeto": name, "filas": rows, "antiguedad_h": age_h, "vieja": age_h > max_h,
               "segundos": round(time.time() - t0, 2)}
        out["latido"] = ping(hb, not out["vieja"], f"copia con {age_h} h" if out["vieja"] else "")
        return out
    except Exception as e:
        msg = f"{type(e).__name__}: {e}" if isinstance(e, (OffsiteError, backup.BackupError)) else type(e).__name__
        return {"ok": False, "error": msg, "latido": ping(hb, False, "simulacro fallido: " + msg)}


def retention_plan(names, daily=14, weekly=8, monthly=12):
    """Qué copias conservar: la última de cada uno de los `daily` días, `weekly` semanas ISO y `monthly` meses más
    recientes. La copia más reciente se conserva siempre. Devuelve (conservar, borrar), ambas ordenadas."""
    dated = sorted(((stamp_of(n), n) for n in names if stamp_of(n)), reverse=True)
    keep = set()
    if dated:
        keep.add(dated[0][1])
    for buckets, fn in ((daily, lambda t: t.date()), (weekly, lambda t: t.isocalendar()[:2]),
                        (monthly, lambda t: (t.year, t.month))):
        seen = []
        for t, n in dated:
            b = fn(t)
            if b not in seen:
                if len(seen) == buckets:
                    break
                seen.append(b)
                keep.add(n)
    all_ = [n for _, n in dated]
    return sorted(keep), sorted(n for n in all_ if n not in keep)


def prune(env=None, dry_run=True) -> dict:
    """Aplica retention_plan en el destino. Requiere CRYPTO_RADAR_BACKUP_PRUNE=1 y, por diseño, una clave distinta de la
    del job (la del job no debería poder borrar). Por defecto solo simula."""
    env = os.environ if env is None else env
    if not enabled(env) or _e(env, "CRYPTO_RADAR_BACKUP_PRUNE") != "1":
        return {"ok": False, "desactivado": True}
    dest = destination(env)
    names = [n for n in dest.list(_e(env, "CRYPTO_RADAR_BACKUP_PREFIX", "crypto-radar/")) if NAME_RE.search(n)]
    keep, drop = retention_plan(names, int(_e(env, "CRYPTO_RADAR_BACKUP_KEEP_DAILY", "14")),
                                int(_e(env, "CRYPTO_RADAR_BACKUP_KEEP_WEEKLY", "8")),
                                int(_e(env, "CRYPTO_RADAR_BACKUP_KEEP_MONTHLY", "12")))
    if not dry_run:
        for n in drop:
            dest.delete(n)
            dest.delete(n + ".json")
    return {"ok": True, "conservar": len(keep), "borrar": drop, "simulado": dry_run}


def cli(args) -> int:
    sub = args[0] if args else ""
    if sub == "job":
        r = job()
    elif sub == "drill" and "--target" in args and "--identity" in args:
        r = drill(args[args.index("--target") + 1], args[args.index("--identity") + 1],
                  name=args[args.index("--object") + 1] if "--object" in args else None)
    elif sub == "prune":
        r = prune(dry_run="--apply" not in args)
    else:
        print("Uso: main.py offsite job | drill --target URL_BASE_VACIA --identity ARCHIVO_AGE [--object NOMBRE] | "
              "prune [--apply]")
        return 1
    if "filas" in r and isinstance(r["filas"], dict):
        r["filas"] = sum(r["filas"].values())
    print(json.dumps(r, ensure_ascii=False))
    return 0 if r.get("ok") else (3 if r.get("desactivado") else 2)
