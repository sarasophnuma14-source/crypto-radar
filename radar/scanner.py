"""Orquesta un escaneo completo con el motor cuantitativo (radar/quant): informe, ranking temprano y alertas."""
from __future__ import annotations
import datetime as dt
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from . import data, storage, alerts, notify
from .config import CATEGORIES, STABLES, load_settings
from .quant import engine as qengine, features as qfeatures, regime as qregime

status = {"scanning": False, "progress": "", "last_error": None, "last_watch": None, "fail_streak": 0}
FETCH_WORKERS = 4      # descargas simultáneas (respeta los límites de las APIs con pausa por host)
BOOK_TOP = 25          # libros de órdenes en vivo para los mejores candidatos
BUY_ACTIONS = ("COMPRAR EN ZONA", "ESPERAR RETROCESO", "ESPERAR RUPTURA")
ALERT_AFTER_FAILS = 3   # avisar por Telegram solo si falla 3 veces seguidas (~1 h), no por un bloqueo pasajero


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
        markets, cg_ok, cg_err = [], True, None
        try:
            for page in range(1, (n - 1) // 250 + 2):
                markets += data.cg_markets(min(250, n), page)
                if len(markets) >= n:
                    break
                time.sleep(3)
            markets = markets[:n]
            sources["coingecko_markets"] = f"OK ({len(markets)})"
            storage.write("markets_cache.json", {"at": time.time(), "markets": markets})
        except Exception as e:
            # CoinGecko limita mucho las IPs compartidas (Render): último universo bueno (<24 h) o pares del exchange
            cg_err = e
            cached = storage.read("markets_cache.json", {}) or {}
            if cached.get("markets") and time.time() - cached.get("at", 0) < 86400:
                markets = cached["markets"]
                sources["coingecko_markets"] = f"CoinGecko no respondió ({e}); usando el universo guardado hace {int((time.time() - cached['at']) / 60)} min"
                cg_ok = True
            else:
                cg_ok = False
                markets = data.exchange_markets(settings["quote"], n)
        if not cg_ok:
            sources["coingecko_markets"] = (f"CoinGecko no respondió ({cg_err}); universo = {len(markets)} pares más negociados en "
                                            f"{data.source_used.get('markets', '?').capitalize()} (capitalización N/D)")
        cats = category_map() if cg_ok else (storage.read("categories_cache.json", {}) or {}).get("map", {})
        try:
            tradable = data.binance_symbols(settings["quote"])
            src = data.source_used.get("symbols", "binance")
            sources["binance_spot"] = f"OK ({len(tradable)} pares)" if src == "binance" else f"Binance no respondió; usando {src.capitalize()} ({len(tradable)} pares)"
            storage.write("pairs_cache.json", {"at": time.time(), "pairs": sorted(tradable)})
        except Exception as e:
            pc = storage.read("pairs_cache.json", {}) or {}
            if pc.get("pairs") and time.time() - pc.get("at", 0) < 86400:
                tradable = set(pc["pairs"])
                sources["binance_spot"] = f"Exchanges limitados ({e}); usando la lista de pares guardada"
            else:
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
        # ---------- datos diarios (solo velas cerradas), en paralelo y con límite de concurrencia
        _progress("Descargando velas diarias…")
        cache = {}

        def fetch(m):
            sym = m["symbol"].upper()
            try:
                d1 = data.klines(sym + settings["quote"], "1d", 400, closed=True)
                return sym, m, d1, None
            except Exception as e:
                return sym, m, None, e
        btc_m = next((m for m in universe if m["symbol"].upper() == "BTC"), {"symbol": "btc", "id": "bitcoin", "name": "Bitcoin"})
        sym, m, btc_d1, err = fetch(btc_m)
        if err or not btc_d1 or len(btc_d1["c"]) < 210:
            raise RuntimeError(f"No se pudieron leer las velas de BTC ({err or 'historial insuficiente'}).")
        cache["BTC"] = (btc_m, btc_d1)
        rest = [m for m in universe if m["symbol"].upper() != "BTC"]
        done = 0
        with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as ex:
            for sym, m, d1, err in ex.map(fetch, rest):
                done += 1
                if done % 10 == 0:
                    _progress(f"Velas diarias {done}/{len(rest)}…")
                if err:
                    skipped.append({"symbol": sym, "reason": f"error de datos: {err}"}); continue
                if len(d1["c"]) < 60:
                    skipped.append({"symbol": sym, "reason": "historial < 60 días"}); continue
                cache[sym] = (m, d1)
        sources["klines"] = f"{data.source_used.get('klines', 'binance').capitalize()} ({len(cache)} activos)"

        # ---------- indicadores, amplitud y régimen (motor cuantitativo común con el backtest)
        _progress("Calculando régimen de mercado…")
        feats = {s: qfeatures.compute(d1) for s, (m, d1) in cache.items()}
        bf = feats["BTC"]; bi = len(bf.c) - 1
        above, rs = [], []
        b30 = qfeatures.chg(bf, bi, 30)
        for s, f in feats.items():
            if s == "BTC":
                continue
            i = len(f.c) - 1
            e50 = qfeatures.val(f.ema50, i)
            if e50 and i >= 50:
                above.append(f.c[i] > e50)
            c30 = qfeatures.chg(f, i, 30)
            if c30 is not None and b30 is not None:
                rs.append(c30 - b30)
        breadth = sum(above) / len(above) * 100 if above else None
        alt_rs = sorted(rs)[len(rs) // 2] if rs else None
        dom = (g.get("market_cap_percentage") or {}).get("btc")
        prev = storage.read("latest.json", {}) or {}
        dom_prev = (prev.get("market") or {}).get("btc_dominance")
        ef = feats.get("ETH")
        reg = qregime.detect(bf, bi, breadth, ef, (len(ef.c) - 1) if ef else None, alt_rs, dom, dom_prev)
        regime = reg["regime"]

        # ---------- análisis por activo
        _progress("Calculando puntuaciones y planes…")
        now_ms = int(time.time() * 1000)
        pos_map = {}
        for p in positions:
            pos_map.setdefault(p["symbol"], p)
        results = []
        for sym, (m, d1) in cache.items():
            try:
                f = feats[sym]; i = len(f.c) - 1
                pos = pos_map.get(sym)
                a = qengine.analyze(sym, f, i, bf, bi, regime=reg, settings=settings, market=m,
                                    position={"entry": pos["entry"], "stop": pos.get("stop") or pos["entry"] * 0.9,
                                              "highest_close": pos.get("highest_close")} if pos else None,
                                    now_ms=now_ms)
                a.update(_asset_meta(m, sym, cats, watch))
                results.append(a)
            except Exception as e:
                skipped.append({"symbol": sym, "reason": f"error de análisis: {e}"})

        # ---------- libro de órdenes en vivo para los mejores candidatos (spread, profundidad, manipulación)
        _progress("Leyendo libros de órdenes de los mejores candidatos…")
        books_prev = storage.read("books.json", {}) or {}
        books = {}
        top = sorted(results, key=lambda r: -r["score"])[:BOOK_TOP]
        for r in top:
            sym = r["symbol"]
            bk = data.order_book(sym + settings["quote"])
            if not bk:
                continue
            books[sym] = bk
            f = feats[sym]; i = len(f.c) - 1; m = cache[sym][0]
            pos = pos_map.get(sym)
            a = qengine.analyze(sym, f, i, bf, bi, regime=reg, settings=settings, market=m, book=bk,
                                book_prev=books_prev.get(sym),
                                position={"entry": pos["entry"], "stop": pos.get("stop") or pos["entry"] * 0.9,
                                          "highest_close": pos.get("highest_close")} if pos else None,
                                now_ms=now_ms)
            a.update(_asset_meta(m, sym, cats, watch)); a["book"] = bk
            results[results.index(r)] = a
        if books:
            storage.write("books.json", {**books_prev, **books})
        sources["order_books"] = f"Binance ({len(books)} libros)" if books else "N/D"
        for r in results:
            r["rank_score"] = rank_score(r)
        results.sort(key=lambda r: -r["rank_score"])
        report = build_report(results, reg, g, fng, settings)
        report.update({
            "engine": "quant-2.0", "scan_id": uuid.uuid4().hex[:10], "at": now().isoformat(),
            "duration_s": round(time.time() - t0), "analyzed": len(results), "skipped": skipped[:400],
            "sources": sources, "assets": results,
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
            "regime": regime, "top": [x["symbol"] for x in report["ranking"][:5]]}], keep=500)
        notify.maybe_summaries(report, settings)
        _progress("")
        status["fail_streak"] = 0
        return report
    except Exception as e:
        status["last_error"] = f"{e}"
        status["fail_streak"] += 1
        traceback.print_exc()
        if status["fail_streak"] >= ALERT_AFTER_FAILS:
            alerts.emit(settings, "SYSTEM", "RADAR",
                        f"El escaneo falló {status['fail_streak']} veces seguidas: {str(e).rstrip('.')}. Se sigue reintentando cada 20 min.",
                        dedupe_hours=6)
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


def _asset_meta(m, sym, cats, watch):
    return {"name": m.get("name", sym), "id": m.get("id"), "image": m.get("image"),
            "market_cap": m.get("market_cap"), "fdv": m.get("fully_diluted_valuation"),
            "rank_mcap": m.get("market_cap_rank"), "volume_24h": m.get("total_volume"),
            "cap_bucket": cap_bucket(m.get("market_cap")),
            "categories": [cap_bucket(m.get("market_cap"))] + cats.get(sym, []), "in_watchlist": sym in watch}


PHASE_PRIORITY = {"PRE-EXPLOSION": 10, "ACCUMULATION": 8, "BREAKOUT": 4, "MOMENTUM": 0}


def rank_score(r):
    """Prioriza oportunidades TEMPRANAS: fase temprana, poco recorrido previo, bajo riesgo de manipulación y buen R:R.
    Las que ya subieron mucho (sobreextendidas) o muestran distribución quedan fuera del ranking."""
    if r["phase"] not in PHASE_PRIORITY or r["action"] in ("DESCARTAR", "EVITAR", "NO PERSEGUIR"):
        return -1.0
    s = r["score"] + PHASE_PRIORITY[r["phase"]]
    c30 = r["metrics"].get("chg_30d") or 0
    if c30 > 40:
        s -= min(20, (c30 - 40) / 3)          # ya recorrió mucho: penalizar
    s -= r["manipulation"]["risk"] * 0.15
    q = (r.get("quality") or {}).get("score")
    if q is not None and q < 80:
        s -= (80 - q) * 0.2
    s += min(5, max(0, (r["plan"]["rr"] - 2.5) * 2))
    return round(s, 1)


def _row(r):
    """Fila compacta del ranking con los campos que se muestran en el escáner."""
    pl, mt = r["plan"], r["metrics"]
    return {"symbol": r["symbol"], "name": r.get("name"), "price": r["price"], "score": r["score"],
            "rank_score": r.get("rank_score"), "phase": r["phase"], "phase_label": r["phase_label"],
            "action": r["action"], "action_reason": r["action_reason"], "rel_volume": mt.get("rel_volume"),
            "chg_24h": mt.get("chg_24h"), "chg_7d": mt.get("chg_7d"), "chg_30d": mt.get("chg_30d"),
            "rs_btc_30d": mt.get("rs_btc_30d"), "liquidity": mt.get("liquidity"),
            "manipulation_risk": r["manipulation"]["risk"], "manipulation_level": r["manipulation"]["level"],
            "entry_low": pl["entry_low"], "entry_high": pl["entry_high"], "trigger": pl["trigger_breakout"],
            "stop": pl["stop"], "tp1": pl["tp1"], "tp2": pl["tp2"], "tp3": pl["tp3"], "rr": pl["rr"],
            "position_usd": pl["position_usd"], "market_cap": r.get("market_cap"), "cap_bucket": r.get("cap_bucket"),
            "quality": (r.get("quality") or {}).get("score")}


def build_report(results, reg, g, fng, settings):
    regime = reg["regime"]
    pol = reg["policy"]
    ranked = [r for r in results if r["rank_score"] >= 0]
    ranking = [dict(_row(r), rank=k) for k, r in enumerate(ranked[:20], 1)]
    buy = [r for r in ranked if r["action"] in BUY_ACTIONS]
    early = [_row(r) for r in ranked if r["phase"] in ("PRE-EXPLOSION", "ACCUMULATION")][:15]
    breakouts = [_row(r) for r in ranked if r["phase"] == "BREAKOUT"][:15]
    avoid = [{"symbol": r["symbol"], "phase": r["phase_label"], "why": r["action_reason"],
              "manipulation_risk": r["manipulation"]["risk"]}
             for r in sorted(results, key=lambda r: -(r.get("market_cap") or 0))
             if r["phase"] in ("OVEREXTENDED", "DISTRIBUTION") or r["manipulation"]["risk"] >= qengine.MANIP_BLOCK][:12]
    if not buy:
        verdict, vtext = "MANTENER LIQUIDEZ", (f"Ningún activo cumple las condiciones del régimen {reg['label'].lower()} "
                                               f"(puntaje ≥ {pol['min_score']}, R:R ≥ {settings['min_risk_reward']}). No forzar entradas.")
    elif any(r["action"] == "COMPRAR EN ZONA" for r in buy):
        verdict = "OPORTUNIDADES ACTIVAS"
        vtext = f"{sum(r['action'] == 'COMPRAR EN ZONA' for r in buy)} activo(s) en zona de entrada con plan completo."
    else:
        verdict, vtext = "ESPERAR ENTRADA", "Hay candidatos, pero el precio aún no está en la zona: esperar retroceso o ruptura."
    rm = reg["metrics"]
    market = {
        "btc_price": rm["btc_price"], "btc_ema50": rm["btc_ema50"], "btc_ema200": rm["btc_ema200"],
        "btc_chg_7d": rm["btc_chg_7d"], "btc_chg_30d": rm["btc_chg_30d"], "btc_vol_annual_pct": rm["btc_vol_annual_pct"],
        "btc_drawdown_90d_pct": rm["btc_drawdown_90d_pct"], "btc_dominance": (g.get("market_cap_percentage") or {}).get("btc"),
        "eth_dominance": (g.get("market_cap_percentage") or {}).get("eth"),
        "total_mcap": (g.get("total_market_cap") or {}).get("usd"), "total_volume": (g.get("total_volume") or {}).get("usd"),
        "mcap_chg_24h": g.get("market_cap_change_percentage_24h_usd"), "fear_greed": fng, "breadth": rm["breadth"],
        "alt_rs_30d": rm["alt_rs_30d"], "regime": regime, "regime_label": reg["label"], "regime_reasons": reg["reasons"],
        "policy": {k: (list(v) if isinstance(v, tuple) else v) for k, v in pol.items()},
        "max_alt_exposure": pol["max_alt_exposure"], "min_buy_score": pol["min_score"],
    }
    counts = {}
    for r in results:
        counts[r["phase"]] = counts.get(r["phase"], 0) + 1
    return {"verdict": verdict, "verdict_text": vtext, "market": market, "phase_counts": counts,
            "outlook": f"Régimen {reg['label']}. " + ". ".join(reg["reasons"]) +
                       f". Exposición máxima recomendada en altcoins: {pol['max_alt_exposure']}% del capital.",
            "ranking": ranking, "early": early, "breakouts": breakouts, "avoid": avoid}


def fire_alerts(prev, rep, settings):
    """Alertas por TRANSICIÓN (no se repiten mientras el estado no cambie) y con deduplicación temporal."""
    prev_assets = {r["symbol"]: r for r in (prev.get("assets") or [])}
    pm = prev.get("market") or {}
    if pm.get("regime") and pm["regime"] != rep["market"]["regime"]:
        alerts.emit(settings, "MARKET REGIME CHANGE", "MERCADO", notify.regime_text(pm, rep["market"], rep["verdict"]),
                    dedupe_hours=6)
    pos = {p["symbol"] for p in (storage.read("positions.json", []) or []) if p.get("status") == "OPEN"}
    watch = {s.upper() for s in settings.get("watchlist", [])}
    ranked = {r["symbol"] for r in rep["ranking"]}
    for r in rep["assets"]:
        s, p = r["symbol"], prev_assets.get(r["symbol"]) or {}
        buyable = r["action"] in BUY_ACTIONS
        if r["phase"] == "PRE-EXPLOSION" and buyable and p.get("phase") != "PRE-EXPLOSION":
            alerts.emit(settings, "PRE-EXPLOSION", s, notify.signal_text(r), extra=_row(r), dedupe_hours=48)
        if r["phase"] == "BREAKOUT" and buyable and p.get("phase") != "BREAKOUT":
            alerts.emit(settings, "BREAKOUT CONFIRMATION", s, notify.signal_text(r), extra=_row(r), dedupe_hours=48)
        if r["action"] == "COMPRAR EN ZONA" and p.get("action") != "COMPRAR EN ZONA" and (s in ranked or s in watch):
            alerts.emit(settings, "ENTRY ZONE REACHED", s, notify.signal_text(r), extra=_row(r), dedupe_hours=24)
        relevant = s in pos or s in watch or s in ranked
        hi_risk = r["manipulation"]["risk"] >= qengine.MANIP_BLOCK
        if relevant and hi_risk and (p.get("manipulation") or {}).get("risk", 0) < qengine.MANIP_BLOCK:
            alerts.emit(settings, "RISK", s, notify.risk_text(r), dedupe_hours=24)
        if relevant and r["phase"] == "DISTRIBUTION" and p.get("phase") != "DISTRIBUTION":
            alerts.emit(settings, "DISTRIBUTION DETECTED", s, notify.risk_text(r), dedupe_hours=24)


def fmt(x):
    if x is None: return "N/D"
    return f"${x:,.2f}" if x >= 1 else f"${x:.6g}"


# ------------------------------------------------------------- posiciones
def update_positions(rep, settings, prices=None):
    """Precio, P&L, objetivos/stop y la decisión de Exit Intelligence (calculada en el escaneo con velas cerradas)."""
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
        p["highest_close"] = max(p.get("highest_close") or p["entry"], (amap.get(s) or {}).get("price") or 0)
        p["updated"] = now().isoformat()
        hits = p.setdefault("hits", [])
        for tp in ("tp1", "tp2", "tp3"):
            if p.get(tp) and price >= p[tp] and tp not in hits:
                hits.append(tp)
                alerts.emit(settings, "TAKE PROFIT REACHED", s, notify.tp_text(p, tp, price), dedupe_hours=72)
        if p.get("stop"):
            if price <= p["stop"] and "stop" not in hits:
                hits.append("stop")
                alerts.emit(settings, "STOP LOSS HIT", s, f"Precio {fmt(price)} ≤ stop {fmt(p['stop'])}. Plan: salir.", dedupe_hours=72)
            elif price <= p["stop"] * 1.03:
                alerts.emit(settings, "STOP LOSS WARNING", s, f"Precio {fmt(price)} a {((price / p['stop']) - 1) * 100:.1f}% del stop {fmt(p['stop'])}.", dedupe_hours=8)
        a = amap.get(s)
        if a and a.get("exit"):
            ex = a["exit"]
            prev_dec = (p.get("exit") or {}).get("decision")
            p["exit"] = ex
            p["phase"] = a["phase"]
            p["suggested_stop"] = ex["suggested_stop"]
            if ex["decision"] != "MANTENER" and ex["decision"] != prev_dec:
                alerts.emit(settings, "EXIT", s, notify.exit_text(p, a), extra={"decision": ex["decision"]}, dedupe_hours=24)
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
        if r["stop"] < p <= r["entry_high"]:
            alerts.emit(settings, "ENTRY ZONE REACHED", s,
                        f"Precio {fmt(p)} dentro de la zona {fmt(r['entry_low'])}–{fmt(r['entry_high'])} · Stop {fmt(r['stop'])} · "
                        f"TP1 {fmt(r['tp1'])} · TP2 {fmt(r['tp2'])}. Puntaje {r['score']:.0f}. Revisa el panel antes de actuar.",
                        extra=r, dedupe_hours=24)
    storage.write("prices.json", {"at": status["last_watch"], "prices": {k: prices[k] for k in list(prices)[:3000]}})
