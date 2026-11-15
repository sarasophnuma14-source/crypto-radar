"""MEME RADAR: vigilancia de memecoins con datos verificables.

Por moneda: antigüedad en el exchange, liquidez (volumen medio y libro si se lee), volumen relativo, cambios,
caída desde el máximo, capitalización y FDV cuando CoinGecko los da, riesgo de manipulación, fase del motor
y una etiqueta NUEVA / JOVEN / ESTABLECIDA. Los datos on-chain (holders, concentración, pool de liquidez,
contratos) NO se consultan: se muestran como N/D. Nunca se inventan.
"""
from __future__ import annotations
import datetime as dt
from . import data, storage
from .config import load_settings
from .quant import engine, features

FILE = "meme_radar.json"
ONCHAIN_ND = "N/D: requiere un proveedor on-chain verificable (no conectado)"


def _age_label(days, capped):
    if capped:
        return "ESTABLECIDA", f"≥ {days} días en Binance"
    if days < 90:
        return "NUEVA", f"{days} días en Binance"
    if days < 365:
        return "JOVEN", f"{days} días en Binance"
    return "ESTABLECIDA", f"{days} días en Binance"


def risk_profile(age_days, avg_vol, mcap, fdv, manip_risk, atr_pct):
    """Riesgo 0-100 con sus razones. Solo usa los datos disponibles; lo que falta queda como N/D."""
    pts, why = 0, []
    if age_days < 30:
        pts += 25; why.append("Listada hace menos de 30 días")
    elif age_days < 90:
        pts += 15; why.append("Listada hace menos de 90 días")
    if avg_vol is not None and avg_vol < 2e6:
        pts += 20; why.append(f"Liquidez baja (${avg_vol / 1e6:.1f} M/día)")
    elif avg_vol is not None and avg_vol < 10e6:
        pts += 8; why.append(f"Liquidez moderada (${avg_vol / 1e6:.1f} M/día)")
    if mcap and fdv and fdv > mcap * 2:
        pts += 15; why.append(f"FDV {fdv / mcap:.1f}× la capitalización (desbloqueos pendientes)")
    if mcap and mcap < 50e6:
        pts += 10; why.append(f"Capitalización pequeña (${mcap / 1e6:.0f} M)")
    if atr_pct and atr_pct > 12:
        pts += 10; why.append(f"Volatilidad extrema (ATR {atr_pct:.0f}% diario)")
    pts += manip_risk * 0.3
    if manip_risk >= 40:
        why.append(f"Riesgo de manipulación {manip_risk}/100")
    return min(100, round(pts)), why


def scan(settings=None, symbols=None):
    from .memes import MEMES
    settings = settings or load_settings()
    q = settings.get("quote", "USDT")
    cats = (storage.read("categories_cache.json", {}) or {}).get("map", {})
    syms = list(dict.fromkeys((symbols or settings.get("meme_list") or MEMES) +
                              [s for s, c in cats.items() if "MEMECOINS" in c]))
    try:
        tradable = data.binance_symbols(q)
        syms = [s for s in syms if s in tradable]
    except Exception:
        pass
    mk = {m["symbol"].upper(): m for m in ((storage.read("markets_cache.json", {}) or {}).get("markets") or [])}
    btc = features.compute(data.klines("BTC" + q, "1d", 400, closed=True))
    bi = len(btc.c) - 1
    rows, errors = [], []
    for s in syms[:80]:
        try:
            k = data.klines(s + q, "1d", 400, closed=True)
            if len(k["c"]) < 15:
                errors.append(f"{s}: historial insuficiente"); continue
            f = features.compute(k); i = len(f.c) - 1
            m = mk.get(s) or {}
            a = engine.analyze(s, f, i, btc, bi, settings=settings, market=m, check_quality=True)
            days = len(k["c"]); capped = days >= 399   # 400 pedidas menos la vela abierta
            label, age_txt = _age_label(days, capped)
            mt = a["metrics"]
            ath = max(f.h)
            risk, why = risk_profile(days, mt["avg_volume_usd"], m.get("market_cap"), m.get("fully_diluted_valuation"),
                                     a["manipulation"]["risk"], mt["atr_pct"])
            rows.append({"symbol": s, "name": m.get("name", s), "price": f.c[i], "age_days": days, "age_capped": capped,
                         "age_label": label, "age_text": age_txt, "avg_volume_usd": mt["avg_volume_usd"],
                         "rel_volume": mt["rel_volume"], "chg_24h": mt["chg_24h"], "chg_7d": mt["chg_7d"],
                         "chg_30d": mt["chg_30d"], "from_high_pct": (f.c[i] / ath - 1) * 100 if ath else None,
                         "market_cap": m.get("market_cap"), "fdv": m.get("fully_diluted_valuation"),
                         "score": a["score"], "phase": a["phase"], "phase_label": a["phase_label"], "action": a["action"],
                         "manipulation": a["manipulation"], "meme_risk": risk, "meme_risk_reasons": why,
                         "plan": {k2: a["plan"][k2] for k2 in ("entry_low", "entry_high", "stop", "tp1", "tp2", "tp3", "rr")},
                         "quality": (a.get("quality") or {}).get("score"),
                         "onchain": {"holders": ONCHAIN_ND, "top10_concentration": ONCHAIN_ND,
                                     "liquidity_pool": ONCHAIN_ND, "contract": ONCHAIN_ND}})
        except Exception as e:
            errors.append(f"{s}: {e}")
    rows.sort(key=lambda r: (r["phase"] in ("PRE-EXPLOSION", "ACCUMULATION", "BREAKOUT"), r["score"] - r["meme_risk"] * 0.3),
              reverse=True)
    out = {"at": dt.datetime.now(dt.timezone.utc).isoformat(), "coins": rows, "errors": errors[:20],
           "note": "Memecoins: riesgo extremo. Datos de exchange (Binance) y CoinGecko; on-chain N/D."}
    storage.write(FILE, out)
    return out


def state():
    return storage.read(FILE, {}) or {"coins": [], "note": "Aún no se ha ejecutado el radar de memecoins."}
