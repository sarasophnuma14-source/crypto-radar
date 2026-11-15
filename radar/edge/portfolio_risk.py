"""Riesgo de cartera para el simulador v2 y el paper trading (solo datos hasta el cierre de D).

Parámetros fijados a priori (AUDITORIA_D_VOLMOM.md §3) antes de cualquier evaluación con el simulador v2. No se
calibran con ningún periodo:

  cov_window 90 días, mínimo 60 observaciones comunes   ventana de la matriz de covarianzas
  Ledoit-Wolf sobre la matriz de correlación             estimación robusta, siempre definida positiva
  número de condición de la CORRELACIÓN máximo 1e3       si se supera, la matriz se considera inestable
  volatilidad individual mínima 5 % anual                 por debajo, el activo se trata como estable y no se compra
  objetivo de volatilidad 40 % anual × 0,5 si BTC < SMA200  es un OBJETIVO DE RIESGO (techo), no de rentabilidad
  freno: sin entradas si la volatilidad realizada de la cartera en 30 días > 1,5 × objetivo
  límites duros: 0,5 % de riesgo por operación, 15 % por activo, 5 posiciones, 3 % de riesgo abierto,
                 exposición bruta ≤ 100 % (sin apalancamiento)
  datos insuficientes o matriz inestable ⇒ no se abren posiciones nuevas

Concentración sectorial: el panel no tiene clasificación sectorial fiable, así que no se aplica (N/D). La correlación
cubre en parte ese riesgo: dos monedas del mismo sector suelen estar muy correlacionadas y la matriz lo penaliza.
"""
import math
import numpy as np

PARAMS = {
    "cov_window": 90, "cov_min_obs": 60, "max_cond": 1e3, "min_asset_vol": 0.05,
    "target_vol": 0.40, "bear_mult": 0.5,
    "rv_window": 30, "rv_min_obs": 20, "rv_brake": 1.5,
    "risk_pct": 0.5, "max_pos_pct": 15.0, "max_positions": 5, "max_open_risk_pct": 3.0, "max_gross_pct": 100.0,
}
ANN = 365


def ledoit_wolf_corr(Z):
    """Contracción de Ledoit-Wolf (2004) de la correlación hacia la identidad. Z: (n, k) estandarizado.
    Devuelve (matriz, intensidad)."""
    n, k = Z.shape
    S = Z.T @ Z / n
    if k == 1:
        return np.ones((1, 1)), 0.0
    target = np.eye(k)
    d2 = ((S - target) ** 2).sum() / k
    b_bar2 = sum((np.outer(z, z) - S) ** 2 for z in Z).sum() / (n * n * k)
    shrink = 1.0 if d2 <= 0 else min(1.0, b_bar2 / d2)
    R = shrink * target + (1 - shrink) * S
    dg = np.sqrt(np.diag(R))
    return R / np.outer(dg, dg), float(shrink)


def estimate(rets, p=PARAMS):
    """rets: (n, k) rendimientos logarítmicos diarios (NaN = sin dato), filas en orden temporal, todas ≤ D.
    Devuelve dict ok/reason/vols/corr/cov (anualizados), condición e intensidad de contracción."""
    rets = np.asarray(rets, float)
    if rets.ndim != 2 or rets.shape[1] == 0:
        return {"ok": False, "reason": "sin activos"}
    rets = rets[-p["cov_window"]:]
    rows = np.all(np.isfinite(rets), axis=1)
    X = rets[rows]
    n, k = X.shape
    if n < p["cov_min_obs"]:
        return {"ok": False, "reason": f"datos insuficientes: {n} observaciones comunes (< {p['cov_min_obs']})"}
    sd = X.std(axis=0, ddof=1)
    if not np.all(np.isfinite(sd)) or np.any(sd <= 0):
        return {"ok": False, "reason": "varianza nula o no finita"}
    Z = (X - X.mean(axis=0)) / sd
    R, shrink = ledoit_wolf_corr(Z)
    vols = sd * math.sqrt(ANN)
    cov = R * np.outer(vols, vols)
    if np.any(vols < p["min_asset_vol"]):
        return {"ok": False, "reason": f"activo con volatilidad < {p['min_asset_vol']:.0%} (posible moneda estable)"}
    ev = np.linalg.eigvalsh(R)
    if not np.all(np.isfinite(ev)) or ev.min() <= 0 or np.linalg.eigvalsh(cov).min() <= 0:
        return {"ok": False, "reason": "matriz no definida positiva"}
    cond = float(ev.max() / ev.min())                                     # de la correlación: no depende de la escala
    if cond > p["max_cond"]:
        return {"ok": False, "reason": f"matriz inestable (condición {cond:.0f})", "cond": cond}
    return {"ok": True, "reason": None, "vols": vols, "corr": R, "cov": cov, "cond": cond, "shrinkage": shrink, "n_obs": n}


def portfolio_vol(w, cov):
    w = np.asarray(w, float)
    return float(math.sqrt(max(0.0, w @ cov @ w)))


def realized_vol(equity, p=PARAMS):
    """Volatilidad anualizada de la cartera en los últimos rv_window días (curva de capital hasta D)."""
    eq = np.asarray(equity[-(p["rv_window"] + 1):], float)
    if len(eq) < p["rv_min_obs"] + 1:
        return None
    r = np.diff(eq) / eq[:-1]
    return float(r.std(ddof=1) * math.sqrt(ANN))


