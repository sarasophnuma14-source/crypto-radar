"""Fuentes de datos públicas y gratuitas (sin claves):
- CoinGecko: universo, capitalización, FDV, supply, categorías, dominancia BTC.
- Binance spot: velas OHLCV (1D, 4H, 1W). Si Binance está bloqueado en tu país se usa data-api.binance.vision.
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
BINANCE_BASES = ["https://api.binance.com", "https://data-api.binance.vision", "https://api1.binance.com"]
_binance_base = None
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
    last_err = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout, context=_context()) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code == 429:
                time.sleep(15 * (attempt + 1))
                continue
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
    global _binance_base
    bases = [_binance_base] if _binance_base else BINANCE_BASES
    err = None
    for b in bases:
        try:
            r = get_json(b + path, params)
            _binance_base = b
            return r
        except Exception as e:
            err = e
    if _binance_base:
        _binance_base = None
    raise err


def binance_symbols(quote="USDT"):
    info = _binance("/api/v3/exchangeInfo", {"permissions": "SPOT"})
    out = set()
    for s in info.get("symbols", []):
        if s.get("quoteAsset") == quote and s.get("status") == "TRADING":
            out.add(s["baseAsset"])
    return out


def klines(symbol, interval="1d", limit=365):
    rows = _binance("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    # [openTime, open, high, low, close, volume, closeTime, quoteVolume, ...]
    return {
        "t": [int(r[0]) for r in rows],
        "o": [float(r[1]) for r in rows],
        "h": [float(r[2]) for r in rows],
        "l": [float(r[3]) for r in rows],
        "c": [float(r[4]) for r in rows],
        "v": [float(r[7]) for r in rows],  # volumen en USDT
    }


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
