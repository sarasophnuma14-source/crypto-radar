"""Prueba adversarial: alguien con acceso de escritura a una copia cambia un usuario a administrador y recalcula
los hashes (SHA-256 por tabla y del manifiesto). ¿Lo detecta `verify`/`restore`?
Uso: python tests/piloto/ataque_backup.py  → imprime DETECTADO, NO DETECTADO o SIN CLAVE (no se crea la copia). Solo usa bases SQLite temporales."""
import hashlib, json, os, sqlite3, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from radar import backup

tmp = Path(tempfile.mkdtemp(prefix="cr-ataque-"))
src = str(tmp / "origen.db")
c = sqlite3.connect(src); backup._ensure_schema(c, False)
c.execute("INSERT INTO users(id, email, pw_hash, created_at, is_admin) VALUES ('u1', 'cliente', 'scrypt$x', 1, 0)")
c.commit(); c.close()
try:
    d = backup.create(src, tmp / "copias")
except backup.BackupError as e:
    print("SIN CLAVE: no se crea ninguna copia, así que no puede haber una copia «verificada» sin firma:", e)
    sys.exit(0)
p = d / "users.jsonl"
rows = [json.loads(x) for x in p.read_text().splitlines()]
rows[0]["is_admin"] = 1                                                # escalada de privilegios dentro de la copia
lines = [json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for r in rows]
p.write_text("".join(x + "\n" for x in lines))
man = json.loads((d / "manifest.json").read_text())
man["tables"]["users"]["sha256"] = backup._sha(lines)
man.pop("manifest_sha256", None)
sig = man.pop("hmac_sha256", None)
man["manifest_sha256"] = hashlib.sha256(json.dumps(man, sort_keys=True).encode()).hexdigest()
(d / "manifest.json").write_text(json.dumps(man))
try:
    backup.verify(d)
    dst = str(tmp / "restaurada.db"); backup.restore(d, dst)
    adm = sqlite3.connect(dst).execute("SELECT is_admin FROM users WHERE id='u1'").fetchone()[0]
    print(f"NO DETECTADO: la copia alterada se restauró y 'cliente' quedó con is_admin={adm}")
except backup.BackupError as e:
    print("DETECTADO:", e)
