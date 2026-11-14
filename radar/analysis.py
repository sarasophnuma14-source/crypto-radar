"""Análisis por activo: fase de mercado, motores EARLY ENTRY / EXPLOSIVE MOMENTUM / EXIT INTELLIGENCE,
plan de entrada (zona, stop, TP1-3), puntuación 0-100 y acción."""
from __future__ import annotations
from . import indicators as ind
from .config import SCORING, classify

MIN_BUY_SCORE = {"ALCISTA": 70, "LATERAL": 75, "ACUMULACIÓN": 75, "DISTRIBUCIÓN": 80, "BAJISTA": 85}
EXPOSURE = {  # exposición máxima recomendada a altcoins (% del capital) según régimen
    "ALCISTA": 70, "LATERAL": 45, "ACUMULACIÓN": 40, "DISTRIBUCIÓN": 25, "BAJISTA": 15,
}


def _pct(a, b):
    return (a / b - 1) * 100 if a and b else None


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def technicals(d1, h4=None, w1=None):
    c, h, l, v = d1["c"], d1["h"], d1["l"], d1["v"]
    n = len(c)
    price = c[-1]
    e20, e50, e200 = ind.ema(c, 20), ind.ema(c, 50), ind.ema(c, 200)
    r = ind.rsi(c)
    ml, ms, mh = ind.macd(c)
    a = ind.atr(h, l, c)
    _, bbu, bbl, bbw = ind.bollinger(c)
    ob = ind.obv(c, v)
    vw = ind.rolling_vwap(h, l, c, v, 20)
    t = {"price": price, "bars": n}
    t["ema20"], t["ema50"], t["ema200"] = ind.last(e20), ind.last(e50), (e200[-1] if n >= 200 else None)
    t["rsi"] = ind.last(r)
    t["atr"] = ind.last(a) or price * 0.05
    t["atr_pct"] = t["atr"] / price * 100
    t["macd_hist"] = ind.last(mh)
    hist_recent = [x for x in mh[-6:] if x is not None]
    t["macd_bull_cross"] = len(hist_recent) >= 2 and hist_recent[-1] > 0 and min(hist_recent[:-1]) < 0
    t["macd_bear_cross"] = len(hist_recent) >= 2 and hist_recent[-1] < 0 and max(hist_recent[:-1]) > 0
    t["macd_fading"] = len(hist_recent) >= 4 and hist_recent[-1] > 0 and hist_recent[-1] < hist_recent[-2] < hist_recent[-3]
    widths = [x for x in bbw[-120:] if x is not None]
    t["bb_squeeze"] = bool(widths) and widths[-1] <= sorted(widths)[max(0, int(len(widths) * 0.2) - 1)]
    vol30 = sum(v[-31:-1]) / 30 if n > 31 else (sum(v) / n)
    vol3 = sum(v[-3:]) / 3
    t["vol_ratio"] = vol3 / vol30 if vol30 else 1.0
    t["vol_usd_24h"] = v[-1]
    win = min(20, n - 1)
    t["obv_flow"] = (ob[-1] - ob[-1 - win]) / (sum(v[-win:]) or 1)
    t["vwap20"] = ind.last(vw)
    t["vwap_recovery"] = bool(t["vwap20"]) and price > t["vwap20"] and n > 6 and vw[-6] is not None and c[-6] < vw[-6]
    hh30 = max(h[-31:-1]) if n > 31 else max(h[:-1] or h)
    ll30 = min(l[-31:-1]) if n > 31 else min(l)
    t["hh30"], t["ll30"] = hh30, ll30
    t["breakout"] = price > hh30
    t["breakout_volume"] = t["breakout"] and t["vol_ratio"] >= 1.3
    t["breakout_no_volume"] = t["breakout"] and t["vol_ratio"] < 1.1
    t["breakout_confirmed"] = n > 33 and price > hh30 and c[-2] > max(h[-32:-2])
    t["failed_breakout"] = (not t["breakout"]) and max(h[-5:]) > hh30 and price < hh30 * 0.98
    t["chg_7d"] = _pct(price, c[-8]) if n > 8 else None
    t["chg_30d"] = _pct(price, c[-31]) if n > 31 else None
    t["chg_90d"] = _pct(price, c[-91]) if n > 91 else None
    lo90, hi90 = min(l[-90:]), max(h[-90:])
    t["range_pos_90"] = (price - lo90) / (hi90 - lo90) if hi90 > lo90 else 0.5
    t["range_60_pct"] = (max(h[-60:]) - min(l[-60:])) / price * 100
    t["from_high_pct"] = _pct(price, max(h))
    t["ext_atr"] = (price - t["ema20"]) / t["atr"] if t["ema20"] else 0
    t["bear_div"] = ind.divergence(c, r, 40, "bearish")
    t["bull_div"] = ind.divergence(c, r, 40, "bullish")
    t["support_retest"] = bool(t["ema20"]) and min(l[-3:]) <= t["ema20"] + 0.3 * t["atr"] and price > t["ema20"]
    t["ema50_breakdown"] = bool(t["ema50"]) and price < t["ema50"] and n > 2 and e50[-2] is not None and c[-2] >= e50[-2]
    up_v = sum(v[i] for i in range(n - 10, n) if c[i] >= c[i - 1])
    dn_v = sum(v[i] for i in range(n - 10, n) if c[i] < c[i - 1])
    t["distribution_volume"] = t["range_pos_90"] > 0.7 and dn_v > up_v * 1.3
    t["ema20_slope"] = ind.slope(e20, 10)
    # 4H
    if h4 and len(h4["c"]) > 60:
        c4 = h4["c"]
        e50_4 = ind.ema(c4, 50)
        _, _, mh4 = ind.macd(c4)
        t["h4_trend_up"] = c4[-1] > ind.last(e50_4)
        t["h4_rsi"] = ind.last(ind.rsi(c4))
        t["h4_macd_up"] = (ind.last(mh4) or 0) > 0
        t["h4_bear_div"] = ind.divergence(c4, ind.rsi(c4), 40, "bearish")
    # 1W
    if w1 and len(w1["c"]) > 25:
        cw = w1["c"]
        t["w1_trend_up"] = cw[-1] > ind.last(ind.ema(cw, 20))
        t["w1_rsi"] = ind.last(ind.rsi(cw))
    # niveles para el plan
    ph, pl = ind.pivots(h[-365:], l[-365:], 3, 3)
    off = max(0, n - 365)
    t["pivot_highs"] = sorted({round(h[off + i], 12) for i in ph})
    t["pivot_lows"] = sorted({round(l[off + i], 12) for i in pl if off + i >= n - 120})
    lo180, hi180 = min(l[-180:]), max(h[-180:])
    t["fib_1272"] = hi180 + (hi180 - lo180) * 0.272
    t["fib_1618"] = hi180 + (hi180 - lo180) * 0.618
    t["ath_window"] = max(h)
    return t


