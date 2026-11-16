"""Descarga el funding y las velas diarias de los perpetuos USDT-M desde el archivo público data.binance.vision.

Solo AÑADE archivos en data/research/funding/ (no toca el panel spot ni nada existente). Reproducible: los archivos
mensuales son inmutables; se guarda un manifiesto con el SHA-256 de cada zip descargado.

Uso: python research/edge3/fetch_funding.py SIMBOLOS.txt   (un ticker spot por línea, p. ej. BTC)
"""
import concurrent.futures as cf, gzip, hashlib, io, json, sys, time, urllib.request, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data" / "research" / "funding"
BASE = "https://data.binance.vision/data/futures/um/monthly"
LIST = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/futures/um/monthly/{kind}/{sym}/{sub}"
MONTHS = [f"{y}-{m:02d}" for y in range(2019, 2027) for m in range(1, 13) if f"{y}-{m:02d}" <= "2026-10"]


def get(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(1 + 2 * i)
        except Exception:
            time.sleep(1 + 2 * i)
    raise RuntimeError(f"no se pudo descargar {url}")


def one(perp, kind):
    sub = "1d/" if kind == "klines" else ""
    rows, man = [], {}
    for m in MONTHS:
        name = f"{perp}-1d-{m}.zip" if kind == "klines" else f"{perp}-fundingRate-{m}.zip"
        url = f"{BASE}/{kind}/{perp}/{sub}{name}"
        b = get(url)
        if b is None:
            continue
        man[name] = hashlib.sha256(b).hexdigest()
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            txt = z.read(z.namelist()[0]).decode()
        for ln in txt.strip().splitlines():
            p = ln.split(",")
            if not p[0][:1].isdigit():
                continue
            rows.append([float(p[0]), float(p[2])] if kind == "fundingRate" else [float(x) for x in p[:6]])
    return perp, kind, rows, man


def main(path):
    syms = [s.strip() for s in open(path) if s.strip()]
    perps = {ln.strip() for ln in open("/tmp/perps.txt")} if Path("/tmp/perps.txt").exists() else set()
    pairs = {}
    for s in syms:
        base = s.split("~")[0]
        for cand in (f"{base}USDT", f"1000{base}USDT"):
            if not perps or cand in perps:
                pairs[base] = cand
                break
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"funding": {}, "klines": {}, "map": pairs, "manifest": {}}
    jobs = [(p, k) for p in sorted(set(pairs.values())) for k in ("fundingRate", "klines")]
    with cf.ThreadPoolExecutor(24) as ex:
        for perp, kind, rows, man in ex.map(lambda a: one(*a), jobs):
            res["funding" if kind == "fundingRate" else "klines"][perp] = rows
            res["manifest"].update(man)
    res["generated"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with gzip.open(OUT / "perp_funding_klines.json.gz", "wt") as f:
        json.dump(res, f)
    print(len(pairs), "perpetuos;", sum(len(v) for v in res["funding"].values()), "registros de funding;",
          sum(len(v) for v in res["klines"].values()), "velas")


if __name__ == "__main__":
    main(sys.argv[1])
