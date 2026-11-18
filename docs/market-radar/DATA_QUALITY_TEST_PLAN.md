# Plan de pruebas de calidad de datos · Market Radar

Fecha: 18-nov-2026. Base: `radar/quant/quality.py` (2.1: huecos, duplicados, OHLC incoherente, saltos, datos viejos), generalizado para varios mercados con calendario, acciones corporativas y futuros.
Las pruebas se ejecutan en dos sitios:

- **Validador en ingesta** (síncrono): rechaza o marca cada lote antes de escribir la capa normalizada.
- **Auditoría por lotes** (diaria): revisa series completas, compara proveedores y produce las métricas de §4.

Cada regla tiene un identificador, un resultado (`ok`, `degraded`, `suspect`, `stale`, `missing`, `rejected`) y una prueba automática con **datos sintéticos** (nunca datos de proveedores reales en el repositorio, por licencia).

Leyenda de fase: I-1 = primer incremento (solo contratos y validadores puros); I-2+ = cuando haya ingesta; F3/F4/F5 = fase del mercado.

---

## 1. Reglas

### 1.1 Duplicados (DQ-DUP)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-DUP-01 | Dos velas con la misma clave (instrumento, proveedor, temporalidad, `bar_start`) en el mismo lote | `rejected` el lote | I-1 |
| DQ-DUP-02 | Vela ya existente con **mismo** hash de contenido | Ignorar (idempotencia) | I-1 |
| DQ-DUP-03 | Vela ya existente con **distinto** hash | Nueva revisión bitemporal + evento `correction` | I-2 |
| DQ-DUP-04 | Más de 3 correcciones del mismo proveedor en 24 h para un instrumento | `suspect` + alerta operativa | I-2 |

### 1.2 Datos atrasados (DQ-STALE)

Frescura medida contra la **sesión**, no contra el reloj.

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-STALE-01 | Última vela diaria cerrada anterior al cierre de la última sesión completada | `degraded` | I-2 |
| DQ-STALE-02 | Retraso ≥ 2 sesiones | `stale`: el scanner no clasifica | I-2 |
| DQ-STALE-03 | Intradía: retraso ≥ 2 barras → `degraded`; ≥ 4 → `stale` | — | I-2 |
| DQ-STALE-04 | Mercado cerrado (festivo o fin de semana): no hay velas esperadas y **no** se marca nada | `ok` | I-1 (calendario) |
| DQ-STALE-05 | `received_ts − source_ts` mayor que la latencia declarada del proveedor × 3 | Evento de latencia | I-2 |

### 1.3 Velas incompletas o incoherentes (DQ-BAR)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-BAR-01 | `low ≤ min(open, close) ≤ max(open, close) ≤ high` | Si falla: `rejected` | I-1 |
| DQ-BAR-02 | Precios > 0; volumen ≥ 0; ningún NaN o infinito | `rejected` | I-1 |
| DQ-BAR-03 | `bar_end − bar_start` = duración de la temporalidad, salvo media sesión declarada por el calendario | `rejected` | I-1 |
| DQ-BAR-04 | `bar_start` alineado a la rejilla de la temporalidad y la sesión | `rejected` | I-1 |
| DQ-BAR-05 | Vela marcada cerrada con `bar_end` posterior al reloj de ingesta | `rejected` (vela abierta presentada como cerrada) | I-1 |
| DQ-BAR-06 | Volumen = 0 en sesión abierta para un instrumento con volumen medio > 0 | `suspect` | I-2 |
| DQ-BAR-07 | `open = high = low = close` repetido > 3 barras en sesión abierta | `suspect` (precio congelado) | I-2 |
| DQ-BAR-08 | Hueco: falta una barra esperada según el calendario | Serie `degraded`; > 2 % de barras faltantes en 30 sesiones → `missing` | I-2 |

### 1.4 Saltos de precio (DQ-JUMP)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-JUMP-01 | \|ln(close_t / close_{t−1})\| > k · σ̂ (σ̂ = desviación robusta, MAD × 1,4826, de 60 barras) con k = 8 | `suspect` | I-2 |
| DQ-JUMP-02 | El salto coincide con una acción corporativa registrada (split, redenominación) | `ok` en serie ajustada; el salto queda solo en la no ajustada | F3 |
| DQ-JUMP-03 | El salto **no** aparece en un segundo proveedor (§1.10) | `suspect` → no se clasifica ese día | I-2+ |
| DQ-JUMP-04 | Gap de apertura entre sesiones: se calcula aparte y **no** dispara DQ-JUMP-01 si el precio intrasesión es coherente | `ok` + métrica de riesgo de gap | F3 |
| DQ-JUMP-05 | Mecha aislada: high o low a > k·σ̂ del rango de cierre de las barras vecinas con volumen bajo | `suspect` (posible impresión errónea o manipulación) | I-2 |

