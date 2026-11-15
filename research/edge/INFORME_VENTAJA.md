# Informe: búsqueda de una ventaja estadística real en cripto spot

Fecha: 2026-11-15 · Rama `claude/project-thread-i8udp5` · Pre-registro: `research/edge/PREREGISTRO.md` (commit `1d6a6aa`,
publicado antes de cualquier resultado) · Selección congelada antes del holdout: commit `2eddb09`.

## Veredicto

**No se encontró una ventaja estadística. Las 5 familias quedan REJECTED y no hay estrategia ganadora.**

- Solo 1 de 5 familias pasó la Validación (momentum gestionado por volatilidad, `D_volmom_L28`). En el holdout perdió
  −22,9 % (Sharpe −0,94, PF 0,68) y no cumplió ninguno de los 9 criterios.
- 22 de las 23 configuraciones pierden dinero en el holdout. La única positiva (`B_donchian_N90_exitchan`, +1,7 %,
  Sharpe 0,14) no se eligió en Desarrollo y tampoco habría pasado los criterios.
- Ningún p-valor del bootstrap baja de 0,39 (sin corregir). Con Holm o Bonferroni, nada se acerca a 0,05.
- El walk-forward anual pierde en las 5 familias (de −3,7 % a −17,1 % encadenado, 2022-2026).
- Recomendación: **no operar con estas señales**, no publicar señales de compra como si tuvieran ventaja y no conectar
  órdenes reales. Prefiere no operar antes que operar sin ventaja.

## 1. Auditoría del sistema existente (motor 2.0, `radar/quant`)

| Hallazgo | Evidencia | Consecuencia |
| --- | --- | --- |
| El puntaje de `early.py` no predice | Correlación de rango con el exceso de retorno a 20 d: −0,091 (2020-23) y −0,060 (2024-26); ver `BACKTEST_REPORT.md` | Ordenar por puntaje no selecciona mejores monedas |
| Pesos fijados a mano | `early.py` usa los pesos de la especificación original, nunca estimados | Sin base estadística |
| Familias redundantes | En 2020-23, 6 de 7 familias tienen correlación negativa de tamaño parecido (−0,055 a −0,118); probablemente miden lo mismo (el retorno reciente) desde ángulos distintos | Sumarlas no parece aportar información independiente |
| Mirada al futuro | No se encontró: señales con velas cerradas, ejecución en D+1 y truncamiento probado (pruebas T02 y T10) | Correcto |
| Reutilización de tickers en los datos | 6 series con huecos > 7 días; LUNA salta ×177 400 (LUNA antigua → LUNA 2.0), STRAX ×0,10 y VIDT ×0,05 (canjes de token) | `backtest_pro.py` no las separa. Ninguna operación del 2.0 cruzó esos huecos, pero no hay protección. El laboratorio nuevo las parte en dos activos |
| Métricas | Calculadas desde operaciones y curva; Sharpe diario ×√365 | Correctas |
| Universo histórico | Top 150 por volumen de 30 días en cada fecha | Correcto. El archivo de Binance solo añadió 30 pares que faltaban (casi todos acciones tokenizadas de 2026), así que el sesgo de supervivencia del panel es pequeño |
| Ajuste de parámetros | La calibración del 2.0 mejoraba 2020-23 y empeoraba 2024-26 | Sobreajuste documentado |

El motor original se dejó intacto. Todo lo nuevo está en `radar/edge/` y `research/edge/`.

## 2. Inventario y limitaciones de datos

| Fuente | Estado |
| --- | --- |
| Binance Spot, velas diarias USDT 2020-01-01 a 2026-11-14 | Usada: 661 pares del panel (469 activos, 192 pausados) |
| Archivo público `data.binance.vision` | Usado para buscar pares retirados por completo: 34 faltaban, 30 con datos; se excluyen 28 acciones tokenizadas |
| Coinbase, Kraken, OKX | Accesibles desde este entorno, no usadas en esta ronda: unirlas exige emparejar activos y monedas de cotización distintas. Ausencia registrada |
| Bybit | Bloqueada desde este entorno (HTTP 403) |
| Spread y libro de órdenes históricos | No existen en fuentes gratuitas: se modelan por tramos de liquidez |
| Concentración de holders, on-chain | N/D |
| Fechas de listado | Se usa la primera vela disponible |

