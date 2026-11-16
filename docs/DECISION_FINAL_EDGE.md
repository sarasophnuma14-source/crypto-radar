# Decisión final de edge · 2026-11-16

## Veredicto: **NO EDGE**

No se ha encontrado ninguna estrategia con una ventaja estadística demostrable ni económicamente explotable. La
estrategia actual tampoco la demuestra.

| Pregunta | Respuesta | Evidencia |
| --- | --- | --- |
| ¿La estrategia actual demuestra edge? | **No.** El motor 2.0 da Sharpe −0,30 y CAGR −3,0 % fuera de muestra (2023-07 a 2026-11), y −0,15 en el holdout. D_volmom (paper trading) da −0,38 y −1,45 | `COMPARACION_ESTRATEGIAS.md` |
| ¿Existe una alternativa superior? | **No demostrada.** En el holdout, F1 (`tsmom_L30_btc`, +8,25 %, Sharpe 0,33) gana al motor 2.0 y a BTC. Pero había quedado fuera en la validación, su p de bootstrap es 0,30 y su DSR 0,00 | ídem, criterios C1 a C12 |
| ¿Supera costes reales? | Ninguna configuración congelada cumple C5. Con costes ×2, solo F1 sigue positiva (+2,1 %), y no pasó la validación | `VALIDACION_ESTADISTICA.md` §6 |
| ¿Supera las pruebas fuera de muestra? | **No.** Las 8 familias quedan RECHAZADAS o con DATOS INSUFICIENTES en el holdout. F3, F6 y F8 eran positivas en walk-forward antes de 2025 y no lo mantienen | ídem §4 y §6 |
| ¿Supera las pruebas de robustez? | **No.** DSR < 0,95 en todas: también con SR0 = 1,31 y con SR0 = 0. PBO ≥ 0,5 en F2, F4 y F5. Holm p = 1,00 | ídem §5 |
| Nivel de confianza | **Alto en el «no»** dentro de lo probado: 35 configuraciones de 8 familias, pre-registradas, con un holdout único y reproducible. **Bajo** como prueba de que no existe ninguna ventaja: un universo limitado a Binance spot y perpetuos, velas diarias, costes modelados y un holdout no virgen | — |
| ¿Qué es reproducible? | Todo. Una copia aislada repitió el desarrollo, la validación y el holdout con resultados idénticos | ídem §7 |

## Qué se hace

1. **Se conserva la estrategia actual sin cambios.** No se integra ninguna alternativa ni se crea una rama de
   implementación, porque ninguna superó los criterios (parte VII.J).
2. **No se comunica ninguna cifra de rentabilidad.** El producto se presenta como herramienta de análisis (R-12,
   G-26).
3. **La única prueba independiente que queda es el futuro.** Hay que arrancar el paper trading de D_volmom, ya
   congelado, en la instancia 2.1 cuando se despliegue, y cualquier estrategia nueva necesita un pre-registro nuevo
   con datos posteriores al 2026-11-16.
4. **Mejoras propuestas** (`INFORME_INVESTIGACION_EDGE.md` §7): costes medidos con libro de órdenes, varios
   exchanges, tipo sin riesgo como benchmark y ejecución *maker*.

## Limitaciones

- **Holdout no virgen.** El periodo de 2025-2026 se había visto en rondas anteriores.
- **Solo Binance.** Spot y perpetuos USDT-M, con velas diarias y sin intradía. El *spread* y el libro están modelados,
  no medidos.
- **Funding de noviembre de 2026.** Falta el de los 14 últimos días (2026-11-01 a 14), que se toma como 0.
- **Cambios de ticker.** Se tratan como retiradas con un descuento del 10 %.
- **Conjunto (F8).** Se aproxima combinando las curvas de los componentes, sin el coste de mover capital entre ellos.
- **Benchmark del motor 2.0.** Es la curva congelada; no se recalculó con el motor nuevo. Sus supuestos de llenado de
  órdenes límite pueden ser optimistas, lo que lo **favorece**.

## Revisión independiente

No se pide para ninguna estrategia, porque ninguna es candidata. Sí se recomienda que alguien ajeno revise el motor
(`research/edge3/engine.py`) y el pre-registro antes de usarlos en una ronda futura.
