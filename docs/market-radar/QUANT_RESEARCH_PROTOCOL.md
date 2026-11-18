# Protocolo de investigación cuantitativa · Market Radar

Versión 1.0 · 18-nov-2026 · Estado: propuesta; reglas marcadas **OBLIGATORIA** derivan directamente de la especificación §13.

## 1. Punto de partida

- Estado vigente: **NO EDGE**. Ronda v3 (16-nov-2026): 35 configuraciones pre-registradas en 8 familias, holdout 2025-04-01 → 2026-11-14 usado una vez y bloqueado; ninguna con ventaja. Motor del producto: Sharpe fuera de muestra −0,30, holdout −0,15. Rondas previas: 23 configuraciones, holdout −22,9 %.
- **Market Radar no hereda ninguna afirmación de ventaja.** Los estados y el score son descriptivos.
- Contador de pruebas acumuladas sobre cripto: **58** (`PRUEBAS_PREVIAS` en `research/prospectivo`, rama `claude/investigacion-prospectiva`, sin PR). Toda prueba nueva lo incrementa.
- En cripto **no queda muestra histórica virgen**: cualquier hipótesis nueva sobre cripto solo puede validarse de forma **prospectiva** (datos posteriores a `CORTE_PROSPECTIVO` = 2026-11-16T00:00Z).
- El paper trading de D_volmom_L28 (en curso desde el 17-nov, mínimo 183 días) es un experimento aparte. **Este protocolo no lo toca ni lo reutiliza.**

## 2. Ciclo de vida de una hipótesis

```
Idea ─► Pre-registro ─► Desarrollo ─► Validación ─► Holdout (1 vez) ─► Prospectivo ─► Decisión
        (bloqueado)     (dev split)   (val split)   (candado)          (≥ 90 días)     (comité = PATRON)
```

| Paso | Regla | Obligatoria |
|---|---|---|
| Pre-registro | Se escribe **antes** de ver resultados: evento, horizonte, universo, benchmark, costos, métrica principal, criterio de éxito, número de variantes. Se guarda en `experiment_registry` con hash | Sí |
| Desarrollo | Solo con el tramo dev. Se cuentan **todas** las variantes probadas | Sí |
| Validación | Tramo val, sin reajustar después | Sí |
| Holdout | Una sola ejecución, protegida por candado (ledger encadenado como `radar/edge/ledger.py`); reintento imposible sin nuevo pre-registro | Sí |
| Prospectivo | Paper trading separado de producción; puntos de control 90/183/365 días con límites O'Brien-Fleming (z 3,78 / 2,54 / 1,70) como en `research/prospectivo` | Sí |
| Decisión | Aprobación del propietario, con informe que incluye resultados negativos | Sí |

## 3. Definiciones obligatorias en cada pre-registro

1. **Evento:** qué se predice exactamente (p. ej. "retorno del instrumento entre el cierre de *t* y el cierre de *t+20* sesiones mayor que el del benchmark").
2. **Horizonte:** en sesiones del mercado, no en días naturales.
3. **Benchmark:** por clase (cripto: BTC o cesta por capitalización; acciones EE. UU.: SPY; ETF sectoriales: SPY; forex: carry cero; materias primas: índice de la clase o comprar y mantener la serie continua).
4. **Costos:** comisión + spread + deslizamiento por clase (§5), en ambas direcciones.
5. **Universo por fecha:** incluye deslistados y vencidos (anti-supervivencia).
6. **Timestamps:** se usan `source_ts` y, para fundamentales, `reported_ts` (anti look-ahead).
7. **Separación temporal:** dev / val / holdout cronológicos, con embargo ≥ horizonte entre tramos.
8. **Walk-forward:** reentrenos solo con datos anteriores a cada ventana.
9. **Métrica principal** única y criterio de éxito numérico.
10. **Número de variantes** previsto (para corrección por pruebas múltiples).

## 4. Holdout por clase de activo