k = 8 es un valor **propuesto**; se calibra midiendo la tasa de falsos positivos en 12 meses de cada clase (objetivo < 0,1 % de barras marcadas sin causa).

### 1.5 Sesiones incorrectas (DQ-SES)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-SES-01 | Vela regular fuera de una sesión regular del calendario | `rejected` (o reclasificada a `pre`/`post` si el proveedor lo indica) | I-1 |
| DQ-SES-02 | Vela en día festivo según el calendario | `suspect` + revisión del calendario | I-1 |
| DQ-SES-03 | Cambio de horario de verano: la sesión conserva su hora local; en UTC se desplaza una hora | Prueba con fechas de cambio de EE. UU. y Europa (que no coinciden) | I-1 |
| DQ-SES-04 | Vela diaria cuyo cierre no coincide con el cierre de sesión (p. ej. cierre a 00:00 UTC en una acción) | `rejected` | I-1 |
| DQ-SES-05 | Calendario con menos de 6 meses generados hacia adelante | Alerta operativa | I-2 |
| DQ-SES-06 | Comparación anual del calendario con el calendario oficial publicado por la bolsa | Diferencias = 0 antes de habilitar un mercado | F3 |

### 1.6 Cambios de símbolo (DQ-SYM)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-SYM-01 | Resolver un identificador sin fecha | Error de programación (la API lo exige) | I-1 |
| DQ-SYM-02 | Dos vigencias solapadas del mismo identificador | Imposible por restricción de exclusión; prueba que el INSERT falla | I-1 |
| DQ-SYM-03 | Ticker reutilizado por otra empresa o token: la serie histórica no se mezcla | Prueba: dos instrumentos, mismo ticker en periodos distintos | I-1 |
| DQ-SYM-04 | El proveedor devuelve un símbolo desconocido para el registro | Cuarentena, no se crea instrumento automáticamente | I-2 |
| DQ-SYM-05 | Cripto: *rebrand* o migración de token (p. ej. un token que cambia de ticker y de contrato) | Nuevo instrumento + `corporate_actions` tipo `token_migration`; la serie continua es un derivado explícito | F3 |

### 1.7 Acciones corporativas (DQ-CA)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-CA-01 | Split N:1: serie ajustada continua; no ajustada con salto exacto de factor N en `ex_date` | Prueba con serie sintética | F3 |
| DQ-CA-02 | Dividendo en efectivo: serie de retorno total ajustada; la de precio no cambia | Prueba | F3 |
| DQ-CA-03 | Acción corporativa recibida tarde: se crea nueva versión de la serie ajustada; las observaciones antiguas conservan la versión con la que se calcularon | Prueba bitemporal | F3 |
| DQ-CA-04 | Salto > k·σ̂ sin acción corporativa en ± 2 sesiones | `suspect` y consulta al segundo proveedor | F3 |
| DQ-CA-05 | Deslistado: el instrumento se cierra (`last_seen`), **no** se borra | Prueba de supervivencia | F3 |

### 1.8 Vencimientos de futuros (DQ-EXP)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-EXP-01 | Todo `instrument` de tipo `future` tiene `expiry` | Restricción en base | I-1 |
| DQ-EXP-02 | Velas posteriores al vencimiento | `rejected` | F4 |
| DQ-EXP-03 | Contrato próximo a vencer con open interest y volumen en caída: no se usa como contrato activo | Regla de `roll_rules` | F4 |
| DQ-EXP-04 | Unidades y tamaño de contrato coinciden con la ficha de la bolsa | Comparación al dar de alta | F4 |

### 1.9 Rollovers (DQ-ROLL)

| Id | Regla | Resultado | Fase |
|---|---|---|---|
| DQ-ROLL-01 | La serie continua cambia de contrato **exactamente** en la fecha que dicta su `roll_rule` versionada | Prueba con dos contratos sintéticos | F4 |
| DQ-ROLL-02 | Ajuste por diferencia: la serie ajustada no tiene salto en la fecha de rollover; la no ajustada sí, igual al diferencial | Prueba | F4 |
| DQ-ROLL-03 | Ajuste por ratio: retornos de la serie ajustada iguales a los del contrato activo en cada tramo | Prueba | F4 |
| DQ-ROLL-04 | Cambiar la regla genera una serie nueva (versión), nunca reescribe la anterior | Prueba | F4 |
| DQ-ROLL-05 | Ningún indicador compara precios de dos contratos sin pasar por una serie | Prueba de arquitectura (los motores solo aceptan `series_id` para futuros) | F4 |

