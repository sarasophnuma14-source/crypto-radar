# Auditoría de D_volmom_L28 y preparación para paper trading

Fecha: 2026-11-15 · Rama `claude/paper-trading-volmom` (sale de `claude/project-thread-i8udp5`, commit 8868070).
El motor 2.0 (`radar/quant`) no se ha tocado. No se ha habilitado ninguna orden real.

## Resumen

1. **El holdout registrado no cambia.** D_volmom_L28 perdió **−22,93 %** (Sharpe −0,935, profit factor 0,68,
   drawdown −34,2 %). Se volvió a ejecutar el simulador v1 congelado y el resultado es idéntico: −22,93 % y 165
   operaciones. Las 5 estrategias congeladas dan también el mismo resultado.
2. **La implementación no cumplía la especificación de riesgo.** El tamaño por volatilidad ignoraba el límite de 0,5 %
   por operación: 134 de las 165 operaciones del holdout arriesgaron más de lo permitido. La media fue 0,96 % y el
   máximo 2,77 %.
3. **El simulador corregido (v2) tampoco encuentra ventaja.** En el periodo del holdout, ya visto y por tanto solo
   exploratorio, pierde **−13,05 %** (Sharpe −0,96, profit factor 0,67). El drawdown baja a −17,6 % porque ahora se
   arriesga menos. En Validación gana +2,89 % con Sharpe 0,27, por debajo del umbral de 0,75 que exigía el
   pre-registro.
4. **El paper trading está listo**, pero solo como medición. No hay base estadística para esperar que gane dinero.
   Cumple 2 de los 12 criterios de aceptación en el periodo del holdout.

## 1. Errores encontrados (Fase 1 y Fase 4)

"Confirmado" significa que se reprodujo con datos o con una prueba.

| # | Dónde | Error | Efecto | Corrección |
| --- | --- | --- | --- | --- |
| B1 | `run.py` | El holdout tenía una opción `--force` para repetirlo, y el candado estaba en `data/`, que git ignora. | Se podía repetir el holdout sin dejar rastro. | Se quitó `--force`. Ahora hay un registro `research/edge/ledger/ledger.jsonl` versionado y encadenado por hash. |
| B2 | `sim.py` v1 | El tamaño por volatilidad (`sizing="vol"`) no aplicaba el 0,5 % de riesgo por operación. | **Confirmado**: 134 de 165 operaciones de D superan el 0,5 %. Media 0,96 %, mediana 0,88 %, máximo 2,77 %. | `portfolio_risk.plan_entries` aplica el mínimo de todos los límites. |
| B3 | `sim.py` v1 | El "objetivo de volatilidad del 40 %" era una aproximación por activo (0,40/5/σ) que supone correlación 1. | La volatilidad realizada fue 11,1 % frente al 40 % de objetivo. El error es conservador, no peligroso. | El objetivo se aplica a la cartera con una matriz de covarianzas Ledoit-Wolf. |
| B4 | `sim.py` v1 | El tamaño y el límite del 15 % se calculaban con la apertura, no con el precio real de ejecución (apertura × (1 + coste)). | Exceso de tamaño pequeño, del orden del coste. | El tamaño se calcula con el precio de ejecución. |
| B5 | `sim.py` v1 | Para detectar retiradas se usaba el último índice de toda la serie, lo que es conocimiento del futuro. | Leve: el sistema "sabía" que una moneda iba a desaparecer. | Ahora se vende tras 3 días seguidos sin vela, al último cierre × (1 − descuento). |
| B6 | `sim.py` v1 | Un activo sin cierre se valoraba al precio de entrada si nunca había tenido marca. | Valoración ficticia posible. | Se valora al último cierre conocido, con un contador de marcas viejas (`stale_marks`). |
| B7 | `sim.py` v1 | El riesgo abierto de las posiciones abiertas ese mismo día usaba el cierre de D−1. | Riesgo abierto mal medido el día de entrada. | Se usa la marca actual, que es el precio de entrada el día en que se abre. |
| B8 | `requirements.txt` | Faltaban numpy y pandas. | `radar/edge` no se puede importar en un despliegue limpio. | Se fijaron numpy 2.5.3 y pandas 3.0.5. |
| B9 | `sim.py` v1 | El coste de una salida en la apertura de D usaba el ADV que incluye el volumen del propio día D. | Mirada al futuro mínima, solo en el tramo de coste. | Todas las ejecuciones de D usan el ADV hasta D−1. |
| B10 | `sim.py` v1 | El tamaño se decidía en la apertura con el capital del cierre anterior y no se registraba la orden. | Sin trazabilidad de las órdenes. | La orden se decide al cierre de D, se registra y se vuelve a acotar en la apertura de D+1. |
| B11 | panel de datos | **Dos monedas estables entraron en el universo**: PAX (Paxos, 2020-21) y U (2026), porque su ticker no contiene "USD". | Confirmado: D operó PAX 2 veces en Desarrollo (−6,5 USD). En el holdout, D no las tocó; otras familias operaron U 7 veces (todas pequeñas pérdidas). | `data.drop_stables()` las quita en v2 y en paper trading, con un filtro de volatilidad mínima del 5 % anual. `build()` no cambia, para que v1 sea reproducible. |

