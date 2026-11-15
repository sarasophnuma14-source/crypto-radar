"""Copias de seguridad lógicas verificables (PostgreSQL/Neon o SQLite).

  create   Exporta las tablas de la app a una carpeta: un archivo JSONL por tabla (filas ordenadas por clave primaria)
           y manifest.json con número de filas, columnas y SHA-256 de cada archivo. En PostgreSQL la lectura se hace
           en una transacción REPEATABLE READ de solo lectura: todas las tablas salen del mismo instante.
  verify   Comprueba los SHA-256 del manifiesto y, además, restaura la copia en una base SQLite temporal y vuelve a
           exportarla: si los hashes coinciden, la copia se puede restaurar de verdad.
  compare  Exporta la base indicada en memoria y la compara con la copia (útil justo después de crearla).
  restore  Restaura en una base de destino VACÍA (nunca borra ni sobrescribe filas). Al terminar vuelve a exportar
           el destino y lo compara con el manifiesto.

Las sesiones y los límites de intentos no se copian (son temporales; tras restaurar, cada persona vuelve a entrar).
La copia SÍ contiene datos personales, hashes de contraseñas y secretos TOTP: guárdala cifrada y fuera del repositorio.
"""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path

from . import db

FORMAT = "crypto-radar-backup/1"
TABLES = {"users": "id", "activity": "id", "positions": "id", "payments": "id", "telegram_links": "code", "kv": "name"}
SKIPPED = ("sessions", "rate_limits")


class BackupError(Exception):
    pass


def _key():
    """Clave de firma (CRYPTO_RADAR_BACKUP_KEY). Sin ella los hashes solo detectan daños accidentales: quien pueda
    escribir en la copia también puede recalcularlos. Con ella, el manifiesto lleva un HMAC-SHA256 que no se puede
    falsificar sin la clave, y verify/restore rechazan copias sin firma o con firma inválida."""
    k = (os.environ.get("CRYPTO_RADAR_BACKUP_KEY") or "").strip()
    if k and len(k) < 32:
        raise BackupError("CRYPTO_RADAR_BACKUP_KEY debe tener al menos 32 caracteres")
    return k.encode() if k else None


def _sign(man, key):
    body = {k: v for k, v in man.items() if k != "hmac_sha256"}
    return hmac.new(key, json.dumps(body, sort_keys=True).encode(), hashlib.sha256).hexdigest()


def mask(url: str) -> str:
    """URL sin contraseña, para mostrarla en pantalla o en el manifiesto."""
    return re.sub(r"//([^:/@]+):[^@]*@", r"//\1:***@", str(url))


def _is_pg(target: str) -> bool:
    return str(target).startswith(("postgres://", "postgresql://"))


def _open(target: str):
    if _is_pg(target):
        import psycopg
        c = psycopg.connect(target, autocommit=True)
        c.execute("SET client_encoding TO 'UTF8'")
        return c, True
    return sqlite3.connect(str(target), timeout=30), False


def _columns(c, pg, table):
    if pg:
        cur = c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() "
                        "AND table_name = %s ORDER BY ordinal_position", (table,))
        return [r[0] for r in cur.fetchall()]
    return [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]


def _ensure_schema(c, pg):
    for stmt in db.SCHEMA:
        c.execute(stmt if pg else stmt.replace("DOUBLE PRECISION", "REAL").replace("BIGINT", "INTEGER"))
    for table, col, typ in db.MIGRATIONS:
        if col not in _columns(c, pg, table):
            t = typ if pg else typ.replace("DOUBLE PRECISION", "REAL").replace("BIGINT", "INTEGER")
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {t}")
    if not pg:
        c.commit()


def _norm(v):
    if isinstance(v, (bytes, memoryview)):
        raise BackupError("Columna binaria inesperada")
    return v


def _dump(c, pg):
    """{tabla: (columnas, [líneas JSON])} leído en una sola transacción."""
    out = {}
    if pg:
        c.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    else:
        c.execute("BEGIN")
    try:
        for table, pk in TABLES.items():
            cols = sorted(_columns(c, pg, table))
            if not cols:
                raise BackupError(f"La tabla {table} no existe en el origen")
            q = f"SELECT {', '.join(cols)} FROM {table} ORDER BY {pk}"      # nombres fijos del código, no del usuario
            rows = c.execute(q).fetchall()
            lines = [json.dumps(dict(zip(cols, (_norm(v) for v in r))), ensure_ascii=False, sort_keys=True,
                                separators=(",", ":")) for r in rows]
            out[table] = (cols, lines)
    finally:
        c.execute("ROLLBACK")
    return out


