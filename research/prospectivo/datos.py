"""Adaptadores de datos públicos con un esquema común.

Esquema de barras (DataFrame indexado por `ts` = apertura de la barra, UTC):
  open high low close volume quote_volume trades taker_buy_volume  available_at  exchange symbol
`available_at` es el instante en que la barra completa es observable (cierre + latencia de publicación). Ninguna señal
puede usar una barra antes de su `available_at` (lo comprueba guardia.comprobar_fugas).

Fuentes (verificadas accesibles el 2026-11-16 desde este entorno):
  Binance archivo  data.binance.vision  klines spot/perp de cualquier intervalo, aggTrades, fundingRate (mensual),
                   bookDepth y metrics de perpetuos (diarios)
  Coinbase         api.exchange.coinbase.com/products/{p}/candles
  Kraken           api.kraken.com/0/public/OHLC
  OKX              www.okx.com/api/v5/market/history-candles
  FRED             DTB3 (letra del Tesoro a 3 meses) como tipo del efectivo remunerado
No disponibles: api.binance.com/fapi (451), Bybit (403), bookTicker spot histórico (404). El libro de órdenes spot
histórico NO existe gratis: para flujo de órdenes/libro spot hay que GRABARLO hacia delante (ver grabar_libro).

Los parsers trabajan sobre bytes y no tocan la red, para poder probarlos sin conexión. La descarga guarda cada archivo
en data/prospectivo/ con su SHA-256 en un manifiesto; nunca sobrescribe un archivo ya descargado con contenido distinto.
"""
from __future__ import annotations
import csv, datetime as dt, hashlib, io, json, time, urllib.request, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

BASE_BINANCE = "https://data.binance.vision/data"
CACHE = Path(__file__).resolve().parents[2] / "data" / "prospectivo"
INTERVALOS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400, "1d": 86400}
COLS = ["open", "high", "low", "close", "volume", "quote_volume", "trades", "taker_buy_volume"]
LATENCIA_PUBLICACION = pd.Timedelta(seconds=2)    # margen conservador entre cierre de barra y dato observable


class DatosError(RuntimeError):
    pass


# ------------------------------------------------------------------------------------------------ utilidades
def _ms_a_ts(x):
    """Binance usa milisegundos y, en spot desde 2025, microsegundos. Se detecta por magnitud."""
    x = np.asarray(x, dtype="int64")
    unit = np.where(x > 10 ** 14, "us", "ms")
    if (unit == "us").all():
        return pd.to_datetime(x, unit="us", utc=True)
    if (unit == "ms").all():
        return pd.to_datetime(x, unit="ms", utc=True)
    return pd.DatetimeIndex([pd.Timestamp(int(v), unit=u, tz="UTC") for v, u in zip(x, unit)])


def _leer_zip_csv(contenido: bytes):
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        nombre = [n for n in z.namelist() if n.endswith(".csv")][0]
        filas = list(csv.reader(io.TextIOWrapper(z.open(nombre), encoding="utf-8")))
    if filas and filas[0] and not filas[0][0].lstrip("-").isdigit():
        return filas[0], filas[1:]      # con cabecera
    return None, filas


def _esquema(df, exchange, symbol, segundos):
    df = df.sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df["available_at"] = df.index + pd.Timedelta(seconds=segundos) + LATENCIA_PUBLICACION
    df["exchange"] = exchange; df["symbol"] = symbol
    for c in COLS:
        if c not in df:
            df[c] = np.nan
    return df[COLS + ["available_at", "exchange", "symbol"]]


# ------------------------------------------------------------------------------------------------ Binance (archivo)
def url_binance(tipo, symbol, fecha, intervalo=None, mercado="spot", periodo="daily"):
    """tipo: klines | aggTrades | fundingRate | bookDepth | metrics. fecha 'YYYY-MM-DD' (daily) o 'YYYY-MM' (monthly).
    mercado: spot | um (perpetuos USDⓈ-M)."""
    raiz = f"{BASE_BINANCE}/spot" if mercado == "spot" else f"{BASE_BINANCE}/futures/um"
    if tipo == "klines":
        if intervalo not in INTERVALOS:
            raise DatosError(f"intervalo no soportado: {intervalo}")
        return f"{raiz}/{periodo}/klines/{symbol}/{intervalo}/{symbol}-{intervalo}-{fecha}.zip"
    if tipo in ("aggTrades", "fundingRate", "bookDepth", "metrics"):
        if tipo in ("fundingRate", "bookDepth", "metrics") and mercado == "spot":
            raise DatosError(f"{tipo} solo existe para perpetuos")
        return f"{raiz}/{periodo}/{tipo}/{symbol}/{symbol}-{tipo}-{fecha}.zip"
    raise DatosError(f"tipo desconocido: {tipo}")


