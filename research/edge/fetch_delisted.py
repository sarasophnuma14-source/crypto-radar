"""Completa el panel con los pares USDT que Binance ya retiró por completo de su API.

Fuente: archivo público https://data.binance.vision (velas diarias mensuales, incluye pares deslistados).
Solo descarga los símbolos que NO están en data/research/panel.json.gz. No inventa datos: lo que no
existe en el archivo queda registrado en data/research/delisted_log.json.
Uso: python3 research/edge/fetch_delisted.py
"""
import concurrent.futures as cf, csv, gzip, io, json, re, sys, time, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
DL = "https://data.binance.vision/"
STABLE = {"USDC", "FDUSD", "TUSD", "BUSD", "USDP", "DAI", "EUR", "AEUR", "EURI", "USDE", "PAXG", "WBTC", "WBETH",
          "BFUSD", "USD1", "XUSD", "RLUSD", "BNSOL", "GBP", "AUD", "XAUT", "TRY", "BRL", "ARS", "ZAR", "UAH", "RUB",
          "BIDR", "IDRT", "NGN", "PLN", "RON", "JPY", "MXN", "COP", "CZK", "SUSD", "UST", "USTC", "PAX", "USDS", "USDSB"}


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read()
        except Exception as e:
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def list_prefixes(prefix):
    out, marker = [], ""
    while True:
        x = get(f"{S3}?delimiter=/&prefix={prefix}&marker={marker}").decode()
        out += re.findall(r"<Prefix>([^<]+)</Prefix>", x)[1:] if not marker else re.findall(r"<Prefix>([^<]+)</Prefix>", x)[1:]
        keys = re.findall(r"<Key>([^<]+)</Key>", x)
        out += keys
        nm = re.search(r"<NextMarker>([^<]+)</NextMarker>", x)
        if "<IsTruncated>true</IsTruncated>" not in x or not nm:
            return out
        marker = nm.group(1)


def main():
    have = set(json.load(gzip.open(OUT / "panel.json.gz", "rt")))
    pre = list_prefixes("data/spot/monthly/klines/")
    syms = sorted({p.rstrip("/").split("/")[-1] for p in pre if p.endswith("/")})
    usdt = []
    for s in syms:
        if not s.endswith("USDT"):
            continue
        b = s[:-4]
        if not b or b in STABLE or "USD" in b or b.endswith(("UP", "DOWN", "BULL", "BEAR")):
            continue
        if b not in have:
            usdt.append(b)
    print("pares USDT en el archivo:", sum(s.endswith("USDT") for s in syms), "· faltan en el panel:", len(usdt), flush=True)
    log, panel = {"missing_files": [], "symbols": {}}, {}

    def one(b):
        keys = [k for k in list_prefixes(f"data/spot/monthly/klines/{b}USDT/1d/") if k.endswith(".zip")]
        keys = [k for k in keys if re.search(r"-(\d{4})-(\d{2})\.zip$", k) and k[-11:-7] >= "2020"]
        rows = []
        for k in sorted(keys):
            try:
                z = zipfile.ZipFile(io.BytesIO(get(DL + k)))
                for r in csv.reader(io.TextIOWrapper(z.open(z.namelist()[0]))):
                    if not r or not r[0].isdigit():
                        continue
                    t = int(r[0]); t = t // 1000 if t > 10**14 else t      # algunos archivos recientes en microsegundos
                    rows.append((t, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[7])))
            except Exception as e:
                log["missing_files"].append([k, str(e)[:80]])
        rows = sorted({r[0]: r for r in rows}.values())
        return b, rows, len(keys)

    with cf.ThreadPoolExecutor(8) as ex:
        for i, (b, rows, nk) in enumerate(ex.map(one, usdt)):
            log["symbols"][b] = {"months": nk, "bars": len(rows)}
            if len(rows) >= 2:
                panel[b] = {"t": [r[0] for r in rows], "o": [r[1] for r in rows], "h": [r[2] for r in rows],
                            "l": [r[3] for r in rows], "c": [r[4] for r in rows], "v": [r[5] for r in rows],
                            "status": "DELISTED"}
            if i % 25 == 0:
                print(i, b, len(rows), flush=True)
    json.dump(panel, gzip.open(OUT / "panel_delisted.json.gz", "wt"))
    (OUT / "delisted_log.json").write_text(json.dumps(log, indent=1))
    print("listo:", len(panel), "símbolos deslistados con datos;", len(log["missing_files"]), "archivos fallidos", flush=True)


if __name__ == "__main__":
    main()
