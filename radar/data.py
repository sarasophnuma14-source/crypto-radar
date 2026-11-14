"""Fuentes de datos públicas y gratuitas (sin claves):
- CoinGecko: universo, capitalización, FDV, supply, categorías, dominancia BTC.
- Binance spot: velas OHLCV (1D, 4H, 1W). Primero data-api.binance.vision (espejo público de datos de mercado),
  luego api.binance.com. Si Binance bloquea la IP (HTTP 418/429, típico en servidores compartidos como Render),
  se respeta el tiempo de espera que pide y se usan Bybit u OKX como respaldo con los mismos pares USDT.
- Binance futuros: funding rate y open interest (solo como dato de sentimiento, la app nunca opera con apalancamiento).
- alternative.me: índice Fear & Greed.
Si una fuente falla, el dato queda como N/D. Nunca se inventan valores.
"""
from __future__ import annotations
import json
import shutil
import ssl
import subprocess
import time
import urllib.parse
import urllib.request

UA = "CryptoRadar/1.0"
BINANCE_BASES = ["https://data-api.binance.vision", "https://api.binance.com", "https://api-gcp.binance.com"]
_binance_base = None
_blocked = {}          # host -> timestamp hasta el que no se le debe preguntar (baneo / límite de peso)
_last_call = {}        # host -> último request (para espaciar peticiones)
MIN_GAP = 0.15         # segundos mínimos entre peticiones al mismo host


class RateLimited(Exception):
    def __init__(self, host, code, wait):
        super().__init__(f"{host} limitó las peticiones (HTTP {code}); se reintenta en {int(wait)} s")
        self.host, self.code, self.wait = host, code, wait


def _host(url):
    return urllib.parse.urlsplit(url).netloc
_ssl_ctx = None


def _context():
    global _ssl_ctx
    if _ssl_ctx is None:
        try:
            import certifi  # type: ignore
            _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            _ssl_ctx = ssl.create_default_context()
    return _ssl_ctx


def get_json(url, params=None, timeout=20, retries=2):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    host = _host(url)
    until = _blocked.get(host, 0)
    if until > time.time():
        raise RateLimited(host, "espera", until - time.time())
    last_err = None
    for attempt in range(retries + 1):
        gap = MIN_GAP - (time.time() - _last_call.get(host, 0))
        if gap > 0:
            time.sleep(gap)
        _last_call[host] = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=_context()) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 418 or (e.code == 429 and "binance" in host):
                # Baneo/límite de Binance: NO insistir (insistir alarga el baneo). Respetar Retry-After.
                try:
                    wait = float(e.headers.get("Retry-After") or 0)
                except (TypeError, ValueError):
                    wait = 0
                wait = wait or (600 if e.code == 418 else 60)
                _blocked[host] = time.time() + wait
                raise RateLimited(host, e.code, wait)
            if e.code == 429:
                # CoinGecko u otra API limitada: esperar lo que pide (máx. 60 s) y reintentar una vez;
                # si sigue, poner el host en espera 10 min para no bloquear el escaneo entero
                try:
                    wait = min(float(e.headers.get("Retry-After") or 20), 60)
                except (TypeError, ValueError):
                    wait = 20
                if attempt == 0:
                    time.sleep(wait)
                    continue
                _blocked[host] = time.time() + 600
                raise RateLimited(host, 429, 600)
            if e.code in (451, 403, 404, 400):
                raise
        except (ssl.SSLError, urllib.error.URLError) as e:
            last_err = e
            # En macOS el Python de python.org a veces no tiene certificados: usamos curl del sistema.
            if shutil.which("curl") and ("CERTIFICATE" in str(e).upper() or isinstance(e, ssl.SSLError)):
                out = subprocess.run(["curl", "-sS", "-m", str(timeout), "-A", UA, url], capture_output=True, text=True)
                if out.returncode == 0 and out.stdout.strip():
                    return json.loads(out.stdout)
        except Exception as e:  # noqa
            last_err = e
        time.sleep(2 * (attempt + 1))
    raise last_err or RuntimeError("fetch failed: " + url)


# ---------------------------------------------------------------- CoinGecko
CG = "https://api.coingecko.com/api/v3"


def cg_markets(per_page=250, page=1, category=None):
    p = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": per_page, "page": page,
         "price_change_percentage": "24h,7d,30d"}
    if category:
        p["category"] = category
    return get_json(CG + "/coins/markets", p)


def cg_global():
    return get_json(CG + "/global").get("data", {})


# ---------------------------------------------------------------- Binance
def _binance(path, params=None):
    """Prueba los hosts de Binance empezando por el último que funcionó; salta los que están en espera."""
    global _binance_base
    bases = ([_binance_base] if _binance_base else []) + [b for b in BINANCE_BASES if b != _binance_base]
    err = None
    for b in bases:
        try:
            r = get_json(b + path, params, retries=1)
            _binance_base = b
            return r
        except Exception as e:
            err = e
    _binance_base = None
    raise err or RuntimeError("Binance no disponible")


