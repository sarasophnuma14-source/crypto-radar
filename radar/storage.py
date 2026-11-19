"""Persistencia de documentos JSON del sistema.

Por defecto, archivos en data/. Si hay DATABASE_URL (producción), los documentos se guardan en la tabla kv de
PostgreSQL y sobreviven a los reinicios (el disco de Render gratis se borra en cada despliegue).
"""
from __future__ import annotations
import json
import os
import threading
from pathlib import Path
from .config import DATA_DIR

_lock = threading.RLock()
USE_DB = bool(os.environ.get("DATABASE_URL")) or os.environ.get("CRYPTO_RADAR_STORAGE") == "db"


def path(name) -> Path:
    return DATA_DIR / name


def read(name, default=None):
    if USE_DB:
        from . import db
        return db.get_kv(name, default)
    p = path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def read_fields(name, keys):
    """Claves de primer nivel de un documento sin leerlo entero desde la base (ver db.get_kv_fields)."""
    if USE_DB:
        from . import db
        return db.get_kv_fields(name, keys)
    doc = read(name, {}) or {}
    return {k: doc.get(k) if isinstance(doc, dict) else None for k in keys}


def write(name, data):
    with _lock:
        if USE_DB:
            from . import db
            return db.upsert_kv(name, data)
        p = path(name)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), "utf-8")
        tmp.replace(p)


def append_list(name, items, keep=2000):
    """Añade elementos de forma atómica (lectura y escritura bajo el mismo candado)."""
    with _lock:
        cur = read(name, []) or []
        cur.extend(items)
        write(name, cur[-keep:])


def update(name, fn, default=None):
    """Lectura-modificación-escritura atómica: fn(valor_actual) -> nuevo valor."""
    with _lock:
        cur = read(name, default)
        new = fn(cur)
        write(name, new)
        return new