Revisado y correcto, sin cambios:

- **Sin doble uso del efectivo.** Cada ejecución resta su efectivo antes de la siguiente (prueba `test_simultaneous_orders_no_double_use_of_cash`).
- **Las órdenes pendientes no superan la exposición permitida.** Se planifican juntas con las posiciones que se mantienen y se vuelven a acotar al llenarse (`open_risk_after_pct` ≤ 3 %, `gross_after_pct` ≤ 100 %).
- **Costes de entrada y salida** descontados una vez cada uno: el resultado es lo cobrado menos lo pagado (prueba `test_size_uses_real_execution_price_and_costs`).
- **Ejecución.** Entrada en la apertura de D+1. Se cancela si la apertura supera el cierre de la señal en más de 1 ATR. Si hay un hueco bajo el stop, se vende a la apertura. El stop se comprueba también el día de entrada. Las ejecuciones parciales se modelan como un tamaño recortado por el límite del 1 % del ADV o por el efectivo.
- **Sin información futura en los indicadores.** Un cambio en los datos posteriores a t no cambia nada hasta t (prueba `test_no_lookahead_future_data_does_not_change_past`).

Pendiente de nota (sin cambios):

- Cada subperiodo se simula con el capital reiniciado.
- No hay datos sectoriales fiables, así que la concentración por sector queda como N/D.

## 2. Control del holdout (Fase 2)

- `research/edge/ledger/ledger.jsonl` es un registro al que solo se añade, versionado en git. Cada línea lleva:
  - `run_id` (uuid4), fecha y hora UTC;
  - commit de git, hash del código (`radar/edge/*.py` y `run.py`) y hash de los datos;
  - parámetros y resultados;
  - el hash de la línea anterior. Si se edita o borra una línea, `ledger.verify()` lo detecta.
- Tipos de entrada:
  - `final_holdout`: solo puede haber una;
  - `holdout_attempt_refused`: intentos de repetir el holdout;
  - `reproduction`: comprobaciones de reproducibilidad, que no son un holdout nuevo;
  - `exploratory`: no es evidencia independiente.
- La entrada original se reconstruyó con `research/edge/seed_ledger.py` y lleva `seeded_retroactively: true`. Contiene:
  - hora original 2026-11-15T03:55:17Z;
  - commit 8868070 y el hash del código de ese commit, calculado con `git show`;
  - el sha256 de `holdout_results.json`.
- `python3 research/edge/run.py holdout` se niega, registra el intento y no carga datos. Nada en el código permite saltarse el bloqueo.
- `run.py reproduce` vuelve a ejecutar el v1 congelado (`sim_v1.py`, byte a byte igual que el de 8868070) y compara con lo registrado. Resultado: idéntico en las 5 estrategias.
- `run.py explore <dev|val|holdout> <v1|v2>` sirve para los experimentos. En el periodo del holdout se etiqueta como "ya visto".
- Contenido actual del registro, sin ninguna línea borrada:
  - 1 `final_holdout`;
  - 2 `reproduction` (ambas idénticas);
  - 2 `exploratory` (la auditoría, ejecutada dos veces con resultados idénticos);
  - 3 `holdout_attempt_refused`. Uno es la demostración final. Los otros dos (07:32 y 07:34 UTC, ejecutados desde `research/edge`) no los lancé yo de forma consciente en esta sesión. El bloqueo los rechazó sin ejecutar nada y quedan a la vista.

## 3. Riesgo de cartera (`radar/edge/portfolio_risk.py`)

