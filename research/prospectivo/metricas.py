"""Métricas y estadística para la fase prospectiva.

Referencias: Bailey y López de Prado (2012, 2014) PSR, MinTRL y DSR; Bailey, Borwein, López de Prado y Zhu (2017) PBO;
Politis y Romano (1994) bootstrap estacionario; Holm (1979); Benjamini y Hochberg (1995); Lan y DeMets (1983) con la
función de gasto de O'Brien-Fleming.
"""
from __future__ import annotations
import itertools, math
from statistics import NormalDist
import numpy as np
import pandas as pd

_N = NormalDist()
EULER = 0.5772156649015329


def _momentos(r):
    r = np.asarray(r, float); d = r - r.mean(); s2 = (d ** 2).mean()
    if s2 <= 0:
        return 0.0, 3.0
    return float((d ** 3).mean() / s2 ** 1.5), float((d ** 4).mean() / s2 ** 2)


def sharpe(r, barras_anio=365, rf=None):
    r = pd.Series(r).dropna()
    if rf is not None:
        r = r - pd.Series(rf).reindex(r.index).fillna(0.0)
    sd = r.std()
    return float(r.mean() / sd * math.sqrt(barras_anio)) if len(r) > 2 and sd > 0 else 0.0


def metricas(res, barras_anio=None, rf=None, episodios=None):
    """Métricas completas de una simulación (salida de motor.simular) o de una serie de retornos."""
    if isinstance(res, dict):
        r = res["retornos"]; barras_anio = barras_anio or res.get("barras_anio", 365)
        rf = res.get("rf") if rf is None else rf
        episodios = res.get("episodios") if episodios is None else episodios
    else:
        r = pd.Series(res); barras_anio = barras_anio or 365
    r = pd.Series(r).dropna()
    eq = (1 + r).cumprod()
    n = len(r); anios = n / barras_anio
    tot = float(eq.iloc[-1] - 1) if n else 0.0
    cagr = float(eq.iloc[-1] ** (1 / anios) - 1) if n and eq.iloc[-1] > 0 and anios > 0 else -1.0
    dd = float((eq / eq.cummax() - 1).min()) if n else 0.0
    neg = r[r < 0]
    sortino = float(r.mean() / math.sqrt((neg ** 2).sum() / n) * math.sqrt(barras_anio)) if len(neg) else 0.0
    rfs = pd.Series(rf).reindex(r.index).fillna(0.0) if rf is not None else pd.Series(0.0, index=r.index)
    exceso = r - rfs
    out = {"barras": n, "anios": round(anios, 3), "retorno_total": tot, "cagr": cagr,
           "vol_anual": float(r.std() * math.sqrt(barras_anio)) if n > 1 else 0.0,
           "sharpe": sharpe(r, barras_anio), "sharpe_exceso_efectivo": sharpe(exceso, barras_anio),
           "sortino": sortino, "max_dd": dd, "calmar": cagr / abs(dd) if dd < 0 else None,
           "retorno_efectivo": float((1 + rfs).prod() - 1), "exceso_sobre_efectivo": tot - float((1 + rfs).prod() - 1)}
    if episodios is not None and len(episodios):
        e = pd.DataFrame(episodios)["retorno"].astype(float)
        g, p = e[e > 0].sum(), -e[e <= 0].sum()
        out.update({"operaciones": int(len(e)), "acierto": float((e > 0).mean()), "esperanza": float(e.mean()),
                    "factor_beneficio": float(g / p) if p > 0 else None,
                    "ganancia_media": float(e[e > 0].mean()) if (e > 0).any() else 0.0,
                    "perdida_media": float(e[e <= 0].mean()) if (e <= 0).any() else 0.0})
    else:
        out.update({"operaciones": 0, "acierto": None, "esperanza": None, "factor_beneficio": None})
    return out