def parse_klines_binance(contenido: bytes, symbol, intervalo, mercado="spot"):
    _, filas = _leer_zip_csv(contenido)
    a = np.array([f[:11] for f in filas], dtype=object)
    df = pd.DataFrame({"open": a[:, 1].astype(float), "high": a[:, 2].astype(float), "low": a[:, 3].astype(float),
                       "close": a[:, 4].astype(float), "volume": a[:, 5].astype(float),
                       "quote_volume": a[:, 7].astype(float), "trades": a[:, 8].astype(float),
                       "taker_buy_volume": a[:, 9].astype(float)}, index=_ms_a_ts(a[:, 0].astype("int64")))
    df.index.name = "ts"
    return _esquema(df, f"binance_{mercado}", symbol, INTERVALOS[intervalo])


def parse_aggtrades_binance(contenido: bytes):
    """Devuelve operaciones agregadas: ts, price, qty, is_buyer_maker (True = el agresor vendió)."""
    _, filas = _leer_zip_csv(contenido)
    a = np.array([f[:7] for f in filas], dtype=object)
    bm = np.array([str(x).strip().lower() == "true" for x in a[:, 6]])
    df = pd.DataFrame({"price": a[:, 1].astype(float), "qty": a[:, 2].astype(float), "is_buyer_maker": bm},
                      index=_ms_a_ts(a[:, 5].astype("int64")))
    df.index.name = "ts"
    return df.sort_index()


def desequilibrio_flujo(trades: pd.DataFrame, frecuencia="1h"):
    """Desequilibrio de flujo de órdenes por barra: (compra agresiva − venta agresiva) / total, en [−1, 1].
    La barra se etiqueta con su apertura y es observable al cierre (available_at)."""
    vol = trades["qty"] * trades["price"]
    compra = vol.where(~trades["is_buyer_maker"], 0.0).resample(frecuencia, label="left", closed="left").sum()
    total = vol.resample(frecuencia, label="left", closed="left").sum()
    ofi = ((2 * compra - total) / total.replace(0, np.nan)).rename("ofi")
    out = pd.DataFrame({"ofi": ofi, "notional": total})
    out["available_at"] = out.index + pd.Timedelta(frecuencia) + LATENCIA_PUBLICACION
    return out


def parse_funding_binance(contenido: bytes, symbol):
    _, filas = _leer_zip_csv(contenido)
    a = np.array([f[:3] for f in filas], dtype=object)
    df = pd.DataFrame({"funding": a[:, 2].astype(float), "intervalo_h": a[:, 1].astype(float)},
                      index=_ms_a_ts(a[:, 0].astype("int64")))
    df.index.name = "ts"; df["symbol"] = symbol
    df["available_at"] = df.index          # el pago se conoce al liquidarse
    return df.sort_index()


def parse_bookdepth_binance(contenido: bytes):
    """bookDepth de perpetuos: timestamp, percentage (±1..±5 %), depth, notional. Devuelve el desequilibrio del libro
    a ±p %: (bid − ask) / (bid + ask) por instantánea."""
    cab, filas = _leer_zip_csv(contenido)
    df = pd.DataFrame(filas, columns=cab or ["timestamp", "percentage", "depth", "notional"])
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True)
    df["percentage"] = df["percentage"].astype(float); df["notional"] = df["notional"].astype(float)
    pv = df.pivot_table(index="ts", columns="percentage", values="notional", aggfunc="last")
    out = pd.DataFrame(index=pv.index)
    for p in sorted({abs(c) for c in pv.columns}):
        if -p in pv and p in pv:
            b, s = pv[-p], pv[p]
            out[f"desequilibrio_{int(p)}pct"] = (b - s) / (b + s)
    out["available_at"] = out.index
    return out


def parse_metrics_binance(contenido: bytes):
    cab, filas = _leer_zip_csv(contenido)
    df = pd.DataFrame(filas, columns=cab)
    df.index = pd.to_datetime(df.pop("create_time"), utc=True); df.index.name = "ts"
    for c in df.columns:
        if c != "symbol":
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df["available_at"] = df.index
    return df