Los parámetros se fijaron antes de cualquier ejecución del v2 y ninguno se eligió por su resultado.

| Parámetro | Valor | Para qué |
| --- | --- | --- |
| Ventana de covarianzas | 90 días, mínimo 60 observaciones comunes | Solo datos hasta el cierre de D |
| Estimador | Ledoit-Wolf sobre la correlación (hacia la identidad) y volatilidades muestrales | Matriz siempre definida positiva |
| Estabilidad | Condición de la correlación ≤ 1 000. Si no se cumple, no hay entrada | Matrices casi singulares |
| Volatilidad mínima por activo | 5 % anual | Monedas estables o datos rotos |
| Objetivo de volatilidad | 40 % anual (techo de riesgo), × 0,5 si BTC está bajo su SMA200 | Riesgo agregado |
| Freno | Sin entradas si la volatilidad realizada a 30 días supera 1,5 × el objetivo | Volatilidad de la cartera |
| Límites duros | 0,5 % de riesgo por operación (× 0,5 en mercado bajista), 15 % por activo, 5 posiciones, 3 % de riesgo abierto, exposición ≤ 100 % | Los originales, como máximos |
| Datos insuficientes o matriz no fiable | No se abre la posición. Se registra el motivo | |

Dos ajustes se hicieron tras la primera ejecución en **Desarrollo**. Ninguno se eligió por su efecto en el resultado.

- **Condición de la matriz.** Primero se medía sobre la covarianza (límite 1e4), y dependía de la escala de las volatilidades. Ahora se mide sobre la correlación.
- **Filtro de volatilidad mínima.** Se añadió porque esa ejecución destapó B11: PAX tenía un 1 % de volatilidad.

Lo que pasa en la práctica:

- El límite que manda casi siempre es el **0,5 % por operación**. Con un stop de 3 ATR, deja posiciones de un 2-4 % del capital.
- La volatilidad realizada queda en un 6-8 % anual, muy por debajo del 40 %. El objetivo de volatilidad casi nunca actúa.

## 4. Estadística (Fase 5)

Fuente: `research/edge/audit/estadistica_auditoria.json`, generado con `python3 research/edge/audit_stats.py`.

### A. Holdout registrado (v1), re-analizado sin volver a simular

| | D_volmom_L28 |
| --- | --- |
| Retorno neto / Sharpe / PF / DD | −22,93 % / −0,935 / 0,68 / −34,2 % |
| Costes ×2 | −25,61 % (PF 0,65) |
| Costes ×3 y descuento por retirada del 30 % | −28,90 % (PF 0,61) |
| Subperiodos | 2024-S2 +12,79 %, 2025 −11,34 %, 2026 −23,35 % |
| Régimen BTC ≥ SMA200 | −4,88 % en 463 días |
| Régimen BTC < SMA200 | −18,98 % en 403 días |
| p-valor (media > 0), bootstrap estacionario y circular, bloques de 10/20/30/60 días | entre 0,874 y 0,895 |
| IC 90 % del Sharpe | entre [−2,39; 0,29] y [−2,31; 0,44] según el método. Siempre incluye el 0 y es mayoritariamente negativo |
| Holm (5 congeladas) / Bonferroni (5) / Bonferroni (23) | 1,0 / 1,0 / 1,0 |
| BTC comprar y mantener | +1,99 % (Sharpe 0,24, DD −53 %) |
| ETH comprar y mantener | −48,6 % |
| Efectivo | 0 % |
| Criterios de aceptación | 1 de 12. **NO CUMPLE** |

### B. Simulador v2 corregido

| Periodo | Retorno | Sharpe | PF | DD máx. | Operaciones | Vol. realizada | Costes ×2 | Costes ×3 | p (rango de los 8 bootstraps) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Desarrollo 2020-2022 (dentro de muestra) | +47,15 % | 1,68 | 2,32 | −8,2 % | 255 | 7,9 % | +42,6 % | +40,3 % | 0,008 – 0,049 |
| Validación 2023-24/06 | +2,89 % | 0,27 | 1,12 | −7,8 % | 169 | 8,5 % | +0,76 % | −1,76 % | 0,33 – 0,35 |
| Periodo del holdout 2024/07-2026/11 (**exploratorio, ya visto**) | **−13,05 %** | −0,96 | 0,67 | −17,6 % | 277 | 5,9 % | −14,6 % | −16,1 % | 0,93 – 0,96 |