def phase(t, regime_btc_bear=False):
    if (t["rsi"] or 0) >= 76 or t["ext_atr"] >= 3.2 or (t["chg_7d"] or 0) >= 45 or (t["chg_30d"] or 0) >= 110:
        return "SOBREEXTENDIDO"
    if t["range_pos_90"] >= 0.7 and (t["bear_div"] or t["distribution_volume"] or t["failed_breakout"]
                                    or (t["obv_flow"] < -0.05 and (t["chg_30d"] or 0) > 0)):
        return "DISTRIBUCIÓN"
    recent_break = t["breakout_volume"] or (t["breakout"] and t["vol_ratio"] >= 1.15 and (t["chg_30d"] or 0) < 60)
    if recent_break:
        return "RUPTURA INICIAL"
    bear = t["ema200"] and t["price"] < t["ema200"] and t["ema50"] and t["ema50"] < t["ema200"] and t["price"] < t["ema50"]
    accum = (t["range_pos_90"] <= 0.65 and (t["bb_squeeze"] or t["range_60_pct"] <= 45)
             and t["obv_flow"] >= -0.02 and t["ema20_slope"] > -3)
    if accum:
        return "ACUMULACIÓN"
    aligned = t["ema20"] and t["ema50"] and t["price"] > t["ema20"] > t["ema50"]
    if aligned and 50 <= (t["rsi"] or 0) < 76:
        return "MOMENTUM"
    if bear:
        return "BAJISTA"
    if t["ema50"] and t["price"] < t["ema20"] and t["price"] > (t["ema200"] or 0):
        return "RETROCESO"
    return "LATERAL"


