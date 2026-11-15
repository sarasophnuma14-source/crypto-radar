# BACKTEST_REPORT — Crypto Radar 2.0

Generado el 2026-11-15 con `python3 research/backtest_pro_run.py` (motor `radar/quant/backtest_pro.py`).
Resultados completos: `docs/backtest_results.json` (los sirve el panel en Backtesting). Operación por operación y curva
diaria: `data/research/backtest_pro_trades.csv` y `backtest_pro_curve.csv` (se regeneran con el mismo comando).

## Veredicto

**La estrategia NO supera la validación fuera de muestra y los pesos del puntaje NO están validados estadísticamente.**

- En el periodo de diseño (2020-07 a 2023-12) gana: +44,7 %, profit factor 1,44, Sharpe 1,09.
- En el periodo que el sistema no vio (2024-01 a 2026-11) pierde: −18,6 %, profit factor 0,72, Sharpe −0,79.
- La calibración de parámetros mejora el periodo de diseño (Sharpe 1,36) y empeora el periodo nuevo (Sharpe −0,96).
  Es sobreajuste.
- El walk-forward anual (re-calibra cada año con los 2 años anteriores y opera el siguiente) encadena **−29,4 %** de 2022 a 2026.
- Comprar y mantener BTC dio +596,6 % en el periodo completo (con caídas de −76,6 %). La estrategia, +25,8 % con
  caída máxima de −26,6 %.
- El puntaje no ordena bien las oportunidades: su correlación de rango con el exceso de retorno a 20 días es
  **negativa** dentro y fuera de muestra (−0,09 y −0,06).

Conclusión operativa: el radar sirve como herramienta de análisis y gestión del riesgo (stops, tamaño, régimen,
manipulación), pero **no hay evidencia de que sus señales de compra tengan ventaja**. No se debe vender con cifras de
rentabilidad ni prometer resultados. Ver "Qué hacer ahora" al final.

## Metodología

| Aspecto | Cómo se hizo |
| --- | --- |
| Datos | Velas diarias de 661 pares spot USDT de Binance (activos, pausados y retirados que aún publica la API), 2020-07-19 a 2026-11-14 |
| Universo | Cada día, las 150 monedas con más volumen medio de 30 días **en esa fecha**, con al menos 120 velas y 1 M$/día |
| Señal | El mismo `engine.analyze` del escáner en vivo, solo con velas cerradas hasta el día t |
| Ejecución | Orden desde la apertura de t+1. Límite: se llena a `min(apertura, límite)`. Stop-buy de ruptura: a `max(apertura, disparo)`. Validez 3 días |
| Costes | Comisión 0,10 % + deslizamiento 0,10 % + medio spread (0,05 %) por lado |
| Stops | Se comprueba el stop la misma vela del llenado. Un hueco bajo el stop se vende a la apertura. Si una vela toca stop y objetivo, se asume el stop (pesimista) |
| Salidas | TP1 y TP2 parciales (33 % cada uno), stop a la entrada tras TP1, TP3 o salida del motor Exit Intelligence a la apertura siguiente |
| Cartera | 10 000 USD, riesgo 1 % por operación, máximo 6 posiciones, límites por activo, categoría, correlación y riesgo abierto. Freno por drawdown con pausa de 30 días |
| Moneda retirada | Sale al último cierre −10 % |
| Fuera de muestra | Corte fijo el 2024-01-01 |
| Walk-forward | Cada año de 2022 a 2026: elige la mejor de 40 combinaciones (Sharpe, mínimo 30 operaciones) en los 2 años previos y la opera ese año |

## Resultados

| Periodo | Retorno | CAGR | Operaciones | Acierto | Profit factor | R medio | Sharpe | Drawdown máx. | BTC comprar y mantener |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Completo 2020-07 → 2026-11 | +25,75 % | 3,69 % | 599 | 35,4 % | 1,13 | 0,03 | 0,43 | −26,61 % | +596,6 % |
| Diseño 2020-07 → 2023-12 | +44,74 % | 11,31 % | 311 | 38,9 % | 1,44 | 0,14 | 1,09 | −24,99 % | +359,2 % |
| Fuera de muestra 2024-01 → 2026-11 | **−18,61 %** | −6,92 % | 290 | 30,7 % | **0,72** | −0,11 | **−0,79** | −20,29 % | +45,2 % |

Exposición media: 9,4 % del capital. Comisiones pagadas en el periodo completo: 473 USD. El freno por drawdown se activó 2 veces.

### Calibración (40 combinaciones)

Mejor combinación en el periodo de diseño: puntaje mínimo sin cambio, sin Exit Intelligence, órdenes de 2 días, riesgo 0,75 %.

| | Retorno | Profit factor | Sharpe | Drawdown máx. |
| --- | --- | --- | --- | --- |
| Diseño | +52,91 % | 1,72 | 1,36 | −10,64 % |
| Fuera de muestra | −18,82 % | 0,61 | −0,96 | −23,04 % |

### Walk-forward anual

| Año | Retorno | Profit factor | Operaciones | BTC ese año |
| --- | --- | --- | --- | --- |
| 2022 | −15,84 % | 0,13 | 45 | −65,3 % |
| 2023 | +11,26 % | 1,43 | 73 | +154,5 % |
| 2024 | −4,72 % | 0,83 | 73 | +111,8 % |
| 2025 | −14,97 % | 0,28 | 55 | −7,3 % |
| 2026 | −6,87 % | 0,56 | 40 | −27,8 % |
| **Encadenado** | **−29,35 %** | | | |

Lo único positivo de 2022: perdió mucho menos que BTC (−15,8 % frente a −65,3 %) porque el régimen redujo la exposición.

