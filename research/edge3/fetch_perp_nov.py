"""Velas diarias de perpetuos de 2026-11-01 a 2026-11-14 (archivo diario de data.binance.vision). El funding de
noviembre aún no está publicado en el archivo mensual: en esos 14 días el funding se toma como 0 (dato faltante,
declarado en el informe). Salida: data/research/funding/perp_klines_2026-11.json.gz"""
import concurrent.futures as cf, gzip, hashlib, io, json, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_funding import get, OUT  # noqa: E402

DAYS = [f"2026-11-{d:02d}" for d in range(1, 15)]


def one(perp):
    rows, man = [], {}
    for d in DAYS:
        name = f"{perp}-1d-{d}.zip"
        try:
            b = get(f"https://data.binance.vision/data/futures/um/daily/klines/{perp}/1d/{name}")
        except RuntimeError:
            man[name] = "ERROR_DESCARGA"; continue
        if b is None:
            continue
        man[name] = hashlib.sha256(b).hexdigest()
        with zipfile.ZipFile(io.BytesIO(b)) as z:
            for ln in z.read(z.namelist()[0]).decode().strip().splitlines():
                p = ln.split(",")
                if p[0][:1].isdigit():
                    rows.append([float(x) for x in p[:6]])
    return perp, rows, man


if __name__ == "__main__":
    base = json.load(gzip.open(OUT / "perp_funding_klines.json.gz", "rt"))
    res = {"klines": {}, "manifest": {}}
    with cf.ThreadPoolExecutor(48) as ex:
        for perp, rows, man in ex.map(one, sorted(set(base["map"].values()))):
            res["klines"][perp] = rows; res["manifest"].update(man)
    with gzip.open(OUT / "perp_klines_2026-11.json.gz", "wt") as f:
        json.dump(res, f)
    print(sum(len(v) for v in res["klines"].values()), "velas;", sum(1 for v in res["manifest"].values() if v == "ERROR_DESCARGA"), "errores")