# ------------------------------------------------------------------------------------------------ Sharpe probabilístico
def psr(r, sr0=0.0, barras_anio=365):
    """Probabilistic Sharpe Ratio: P(SR verdadero > sr0) con asimetría y curtosis. sr0 anualizado."""
    r = np.asarray(pd.Series(r).dropna(), float); n = len(r)
    if n < 3 or r.std(ddof=1) == 0:
        return 0.0
    sr = r.mean() / r.std(ddof=1); s0 = sr0 / math.sqrt(barras_anio)
    sk, ku = _momentos(r)
    den = math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr ** 2))
    return float(_N.cdf((sr - s0) * math.sqrt(n - 1) / den))


def sr0_deflactado(n_pruebas, var_sr_anual, barras_anio=365):
    """Umbral del DSR: Sharpe máximo esperado entre n_pruebas independientes bajo H0 (anualizado)."""
    if n_pruebas <= 1:
        return 0.0
    z1 = _N.inv_cdf(1 - 1 / n_pruebas); z2 = _N.inv_cdf(1 - 1 / (n_pruebas * math.e))
    return float(math.sqrt(max(var_sr_anual, 0.0)) * ((1 - EULER) * z1 + EULER * z2))


def dsr(r, n_pruebas, var_sr_anual, barras_anio=365):
    """Deflated Sharpe Ratio con N = total acumulado del programa (registro.total_pruebas())."""
    s0 = sr0_deflactado(n_pruebas, var_sr_anual, barras_anio)
    return {"sr0": s0, "dsr": psr(r, s0, barras_anio)}


def min_trl(sr_anual, sr0=0.0, sk=0.0, ku=3.0, confianza=0.95, barras_anio=365):
    """Minimum Track Record Length (en años) para que el Sharpe observado supere sr0 con la confianza dada."""
    sr, s0 = sr_anual / math.sqrt(barras_anio), sr0 / math.sqrt(barras_anio)
    if sr <= s0:
        return math.inf
    n = 1 + (1 - sk * sr + (ku - 1) / 4 * sr ** 2) * (_N.inv_cdf(confianza) / (sr - s0)) ** 2
    return n / barras_anio


def anios_necesarios(sr_anual, alfa=0.05, potencia=0.80, barras_anio=365):
    """Años de datos para detectar un Sharpe anual dado (contraste unilateral, iid). Var(SR por barra) ≈
    (1 + s²/2)/T con s el Sharpe por barra; con barras diarias o más finas el término s²/2 es despreciable y queda
    T_años ≈ ((z_α + z_β)/SR_anual)²."""
    if sr_anual <= 0:
        return math.inf
    s = sr_anual / math.sqrt(barras_anio)
    z = _N.inv_cdf(1 - alfa) + _N.inv_cdf(potencia)
    return (1 + s ** 2 / 2) * (z / s) ** 2 / barras_anio


