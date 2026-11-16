"""Registro de hipótesis append-only, encadenado por SHA-256. Se escribe ANTES de probar nada.

Cada línea del archivo JSONL es {seq, ts_utc, tipo, id, payload, prev, hash}. Tipos:
  hipotesis  alta de una hipótesis (campos obligatorios en CAMPOS)
  enmienda   cambio de una hipótesis: reinicia el reloj prospectivo y suma sus pruebas al total
  mirada     cada vez que se evalúa con datos prospectivos (cuenta para el reparto del error)
  cierre     clasificación final (APROBADA / RECHAZADA / DATOS INSUFICIENTES)
No hay borrado ni edición: verify() detecta cualquier cambio en una línea anterior.
"""
from __future__ import annotations
import datetime as dt, hashlib, itertools, json, math
from pathlib import Path
from . import CORTE_PROSPECTIVO, PRUEBAS_PREVIAS

CAMPOS = ("id", "linea", "hipotesis", "autor", "datos", "universo", "reglas_entrada", "reglas_salida", "parametros",
          "modelo_costes", "frecuencia", "metrica_principal", "criterios", "puntos_control_dias", "codigo")
TIPOS = ("hipotesis", "enmienda", "mirada", "cierre")
CLASES = ("APROBADA", "RECHAZADA", "DATOS INSUFICIENTES")


class RegistroError(RuntimeError):
    pass


def _canon(o):
    return json.dumps(o, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def n_pruebas(parametros: dict) -> int:
    """Número de configuraciones de la rejilla (producto de los tamaños). Una rejilla vacía cuenta como 1."""
    if not parametros:
        return 1
    for k, v in parametros.items():
        if not isinstance(v, list) or not v:
            raise RegistroError(f"el parámetro {k} debe ser una lista finita y no vacía")
    return math.prod(len(v) for v in parametros.values())


def hash_archivo(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Registro:
    def __init__(self, path, root=None, reloj=_now):
        self.path = Path(path); self.root = Path(root) if root else self.path.parent; self.reloj = reloj
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- lectura y verificación
    def lineas(self):
        if not self.path.exists():
            return []
        return [json.loads(x) for x in self.path.read_text().splitlines() if x.strip()]

    def verify(self):
        prev = "0" * 64
        for i, r in enumerate(self.lineas()):
            body = {k: r[k] for k in ("seq", "ts_utc", "tipo", "id", "payload", "prev")}
            if r["seq"] != i or r["prev"] != prev or hashlib.sha256(_canon(body).encode()).hexdigest() != r["hash"]:
                raise RegistroError(f"cadena rota en la línea {i}: el registro fue modificado")
            prev = r["hash"]
        return True

    def _append(self, tipo, hid, payload):
        if tipo not in TIPOS:
            raise RegistroError(f"tipo desconocido: {tipo}")
        self.verify()
        ls = self.lineas()
        body = {"seq": len(ls), "ts_utc": self.reloj(), "tipo": tipo, "id": hid, "payload": payload,
                "prev": ls[-1]["hash"] if ls else "0" * 64}
        rec = dict(body, hash=hashlib.sha256(_canon(body).encode()).hexdigest())
        with self.path.open("a") as f:
            f.write(_canon(rec) + "\n")
        return rec

    # ---------------------------------------------------------------- operaciones
    def registrar(self, h: dict):
        falt = [c for c in CAMPOS if c not in h]
        if falt:
            raise RegistroError(f"faltan campos obligatorios: {', '.join(falt)}")
        if self.hipotesis(h["id"]) is not None:
            raise RegistroError(f"la hipótesis {h['id']} ya existe: usa una enmienda")
        cod = self.root / h["codigo"]
        if not cod.exists():
            raise RegistroError(f"el código {h['codigo']} no existe: se registra con el código ya escrito")
        pc = h["puntos_control_dias"]
        if not pc or sorted(pc) != pc or pc[0] <= 0:
            raise RegistroError("puntos_control_dias debe ser una lista creciente de días > 0")
        p = dict(h, n_pruebas=n_pruebas(h["parametros"]), codigo_sha256=hash_archivo(cod))
        rec = self._append("hipotesis", h["id"], p)
        # el reloj prospectivo empieza al registrar (y nunca antes del corte global)
        rec["payload"]["inicio_prospectivo"] = max(rec["ts_utc"], CORTE_PROSPECTIVO)
        return rec

    def enmendar(self, hid, cambios: dict, motivo: str):
        if self.hipotesis(hid) is None:
            raise RegistroError(f"no existe la hipótesis {hid}")
        if self.cerrada(hid):
            raise RegistroError(f"la hipótesis {hid} ya está cerrada")
        if "codigo" in cambios:
            cambios = dict(cambios, codigo_sha256=hash_archivo(self.root / cambios["codigo"]))
        if "parametros" in cambios:
            cambios = dict(cambios, n_pruebas=n_pruebas(cambios["parametros"]))
        return self._append("enmienda", hid, {"cambios": cambios, "motivo": motivo})

    def mirar(self, hid, dia_prospectivo: int, resumen: dict):
        if self.hipotesis(hid) is None:
            raise RegistroError(f"no existe la hipótesis {hid}")
        return self._append("mirada", hid, {"dia": dia_prospectivo, "resumen": resumen})

    def cerrar(self, hid, clase: str, motivos: list):
        if clase not in CLASES:
            raise RegistroError(f"clase inválida: {clase}")
        if self.cerrada(hid):
            raise RegistroError(f"la hipótesis {hid} ya está cerrada")
        return self._append("cierre", hid, {"clase": clase, "motivos": motivos})

    # ---------------------------------------------------------------- consultas
    def hipotesis(self, hid):
        """Estado vigente: alta + enmiendas aplicadas en orden. inicio_prospectivo = última alta o enmienda."""
        cur = None
        for r in self.lineas():
            if r["id"] != hid:
                continue
            if r["tipo"] == "hipotesis":
                cur = dict(r["payload"]); cur["inicio_prospectivo"] = max(r["ts_utc"], CORTE_PROSPECTIVO)
                cur["n_pruebas_acumuladas"] = cur["n_pruebas"]; cur["enmiendas"] = 0
            elif r["tipo"] == "enmienda" and cur is not None:
                cur.update(r["payload"]["cambios"]); cur["enmiendas"] += 1
                cur["inicio_prospectivo"] = max(r["ts_utc"], CORTE_PROSPECTIVO)   # el reloj vuelve a cero
                cur["n_pruebas_acumuladas"] += r["payload"]["cambios"].get("n_pruebas", 1)
        return cur

    def miradas(self, hid):
        return [r for r in self.lineas() if r["id"] == hid and r["tipo"] == "mirada"]

    def cerrada(self, hid):
        return any(r["id"] == hid and r["tipo"] == "cierre" for r in self.lineas())

    def total_pruebas(self):
        """Pruebas acumuladas de TODO el programa (anteriores + todas las hipótesis y enmiendas): N del DSR."""
        ids = {r["id"] for r in self.lineas() if r["tipo"] == "hipotesis"}
        return PRUEBAS_PREVIAS + sum(self.hipotesis(i)["n_pruebas_acumuladas"] for i in ids)

    def comprobar_codigo(self, hid):
        """El código de una hipótesis no puede cambiar sin enmienda."""
        h = self.hipotesis(hid)
        if hash_archivo(self.root / h["codigo"]) != h["codigo_sha256"]:
            raise RegistroError(f"el código de {hid} cambió desde su registro: registra una enmienda")
        return True
