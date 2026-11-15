"""MARKET REGIME DETECTOR: BULLISH · NEUTRAL · BEARISH · HIGH VOLATILITY · CAPITULATION.

El régimen cambia las reglas: puntuación mínima de entrada, exposición máxima a altcoins, multiplicador del
tamaño de posición y fases que se permiten comprar. Las cifras de POLICY se validan en el backtest.
"""
from __future__ import annotations
import math
from .features import val, chg

LABEL = {"BULLISH": "Alcista", "NEUTRAL": "Neutral", "BEARISH": "Bajista",
         "HIGH VOLATILITY": "Alta volatilidad", "CAPITULATION": "Capitulación"}
ENTRY_PHASES = ("PRE-EXPLOSION", "ACCUMULATION", "BREAKOUT", "MOMENTUM")
POLICY = {
    "BULLISH":         {"min_score": 55, "max_alt_exposure": 70, "size_mult": 1.00, "phases": ENTRY_PHASES},
    "NEUTRAL":         {"min_score": 62, "max_alt_exposure": 45, "size_mult": 0.75, "phases": ENTRY_PHASES},
    "HIGH VOLATILITY": {"min_score": 68, "max_alt_exposure": 30, "size_mult": 0.50, "phases": ("PRE-EXPLOSION", "ACCUMULATION", "BREAKOUT")},
    "BEARISH":         {"min_score": 72, "max_alt_exposure": 15, "size_mult": 0.50, "phases": ("PRE-EXPLOSION", "BREAKOUT")},
    "CAPITULATION":    {"min_score": 78, "max_alt_exposure": 10, "size_mult": 0.25, "phases": ("PRE-EXPLOSION",)},
}


def detect(btc_f, bi, breadth=None, eth_f=None, ei=None, alt_rs=None, dominance=None, dominance_prev=None):
    """btc_f/bi: series de BTC y su índice. breadth: % de altcoins sobre su EMA50. alt_rs: mediana del rendimiento
    30 d de las altcoins menos el de BTC. Devuelve {"regime", "label", "policy", "reasons", "metrics"}."""
    p = btc_f.c[bi]
    e50, e200 = val(btc_f.ema50, bi), val(btc_f.ema200, bi)
    rv = val(btc_f.rv20, bi)
    vol_ann = rv * math.sqrt(365) * 100 if rv else None
    hh = max(btc_f.c[max(0, bi - 89):bi + 1])
    dd90 = (p / hh - 1) * 100 if hh else 0
    c7 = chg(btc_f, bi, 7)
    reasons = []
    m = {"btc_price": p, "btc_ema50": e50, "btc_ema200": e200, "btc_vol_annual_pct": vol_ann,
         "btc_drawdown_90d_pct": dd90, "btc_chg_7d": c7, "btc_chg_30d": chg(btc_f, bi, 30), "breadth": breadth,
         "alt_rs_30d": alt_rs, "btc_dominance": dominance}
    if eth_f is not None and ei is not None:
        m["eth_above_ema50"] = bool(val(eth_f.ema50, ei) and eth_f.c[ei] > eth_f.ema50[ei])
    b = breadth if breadth is not None else 50
    if (dd90 <= -25 and (vol_ann or 0) >= 60 and b <= 25) or ((c7 or 0) <= -20 and b <= 15):
        reg = "CAPITULATION"
        reasons.append(f"BTC {dd90:.0f}% desde su máximo de 90 días con volatilidad {vol_ann or 0:.0f}% anual y solo {b:.0f}% de altcoins sobre su EMA50")
    elif vol_ann is not None and vol_ann >= 75:
        reg = "HIGH VOLATILITY"
        reasons.append(f"Volatilidad de BTC {vol_ann:.0f}% anualizada")
    elif e200 and e50 and p > e50 > e200 and b >= 50:
        reg = "BULLISH"
        reasons.append("BTC sobre EMA50 > EMA200 y mayoría de altcoins en tendencia")
    elif e200 and e50 and p < e200 and e50 < e200 and b < 40:
        reg = "BEARISH"
        reasons.append("BTC bajo EMA200 con EMA50 < EMA200 y pocas altcoins en tendencia")
    else:
        reg = "NEUTRAL"
        reasons.append("Señales mixtas en BTC y amplitud")
    reasons.append(f"{b:.0f}% de las altcoins sobre su EMA50")
    if alt_rs is not None:
        reasons.append(f"Altcoins vs BTC en 30 días (mediana): {alt_rs:+.1f} puntos")
    if dominance is not None and dominance_prev is not None and abs(dominance - dominance_prev) >= 0.3:
        reasons.append(f"Dominancia BTC {dominance_prev:.1f}% → {dominance:.1f}%")
    return {"regime": reg, "label": LABEL[reg], "policy": POLICY[reg], "reasons": reasons, "metrics": m}