# ---------------------------------------------------------------- respaldo: Bybit y OKX (spot, públicos)
BYBIT = "https://api.bybit.com"
OKX = "https://www.okx.com"
_BYBIT_IV = {"1h": "60", "4h": "240", "1d": "D", "1w": "W"}
_OKX_IV = {"1h": "1H", "4h": "4H", "1d": "1Dutc", "1w": "1Wutc"}
source_used = {"klines": "binance"}


def _split(symbol, quotes=("USDT", "USDC", "FDUSD", "BTC", "ETH")):
    for q in quotes:
        if symbol.endswith(q):
            return symbol[: -len(q)], q
    return symbol, ""


def _bybit_klines(symbol, interval, limit, start=None):
    p = {"category": "spot", "symbol": symbol, "interval": _BYBIT_IV[interval], "limit": min(limit, 1000)}
    if start:
        p["start"] = start
    r = get_json(BYBIT + "/v5/market/kline", p, retries=1)
    if r.get("retCode") != 0:
        raise RuntimeError(f"Bybit: {r.get('retMsg')}")
    rows = sorted(r["result"]["list"], key=lambda x: int(x[0]))   # Bybit entrega de más nuevo a más viejo
    # [start, open, high, low, close, volume, turnover] -> mismo orden que Binance; turnover = volumen en USDT
    return [[int(x[0]), x[1], x[2], x[3], x[4], x[5], 0, x[6]] for x in rows]


def _okx_klines(symbol, interval, limit):
    base, q = _split(symbol)
    r = get_json(OKX + "/api/v5/market/candles", {"instId": f"{base}-{q}", "bar": _OKX_IV[interval], "limit": min(limit, 300)}, retries=1)
    if r.get("code") != "0":
        raise RuntimeError(f"OKX: {r.get('msg')}")
    rows = sorted(r["data"], key=lambda x: int(x[0]))
    # [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]; la vela sin cerrar se descarta con klines(closed=True)
    return [[int(x[0]), x[1], x[2], x[3], x[4], x[5], 0, x[7]] for x in rows]


def kline_rows(symbol, interval="1d", limit=365, start=None):
    """Filas tipo Binance desde la primera fuente que responda: Binance → Bybit → OKX."""
    errs = []
    p = {"symbol": symbol, "interval": interval, "limit": limit}
    if start:
        p["startTime"] = start
    try:
        rows = _binance("/api/v3/klines", p); source_used["klines"] = "binance"; return rows
    except Exception as e:
        errs.append(f"Binance: {e}")
    try:
        rows = _bybit_klines(symbol, interval, limit, start); source_used["klines"] = "bybit"; return rows
    except Exception as e:
        errs.append(f"Bybit: {e}")
    if not start:
        try:
            rows = _okx_klines(symbol, interval, limit); source_used["klines"] = "okx"; return rows
        except Exception as e:
            errs.append(f"OKX: {e}")
    raise RuntimeError(" | ".join(errs))


def ticker_prices(quote="USDT"):
    """{BASE: último precio} desde Binance, o Bybit/OKX si Binance no responde."""
    try:
        rows = _binance("/api/v3/ticker/price")
        return {r["symbol"][:-len(quote)]: float(r["price"]) for r in rows if r["symbol"].endswith(quote)}
    except Exception:
        pass
    try:
        r = get_json(BYBIT + "/v5/market/tickers", {"category": "spot"}, retries=1)
        return {x["symbol"][:-len(quote)]: float(x["lastPrice"]) for x in r["result"]["list"] if x["symbol"].endswith(quote)}
    except Exception:
        pass
    r = get_json(OKX + "/api/v5/market/tickers", {"instType": "SPOT"}, retries=1)
    return {x["instId"].split("-")[0]: float(x["last"]) for x in r["data"] if x["instId"].endswith("-" + quote)}


STABLE_BASES = {"USDT", "USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "AEUR", "EURI", "USDE", "PAXG",
                "WBTC", "WBETH", "BFUSD", "USD1", "XUSD", "RLUSD", "BNSOL", "XAUT", "GBP", "TRY", "BRL", "USDS", "PYUSD"}


