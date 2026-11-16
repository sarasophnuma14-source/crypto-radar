# Pre-registro v3 de la investigación de edge

Este documento se escribe y se publica en un commit **antes** de ejecutar cualquier experimento de esta ronda.
- Fecha: 2026-11-16.
- Rama: `claude/investigacion-edge`.
- Cualquier cambio posterior queda en el historial de git y se explica en `docs/INFORME_INVESTIGACION_EDGE.md`.

## 0. Contexto honesto

- **Ya se miraron todos los periodos históricos disponibles.**
  - El backtest del motor 2.0 cubrió 2020 a 2026.
  - El pre-registro v1 (`research/edge/PREREGISTRO.md`) usó 23 configuraciones. Su holdout, de 2024-07 a 2026-11,
    se gastó una vez: todas las familias RECHAZADAS.
  - La auditoría v2 de D_volmom repasó ese mismo holdout de forma exploratoria.
- **Consecuencia:** el holdout de esta ronda **no es virgen**. Se ejecuta una vez y con todo congelado, pero el
  conocimiento previo del investigador sobre esos años puede sesgar las hipótesis.
- **La única muestra realmente independiente es el futuro:** paper trading desde 2026-11-16. Ninguna estrategia
  puede pasar a producción sin superarla.
- **Número de pruebas que se declaran para el Deflated Sharpe:**
  - N = 35 configuraciones nuevas + 23 de v1 = **58**;
  - como sensibilidad, N = 100, que cubre la calibración del motor 2.0, de tamaño no documentado.
- **No se modifican:**
  - `radar/quant/`, `radar/edge/`, `radar/paper_trading/`;
  - el ledger (`research/edge/ledger/ledger.jsonl`);
  - los datos existentes de `data/research/`.

  El código nuevo vive en `research/edge3/`. Los datos nuevos (funding y velas de perpetuos) se **añaden** en
  `data/research/funding/`.

## 1. Datos

**Spot.** El mismo panel diario de Binance Spot en USDT, con las retiradas incluidas (`radar.edge.data.build()` y
`drop_stables()`, solo lectura), de 2020-01-01 a 2026-11-14. Ya excluye:
- stablecoins, tokens apalancados, envueltos y acciones tokenizadas;
- las series con huecos de más de 7 días, que se parten en dos activos.

**Perpetuos USDT-M.** Funding cada 8 h y velas diarias del archivo público `data.binance.vision`, para las monedas
que estuvieron alguna vez entre las 30 de mayor volumen spot a fin de mes. Hay un manifiesto SHA-256 de cada zip.

**Universo de cada día t.** Se calcula solo con datos hasta el cierre de t−1:
- historia mínima de H días (180 por defecto, 365 en F3);
- volumen medio de 30 días ≥ 5 M USD (2 M en F3);
- ranking por ese volumen.

Así, una moneda no entra antes de existir ni antes de tener liquidez. Las retiradas permanecen en el histórico.

**Auditoría de datos, previa a los experimentos.** Se publica en `docs/VALIDACION_ESTADISTICA.md` §1:
- velas faltantes, duplicadas y fuera de la medianoche UTC;
- incoherencias OHLC;
- retornos extremos y días con volumen cero;
- cobertura del funding;
- comparación del precio de cierre de BTC y ETH con otro exchange, si es accesible (Coinbase o Kraken).

## 2. Cortes cronológicos

| Conjunto | Fechas | Uso |
| --- | --- | --- |
| Desarrollo | 2020-01-01 a 2023-06-30 | Elegir **una** configuración por familia |
| Validación | 2023-07-01 a 2025-03-31 | Filtro: sigue adelante si Sharpe > 0,5 y retorno > 0 |
| **Holdout** | **2025-04-01 a 2026-11-14** | **Una sola ejecución**, con todo congelado y un hash en `HOLDOUT_V3.lock` |
| Walk-forward | Ventanas semestrales de 2021-07 a 2025-03 | Solo información: cada semestre elige la mejor configuración de la familia con los 18 meses anteriores |

Hay 1 día de embargo entre conjuntos: las señales del primer día de cada conjunto usan datos anteriores, como en
producción, pero las métricas solo cuentan días dentro del conjunto.

## 3. Hipótesis y familias: lista cerrada, 35 configuraciones

Reglas comunes a todas las configuraciones:
- solo largo en spot, salvo F6a, que va corto en el perpetuo como cobertura;
- sin apalancamiento: exposición bruta ≤ 1;
- señal con el cierre de t−1 y ejecución a la apertura de t.

