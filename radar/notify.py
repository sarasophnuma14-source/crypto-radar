"""Textos de las alertas (Telegram, escritorio y panel) y resúmenes diario y semanal.

Cada alerta de señal incluye: precio, puntaje, justificación, riesgos, invalidación, plan, fecha y hora,
y la calidad de los datos. Nunca promete rendimientos.
"""
from __future__ import annotations
import datetime as dt
from . import storage, alerts

DISCLAIMER = "Solo análisis, no es asesoría financiera. Las cripto pueden perder todo su valor."


def fmt(x):
    if x is None:
        return "N/D"
    return f"${x:,.2f}" if x >= 1 else f"${x:.6g}"


def pct(x, sign=True):
    return "N/D" if x is None else (f"{x:+.1f}%" if sign else f"{x:.1f}%")


def _stamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _quality(r):
    q = r.get("quality") or {}
    if q.get("score") is None:
        return "N/D"
    issues = "; ".join(q.get("issues", [])[:2])
    return f"{q['score']}/100" + (f" ({issues})" if issues else "")


def _ev(e):
    return e.get("text", "") if isinstance(e, dict) else str(e)


def _justification(r, n=3):
    out = []
    fams = sorted(((k, v) for k, v in (r.get("families") or {}).items() if v.get("score") is not None),
                  key=lambda kv: -(kv[1]["score"] * kv[1]["weight"]))
    for k, v in fams[:n]:
        ev = (v.get("evidence") or [""])[0]
        out.append(f"• {v['label']} {v['score'] * 100:.0f}/100" + (f": {ev}" if ev else ""))
    return out


def _risks(r):
    out = []
    man = r.get("manipulation") or {}
    out.append(f"• Riesgo de manipulación {man.get('level', 'N/D').lower()} ({man.get('risk', 'N/D')}/100)"
               + (f": {_ev(man['evidence'][0])}" if man.get("evidence") else ""))
    for why in (r.get("phase_reasons") or [])[1:2]:
        out.append(f"• {why}")
    mt = r.get("metrics") or {}
    if (mt.get("atr_pct") or 0) > 8:
        out.append(f"• Volatilidad alta: ATR {mt['atr_pct']:.1f}% diario")
    if (mt.get("liquidity") or 1) < 0.4:
        out.append("• Liquidez limitada: usar órdenes límite y tamaño reducido")
    return out


def signal_text(r):
    pl, mt = r["plan"], r.get("metrics") or {}
    lines = [f"{r['phase_label']} · {r['action']}",
             f"Precio {fmt(r['price'])} · Puntaje {r['score']:.0f}/100 · Régimen {r.get('regime', 'N/D')}",
             f"24h {pct(mt.get('chg_24h'))} · 7d {pct(mt.get('chg_7d'))} · 30d {pct(mt.get('chg_30d'))} · "
             f"vs BTC 30d {pct(mt.get('rs_btc_30d'))} · Vol. relativo {('x%.1f' % mt['rel_volume']) if mt.get('rel_volume') else 'N/D'}",
             "", "Por qué:"] + _justification(r) + ["", "Riesgos:"] + _risks(r) + [
             "", "Plan:",
             f"• Zona de entrada {fmt(pl['entry_low'])} – {fmt(pl['entry_high'])}"
             + (f" (o ruptura sobre {fmt(pl['trigger_breakout'])})" if pl.get("trigger_breakout") else ""),
             f"• Invalidación / stop {fmt(pl['stop'])} ({pct(-(pl.get('risk_pct') or 0))})",
             f"• TP1 {fmt(pl['tp1'])} · TP2 {fmt(pl['tp2'])} · TP3 {fmt(pl['tp3'])} · R:R {pl['rr']:.1f}",
             f"• {pl['partials']}",
             "", f"Datos: velas diarias cerradas · calidad {_quality(r)} · {_stamp()}"]
    return "\n".join(lines)


def risk_text(r):
    man = r.get("manipulation") or {}
    ev = "\n".join(f"• {_ev(e)}" for e in (man.get("evidence") or [])[:4]) or "• Sin evidencia adicional"
    return (f"{r['phase_label']} · Precio {fmt(r['price'])} · Puntaje {r['score']:.0f}\n"
            f"Riesgo de manipulación {man.get('level', 'N/D')} ({man.get('risk', 'N/D')}/100)\n{ev}\n"
            f"{man.get('note', '')}\nAcción del sistema: {r['action']} — {r['action_reason']}\n"
            f"Datos: calidad {_quality(r)} · {_stamp()}")


def regime_text(prev_market, market, verdict):
    pol = market.get("policy") or {}
    reasons = "\n".join(f"• {x}" for x in (market.get("regime_reasons") or [])[:4])
    return (f"{prev_market.get('regime')} → {market['regime']}\n{reasons}\n"
            f"Nuevas reglas: puntaje mínimo {pol.get('min_score')}, exposición máx. en altcoins {pol.get('max_alt_exposure')}%, "
            f"tamaño x{pol.get('size_mult')}.\nVeredicto: {verdict}. {_stamp()}")