def exchange_markets(quote="USDT", n=150):
    """Respaldo del universo cuando CoinGecko no responde: los N pares más negociados en 24 h
    (Binance → Bybit → OKX). Sin capitalización (queda N/D; nunca se inventa)."""
    rows, src = None, None
    try:
        r = _binance("/api/v3/ticker/24hr")
        rows = [(x["symbol"][:-len(quote)], float(x["lastPrice"]), float(x["quoteVolume"]), float(x["priceChangePercent"]))
                for x in r if x["symbol"].endswith(quote)]
        src = "binance"
    except Exception:
        pass
    if rows is None:
        try:
            r = get_json(BYBIT + "/v5/market/tickers", {"category": "spot"}, retries=1)
            rows = [(x["symbol"][:-len(quote)], float(x["lastPrice"]), float(x.get("turnover24h") or 0),
                     float(x.get("price24hPcnt") or 0) * 100) for x in r["result"]["list"] if x["symbol"].endswith(quote)]
            src = "bybit"
        except Exception:
            pass
    if rows is None:
        r = get_json(OKX + "/api/v5/market/tickers", {"instType": "SPOT"}, retries=1)
        rows = []
        for x in r["data"]:
            if x["instId"].endswith("-" + quote):
                last, op = float(x["last"]), float(x.get("sodUtc0") or x.get("open24h") or 0)
                rows.append((x["instId"].split("-")[0], last, float(x.get("volCcy24h") or 0), (last / op - 1) * 100 if op else 0))
        src = "okx"
    rows = [r for r in rows if r[0] and r[0] not in STABLE_BASES and "USD" not in r[0]
            and not r[0].endswith(("UP", "DOWN", "BULL", "BEAR"))]
    rows.sort(key=lambda r: -r[2])
    source_used["markets"] = src
    return [{"symbol": b.lower(), "id": b.lower(), "name": b, "current_price": px, "total_volume": qv,
             "price_change_percentage_24h": chg, "market_cap": None} for b, px, qv, chg in rows[:n]]


def binance_symbols(quote="USDT"):
    """Pares spot operables. Si Binance no responde, usa la lista de Bybit u OKX (source_used['symbols'])."""
    errs = []
    try:
        info = _binance("/api/v3/exchangeInfo", {"permissions": "SPOT"})
        out = {s["baseAsset"] for s in info.get("symbols", []) if s.get("quoteAsset") == quote and s.get("status") == "TRADING"}
        if out:
            source_used["symbols"] = "binance"; return out
    except Exception as e:
        errs.append(f"Binance: {e}")
    try:
        r = get_json(BYBIT + "/v5/market/instruments-info", {"category": "spot", "limit": 1000}, retries=1)
        out = {x["baseCoin"] for x in r["result"]["list"] if x.get("quoteCoin") == quote and x.get("status") == "Trading"}
        if out:
            source_used["symbols"] = "bybit"; return out
    except Exception as e:
        errs.append(f"Bybit: {e}")
    try:
        r = get_json(OKX + "/api/v5/public/instruments", {"instType": "SPOT"}, retries=1)
        out = {x["baseCcy"] for x in r["data"] if x.get("quoteCcy") == quote and x.get("state") == "live"}
        if out:
            source_used["symbols"] = "okx"; return out
    except Exception as e:
        errs.append(f"OKX: {e}")
    raise RuntimeError(" | ".join(errs))


INTERVAL_MS = {"1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000, "1w": 604_800_000}


def drop_open_candle(k, interval, now_ms=None):
    """Quita la última vela si aún no ha cerrado (las decisiones se toman solo con velas cerradas)."""
    now_ms = now_ms or int(time.time() * 1000)
    step = INTERVAL_MS.get(interval)
    if step and k["t"] and k["t"][-1] + step > now_ms:
        k = {key: v[:-1] for key, v in k.items()}
    return k


def klines(symbol, interval="1d", limit=365, start=None, closed=False):
    """Velas OHLCV. Con closed=True se descarta la vela en curso (sin cerrar)."""
    rows = kline_rows(symbol, interval, limit, start)
    # [openTime, open, high, low, close, volume, closeTime, quoteVolume, ...]
    k = {
        "t": [int(r[0]) for r in rows],
        "o": [float(r[1]) for r in rows],
        "h": [float(r[2]) for r in rows],
        "l": [float(r[3]) for r in rows],
        "c": [float(r[4]) for r in rows],
        "v": [float(r[7]) for r in rows],  # volumen en USDT
    }
    return drop_open_candle(k, interval) if closed else k


def funding_rates():
    """Último funding de todos los perpetuos USDT (dato de sentimiento)."""
    try:
        rows = get_json("https://fapi.binance.com/fapi/v1/premiumIndex")
        return {r["symbol"]: float(r.get("lastFundingRate") or 0) for r in rows}
    except Exception:
        return {}


def open_interest_change(symbol):
    """Cambio % del open interest en 24h (periodos de 4h)."""
    try:
        rows = get_json("https://fapi.binance.com/futures/data/openInterestHist",
                        {"symbol": symbol, "period": "4h", "limit": 7})
        if len(rows) >= 2:
            a, b = float(rows[0]["sumOpenInterestValue"]), float(rows[-1]["sumOpenInterestValue"])
            return (b - a) / a * 100 if a else None
    except Exception:
        return None
    return None


def fear_greed():
    try:
        d = get_json("https://api.alternative.me/fng/", {"limit": 7})["data"]
        return {"value": int(d[0]["value"]), "label": d[0]["value_classification"],
                "week": [int(x["value"]) for x in d]}
    except Exception:
        return None