### 1.10 Datos de distintos proveedores (DQ-XPROV)

| Id | Regla | Umbral propuesto | Fase |
|---|---|---|---|
| DQ-XPROV-01 | Discrepancia de cierre diario entre fuente primaria y secundaria | Cripto grandes 0,5 %; cripto resto 2 %; acciones y ETF 0,1 %; FX mayores 5 pb; futuros 1 tick | I-2+ |
| DQ-XPROV-02 | Discrepancia de volumen | No se compara entre exchanges cripto (son mercados distintos); en acciones, consolidado vs. consolidado ≤ 5 % | F3 |
| DQ-XPROV-03 | La fuente secundaria nunca reemplaza silenciosamente a la primaria: el cambio de primaria es un evento auditado | — | I-2 |
| DQ-XPROV-04 | Forex OTC: las series de dos proveedores **no** se mezclan en una misma serie | Prueba | F4 |
| DQ-XPROV-05 | Si la discrepancia supera el umbral 3 días en 10, el instrumento pasa a `suspect` | — | I-2+ |

## 2. Datos sintéticos de prueba

Generador determinista (semilla fija) en `tests/market_radar/fixtures/`, que produce:

| Fixture | Contenido |
|---|---|
| `serie_limpia` | 500 barras diarias coherentes |
| `con_duplicado`, `con_hueco`, `con_ohlc_invalido`, `con_vela_abierta` | Un defecto cada una, en posición conocida |
| `con_salto`, `con_mecha` | Salto de 15σ̂ y mecha aislada |
| `calendario_ficticio` | Bolsa inventada con festivos, media sesión y cambio de hora (no representa ninguna bolsa real) |
| `ticker_reutilizado` | Dos instrumentos con el mismo ticker en 2020–2022 y 2024–2026 |
| `split_4x1`, `dividendo` | Acciones corporativas |
| `dos_contratos` | Futuro sintético con rollover |
| `dos_proveedores` | Misma serie con ruido y un error inyectado |

Cada regla tiene al menos una prueba positiva (detecta el defecto) y una negativa (no marca la serie limpia).

## 3. Cobertura por incremento

| Incremento | Reglas |
|---|---|
| I-1 | DQ-DUP-01/02, DQ-STALE-04, DQ-BAR-01…05, DQ-SES-01…04, DQ-SYM-01…03, DQ-EXP-01 (todas puras o de restricción en base) |
| I-2 | Resto de DQ-DUP, DQ-STALE, DQ-BAR, DQ-JUMP-01/03/05, DQ-SYM-04, DQ-XPROV-01/03/05, DQ-SES-05 |
| F3 | DQ-JUMP-02/04, DQ-SES-06, DQ-SYM-05, DQ-CA, DQ-XPROV-02 |
| F4–F5 | DQ-EXP-02…04, DQ-ROLL, DQ-XPROV-04 |

## 4. Métricas para "calidad medida" (criterio 5 de la §18)

Un mercado cumple el criterio cuando, durante **30 sesiones consecutivas**:

| Métrica | Definición | Umbral propuesto |
|---|---|---|
| Completitud | barras recibidas ÷ barras esperadas por calendario (universo habilitado) | ≥ 99,5 % |
| Frescura | % de sesiones con datos diarios disponibles ≤ 30 min tras el cierre | ≥ 99 % |
| Coherencia | % de barras `rejected` por DQ-BAR | ≤ 0,05 % |
| Saltos sospechosos sin causa | barras `suspect` por DQ-JUMP sin acción corporativa ni confirmación del secundario | ≤ 0,1 % |
| Discrepancia entre proveedores | % de instrumentos-día sobre el umbral DQ-XPROV-01 | ≤ 1 % |
| Correcciones | revisiones por cada 10.000 barras | Se informa; sin umbral hasta tener base |
| Liquidez | instrumentos del universo que cumplen el mínimo de su clase (volumen medio 30 días: cripto ≥ US$2 M, acciones ≥ US$5 M, ETF ≥ US$2 M; FX y futuros por volumen del contrato) | Los que no cumplen se excluyen con motivo |

Todos los umbrales son **propuestas** que el propietario aprueba; se registran en `model_versions` como parámetros de calidad.

## 5. Informe

La auditoría diaria produce un informe por mercado (tabla `mr.quality_reports` en I-2) con las métricas de §4, las reglas activadas y los instrumentos en `suspect`. Ese informe es la evidencia que se adjunta a la PR de habilitación del mercado.