# ------------------------------------------------------------------------------------------------ PBO (CSCV)
def pbo(M: pd.DataFrame | np.ndarray, S=16, barras_anio=365):
    """Probability of Backtest Overfitting por CSCV. M: barras × configuraciones (retornos)."""
    M = np.asarray(M, float)
    T, K = M.shape
    if K < 2:
        raise ValueError("PBO necesita al menos 2 configuraciones")
    S = S - S % 2
    bloques = np.array_split(np.arange(T), S)
    logits = []
    for comb in itertools.combinations(range(S), S // 2):
        ins = np.concatenate([bloques[i] for i in comb]); oos = np.concatenate([bloques[i] for i in range(S) if i not in comb])
        def sr(x):
            sd = x.std(axis=0); return np.where(sd > 0, x.mean(axis=0) / np.where(sd > 0, sd, 1), 0.0)
        best = int(np.argmax(sr(M[ins])))
        rank = (sr(M[oos]).argsort().argsort()[best] + 1) / (K + 1)
        logits.append(math.log(rank / (1 - rank)))
    logits = np.array(logits)
    return {"pbo": float((logits <= 0).mean()), "combinaciones": len(logits), "logit_mediano": float(np.median(logits))}


# ------------------------------------------------------------------------------------------------ bootstrap
def bootstrap_estacionario(r, estadistico=None, n=2000, bloque_medio=20, semilla=0):
    """Bootstrap estacionario (bloques de longitud geométrica). Devuelve la distribución del estadístico y el
    p-valor unilateral de H0: estadístico ≤ 0 (centrando la serie en cero)."""
    x = np.asarray(pd.Series(r).dropna(), float); T = len(x)
    est = estadistico or (lambda v: v.mean() / v.std() if v.std() > 0 else 0.0)
    obs = est(x); xc = x - x.mean()
    rng = np.random.default_rng(semilla); p = 1 / bloque_medio
    dist = np.empty(n)
    tt = np.arange(T)
    for b in range(n):
        reinicio = rng.random(T) < p; reinicio[0] = True
        seg = np.cumsum(reinicio) - 1
        inicio_seg = tt[reinicio]; origen = rng.integers(T, size=len(inicio_seg))
        idx = (origen[seg] + tt - inicio_seg[seg]) % T
        dist[b] = est(xc[idx])
    return {"observado": float(obs), "p_valor": float((1 + (dist >= obs).sum()) / (n + 1)),
            "ic95_centrado": (float(np.quantile(dist, 0.025)), float(np.quantile(dist, 0.975)))}


# ------------------------------------------------------------------------------------------------ pruebas múltiples
def holm(pvalores: dict, alfa=0.05):
    items = sorted(pvalores.items(), key=lambda kv: kv[1]); m = len(items); out = {}; seguir = True
    for i, (k, p) in enumerate(items):
        umbral = alfa / (m - i)
        seguir = seguir and p <= umbral
        out[k] = {"p": p, "umbral": umbral, "rechaza_h0": seguir}
    return out


def benjamini_hochberg(pvalores: dict, q=0.05):
    items = sorted(pvalores.items(), key=lambda kv: kv[1]); m = len(items)
    kmax = max([i + 1 for i, (_, p) in enumerate(items) if p <= q * (i + 1) / m], default=0)
    return {k: {"p": p, "umbral": q * (i + 1) / m, "rechaza_h0": i + 1 <= kmax} for i, (k, p) in enumerate(items)}


# ------------------------------------------------------------------------------------------------ miradas secuenciales
def gasto_obf(fraccion_informacion, alfa=0.05):
    """Alfa acumulado gastado hasta una fracción de la información (Lan-DeMets, tipo O'Brien-Fleming, unilateral)."""
    t = min(max(fraccion_informacion, 1e-9), 1.0)
    return float(2 * (1 - _N.cdf(_N.inv_cdf(1 - alfa / 2) / math.sqrt(t))))


def fronteras_obf(puntos_control_dias, alfa=0.05):
    """Frontera z de cada mirada (aproximación conservadora: alfa incremental de cada mirada como si fuera
    independiente). Las miradas fuera de los puntos de control pre-registrados no tienen alfa."""
    total = puntos_control_dias[-1]; prev = 0.0; out = []
    for d in puntos_control_dias:
        g = gasto_obf(d / total, alfa); inc = max(g - prev, 1e-12); prev = g
        out.append({"dia": d, "alfa_acumulado": g, "alfa_incremental": inc, "z_frontera": _N.inv_cdf(1 - inc)})
    return out


def estadistico_z_sharpe(r, barras_anio=365):
    """z de H0: SR ≤ 0 con la corrección de Lo/Mertens para asimetría y curtosis."""
    r = np.asarray(pd.Series(r).dropna(), float); n = len(r)
    if n < 3 or r.std(ddof=1) == 0:
        return 0.0
    sr = r.mean() / r.std(ddof=1); sk, ku = _momentos(r)
    return float(sr * math.sqrt(n - 1) / math.sqrt(max(1e-12, 1 - sk * sr + (ku - 1) / 4 * sr ** 2)))