| Clase | Holdout propuesto | Estado |
|---|---|---|
| Cripto | **Agotado** (v3). Solo prospectivo | Bloqueado |
| Acciones/ETF EE. UU. | Últimos 24 meses antes del primer pre-registro | Virgen (nadie del proyecto lo ha mirado con una estrategia) |
| Forex | Últimos 24 meses | Virgen |
| Metales | Últimos 24 meses | Virgen |
| Índices | Últimos 24 meses | Virgen |
| Energía | Últimos 24 meses | Virgen |
| Agrícolas | Últimos 24 meses | Virgen |

Regla: el candado de holdout de cada clase se crea **antes** de descargar el historial a la máquina de investigación; las herramientas de exploración leen solo hasta la fecha de corte. Mirar gráficos del tramo holdout para "inspirarse" invalida el holdout y se debe declarar.

## 5. Costos mínimos por clase (SUPUESTO conservador, a calibrar con datos)

| Clase | Comisión | Spread + deslizamiento (ida) |
|---|---|---|
| Cripto grandes | 0,10 % | 0,05–0,10 % |
| Cripto pequeñas | 0,10 % | 0,30–1,00 % según volumen |
| Acciones grandes EE. UU. | 0 | 0,02–0,05 % |
| Acciones pequeñas | 0 | 0,20–0,50 % |
| ETF líquidos | 0 | 0,01–0,03 % |
| Forex mayores | 0 | 0,5–1,5 pips |
| Futuros | por contrato | 1 tick |

Sensibilidad obligatoria: resultados con costos × 0,5, × 1, × 2.

## 6. Métricas

Se reportan **todas**, no solo la principal: Sharpe, Sortino, Profit Factor, Expectancy, Max Drawdown, Turnover, Hit Rate, costos totales, calibración (si hay probabilidades), estabilidad por subperiodo y por régimen.

Corrección estadística:
- **Deflated Sharpe Ratio** con el número total de pruebas (incluidas las 58 previas si es cripto).
- Bootstrap por bloques para intervalos de confianza.
- p-valores ajustados (Holm o Benjamini-Hochberg) cuando hay familias de variantes.
- Potencia: informar cuántos años harían falta para detectar el Sharpe objetivo (referencia: SR 1 ≈ 6,2 años; SR 2 ≈ 1,55 años según `research/prospectivo`).

## 7. Criterios de aprobación (todos)

1. Métrica principal supera el criterio pre-registrado en val **y** en holdout.
2. Deflated Sharpe > 0 con significación pre-registrada.
3. Resultado positivo con costos × 2.
4. Ningún subperiodo de 12 meses explica más del 50 % del resultado.
5. Robusto a ±20 % en cada parámetro (sin "picos" aislados).
6. Funciona en ≥ 2 regímenes o declara explícitamente en cuál no se usa.
7. Prospectivo ≥ 90 días sin cruzar el límite inferior de O'Brien-Fleming.
8. Código y datos reproducibles por un tercero desde el registro.

No se aprueba una estrategia por resultado agregado si falla cualquiera de los anteriores.

## 8. Qué se publica

- Toda hipótesis registrada aparece en el informe, **incluidas las fallidas**, con su número de variantes.
- La interfaz solo puede llamar "validada" a una hipótesis que pasó §7. Hasta entonces: "Señal analítica · no validada estadísticamente".
- El componente "evidencia histórica" del score es 0 para cualquier configuración no validada.

## 9. Evaluación descriptiva del scanner (no es validación)

Market Radar sí medirá, desde el primer día, qué pasó después de cada observación (`hypothesis_outcomes` a 5, 20 y 60 sesiones) para cada estado. Esto es **seguimiento descriptivo**, no prueba de ventaja: se publica con intervalos y con el benchmark, y no se usa para ajustar pesos sin un pre-registro nuevo.

## 10. Separación de entornos

| Entorno | Puede | No puede |
|---|---|---|
| Investigación (`research/`) | Leer copias de datos, ejecutar backtests, escribir en `experiment_registry` | Escribir en tablas de producción |
| Paper trading | Simular con datos en vivo, guardar en su propio almacén | Enviar órdenes reales; mezclarse con D_volmom_L28 |
| Producción | Mostrar estados y score descriptivos | Mostrar resultados de backtest como promesa |

**No se implementa ejecución real de operaciones.**
