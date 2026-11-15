"""Datos de mercado y ejecución SIMULADA.

- Velas diarias spot USDT públicas de Binance (data-api.binance.vision; sin claves, sin cuenta). Solo velas cerradas.
- No se mezclan fuentes: si Binance no responde, ese día no se procesa (no se usan Bybit ni OKX como respaldo,
  porque sus velas no son idénticas y cambiarían las señales).
- La ejecución (apertura de D+1, costes por tramo de liquidez, stops, huecos, límite del 1 % del ADV, retiradas)
  la hace radar.edge.sim.Engine, el mismo código que el backtest v2.
- No existe ninguna función que envíe órdenes reales. place_real_order() falla siempre.
"""
import datetime as dt, gzip, json, time
from pathlib import Path
from radar import data as rdata
from radar.edge import data as edata
from radar.paper_trading import REAL_ORDERS_ENABLED

DAY = 86_400_000
_LEVERAGED = ("UP", "DOWN", "BULL", "BEAR")
STABLE_FIAT = {"USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "AEUR", "EURI", "USDE", "PAXG", "WBTC", "WBETH",
               "BFUSD", "USD1", "XUSD", "RLUSD", "BNSOL", "GBP", "AUD", "XAUT", "TRY", "BRL", "ARS", "ZAR", "UAH", "RUB",
               "BIDR", "IDRT", "NGN", "PLN", "RON", "JPY", "MXN", "COP", "CZK", "SUSD", "UST", "USTC"}


def place_real_order(*a, **k):
    raise RuntimeError("Órdenes reales deshabilitadas: Crypto Radar paper trading solo simula.")


assert REAL_ORDERS_ENABLED is False


def tradable_symbols():
    """Pares spot USDT en TRADING, sin monedas estables, fiat, tokens envueltos ni apalancados (mismo filtro que el panel)."""
    info = rdata._binance("/api/v3/exchangeInfo", {"permissions": "SPOT"})
    out = set()
    for s in info.get("symbols", []):
        b = s.get("baseAsset", "")
        if s.get("quoteAsset") != "USDT" or s.get("status") != "TRADING":
            continue
        if b in STABLE_FIAT or b in edata.STABLE_EXTRA or b in edata.EXCLUDE or "USD" in b or b.endswith(_LEVERAGED):
            continue
        out.add(b)
    return out


def fetch_daily(sym, start_ms=None, limit=1000, now_ms=None):
    p = {"symbol": sym + "USDT", "interval": "1d", "limit": limit}
    if start_ms:
        p["startTime"] = int(start_ms)
    rows = rdata._binance("/api/v3/klines", p)
    k = {"t": [int(r[0]) for r in rows], "o": [float(r[1]) for r in rows], "h": [float(r[2]) for r in rows],
         "l": [float(r[3]) for r in rows], "c": [float(r[4]) for r in rows], "v": [float(r[7]) for r in rows]}
    return rdata.drop_open_candle(k, "1d", now_ms)


class CandleCache:
    """Velas diarias cerradas por símbolo en un archivo gz (se puede reconstruir descargando de nuevo)."""

    def __init__(self, path):
        self.path = Path(path); self.d = {}
        if self.path.exists():
            self.d = json.load(gzip.open(self.path, "rt"))

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with gzip.open(tmp, "wt") as fh:
            json.dump(self.d, fh)
        tmp.replace(self.path)

    def update(self, symbols, history_days=420, now_ms=None, pause=0.05, log=print):
        now_ms = now_ms or int(time.time() * 1000)
        last_closed = (now_ms // DAY) * DAY - DAY                       # apertura de la última vela diaria cerrada
        errors = {}
        for i, s in enumerate(sorted(symbols)):
            cur = self.d.get(s)
            if cur and cur["t"] and cur["t"][-1] >= last_closed:
                continue
            start = cur["t"][-1] + DAY if cur and cur["t"] else now_ms - history_days * DAY
            try:
                k = fetch_daily(s, start, now_ms=now_ms)
            except Exception as e:                                       # sin dato hoy: no se inventa
                errors[s] = str(e)[:120]; continue
            if cur:
                for key in "tohlcv":
                    cur[key] += k[key]
            elif k["t"]:
                self.d[s] = dict(k, status="TRADING")
            if pause:
                time.sleep(pause)
            if log and i % 100 == 0:
                log(f"velas {i}/{len(symbols)}")
        return {"last_closed": dt.datetime.fromtimestamp(last_closed / 1000, dt.timezone.utc).date().isoformat(),
                "errors": errors}
