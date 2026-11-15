"""Almacenamiento persistente del paper trading.

Cada evaluación vive en su propia carpeta (data/paper/<nombre>/):
  spec.json      especificación congelada (estrategia, parámetros, hash del código). Se escribe una vez.
  state.json     estado del motor (efectivo, posiciones, órdenes pendientes). Se reescribe de forma atómica.
  events.jsonl   señales, rechazos, órdenes, ejecuciones, cancelaciones y salidas   } solo se añade;
  trades.jsonl   operaciones cerradas                                               } cada línea lleva el hash
  equity.jsonl   una fila por día: capital, efectivo, exposición, BTC y efectivo     } de la anterior
Si DATABASE_URL está definida (Render), los mismos documentos se guardan en la tabla kv de PostgreSQL.
"""
import hashlib, json, os
from pathlib import Path

KINDS = ("events", "trades", "equity")


def _h(rec):
    return hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


class FileStore:
    def __init__(self, root):
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)

    def read_json(self, name, default=None):
        p = self.root / name
        return json.loads(p.read_text("utf-8")) if p.exists() else default

    def write_json(self, name, obj):
        p = self.root / name; tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), "utf-8")
        os.replace(tmp, p)

    def read_all(self, kind):
        p = self.root / f"{kind}.jsonl"
        return [json.loads(l) for l in p.read_text("utf-8").splitlines() if l.strip()] if p.exists() else []

    def _last(self, kind):
        p = self.root / f"{kind}.jsonl"
        if not p.exists():
            return None
        lines = [l for l in p.read_text("utf-8").splitlines() if l.strip()]
        return json.loads(lines[-1]) if lines else None

    def append(self, kind, recs):
        last = self._last(kind); prev = _h(last) if last else None
        with open(self.root / f"{kind}.jsonl", "a", encoding="utf-8") as fh:
            for r in recs:
                r = dict(r, _prev=prev); fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n"); prev = _h(r)


class KVStore:
    """Misma interfaz sobre radar.storage (PostgreSQL en producción)."""

    def __init__(self, name):
        from radar import storage
        self.s = storage; self.prefix = f"paper_{name}_"

    def read_json(self, name, default=None):
        return self.s.read(self.prefix + name, default)

    def write_json(self, name, obj):
        self.s.write(self.prefix + name, json.loads(json.dumps(obj, default=str)))

    def read_all(self, kind):
        return self.s.read(self.prefix + kind + ".jsonl", []) or []

    def append(self, kind, recs):
        cur = self.read_all(kind); prev = _h(cur[-1]) if cur else None
        for r in recs:
            r = dict(r, _prev=prev); cur.append(json.loads(json.dumps(r, default=str))); prev = _h(r)
        self.s.write(self.prefix + kind + ".jsonl", cur)


def verify_chain(recs):
    """True si ninguna línea del diario se editó o borró."""
    return all(recs[i].get("_prev") == _h(recs[i - 1]) for i in range(1, len(recs))) and (not recs or recs[0].get("_prev") is None)


def open_store(name, root=None):
    from radar import storage
    if root is None and storage.USE_DB:
        return KVStore(name)
    from radar.config import DATA_DIR
    return FileStore(Path(root or DATA_DIR / "paper") / name)
