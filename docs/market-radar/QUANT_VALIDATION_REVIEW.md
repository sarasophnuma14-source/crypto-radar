# Revisión de validación cuantitativa · Market Radar

Fecha: 18-nov-2026. Objeto: `QUANT_RESEARCH_PROTOCOL.md` y los requisitos cuantitativos de `PRODUCT_REQUIREMENTS.md`.
Alcance de la revisión: **solo documentos y código**. No se accedió a ningún holdout bloqueado (`research/edge3/HOLDOUT_V3.lock`, ledger de `research/edge/`), no se ejecutó ningún backtest y no se tocó el paper trading de D_volmom_L28. Se leyó el código de `research/prospectivo/costes.py` y `registro.py` (rama `claude/investigacion-prospectiva`) para contrastar.

Estado por punto: **Adecuado** · **Insuficiente** (existe pero debe corregirse) · **Ausente**.

## Resumen

| # | Punto | Estado |
|---|---|---|
| 1 | Separación de hipótesis | Insuficiente |
| 2 | Pre-registro | Adecuado, con 3 correcciones |
| 3 | Holdout por mercado | Insuficiente |
| 4 | Look-ahead | Insuficiente |
| 5 | Sesgo de supervivencia | Insuficiente |
| 6 | Costos | Insuficiente (contradice el módulo existente) |
| 7 | Slippage | Insuficiente |
| 8 | Benchmarks | Insuficiente |
| 9 | Robustez | Adecuado, con 2 precisiones |
| 10 | Calibración | Ausente |
| 11 | Seguimiento descriptivo del scanner | Riesgo nuevo |

Conclusión: el protocolo es una base sólida para **no engañarse**, pero no está listo para registrar la primera hipótesis multiactivo. Ninguna de las correcciones afecta a I-1, que no contiene motores ni investigación.

---

## 1. Separación de hipótesis — Insuficiente

| Hallazgo | Corrección |
|---|---|
| El protocolo define una hipótesis por experimento, pero no dice qué pasa con hipótesis que comparten datos, parámetros o señales (p. ej. momentum en acciones y en ETF sectoriales del mismo periodo) | Agrupar en **familias**: hipótesis de la misma familia comparten la corrección por pruebas múltiples y el presupuesto de holdout |
| No separa las hipótesis del **producto** (estados, score) de las de **investigación** (estrategias) | El score y los estados no son hipótesis: son descriptivos. Si alguien quiere afirmar que un estado "funciona", eso se registra como hipótesis nueva con evento y horizonte |
| El contador de 58 pruebas previas es de cripto; no se dice si cuenta para otras clases | Contador por clase de activo **más** un contador global; el *deflated Sharpe* de una hipótesis multiactivo usa el global |

## 2. Pre-registro — Adecuado, con correcciones

Lo que está bien: evento, horizonte, benchmark, costos, universo por fecha, separación temporal, métrica única, número de variantes, hash en `experiment_registry`. Coincide con `research/prospectivo/registro.py` (registro encadenado, `enmendar`, `mirar`, `cerrar`).

Correcciones:
1. Añadir **potencia estadística esperada** (tamaño de efecto mínimo detectable con el tramo disponible) **antes** de correr nada; si la potencia es < 50 %, no se registra.
2. Añadir el **modelo de costos exacto** (nombre y parámetros de `ModeloCostes`), no una descripción.
3. Las enmiendas se permiten solo antes de la primera mirada (`mirar`); después, cualquier cambio es una hipótesis nueva (así lo hace ya `registro.py`, que reinicia el reloj; el protocolo debe decirlo).

## 3. Holdout por mercado — Insuficiente

