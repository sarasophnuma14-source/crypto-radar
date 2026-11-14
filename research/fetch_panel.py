"""Descarga velas diarias de TODOS los pares spot USDT de Binance (activos, pausados y
retirados que aún aparecen) desde 2020-01-01 y las guarda en un solo archivo comprimido.
Uso: CRYPTO_RADAR_HOME=$(pwd) python3 research/fetch_panel.py"""
import datetime as dt, gzip, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from radar import data
from radar.portfolio_backtest import fetch_history

STABLE = {"USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "AEUR", "EURI", "USDE", "PAXG", "WBTC", "WBETH",
          "BFUSD", "USD1", "XUSD", "RLUSD", "BNSOL", "GBP", "AUD", "XAUT", "TRY", "BRL", "ARS", "ZAR", "UAH", "RUB",
          "BIDR", "IDRT", "NGN", "PLN", "RON", "JPY", "MXN", "COP", "CZK", "SUSD", "UST", "USTC"}
out_dir = Path("data/research"); cache = out_dir / "cache"; cache.mkdir(parents=True, exist_ok=True)
start = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
info = data._binance("/api/v3/exchangeInfo")
syms = []
for s in info.get("symbols", []):
    b = s.get("baseAsset", "")
    if s.get("quoteAsset") != "USDT" or s.get("status") not in ("TRADING", "BREAK", "HALT"):
        continue
    if b in STABLE or "USD" in b or b.endswith(("UP", "DOWN", "BULL", "BEAR")):
        continue
    syms.append((b, s.get("status")))
print("pares:", len(syms), flush=True)
panel = {}
for i, (b, st) in enumerate(syms):
    f = cache / f"{b}.json"
    try:
        if f.exists():
            h = json.loads(f.read_text())
        else:
            h = fetch_history(b, start); f.write_text(json.dumps(h)); time.sleep(0.05)
    except Exception as e:
        print("sin datos", b, e, flush=True); continue
    if len(h["c"]) >= 60:
        h["status"] = st; panel[b] = h
    if i % 50 == 0:
        print(i, b, len(h["c"]), flush=True)
with gzip.open(out_dir / "panel.json.gz", "wt") as g:
    json.dump(panel, g)
print("listo:", len(panel), "monedas ->", out_dir / "panel.json.gz", flush=True)
