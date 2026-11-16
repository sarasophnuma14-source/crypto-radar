# Informe de investigación cuantitativa prospectiva

Fecha: 2026-11-16. Rama: `claude/investigacion-prospectiva` (sale de `claude/investigacion-edge`). Código: `research/prospectivo/`.

## 1. Resumen

- **No hay ninguna estrategia aprobada.** La ronda v3 terminó en **NO EDGE** (35 configuraciones, 8 familias, reserva final usada una vez; ver `DECISION_FINAL_EDGE.md`). Este informe no cambia ese resultado.
- Ya no queda ninguna muestra histórica sin ver: todo el histórico diario hasta el 2026-11-14 se ha usado para explorar o validar. Por eso, a partir de ahora, **una ventaja solo puede confirmarse con datos posteriores a su registro** (prospectivos).
- Esta fase entrega la **infraestructura** para hacerlo bien:
  - registro previo encadenado por hash;
  - guardias contra anticipación, fugas y supervivencia;
  - adaptadores de datos de cuatro exchanges y FRED;
  - modelo de costes, motor multi-frecuencia y estadística completa;
  - diario de señales de paper trading y clasificación automática.
  En total, 43 pruebas sin red, en verde en Python 3.12 y 3.13.
- Todas las líneas de investigación quedan en **DATOS INSUFICIENTES** (ver `MATRIZ_DE_ESTRATEGIAS.md`). La primera decisión posible es a los 90 días de registrar cada hipótesis, y solo si el efecto es muy grande. Lo normal es esperar a los 183 o 365 días.
- Nada de esto toca el motor actual, D_volmom, el paper trading existente, el ledger ni la plataforma.

## 2. Aislamiento (comprobado)

| Restricción | Cómo se cumple |
|---|---|
| No modificar el motor actual | `research/prospectivo/` no importa `radar/*` ni `research/edge*`. El diff de la rama solo añade archivos nuevos. |
| No alterar paper trading ni ledger | El diario es un archivo nuevo, y las rutas las elige quien lo use. `research/edge/ledger/ledger.jsonl` no se abre. |
| D_volmom congelada | Sigue en `research/edge3/benchmark/` con su SHA256SUMS, sin cambios. |
| No reutilizar la reserva final anterior | `guardia.VENTANAS_CONSUMIDAS` marca el holdout v1, el holdout v3, la validación v3 y todo el histórico explorado. `exigir_prospectivo` rechaza cualquier barra anterior al registro o a `CORTE_PROSPECTIVO` = 2026-11-16. |
| No eliminar datos | La caché `data/prospectivo/` solo añade archivos, nunca sobrescribe, y lleva un manifiesto SHA-256. |
| Sin dinero real | No hay ningún conector de órdenes. Solo se leen datos públicos. |

## 3. Diseño del módulo