def engines(t):
    """Puntuaciones 0-100 de los tres motores y lista de señales detectadas."""
    sig_e, sig_m, sig_x = [], [], []
    e = 0
    if t["bb_squeeze"]: e += 15; sig_e.append("Compresión Bollinger (squeeze)")
    if t["range_pos_90"] <= 0.55: e += 10; sig_e.append("Precio en zona baja/media del rango 90d")
    if t["obv_flow"] > 0.05: e += 15; sig_e.append("OBV en acumulación")
    if 1.2 <= t["vol_ratio"] <= 4: e += 10; sig_e.append(f"Volumen en expansión x{t['vol_ratio']:.1f}")
    if t["macd_bull_cross"]: e += 10; sig_e.append("Cruce alcista MACD")
    if t["rsi"] and 40 <= t["rsi"] <= 60 and t["rsi"] > 45: e += 10; sig_e.append(f"RSI recuperando ({t['rsi']:.0f})")
    if t["vwap_recovery"]: e += 10; sig_e.append("Recuperación del VWAP")
    if t["support_retest"]: e += 10; sig_e.append("Retest de soporte EMA20")
    if t["bull_div"]: e += 10; sig_e.append("Divergencia alcista RSI")
    if t["breakout_volume"]: e += 10; sig_e.append("Ruptura de resistencia con volumen")
    if (t["chg_30d"] or 0) > 60: e -= 25
    m = 0
    if t["ema20"] and t["ema50"] and t["price"] > t["ema20"] > t["ema50"]: m += 20; sig_m.append("EMA20 > EMA50 con precio encima")
    if t["ema200"] and t["price"] > t["ema200"]: m += 10; sig_m.append("Sobre EMA200")
    if t["breakout_volume"]: m += 20; sig_m.append("Ruptura con volumen anormal")
    if 1.5 <= t["vol_ratio"]: m += 15; sig_m.append(f"Volumen anormal x{t['vol_ratio']:.1f}")
    if (t["macd_hist"] or 0) > 0: m += 10
    if t.get("h4_trend_up"): m += 10; sig_m.append("Tendencia 4H alcista")
    if t.get("w1_trend_up"): m += 5
    if t["obv_flow"] > 0.1: m += 10; sig_m.append("Entrada de capital (OBV)")
    if t["breakout_no_volume"]: m -= 15; sig_m.append("Ruptura SIN volumen (dudosa)")
    if (t["chg_7d"] or 0) > 40: m -= 20; sig_m.append("Subida vertical: especulativa")
    x = 0
    checks = [
        (t["bear_div"], 20, "Divergencia bajista RSI (1D)"),
        (t.get("h4_bear_div"), 10, "Divergencia bajista RSI (4H)"),
        (t["macd_bear_cross"], 15, "Cruce bajista MACD"),
        (t["distribution_volume"], 15, "Volumen de distribución"),
        (t["obv_flow"] < -0.08, 10, "OBV cayendo"),
        (t["ema50_breakdown"], 15, "Pérdida de EMA50"),
        (t["failed_breakout"], 15, "Ruptura fallida"),
        (t["macd_fading"] and (t["rsi"] or 0) > 65, 10, "Agotamiento del impulso"),
        ((t["rsi"] or 0) >= 76, 15, "RSI sobrecomprado"),
    ]
    for cond, pts, label in checks:
        if cond:
            x += pts
            sig_x.append(label)
    return (int(_clamp(e, 0, 100)), int(_clamp(m, 0, 100)), int(_clamp(x, 0, 100)), sig_e, sig_m, sig_x)