- En el periodo del holdout, v2 tiene subperiodos de +3,11 %, −6,40 % y −9,95 %.
- Por régimen: −4,49 % con BTC alcista y −8,96 % con BTC bajista.
- BTC hizo +1,99 % y el efectivo 0 %.
- El patrón es el mismo que antes: funciona en Desarrollo, apenas en Validación y pierde después.
- La corrección de riesgo reduce pérdidas y drawdown, pero **no crea una ventaja**. No se cambió ningún parámetro a la vista de estos números.

## 5. Archivos

**Modificados**
- `radar/edge/sim.py`: ahora es el simulador v2, una clase `Engine` con estado indexado por símbolo que se puede guardar.
- `radar/edge/data.py`: `STABLE_EXTRA`, `drop_stables()` y `panel_from_raw()`. `build()` no cambia.
- `radar/edge/stats.py`: bootstrap circular, `bootstrap_test`, `block_sensitivity` y `bonferroni`. Lo anterior no cambia.
- `research/edge/run.py`: sin `--force`, con el registro, `reproduce`, `explore` y BLAS en un hilo.
- `main.py`: comando `paper`.
- `radar/server.py` y `radar/webapi.py`: `GET /api/paper/report` y una tarea diaria opcional con `PAPER_TRADING=1`.
- `requirements.txt`.

**Nuevos**
- `radar/edge/sim_v1.py`: copia congelada del simulador del holdout.
- `radar/edge/ledger.py` y `radar/edge/portfolio_risk.py`.
- `radar/paper_trading/`: `__init__`, `engine`, `portfolio`, `execution`, `storage`, `metrics` y `report`.
- `research/edge/seed_ledger.py`, `research/edge/audit_stats.py` y `research/edge/ledger/ledger.jsonl`.
- `research/edge/audit/`: el JSON de estadística y los CSV de curvas y operaciones de v2.
- `tests/test_paper.py`.

## 6. Pruebas ejecutadas (todas se ejecutaron en esta sesión)

| Archivo | Resultado |
| --- | --- |
| `python3 tests/test_paper.py` | **39 pruebas, OK** |
| `python3 tests/test_edge.py` (ahora contra v2) | **29 pruebas, OK** |
| `TEST_DATABASE_URL=… python3 tests/test_suite.py` (PostgreSQL local) | **158 pruebas, OK** |
| `run.py reproduce` | v1 idéntico al registrado en las 5 estrategias |
| `run.py holdout` | rechazado y registrado |
| `main.py paper init smoke-test` contra Binance en vivo | 496 pares descargados, 0 errores, primer día 2026-11-14 procesado, universo de 108 monedas |
| Replay histórico frente al backtest | curvas idénticas día a día (diferencia máxima 0,0) |

`test_paper.py` cubre:
- ausencia de mirada al futuro;
- covarianza (definida positiva, datos insuficientes, colinealidad, series constantes, monedas estables);
- control de volatilidad, freno y reducción en mercado bajista;
- límites de exposición, capital insuficiente y órdenes simultáneas;
- huecos (bajo el stop y al alza), stops intradía, retiradas sin futuro y datos incompletos;
- persistencia (procesar de forma incremental da lo mismo que de una vez, y la cadena de hashes detecta manipulación);
- protección del holdout (rechazo, registro, ediciones y borrados detectados, sin `force`);
- reproducibilidad, especificación congelada y ausencia de órdenes reales.

## 7. Cambios de arquitectura

- El simulador pasa de un bucle cerrado a `sim.Engine.step(state, t)`. El backtest (`simulate`) y el paper trading usan **el mismo código** para señales, tamaño y ejecución.
- `portfolio_risk` es independiente y se puede probar por separado.
- El paper trading guarda:
  - `spec.json`: congelado, con el hash del código que decide;
  - `state.json`: escritura atómica;
  - tres diarios a los que solo se añade, encadenados por hash: `events`, `trades` y `equity`.
- Con `DATABASE_URL`, todo se guarda en la tabla kv de PostgreSQL. Las velas van a un caché en archivo que se puede reconstruir.
- La investigación queda separada en `final_holdout`, `reproduction` y `exploratory` dentro de un registro versionado.

## 8. Cómo iniciar el paper trading