### Sensibilidad (periodo completo)

| Escenario | Retorno | Profit factor | Sharpe | Drawdown máx. |
| --- | --- | --- | --- | --- |
| Base | +25,75 % | 1,13 | 0,43 | −26,61 % |
| Costes ×2 | +9,17 % | 1,05 | 0,19 | −33,95 % |
| Deslizamiento 0,3 % | +11,19 % | 1,06 | 0,22 | −32,76 % |
| Sin costes (irreal) | +26,40 % | 1,13 | 0,45 | −26,48 % |
| Máximo 3 posiciones | +15,02 % | 1,14 | 0,39 | −17,83 % |
| Máximo 10 posiciones | +17,94 % | 1,06 | 0,25 | −34,63 % |
| Sin objetivos parciales | +33,21 % | 1,20 | 0,46 | −28,22 % |
| Sin Exit Intelligence | +25,07 % | 1,15 | 0,42 | −25,90 % |
| Puntaje mínimo +10 | +34,09 % | 1,18 | 0,53 | −27,48 % |
| Puntaje mínimo −10 | +22,19 % | 1,12 | 0,39 | −22,28 % |
| Riesgo 2 % por operación | +62,96 % | 1,12 | 0,49 | −42,38 % |
| Órdenes válidas 1 día | +26,84 % | 1,15 | 0,46 | −26,53 % |

Con costes realistas algo peores, el margen casi desaparece. Subir el umbral +10 parece mejor en el periodo completo,
pero esa mejora viene del periodo de diseño y no aguanta fuera de muestra (ver calibración).

### De dónde sale el resultado (periodo completo)

| Salida | Operaciones | Resultado |
| --- | --- | --- |
| Stop | 224 | −14 798,52 USD |
| Stop el mismo día de la entrada | 10 | −707,74 USD |
| TP3 | 66 | +13 802,13 USD |
| Stop a la entrada tras TP1 | 52 | +2 448,94 USD |
| Exit Intelligence: cerrar | 242 | +1 817,27 USD |
| Fin del periodo | 5 | +13,15 USD |

| Fase de entrada | Operaciones | Resultado | Acierto |
| --- | --- | --- | --- |
| BREAKOUT | 414 | +3 044,44 USD | 37,0 % |
| ACCUMULATION | 57 | +954,63 USD | 43,9 % |
| PRE-EXPLOSION | 28 | +249,36 USD | 28,6 % |
| MOMENTUM | 100 | −1 673,20 USD | 26,0 % |

| Régimen | Operaciones | Resultado |
| --- | --- | --- |
| BULLISH | 118 | +1 821,93 USD |
| HIGH VOLATILITY | 52 | +1 004,87 USD |
| BEARISH | 84 | +51,36 USD |
| NEUTRAL | 343 | −296,52 USD |
| CAPITULATION | 2 | −6,41 USD |

El beneficio depende de pocas operaciones que llegan a TP3. MOMENTUM pierde dinero de forma sistemática.

## Validación del puntaje (por qué los pesos no están validados)

Se tomó una muestra cada 5 días de todas las monedas del universo (34 767 observaciones en diseño y 30 513 fuera de
muestra) y se midió el exceso de retorno a 20 días frente a BTC según el puntaje.

| Familia | Correlación de rango (diseño) | Fuera de muestra |
| --- | --- | --- |
| Puntaje total | −0,091 | −0,060 |
| Estructura | −0,067 | −0,020 |
| Volumen | −0,065 | −0,079 |
| Tendencia | −0,118 | −0,076 |
| Momentum | −0,055 | −0,060 |
| Fuerza relativa | −0,084 | −0,064 |
| Liquidez | −0,065 | +0,034 |
| Ruptura | +0,062 | +0,000 |

Exceso de retorno medio por quintil de puntaje fuera de muestra (1 = más bajo): +0,06 %, +0,22 %, +0,12 %, −0,89 %, +0,48 %.
No hay una escalera creciente: un puntaje más alto no anticipa mejores resultados.

Por fase, fuera de muestra: BREAKOUT +2,50 % de exceso a 20 días (989 casos), OVEREXTENDED −4,65 % (1 564 casos, el
filtro de "no perseguir" sí acierta), PRE-EXPLOSION −2,28 % (203 casos).

Los pesos de las 7 familias siguen siendo los de la especificación original. Ajustarlos para que esta tabla salga
positiva sería sobreajuste a menos que se valide en un periodo nuevo.

## Limitaciones

- **Sesgo de supervivencia residual**: las monedas que Binance eliminó por completo de la API no están en el panel.
  Probablemente eran perdedoras, así que el resultado real sería algo peor.
- Velas diarias: dentro del día no se sabe qué tocó primero; se asume lo peor.
- Liquidez: no se modela el impacto en el libro de órdenes más allá del deslizamiento fijo.
- Los datos de manipulación del libro de órdenes y on-chain no existen en histórico; el backtest usa solo la parte de precio y volumen.
- 2022-2026 incluye un mercado bajista fuerte y una recuperación liderada por BTC, donde las altcoins rindieron poco.

## Qué hacer ahora

1. No publicar cifras de rentabilidad en la web de ventas. Vender el producto como herramienta de análisis y gestión del riesgo.
2. Probar las señales en modo papel (la cartera ya permite operaciones simuladas) durante al menos 3 meses.
3. Investigar una versión centrada en rupturas (la única familia con señal positiva en diseño) y validarla en un periodo nuevo antes de usarla.
4. Retirar MOMENTUM como fase de compra o exigirle más confirmación.
