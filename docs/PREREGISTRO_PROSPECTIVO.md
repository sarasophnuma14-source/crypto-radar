# Pre-registro prospectivo: proceso, plantilla y criterios

Vigente desde 2026-11-16. Este documento fija **antes de ver ningún dato prospectivo** cómo se registra, se evalúa y se clasifica cualquier hipótesis nueva. Cambiarlo después cuenta como una enmienda general: hay que anotarla con fecha y motivo al final del documento, y no se aplica a las hipótesis ya registradas.

## 1. Principios

1. Todo dato anterior al **2026-11-16T00:00Z** (`CORTE_PROSPECTIVO`) ya se ha visto. Sirve para explorar y desarrollar, nunca para confirmar.
2. Una hipótesis se registra **con el código ya escrito**. Al registrarla se guarda el SHA-256 de su archivo, y su reloj prospectivo empieza en ese instante.
3. **Rejilla de parámetros:** debe ser finita y declarada. Su tamaño se suma al N global del DSR (58 pruebas anteriores: 23 de v1 + 35 de v3).
4. **Enmiendas:** cualquier cambio (código, parámetros, universo, reglas, costes) es una enmienda. Pone el reloj prospectivo a cero y suma sus pruebas. No hay ediciones silenciosas: el registro es append-only y está encadenado por hash.
5. **Puntos de control:** solo se mira en los pre-registrados (por defecto 90, 183 y 365 días). Cada mirada queda escrita.
6. **Señales:** las de paper trading se escriben en el diario antes de su ejecución. Las tardías no cuentan.

## 2. Plantilla (campos obligatorios de `registro.CAMPOS`)

```python
from prospectivo.registro import Registro
reg = Registro("research/prospectivo/registro/registro.jsonl", root="research/prospectivo")
reg.registrar({
  "id": "P01_momentum_intradia_4h",          # único; no se reutiliza nunca
  "linea": "momentum intradía / multi-marco", # una de las líneas de MATRIZ_DE_ESTRATEGIAS.md
  "hipotesis": "texto falsable: qué efecto, por qué existiría, qué lo anularía",
  "autor": "…",
  "datos": "binance spot klines 4h (archivo), funding UM; available_at = cierre + 2 s",
  "universo": "point-in-time: top 20 por notional 30 d, historia ≥ 180 d, sin stablecoins",
  "reglas_entrada": "…", "reglas_salida": "…",
  "parametros": {"L": [6, 12, 24]},           # rejilla finita: n_pruebas = 3
  "modelo_costes": "ModeloCostes('binance_spot', ejecucion='taker', latencia_barras=1) y ×2",
  "frecuencia": "4h",
  "metrica_principal": "sharpe_exceso_efectivo",
  "criterios": {"min_operaciones": 30},       # solo puede ENDURECER los de §4
  "puntos_control_dias": [90, 183, 365],
  "codigo": "estrategias/p01_momentum_4h.py",
})
```

## 3. Datos y referencias obligatorias

- **Evidencia:** solo barras con `available_at` ≥ inicio prospectivo (`guardia.exigir_prospectivo`).
- **Referencias de comparación**, en el mismo periodo y con el mismo motor y los mismos costes:
  - BTC comprar y mantener;
  - efectivo remunerado (FRED DTB3);
  - D_volmom congelada (paper trading existente, sin tocar).
- **Costes:** los de `costes.py`, verificando las comisiones del exchange en la fecha del registro, más una prueba de estrés ×2.

## 4. Criterios de aceptación (por defecto, fijados hoy)

Una hipótesis es **APROBADA** solo si, en un punto de control pre-registrado, se cumplen **todos** estos criterios:

| # | Criterio | Umbral |
|---|---|---|
| 1 | Guardias | Pasa la de anticipación, la de fugas, la de supervivencia y la de solo datos prospectivos |
| 2 | Días prospectivos | ≥ 90 y en un punto de control |
| 3 | Operaciones independientes (episodios) | ≥ 30 |
| 4 | Significación secuencial | z (Sharpe en exceso sobre el efectivo) ≥ frontera O'Brien-Fleming: 3,78 / 2,54 / 1,70 |
| 5 | Costes realistas | Neto de costes; y con costes ×2, Sharpe en exceso > 0 y retorno > efectivo |
| 6 | Supera al efectivo | Retorno total > retorno del efectivo remunerado |
| 7 | Supera a BTC | Sharpe y retorno total mayores que BTC comprar y mantener |
| 8 | Pruebas múltiples (DSR) | DSR ≥ 0,95 con N = `total_pruebas()` |
| 9 | Pruebas múltiples (Holm) | Holm al 5 % entre todas las hipótesis evaluadas en la misma ronda (BH se informa) |
| 10 | Robustez de parámetros | ≥ 75 % de los vecinos de la rejilla con Sharpe > 0, y mediana de los vecinos ≥ 50 % del Sharpe elegido |
| 11 | Sin dependencia de un activo | El mejor activo aporta ≤ 50 % del PnL positivo, y sin él el PnL sigue > 0 |
| 12 | Sin dependencia de un episodio | El mejor episodio aporta ≤ 30 % del PnL total |
| 13 | Coherencia histórica | Walk-forward en el histórico explorado con Sharpe neto > 0 (condición necesaria, nunca suficiente) |

**RECHAZADA** en cualquiera de estos casos:
- falla una guardia;
- futilidad: z < 0 con ≥ 50 % de la información, o z < −1,645 en cualquier punto;
- se llega al último punto de control sin cumplir todos los criterios.

**DATOS INSUFICIENTES** en cualquiera de estos casos:
- antes del primer punto de control;
- en un punto intermedio que no aprueba y no es fútil (se continúa);
- al final, con menos operaciones independientes de las exigidas.

La implementación exacta está en `research/prospectivo/clasificacion.py`, y sus pruebas en `tests/test_prospectivo.py::TestClasificacion`.

## 5. Qué permite una APROBADA

- Permite implementarla en una **rama experimental** y seguir en paper trading.
- **No** permite usar dinero real, cambiar el motor actual ni sustituir a D_volmom. Para eso hace falta una autorización explícita de PATRON, con el informe delante.

## 6. Hipótesis registradas

Ninguna a fecha 2026-11-16. Las líneas candidatas y lo que necesita cada una están en `MATRIZ_DE_ESTRATEGIAS.md`.

## 7. Enmiendas a este documento

(ninguna)