Tras limpiar y partir series: 671 activos. Volumen en USDT.

## 3. Estrategias, parámetros y protocolo

23 configuraciones fijadas en el pre-registro: A momentum de serie temporal (6), B Donchian (6), C early breakout (4),
D momentum gestionado por volatilidad (3) y E híbrida (4: tendencia semanal + compresión + Donchian + fuerza relativa + trailing ATR).

Cortes: Desarrollo 2020-01 a 2022-12, Validación 2023-01 a 2024-06, Holdout 2024-07 a 2026-11 (ejecutado una vez;
`HOLDOUT_EXECUTED.lock` impide repetirlo).

Simulador (`radar/edge/sim.py`): ejecución a la apertura de D+1, costes por tramo de liquidez (base, ×2, ×3),
tope del 1 % del volumen diario (ejecución parcial), órdenes canceladas si la apertura salta más de 1 ATR, stops intradía
con huecos a la apertura y revisión el mismo día de la entrada, retiradas con descuento del 10 % (estrés 30 %),
riesgo 0,5 % por operación, 15 % máximo por activo, 5 posiciones, 3 % de riesgo abierto, riesgo a la mitad con BTC bajo su media de 200 días.

## 4. Resultados de las configuraciones elegidas

| Familia | Configuración elegida | Desarrollo Sharpe | Validación Sharpe / PF | Holdout retorno | Holdout Sharpe | PF | Drawdown | Expectancy | Costes ×2 | Estrés | Veredicto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A Momentum | `A_tsmom_L28_btcf1` | 1,65 | 0,19 / 1,08 | −8,38 % | −0,69 | 0,72 | −11,6 % | −5,23 USD | −9,83 % | −11,47 % | REJECTED (no pasó Validación) |
| B Donchian | `B_donchian_N20_trail3` | 1,07 | 0,04 / 1,00 | −2,06 % | −0,03 | 0,95 | −15,3 % | −1,06 USD | −4,34 % | −7,78 % | REJECTED (no pasó Validación) |
| C Early breakout | `C_early_p35_trail3` | 0,68 | −0,19 / 0,85 | −5,14 % | −0,21 | 0,81 | −13,4 % | −4,14 USD | −6,33 % | −7,51 % | REJECTED (no pasó Validación) |
| D Momentum por volatilidad | `D_volmom_L28` | 0,94 | 0,90 / 1,69 | −22,93 % | −0,94 | 0,68 | −34,2 % | −13,90 USD | −25,61 % | −28,90 % | REJECTED (0 de 9 criterios) |
| E Híbrida | `E_hybrid_N20_trail2.5` | 1,05 | 0,04 / 0,99 | −11,61 % | −0,59 | 0,69 | −16,2 % | −8,67 USD | −13,47 % | −15,67 % | REJECTED (no pasó Validación) |

Patrón: todas las familias ganaron en Desarrollo (mercado alcista de 2020-2021) y se desinflaron después.

Detalle de `D_volmom_L28` en el holdout: 165 operaciones, acierto 26,1 %, ganancia media 113 USD, pérdida media −59 USD,
13,2 días de media en posición, exposición media 8,9 %, rotación 4,2× al año, costes 343 USD. Por subperiodo: 2024-S2 +12,8 %,
2025 −11,3 %, 2026 −23,4 %. IC 90 % del Sharpe por bootstrap: [−2,34; 0,38]; p-valor 0,88.

## 5. Comparación con referencias (holdout 2024-07 a 2026-11)

| Referencia | Retorno | Sharpe | Drawdown máx. |
| --- | --- | --- | --- |
| Efectivo | 0,0 % | 0,00 | 0,0 % |
| BTC comprar y mantener | +2,0 % | 0,24 | −53,0 % |
| ETH comprar y mantener | −48,6 % | −0,07 | −67,6 % |
| Equiponderada top 50 | −85,5 % | −0,69 | −91,2 % |
| Mejor estrategia elegida (B) | −2,1 % | −0,03 | −15,3 % |