| Módulo | Función |
|---|---|
| `registro.py` | JSONL append-only encadenado por SHA-256 (tipos: hipótesis, enmienda, mirada, cierre). **Campos obligatorios:** fecha, datos, universo, reglas de entrada y salida, rejilla finita de parámetros, costes, frecuencia, métrica principal, criterios, puntos de control y código. **Al registrar:** se exige que el código exista, y se guarda su hash. **Una enmienda:** pone a cero el reloj prospectivo y suma sus pruebas al N global. **Verificación:** `verify()` detecta cualquier edición o borrado. |
| `guardia.py` | **Ventanas consumidas:** detecta solapes con ellas. **Solo datos prospectivos:** rechaza lo anterior al registro. **Anticipación:** prueba genérica por truncado; detecta `shift(-1)` y medias de toda la muestra. **Fugas:** `available_at > decision_at`. **Supervivencia:** activos elegibles antes del listado o después del deslistado, o un universo que omite los deslistados. |
| `datos.py` | Esquema común con `available_at` (cierre de barra más 2 s). **Binance (archivo):** klines spot/perp de 1 m a 1 d, con marcas en ms y µs; aggTrades y desequilibrio de flujo de órdenes; funding; bookDepth (desequilibrio del libro a ±1–5 %); metrics (interés abierto). **Otros exchanges:** Coinbase; Kraken (descarta la barra en curso); OKX (solo barras confirmadas). **Efectivo y universo:** FRED DTB3 como efectivo remunerado, con un día de retraso de publicación; universo point-in-time. **Libro spot hacia delante:** `grabar_libro` graba instantáneas. |
| `costes.py` | **Comisiones:** maker/taker por exchange (Binance spot y UM, Coinbase, Kraken, OKX). **Spread:** medido o por nivel de liquidez. **Deslizamiento e impacto:** el impacto es k·σ·√participación. **Funding:** el largo paga si la tasa es positiva. **Latencia y estrés:** latencia en barras; multiplicador ×2 para la prueba de estrés. |
| `motor.py` | **Entrada:** pesos objetivo con cualquier frecuencia y varios activos. **Ejecución:** en la apertura de t+latencia (latencia ≥ 1, obligatoria), con un tope de participación sobre la barra anterior. **Cortos:** solo en perpetuos (nocional y funding). **Efectivo:** se remunera, y el apalancamiento se financia. **Deslistado:** liquidación con recorte. **Salida:** operaciones, episodios, PnL por activo y desglose de costes. **Referencias:** comprar y mantener BTC, y efectivo remunerado. |
| `metricas.py` | **Rendimiento:** Sharpe (total y en exceso sobre el efectivo), Sortino, CAGR, Calmar, DD, PF y esperanza. **Sobreajuste:** PSR, DSR con el N del programa, MinTRL y años necesarios, PBO (CSCV). **Remuestreo:** bootstrap estacionario vectorizado. **Pruebas múltiples:** Holm y BH. **Miradas secuenciales:** gasto de alfa O'Brien-Fleming y estadístico z con asimetría y curtosis. |
| `validacion.py` | Walk-forward (deslizante o expansivo, con embargo), k-fold purgado con embargo y CPCV. |
| `diario.py` | Señales de paper trading encadenadas por hash. Solo se admiten señales de hipótesis registradas, abiertas y con el código sin cambios. **Condición de tiempo:** cada señal se escribe después de que su dato exista y antes de su ejecución. Una señal tardía se conserva, pero no cuenta. **Reconstrucción:** `pesos()` rehace la matriz para el motor. |
| `clasificacion.py` | APROBADA, RECHAZADA o DATOS INSUFICIENTES (reglas en `PREREGISTRO_PROSPECTIVO.md` §4). La mirada se anota siempre en el registro, y el cierre cuando la clase es definitiva. |
| `humo_datos.py` | Prueba de humo contra las fuentes reales. No evalúa ninguna estrategia. |

## 4. Riesgos metodológicos y cómo se tratan

1. **Potencia estadística (el más importante).** Años de datos necesarios para detectar un Sharpe anual dado (α 5 % unilateral, potencia 80 %, `metricas.anios_necesarios`):

| Sharpe real | 0,5 | 1,0 | 1,5 | 2,0 | 3,0 |
|---|---|---|---|---|---|
| Años | 24,7 | 6,2 | 2,8 | 1,55 | 0,70 |

   Con un año de paper trading solo puede confirmarse un Sharpe de alrededor de 2 o más, y además hay que superar el DSR con N ≥ 58 pruebas (SR0 ≈ 2,3 si la varianza entre pruebas es 1). Una ventaja real, pero modesta (Sharpe < 1,5), probablemente quedará en DATOS INSUFICIENTES durante años. Es el resultado honesto, no un fallo del módulo.
