#!/usr/bin/env python3
"""CRYPTO RADAR AI
  python3 main.py serve            -> panel en http://localhost:8777 + escaneos automáticos
  python3 main.py scan             -> un escaneo ahora (imprime el resumen)
  python3 main.py backtest SOL     -> backtest de las reglas sobre SOL
  python3 main.py cartera          -> backtest de cartera con órdenes exactas (2023 → hoy)
  python3 main.py paper init|step|report|replay [nombre]  -> paper trading de D_volmom_L28 (sin dinero real)
  python3 main.py backup create|verify|compare|restore    -> copias de seguridad verificables de la base
  python3 main.py preflight        -> revisa la configuración de producción (no cambia nada)
  python3 main.py admin enroll-token [minutos] -> código de un solo uso para el primer TOTP del administrador
  python3 main.py secrets status|encrypt       -> estado / cifrado y rotación de los secretos TOTP en la base
  python3 main.py payments-selftest -> prueba de extremo a extremo de pagos en sandbox simulado (sin red, sin cobros)
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
    elif cmd == "altcoins":
        from radar import alt_study
        from radar.config import DATA_DIR
        comp = alt_study.main(DATA_DIR / "backtest_altcoins")
        print(json.dumps(comp, indent=1, ensure_ascii=False))
        print("Informe:", DATA_DIR / "backtest_altcoins" / "informe_altcoins.html")
    elif cmd == "paper":
        import os
        os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
        from radar.paper_trading import engine, report
        sub = sys.argv[2] if len(sys.argv) > 2 else "report"
        if sub == "replay":
            a, b = sys.argv[3], sys.argv[4]
            name = sys.argv[5] if len(sys.argv) > 5 else f"replay_{a}_{b}"
            rows = engine.replay(name, a, b)
            rep, d = report.write(name)
            print(f"REPLAY HISTÓRICO (no prospectivo): {len(rows)} días procesados. Informe: {d / 'report.md'}")
            return
        name = sys.argv[3] if len(sys.argv) > 3 else "principal"
        if sub == "init":
            spec = engine.init(name)
            print(f"Evaluación '{name}' creada. Empieza con el cierre del {spec['start_date']} (UTC). spec_hash {spec['spec_hash'][:16]}")
            print(json.dumps(engine.step_live(name), ensure_ascii=False))
        elif sub == "step":
            print(json.dumps(engine.step_live(name), ensure_ascii=False))
            report.write(name)
        elif sub == "report":
            rep, d = report.write(name)
            print(report.markdown(rep)); print("\nArchivos:", d)
        else:
            print(__doc__)
    elif cmd == "backup":
        from radar import backup
        sys.exit(backup.cli(sys.argv[2:]))
    elif cmd == "preflight":
        from radar import preflight
        sys.exit(preflight.cli())
    elif cmd == "admin" and len(sys.argv) > 2 and sys.argv[2] == "enroll-token":
        from radar import auth, db
        db.init()
        tok, ttl = auth.new_enroll_token(sys.argv[3] if len(sys.argv) > 3 else None)
        print("Código de alta del administrador (se muestra solo esta vez; un solo uso; caduca en "
              f"{round(ttl / 60)} min):\n\n  {tok}\n\nEscríbelo en Cuenta → Verificación en dos pasos. "
              "No lo envíes por chat ni correo.")
    elif cmd == "secrets" and len(sys.argv) > 2 and sys.argv[2] in ("status", "encrypt"):
        from radar import auth, db, secretbox
        db.init()
        try:
            if sys.argv[2] == "encrypt":
                print("Resultado:", json.dumps(auth.encrypt_totp_secrets(), ensure_ascii=False))
            st = auth.totp_secrets_status()
        except secretbox.SecretError as e:
            print("ERROR:", e); sys.exit(2)
        print("Secretos TOTP:", json.dumps(st, ensure_ascii=False))
        sys.exit(1 if st["en_claro"] or st["ilegibles"] else 0)
    elif cmd == "payments-selftest":
        from radar import payments_selftest
        sys.exit(payments_selftest.cli())
    elif cmd == "backtest":
        print(json.dumps({k: v for k, v in backtest.run(sys.argv[2]).items() if k not in ("list", "equity")}, indent=1, ensure_ascii=False))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