| Hallazgo | Corrección |
|---|---|
| "Virgen (nadie del proyecto lo ha mirado)" no es verificable (VER-01) | Llamarlo **bloqueado**: candado creado antes de descargar el tramo; el registro prueba que ningún experimento lo leyó |
| El conocimiento general contamina: el propietario y el modelo saben qué pasó en 2024–2026 (p. ej. qué clases subieron) | Declararlo en cada pre-registro; preferir hipótesis cuyo resultado no sea "obvio" conociendo el periodo; dar más peso al prospectivo |
| 24 meses sin justificar (JUS-03) | **Potencia:** con datos diarios, el error estándar del Sharpe anualizado es ≈ 1/√T (T en años). Para 80 % de potencia y α = 5 % unilateral hace falta SR ≥ (1,645 + 0,842)/√T. Con T = 2 años: **SR ≥ 1,76**. Con T = 3: SR ≥ 1,44. El mismo cálculo da los 6,2 años para SR = 1 citados en `research/prospectivo`. Conclusión: 24 meses solo detectan estrategias muy fuertes; se mantiene 24 meses para no consumir más historia de desarrollo, pero el pre-registro debe declarar el SR mínimo detectable |
| Una hipótesis multiactivo (p. ej. rotación entre clases) usa los holdouts de varias clases a la vez | Regla: consumir el holdout de una clase en una hipótesis multiactivo **lo consume para todas las hipótesis de esa clase** en la misma familia |
| Cripto | Correcto: solo prospectivo desde `CORTE_PROSPECTIVO` = 2026-11-16T00:00Z |

## 4. Look-ahead — Insuficiente

El protocolo cubre `source_ts` y `reported_ts`. Faltan:

| Fuente de look-ahead | Corrección |
|---|---|
| **Correcciones posteriores** de proveedores (precio corregido días después) | Investigar con el dato **tal como se conocía** en cada fecha: usar la persistencia bitemporal (`ARCHITECTURE_REVIEW` §8) |
| **Series ajustadas** por splits y dividendos usan información futura (el factor de ajuste se conoce después) | Señales sobre serie **no ajustada** hasta la fecha o con ajuste reconstruido punto en el tiempo; retornos sobre serie ajustada |
| **Rollover por volumen u open interest**: el cruce se conoce al cierre | La serie cambia de contrato en la sesión **siguiente** al cruce |
| **Universos por capitalización actual** | Universo por fecha (ver §5) |
| **Ejecución**: señal al cierre de *t* ejecutada al cierre de *t* | Ejecución en la apertura de *t+1* como mínimo (`latencia_barras = 1` en `ModeloCostes`) |
| **Calendario**: festivos conocidos por adelantado sí; suspensiones no | Las suspensiones se tratan como datos faltantes, no como sesiones conocidas |
| **Prueba automática**: no existe | Prueba de "truncado": calcular todos los indicadores con datos hasta *t* y con la serie completa; los valores en *t* deben coincidir exactamente |

## 5. Sesgo de supervivencia — Insuficiente

| Hallazgo | Corrección |
|---|---|
| La 2.1 construye el universo con el **top actual** de CoinGecko (`scanner.py`, `run_scan`): eso tiene sesgo de supervivencia para cualquier uso histórico | Para investigación, universo reconstruido por fecha; en producción no importa (es el universo de hoy) |
| No se ha verificado si el panel de 281 perpetuos de `data.binance.vision` usado en la v3 incluye contratos deslistados | **NO VERIFICADO**; anotarlo como limitación de los resultados v3 (que ya son negativos, así que el sesgo solo los haría peores) |
| Acciones: hace falta historial de deslistados y de composición de índices, que es dato licenciado (DEP-05) | Requisito para elegir proveedor de acciones |
| Futuros: contratos vencidos | Se conservan (`instruments` nunca se borran) |

## 6. Costos — Insuficiente

| Hallazgo | Corrección |
|---|---|
| La tabla de §5 del protocolo contradice `research/prospectivo/costes.py` (CON-08): el módulo usa semiespread BTC/ETH 0,005 %, top10 0,02 %, top50 0,08 %, resto 0,25 %, deslizamiento fijo 0,02 %, impacto k·σ·√participación con k = 0,5 y participación máxima 1 % | Reutilizar `ModeloCostes` y extenderlo por clase: comisiones por bróker de referencia (acciones EE. UU. 0 en brókeres minoristas, pero tasas regulatorias en ventas), spread medido o por nivel de liquidez, impacto con la misma fórmula |
| Las comisiones del módulo dicen "revisar antes de usar" | Cada pre-registro fija la fecha de verificación de comisiones |
| Faltan costos de **financiación**: swaps en FX, *roll yield* en futuros, préstamo de títulos si hubiera cortos | Incluir; el producto es spot y sin apalancamiento, pero las comparaciones con benchmarks de futuros deben incluir el *roll yield* |
| Impuestos | Fuera del backtest; se mencionan como limitación |

