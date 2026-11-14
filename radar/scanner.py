"""Orquesta un escaneo completo y genera el informe, el ranking y las alertas."""
from __future__ import annotations
import datetime as dt
import time
import traceback
import uuid
from . import data, storage, alerts
from .analysis import analyze, technicals, EXPOSURE, MIN_BUY_SCORE
from .config import CATEGORIES, STABLES, load_settings
from .regime import detect

status = {"scanning": False, "progress": "", "last_error": None, "last_watch": None}


def now():
    return dt.datetime.now(dt.timezone.utc)


def weekly_from_daily(d1):
    out = {"t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    for i in range(0, len(d1["c"]), 7):
        j = min(i + 7, len(d1["c"]))
        out["t"].append(d1["t"][i]); out["o"].append(d1["o"][i])
        out["h"].append(max(d1["h"][i:j])); out["l"].append(min(d1["l"][i:j]))
        out["c"].append(d1["c"][j - 1]); out["v"].append(sum(d1["v"][i:j]))
    return out


def category_map(force=False):
    cache = storage.read("categories_cache.json", {}) or {}
    if not force and cache.get("at") and (time.time() - cache["at"]) < 86400:
        return cache.get("map", {})
    m = {}
    for label, cat in CATEGORIES.items():
        try:
            for row in data.cg_markets(250, 1, cat):
                m.setdefault(row["symbol"].upper(), [])
                if label not in m[row["symbol"].upper()]:
                    m[row["symbol"].upper()].append(label)
        except Exception:
            pass
        time.sleep(3)
    if m:
        storage.write("categories_cache.json", {"at": time.time(), "map": m})
    return m or cache.get("map", {})


def cap_bucket(mcap):
    if not mcap: return "N/D"
    return "LARGE CAP" if mcap >= 10e9 else "MID CAP" if mcap >= 1e9 else "SMALL CAP"


def _progress(msg):
    status["progress"] = msg


def run_scan(settings=None):
    if status["scanning"]:
        return None
    status["scanning"] = True
    status["last_error"] = None
    t0 = time.time()
    settings = settings or load_settings()
    sources = {}
    try:
        _progress("Leyendo mercado global…")
        try:
            g = data.cg_global(); sources["coingecko_global"] = "OK"
        except Exception as e:
            g = {}; sources["coingecko_global"] = f"ERROR: {e}"
        fng = data.fear_greed(); sources["fear_greed"] = "OK" if fng else "N/D"
        _progress("Leyendo universo de criptomonedas…")
        n = int(settings["universe_size"])
        markets, cg_ok = [], True
        try:
            for page in range(1, (n - 1) // 250 + 2):
                markets += data.cg_markets(min(250, n), page)
                if len(markets) >= n:
                    break
                time.sleep(3)
            markets = markets[:n]
            sources["coingecko_markets"] = f"OK ({len(markets)})"
        except Exception as e:
            # CoinGecko limita mucho las IPs compartidas (Render): usar los pares más negociados del exchange
            cg_ok = False
            markets = data.exchange_markets(settings["quote"], n)
            sources["coingecko_markets"] = (f"CoinGecko no respondió ({e}); universo = {len(markets)} pares más negociados en "
                                            f"{data.source_used.get('markets', '?').capitalize()} (capitalización N/D)")
        cats = category_map() if cg_ok else (storage.read("categories_cache.json", {}) or {}).get("map", {})
        try:
            tradable = data.binance_symbols(settings["quote"])
            src = data.source_used.get("symbols", "binance")
            sources["binance_spot"] = f"OK ({len(tradable)} pares)" if src == "binance" else f"Binance no respondió; usando {src.capitalize()} ({len(tradable)} pares)"
        except Exception as e:
            raise RuntimeError(f"No se pudo leer la lista de pares en Binance, Bybit ni OKX ({e}).")
        funding = data.funding_rates(); sources["binance_funding"] = "OK" if funding else "N/D"
        excl = {s.upper() for s in settings.get("exclude", [])}
        watch = {s.upper() for s in settings.get("watchlist", [])}
        positions = [p for p in (storage.read("positions.json", []) or []) if p.get("status") == "OPEN"]
        must = watch | {p["symbol"] for p in positions}
        universe, skipped = [], []
        seen = set()
        for m in markets:
            sym = m["symbol"].upper()
            if sym in seen: continue
            seen.add(sym)
            reason = None
            if m["symbol"].lower() in STABLES or (m.get("id") or "").startswith(("wrapped", "bridged", "staked")): reason = "stable/envuelto"
            elif sym in excl: reason = "excluido por ti"
            elif sym not in tradable: reason = f"sin par {settings['quote']} en Binance"
            elif sym not in must and (m.get("total_volume") or 0) < settings["min_volume_usd"]: reason = "liquidez insuficiente"
            elif sym not in must and cg_ok and (m.get("market_cap") or 0) < settings["min_mcap_usd"]: reason = "capitalización baja"
            elif not settings.get("include_memecoins", True) and "MEMECOINS" in cats.get(sym, []): reason = "memecoin (desactivadas)"
            if reason and sym not in must:
                skipped.append({"symbol": sym, "reason": reason}); continue
            universe.append(m)
        for sym in must - {m["symbol"].upper() for m in universe}:
            if sym in tradable:
                universe.append({"symbol": sym.lower(), "id": sym.lower(), "name": sym})
        # BTC primero
        _progress("Analizando Bitcoin y régimen de mercado…")
        btc_d1 = data.klines("BTC" + settings["quote"], "1d", 400)
        btc_t = technicals(btc_d1, data.klines("BTC" + settings["quote"], "4h", 200), weekly_from_daily(btc_d1))
        btc_30 = btc_t["chg_30d"]
        cache = {}
        for i, m in enumerate(universe):
            sym = m["symbol"].upper()
            _progress(f"Analizando {sym} ({i + 1}/{len(universe)})…")
            try:
                pair = sym + settings["quote"]
                d1 = btc_d1 if sym == "BTC" else data.klines(pair, "1d", 400)
                if len(d1["c"]) < 60:
                    skipped.append({"symbol": sym, "reason": "historial < 60 días"}); continue
                h4 = data.klines(pair, "4h", 200)
                cache[sym] = (m, d1, h4)
                time.sleep(0.08)
            except Exception as e:
                skipped.append({"symbol": sym, "reason": f"error de datos: {e}"})
        # amplitud
        above = [1 if (lambda t: t["ema50"] and t["price"] > t["ema50"])(technicals(d1)) else 0
                 for s, (m, d1, h4) in cache.items() if s != "BTC"]
        breadth = sum(above) / len(above) * 100 if above else 50
        dom = (g.get("market_cap_percentage") or {}).get("btc")
        prev = storage.read("latest.json", {}) or {}
        dom_prev = (prev.get("market") or {}).get("btc_dominance")
        reg = detect(btc_t, breadth, fng["value"] if fng else None, dom, dom_prev,
                     g.get("market_cap_change_percentage_24h_usd"))
        regime = reg["regime"]
        _progress("Calculando puntuaciones y planes…")
        cats_map = cats
        results = []
        for sym, (m, d1, h4) in cache.items():
            try:
                t30 = (d1["c"][-1] / d1["c"][-31] - 1) * 100 if len(d1["c"]) > 31 else None
                ctx = {"fng": fng["value"] if fng else None,
                       "funding": funding.get(sym + "USDT"),
                       "rel_strength": (t30 - btc_30) if (t30 is not None and btc_30 is not None and sym != "BTC") else None,
                       "catalyst": (settings.get("catalysts") or {}).get(sym)}
                a = analyze(sym, d1, h4, weekly_from_daily(d1), m if m.get("market_cap") else None, ctx, settings, regime)
                a.update({"name": m.get("name", sym), "id": m.get("id"), "image": m.get("image"),
                          "market_cap": m.get("market_cap"), "fdv": m.get("fully_diluted_valuation"),
                          "rank_mcap": m.get("market_cap_rank"), "volume_24h": m.get("total_volume"),
                          "price_cg": m.get("current_price"), "chg_24h": m.get("price_change_percentage_24h"),
                          "categories": [cap_bucket(m.get("market_cap"))] + cats_map.get(sym, []),
                          "funding": ctx["funding"], "catalyst": ctx["catalyst"],
                          "in_watchlist": sym in watch})
                results.append(a)
            except Exception as e:
                skipped.append({"symbol": sym, "reason": f"error de análisis: {e}"})
        # OI solo para los mejores candidatos con futuros (dato de sentimiento)
        results.sort(key=lambda r: r["score"], reverse=True)
        for r in results[:15]:
            if r["symbol"] + "USDT" in funding:
                r["oi_change_24h"] = data.open_interest_change(r["symbol"] + "USDT")
                if r["oi_change_24h"] is not None and abs(r["oi_change_24h"]) > 25:
                    r["signals_exit"].append(f"Open interest inestable ({r['oi_change_24h']:+.0f}% 24h)")
        report = build_report(results, reg, btc_t, g, fng, breadth, settings)
        report.update({
            "scan_id": uuid.uuid4().hex[:10], "at": now().isoformat(), "duration_s": round(time.time() - t0),
            "analyzed": len(results), "skipped": skipped[:400], "sources": sources,
            "assets": results,
        })
        save_candles(cache, report)
        fire_alerts(prev, report, settings)
        update_positions(report, settings)
        log_journal(report)
        evaluate_journal(settings)
        storage.write("latest.json", report)
        hist = storage.read("history.json", {}) or {}
        stamp = report["at"][:16]
        for r in results:
            hist.setdefault(r["symbol"], []).append([stamp, r["score"], r["phase"], r["price"]])
            hist[r["symbol"]] = hist[r["symbol"]][-180:]
        storage.write("history.json", hist)
        storage.append_list("scans.json", [{k: report[k] for k in ("scan_id", "at", "verdict", "analyzed", "duration_s")} | {
            "regime": reg["regime"], "top": [x["symbol"] for x in report["ranking"][:5]]}], keep=500)
        _progress("")
        return report
    except Exception as e:
        status["last_error"] = f"{e}"
        traceback.print_exc()
        alerts.emit(settings, "SYSTEM", "RADAR", f"El escaneo falló: {e}", dedupe_hours=6)
        return None
    finally:
        status["scanning"] = False
        status["progress"] = ""


def save_candles(cache, report):
    keep = {r["symbol"] for r in report["ranking"]} | {"BTC"}
    keep |= {p["symbol"] for p in (storage.read("positions.json", []) or []) if p.get("status") == "OPEN"}
    keep |= {r["symbol"] for r in report["assets"][:40]}
    store = {}
    for sym in keep:
        if sym in cache:
            d1 = cache[sym][1]
            store[sym] = {k: d1[k][-240:] for k in ("t", "o", "h", "l", "c", "v")}
    storage.write("candles.json", store)


def build_report(results, reg, btc_t, g, fng, breadth, settings):
    regime = reg["regime"]
    min_buy = MIN_BUY_SCORE.get(regime, 75)
    avoid_phase = ("SOBREEXTENDIDO", "DISTRIBUCIÓN")
    ok = [r for r in results if not r["action"].startswith(("EVITAR", "RECHAZAR"))]
    ranking = sorted(ok, key=lambda r: (r["score"], r["plan"]["rr"]), reverse=True)[:10]
    for i, r in enumerate(ranking, 1):
        r["rank"] = i
    buyable = [r for r in ok if r["action"] in ("COMPRAR EN ZONA", "ESPERAR RETROCESO", "ESPERAR RUPTURA")]
    def best(key, pool, cond=lambda r: True):
        c = [r for r in pool if cond(r)]
        return max(c, key=key)["symbol"] if c else None
    pool = [r for r in ok if r["score"] >= 60 and r["plan"]["rr"] >= settings["min_risk_reward"]]
    extra = {
        "top3": [r["symbol"] for r in ranking[:3]],
        "best_early_entry": best(lambda r: (r["early_score"], r["score"]), pool, lambda r: r["phase"] in ("ACUMULACIÓN", "RUPTURA INICIAL", "RETROCESO")),
        "best_risk_reward": best(lambda r: r["plan"]["rr"], pool),
        "highest_growth": best(lambda r: r["plan"]["return_tp3_pct"], [r for r in pool if r["score"] >= 65]),
        "short_term_trade": best(lambda r: (r["momentum_score"], r["score"]), pool, lambda r: r["tech"].get("h4_trend_up") and r["phase"] in ("RUPTURA INICIAL", "MOMENTUM")),
        "avoid": [{"symbol": r["symbol"], "why": r["phase"] + (": " + ", ".join(r["signals_exit"][:2]) if r["signals_exit"] else "")}
                  for r in sorted([r for r in results if r["phase"] in avoid_phase or r["exit_risk"] >= 50],
                                  key=lambda r: (r.get("market_cap") or 0), reverse=True)[:8]],
    }
    actionable = [r for r in buyable if r["score"] >= min_buy and r["plan"]["rr"] >= settings["min_risk_reward"]]
    if not actionable:
        verdict = "MANTENER LIQUIDEZ"
        verdict_text = (f"Ningún activo cumple a la vez puntuación ≥ {min_buy} (exigida en régimen {regime}) y R:R ≥ "
                        f"{settings['min_risk_reward']}. No forzar entradas: esperar.")
    elif any(r["action"] == "COMPRAR EN ZONA" for r in actionable):
        verdict = "OPORTUNIDADES ACTIVAS"
        verdict_text = f"{sum(r['action'] == 'COMPRAR EN ZONA' for r in actionable)} activo(s) en zona de entrada con plan completo."
    else:
        verdict = "ESPERAR ENTRADA"
        verdict_text = "Hay candidatos de calidad, pero el precio aún no está en la zona ideal: esperar retroceso o ruptura."
    expo = EXPOSURE.get(regime, 40)
    outlook = (f"Régimen {regime}. " + ". ".join(reg["reasons"]) +
               f". Exposición máxima recomendada en altcoins: {expo}% del capital; el resto en liquidez (stablecoins).")
    market = {
        "btc_price": btc_t["price"], "btc_rsi": btc_t["rsi"], "btc_ema50": btc_t["ema50"], "btc_ema200": btc_t["ema200"],
        "btc_chg_30d": btc_t["chg_30d"], "btc_dominance": (g.get("market_cap_percentage") or {}).get("btc"),
        "eth_dominance": (g.get("market_cap_percentage") or {}).get("eth"),
        "total_mcap": (g.get("total_market_cap") or {}).get("usd"), "total_volume": (g.get("total_volume") or {}).get("usd"),
        "mcap_chg_24h": g.get("market_cap_change_percentage_24h_usd"), "fear_greed": fng, "breadth": breadth,
        "regime": regime, "alt_bias": reg["alt_bias"], "max_alt_exposure": expo, "min_buy_score": min_buy,
    }
    return {"verdict": verdict, "verdict_text": verdict_text, "market": market, "outlook": outlook,
            "ranking": ranking, "extra": extra}


def fire_alerts(prev, rep, settings):
    prev_assets = {r["symbol"]: r for r in (prev.get("assets") or [])}
    prev_top = {r["symbol"] for r in (prev.get("ranking") or [])}
    watch = {s.upper() for s in settings.get("watchlist", [])}
    pos = {p["symbol"] for p in (storage.read("positions.json", []) or []) if p.get("status") == "OPEN"}
    pm = prev.get("market") or {}
    if pm.get("regime") and pm["regime"] != rep["market"]["regime"]:
        alerts.emit(settings, "MARKET REGIME CHANGE", "MERCADO", f"{pm['regime']} → {rep['market']['regime']}. {rep['verdict']}.")
    top = {r["symbol"] for r in rep["ranking"]}
    for r in rep["assets"]:
        s, p = r["symbol"], prev_assets.get(r["symbol"], {})
        relevant = s in top or s in watch or s in pos or s in prev_top
        pl = r["plan"]
        lv = f"Zona {fmt(pl['entry_ideal'])}–{fmt(pl['entry_zone_high'])} · SL {fmt(pl['stop'])} · TP1 {fmt(pl['tp1'])} · TP2 {fmt(pl['tp2'])} · Score {r['score']:.0f}"
        if r["phase"] in ("ACUMULACIÓN", "RUPTURA INICIAL") and r["score"] >= 70 and r["early_score"] >= 45 \
                and not r["action"].startswith(("EVITAR", "RECHAZAR", "VIGILAR")) and (p.get("score", 0) < 70 or p.get("phase") != r["phase"]):
            alerts.emit(settings, "NEW EARLY ENTRY", s, f"{r['phase']} · {lv}")
        if r["phase"] == "RUPTURA INICIAL" and p.get("phase") and p.get("phase") != "RUPTURA INICIAL" and r["score"] >= 65:
            alerts.emit(settings, "BREAKOUT CONFIRMATION", s, f"Ruptura con volumen x{r['tech']['vol_ratio']:.1f}. {lv}")
        if r["action"] == "COMPRAR EN ZONA" and p.get("action") != "COMPRAR EN ZONA" and relevant:
            alerts.emit(settings, "ENTRY ZONE REACHED", s, lv)
        if r["phase"] == "DISTRIBUCIÓN" and p.get("phase") != "DISTRIBUCIÓN" and relevant:
            alerts.emit(settings, "DISTRIBUTION DETECTED", s, ", ".join(r["signals_exit"][:3]) or "Señales de distribución")
        if r["exit_risk"] >= 50 and p.get("exit_risk", 0) < 50 and (s in pos or s in prev_top or s in watch):
            alerts.emit(settings, "BEARISH REVERSAL", s, ", ".join(r["signals_exit"][:3]))


def fmt(x):
    if x is None: return "N/D"
    return f"${x:,.2f}" if x >= 1 else f"${x:.6g}"


# ------------------------------------------------------------- posiciones
def update_positions(rep, settings, prices=None):
    positions = storage.read("positions.json", []) or []
    amap = {r["symbol"]: r for r in (rep.get("assets") or [])} if rep else {}
    changed = False
    for p in positions:
        if p.get("status") != "OPEN":
            continue
        s = p["symbol"]
        price = (prices or {}).get(s) or (amap.get(s) or {}).get("price")
        if not price:
            continue
        p["last_price"] = price
        p["pnl_pct"] = (price / p["entry"] - 1) * 100
        p["updated"] = now().isoformat()
        hits = p.setdefault("hits", [])
        for tp in ("tp1", "tp2", "tp3"):
            if p.get(tp) and price >= p[tp] and tp not in hits:
                hits.append(tp)
                alerts.emit(settings, "TAKE PROFIT REACHED", s, f"{tp.upper()} {fmt(p[tp])} alcanzado ({p['pnl_pct']:+.1f}%). "
                            + ("Sugerido: vender ~40% y subir stop a la entrada." if tp == "tp1" else
                               "Sugerido: vender ~35% más y subir stop a TP1." if tp == "tp2" else "Objetivo final alcanzado."), dedupe_hours=72)
        if p.get("stop"):
            if price <= p["stop"] and "stop" not in hits:
                hits.append("stop")
                alerts.emit(settings, "STOP LOSS HIT", s, f"Precio {fmt(price)} ≤ stop {fmt(p['stop'])}. Plan: salir.", dedupe_hours=72)
            elif price <= p["stop"] * 1.03:
                alerts.emit(settings, "STOP LOSS WARNING", s, f"Precio {fmt(price)} a {((price / p['stop']) - 1) * 100:.1f}% del stop {fmt(p['stop'])}.", dedupe_hours=8)
        a = amap.get(s)
        if a:
            p["exit_signals"] = a["signals_exit"]
            p["exit_risk"] = a["exit_risk"]
            p["phase"] = a["phase"]
        changed = True
    if changed:
        storage.write("positions.json", positions)


# ------------------------------------------------------------- diario de señales (rendimiento real del sistema)
def log_journal(rep):
    j = storage.read("journal.json", []) or []
    open_syms = {x["symbol"] for x in j if x["status"] == "OPEN"}
    for r in rep["assets"]:
        if r["action"] == "COMPRAR EN ZONA" and r["symbol"] not in open_syms:
            pl = r["plan"]
            j.append({"id": uuid.uuid4().hex[:8], "symbol": r["symbol"], "at": rep["at"], "score": r["score"],
                      "phase": r["phase"], "entry": r["price"], "stop": pl["stop"], "tp1": pl["tp1"], "tp2": pl["tp2"],
                      "tp3": pl["tp3"], "status": "OPEN", "hits": [], "r_multiple": None, "regime": rep["market"]["regime"]})
    storage.write("journal.json", j[-1000:])


def evaluate_journal(settings):
    """Recorre velas 1H desde cada señal: 40% en TP1 (stop a entrada), 35% en TP2, 25% en TP3."""
    j = storage.read("journal.json", []) or []
    changed = False
    for x in j:
        if x["status"] != "OPEN":
            continue
        try:
            start = int(dt.datetime.fromisoformat(x["at"]).timestamp() * 1000)
            rows = data.kline_rows(x["symbol"] + settings["quote"], "1h", 1000, start)
        except Exception:
            continue
        R = x["entry"] - x["stop"]
        if R <= 0:
            x["status"] = "INVALID"; continue
        stop, realized, left, hits = x["stop"], 0.0, 1.0, []
        closed = False
        for row in rows:
            hi, lo = float(row[2]), float(row[3])
            if lo <= stop:
                realized += left * (stop - x["entry"]) / R; left = 0; hits.append("stop"); closed = True; break
            for tp, w in (("tp1", 0.40), ("tp2", 0.35), ("tp3", 0.25)):
                if tp not in hits and hi >= x[tp]:
                    realized += w * (x[tp] - x["entry"]) / R; left -= w; hits.append(tp)
                    if tp == "tp1": stop = x["entry"]
                    if tp == "tp2": stop = x["tp1"]
            if left <= 1e-9:
                closed = True; break
        last = float(rows[-1][4]) if rows else x["entry"]
        age_days = (now() - dt.datetime.fromisoformat(x["at"])).days
        x["hits"] = hits
        x["last_price"] = last
        if closed or age_days >= 45:
            if left > 0:
                realized += left * (last - x["entry"]) / R
            x["status"] = "CLOSED"
            x["closed_at"] = now().isoformat()
        x["r_multiple"] = round(realized + (left * (last - x["entry"]) / R if x["status"] == "OPEN" else 0), 2)
        changed = True
        time.sleep(0.1)
    if changed:
        storage.write("journal.json", j)


# ------------------------------------------------------------- vigilancia rápida de precio (cada 15 min)
def price_watch(settings=None):
    settings = settings or load_settings()
    try:
        prices = data.ticker_prices(settings["quote"])
    except Exception as e:
        status["last_error"] = f"Vigilancia de precio: {e}"
        return
    status["last_watch"] = now().isoformat()
    update_positions({}, settings, prices)
    rep = storage.read("latest.json", {}) or {}
    for r in rep.get("ranking", []):
        s = r["symbol"]
        p = prices.get(s)
        if not p or r["action"] not in ("ESPERAR RETROCESO", "COMPRAR EN ZONA"):
            continue
        pl = r["plan"]
        if pl["stop"] < p <= pl["entry_zone_high"]:
            alerts.emit(settings, "ENTRY ZONE REACHED", s,
                        f"Precio {fmt(p)} dentro de la zona {fmt(pl['entry_ideal'])}–{fmt(pl['entry_zone_high'])} · SL {fmt(pl['stop'])} · TP1 {fmt(pl['tp1'])}. Revisa el panel antes de actuar.")
    storage.write("prices.json", {"at": status["last_watch"], "prices": {k: prices[k] for k in list(prices)[:3000]}})
