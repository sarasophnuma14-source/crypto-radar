"""Métricas y estadística de la ronda v3: métricas completas, Deflated Sharpe Ratio y PBO por CSCV.

Referencias:
  Bailey, D. y López de Prado, M. (2014). The Deflated Sharpe Ratio. Journal of Portfolio Management 40(5).
  Bailey, D., Borwein, J., López de Prado, M. y Zhu, Q. (2017). The Probability of Backtest Overfitting.
    Journal of Computational Finance 20(4).
"""
from __future__ import annotations
import itertools, math
import numpy as np
import pandas as pd
from statistics import NormalDist

_N = NormalDist()


def _skew_kurt(x):
    x = np.asarray(x, float); m = x.mean(); d = x - m; s2 = (d ** 2).mean()
    return float((d ** 3).mean() / s2 ** 1.5), float((d ** 4).mean() / s2 ** 2)   # curtosis no en exceso

ANN = 365
EULER = 0.5772156649015329


def rets(curve):
    return curve.pct_change().dropna()


def sharpe(r):
    r = pd.Series(r).dropna()
    return float(r.mean() / r.std() * math.sqrt(ANN)) if len(r) > 2 and r.std() > 0 else 0.0


def metrics(res, start=None, end=None, P_regime=None):
    cv = res["curve"]
    if start is not None:
        cv = cv[cv.index >= pd.Timestamp(start)]
    if end is not None:
        cv = cv[cv.index <= pd.Timestamp(end)]
    base = res["curve"][res["curve"].index < cv.index[0]]
    c0 = base.iloc[-1] if len(base) else res["capital"]
    eq = pd.concat([pd.Series([c0], index=[cv.index[0] - pd.Timedelta(days=1)]), cv])
    r = rets(eq)
    days = len(cv)
    tot = eq.iloc[-1] / c0 - 1
    cagr = (eq.iloc[-1] / c0) ** (ANN / max(days, 1)) - 1 if eq.iloc[-1] > 0 else -1.0
    dd = float((eq / eq.cummax() - 1).min())
    neg = r[r < 0]
    sortino = float(r.mean() / math.sqrt((neg ** 2).sum() / len(r)) * math.sqrt(ANN)) if len(neg) else 0.0
    ep = [p for a, p in res["episodes"]]
    wins = [p for p in ep if p > 0]; los = [p for p in ep if p <= 0]
    ex = res["exposure"].reindex(cv.index)
    return {
        "retorno_neto_pct": round(tot * 100, 2), "cagr_pct": round(cagr * 100, 2), "sharpe": round(sharpe(r), 3),
        "sortino": round(sortino, 3), "calmar": round(cagr / abs(dd), 3) if dd < 0 else None,
        "max_dd_pct": round(dd * 100, 2), "vol_anual_pct": round(float(r.std() * math.sqrt(ANN) * 100), 2),
        "dias": days, "exposicion_media_pct": round(float(ex.mean() * 100), 1),
        "tiempo_en_mercado_pct": round(float((ex > 0.01).mean() * 100), 1),
        # Las métricas de episodios y costes se refieren a TODA la ejecución pasada a run() (start/end de run)
        "episodios": len(ep), "win_rate_pct": round(len(wins) / len(ep) * 100, 1) if ep else None,
        "ganancia_media": round(float(np.mean(wins)), 2) if wins else None,
        "perdida_media": round(float(np.mean(los)), 2) if los else None,
        "expectancy": round(float(np.mean(ep)), 2) if ep else None,
        "profit_factor": round(sum(wins) / -sum(los), 3) if los and sum(los) < 0 else None,
        "costes_totales": round(res["fees"] + res["slippage"], 2), "comisiones": round(res["fees"], 2),
        "deslizamiento": round(res["slippage"], 2), "funding": round(res["funding"], 2),
        "rotacion_x_anual": round(res["turnover"] / float(eq.mean()) * ANN / max(days, 1), 2),
        "perdida_retiradas": round(res["delist_loss"], 2),
    }


def dsr(r, n_trials, var_sr_trials, sr0_override=None):
    """Deflated Sharpe Ratio. r: retornos diarios del periodo evaluado. var_sr_trials: varianza de los Sharpe
    (diarios, no anualizados) de las pruebas. Devuelve la probabilidad de que el Sharpe real sea > SR0."""
    r = pd.Series(r).dropna().values
    T = len(r)
    if T < 30 or r.std() == 0:
        return {"dsr": 0.0, "sr0_anual": None, "sr_anual": 0.0, "T": T}
    sr = r.mean() / r.std(ddof=1)
    g3, g4 = _skew_kurt(r)
    if sr0_override is None:
        N = max(int(n_trials), 2)
        z1 = _N.inv_cdf(1 - 1 / N); z2 = _N.inv_cdf(1 - 1 / (N * math.e))
        sr0 = math.sqrt(max(var_sr_trials, 0.0)) * ((1 - EULER) * z1 + EULER * z2)
    else:
        sr0 = sr0_override
    den = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr ** 2, 1e-12))
    z = (sr - sr0) * math.sqrt(T - 1) / den
    return {"dsr": round(float(_N.cdf(z)), 4), "sr0_anual": round(sr0 * math.sqrt(ANN), 3),
            "sr_anual": round(sr * math.sqrt(ANN), 3), "T": T, "skew": round(float(g3), 3), "kurt": round(float(g4), 3)}


def pbo_cscv(R, S=16):
    """PBO por CSCV. R: DataFrame (días × configuraciones) de retornos diarios. Devuelve PBO y la mediana de λ."""
    R = R.dropna(how="all").fillna(0.0)
    T = len(R) // S * S
    R = R.iloc[:T]
    blocks = np.array_split(np.arange(T), S)
    lam = []
    for comb in itertools.combinations(range(S), S // 2):
        tr = np.concatenate([blocks[k] for k in comb]); te = np.concatenate([blocks[k] for k in range(S) if k not in comb])
        a, b = R.iloc[tr], R.iloc[te]
        s_tr = a.mean() / a.std().replace(0, np.nan); s_te = b.mean() / b.std().replace(0, np.nan)
        best = s_tr.idxmax()
        rank = s_te.rank(pct=True)[best]
        w = min(max(rank, 1e-6), 1 - 1e-6)
        lam.append(math.log(w / (1 - w)))
    lam = np.array(lam)
    return {"pbo": round(float((lam <= 0).mean()), 4), "lambda_mediana": round(float(np.median(lam)), 3),
            "combinaciones": len(lam), "S": S, "configs": R.shape[1]}
