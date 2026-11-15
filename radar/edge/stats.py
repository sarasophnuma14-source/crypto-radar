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
