"""Guardias metodológicas: ventanas ya consumidas, datos prospectivos, anticipación, fugas y supervivencia.

Toda evaluación de una hipótesis registrada pasa por estas comprobaciones; si alguna falla se lanza GuardiaError
y la evaluación no se produce (no se degrada a un aviso).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import CORTE_PROSPECTIVO

# Ventanas que ya se usaron como validación o reserva final en rondas anteriores: no pueden volver a usarse como
# evidencia confirmatoria. Todo el histórico diario hasta 2026-11-14 ya se ha explorado.
VENTANAS_CONSUMIDAS = {
    "holdout_v1": ("2024-07-01", "2026-11-14"),
    "holdout_v3": ("2025-04-01", "2026-11-14"),
    "validacion_v3": ("2023-07-01", "2025-03-31"),
    "historico_explorado": ("2017-01-01", "2026-11-15"),
}


class GuardiaError(RuntimeError):
    pass


def _ts(x):
    t = pd.Timestamp(x)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def ventana_consumida(inicio, fin):
    """Nombres de las ventanas consumidas que se solapan con [inicio, fin]."""
    a, b = _ts(inicio), _ts(fin)
    return [k for k, (i, f) in VENTANAS_CONSUMIDAS.items() if a <= _ts(f) + pd.Timedelta(days=1) and b >= _ts(i)]


def exigir_prospectivo(index, inicio_prospectivo):
    """La evidencia confirmatoria solo puede usar barras posteriores al registro y al corte global."""
    lim = max(_ts(inicio_prospectivo), _ts(CORTE_PROSPECTIVO))
    idx = pd.DatetimeIndex(index)
    idx = idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")
    if len(idx) and idx.min() < lim:
        raise GuardiaError(f"hay datos anteriores al inicio prospectivo ({idx.min()} < {lim}): no son confirmatorios")
    return True


def recortar_prospectivo(df, inicio_prospectivo):
    lim = max(_ts(inicio_prospectivo), _ts(CORTE_PROSPECTIVO))
    idx = df.index.tz_localize("UTC") if df.index.tz is None else df.index.tz_convert("UTC")
    return df[idx >= lim]


def prueba_anticipacion(fn_senal, datos: pd.DataFrame, cortes=5, semilla=0, tol=1e-9):
    """Prueba genérica de anticipación por truncado: la señal en t calculada con datos[:t] debe ser idéntica a la
    calculada con todo el histórico. fn_senal(datos) -> DataFrame/Series indexado como datos."""
    full = fn_senal(datos)
    rng = np.random.default_rng(semilla)
    n = len(datos)
    if n < 20:
        raise GuardiaError("serie demasiado corta para la prueba de anticipación")
    for k in sorted(rng.choice(np.arange(10, n - 1), size=min(cortes, n - 11), replace=False)):
        part = fn_senal(datos.iloc[: k + 1])
        a = pd.DataFrame(full).iloc[k].astype(float).values
        b = pd.DataFrame(part).iloc[-1].astype(float).values
        same = np.isclose(a, b, atol=tol, equal_nan=True)
        if not same.all():
            raise GuardiaError(f"anticipación detectada: la señal en {datos.index[k]} cambia al añadir datos futuros")
    return True


def comprobar_fugas(disponible_en: pd.Series, decision_en: pd.Series):
    """Cada dato usado en una decisión debe estar disponible antes de esa decisión (available_at <= decision_at)."""
    d = pd.to_datetime(disponible_en, utc=True); t = pd.to_datetime(decision_en, utc=True)
    malos = d > t
    if malos.any():
        raise GuardiaError(f"fuga de información: {int(malos.sum())} datos disponibles después de la decisión "
                           f"(primero: {d[malos].iloc[0]} > {t[malos].iloc[0]})")
    return True


def comprobar_supervivencia(universo: pd.DataFrame, listados: dict, deslistados: dict | None = None):
    """universo: fecha × activo booleano (activo elegible). listados/deslistados: activo -> fecha.
    Falla si un activo es elegible antes de su listado o después de su deslistado (información futura), y también si
    el universo no incluye NINGÚN activo deslistado cuando sí los hubo en el periodo (sesgo de supervivencia)."""
    deslistados = deslistados or {}
    naive = lambda x: _ts(x).tz_localize(None)
    idx = pd.DatetimeIndex(universo.index)
    idx = idx.tz_convert("UTC").tz_localize(None) if idx.tz is not None else idx
    for a in universo.columns:
        sel = idx[universo[a].fillna(False).astype(bool).values]
        if not len(sel):
            continue
        if a in listados and sel.min() < naive(listados[a]):
            raise GuardiaError(f"supervivencia/anticipación: {a} elegible antes de su listado")
        if a in deslistados and sel.max() > naive(deslistados[a]):
            raise GuardiaError(f"supervivencia: {a} elegible después de su deslistado")
    en_periodo = [a for a, f in deslistados.items() if idx.min() <= naive(f) <= idx.max()]
    if en_periodo and not any(a in universo.columns and universo[a].fillna(False).any() for a in en_periodo):
        raise GuardiaError(f"sesgo de supervivencia: el universo omite los {len(en_periodo)} activos deslistados "
                           "en el periodo")
    return True