def _cluster(levels, tol=0.02):
    out = []
    for lv in sorted(levels):
        if not out or lv > out[-1] * (1 + tol):
            out.append(lv)
    return out


def trade_plan(t, settings, regime="LATERAL"):
    price, a = t["price"], t["atr"]
    cands = [x for x in [t["ema20"], t["ema50"], t["vwap20"]] + t["pivot_lows"]
             if x and price - 3 * a < x < price * 0.997]
    if t["breakout"] and t["hh30"] < price:
        cands.append(t["hh30"])
    support = max(cands) if cands else price - 1.5 * a
    ideal = min(price, support + 0.3 * a)
    lows_below = [x for x in t["pivot_lows"] if support - 2 * a < x < support]
    stop = (min(lows_below) - 0.3 * a) if lows_below else support - 1.0 * a
    stop = min(stop, ideal - float(settings.get("stop_atr_min", 0.8)) * a)
    if stop <= 0:
        stop = ideal * 0.85
    R = ideal - stop
    targets = _cluster([x for x in t["pivot_highs"] + [t["ath_window"], t["fib_1272"], t["fib_1618"]] if x > ideal * 1.03])
    def nxt(minv):
        for x in targets:
            if x >= minv:
                return x
        return None
    tp1 = nxt(ideal + 1.0 * R) or ideal + 1.5 * R
    tp2 = nxt(max(tp1 * 1.02, ideal + 2 * R)) or max(t["fib_1272"], ideal + 2.5 * R)
    tp3 = nxt(tp2 * 1.03) or max(t["fib_1618"], tp2 + (tp2 - ideal) * 0.6)
    if tp3 <= tp2:
        tp3 = tp2 + (tp2 - ideal) * 0.6
    confirm = t["hh30"] * 1.005 if price < t["hh30"] else price
    rr = (tp2 - ideal) / R if R > 0 else 0
    rr3 = (tp3 - ideal) / R if R > 0 else 0
    cap = float(settings.get("capital_usd", 1000))
    risk_usd = cap * float(settings.get("risk_per_trade_pct", 1)) / 100
    max_pos = cap * min(float(settings.get("max_position_pct", 20)), EXPOSURE.get(regime, 40)) / 100
    pos_usd = min(risk_usd / R * ideal, max_pos) if R > 0 else 0
    return {
        "entry_ideal": ideal, "entry_aggressive": price, "entry_confirmation": confirm,
        "entry_zone_high": ideal + 0.5 * a, "stop": stop, "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "final_exit": f"Cierre diario bajo EMA50 ({t['ema50']:.6g})" if t["ema50"] else "Cierre diario bajo el stop",
        "risk_pct": R / ideal * 100 if ideal else None,
        "return_tp2_pct": (tp2 / ideal - 1) * 100, "return_tp3_pct": (tp3 / ideal - 1) * 100,
        "rr": rr, "rr_tp3": rr3, "position_usd": pos_usd, "risk_usd": risk_usd,
        "plan_note": "Vender ~40% en TP1 y subir stop a la entrada; ~35% en TP2; resto en TP3 o al invalidarse la estructura.",
    }


