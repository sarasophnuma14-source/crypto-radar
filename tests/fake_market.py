"""Datos sintéticos para probar la app sin internet (NO son datos reales)."""
import math, random, time
from radar import data

random.seed(7)
SYMS = ["BTC", "ETH", "SOL", "BNB", "XRP", "ADA", "AVAX", "LINK", "DOT", "NEAR", "FET", "RNDR", "TAO", "ONDO", "INJ",
        "ARB", "OP", "SUI", "APT", "PEPE", "DOGE", "WIF", "AAVE", "UNI", "TIA", "SEI", "JUP", "PYTH", "IMX", "GALA",
        "HBAR", "ATOM", "FIL", "AR", "LDO", "ENA", "PENDLE", "RUNE", "STX", "KAS"]
_cache = {}


def _series(sym, interval, limit):
    key = (sym, interval)
    if key not in _cache:
        rnd = random.Random(hash(sym) % 10000 + (0 if interval == "1d" else 1))
        n = 1000
        p = rnd.uniform(0.5, 100) if sym != "BTC" else 30000
        drift = rnd.uniform(-0.002, 0.004)
        vol = rnd.uniform(0.02, 0.06) if interval == "1d" else 0.012
        t0 = int(time.time() * 1000) - n * (86400000 if interval == "1d" else 14400000)
        out = {k: [] for k in "tohlcv"}
        regime_shift = rnd.randint(600, 950)
        for i in range(n):
            d = drift if i < regime_shift else rnd.uniform(-0.004, 0.01)
            o = p
            p = max(1e-6, p * math.exp(d + rnd.gauss(0, vol)))
            out["t"].append(t0 + i * (86400000 if interval == "1d" else 14400000))
            out["o"].append(o); out["c"].append(p)
            out["h"].append(max(o, p) * (1 + abs(rnd.gauss(0, vol / 2))))
            out["l"].append(min(o, p) * (1 - abs(rnd.gauss(0, vol / 2))))
            out["v"].append(abs(rnd.gauss(1, 0.4)) * 3e7 * (2.5 if i > n - 4 and rnd.random() < .3 else 1))
        _cache[key] = out
    s = _cache[key]
    return {k: v[-limit:] for k, v in s.items()}


def install():
    data.cg_global = lambda: {"market_cap_percentage": {"btc": 57.2, "eth": 11.8}, "total_market_cap": {"usd": 2.4e12},
                              "total_volume": {"usd": 9e10}, "market_cap_change_percentage_24h_usd": -1.2}
    data.fear_greed = lambda: {"value": 28, "label": "Fear", "week": [28, 25, 22, 30, 33, 35, 31]}

    def markets(per_page=250, page=1, category=None):
        if category:
            return [{"symbol": s.lower()} for s in SYMS[hash(category) % 7::5]]
        rows = []
        for i, s in enumerate(SYMS):
            d = _series(s, "1d", 400)
            mc = 1.2e12 / (i + 1) ** 1.6
            rows.append({"id": s.lower(), "symbol": s.lower(), "name": s.title(), "image": None, "current_price": d["c"][-1],
                         "market_cap": mc, "fully_diluted_valuation": mc / random.Random(i).uniform(0.3, 1.0),
                         "market_cap_rank": i + 1, "total_volume": mc * random.Random(i + 5).uniform(0.02, 0.2),
                         "price_change_percentage_24h": (d["c"][-1] / d["c"][-2] - 1) * 100,
                         "ath_change_percentage": (d["c"][-1] / max(d["h"]) - 1) * 100})
        return rows
    data.cg_markets = markets
    data.binance_symbols = lambda quote="USDT": set(SYMS)
    data.klines = lambda symbol, interval="1d", limit=365, start=None, closed=False: _series(symbol[:-4], interval, limit)
    data.funding_rates = lambda: {s + "USDT": random.Random(s).uniform(-0.0002, 0.0007) for s in SYMS[:25]}
    data.open_interest_change = lambda s: random.Random(s).uniform(-30, 30)

    def binance(path, params=None):
        if path == "/api/v3/ticker/price":
            return [{"symbol": s + "USDT", "price": str(_series(s, "1d", 2)["c"][-1] * 0.99)} for s in SYMS]
        if path == "/api/v3/klines":
            s = _series(params["symbol"][:-4], "4h", 300)
            return [[s["t"][i], s["o"][i], s["h"][i], s["l"][i], s["c"][i], 0] for i in range(len(s["c"]))]
        return {}
    data._binance = binance
