"""Estudio en altcoins / small caps: reglas actuales (v1) vs reglas v2, con periodo de diseño y periodo fuera de muestra."""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
from pathlib import Path
from . import data
from .portfolio_backtest import alt_universe, fetch_history, run, day

V1 = {}
V2 = {"stop_atr_min": 1.8, "confirm_breakout": True}
IS_END = "2024-12-31"


def load_histories(cache_dir, start, log=print):
    cache_dir.mkdir(parents=True, exist_ok=True)
    uni = alt_universe()
    log(f"Universo: {len(uni)} pares USDT (activos y retirados) sin grandes ni stablecoins")
    hist, status = {}, {}
    for b, st in [("BTC", "TRADING")] + uni:
        f = cache_dir / f"{b}.json"
        try:
            if f.exists():
                h = json.loads(f.read_text())
            else:
                h = fetch_history(b, start)
                f.write_text(json.dumps(h))
                time.sleep(0.05)
        except Exception as e:
            log(f"  sin datos {b}: {e}")
            continue
        if len(h["c"]) >= 260:
            hist[b] = h; status[b] = st
    log(f"Con historial suficiente (≥260 días): {len(hist) - 1} altcoins")
    return hist, status


def period_stats(res, frm, to, capital):
    eq = [(d, v) for d, v in res["equity"] if frm <= d <= to]
    if not eq:
        return {}
    prev = [v for d, v in res["equity"] if d < frm]
    v0 = prev[-1] if prev else capital
    peak, mdd = v0, 0.0
    for _, v in eq:
        peak = max(peak, v); mdd = min(mdd, v / peak - 1)
    tr = [t for t in res["trades"] if frm <= t["entrada_fecha"] <= to]
    wins = [t for t in tr if t["pnl_usd"] > 0]
    gw = sum(t["pnl_usd"] for t in wins); gl = -sum(t["pnl_usd"] for t in tr if t["pnl_usd"] <= 0)
    return {"desde": eq[0][0], "hasta": eq[-1][0], "retorno_pct": round((eq[-1][1] / v0 - 1) * 100, 2),
            "max_drawdown_pct": round(mdd * 100, 2), "operaciones": len(tr),
            "acierto_pct": round(len(wins) / len(tr) * 100, 1) if tr else None,
            "profit_factor": round(gw / gl, 2) if gl else None,
            "R_medio": round(sum(t["R"] for t in tr) / len(tr), 2) if tr else None,
            "sin_llegar_a_TP1": sum(1 for t in tr if t["objetivos"] == "-")}


def main(out_dir, start="2022-01-01", test_from="2023-01-01", min_liq=5_000_000, log=print):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    t_start = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc)
    hist, status = load_histories(out / "cache", t_start, log)
    results = {}
    for name, rules in (("v1_actual", V1), ("v2_ajustada", V2)):
        log(f"Simulando {name}…")
        t0 = time.time()
        r = run(histories=hist, test_from=test_from, rules=rules, min_liq_usd=min_liq, trade_btc=False, log=log)
        log(f"  listo en {time.time() - t0:.0f}s")
        results[name] = r
        for fn, rows in ((f"ordenes_{name}.csv", r["orders"]), (f"operaciones_{name}.csv", r["trades"])):
            if rows:
                with open(out / fn, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    last = max(d for d, _ in results["v1_actual"]["equity"])
    comp = {}
    for name, r in results.items():
        cap = r["summary"]["capital_inicial"]
        comp[name] = {"total": period_stats(r, test_from, last, cap),
                      "diseño_2023_2024": period_stats(r, test_from, IS_END, cap),
                      "fuera_de_muestra_2025_hoy": period_stats(r, "2025-01-01", last, cap),
                      "comisiones": r["summary"]["comisiones_pagadas"]}
    b = hist["BTC"]
    def px(dstr):
        best = None
        for t, c in zip(b["t"], b["c"]):
            if day(t) <= dstr: best = c
        return best
    comp["btc_comprar_mantener"] = {
        "diseño_2023_2024": round((px(IS_END) / px(test_from) - 1) * 100, 1),
        "fuera_de_muestra_2025_hoy": round((px(last) / px("2024-12-31") - 1) * 100, 1)}
    traded = {t["token"] for r in results.values() for t in r["trades"]}
    comp["universo"] = {"altcoins_con_datos": len(hist) - 1, "retiradas_o_pausadas_incluidas": sum(1 for s, v in status.items() if v != "TRADING"),
                        "operadas_alguna_vez": len(traded), "filtro_liquidez_usd_dia": min_liq,
                        "reglas_v2": V2}
    (out / "comparacion.json").write_text(json.dumps(comp, indent=1, ensure_ascii=False), "utf-8")
    html_report(comp, results, out / "informe_altcoins.html")
    return comp


def html_report(comp, results, path):
    rows = [("Retorno", "retorno_pct", "%"), ("Máx. drawdown", "max_drawdown_pct", "%"), ("Operaciones", "operaciones", ""),
            ("Acierto", "acierto_pct", "%"), ("Profit factor", "profit_factor", ""), ("R medio", "R_medio", ""),
            ("Stop antes de TP1", "sin_llegar_a_TP1", "")]
    def table(period):
        h = f"<tr><th></th><th>v1 actual</th><th>v2 ajustada</th></tr>"
        for lab, k, u in rows:
            h += f"<tr><td>{lab}</td>" + "".join(f"<td>{comp[n][period].get(k, '—')}{u if comp[n][period].get(k) is not None else ''}</td>" for n in ("v1_actual", "v2_ajustada")) + "</tr>"
        return f"<table>{h}</table>"
    ok = ["fecha", "token", "lado", "tipo", "motivo", "precio", "cantidad", "valor_usd", "comision_usd", "pnl_usd", "caja_usd"]
    def orders(name):
        return "<table><tr>" + "".join(f"<th>{k}</th>" for k in ok) + "</tr>" + "".join(
            "<tr>" + "".join(f"<td>{'' if o.get(k) is None else o.get(k)}</td>" for k in ok) + "</tr>" for o in results[name]["orders"]) + "</table>"
    u = comp["universo"]; bh = comp["btc_comprar_mantener"]
    html = f"""<!doctype html><html lang="es"><meta charset="utf-8"><title>Backtest altcoins</title>
<style>body{{font:14px -apple-system,Segoe UI,sans-serif;background:#0b0f14;color:#e6edf3;margin:20px}}table{{border-collapse:collapse;font-size:12px;margin:8px 0 20px}}td,th{{border-bottom:1px solid #233042;padding:5px 8px;text-align:left;white-space:nowrap}}th{{color:#8b98a8}}.w{{overflow-x:auto}}</style>
<h1>Backtest en altcoins y small caps</h1>
<p>Universo: {u['altcoins_con_datos']} altcoins USDT de Binance ({u['retiradas_o_pausadas_incluidas']} retiradas o pausadas incluidas), sin BTC/ETH ni grandes ni stablecoins. Solo se opera un token el día que su volumen medio de 20 días supera ${u['filtro_liquidez_usd_dia']:,.0f}. Capital $10.000, riesgo 1% por operación, máx. 5 posiciones, comisión 0,1% por lado, slippage 0,05%.</p>
<p><b>v2</b>: stop al menos a 1,8 ATR (antes 0,8) y en rupturas exige dos cierres diarios sobre la resistencia con volumen ≥1,5× la media. Se decidió antes de mirar estos datos.</p>
<h2>Diseño 2023–2024</h2>{table('diseño_2023_2024')}<p>BTC comprar y mantener: {bh['diseño_2023_2024']}%</p>
<h2>Fuera de muestra 2025–hoy</h2>{table('fuera_de_muestra_2025_hoy')}<p>BTC comprar y mantener: {bh['fuera_de_muestra_2025_hoy']}%</p>
<h2>Total</h2>{table('total')}
<h2>Órdenes v2</h2><div class="w">{orders('v2_ajustada')}</div><h2>Órdenes v1</h2><div class="w">{orders('v1_actual')}</div>
<p style="color:#8b98a8">Tokens que dejaron de cotizar sin aparecer en la API pública no se incluyen, así que aún hay algo de sesgo de supervivencia. Resultados pasados no garantizan resultados futuros. No es asesoría financiera.</p></html>"""
    Path(path).write_text(html, "utf-8")