def tp_text(p, tp, price):
    nxt = {"tp1": "Plan: vender 33% y subir el stop a la entrada.", "tp2": "Plan: vender otro 33% y seguir con trailing.",
           "tp3": "Objetivo final: cerrar el resto o seguir con trailing de 3 ATR."}[tp]
    return f"{tp.upper()} {fmt(p[tp])} alcanzado. Precio {fmt(price)} ({pct((price / p['entry'] - 1) * 100)}). {nxt} {_stamp()}"


def exit_text(p, a):
    ex = a["exit"]
    why = "\n".join(f"• {x}" for x in ex["reasons"][:4])
    sell = f"Vender {ex['sell_fraction'] * 100:.0f}% de la posición. " if ex["sell_fraction"] else ""
    return (f"{ex['decision']} · Precio {fmt(a['price'])} · Entrada {fmt(p['entry'])} ({pct((a['price'] / p['entry'] - 1) * 100)}, "
            f"{ex['gain_R']:+.1f} R)\n{why}\n{sell}Stop sugerido {fmt(ex['suggested_stop'])}"
            + (f" · trailing {fmt(ex['trailing_stop'])}" if ex.get("trailing_stop") else "")
            + f"\nDatos: calidad {_quality(a)} · {_stamp()}")


def daily_text(rep):
    m = rep["market"]
    lines = [f"Régimen {m.get('regime_label', m['regime'])} · BTC {fmt(m['btc_price'])} (7d {pct(m.get('btc_chg_7d'))})",
             f"Amplitud: {pct(m.get('breadth'), False)} de altcoins sobre su EMA50", f"Veredicto: {rep['verdict']} — {rep['verdict_text']}", ""]
    if rep.get("ranking"):
        lines.append("Mejores oportunidades tempranas:")
        for r in rep["ranking"][:5]:
            lines.append(f"{r['rank']}. {r['symbol']} · {r['phase_label']} · {r['score']:.0f} · {r['action']} · "
                         f"zona {fmt(r['entry_low'])}–{fmt(r['entry_high'])} · stop {fmt(r['stop'])}")
    else:
        lines.append("Sin oportunidades que cumplan las reglas del régimen.")
    if rep.get("avoid"):
        lines += ["", "Evitar: " + ", ".join(a["symbol"] for a in rep["avoid"][:6])]
    pos = [p for p in (storage.read("positions.json", []) or []) if p.get("status") == "OPEN"]
    if pos:
        lines += ["", "Tus posiciones:"] + [f"• {p['symbol']} {pct(p.get('pnl_pct'))} · {(p.get('exit') or {}).get('decision', 'MANTENER')}"
                                            for p in pos[:8]]
    lines += ["", f"{rep.get('analyzed', 0)} activos analizados · {_stamp()}"]
    return "\n".join(lines)


def weekly_text():
    scans = storage.read("scans.json", []) or []
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=7)).isoformat()
    week = [s for s in scans if s["at"] >= since]
    regs = {}
    for s in week:
        regs[s.get("regime")] = regs.get(s.get("regime"), 0) + 1
    j = [x for x in (storage.read("journal.json", []) or []) if x.get("at", "") >= since or x.get("closed_at", "") >= since]
    closed = [x for x in j if x["status"] == "CLOSED" and x.get("r_multiple") is not None]
    al = [a for a in (storage.read("alerts.json", []) or []) if a["at"] >= since]
    lines = [f"{len(week)} escaneos · regímenes: " + (", ".join(f"{k} {v}" for k, v in regs.items()) or "N/D"),
             f"{len(al)} alertas emitidas · {sum(1 for x in j if x.get('at', '') >= since)} señales nuevas en el diario"]
    if closed:
        wins = sum(x["r_multiple"] > 0 for x in closed)
        lines.append(f"Señales cerradas: {len(closed)} · acierto {wins / len(closed) * 100:.0f}% · "
                     f"resultado {sum(x['r_multiple'] for x in closed):+.1f} R (registro real, sin simular)")
    else:
        lines.append("Ninguna señal del diario se cerró esta semana.")
    lines.append(_stamp())
    return "\n".join(lines)


def maybe_summaries(rep, settings):
    """Resumen diario (primer escaneo tras las 00:00 UTC) y semanal (lunes). Uno por periodo, sin duplicados."""
    now = dt.datetime.now(dt.timezone.utc)
    today, wk = now.strftime("%Y-%m-%d"), now.strftime("%G-W%V")
    sent = {}

    def mark(st):
        st = st or {}
        sent["daily"] = st.get("daily") != today
        sent["weekly"] = now.weekday() == 0 and st.get("weekly") != wk
        if sent["daily"]:
            st["daily"] = today
        if sent["weekly"]:
            st["weekly"] = wk
        return st
    storage.update("summaries.json", mark, {})
    if sent.get("daily"):
        alerts.emit(settings, "DAILY SUMMARY", "MERCADO", daily_text(rep), dedupe_hours=20)
    if sent.get("weekly"):
        alerts.emit(settings, "WEEKLY SUMMARY", "MERCADO", weekly_text(), dedupe_hours=24 * 6)