def score(t, plan, market, ctx, phase_name, eng):
    """market: fila CoinGecko (o None en backtest). ctx: fng, funding, btc_30d, catalysts."""
    blocks, notes = {}, []
    # 1. Estructura técnica
    s = 0.0
    if t["ema20"] and t["price"] > t["ema20"]: s += 0.15
    if t["ema20"] and t["ema50"] and t["ema20"] > t["ema50"]: s += 0.15
    if t["ema200"] is None: s += 0.05
    elif t["price"] > t["ema200"]: s += 0.15
    rv = t["rsi"] or 50
    s += 0.15 if 45 <= rv <= 68 else 0.05 if 68 < rv < 75 else 0.08 if (rv < 40 and t["bull_div"]) else 0
    if (t["macd_hist"] or 0) > 0: s += 0.1
    if t["macd_bull_cross"]: s += 0.05
    if t["breakout_volume"]: s += 0.1
    elif t["bb_squeeze"]: s += 0.06
    if t.get("h4_trend_up"): s += 0.1
    if t.get("w1_trend_up"): s += 0.05
    if phase_name == "SOBREEXTENDIDO": s -= 0.3
    if t["bear_div"]: s -= 0.15
    if t["failed_breakout"]: s -= 0.2
    blocks["technical_structure"] = _clamp(s)
    # 2. Volumen y liquidez
    s = 0.0
    vol24 = (market or {}).get("total_volume") or t["vol_usd_24h"]
    mcap = (market or {}).get("market_cap")
    if vol24 >= 20e6: s += 0.2
    elif vol24 >= 5e6: s += 0.1
    if mcap:
        turn = vol24 / mcap
        if 0.03 <= turn <= 0.3: s += 0.3
        elif turn > 0.6:
            s += 0.05; notes.append("Volumen/capitalización muy alto: posible volumen artificial o especulativo")
        else: s += 0.12
    else:
        s += 0.12
    if 1.2 <= t["vol_ratio"] <= 3.5: s += 0.25
    elif t["vol_ratio"] > 5: s += 0.08
    elif t["vol_ratio"] >= 0.9: s += 0.1
    if t["obv_flow"] > 0.05: s += 0.25
    elif t["obv_flow"] > 0: s += 0.1
    blocks["volume_and_liquidity"] = _clamp(s)
    # 3. On-chain: sin fuente gratuita verificable -> N/D (no se inventa)
    blocks["on_chain_activity"] = None
    # 4. Fundamentales y tokenomics
    if market and market.get("market_cap"):
        s = 0.0
        fdv = market.get("fully_diluted_valuation")
        ratio = market["market_cap"] / fdv if fdv else None
        if ratio is None: s += 0.15
        elif ratio >= 0.85: s += 0.4
        elif ratio >= 0.6: s += 0.25
        elif ratio >= 0.4: s += 0.1; notes.append(f"Solo {ratio*100:.0f}% del supply en circulación: riesgo de unlocks")
        else: notes.append(f"Solo {ratio*100:.0f}% del supply en circulación: fuerte dilución futura")
        rank = market.get("market_cap_rank") or 999
        s += 0.25 if rank <= 50 else 0.18 if rank <= 150 else 0.1
        ath_chg = market.get("ath_change_percentage")
        if ath_chg is not None:
            if -85 <= ath_chg <= -35: s += 0.25
            elif ath_chg > -35: s += 0.15
            else: s += 0.05; notes.append("Más de 85% bajo su ATH")
        blocks["fundamentals_and_tokenomics"] = _clamp(s + 0.1)
    else:
        blocks["fundamentals_and_tokenomics"] = None
    # 5. Catalizadores: solo si el usuario registró uno verificable
    cat = ctx.get("catalyst")
    blocks["market_catalysts"] = 0.8 if cat else None
    # 6. Riesgo / beneficio
    rr = plan["rr"]
    blocks["risk_reward_ratio"] = 1.0 if rr >= 5 else 0.85 if rr >= 4 else 0.7 if rr >= 3 else 0.4 if rr >= 2 else 0.1
    # 7. Sentimiento
    parts, s = 0, 0.0
    fng = ctx.get("fng")
    if fng is not None:
        parts += 1
        early = phase_name in ("ACUMULACIÓN", "RUPTURA INICIAL", "RETROCESO")
        s += (0.9 if early else 0.5) if fng < 30 else 0.7 if fng <= 65 else 0.4 if fng <= 80 else 0.1
    fr = ctx.get("funding")
    if fr is not None:
        parts += 1
        if fr > 0.0005: s += 0.0; notes.append(f"Funding excesivo ({fr*100:.3f}%/8h): euforia apalancada")
        elif fr > 0.0002: s += 0.5
        else: s += 0.9
    rs = ctx.get("rel_strength")
    if rs is not None:
        parts += 1
        s += _clamp(0.5 + rs / 40)
    blocks["market_sentiment"] = s / parts if parts else None
    avail = {k: v for k, v in blocks.items() if v is not None}
    wsum = sum(SCORING[k] for k in avail)
    total = sum(SCORING[k] * v for k, v in avail.items()) / wsum * 100 if wsum else 0
    coverage = wsum / 100
    return round(total, 1), coverage, {k: (None if v is None else round(v * SCORING[k], 1)) for k, v in blocks.items()}, notes