# ------------------------------------------------------------------------------------------------ otros exchanges
def url_coinbase(producto, granularidad_s, inicio, fin):
    return (f"https://api.exchange.coinbase.com/products/{producto}/candles?granularity={granularidad_s}"
            f"&start={inicio}&end={fin}")


def parse_coinbase(texto: str, producto, granularidad_s):
    a = np.array(json.loads(texto), dtype=float).reshape(-1, 6)       # time, low, high, open, close, volume
    df = pd.DataFrame({"open": a[:, 3], "high": a[:, 2], "low": a[:, 1], "close": a[:, 4], "volume": a[:, 5]},
                      index=pd.to_datetime(a[:, 0].astype("int64"), unit="s", utc=True))
    df.index.name = "ts"
    return _esquema(df, "coinbase", producto, granularidad_s)


def url_kraken(par, intervalo_min, desde=None):
    return f"https://api.kraken.com/0/public/OHLC?pair={par}&interval={intervalo_min}" + (f"&since={desde}" if desde else "")


def parse_kraken(texto: str, par, intervalo_min):
    j = json.loads(texto)
    if j.get("error"):
        raise DatosError(f"Kraken: {j['error']}")
    clave = [k for k in j["result"] if k != "last"][0]
    a = np.array(j["result"][clave], dtype=object)
    df = pd.DataFrame({"open": a[:, 1].astype(float), "high": a[:, 2].astype(float), "low": a[:, 3].astype(float),
                       "close": a[:, 4].astype(float), "volume": a[:, 6].astype(float), "trades": a[:, 7].astype(float)},
                      index=pd.to_datetime(a[:, 0].astype("int64"), unit="s", utc=True))
    df.index.name = "ts"
    df = _esquema(df, "kraken", par, intervalo_min * 60)
    return df.iloc[:-1]     # Kraken devuelve la barra en curso como última: se descarta (no está cerrada)


def url_okx(inst, barra, despues=None):
    return f"https://www.okx.com/api/v5/market/history-candles?instId={inst}&bar={barra}&limit=100" + \
           (f"&after={despues}" if despues else "")


def parse_okx(texto: str, inst, segundos):
    j = json.loads(texto)
    if j.get("code") not in ("0", 0):
        raise DatosError(f"OKX: {j.get('msg')}")
    filas = [f for f in j["data"] if str(f[8]) == "1"]                  # solo barras confirmadas (cerradas)
    a = np.array(filas, dtype=object).reshape(-1, 9)
    df = pd.DataFrame({"open": a[:, 1].astype(float), "high": a[:, 2].astype(float), "low": a[:, 3].astype(float),
                       "close": a[:, 4].astype(float), "volume": a[:, 5].astype(float),
                       "quote_volume": a[:, 7].astype(float)},
                      index=pd.to_datetime(a[:, 0].astype("int64"), unit="ms", utc=True))
    df.index.name = "ts"
    return _esquema(df, "okx", inst, segundos)


def parse_fred(texto: str):
    """Serie diaria del tipo del efectivo (DTB3, % anual). Devuelve tipo diario compuesto, rellenado hacia delante.
    Se publica con retraso: el valor del día d se considera disponible en d+1."""
    df = pd.read_csv(io.StringIO(texto))
    df.columns = ["fecha", "tipo"]
    df["tipo"] = pd.to_numeric(df["tipo"], errors="coerce")
    s = df.set_index(pd.to_datetime(df["fecha"]))["tipo"].dropna() / 100
    s.index = s.index + pd.Timedelta(days=1)
    s = s.asfreq("D").ffill()
    return ((1 + s) ** (1 / 365) - 1).rename("rf_diario")


