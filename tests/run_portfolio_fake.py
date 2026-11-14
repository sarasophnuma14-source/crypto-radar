import os, sys, tempfile, pathlib, time
os.environ.setdefault("CRYPTO_RADAR_HOME", tempfile.mkdtemp())
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import fake_market
from radar import portfolio_backtest as pb
H = {s: dict(fake_market._series(s, "1d", 1000)) for s in fake_market.SYMS[:15]}
for s in H: H[s]["t"] = H["BTC"]["t"]
t = time.time()
r = pb.run(histories=H, test_from="2024-06-01", out_dir=sys.argv[1] if len(sys.argv) > 1 else None)
print("s", round(time.time() - t, 1))
s = r["summary"]; print({k: v for k, v in s.items() if k not in ("tokens", "mejor_operacion", "peor_operacion", "posiciones_abiertas_al_final")})
for o in r["orders"][:12]: print(o)
print(r["trades"][:2])
