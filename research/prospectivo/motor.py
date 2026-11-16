"""Motor de backtest/simulación por pesos objetivo, para cualquier frecuencia de barra y varios exchanges.

Independiente de research/edge3/engine.py y de radar/quant (no los importa). Convenciones:
  * `pesos` (barra × activo): peso objetivo decidido con información hasta el CIERRE de esa barra. Fila NaN = no
    rebalancear. Pesos ≥ 0 en spot; un activo marcado como perpetuo admite pesos negativos (corto) y paga/cobra funding.
  * Ejecución en la APERTURA de la barra t + latencia (latencia ≥ 1: nunca en la misma barra en que se decide).
  * La operación se limita a `participacion_max` del notional de la barra ANTERIOR (dato ya conocido).
  * Costes: ModeloCostes (comisión + spread + deslizamiento + impacto √participación). Funding por barra en perps.
  * Perpetuos: la posición es nocional (no consume efectivo salvo costes); su PnL se liquida al efectivo cada barra.
  * El efectivo no invertido rinde el tipo libre de riesgo (rf por barra); el apalancamiento (efectivo < 0) lo paga.
  * Si un activo deja de cotizar con posición abierta, se liquida al último precio con un recorte (`recorte_deslistado`).
Salida: curva de capital, retornos por barra, exposición, operaciones, episodios (entrada→salida por activo) y desglose
de costes.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd
from .costes import ModeloCostes


@dataclass
class Mercado:
    open: pd.DataFrame            # barra × activo
    close: pd.DataFrame
    notional: pd.DataFrame        # volumen negociado en moneda de cotización por barra
    segundos_barra: int
    perpetuos: tuple = ()         # activos que admiten corto (y pagan funding)
    funding: pd.DataFrame | None = None   # tasa total liquidada dentro de cada barra (fracción), barra × activo
    rf: pd.Series | None = None           # tipo libre de riesgo por barra (fracción)

    @property
    def barras_anio(self):
        return 365 * 86400 / self.segundos_barra


def simular(m: Mercado, pesos: pd.DataFrame, costes: ModeloCostes | None = None, capital=100_000.0,
            apalancamiento_max=1.0, recorte_deslistado=0.5, diferencial_prestamo=0.0):
    costes = costes or ModeloCostes()
    if costes.latencia_barras < 1:
        raise ValueError("latencia_barras debe ser ≥ 1: no se puede ejecutar en la barra de la decisión")
    cols = list(m.close.columns)
    idx = m.close.index
    W = pesos.reindex(index=idx, columns=cols)
    spot = [c for c in cols if c not in m.perpetuos]
    if (W[spot] < -1e-12).any().any():
        raise ValueError("peso negativo en un activo spot: solo los perpetuos admiten cortos")
    O, C = m.open[cols].values, m.close[cols].values
    N = m.notional.reindex(index=idx, columns=cols).values
    F = (m.funding.reindex(index=idx, columns=cols).fillna(0.0).values if m.funding is not None
         else np.zeros(C.shape))
    RF = m.rf.reindex(idx).fillna(0.0).values if m.rf is not None else np.zeros(len(idx))
    sig = pd.DataFrame(C, index=idx).pct_change(fill_method=None).rolling(48, min_periods=10).std().shift(1).values
    T, A = C.shape
    perp = np.array([c in m.perpetuos for c in cols]); sp = ~perp
    h = np.zeros(A); cash = capital
    eq = np.empty(T); expo = np.empty(T)
    cost_tot = {"comision": 0.0, "spread": 0.0, "deslizamiento": 0.0, "impacto": 0.0, "funding": 0.0,
                "deslistado": 0.0, "financiacion": 0.0}
    ops = []
    ep_open = {}; episodios = []
    pnl_asset = np.zeros(A)
    lat = costes.latencia_barras
    Wv = W.values
    last_close = np.full(A, np.nan)
    for t in range(T):
        # 1) del cierre anterior a la apertura actual
        o = O[t]
        if t > 0:
            g = np.where(np.isfinite(o) & np.isfinite(last_close) & (h != 0), o / last_close - 1, 0.0)
            pnl_asset += h * g; cash += float((h * g)[perp].sum()); h = h * (1 + g)
        # activos deslistados (sin precio) con posición abierta: liquidación forzosa con recorte
        dead = (h != 0) & ~np.isfinite(o)
        for a in np.where(dead)[0]:
            loss = abs(h[a]) * recorte_deslistado
            cash += (h[a] if sp[a] else 0.0) - loss; pnl_asset[a] -= loss; cost_tot["deslistado"] += loss
            ops.append((idx[t], cols[a], -h[a], loss, "deslistado")); h[a] = 0.0
        # 2) rebalanceo con la decisión de la barra t-lat
        if t - lat >= 0 and not np.isnan(Wv[t - lat]).all():
            E = cash + h[sp].sum()
            w = np.nan_to_num(Wv[t - lat]); w = np.where(np.isfinite(o), w, 0.0)
            gross = np.abs(w).sum()
            if gross > apalancamiento_max:
                w = w * apalancamiento_max / gross
            delta = w * E - h
            lim = costes.participacion_max * np.nan_to_num(N[t - 1] if t > 0 else np.zeros(A))
            delta = np.clip(delta, -lim, lim)
            for a in np.where(np.abs(delta) > 1e-9)[0]:
                vb = N[t - 1, a] if t > 0 else np.nan
                if sp[a] and delta[a] > 0:      # compra spot: el coste sale del mismo efectivo (sin apalancarse)
                    delta[a] = delta[a] / (1 + costes.coste_unitario(cols[a], delta[a], vb, sig[t, a]))
                d = costes.desglose(cols[a], abs(delta[a]), vb, sig[t, a])
                c = sum(d.values())
                for k, v in d.items():
                    cost_tot[k] += v
                prev = h[a]; h[a] += delta[a]; cash -= (delta[a] if sp[a] else 0.0) + c; pnl_asset[a] -= c
                ops.append((idx[t], cols[a], delta[a], c, "rebalanceo"))
                if prev == 0 and h[a] != 0:
                    ep_open[a] = (idx[t], pnl_asset[a] + c, abs(h[a]))
                elif prev != 0 and abs(h[a]) < 1e-9 * max(1.0, abs(prev)):
                    h[a] = 0.0
        # 3) de la apertura al cierre
        c_ = C[t]
        g = np.where(np.isfinite(c_) & np.isfinite(o) & (h != 0), c_ / o - 1, 0.0)
        pnl_asset += h * g; cash += float((h * g)[perp].sum()); h = h * (1 + g)
        # 4) funding de perpetuos (largo paga tasa positiva) y remuneración/financiación del efectivo
        fpay = float((h * F[t]).sum()); cash -= fpay; pnl_asset -= h * F[t]; cost_tot["funding"] += fpay
        # el colateral de los perpetuos está en el efectivo: se supone remunerado al rf (optimista, documentado)
        if cash >= 0:
            cash += cash * RF[t]
        else:
            fin = -cash * (RF[t] + diferencial_prestamo / m.barras_anio); cash -= fin; cost_tot["financiacion"] += fin
        last_close = np.where(np.isfinite(c_), c_, last_close)
        # cierre de episodios
        for a in list(ep_open):
            if h[a] == 0:
                t0, p0, n0 = ep_open.pop(a)
                episodios.append({"activo": cols[a], "entrada": t0, "salida": idx[t],
                                  "pnl": float(pnl_asset[a] - p0), "retorno": float((pnl_asset[a] - p0) / n0)})
        eq[t] = cash + h[sp].sum()
        expo[t] = np.abs(h).sum() / eq[t] if eq[t] > 0 else np.nan
    for a, (t0, p0, n0) in ep_open.items():
        episodios.append({"activo": cols[a], "entrada": t0, "salida": None, "pnl": float(pnl_asset[a] - p0),
                          "retorno": float((pnl_asset[a] - p0) / n0)})
    curva = pd.Series(eq, index=idx, name="capital")
    ret = curva.pct_change().fillna(curva.iloc[0] / capital - 1)
    return {"curva": curva, "retornos": ret, "exposicion": pd.Series(expo, index=idx), "capital": capital,
            "operaciones": pd.DataFrame(ops, columns=["ts", "activo", "notional", "coste", "motivo"]),
            "episodios": pd.DataFrame(episodios, columns=["activo", "entrada", "salida", "pnl", "retorno"]),
            "costes": cost_tot, "pnl_por_activo": dict(zip(cols, pnl_asset.tolist())),
            "barras_anio": m.barras_anio, "rf": (pd.Series(RF, index=idx))}


def comprar_y_mantener(m: Mercado, activo="BTC", costes=None, capital=100_000.0):
    """Referencia: 100 % en un activo desde la primera barra (con su coste de entrada)."""
    W = pd.DataFrame(np.nan, index=m.close.index, columns=m.close.columns)
    W.iloc[0] = 0.0; W.iloc[0, W.columns.get_loc(activo)] = 1.0
    return simular(m, W, costes, capital)


def efectivo_remunerado(m: Mercado, capital=100_000.0):
    rf = m.rf.reindex(m.close.index).fillna(0.0) if m.rf is not None else pd.Series(0.0, index=m.close.index)
    curva = capital * (1 + rf).cumprod()
    return {"curva": curva, "retornos": rf, "barras_anio": m.barras_anio}