## 7. Slippage — Insuficiente

| Hallazgo | Corrección |
|---|---|
| El protocolo mezcla spread y slippage en una cifra | Separar tres términos, como el módulo: semiespread + deslizamiento fijo + impacto dependiente de la participación |
| Gaps de apertura en acciones: un stop puede ejecutarse muy lejos | Ejecución de stops al **peor** de (stop, apertura) |
| Activos ilíquidos | Participación máxima 1 % del volumen de la barra; si la orden no cabe, se ejecuta parcial o no se ejecuta |
| Sensibilidad | Mantener costos × 0,5 / × 1 / × 2 y añadir el **costo de equilibrio**: multiplicador de costos que lleva el resultado a cero |

## 8. Benchmarks — Insuficiente

| Clase | Benchmark del protocolo | Problema | Propuesta |
|---|---|---|---|
| Cripto | BTC o cesta por capitalización | Ambiguo | Principal BTC (comprar y mantener); secundario cesta top-10 por capitalización reconstruida por fecha |
| Acciones EE. UU. | SPY | Correcto para grandes; injusto para pequeñas | SPY + benchmark del mismo universo con pesos iguales |
| ETF sectoriales | SPY | Correcto | Igual |
| Forex | "carry cero" | No es un benchmark comparable | Retorno cero **más** el diferencial de tipos (posición neutral) y, como alternativa, el índice del dólar si hay licencia |
| Materias primas | Índice de la clase o comprar y mantener la serie continua | El índice requiere licencia | Comprar y mantener la serie continua con el mismo `roll_rule` |
| Todas | — | Falta el benchmark de **azar** | Señales aleatorias con la misma rotación y exposición (prueba de permutación) |

## 9. Robustez — Adecuado, con precisiones

Lo que está bien: ±20 % por parámetro, subperiodos, regímenes, costos × 2, *deflated Sharpe*, bootstrap por bloques, Holm/BH.
Precisiones:
1. *Deflated Sharpe* necesita la **varianza de los Sharpe de todas las variantes probadas** y la asimetría y curtosis de los retornos: el registro debe guardarlas, no solo el número de pruebas.
2. Bootstrap por bloques: fijar la longitud del bloque (p. ej. ≈ horizonte de la hipótesis o regla de Politis-White) en el pre-registro.

## 10. Calibración — Ausente

RS-07 prohíbe mostrar probabilidades sin calibración, pero no dice cómo se calibra. Propuesta mínima, solo aplicable si algún día se registra una hipótesis probabilística:

| Elemento | Definición |
|---|---|
| Evento | Binario y pre-registrado (p. ej. "retorno a 20 sesiones > benchmark") |
| Métricas | Brier score, *log loss*, diagrama de fiabilidad con ≥ 10 cubos y ≥ 50 eventos por cubo, error de calibración esperado (ECE) |
| Comparación | Contra la frecuencia base del evento (probabilidad constante) |
| Aprobación | Brier mejor que la frecuencia base con intervalo bootstrap que excluya 0, en validación **y** en prospectivo |
| Presentación | Probabilidad con intervalo, horizonte y fecha del modelo |

## 11. Riesgo nuevo: el seguimiento descriptivo del scanner

El protocolo (§9) propone medir desde el primer día qué pasó tras cada estado a 5/20/60 sesiones. Es útil y honesto, pero crea una tentación: ajustar pesos o reglas mirando esos resultados, lo que convierte el seguimiento en una búsqueda de patrones sin control.

Regla propuesta: los resultados del seguimiento solo pueden generar **ideas**; cualquier cambio de pesos o reglas basado en ellos se registra como hipótesis nueva, cuyo periodo de validación empieza **después** del cambio.

---

## Qué se puede afirmar hoy

- NO EDGE sigue vigente. Nada en esta revisión lo cambia.
- Ninguna afirmación de ventaja puede hacerse en otros mercados sin pasar el protocolo corregido.
- El primer incremento técnico (I-1) no contiene motores ni señales, por lo que no requiere validación cuantitativa; sí requiere que la persistencia sea bitemporal para que la investigación futura pueda evitar look-ahead (§4).