def analyze(symbol, d1, h4=None, w1=None, market=None, ctx=None, settings=None, regime="LATERAL"):
    ctx = ctx or {}
    settings = settings or {}
    t = technicals(d1, h4, w1)
    ph = phase(t)
    eng = engines(t)
    plan = trade_plan(t, settings, regime)
    sc, cov, breakdown, notes = score(t, plan, market, ctx, ph, eng)
    is_alt = symbol not in ("BTC",)
    if is_alt and regime in ("BAJISTA", "DISTRIBUCIÓN"):
        sc = round(sc - 5, 1)
        notes.append("Régimen de mercado desfavorable: -5 puntos a altcoins")
    min_rr = float(settings.get("min_risk_reward", 3.0))
    min_buy = MIN_BUY_SCORE.get(regime, 75)
    price = t["price"]
    if ph in ("SOBREEXTENDIDO", "DISTRIBUCIÓN"):
        action = "EVITAR / NO PERSEGUIR" if ph == "SOBREEXTENDIDO" else "EVITAR (DISTRIBUCIÓN)"
    elif ph == "BAJISTA" and sc < min_buy:
        action = "EVITAR (TENDENCIA BAJISTA)"
    elif sc < 60:
        action = "RECHAZAR"
    elif plan["rr"] < min_rr:
        action = "VIGILAR (R:R < %.1f)" % min_rr
    elif sc < min_buy:
        action = "WATCHLIST"
    elif settings.get("confirm_breakout") and ph == "RUPTURA INICIAL" and not (t["breakout_confirmed"] and t["vol_ratio"] >= 1.5):
        action = "ESPERAR CONFIRMACIÓN"
    elif price <= plan["entry_zone_high"]:
        action = "COMPRAR EN ZONA"
    elif ph == "ACUMULACIÓN" and price < t["hh30"]:
        action = "ESPERAR RUPTURA"
    else:
        action = "ESPERAR RETROCESO"
    if sc >= 80 and cov >= 0.65 and ph in ("RUPTURA INICIAL", "MOMENTUM", "ACUMULACIÓN") and regime not in ("BAJISTA",):
        conf = "ALTA"
    elif sc >= 70 and cov >= 0.55:
        conf = "MEDIA"
    else:
        conf = "BAJA"
    return {
        "symbol": symbol, "price": price, "phase": ph, "score": sc, "class": classify(sc),
        "coverage": round(cov * 100), "breakdown": breakdown, "action": action, "confidence": conf,
        "early_score": eng[0], "momentum_score": eng[1], "exit_risk": eng[2],
        "signals_early": eng[3], "signals_momentum": eng[4], "signals_exit": eng[5],
        "notes": notes, "plan": plan,
        "tech": {k: t[k] for k in ("rsi", "ema20", "ema50", "ema200", "atr_pct", "vol_ratio", "obv_flow",
                                    "chg_7d", "chg_30d", "chg_90d", "range_pos_90", "from_high_pct", "bb_squeeze",
                                    "breakout", "hh30", "macd_hist")} | {
            "h4_rsi": t.get("h4_rsi"), "h4_trend_up": t.get("h4_trend_up"), "w1_trend_up": t.get("w1_trend_up")},
    }
