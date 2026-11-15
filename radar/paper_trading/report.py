"""Informe del paper trading: JSON (para el panel, /api/paper/report) y Markdown legible."""
import json
from radar.paper_trading import storage as pstore, metrics, portfolio
from radar.paper_trading.storage import verify_chain


def build(name, store=None):
    store = store or pstore.open_store(name)
    spec = store.read_json("spec.json")
    if not spec:
        return {"available": False, "note": f"No existe la evaluación '{name}'. Créala con: python3 main.py paper init {name}"}
    eq, tr, ev = store.read_all("equity"), store.read_all("trades"), store.read_all("events")
    st = store.read_json("state.json") or {}
    m = metrics.compute(eq, tr, spec)
    counts = {}
    for e in ev:
        counts[e["type"]] = counts.get(e["type"], 0) + 1
    return {"available": True, "name": name, "mode": spec["mode"], "strategy": spec["strategy"], "spec_hash": spec["spec_hash"],
            "start_date": spec["start_date"], "last_date": st.get("last_date"), "real_orders": False,
            "integrity": {k: verify_chain(v) for k, v in (("events", ev), ("trades", tr), ("equity", eq))},
            "metrics": m, "portfolio": portfolio.snapshot(st) if st else None, "event_counts": counts,
            "recent_trades": tr[-20:], "recent_rejections": [e for e in ev if e["type"] in ("rejected", "order_cancelled")][-20:],
            "equity_curve": [{"date": r["date"], "equity": r["equity"], "btc": r["btc_bh_equity"], "cash": r["cash_equity"]} for r in eq],
            "disclaimer": "Simulación sin dinero real. Señal experimental, no es una recomendación de inversión."}


def markdown(rep):
    if not rep.get("available"):
        return rep["note"]
    m = rep["metrics"]
    f = lambda v, s="": "—" if v is None else f"{v}{s}"
    L = [f"# Paper trading {rep['strategy']} — {rep['name']}", "",
         f"Modo: **{rep['mode']}** · desde {rep['start_date']} hasta {rep['last_date']} · {m.get('days', 0)} días · "
         "**sin órdenes reales**", "", f"**{m.get('after_costs', '')}**", "",
         f"Estado frente a los criterios: **{m['acceptance']['verdict']}** ({m['acceptance']['passed']}/{m['acceptance']['total']})"
         if m.get("acceptance") else "", "",
         "| Métrica | Valor |", "| --- | --- |"]
    for k, lab, suf in (("net_return_pct", "Retorno acumulado", " %"), ("cagr_pct", "CAGR", " %"), ("sharpe", "Sharpe", ""),
                        ("sortino", "Sortino", ""), ("profit_factor", "Profit factor", ""), ("expectancy_usd", "Expectativa por operación", " USD"),
                        ("max_drawdown_pct", "Drawdown máximo", " %"), ("win_rate_pct", "Acierto", " %"),
                        ("avg_win_usd", "Ganancia media", " USD"), ("avg_loss_usd", "Pérdida media", " USD"),
                        ("trades", "Operaciones cerradas", ""), ("open_positions", "Posiciones abiertas", ""),
                        ("avg_exposure_pct", "Exposición media", " %"), ("portfolio_vol_ann_pct", "Volatilidad de la cartera", " %"),
                        ("costs_usd", "Costes acumulados", " USD")):
        L.append(f"| {lab} | {f(m.get(k), suf)} |")
    L += ["", "| Comparación | Retorno | Sharpe | Drawdown |", "| --- | --- | --- | --- |",
          f"| Estrategia | {f(m.get('net_return_pct'), ' %')} | {f(m.get('sharpe'))} | {f(m.get('max_drawdown_pct'), ' %')} |"]
    for k, v in (m.get("vs") or {}).items():
        L.append(f"| {k} | {v['net_return_pct']} % | {v['sharpe']} | {v['max_drawdown_pct']} % |")
    if m.get("monthly_pct"):
        L += ["", "Retornos mensuales: " + ", ".join(f"{k} {v:+.2f} %" for k, v in m["monthly_pct"].items())]
    if m.get("by_regime_days"):
        L += ["", "Por régimen de BTC (días): " + "; ".join(f"{k}: {v['cum_pct']:+.2f} % en {v['days']} días" for k, v in m["by_regime_days"].items())]
    L += ["", "Criterios (filtros mínimos, no garantías):"] + [f"- {'✓' if v else '✗'} {k}" for k, v in m["acceptance"]["checks"].items()]
    L += ["", f"Integridad del diario: {rep['integrity']}", "", rep["disclaimer"]]
    return "\n".join(L)


def write(name, out_dir=None, store=None):
    from pathlib import Path
    from radar.config import DATA_DIR
    rep = build(name, store)
    d = Path(out_dir or DATA_DIR / "paper" / name); d.mkdir(parents=True, exist_ok=True)
    (d / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1, default=str), "utf-8")
    (d / "report.md").write_text(markdown(rep), "utf-8")
    return rep, d
