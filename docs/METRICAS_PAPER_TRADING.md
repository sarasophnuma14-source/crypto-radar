# Métricas de paper trading prospectivo

Se aplican a cada hipótesis registrada y a la referencia **D_volmom congelada**, que sigue siendo el benchmark de paper trading. D_volmom no se modifica, no se re-optimiza y no se sustituye. Su paper trading y su ledger existentes (`research/edge/ledger/`) no se tocan. El diario prospectivo es un archivo nuevo y separado.

## 1. Qué se registra por señal (`diario.py`)

`creada_utc` (reloj real), `barra` de decisión, `disponible_en` del último dato, `ejecutar_en`, pesos objetivo, contexto opcional, `a_tiempo` y la cadena de hash. Las señales tardías se guardan, pero no se ejecutan en la simulación.

## 2. Qué se calcula en cada punto de control

Todo sale del mismo motor, con los mismos costes, en el mismo periodo prospectivo, para la hipótesis, BTC comprar y mantener, el efectivo remunerado y D_volmom.

| Grupo | Métricas |
|---|---|
| Rentabilidad | Retorno total, CAGR, exceso sobre el efectivo remunerado (DTB3) |
| Riesgo | Volatilidad anual, max drawdown, Calmar |
| Riesgo ajustado | Sharpe, Sharpe en exceso sobre el efectivo, Sortino |
| Operaciones | Número de episodios independientes, acierto, esperanza por operación, factor de beneficio, ganancia y pérdida media |
| Costes | Comisión, spread, deslizamiento, impacto, funding, financiación y deslistado, por separado; resultado con costes ×2 |
| Concentración | Cuota del mejor activo y del mejor episodio; PnL sin el mejor activo |
| Estadística | z secuencial frente a la frontera O'Brien-Fleming, PSR, DSR con el N global, MinTRL, bootstrap estacionario, Holm y BH entre hipótesis |
| Integridad | `verify()` del registro y del diario, hash del código, señales a tiempo frente a tardías, guardias |

## 3. Calendario

| Punto | Días desde el registro | Frontera z | Uso |
|---|---|---|---|
| 1 | 90 | 3,78 | Solo aprueba un efecto enorme; se puede rechazar por futilidad fuerte (z < −1,645) |
| 2 | 183 | 2,54 | Aprobación o futilidad (z < 0) |
| 3 | 365 | 1,70 | Decisión final |

## 4. Separación de resultados

- Todos los resultados de este módulo son **simulados** (paper trading con datos públicos). No existe ningún resultado con dinero real, y ningún documento debe presentarlos como reales ni como promesa de rentabilidad.
- Las cifras del histórico explorado (antes del 2026-11-16) se etiquetan como **exploración** y nunca se mezclan con las prospectivas.