```bash
pip install -r requirements.txt
python3 main.py paper init principal     # congela la especificación y descarga ~500 pares (≈ 8 min la primera vez)
python3 main.py paper step principal     # cada día después de las 00:00 UTC (cron: 20 0 * * *)
python3 main.py paper report principal   # métricas, comparación con BTC y efectivo, criterios
```

- **En el servidor (Render)** define `PAPER_TRADING=1`, más `DATABASE_URL` para que el diario sobreviva a los despliegues. El proceso ejecuta el paso a las 00:20 UTC y el panel lo lee en `GET /api/paper/report`.
- **En un ordenador propio**, programa `paper step` con cron o con el Programador de tareas de Windows.
- **Si se salta un día**, el siguiente paso procesa en orden todos los días pendientes. Si a un día le faltan datos (BTC sin vela o menos del 90 % de los pares), no se procesa y se reintenta en el siguiente paso.
- **Si cambia el código que decide** (estrategia, indicadores, simulador, riesgo o datos), `step` se niega a continuar. Hay que abrir otra evaluación con otro nombre. Así no se puede "mejorar" la estrategia a mitad de la prueba.
- **Duración mínima: 183 días.** Antes de eso el informe dice "EN CURSO".

## 9. Ejemplo de registro de una operación

Sale del replay histórico (`main.py paper replay 2024-07-01 2026-11-14`). **No es paper trading prospectivo.**

```json
{"date": "2024-07-21", "type": "signal", "symbol": "RAY", "score": 0.6588}
{"date": "2024-07-21", "type": "order", "symbol": "RAY", "value": 238.99}
{"date": "2024-07-22", "type": "fill", "symbol": "RAY", "px": 2.6895445, "qty": 88.8537, "value": 238.976,
 "stop": 2.1216, "limit": "riesgo por operación", "risk_pct_equity": 0.5, "open_risk_after_pct": 2.52, "gross_after_pct": 8.80}
{"date": "2024-07-23", "type": "exit", "symbol": "RAY", "reason": "Stop", "px": 2.1152494, "pnl_usd": -51.03}
```

Operación cerrada (`trades.jsonl`):
- entrada a 2,6815 de apertura, 2,6895 con costes; salida en el stop a 2,1216, 2,1152 con costes;
- 88,85 unidades: pagados 238,98 USD, cobrados 187,95 USD; resultado −51,03 USD (−1,01 R);
- riesgo 50,46 USD (0,50 % del capital); comisiones 0,71 USD a la entrada y 0,57 USD a la salida;
- cada línea lleva `_prev` con el hash de la línea anterior.

## 10. Riesgos pendientes

1. **No hay ventaja demostrada.** Lo más probable es que el paper trading pierda poco a poco (−5 % a −6 % al año en el periodo del holdout con v2). Vale como medición honesta, no como fuente de ingresos.
2. Seis meses son pocos: con un Sharpe real de 0, el error típico del Sharpe anualizado medido en 183 días es ≈ 1,4, así que puede salir entre −2,8 y +2,8 (95 %) por puro azar. Un resultado positivo a 6 meses **no** bastaría para cumplir el criterio estadístico.
3. **Datos.** Solo hay una fuente (Binance). Si data-api.binance.vision falla, no se procesa el día. No hay datos sectoriales.
4. El universo en vivo tiene ~108 monedas con ADV ≥ 2 M$ (el umbral de 150 no se llena). Es coherente con la regla, pero distinto en tamaño del periodo histórico.
5. Los costes son un modelo por tramos de ADV, sin libro de órdenes. Como las posiciones son pequeñas (≈ 240 USD con 10 000 USD de capital), el impacto real debería ser menor que el modelado.
6. El caché de velas de Render se borra en cada despliegue. Se reconstruye solo, en unos 8 minutos.
7. El registro del holdout se reconstruyó después del holdout original (marcado como tal). La garantía fuerte empieza ahora.

## 11. Confirmación

**No se ha habilitado ninguna orden real.**
- `radar/paper_trading` no contiene claves de API, firmas ni llamadas a endpoints de órdenes.
- `REAL_ORDERS_ENABLED = False`, y `execution.place_real_order()` lanza un error siempre.
- La especificación guarda `"real_orders": false`.
- La prueba `test_no_real_orders` lo comprueba.

Ni el holdout original ni el motor 2.0 se han modificado, y no se ha borrado ninguna operación perdedora.