| Familia | Hipótesis | Configuraciones |
| --- | --- | --- |
| **F1 · Momentum de serie temporal** | H1: funciona mejor con filtro de régimen; H5: el filtro de liquidez reduce las señales falsas | Universo top 30. Largo si el retorno de L días es > 0. Peso por paridad de riesgo (1/vol de 60 días), máximo 20 % por activo. Rebalanceo semanal, el lunes. L ∈ {30, 90, 180} × filtro BTC > media de 200 días ∈ {no, sí} = 6. Más 1 variante de liquidez: L = 90, filtro BTC, top 20 con volumen ≥ 50 M. **7** |
| **F2 · Momentum transversal gestionado por riesgo** | Momentum transversal con volatilidad escalada (Barroso y Santa-Clara; *Cryptocurrency Market Risk-Managed Momentum*, 2025) | Universo top 50. Ranking por el retorno de L días sin el último día. Las 10 mejores a peso igual. Rebalanceo semanal. L ∈ {7, 28, 90} × escalado ∈ {ninguno, volatilidad objetivo del 40 % con la volatilidad realizada de 30 días de la propia cartera, tope 1} = **6** |
| **F3 · Tendencia con conjunto de canales Donchian** | H2: rupturas Donchian con tamaño por volatilidad (réplica de *Catching Crypto Trends*, Zarattini, Pagani y Barbon, 2025) | Lookbacks {5, 10, 20, 30, 60, 90, 150, 250, 360}. Por cada uno: entrada si el cierre supera el máximo de N cierres previos; *trailing stop* = max(stop anterior, punto medio del canal). Señal = media de los estados. Tamaño = 25 % / vol de 90 días. Bruto ≤ 1 (el artículo permite 200 %). Universo ∈ {solo BTC, top 20 con ≥ 365 días}; rebalanceo ∈ {diario, banda: solo si el peso objetivo se aleja más de un 25 % relativo} = **4** |
| **F4 · Reversión a la media** | H3: solo funciona en ciertos regímenes | Universo top 50. Compra las 5 con peor retorno de k días. Cohortes solapadas de 3 días. k ∈ {3, 7} × filtro BTC > media de 200 días ∈ {no, sí} = **4** |
| **F5 · Volatilidad** | Volatilidad objetivo y expansión de volatilidad | (a) BTC con peso min(1, 40 % / vol30), sin filtro y con filtro de media de 200 días = 2. (b) Top 10 a peso igual con volatilidad objetivo del 40 % de la cartera = 1. (c) Expansión: vol7/vol90 > 1,5, retorno de 7 días > 0 y cierre > máximo de 20 días; salida con cierre < media de 20 días; tamaño por volatilidad; universo top 30 = 1. **4** |
| **F6 · Funding y basis** | H4: el funding mejora la selección | (a) *Carry* neutral: largo spot y corto perpetuo en las monedas con perpetuo. Entra si el funding medio de 3 días, anualizado, supera el umbral; sale si es < 0. Umbral ∈ {0 %, 10 %} × universo ∈ {BTC + ETH, top 10 con perpetuo} = 4. (b) F1 con L = 90 y filtro BTC, excluyendo el 20 % del universo con el funding de 7 días más alto (posiciones saturadas) = 1. (c) Contrario: las 5 con el funding de 7 días más negativo del top 30, semanal, con filtro BTC = 1. **6** |
| **F7 · Régimen adaptativo** | H7: lo adaptativo supera a lo estático | (a) BTC > media de 200 días y vol30 ≤ su mediana expandida → F1 con L = 90; BTC > media de 200 días y vol alta → F4 con k = 3; BTC < media de 200 días → efectivo. (b) Igual, pero con un régimen solo por volatilidad: vol baja → F1 con L = 90, vol alta → efectivo. **2** |
| **F8 · Conjunto** | H6: combinar señales independientes mejora la estabilidad fuera de muestra | Componentes fijados **a priori**, no por resultados: F1 (L = 90, filtro BTC), F3 (top 20, diario), F5a (BTC sin filtro) y F6a (umbral 10 %, top 10). Mezcla ∈ {capital igual, inverso de la volatilidad de 60 días de cada componente} = **2**. La principal es la de capital igual |

Benchmarks congelados (`research/edge3/benchmark/`, con SHA-256):
- **Crypto Radar actual:** la curva del motor 2.0 (`backtest_pro`, de 2020-07-19 a 2026-11-14, costes de 0,1 + 0,1 +
  0,1 % por lado, sin recalcular).
- **D_volmom_L28 v2:** la estrategia del paper trading. Curvas de la auditoría v2.
- **Comprar y mantener:** BTC y ETH.
- **Cartera equiponderada:** top 50 por volumen, rebalanceo mensual, con los mismos costes que el motor nuevo.
- **Efectivo:** 0 %.

## 4. Motor (`research/edge3/engine.py`, igual para todas)

**Ejecución.** A la apertura del día siguiente a la señal. Prueba de latencia: un día más tarde. Nunca se ejecuta al
máximo ni al mínimo de la vela.

**Costes por lado en spot (escenario BASE, *taker*).** Comisión del 0,10 % más medio *spread* y deslizamiento según el
volumen de 30 días:

| Volumen de 30 días | Medio *spread* | Deslizamiento |
| --- | --- | --- |
| > 50 M | 0,02 % | 0,05 % |
| 5 a 50 M | 0,05 % | 0,15 % |
| < 5 M | 0,15 % | 0,30 % |

