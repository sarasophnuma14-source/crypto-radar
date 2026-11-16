# Informe de la investigación de edge cuantitativo · ronda v3

Fecha: 2026-11-16. Rama experimental: `claude/investigacion-edge`. **No** se ha integrado nada en producción.

**No se modificaron** `radar/quant/`, `radar/edge/`, `radar/paper_trading/`, el ledger, los datos históricos ni la
estrategia actual. Todo el código nuevo está en `research/edge3/`.

## 1. Resumen

Se probaron 35 configuraciones de 8 familias, pre-registradas antes de ver ningún resultado:
- momentum de serie temporal y transversal;
- tendencia con canales Donchian;
- reversión a la media;
- volatilidad;
- funding y basis;
- régimen adaptativo;
- conjunto.

Todas pasaron por el mismo motor, con costes realistas, universo histórico sin sesgo de supervivencia, ejecución a la
apertura siguiente, walk-forward, PBO, Deflated Sharpe, bootstrap por bloques y un holdout ejecutado una sola vez.

**Resultado: NO EDGE.** Ninguna familia cumple los 12 criterios fijados de antemano; ninguna llega siquiera a
PROMETEDORA. La estrategia actual tampoco demuestra ventaja: el motor 2.0 da Sharpe −0,30 fuera de muestra
(2023-07 a 2026-11) y −0,15 en el holdout. Se recomienda **conservarla sin cambios** y **no presentarla con cifras de
rentabilidad**.

## 2. Revisión de literatura

