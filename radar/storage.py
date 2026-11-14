"""Persistencia simple en archivos JSON dentro de data/."""
from __future__ import annotations
import json
import threading
from pathlib import Path
from .config import DATA_DIR

_lock = threading.Lock()


def path(name) -> Path:
    return DATA_DIR / name


def read(name, default=None):
    p = path(name)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return default


def write(name, data):
    with _lock:
        p = path(name)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), "utf-8")
        tmp.replace(p)


def append_list(name, items, keep=2000):
    with _lock:
        cur = read(name, []) or []
    cur.extend(items)
    write(name, cur[-keep:])
