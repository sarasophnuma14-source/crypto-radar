"""Prueba adversarial: ¿cuántos códigos de vinculación puede probar un mismo chat de Telegram?
Uso: python tests/piloto/ataque_telegram.py  → base SQLite temporal; imprime cuántos intentos se procesaron."""
import os, sys, tempfile
from pathlib import Path
d = tempfile.mkdtemp(prefix="cr-tg-"); os.environ["CRYPTO_RADAR_DATA"] = d; os.environ.pop("DATABASE_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from radar import db, telegram_bot
db.init()
r = [telegram_bot.handle({"chat": {"id": 777}, "text": f"/start {i:08X}"}) for i in range(200)]
probados = sum("no válido" in x for x in r)
bloqueados = sum("Demasiados" in x for x in r)
print(f"intentos procesados: {probados} de 200 · bloqueados: {bloqueados}")