# ------------------------------------------------------------------------------------------------ universo point-in-time
def universo_point_in_time(barras: dict, min_hist_barras, min_notional, ventana, top=None):
    """barras: símbolo -> DataFrame del esquema común. Elegible en t si tiene ≥ min_hist_barras cerradas y notional
    medio (ventana barras, solo pasado) ≥ min_notional. Los activos que dejan de cotizar salen solos (sin datos ⇒ no
    elegibles), y los listados posteriores entran cuando acumulan historia: no hay sesgo de supervivencia."""
    close = pd.DataFrame({s: b["close"] for s, b in barras.items()})
    notional = pd.DataFrame({s: b["quote_volume"].fillna(b["close"] * b["volume"]) for s, b in barras.items()})
    hist = close.notna().cumsum()
    adv = notional.rolling(ventana, min_periods=max(1, ventana // 2)).mean()
    ok = (hist >= min_hist_barras) & (adv >= min_notional) & close.notna()
    if top:
        ok = ok & (adv.where(ok).rank(axis=1, ascending=False) <= top)
    return ok


# ------------------------------------------------------------------------------------------------ descarga con caché
def descargar(url, destino: Path | None = None, reintentos=4, timeout=60):
    """Descarga con caché local y manifiesto SHA-256. Devuelve bytes. Un 404 lanza DatosError (sin reintentos)."""
    destino = destino or CACHE / url.split("://", 1)[1].replace("/", "_").replace("?", "_").replace("&", "_")[:200]
    if destino.exists():
        return destino.read_bytes()
    destino.parent.mkdir(parents=True, exist_ok=True)
    err = None
    for i in range(reintentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "research-client/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (400, 403, 404, 451):
                raise DatosError(f"{e.code} en {url}") from e
            err = e
        except Exception as e:   # red
            err = e
        time.sleep(2 ** i)
    else:
        raise DatosError(f"descarga fallida tras {reintentos} intentos: {url}: {err}")
    destino.write_bytes(data)
    with (destino.parent / "MANIFIESTO.jsonl").open("a") as f:
        f.write(json.dumps({"url": url, "archivo": destino.name, "sha256": hashlib.sha256(data).hexdigest(),
                            "bytes": len(data), "descargado_utc": dt.datetime.now(dt.timezone.utc).isoformat()}) + "\n")
    return data


def binance_klines(symbol, intervalo, dias, mercado="spot"):
    """Concatena barras diarias del archivo de Binance para una lista de fechas 'YYYY-MM-DD'."""
    partes = []
    for d in dias:
        try:
            partes.append(parse_klines_binance(descargar(url_binance("klines", symbol, d, intervalo, mercado)),
                                               symbol, intervalo, mercado))
        except DatosError:
            continue          # día aún no publicado o par sin datos: se deja el hueco (no se rellena)
    if not partes:
        raise DatosError(f"sin datos de {symbol} {intervalo}")
    return pd.concat(partes).sort_index()


# ------------------------------------------------------------------------------------------------ grabación hacia delante
def parse_depth_snapshot(texto: str, niveles=(0.001, 0.005, 0.01)):
    """Instantánea REST del libro (data-api.binance.vision/api/v3/depth): spread relativo y desequilibrio a ±p."""
    j = json.loads(texto)
    b = np.array(j["bids"], dtype=float).reshape(-1, 2); a = np.array(j["asks"], dtype=float).reshape(-1, 2)
    if not len(b) or not len(a):
        raise DatosError("libro vacío")
    mid = (b[0, 0] + a[0, 0]) / 2
    out = {"mid": mid, "spread_rel": (a[0, 0] - b[0, 0]) / mid}
    for p in niveles:
        nb = float((b[:, 0] * b[:, 1])[b[:, 0] >= mid * (1 - p)].sum())
        na = float((a[:, 0] * a[:, 1])[a[:, 0] <= mid * (1 + p)].sum())
        out[f"bid_{p}"] = nb; out[f"ask_{p}"] = na
        out[f"desequilibrio_{p}"] = (nb - na) / (nb + na) if nb + na else 0.0
    return out


def grabar_libro(symbol, archivo: Path, reloj=lambda: dt.datetime.now(dt.timezone.utc)):
    """Toma UNA instantánea del libro spot y la añade a un JSONL (para ejecutar periódicamente, p. ej. cada minuto,
    en una máquina persistente). El histórico de libro spot no existe gratis: esta es la única forma honesta de
    obtenerlo. El instante de captura es el available_at."""
    url = f"https://data-api.binance.vision/api/v3/depth?symbol={symbol}&limit=1000"
    req = urllib.request.Request(url, headers={"User-Agent": "research-client/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        snap = parse_depth_snapshot(r.read().decode())
    rec = dict(snap, symbol=symbol, available_at=reloj().isoformat())
    archivo.parent.mkdir(parents=True, exist_ok=True)
    with archivo.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec
