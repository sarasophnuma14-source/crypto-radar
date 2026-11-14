"""Backtest de CARTERA con órdenes exactas de compra y venta.

Reglas (las mismas de la app):
- Cada día, al cierre, se analiza cada token solo con las velas disponibles hasta ese día (sin mirar el futuro).
- Régimen de mercado diario a partir de BTC y la amplitud del universo -> puntuación mínima de compra y exposición máxima.
- Señal = acción "COMPRAR EN ZONA" con puntuación >= mínimo del régimen y R:R >= mínimo.
- COMPRA: orden LIMIT al tope de la zona de entrada, válida 3 días. Se ejecuta si el mínimo del día la toca,
  al precio min(apertura, límite) + slippage.
- Tamaño: arriesga `risk_pct` del capital entre entrada y stop; tope por activo y por exposición del régimen; máx. N posiciones.
- VENTAS: stop-loss (stop market), TP1 40% (stop sube a la entrada), TP2 35% (stop sube a TP1), TP3 25%.
  Salida por Exit Intelligence: si al cierre la fase es DISTRIBUCIÓN/SOBREEXTENDIDO con riesgo de salida >= 50,
  o cierre diario bajo EMA50 (salida final), se vende el resto a la apertura siguiente. Salida por tiempo: 120 días.
- Si en una misma vela se tocan stop y TP, se asume primero el stop (conservador).
- Comisión por lado y slippage configurables (por defecto 0,10% y 0,05%, tarifas spot estándar de Binance).
Limitaciones: universo = tokens actuales (sesgo de supervivencia); sin fundamentales/sentimiento históricos (N/D).
"""
from __future__ import annotations
import csv
import datetime as dt
import json
import time
from pathlib import Path
from . import data, indicators as ind
from .analysis import analyze, technicals, MIN_BUY_SCORE, EXPOSURE
from .regime import detect

DEFAULT_UNIVERSE = ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "NEAR", "LTC", "ATOM",
                    "UNI", "AAVE", "INJ", "ARB", "OP", "SUI", "APT", "FET", "RENDER", "TIA", "SEI", "HBAR", "FIL"]
WINDOW = 400


def fetch_history(symbol, start, quote="USDT"):
    """Velas diarias completas desde `start` (paginando de 1000 en 1000)."""
    out = {k: [] for k in "tohlcv"}
    t = int(start.timestamp() * 1000)
    while True:
        rows = data._binance("/api/v3/klines", {"symbol": symbol + quote, "interval": "1d", "startTime": t, "limit": 1000})
        if not rows:
            break
        for r in rows:
            out["t"].append(int(r[0])); out["o"].append(float(r[1])); out["h"].append(float(r[2]))
            out["l"].append(float(r[3])); out["c"].append(float(r[4])); out["v"].append(float(r[7]))
        if len(rows) < 1000:
            break
        t = int(rows[-1][0]) + 86400000
        time.sleep(0.15)
    # quitar la vela de hoy (aún abierta)
    today = int(dt.datetime.now(dt.timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    while out["t"] and out["t"][-1] >= today:
        for k in out: out[k].pop()
    return out


def day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


MAJORS = {"BTC", "ETH", "BNB", "SOL", "XRP", "ADA", "DOGE", "TRX", "TON", "AVAX", "LINK", "DOT", "LTC", "BCH", "SHIB",
          "XLM", "ETC", "XMR", "USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "AEUR", "EURI", "USDE", "PAXG",
          "WBTC", "WBETH", "BFUSD", "USD1", "XUSD", "RLUSD", "BNSOL", "WLFI"}


def alt_universe(quote="USDT"):
    """Todos los pares spot USDT de Binance (activos y retirados/pausados) salvo grandes, stablecoins y tokens apalancados."""
    info = data._binance("/api/v3/exchangeInfo")
    out = []
    for s in info.get("symbols", []):
        b = s.get("baseAsset", "")
        if s.get("quoteAsset") != quote or s.get("status") not in ("TRADING", "BREAK", "HALT"):
            continue
        if b in MAJORS or b.endswith(("UP", "DOWN", "BULL", "BEAR")) or "USD" in b:
            continue
        out.append((b, s.get("status")))
    return out


def run(universe=None, start="2022-01-01", test_from="2023-01-01", capital=10_000.0, risk_pct=1.0,
        max_pos_pct=20.0, max_positions=5, fee=0.001, slippage=0.0005, min_rr=3.0, limit_days=3,
        max_hold=120, out_dir=None, log=print, histories=None, rules=None, min_liq_usd=0.0,
        test_to=None, trade_btc=True):
    universe = universe or DEFAULT_UNIVERSE
    settings = {"min_risk_reward": min_rr, "capital_usd": capital, "risk_per_trade_pct": risk_pct, "max_position_pct": 100}
    settings.update(rules or {})
    t_start = dt.datetime.fromisoformat(start).replace(tzinfo=dt.timezone.utc)
    hist = {}
    if histories:
        hist = histories
    else:
        for s in universe:
            try:
                h = fetch_history(s, t_start)
                if len(h["c"]) >= 260:
                    hist[s] = h
                    log(f"datos {s}: {len(h['c'])} velas {day(h['t'][0])} → {day(h['t'][-1])}")
                else:
                    log(f"omitido {s}: solo {len(h['c'])} velas")
            except Exception as e:
                log(f"omitido {s}: {e}")
    if "BTC" not in hist:
        raise RuntimeError("Se necesita el historial de BTC para el régimen de mercado")
    idx = {s: {t: i for i, t in enumerate(h["t"])} for s, h in hist.items()}
    days = sorted({t for h in hist.values() for t in h["t"]})
    tf = int(dt.datetime.fromisoformat(test_from).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
    days = [d for d in days if d >= tf]
    if test_to:
        tt = int(dt.datetime.fromisoformat(test_to).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        days = [d for d in days if d <= tt]

    cash, positions, pending = capital, {}, {}
    orders, trades, equity_curve = [], [], []
    peak, max_dd = capital, 0.0
    fees_paid = 0.0
    regime_log = []

    def slc(s, i):
        h = hist[s]
        return {k: v[max(0, i + 1 - WINDOW):i + 1] for k, v in h.items()}

    def order(d, s, side, typ, reason, price, qty, pnl=None):
        nonlocal cash, fees_paid
        value = price * qty
        f = value * fee
        fees_paid += f
        cash += (-value - f) if side == "COMPRA" else (value - f)
        orders.append({"fecha": day(d), "token": s, "lado": side, "tipo": typ, "motivo": reason, "precio": round(price, 8),
                       "cantidad": round(qty, 8), "valor_usd": round(value, 2), "comision_usd": round(f, 4),
                       "pnl_usd": None if pnl is None else round(pnl - f, 2), "caja_usd": round(cash, 2)})

    def close_part(d, s, p, frac_of_initial, price, typ, reason):
        qty = min(p["qty_left"], p["qty0"] * frac_of_initial) if frac_of_initial < 1 else p["qty_left"]
        if qty <= 0:
            return
        fill = price * (1 - slippage)
        pnl = (fill - p["entry"]) * qty - p["entry_fee"] * qty / p["qty0"]
        order(d, s, "VENTA", typ, reason, fill, qty, pnl)
        p["qty_left"] -= qty
        p["realized"] += pnl - fill * qty * fee
        if p["qty_left"] <= 1e-12:
            p["exit_date"] = d

    for d in days:
        # ---------- 1) ejecución intradía de órdenes (con la vela del día d)
        for s in list(positions):
            i = idx[s].get(d)
            if i is None:
                continue
            h, p = hist[s], positions[s]
            o, hi, lo = h["o"][i], h["h"][i], h["l"][i]
            if p.get("exit_next_open"):
                close_part(d, s, p, 1, o, "MERCADO", p["exit_next_open"])
            else:
                if lo <= p["stop"]:
                    lbl = "STOP LOSS" if not p["hits"] else ("STOP EN ENTRADA (tras TP1)" if p["hits"] == ["TP1"] else "STOP EN TP1 (tras TP2)")
                    close_part(d, s, p, 1, min(o, p["stop"]), "STOP", lbl)
                else:
                    for tp, frac in (("tp1", .40), ("tp2", .35), ("tp3", 1)):
                        if tp.upper() not in p["hits"] and hi >= p[tp]:
                            close_part(d, s, p, frac, max(o, p[tp]), "LIMIT", f"TAKE PROFIT {tp.upper()}")
                            p["hits"].append(tp.upper())
                            if tp == "tp1": p["stop"] = p["entry"]
                            if tp == "tp2": p["stop"] = p["tp1"]
                    if p["qty_left"] > 0 and i - p["entry_i"] >= max_hold:
                        close_part(d, s, p, 1, h["c"][i], "MERCADO", f"SALIDA POR TIEMPO ({max_hold} días)")
            if p["qty_left"] <= 1e-12:
                trades.append({"token": s, "entrada_fecha": day(p["entry_date"]), "salida_fecha": day(d),
                               "dias": i - p["entry_i"], "entrada": round(p["entry"], 8), "stop_inicial": round(p["stop0"], 8),
                               "tp1": round(p["tp1"], 8), "tp2": round(p["tp2"], 8), "tp3": round(p["tp3"], 8),
                               "score": p["score"], "fase": p["phase"], "regimen": p["regime"], "objetivos": ",".join(p["hits"]) or "-",
                               "invertido_usd": round(p["entry"] * p["qty0"], 2), "pnl_usd": round(p["realized"], 2),
                               "pnl_pct": round(p["realized"] / (p["entry"] * p["qty0"]) * 100, 2),
                               "R": round(p["realized"] / p["risk_usd"], 2) if p["risk_usd"] else None})
                del positions[s]
        for s in list(pending):
            i = idx[s].get(d)
            if i is None:
                continue
            po, h = pending[s], hist[s]
            if s in positions:
                del pending[s]; continue
            if h["l"][i] <= po["limit"]:
                fill = min(h["o"][i], po["limit"]) * (1 + slippage)
                if fill <= po["stop"]:
                    orders.append({"fecha": day(d), "token": s, "lado": "COMPRA", "tipo": "LIMIT", "motivo": "CANCELADA: abrió bajo el stop",
                                   "precio": None, "cantidad": 0, "valor_usd": 0, "comision_usd": 0, "pnl_usd": None, "caja_usd": round(cash, 2)})
                    del pending[s]; continue
                eq_now = equity_curve[-1][1] if equity_curve else capital
                risk_usd = eq_now * risk_pct / 100
                qty = risk_usd / (fill - po["stop"])
                cap_usd = min(eq_now * max_pos_pct / 100, cash / (1 + fee))
                qty = min(qty, cap_usd / fill)
                if qty * fill < 10:
                    orders.append({"fecha": day(d), "token": s, "lado": "COMPRA", "tipo": "LIMIT", "motivo": "CANCELADA: sin caja suficiente",
                                   "precio": None, "cantidad": 0, "valor_usd": 0, "comision_usd": 0, "pnl_usd": None, "caja_usd": round(cash, 2)})
                    del pending[s]; continue
                order(d, s, "COMPRA", "LIMIT", f"ENTRADA {po['phase']} score {po['score']:.0f} R:R {po['rr']:.1f}", fill, qty)
                positions[s] = {"entry": fill, "qty0": qty, "qty_left": qty, "stop": po["stop"], "stop0": po["stop"],
                                "tp1": po["tp1"], "tp2": po["tp2"], "tp3": po["tp3"], "hits": [], "entry_i": i, "entry_date": d,
                                "entry_fee": fill * qty * fee, "realized": 0.0, "risk_usd": (fill - po["stop"]) * qty,
                                "score": po["score"], "phase": po["phase"], "regime": po["regime"]}
                del pending[s]
            elif d >= po["expires"]:
                orders.append({"fecha": day(d), "token": s, "lado": "COMPRA", "tipo": "LIMIT", "motivo": "EXPIRADA sin ejecutarse",
                               "precio": round(po["limit"], 8), "cantidad": 0, "valor_usd": 0, "comision_usd": 0, "pnl_usd": None, "caja_usd": round(cash, 2)})
                del pending[s]

        # ---------- 2) valoración al cierre
        mtm = cash
        for s, p in positions.items():
            i = idx[s].get(d)
            px = hist[s]["c"][i] if i is not None else p["entry"]
            p["last"] = px
            mtm += px * p["qty_left"]
        equity_curve.append([day(d), round(mtm, 2)])
        peak = max(peak, mtm); max_dd = min(max_dd, mtm / peak - 1)

        # ---------- 3) análisis al cierre del día d -> órdenes para mañana
        bi = idx["BTC"].get(d)
        if bi is None or bi < 220:
            continue
        above, tech_cache = [], {}
        for s in hist:
            i = idx[s].get(d)
            if i is None or i < 220:
                continue
            if s != "BTC" and min_liq_usd and s not in positions:
                if sum(hist[s]["v"][i - 19:i + 1]) / 20 < min_liq_usd:
                    continue
            t = technicals(slc(s, i))
            tech_cache[s] = t
            if s != "BTC" and t["ema50"]:
                above.append(t["price"] > t["ema50"])
        breadth = sum(above) / len(above) * 100 if above else 50
        reg = detect(tech_cache["BTC"], breadth, None, None, None, None)["regime"]
        regime_log.append([day(d), reg])
        min_buy = MIN_BUY_SCORE.get(reg, 75)
        expo_cap = EXPOSURE.get(reg, 40) / 100
        btc_30 = tech_cache["BTC"]["chg_30d"]
        alt_exposure = sum(p.get("last", p["entry"]) * p["qty_left"] for s, p in positions.items() if s != "BTC")
        for s in tech_cache:
            i = idx[s][d]
            h = hist[s]
            sl = slc(s, i)
            t30 = tech_cache[s]["chg_30d"]
            ctx = {"rel_strength": (t30 - btc_30) if (t30 is not None and btc_30 is not None and s != "BTC") else None}
            a = analyze(s, sl, None, None, None, ctx, settings, reg)
            if s in positions:
                p = positions[s]
                ema50 = a["tech"]["ema50"]
                if (a["phase"] in ("DISTRIBUCIÓN", "SOBREEXTENDIDO") and a["exit_risk"] >= 50):
                    p["exit_next_open"] = "EXIT INTELLIGENCE: " + ", ".join(a["signals_exit"][:2])
                elif ema50 and h["c"][i] < ema50 and p["hits"]:
                    p["exit_next_open"] = "SALIDA FINAL: cierre diario bajo EMA50"
                continue
            if s in pending or len(positions) + len(pending) >= max_positions:
                continue
            if s == "BTC" and not trade_btc:
                continue
            if a["action"] == "COMPRAR EN ZONA" and a["score"] >= min_buy and a["plan"]["rr"] >= min_rr:
                if s != "BTC" and alt_exposure >= expo_cap * (equity_curve[-1][1]):
                    continue
                pl = a["plan"]
                pending[s] = {"limit": pl["entry_zone_high"], "stop": pl["stop"], "tp1": pl["tp1"], "tp2": pl["tp2"], "tp3": pl["tp3"],
                              "score": a["score"], "phase": a["phase"], "rr": pl["rr"], "regime": reg,
                              "expires": d + limit_days * 86400000}
                orders.append({"fecha": day(d), "token": s, "lado": "COMPRA", "tipo": "LIMIT (colocada)",
                               "motivo": f"Señal {a['phase']} score {a['score']:.0f} R:R {pl['rr']:.1f} · stop {pl['stop']:.6g} · TP1 {pl['tp1']:.6g} TP2 {pl['tp2']:.6g} TP3 {pl['tp3']:.6g}",
                               "precio": round(pl["entry_zone_high"], 8), "cantidad": 0, "valor_usd": 0, "comision_usd": 0,
                               "pnl_usd": None, "caja_usd": round(cash, 2)})

    # posiciones aún abiertas: valoradas al último cierre (no se venden)
    open_pos = [{"token": s, "entrada_fecha": day(p["entry_date"]), "entrada": round(p["entry"], 8), "cantidad": round(p["qty_left"], 8),
                 "ultimo": round(p.get("last", p["entry"]), 8), "stop": round(p["stop"], 8), "objetivos": ",".join(p["hits"]) or "-",
                 "pnl_no_realizado_usd": round((p.get("last", p["entry"]) - p["entry"]) * p["qty_left"], 2)} for s, p in positions.items()]
    final = equity_curve[-1][1] if equity_curve else capital
    yrs = max(len(equity_curve) / 365, 1e-9)
    wins = [t for t in trades if t["pnl_usd"] > 0]
    gw, gl = sum(t["pnl_usd"] for t in wins), -sum(t["pnl_usd"] for t in trades if t["pnl_usd"] <= 0)
    b = hist["BTC"]; bdays = [d for d in days if d in idx["BTC"]]; b0 = b["c"][idx["BTC"][bdays[0]]]; b1 = b["c"][idx["BTC"][bdays[-1]]]
    btc_curve, bpeak, bdd = [], 0, 0
    for d in days:
        i = idx["BTC"].get(d)
        if i is None: continue
        v = capital * b["c"][i] / b0; bpeak = max(bpeak, v); bdd = min(bdd, v / bpeak - 1)
    summary = {
        "periodo": f"{day(days[0])} → {day(days[-1])}", "dias": len(days), "tokens": list(hist.keys()),
        "capital_inicial": capital, "capital_final": round(final, 2), "retorno_pct": round((final / capital - 1) * 100, 2),
        "cagr_pct": round(((final / capital) ** (1 / yrs) - 1) * 100, 2), "max_drawdown_pct": round(max_dd * 100, 2),
        "operaciones_cerradas": len(trades), "ganadoras": len(wins),
        "tasa_acierto_pct": round(len(wins) / len(trades) * 100, 1) if trades else None,
        "profit_factor": round(gw / gl, 2) if gl else None,
        "R_medio": round(sum(t["R"] for t in trades) / len(trades), 2) if trades else None,
        "mejor_operacion": max(trades, key=lambda t: t["pnl_usd"]) if trades else None,
        "peor_operacion": min(trades, key=lambda t: t["pnl_usd"]) if trades else None,
        "comisiones_pagadas": round(fees_paid, 2), "ordenes": len(orders),
        "posiciones_abiertas_al_final": open_pos,
        "btc_comprar_y_mantener_pct": round((b1 / b0 - 1) * 100, 2), "btc_max_drawdown_pct": round(bdd * 100, 2),
        "parametros": {"riesgo_por_operacion_pct": risk_pct, "max_por_activo_pct": max_pos_pct, "max_posiciones": max_positions,
                       "comision_por_lado_pct": fee * 100, "slippage_pct": slippage * 100, "rr_minimo": min_rr,
                       "validez_orden_limit_dias": limit_days, "max_dias_en_posicion": max_hold},
    }
    result = {"summary": summary, "orders": orders, "trades": trades, "equity": equity_curve, "regimes": regime_log}
    if out_dir:
        out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
        for name, rows in (("ordenes.csv", orders), ("operaciones.csv", trades)):
            if rows:
                with open(out / name, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        with open(out / "curva_capital.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f); w.writerow(["fecha", "capital_usd"]); w.writerows(equity_curve)
        (out / "resumen.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False), "utf-8")
    return result


def html_report(result, path):
    s, eq = result["summary"], result["equity"]
    vals = [v for _, v in eq]; lo, hi = min(vals), max(vals); W, H = 1000, 260
    pts = " ".join(f"{i / max(1, len(vals) - 1) * W:.1f},{H - (v - lo) / ((hi - lo) or 1) * (H - 20) - 10:.1f}" for i, v in enumerate(vals))
    def row(o, keys): return "<tr>" + "".join(f"<td>{'' if o.get(k) is None else o.get(k)}</td>" for k in keys) + "</tr>"
    ok = ["fecha", "token", "lado", "tipo", "motivo", "precio", "cantidad", "valor_usd", "comision_usd", "pnl_usd", "caja_usd"]
    tk = ["token", "entrada_fecha", "salida_fecha", "dias", "fase", "score", "regimen", "entrada", "stop_inicial", "tp1", "tp2", "tp3", "objetivos", "invertido_usd", "pnl_usd", "pnl_pct", "R"]
    kpi = [("Periodo", s["periodo"]), ("Capital inicial", f"${s['capital_inicial']:,.0f}"), ("Capital final", f"${s['capital_final']:,.0f}"),
           ("Retorno", f"{s['retorno_pct']}%"), ("CAGR", f"{s['cagr_pct']}%"), ("Máx. drawdown", f"{s['max_drawdown_pct']}%"),
           ("Operaciones", s["operaciones_cerradas"]), ("Acierto", f"{s['tasa_acierto_pct']}%"), ("Profit factor", s["profit_factor"]),
           ("R medio", s["R_medio"]), ("Comisiones", f"${s['comisiones_pagadas']:,.0f}"),
           ("BTC comprar y mantener", f"{s['btc_comprar_y_mantener_pct']}% (DD {s['btc_max_drawdown_pct']}%)")]
    html = f"""<!doctype html><html lang="es"><meta charset="utf-8"><title>Backtest Crypto Radar</title>
<style>body{{font:14px -apple-system,Segoe UI,sans-serif;background:#0b0f14;color:#e6edf3;margin:20px}}.k{{display:inline-block;background:#121821;border:1px solid #233042;border-radius:10px;padding:8px 12px;margin:4px}}
.k b{{display:block;font-size:18px}}table{{border-collapse:collapse;font-size:12px;width:100%}}td,th{{border-bottom:1px solid #233042;padding:4px 6px;text-align:left;white-space:nowrap}}th{{color:#8b98a8}}
svg{{background:#121821;border-radius:10px;width:100%;height:260px}}h2{{margin-top:28px}}.w{{overflow-x:auto}}</style>
<h1>Backtest de cartera · Crypto Radar</h1><p>Reglas de la app aplicadas día a día sin mirar el futuro. Comisión {s['parametros']['comision_por_lado_pct']}% por lado, slippage {s['parametros']['slippage_pct']}%, riesgo {s['parametros']['riesgo_por_operacion_pct']}% por operación, máx. {s['parametros']['max_posiciones']} posiciones. Tokens: {', '.join(s['tokens'])}.</p>
{''.join(f'<div class="k">{a}<b>{b}</b></div>' for a, b in kpi)}
<h2>Curva de capital</h2><svg viewBox="0 0 {W} {H}" preserveAspectRatio="none"><polyline fill="none" stroke="#38bdf8" stroke-width="2" points="{pts}"/></svg>
<h2>Operaciones cerradas ({len(result['trades'])})</h2><div class="w"><table><tr>{''.join(f'<th>{k}</th>' for k in tk)}</tr>{''.join(row(t, tk) for t in result['trades'])}</table></div>
<h2>Registro de órdenes ({len(result['orders'])})</h2><div class="w"><table><tr>{''.join(f'<th>{k}</th>' for k in ok)}</tr>{''.join(row(o, ok) for o in result['orders'])}</table></div>
<p style="color:#8b98a8">Limitaciones: universo de tokens actuales (sesgo de supervivencia); sin fundamentales ni sentimiento históricos; las velas diarias no muestran el orden intradía (si stop y TP caen el mismo día se asume primero el stop). Resultados pasados no garantizan resultados futuros. No es asesoría financiera.</p></html>"""
    Path(path).write_text(html, "utf-8")