def _sha(lines):
    h = hashlib.sha256()
    for ln in lines:
        h.update(ln.encode("utf-8") + b"\n")
    return h.hexdigest()


def _summary(dump):
    return {t: {"rows": len(lines), "columns": cols, "sha256": _sha(lines)} for t, (cols, lines) in dump.items()}


def create(source: str, out_dir) -> Path:
    c, pg = _open(source)
    try:
        dump = _dump(c, pg)
    finally:
        c.close()
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    d = Path(out_dir) / f"crypto-radar-backup-{stamp}"
    n = 1
    while d.exists():
        n += 1
        d = Path(out_dir) / f"crypto-radar-backup-{stamp}-{n}"
    d.mkdir(parents=True, mode=0o700)
    for t, (_, lines) in dump.items():
        p = d / f"{t}.jsonl"
        with open(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
    man = {"format": FORMAT, "created_at": time.time(), "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "source_backend": "postgresql" if pg else "sqlite", "source": mask(source) if pg else Path(source).name,
           "skipped_tables": list(SKIPPED), "tables": _summary(dump)}
    man["manifest_sha256"] = hashlib.sha256(json.dumps(man, sort_keys=True).encode()).hexdigest()
    key = _key()
    if key:
        man["hmac_sha256"] = _sign(man, key)
    with open(os.open(d / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    return d


def _load(backup_dir):
    d = Path(backup_dir)
    try:
        man = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BackupError(f"Manifiesto ilegible: {e}") from e
    if man.get("format") != FORMAT:
        raise BackupError("Formato de copia desconocido")
    body = {k: v for k, v in man.items() if k not in ("manifest_sha256", "hmac_sha256")}
    if hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != man.get("manifest_sha256"):
        raise BackupError("El manifiesto fue modificado (hash distinto)")
    key = _key()
    if key:
        if not man.get("hmac_sha256"):
            raise BackupError("La copia no está firmada y CRYPTO_RADAR_BACKUP_KEY está definida: no se acepta")
        if not hmac.compare_digest(_sign(man, key), str(man["hmac_sha256"])):
            raise BackupError("Firma HMAC inválida: la copia fue alterada o se firmó con otra clave")
    data, problems = {}, []
    for t in TABLES:
        info = man["tables"].get(t)
        if info is None:
            problems.append(f"{t}: falta en el manifiesto"); continue
        try:
            lines = (d / f"{t}.jsonl").read_text(encoding="utf-8").splitlines()
        except OSError:
            problems.append(f"{t}: falta el archivo"); continue
        if len(lines) != info["rows"]:
            problems.append(f"{t}: {len(lines)} filas, el manifiesto dice {info['rows']}")
        if _sha(lines) != info["sha256"]:
            problems.append(f"{t}: SHA-256 distinto")
        data[t] = (info["columns"], lines)
    if problems:
        raise BackupError("Copia dañada: " + "; ".join(problems))
    return man, data


def _insert(c, pg, data):
    ph = "%s" if pg else "?"
    if pg:
        c.execute("BEGIN")
    try:
        for t, (cols, lines) in data.items():
            have = set(_columns(c, pg, t))
            extra = [x for x in cols if x not in have]
            if extra:
                raise BackupError(f"El destino no tiene las columnas {t}.{', '.join(extra)}")
            q = f"INSERT INTO {t} ({', '.join(cols)}) VALUES ({', '.join([ph] * len(cols))})"
            for ln in lines:
                row = json.loads(ln)
                c.execute(q, tuple(row[k] for k in cols))
        c.execute("COMMIT") if pg else c.commit()
    except Exception:
        c.execute("ROLLBACK") if pg else c.rollback()
        raise


def restore(backup_dir, target: str) -> dict:
    """Restaura en una base vacía. Si alguna tabla del destino tiene filas, no toca nada."""
    man, data = _load(backup_dir)
    c, pg = _open(target)
    try:
        _ensure_schema(c, pg)
        busy = {t: n for t in list(TABLES) + list(SKIPPED)
                if (n := c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])}
        if busy:
            raise BackupError("El destino no está vacío (" + ", ".join(f"{t}: {n}" for t, n in busy.items()) +
                              "). Restaura en una base nueva; esta herramienta nunca borra datos.")
        _insert(c, pg, data)
        after = _summary(_dump(c, pg))
    finally:
        c.close()
    diff = _diff(man["tables"], after)
    if diff:
        raise BackupError("La restauración no coincide con la copia: " + "; ".join(diff))
    return {t: v["rows"] for t, v in after.items()}


def _diff(expected, got):
    out = []
    for t in TABLES:
        e, g = expected.get(t, {}), got.get(t, {})
        if e.get("rows") != g.get("rows"):
            out.append(f"{t}: filas {g.get('rows')} vs {e.get('rows')}")
        elif e.get("sha256") != g.get("sha256"):
            out.append(f"{t}: contenido distinto")
    return out


def verify(backup_dir) -> dict:
    """Integridad (hashes) + prueba real de restauración en una SQLite temporal."""
    man, _ = _load(backup_dir)
    with tempfile.TemporaryDirectory(prefix="cr-verify-") as tmp:
        rows = restore(backup_dir, str(Path(tmp) / "restore-test.db"))
    return {"created_utc": man.get("created_utc"), "source_backend": man.get("source_backend"), "rows": rows,
            "signed": bool(man.get("hmac_sha256")) and _key() is not None}


def compare(backup_dir, source: str) -> list:
    man, _ = _load(backup_dir)
    c, pg = _open(source)
    try:
        now = _summary(_dump(c, pg))
    finally:
        c.close()
    return _diff(man["tables"], now)


def default_source() -> str:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if url:
        return url
    from .config import DATA_DIR
    return str(DATA_DIR / "app.db")


def cli(args) -> int:
    sub = args[0] if args else ""
    try:
        if sub == "create":
            out = args[args.index("--out") + 1] if "--out" in args else "backups"
            src = default_source()
            d = create(src, out)
            man, _ = _load(d)
            print(f"Copia creada en {d} (origen {man['source']})")
            for t, i in man["tables"].items():
                print(f"  {t:<15} {i['rows']:>7} filas  sha256 {i['sha256'][:16]}…")
            diff = compare(d, src)
            print("Comparación con el origen:", "idéntica" if not diff else "; ".join(diff) + " (hubo escrituras durante la copia)")
            print("AVISO: contiene datos personales y secretos TOTP. Guárdala cifrada y fuera del repositorio.")
            if not man.get("hmac_sha256"):
                print("AVISO: copia SIN firma HMAC. Define CRYPTO_RADAR_BACKUP_KEY (32+ caracteres) para detectar alteraciones deliberadas.")
            return 0
        if sub == "verify" and len(args) > 1:
            r = verify(args[1])
            print(f"Copia íntegra y restaurable ({r['source_backend']}, {r['created_utc']}): " +
                  ", ".join(f"{t} {n}" for t, n in r["rows"].items()))
            print("Firma HMAC verificada." if r["signed"] else
                  "AVISO: sin firma HMAC (defina CRYPTO_RADAR_BACKUP_KEY): los hashes no protegen contra alteraciones deliberadas.")
            return 0
        if sub == "compare" and len(args) > 1:
            diff = compare(args[1], default_source())
            print("Idéntica a la base actual" if not diff else "Diferencias: " + "; ".join(diff))
            return 0 if not diff else 1
        if sub == "restore" and len(args) > 1 and "--target" in args:
            target = args[args.index("--target") + 1]
            if (os.environ.get("DATABASE_URL") or "").strip() == target.strip():
                raise BackupError("El destino es la base configurada en DATABASE_URL. Restaura en una base nueva.")
            rows = restore(args[1], target)
            print(f"Restaurada en {mask(target)}: " + ", ".join(f"{t} {n}" for t, n in rows.items()))
            return 0
    except BackupError as e:
        print("ERROR:", e)
        return 2
    print("Uso: main.py backup create [--out DIR] | verify DIR | compare DIR | restore DIR --target URL_O_RUTA_SQLITE")
    return 1
