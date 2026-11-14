#!/usr/bin/env python3
"""CRYPTO RADAR AI
  python3 main.py serve            -> panel en http://localhost:8777 + escaneos automáticos
  python3 main.py scan             -> un escaneo ahora (imprime el resumen)
  python3 main.py backtest SOL     -> backtest de las reglas sobre SOL
  python3 main.py cartera          -> backtest de cartera con órdenes exactas (2023 → hoy)
Solo análisis. No es asesoría financiera."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from radar import server, scanner, backtest  # noqa: E402


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd == "serve":
        server.serve(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "scan":
        rep = scanner.run_scan()
        if not rep:
            print("Error:", scanner.status["last_error"]); sys.exit(1)
        print(rep["verdict"], "-", rep["verdict_text"])
        print(rep["outlook"])
        for r in rep["ranking"]:
            print(f"{r['rank']:>2} {r['symbol']:<8} score {r['score']:>5} {r['phase']:<16} {r['action']:<20} R:R {r['plan']['rr']:.1f}")
    elif cmd == "cartera":
        from radar import portfolio_backtest as pb
        from radar.config import DATA_DIR
        out = DATA_DIR / "backtest_cartera"
        start = sys.argv[2] if len(sys.argv) > 2 else "2022-01-01"
        test_from = sys.argv[3] if len(sys.argv) > 3 else "2023-01-01"
        r = pb.run(start=start, test_from=test_from, out_dir=out)
        pb.html_report(r, out / "informe.html")
        s = r["summary"]
        print(json.dumps({k: v for k, v in s.items() if k not in ("mejor_operacion", "peor_operacion")}, indent=1, ensure_ascii=False))
        print("Informe:", out / "informe.html")
    elif cmd == "backtest":
        print(json.dumps({k: v for k, v in backtest.run(sys.argv[2]).items() if k not in ("list", "equity")}, indent=1, ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
