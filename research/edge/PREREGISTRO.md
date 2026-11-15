# Pre-registro de la investigación de ventaja (escrito ANTES de ejecutar cualquier prueba)

Fecha: 2026-11-15 · Rama `claude/project-thread-i8udp5`. Este archivo se publica en un commit antes del primer
resultado; cualquier cambio posterior quedará en el historial de git y se explicará en el informe.

## 1. Datos
- Panel diario de Binance Spot, pares USDT, 2020-01-01 a 2026-11-14 (`data/research/panel.json.gz`, 661 monedas:
  469 activas y 192 pausadas/retiradas que la API aún publica) + archivo público `data.binance.vision` para las
  retiradas por completo (`panel_delisted.json.gz`). Volumen en USDT.
- Excluidos: stablecoins, tokens apalancados (UP/DOWN/BULL/BEAR), envueltos (WBTC, WBETH, BNSOL) y acciones
  tokenizadas (sufijo B en el archivo de 2026).
- Una serie con un hueco de más de 7 días se parte en dos activos (p. ej. LUNA antigua y LUNA 2.0): la primera parte
  se trata como retirada en su último cierre. Nunca se rellenan datos faltantes.
- Coinbase, Kraken, OKX: no se usan (sin pares comparables en USDT y sin tiempo para unir libros); se registra la ausencia.
  Bybit: bloqueado (HTTP 403) desde este entorno. Sin spread histórico ni libro histórico: se modelan por tramos de liquidez.

## 2. Cortes cronológicos
| Conjunto | Fechas |
| --- | --- |
| Desarrollo | 2020-01-01 a 2022-12-31 (las señales empiezan cuando hay historia suficiente) |
| Validación | 2023-01-01 a 2024-06-30 |
| Holdout final | 2024-07-01 a 2026-11-14 · se ejecuta UNA vez, con todo congelado |

Advertencia honesta: en este proyecto ya se miraron antes 2024-2026 (backtest del motor 2.0) y 2025-2026 (laboratorio
anterior con rupturas y momentum). Las estrategias y parámetros de este pre-registro no se ajustaron con esos
resultados, pero el holdout histórico no es virgen. El único holdout realmente limpio será el paper trading futuro.

## 3. Estrategias (lista cerrada, 23 configuraciones)
Todas: solo largo spot, señal al cierre de D, ejecución a la apertura de D+1.
- **A. Momentum de serie temporal** (rebalanceo semanal, lunes): retorno de L días > 0 y cierre > media de L días;
  ranking por retorno/volatilidad; top 5. L ∈ {28, 56, 84} × filtro semanal de BTC (cierre semanal > media de 20 semanas) ∈ {sí, no} → 6.
- **B. Donchian**: entrada si cierre > máximo de N días previos; N ∈ {20, 55, 90}; salida ∈ {canal mínimo de N/2 días,
  trailing 3 ATR} → 6.
- **C. Early breakout**: ancho de Bollinger(20) en el percentil ≤ p de 120 días durante alguno de los 10 días previos,
  volumen 10 d / 60 d ≥ 1,2, cierre > máximo de 55 días, fuerza relativa 28 d frente a BTC > 0, cierre ≥ 0,85 × máximo de 365 d
  no exigido (se mide la distancia, no filtra); p ∈ {20, 35} × salida ∈ {trailing 3 ATR, tiempo 30 días + stop} → 4.
- **D. Momentum gestionado por volatilidad**: como A con L ∈ {28, 56, 84}, tamaño inverso a la volatilidad con objetivo
  de 40 % anual de cartera, exposición a la mitad si BTC < media de 200 d y salida total a efectivo si BTC cae > 15 % en 7 días → 3.
- **E. Híbrida**: activo con cierre semanal > media de 10 semanas, BTC con cierre semanal > media de 20 semanas, compresión
  (percentil ≤ 35), ruptura Donchian N ∈ {20, 55}, fuerza relativa 28 d > 0, trailing ATR k ∈ {2,5, 3,5} → 4.