2. **Mirar demasiado (peeking).** Solo hay tres miradas, en los puntos de control pre-registrados: 90, 183 y 365 días. La frontera O'Brien-Fleming es z ≥ 3,78, 2,54 y 1,70 (alfa incremental 0,00008, 0,0056 y 0,044). Una mirada fuera de esos puntos no puede aprobar nada.
3. **Pruebas múltiples.** El DSR usa el N acumulado del programa (`Registro.total_pruebas()` = 58 anteriores + todas las rejillas y enmiendas). Holm se aplica entre todas las hipótesis evaluadas en cada ronda de miradas.
4. **Cambiar la hipótesis al ver datos.** Cualquier cambio exige una enmienda: el reloj vuelve a cero, las pruebas se suman y el hash del código se comprueba antes de cada señal o evaluación.
5. **Anticipación y fugas.** La latencia ≥ 1 es obligatoria, `available_at` va por dato, y hay una prueba de truncado y una comprobación de fugas.
6. **Supervivencia.** El universo es point-in-time (los deslistados salen solos, los listados entran con historia), con una comprobación explícita y un recorte en la liquidación por deslistado.
7. **No hay libro spot histórico gratis.** El archivo de bookTicker spot da 404. Para el libro de perpetuos sí hay `bookDepth` diario (a ±1–5 %, cada 30 s). Para el libro spot hay que grabarlo hacia delante con `grabar_libro` en una máquina persistente. Este contenedor es efímero: necesita Render (un worker) o el ordenador del usuario.
8. **Diferencia entre paper y real.** Llenado taker con spread, impacto y latencia; las órdenes maker se suponen no ejecutadas, salvo que se modelen. Queda un sesgo optimista residual: el colateral de los perpetuos se remunera al rf.
9. **Cambios del entorno.** Comisiones, tickers, caídas y funding comprimido (como pasó con el carry en el holdout v3). Las comisiones se verifican antes de cada evaluación. La regla de concentración impide depender de un activo o de un episodio.
10. **Bloqueos geográficos.** api.binance.com/fapi da 451 y Bybit da 403. Se usa el archivo de Binance (con 1–2 días de retraso), Coinbase, Kraken y OKX.

## 5. Pruebas ejecutadas (todas locales, sin red salvo la de humo)

- `python research/prospectivo/tests/test_prospectivo.py`: **43 pruebas OK** en Python 3.12 y 3.13 (`docs/evidencia_prospectivo/pruebas_py31*.txt`). Cubren:
  - cadena de hash: edición y borrado;
  - campos obligatorios;
  - enmiendas y reloj;
  - código cambiado;
  - ventanas, anticipación, fugas y supervivencia;
  - parsers de las seis fuentes (ms y µs, cabeceras, barras abiertas descartadas);
  - costes y ×2;
  - funding de largo y corto;
  - latencia y oráculo;
  - contabilidad exacta de comisiones;
  - tope de participación y deslistado;
  - PSR, DSR, MinTRL, PBO, bootstrap, Holm, BH y O'Brien-Fleming;
  - WF, purga y CPCV;
  - diario a tiempo, tardío y manipulado;
  - las tres clases, futilidad, concentración, fragilidad de parámetros, pocas operaciones y DSR con N enorme.
- `python research/edge3/test_engine.py`: 7 pruebas OK. El motor v3 no ha cambiado.
- `python research/prospectivo/humo_datos.py` (con red, 2026-11-16): las 10 fuentes responden y se convierten al esquema común (`docs/evidencia_prospectivo/humo_datos_2026-11-16.json`). Datos del 2026-11-14 en el archivo de Binance; el del 2026-11-15 aún no estaba publicado.

## 6. Qué falta para obtener evidencia

1. Registrar hipótesis concretas, con su código ya escrito, siguiendo `PREREGISTRO_PROSPECTIVO.md`. **No se ha registrado ninguna en esta entrega**: el registro debe hacerse con el código final y una fecha real, y cada registro empieza a consumir N.
2. Un proceso persistente (Render worker o una máquina del usuario) que, cada barra, descargue datos, escriba señales en el diario y, para las líneas de libro spot, grabe instantáneas.
3. Esperar a los puntos de control. Primera fecha posible de decisión: registro + 90 días (no antes del 2027-02-14).