def target_vol(bear, p=PARAMS):
    return p["target_vol"] * (p["bear_mult"] if bear else 1.0)


def plan_entries(equity, held, cands, rets, bear, equity_curve=None, p=PARAMS):
    """Tamaño de las órdenes nuevas.

    equity : capital al cierre de D (punto en el tiempo)
    held   : lista de dicts {"key", "value", "risk_usd"} de las posiciones que seguirán abiertas
    cands  : lista ordenada de dicts {"key", "ref_px", "stop"} (ref_px = precio de ejecución estimado con costes)
    rets   : (n, len(held)+len(cands)) rendimientos hasta D, columnas en el orden held + cands
    Devuelve {"orders": {key: valor_usd}, "rejected": {key: motivo}, "diag": {...}}.
    El valor final aún lo recortan, en la ejecución, el efectivo, la liquidez (1 % del ADV) y el precio real."""
    out = {"orders": {}, "rejected": {}, "diag": {}}
    if not cands:
        return out
    tv = target_vol(bear, p)
    risk_pct = p["risk_pct"] * (p["bear_mult"] if bear else 1.0)            # en mercado bajista también se reduce el riesgo
    out["diag"]["target_vol"] = tv; out["diag"]["risk_pct"] = risk_pct
    if equity <= 0:
        out["rejected"] = {c["key"]: "capital no positivo" for c in cands}
        return out
    rv = realized_vol(equity_curve, p) if equity_curve is not None else None
    out["diag"]["realized_vol_30d"] = rv
    if rv is not None and rv > p["rv_brake"] * tv:
        out["rejected"] = {c["key"]: f"freno: volatilidad realizada {rv:.0%} > {p['rv_brake']}×objetivo" for c in cands}
        return out
    # filtro individual: un candidato sin historia suficiente o sin volatilidad se rechaza sin bloquear a los demás
    rets = np.asarray(rets, float)[-p["cov_window"]:]
    nh0 = len(held); keep = []
    for i, c in enumerate(cands):
        x = rets[:, nh0 + i]; x = x[np.isfinite(x)]
        if len(x) < p["cov_min_obs"]:
            out["rejected"][c["key"]] = f"datos insuficientes: {len(x)} días (< {p['cov_min_obs']})"
        elif x.std(ddof=1) * math.sqrt(ANN) < p["min_asset_vol"]:
            out["rejected"][c["key"]] = "volatilidad casi nula (posible moneda estable)"
        else:
            keep.append(i)
    cands = [cands[i] for i in keep]
    rets = rets[:, list(range(nh0)) + [nh0 + i for i in keep]]
    if not cands:
        return out
    est = estimate(rets, p)
    out["diag"]["cov_ok"] = est["ok"]; out["diag"]["cov_reason"] = est.get("reason")
    if not est["ok"]:
        out["rejected"].update({c["key"]: "riesgo no estimable: " + est["reason"] for c in cands})
        return out
    out["diag"]["cond"] = est["cond"]; out["diag"]["shrinkage"] = est["shrinkage"]
    nh = len(held)
    w = np.zeros(nh + len(cands))
    for i, h in enumerate(held):
        w[i] = h["value"] / equity
    free_slots = p["max_positions"] - nh
    open_risk = sum(h["risk_usd"] for h in held)
    gross = w[:nh].sum()
    for i, c in enumerate(cands):
        j = nh + i
        if free_slots <= 0:
            out["rejected"][c["key"]] = "máximo de posiciones"; continue
        rps = c["ref_px"] - c["stop"]
        if not (rps > 0 and c["ref_px"] > 0):
            out["rejected"][c["key"]] = "stop no válido"; continue
        vol_i = est["vols"][j]
        wv = tv / p["max_positions"] / vol_i                                    # paridad de volatilidad (regla original)
        wr = risk_pct / 100 * c["ref_px"] / rps                                 # 0,5 % de riesgo por operación
        room = p["max_open_risk_pct"] / 100 * equity - open_risk
        wo = max(0.0, room) / equity * c["ref_px"] / rps                        # riesgo abierto 3 %
        wg = max(0.0, p["max_gross_pct"] / 100 - gross)                         # sin apalancamiento
        caps = {"límite 15 % por activo": p["max_pos_pct"] / 100, "paridad de volatilidad": wv,
                "riesgo 0,5 % por operación": wr, "límite de riesgo abierto 3 %": wo, "sin apalancamiento": wg}
        binding = min(caps, key=caps.get); wi = caps[binding]
        # límite de volatilidad de la cartera con la matriz completa: se reduce wi hasta cumplir el objetivo
        w[j] = wi
        if portfolio_vol(w, est["cov"]) > tv:
            lo, hi = 0.0, wi
            for _ in range(40):
                mid = (lo + hi) / 2; w[j] = mid
                lo, hi = (mid, hi) if portfolio_vol(w, est["cov"]) <= tv else (lo, mid)
            w[j] = wi = lo; binding = "volatilidad de la cartera en el objetivo"
        if wi * equity < 20:
            w[j] = 0.0
            out["rejected"][c["key"]] = f"tamaño < 20 USD ({binding})"; continue
        out["orders"][c["key"]] = wi * equity
        out["diag"].setdefault("binding", {})[c["key"]] = binding
        free_slots -= 1
        open_risk += wi * equity / c["ref_px"] * rps
        gross += wi
    out["diag"]["portfolio_vol_planned"] = portfolio_vol(w, est["cov"])
    return out