A eso se suma un impacto de 0,10 % × √(orden / (1 % del volumen)).

**Costes del perpetuo.**
- Comisión del 0,05 % más la mitad del deslizamiento spot del mismo tramo.
- El funding real se cobra o se paga sobre el nocional corto.
- El margen del corto se cubre con un 50 % del nocional en efectivo, sin rendimiento: capital usado = 1,5 × nocional.

**Escenarios de coste.** ELEVADO multiplica todos los costes por 2 y ESTRÉS por 3. MAKER (0,02 %, sin *spread*) solo
se informa.

**Liquidez.** Una orden no supera el 1 % del volumen medio de 30 días. El resto queda pendiente para el día siguiente
(ejecución parcial).

**Retirada.** Si un activo deja de cotizar para siempre, se vende al último cierre con un 10 % de descuento (30 % en
ESTRÉS).

**Límites.** Sin apalancamiento. Máximo de 20 % por activo, salvo en las familias de un solo activo (BTC). El efectivo
no rinde nada.

**Contabilidad.** Curva diaria al cierre. Una operación es un episodio por activo, desde que su peso pasa de 0 a > 0
hasta que vuelve a 0, con su PnL neto de costes.

**Pruebas del motor.** Antes de cualquier resultado: sin anticipación (una señal que mira el futuro debe detectarse),
costes, ejecución parcial y retiradas (`research/edge3/test_engine.py`).

## 5. Selección

1. **Desarrollo.** Por familia, la configuración con mayor Sharpe en BASE, con ≥ 30 episodios. F8 no se selecciona:
   cuenta la de capital igual.
2. **Validación.** Sigue si el Sharpe es > 0,5 y el retorno > 0.
3. **Holdout.**
   - Las que siguen se congelan y se ejecutan una vez.
   - En la misma ejecución se calculan las 35, solo como información.
   - Si ninguna sigue, el holdout se ejecuta igualmente para informar, y el veredicto es NO EDGE.

## 6. Criterios de EDGE (no se cambian después)

Se evalúan sobre la configuración congelada de cada familia.

| # | Criterio |
| --- | --- |
| C1 | Retorno neto en el holdout > 0 (BASE) |
| C2 | Sharpe del holdout > 0,75 **y** mayor que el de BTC comprar y mantener, la cartera equiponderada y el Crypto Radar actual en el mismo periodo |
| C3 | Drawdown máximo del holdout ≤ 30 % |
| C4 | Factor de beneficio de los episodios del holdout > 1,15 y ≥ 30 episodios |
| C5 | ELEVADO: retorno del holdout > 0. ESTRÉS: Sharpe > 0 |
| C6 | Bootstrap estacionario (bloque medio de 20 días, 5 000 réplicas) sobre los retornos diarios del holdout: p de Holm entre las familias que llegan al holdout < 0,05, y límite inferior del IC 90 % del Sharpe > 0 |
| C7 | Deflated Sharpe Ratio (Bailey y López de Prado, 2014) sobre validación + holdout con N = 58 y la varianza de los Sharpe de desarrollo de las 35: DSR > 0,95. Como información, también con N = 100 |
| C8 | PBO por CSCV (S = 16 bloques sobre desarrollo + validación, configuraciones de la familia) < 0,5. Solo familias con ≥ 4 configuraciones; en las demás se marca N/A |
| C9 | Sin el activo que más aporta, el PnL del holdout sigue > 0 (no aplica a las de un solo activo, que entonces **fallan** este criterio por depender de una moneda) |
| C10 | Retorno > 0 en al menos 2 de 3 subperiodos fuera de muestra: 2023-07 a 2024-06, 2024-07 a 2025-03 y el holdout |
| C11 | Estabilidad: al menos la mitad de las configuraciones de la familia con Sharpe de validación > 0 |
| C12 | Latencia de un día más: retorno del holdout > 0 |

Veredicto por familia:
- **EDGE CANDIDATA:** cumple C1 a C12. Aun así, no va a producción sin paper trading de ≥ 183 días y revisión
  independiente.
- **PROMETEDORA:** cumple C1 a C3 y al menos 8 de los 12.
- **RECHAZADA:** el resto.

**Datos insuficientes:** menos de 30 episodios en el holdout. Si ninguna familia queda como EDGE CANDIDATA, el informe
dice **NO EDGE**.

## 7. Información adicional (no cambia la selección)

- Métricas completas:
  - CAGR, retorno neto, Sharpe, Sortino, Calmar, factor de beneficio y drawdown máximo;
  - volatilidad, porcentaje de aciertos, ganancia y pérdida medias, *expectancy* y número de episodios;
  - rotación, exposición, tiempo en el mercado, costes y deslizamiento;
  - PnL por activo y por régimen de BTC: tendencia alcista o bajista según la media de 200 días, y volatilidad alta o
    baja.
- Escenario MAKER.
- Capital de 1 M USD, para ver la capacidad cuando la ejecución parcial empieza a pesar.
