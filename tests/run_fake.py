import os, sys, tempfile, pathlib
os.environ.setdefault("CRYPTO_RADAR_HOME", tempfile.mkdtemp())
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tests"))
import shutil
shutil.copytree(ROOT / "web", pathlib.Path(os.environ["CRYPTO_RADAR_HOME"]) / "web", dirs_exist_ok=True)
import fake_market; fake_market.install()
from radar import scanner, server, alerts, backtest
alerts._desktop = lambda *a: None
import time
t = time.time()
rep = scanner.run_scan()
print("scan s", round(time.time() - t, 1), "err", scanner.status["last_error"])
print(rep["verdict"], rep["verdict_text"]); print(rep["outlook"])
for r in rep["ranking"]:
    print(r["rank"], r["symbol"], r["score"], r["phase"], r["action"], round(r["plan"]["rr"], 2), r["confidence"], r["coverage"])
print("extra", rep["extra"])
from collections import Counter
print(Counter(r["phase"] for r in rep["assets"])); print(Counter(r["action"] for r in rep["assets"]))
scanner.price_watch()
t = time.time(); bt = backtest.run("SOL", d1=fake_market._series("SOL", "1d", 1000))
print("bt s", round(time.time() - t, 1), {k: v for k, v in bt.items() if k not in ("list", "equity")})
if "--serve" in sys.argv:
    server.serve(8777, schedule=False)
