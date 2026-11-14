"""Régimen de mercado: Bitcoin, dominancia, liquidez y amplitud de las altcoins."""
from __future__ import annotations


def detect(btc_t, breadth, fng, dom, dom_prev, mcap_chg_24h):
    p, e20, e50, e200 = btc_t["price"], btc_t["ema20"], btc_t["ema50"], btc_t["ema200"]
    rsi = btc_t["rsi"] or 50
    reasons = []
    if e200 and p > e200 and e50 > e200 and p > e50 and breadth >= 50:
        reg = "ALCISTA"
        reasons.append("BTC sobre EMA50 y EMA200 con EMA50 > EMA200")
    elif e200 and p < e200 and e50 < e200 and breadth < 40 and not (p > e20 and btc_t["bull_div"]):
        reg = "BAJISTA"
        reasons.append("BTC bajo EMA200 con EMA50 < EMA200 (estructura bajista)")
    elif e200 and p > e200 and (p < e50 or btc_t["bear_div"] or btc_t["distribution_volume"]):
        reg = "DISTRIBUCIÓN"
        reasons.append("BTC sobre EMA200 pero perdiendo fuerza (bajo EMA50 o divergencia bajista)")
    elif e200 and p < e200 and (p > e20 or btc_t["bull_div"]) and (fng is None or fng < 40):
        reg = "ACUMULACIÓN"
        reasons.append("BTC bajo EMA200 pero recuperando EMA20 con miedo en el mercado")
    else:
        reg = "LATERAL"
        reasons.append("Sin tendencia clara en BTC")
    reasons.append(f"{breadth:.0f}% de las altcoins analizadas está sobre su EMA50 (amplitud)")
    if fng is not None:
        reasons.append(f"Fear & Greed: {fng}")
    alt_bias = "NEUTRAL"
    if dom is not None and dom_prev is not None:
        if dom < dom_prev - 0.3 and breadth >= 50:
            alt_bias = "FAVORABLE A ALTCOINS"
            reasons.append(f"Dominancia BTC bajando ({dom_prev:.1f}% → {dom:.1f}%)")
        elif dom > dom_prev + 0.3:
            alt_bias = "FAVORABLE A BTC"
            reasons.append(f"Dominancia BTC subiendo ({dom_prev:.1f}% → {dom:.1f}%): capital rotando a BTC")
    if mcap_chg_24h is not None:
        reasons.append(f"Capitalización total 24h: {mcap_chg_24h:+.1f}%")
    return {"regime": reg, "alt_bias": alt_bias, "reasons": reasons, "btc_rsi": rsi}