## 4. Simulador y riesgo (iguales para todas)
- Capital 10 000 USD, riesgo 0,5 % por operación (stop inicial 3 ATR(14) salvo trailing propio), exposición máxima 15 %
  por activo, máximo 5 posiciones, riesgo abierto total ≤ 3 %, sin apalancamiento. Riesgo a la mitad si BTC < media de 200 d.
- Universo de cada día: 150 monedas con mayor volumen medio de 30 días en esa fecha, mínimo 2 M USD/día y 120 velas.
- Liquidez: una orden no supera el 1 % del volumen medio diario de 30 días (ejecución parcial). Se cancela la entrada si
  la apertura de D+1 supera el cierre de D en más de 1 ATR.
- Stops intradía; hueco bajo el stop = venta a la apertura; el stop se revisa también el día de entrada.
- Activo retirado: venta al último cierre con descuento del 10 % (estrés: 30 %).
- Costes por lado según volumen medio de 30 días: > 50 M: 0,10 % comisión + 0,02 % medio spread + 0,05 % deslizamiento;
  5-50 M: 0,10 + 0,05 + 0,15 %; < 5 M: 0,10 + 0,15 + 0,30 %. Escenarios: BASE ×1, ELEVADO ×2, ESTRÉS ×3 (y descuento de retirada 30 %).
- Sin financiación (spot sin apalancamiento: coste 0).

## 5. Protocolo de selección
1. En Desarrollo, por familia, se elige la configuración con mayor Sharpe con costes BASE y ≥ 30 operaciones.
2. Esa configuración pasa a Validación. Sigue adelante si en Validación tiene retorno > 0, PF > 1,15 y Sharpe > 0,75 con costes BASE.
3. Las que pasan se congelan y van al Holdout (una ejecución). Para transparencia, en esa misma ejecución se calculan
   las 23 configuraciones, pero solo cuenta la congelada de cada familia.
4. Comparaciones múltiples: corrección de Holm sobre los p-valores del bootstrap de las familias que llegan al holdout
   (y Bonferroni sobre las 23 configuraciones como referencia).

## 6. Criterios de aceptación en el Holdout (no se cambian después)
1. Retorno neto > 0 con costes BASE.
2. Expectancy por operación > 0 después de costes.
3. Profit factor > 1,15.
4. Sharpe diario anualizado (√365) > 0,75.
5. Drawdown máximo ≤ 25 %.
6. Retorno > 0 en al menos 2 de 3 subperiodos (2024-S2, 2025, 2026) y también en Validación.
7. Con costes ELEVADOS: retorno > 0 y PF > 1,0.
8. Sin las 5 mejores operaciones, el resultado neto sigue > 0; al menos 30 operaciones.
9. Bootstrap por bloques estacionario (bloque medio 20 días, 5 000 réplicas) sobre retornos diarios: p-valor de media > 0
   corregido por Holm < 0,05 y límite inferior del IC 90 % del Sharpe > 0.

ACCEPTED: cumple 1-9. PROMISING: cumple 1-4 y falla alguno de 5-9. INSUFFICIENT DATA: < 30 operaciones.
REJECTED: el resto. Si ninguna queda ACCEPTED, el informe dirá que no se encontró ventaja.

## 7. Pruebas adicionales (información, no cambian la selección)
Walk-forward anual (elige la mejor configuración de cada familia con los 2 años previos), parámetros vecinos en
Validación, universo alternativo de 50 monedas en el Holdout, resultados por año y por régimen de BTC, comparación con
BTC y ETH comprar y mantener, cartera equiponderada (top 50 por volumen, rebalanceo mensual) y efectivo.

## 8. Riesgo de manipulación
Puntaje 0-100 solo con OHLCV diario (volumen anormal, rango sin volumen, pico de volumen con reversión, subida vertical
con poca liquidez, mechas). Libro histórico y concentración de holders: N/D. Se evalúa como filtro (no entrar si ≥ 60)
primero en Validación y luego, una vez, en el Holdout como comparación secundaria. Es una sospecha, nunca una prueba.