Las estrategias perdieron mucho menos que las altcoins en conjunto (el control de riesgo funciona como defensa), pero
ninguna superó al efectivo ni a BTC. Defenderse no es una ventaja: el efectivo lo hace gratis.

## 6. Evidencia estadística

- Bootstrap por bloques estacionario (bloque medio 20 días, 5 000 réplicas) sobre retornos diarios del holdout.
- p-valores (media > 0) de las 5 elegidas: A 0,85 · B 0,50 · C 0,60 · D 0,88 · E 0,78. Holm aplicado solo a D (la única que llegó al holdout como candidata): 0,88.
- El menor p-valor de las 23 configuraciones es 0,40 (`B_donchian_N90_exitchan`); con Bonferroni (×23) es 1.
- Walk-forward anual 2022-2026 (re-elige cada año con los 2 previos): A −8,8 %, B −3,7 %, C −17,1 %, D −7,8 %, E −13,0 %.

## 7. Riesgo de manipulación

Módulo `radar/edge/manip.py`: puntaje 0-100 con volumen anormal (últimos 10 días), subida vertical con poca liquidez,
pico de volumen seguido de reversión, mechas superiores y rango amplio sin volumen. Libro histórico y holders: N/D.
Es una sospecha, no una prueba.

Efecto como filtro (no entrar con puntaje ≥ 60) sobre `D_volmom_L28`: en Validación, ninguno (Sharpe 0,90 igual);
en el holdout, −21,6 % con filtro frente a −22,9 % sin él. Mejora mínima y no significativa: no convierte la estrategia en rentable.

Cambio declarado: antes del holdout se amplió el componente de volumen anormal a "máximo de los últimos 10 días"
porque una prueba unitaria mostró que el puntaje nunca combinaba el pico de volumen con la reversión. El cambio se hizo
tras ver la Validación (donde el filtro no tuvo efecto) y no afectó a la selección.

## 8. Pruebas adicionales (información)

- Universo alternativo de 50 monedas, `D_volmom_L28` en el holdout: +7,2 %, Sharpe 0,34, PF 1,16. No cumple el Sharpe > 0,75
  y elegir el universo después de ver el holdout sería sobreajuste; se reporta solo como sensibilidad.
- Resultados completos por año, régimen de BTC y motivo de salida: `results/holdout_results.json`.

## 9. Integración con Crypto Radar

No se integra ninguna señal nueva: ninguna estrategia fue aceptada. El motor original sigue intacto.
Si se quiere seguir investigando, el siguiente paso honesto es **paper trading hacia adelante** de 1 o 2 hipótesis
fijadas hoy (por ejemplo la familia D y Donchian 90), sin mostrarlas como recomendaciones, durante al menos 6 meses:
es el único holdout realmente limpio.

## 10. Reproducir

```
python3 research/edge/fetch_delisted.py          # pares retirados (archivo público de Binance)
python3 research/edge/run.py devval              # Desarrollo + Validación, congela la selección (~15 s)
python3 research/edge/run.py holdout             # Holdout: una sola vez
python3 tests/test_edge.py -v                    # 29 pruebas del laboratorio
```

Archivos en `research/edge/results/`: `comparativa_23_configuraciones.csv` (todas las configuraciones, periodos y
escenarios de coste), `holdout_estadistica.csv`, `benchmarks.csv`, `walk_forward.csv`, `holdout_operaciones.csv` y
`desarrollo_validacion_operaciones.csv` (cada operación), `holdout_curvas.csv` (curva diaria) y `holdout_results.json`.
Cada resultado neto se reproduce sumando `pnl_usd` del registro de operaciones (comprobado: `D_volmom_L28` −2 293,38 USD
en operaciones y en la curva).

## 11. Limitaciones

- El holdout histórico no es virgen: en este proyecto ya se habían mirado 2024-2026 con otras estrategias.
  Esto juega a favor de encontrar algo, y aun así no apareció nada.
- Solo velas diarias de Binance; sin libro histórico ni spread real.
- Riesgo pre-registrado conservador (0,5 % por operación, ~9 % de exposición media): con más riesgo las pérdidas serían mayores, no menores, porque la expectancy es negativa.
- 23 configuraciones no agotan el espacio de estrategias. El resultado dice que estas familias clásicas, con estos datos y costes, no muestran ventaja.
