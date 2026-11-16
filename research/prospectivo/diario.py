"""Diario de señales de paper trading (prospectivo), append-only y encadenado por SHA-256.

Cada señal se escribe ANTES de que exista el resultado que intenta predecir:
  creada_utc  instante real en que se escribió la línea (reloj del sistema, no el de los datos)
  barra       apertura de la barra cuyo CIERRE es el último dato usado (la decisión)
  ejecutar_en apertura de la barra en que se ejecutaría (barra + latencia)
Reglas: creada_utc ≥ available_at de la barra de decisión (no se pudo calcular antes) y creada_utc < ejecutar_en
(se escribió antes de que la ejecución fuera posible). Una señal que llega tarde se conserva pero se marca y se trata
como NO ejecutada: nunca se rellena a posteriori. Este diario es NUEVO y no toca el ledger de research/edge/ledger/.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import numpy as np
import pandas as pd
from .registro import _canon, _now, Registro, RegistroError


class DiarioError(RuntimeError):
    pass


class Diario:
    def __init__(self, path, registro: Registro | None = None, reloj=_now):
        self.path = Path(path); self.registro = registro; self.reloj = reloj
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def lineas(self):
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def verify(self):
        prev = "0" * 64
        for i, r in enumerate(self.lineas()):
            body = {k: v for k, v in r.items() if k != "hash"}
            if r["seq"] != i or r["prev"] != prev or hashlib.sha256(_canon(body).encode()).hexdigest() != r["hash"]:
                raise DiarioError(f"cadena rota en la línea {i}: el diario fue modificado")
            prev = r["hash"]
        return True

    def senal(self, hid, barra, disponible_en, ejecutar_en, pesos: dict, contexto: dict | None = None):
        if self.registro is not None:
            h = self.registro.hipotesis(hid)
            if h is None:
                raise DiarioError(f"la hipótesis {hid} no está registrada: no se admiten señales sin pre-registro")
            if self.registro.cerrada(hid):
                raise DiarioError(f"la hipótesis {hid} está cerrada")
            self.registro.comprobar_codigo(hid)
        self.verify()
        ls = self.lineas()
        creada = self.reloj()
        tc, td, te = pd.Timestamp(creada), pd.Timestamp(disponible_en), pd.Timestamp(ejecutar_en)
        if tc < td:
            raise DiarioError("la señal se escribe antes de que su dato estuviera disponible: reloj o datos erróneos")
        body = {"seq": len(ls), "creada_utc": creada, "id": hid, "barra": pd.Timestamp(barra).isoformat(),
                "disponible_en": td.isoformat(), "ejecutar_en": te.isoformat(),
                "pesos": {k: float(v) for k, v in pesos.items()}, "contexto": contexto or {},
                "a_tiempo": bool(tc < te), "prev": ls[-1]["hash"] if ls else "0" * 64}
        rec = dict(body, hash=hashlib.sha256(_canon(body).encode()).hexdigest())
        with self.path.open("a") as f:
            f.write(_canon(rec) + "\n")
        return rec

    def pesos(self, hid, columnas=None):
        """Reconstruye la matriz de pesos (por barra de decisión) solo con las señales escritas a tiempo."""
        self.verify()
        rs = [r for r in self.lineas() if r["id"] == hid and r["a_tiempo"]]
        if not rs:
            return pd.DataFrame(columns=columnas or [])
        df = pd.DataFrame([r["pesos"] for r in rs], index=pd.DatetimeIndex([r["barra"] for r in rs]))
        df = df[~df.index.duplicated(keep="first")]      # la primera señal manda: no se corrige una señal escrita
        return df.reindex(columns=columnas).fillna(0.0) if columnas else df.fillna(0.0)

    def resumen(self, hid):
        rs = [r for r in self.lineas() if r["id"] == hid]
        return {"senales": len(rs), "a_tiempo": sum(r["a_tiempo"] for r in rs),
                "tardias": sum(not r["a_tiempo"] for r in rs),
                "primera": rs[0]["barra"] if rs else None, "ultima": rs[-1]["barra"] if rs else None}