| Trabajo | Tipo | Qué aporta | Uso aquí |
| --- | --- | --- | --- |
| Zarattini, Pagani y Barbon (2025), *Catching Crypto Trends: A Tactical Approach for Bitcoin and Altcoins* ([página del autor](https://abarbon.com/papers/catching-crypto-trends), [resumen de CXO](https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/)) | **Working paper** (SSRN, revisión de abril de 2025) | Conjunto de canales de 5 a 360 días, volatilidad objetivo del 25 %, top 20 líquidas, datos sin sesgo de supervivencia. Declara un Sharpe neto > 1,5, con costes del 0,10 % y de 2015 a 2025 | F3, réplica sin apalancamiento: el artículo llega al 200 % |
| *Cryptocurrency Market Risk-Managed Momentum Strategies* (2025) | **No se pudo verificar.** La búsqueda devolvió *Cryptocurrency momentum has (not) its moments* ([Springer, FMPM 2025](https://link.springer.com/article/10.1007/s11408-025-00474-9); [repositorio de Vaasa](https://osuva.uwasa.fi/handle/10024/20018)), pero no se pudo leer el texto completo (acceso denegado) | Momentum con volatilidad escalada (en la línea de Barroso y Santa-Clara, 2015) | F2, con la volatilidad objetivo de la cartera |
| He, Manela, Ross y von Wachter, *Fundamentals of Perpetual Futures* ([arXiv 2212.06888 v5, 2024](https://arxiv.org/html/2212.06888v5)) | **Working paper** (arXiv) | Desviaciones grandes entre el perpetuo y el spot; *carry* de BTC con Sharpe ≈ 1,8 con costes minoristas; las desviaciones **se reducen ≈ 11 % por año** | F6a. La compresión anunciada se observa: el *carry* pasa de un Sharpe de 5 a 9 (2020-2024) a −3,6 en el holdout |
| Moskowitz, Ooi y Pedersen (2012), *Time Series Momentum*, JFE | **Publicado** | Momentum de serie temporal | F1 |
| Liu y Tsyvinski (2021), *Risks and Returns of Cryptocurrency*, RFS ([NBER w24877](https://www.nber.org/system/files/working_papers/w24877/w24877.pdf)); Liu, Tsyvinski y Wu (2022), *Common Risk Factors in Cryptocurrency*, JF | **Publicados** | Momentum y factores en cripto | Hipótesis de F1 y F2 |
| Daniel y Moskowitz (2016), *Momentum Crashes*, JFE; Moreira y Muir (2017), *Volatility-Managed Portfolios*, JF | **Publicados** | Choques del momentum y gestión por volatilidad | F2 y F5 |
| Bailey y López de Prado (2014), *The Deflated Sharpe Ratio*, JPM; Bailey, Borwein, López de Prado y Zhu (2017), *The Probability of Backtest Overfitting*, J. Comp. Finance; Harvey, Liu y Zhu (2016), RFS | **Publicados** | Corrección por pruebas múltiples y sobreajuste | DSR, PBO y Holm |

Los trabajos marcados como publicados se citan de memoria; esta sesión no los volvió a leer. Los enlaces son los que
sí se consultaron.

**Costes reales de ejecución.** El artículo de Zarattini y otros prueba costes por lado del 0,10 %, 0,25 % y 0,50 %.
Aquí, BASE ronda del 0,17 % al 0,55 % por lado según la liquidez, más el impacto. ELEVADO y ESTRÉS lo multiplican
por 2 y por 3.

**Régimen.** La literatura de momentum y tendencia en cripto coincide en que el resultado depende mucho del régimen
alcista. Aquí se confirma: todas las familias de tendencia ganan en 2020-2021 y 2023-2024 y lo devuelven en 2022 y en
2025-2026.

## 3. Datos

Están en `VALIDACION_ESTADISTICA.md` §1:
- panel spot de Binance con las monedas retiradas;
- funding y velas reales de 281 perpetuos (archivo público `data.binance.vision`);
- universo reconstruido en cada fecha;
- contraste con Coinbase: diferencia mediana del 0,04 %.

## 4. Hipótesis: resultado

| Hipótesis | Resultado |
| --- | --- |
| H1: el momentum temporal funciona mejor con filtro de régimen | **En parte en desarrollo, no después.** Con el filtro BTC > media de 200 días, el Sharpe de desarrollo pasa de 0,55 a 1,19 (L = 90). En la validación cae a 0,06–0,09 y en el holdout a −0,23 (L = 90) y +0,33 (L = 30). No pasa la validación |
| H2: las rupturas Donchian con tamaño por volatilidad mejoran el resultado ajustado al riesgo | **No se confirma.** El drawdown baja al 10–20 %, pero el retorno es casi nulo con 20 monedas. En BTC, el Sharpe de validación es 1,46 con solo 4 operaciones; en el holdout, −2 % con 16 |
| H3: la reversión a la media solo funciona en ciertos regímenes | **Rechazada.** Pierde en todos los regímenes y conjuntos: de −57 % a −99 %. Los costes de una rotación de 100 a 175 veces al año lo explican casi todo |
| H4: el funding mejora la selección | **Rechazada.** Filtrar el funding saturado no mejora F1: holdout −30,5 %. El enfoque contrario: −40 % |
| H4b: *carry* de funding neutral | **Funcionó y dejó de funcionar.** Sharpe de 5,3 (desarrollo) y 5,9 (validación) con un rendimiento pequeño: un 0,56 % anual fuera de muestra, por debajo del efectivo remunerado. Holdout: −2,25 %, porque el funding comprimido no cubre los costes |
| H5: el filtro de liquidez reduce las señales falsas | **Rechazada.** El top 20 con ≥ 50 M empeora la validación: −42 % frente a −19 % |
| H6: combinar señales estabiliza el resultado | **En parte.** En el holdout, el conjunto reduce el drawdown (−26 % frente a −41 % y −52 % de sus componentes direccionales, F1 y la volatilidad objetivo de BTC) y es positivo en walk-forward (+37 %). Pierde en el holdout (−13 %) |
| H7: lo adaptativo supera a lo estático | **Rechazada.** F7 no pasa la validación: Sharpe −0,02 y 0,35 |

## 5. Motor de backtest

Se reescribió como motor nuevo (`research/edge3/engine.py`), sin tocar los anteriores. Incluye:
- ejecución a la apertura siguiente, con latencia opcional;
- comisión *taker* y *maker*, medio *spread*, deslizamiento por tramo e impacto √;
- ejecución parcial al 1 % del volumen;
- funding real y cobertura con perpetuo, con margen inmovilizado;
- retiradas con descuento;
- límites por activo y bruto ≤ 1;
- rotación, contabilidad por activo y por episodio.

Tiene 7 pruebas propias y una auditoría de anticipación de cada estrategia (`VALIDACION_ESTADISTICA.md` §2).

**Cambio declarado.** Durante el desarrollo (prueba de humo, antes de cualquier validación u holdout), F3 asignaba a
cada moneda el 25 %/vol sin dividir entre las 20 del universo. Se corrigió para replicar el artículo (1/N del capital
por moneda), en el commit `40b263a`, antes de ejecutar el desarrollo completo. Ningún otro parámetro cambió después del pre-registro.

## 6. Por qué no hay edge

1. **Dependencia del régimen.** Lo que funciona en tendencia alcista devuelve las ganancias en mercados bajistas o
   laterales. El holdout (2025-04 a 2026-11) fue bajista: BTC −22,5 %; cartera equiponderada −75,5 %.
2. **Costes.** Las estrategias de alta rotación (reversión, momentum de 7 días, *carry* en altcoins) pierden más en
   costes de lo que ganan en señal: F4 paga 2 108 USD sobre 10 000 en 19 meses.
3. **Compresión del *carry*.** Es lo que predice la literatura, y se observa: el funding de BTC y ETH ya no cubre los
   costes.
4. **Sobreajuste.** Las mejores de desarrollo (F1 con L = 30 y filtro, Sharpe 1,28; F2) se desploman en la validación.
   El PBO de F2 y F4 es de 0,76.
5. **Pocas operaciones donde parece funcionar.** F3 en BTC tiene 4 operaciones en la validación y 16 en el holdout.

## 7. Propuestas de mejora (sin promesas)

**Datos.**
- Libro de órdenes y *spread* históricos reales (Kaiko, Tardis), para medir los costes en vez de modelarlos.
- Universo de varios exchanges, para cubrir las monedas que no cotizan en Binance.
- Funding de varios exchanges, porque el diferencial entre ellos es otra fuente de *carry*.
- Tipos sin riesgo (letras del Tesoro y préstamos de stablecoins) como benchmark del efectivo.

**Ejecución.**
- Órdenes *maker* (en el escenario MAKER, el *carry* de BTC y ETH sale +1,8 % en el holdout en vez de −2,25 %).
- Bandas de rebalanceo más anchas y menos rotación.

**Producto.**
- Seguir presentando Crypto Radar como **herramienta de análisis**, no de rentabilidad.
- El paper trading de D_volmom (ya definido) es la única prueba sobre datos nuevos. Hay que **ponerlo en marcha** con
  la 2.1 desplegada (`PAPER_TRADING=1`).

**Investigación futura.** Solo con un nuevo pre-registro y un holdout futuro: los datos a partir de 2026-11-16, en
paper trading, durante ≥ 183 días.

## 8. Archivos

| Archivo | Qué contiene |
| --- | --- |
| `research/edge3/PREREGISTRO_V3.md` | Pre-registro: hipótesis, presupuesto, cortes y criterios |
| `research/edge3/benchmark/` | Benchmark congelado, con SHA-256 |
| `research/edge3/engine.py`, `strategies3.py`, `stats3.py`, `run3.py` | Motor, estrategias, estadística y ejecución |
| `research/edge3/test_engine.py`, `audit_data.py`, `fetch_funding.py`, `fetch_perp_nov.py` | Pruebas del motor, auditoría de datos y descargas |
| `research/edge3/results/*.json` y `*.csv.gz` | Resultados |
| `research/edge3/HOLDOUT_V3.lock` | Candado de la ejecución única del holdout |
| `docs/COMPARACION_ESTRATEGIAS.md` | Tablas completas |
| `docs/VALIDACION_ESTADISTICA.md` | Validación estadística |
| `docs/DECISION_FINAL_EDGE.md` | Decisión final |
