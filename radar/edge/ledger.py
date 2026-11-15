"""Registro de ejecuciones (solo se añade, nunca se borra) con hash del código y de los datos.

Cada línea de research/edge/ledger/ledger.jsonl encadena el hash de la anterior, así que borrar o editar una línea
rompe la cadena y `verify()` lo detecta. Tipos:
  final_holdout            evaluación final pre-registrada (solo puede existir una)
  holdout_attempt_refused  intento de repetir el holdout: se registra y se rechaza
  reproduction             re-ejecución idéntica (v1) para comprobar reproducibilidad: NO es un holdout independiente
  exploratory              experimento exploratorio: NO es evidencia independiente
"""
import datetime as dt, hashlib, json, subprocess, uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "research" / "edge" / "ledger" / "ledger.jsonl"
DATA_FILES = ["data/research/panel.json.gz", "data/research/panel_delisted.json.gz"]
CODE_GLOBS = ["radar/edge/*.py", "research/edge/run.py"]


def sha256_files(paths):
    h = hashlib.sha256()
    for p in sorted(paths):
        h.update(str(p.relative_to(ROOT)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def code_hash():
    return sha256_files([p for g in CODE_GLOBS for p in ROOT.glob(g)])


def data_hash():
    return sha256_files([ROOT / f for f in DATA_FILES if (ROOT / f).exists()])


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except Exception:
        return None


def entries():
    if not LEDGER.exists():
        return []
    return [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]


def _line_hash(e):
    return hashlib.sha256(json.dumps(e, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def append(kind, **fields):
    prev = entries()
    e = {"run_id": str(uuid.uuid4()), "kind": kind, "at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
         "git_commit": git_commit(), "code_hash": code_hash(), "data_hash": data_hash(),
         "prev_hash": _line_hash(prev[-1]) if prev else None, **fields}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as fh:
        fh.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
    return e


def final_holdout():
    return next((e for e in entries() if e["kind"] == "final_holdout"), None)


def verify():
    """True si la cadena está intacta (ninguna línea editada ni borrada)."""
    es = entries()
    return all(es[i]["prev_hash"] == _line_hash(es[i - 1]) for i in range(1, len(es))) and (not es or es[0]["prev_hash"] is None)
