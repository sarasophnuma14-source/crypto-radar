"""Clasificación APROBADA / RECHAZADA / DATOS INSUFICIENTES según los criterios pre-registrados.

Solo se clasifica en un punto de control pre-registrado (días desde inicio_prospectivo). Entre puntos de control no hay
decisión posible: DATOS INSUFICIENTES. Reglas:
  APROBADA            todos los criterios se cumplen en un punto de control, incluido cruzar la frontera O'Brien-Fleming
  RECHAZADA           (a) último punto de control sin cumplir todos los criterios; (b) futilidad: con ≥ 50 % de la
                      información el estadístico z es negativo, o en cualquier punto z < −1,645; (c) falla una guardia
  DATOS INSUFICIENTES antes del primer punto de control, o sin operaciones independientes suficientes, o en un punto
                      intermedio que ni aprueba ni es fútil
Una APROBADA aquí solo autoriza implementar en una rama experimental: no autoriza dinero real ni cambiar el motor.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from . import metricas as M

CRITERIOS_POR_DEFECTO = {
    "min_dias": 90, "min_operaciones": 30, "dsr_min": 0.95, "alfa": 0.05,
    "vecinos_positivos_min": 0.75, "vecinos_ratio_mediana_min": 0.5,
    "max_cuota_activo": 0.5, "max_cuota_episodio": 0.3, "exigir_supera_btc": True,
}


def _cuotas(pnl_por_activo: dict, episodios: pd.DataFrame | None):
    tot = sum(pnl_por_activo.values())
    pos = sum(v for v in pnl_por_activo.values() if v > 0)
    cuota_activo = max(pnl_por_activo.values()) / pos if pos > 0 else 1.0
    sin_mejor = tot - max(pnl_por_activo.values()) if pnl_por_activo else 0.0
    if episodios is not None and len(episodios) and tot > 0:
        cuota_ep = float(episodios["pnl"].max() / tot)
    else:
        cuota_ep = 1.0
    return cuota_activo, cuota_ep, sin_mejor


def clasificar(h: dict, ev: dict, total_pruebas: int, pvalores_programa: dict | None = None):
    """h: estado vigente de la hipótesis (Registro.hipotesis). ev (evidencia PROSPECTIVA, ya filtrada por guardia):
      dias, retornos, retornos_costes_x2, retornos_btc, rf, barras_anio, episodios, pnl_por_activo,
      sharpe_vecinos (lista), var_sr (varianza entre pruebas del Sharpe anual), wf_historico_sharpe, guardias_ok
    pvalores_programa: p-valores de todas las hipótesis evaluadas en esta ronda de miradas (para Holm y BH)."""
    c = dict(CRITERIOS_POR_DEFECTO, **(h.get("criterios") or {}))
    pcs = list(h["puntos_control_dias"]); dias = ev["dias"]
    motivos, ok = [], {}
    if not ev.get("guardias_ok", False):
        return {"clase": "RECHAZADA", "motivos": ["falló una guardia (anticipación, fuga, supervivencia o ventana)"],
                "criterios": {}}
    alcanzados = [p for p in pcs if p <= dias]
    if not alcanzados or dias < c["min_dias"]:
        return {"clase": "DATOS INSUFICIENTES", "motivos": [f"{dias} días prospectivos; primer punto de control "
                                                            f"{pcs[0]} (mínimo {c['min_dias']})"], "criterios": {}}
    pc = alcanzados[-1]; final = pc == pcs[-1]
    ba = ev.get("barras_anio", 365); r = pd.Series(ev["retornos"]).dropna()
    rf = ev.get("rf")
    exc = r - (pd.Series(rf).reindex(r.index).fillna(0.0) if rf is not None else 0.0)
    z = M.estadistico_z_sharpe(exc, ba)
    fr = {f["dia"]: f for f in M.fronteras_obf(pcs, c["alfa"])}[pc]
    m = M.metricas({"retornos": r, "barras_anio": ba, "rf": rf, "episodios": ev.get("episodios")})
    info = pc / pcs[-1]
    ok["frontera_obf"] = z >= fr["z_frontera"]
    nops = m["operaciones"]
    ok["operaciones"] = nops >= c["min_operaciones"]
    m2 = M.metricas({"retornos": ev["retornos_costes_x2"], "barras_anio": ba, "rf": rf})
    ok["costes_x2"] = m2["sharpe_exceso_efectivo"] > 0 and m2["exceso_sobre_efectivo"] > 0
    ok["exceso_efectivo"] = m["exceso_sobre_efectivo"] > 0
    if c["exigir_supera_btc"]:
        mb = M.metricas({"retornos": ev["retornos_btc"], "barras_anio": ba, "rf": rf})
        ok["supera_btc"] = m["sharpe"] > mb["sharpe"] and m["retorno_total"] > mb["retorno_total"]
    d = M.dsr(exc, total_pruebas, ev.get("var_sr", 1.0), ba)
    ok["dsr"] = d["dsr"] >= c["dsr_min"]
    if pvalores_programa:
        hid = h["id"]
        ok["holm"] = bool(M.holm(pvalores_programa, c["alfa"]).get(hid, {}).get("rechaza_h0", False))
        ok["bh"] = bool(M.benjamini_hochberg(pvalores_programa, c["alfa"]).get(hid, {}).get("rechaza_h0", False))
    else:
        ok["holm"] = False; motivos.append("sin p-valores del programa: no se puede aplicar Holm")
    vec = [v for v in ev.get("sharpe_vecinos", []) if v is not None]
    ok["robustez_parametros"] = bool(vec) and np.mean(np.array(vec) > 0) >= c["vecinos_positivos_min"] and \
        np.median(vec) >= c["vecinos_ratio_mediana_min"] * m["sharpe"]
    ca, ce, sin_mejor = _cuotas(ev.get("pnl_por_activo", {}), ev.get("episodios"))
    ok["no_depende_de_un_activo"] = ca <= c["max_cuota_activo"] and sin_mejor > 0
    ok["no_depende_de_un_episodio"] = ce <= c["max_cuota_episodio"]
    ok["walk_forward_historico"] = (ev.get("wf_historico_sharpe") or 0) > 0
    detalle = {"punto_control": pc, "final": final, "z": z, "z_frontera": fr["z_frontera"], "dsr": d["dsr"],
               "sr0": d["sr0"], "N_pruebas": total_pruebas, "operaciones": nops, "cuota_activo": ca,
               "cuota_episodio": ce, "metricas": m, "metricas_costes_x2": m2, "cumple": ok}
    fallan = [k for k, v in ok.items() if not v]
    if not fallan:
        return {"clase": "APROBADA", "motivos": ["cumple todos los criterios pre-registrados"] + motivos,
                "criterios": detalle}
    if z < -1.645 or (info >= 0.5 and z < 0):
        return {"clase": "RECHAZADA", "motivos": [f"futilidad: z={z:.2f} con {info:.0%} de la información"]
                + [f"falla {k}" for k in fallan], "criterios": detalle}
    if final:
        if not ok["operaciones"]:
            return {"clase": "DATOS INSUFICIENTES", "motivos": [f"solo {nops} operaciones independientes "
                    f"(mínimo {c['min_operaciones']}) al final del periodo"] + [f"falla {k}" for k in fallan],
                    "criterios": detalle}
        return {"clase": "RECHAZADA", "motivos": ["último punto de control sin cumplir todos los criterios"]
                + [f"falla {k}" for k in fallan], "criterios": detalle}
    return {"clase": "DATOS INSUFICIENTES", "motivos": [f"punto de control intermedio ({pc} d): no cruza los "
            "criterios ni es fútil; se continúa"] + [f"falla {k}" for k in fallan], "criterios": detalle}


def evaluar_y_registrar(registro, hid, ev, pvalores_programa=None):
    """Clasifica y deja constancia en el registro (mirada siempre; cierre si la clase es definitiva)."""
    h = registro.hipotesis(hid)
    registro.comprobar_codigo(hid)
    res = clasificar(h, ev, registro.total_pruebas(), pvalores_programa)
    resumen = {"clase": res["clase"], "motivos": res["motivos"]}
    if res["criterios"]:
        cr = res["criterios"]
        resumen.update({k: (float(cr[k]) if isinstance(cr[k], (int, float, np.floating)) else cr[k])
                        for k in ("punto_control", "z", "z_frontera", "dsr", "N_pruebas", "operaciones")})
        resumen["cumple"] = {k: bool(v) for k, v in cr["cumple"].items()}
    registro.mirar(hid, int(ev["dias"]), resumen)
    if res["clase"] in ("APROBADA", "RECHAZADA"):
        registro.cerrar(hid, res["clase"], res["motivos"])
    return res
