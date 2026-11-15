"""Bootstrap por bloques estacionario (Politis-Romano) y corrección de Holm."""
import math
import numpy as np


def stationary_bootstrap(r, n_boot=5000, mean_block=20, seed=7):
    r = np.asarray(r, float); n = len(r)
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    idx = np.empty((n_boot, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, n_boot)
    jump = rng.random((n_boot, n)) < p
    newi = rng.integers(0, n, (n_boot, n))
    for t in range(1, n):
        idx[:, t] = np.where(jump[:, t], newi[:, t], (idx[:, t - 1] + 1) % n)
    return r[idx]


def test_mean(r, n_boot=5000, mean_block=20, seed=7):
    """p-valor unilateral de media > 0 (bootstrap centrado) e IC 90 % del Sharpe anualizado."""
    r = np.asarray(r, float)
    if len(r) < 30 or r.std() == 0:
        return {"p_value": 1.0, "sharpe_ci90": [None, None], "mean_ci90": [None, None]}
    B = stationary_bootstrap(r, n_boot, mean_block, seed)
    means = B.mean(axis=1)
    centered = means - r.mean()
    p = float((centered >= r.mean()).mean())
    sh = means / B.std(axis=1) * math.sqrt(365)
    return {"p_value": round(p, 4), "sharpe_ci90": [round(float(np.percentile(sh, 5)), 3), round(float(np.percentile(sh, 95)), 3)],
            "mean_ci90": [float(np.percentile(means, 5)), float(np.percentile(means, 95))]}


def holm(pvals):
    """Devuelve p-valores ajustados por Holm (dict nombre → p)."""
    items = sorted(pvals.items(), key=lambda kv: kv[1]); m = len(items); out = {}; run = 0.0
    for i, (k, p) in enumerate(items):
        run = max(run, min(1.0, (m - i) * p)); out[k] = round(run, 4)
    return out


# ---------------------------------------------------------------- añadido en la auditoría (Fase 5)
def circular_block_bootstrap(r, n_boot=5000, block=20, seed=7):
    """Bootstrap circular por bloques de longitud fija (Politis-Romano 1992)."""
    r = np.asarray(r, float); n = len(r)
    rng = np.random.default_rng(seed)
    nb = int(math.ceil(n / block))
    starts = rng.integers(0, n, (n_boot, nb))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n] % n
    return r[idx]


def bootstrap_test(r, method="stationary", block=20, n_boot=5000, seed=7, alpha=0.10):
    """p-valor unilateral (H0: media ≤ 0, bootstrap centrado) e intervalos de confianza (1 − alpha) de la media diaria,
    del Sharpe anualizado y del retorno anualizado."""
    r = np.asarray(r, float)
    r = r[np.isfinite(r)]
    if len(r) < 30 or r.std() == 0:
        return {"method": method, "block": block, "n": int(len(r)), "p_value": 1.0, "mean_ci": [None, None],
                "sharpe_ci": [None, None], "ann_return_ci": [None, None]}
    B = (stationary_bootstrap(r, n_boot, block, seed) if method == "stationary"
         else circular_block_bootstrap(r, n_boot, block, seed))
    means = B.mean(axis=1)
    p = float(((means - r.mean()) >= r.mean()).mean())
    sd = B.std(axis=1)
    sh = np.where(sd > 0, means / np.where(sd > 0, sd, 1) * math.sqrt(365), 0.0)
    q = [100 * alpha / 2, 100 * (1 - alpha / 2)]
    ann = (1 + means) ** 365 - 1
    return {"method": method, "block": block, "n": int(len(r)), "p_value": round(p, 4),
            "mean_daily": float(r.mean()), "sharpe": round(float(r.mean() / r.std() * math.sqrt(365)), 3),
            "mean_ci": [float(x) for x in np.percentile(means, q)],
            "sharpe_ci": [round(float(x), 3) for x in np.percentile(sh, q)],
            "ann_return_ci": [round(float(x) * 100, 2) for x in np.percentile(ann, q)], "ci_level": 1 - alpha}


def block_sensitivity(r, blocks=(10, 20, 30, 60), methods=("stationary", "circular"), **kw):
    return [bootstrap_test(r, m, b, **kw) for m in methods for b in blocks]


def bonferroni(pvals, m=None):
    m = m or len(pvals)
    return {k: round(min(1.0, p * m), 4) for k, p in pvals.items()}
