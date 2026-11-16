# Validación estadística · investigación de edge v3

Fecha: 2026-11-16. El protocolo está en `research/edge3/PREREGISTRO_V3.md`. Se publicó en el commit `26042ec`,
**antes** de cualquier resultado.

## 1. Auditoría de datos (`research/edge3/results/auditoria_datos.json`)

| Comprobación | Resultado |
| --- | --- |
| Panel spot de Binance (USDT, diario) | 669 activos (664 series brutas; 14 partidas por huecos de más de 7 días), 2 510 días, de 2020-01-01 a 2026-11-14, 786 255 velas |
| Duplicados | 0 |
| Velas fuera de la medianoche UTC | 0 |
| Incoherencias OHLC (máximo < max(apertura, cierre) o mínimo > min(apertura, cierre)) | 0 |
| Días con volumen cero | 2 |
| Velas faltantes en huecos de hasta 7 días | 20. No se rellenan: el motor mantiene el último precio y no opera ese día |
| Retornos diarios > +100 % | 148, casi todos en monedas recién listadas y pequeñas. Con < −80 %: 6. No se recortan, porque son reales |
| Sesgo de supervivencia | Se incluyen las monedas retiradas: 191 en pausa o rotas, 3 retiradas por completo y 7 tramos partidos. Del top 50 por volumen a mitad de cada año, dejaron de cotizar después: 11 (2020), 14 (2021), 9 (2022), 10 (2023)… Ejemplos: LUNA antigua, FTM, WAVES, EOS y MATIC |
| Universo de cada fecha | Solo con datos hasta el cierre del día anterior: historia mínima, volumen medio de 30 días y ranking. Una moneda no entra antes de existir ni antes de tener volumen |
| Comparación con Coinbase (BTC-USD y ETH-USD) | 2 510 días. Diferencia mediana del cierre: 0,042 % (BTC) y 0,040 % (ETH); percentil 99: 0,32 % y 0,33 %. Máxima: 1,18 % y 2,25 % el 2020-03-12 (caída del COVID, USDT frente a USD) |
| Funding de perpetuos | 281 perpetuos USDT-M, con 24 753 zips y su SHA-256. BTC y ETH desde 2020-01-01, sin huecos. 5 perpetuos tienen huecos de más de 9 h. Algunos pasan a funding cada 4 h, y se suma por día UTC |
| Limitación: funding de noviembre de 2026 | El archivo mensual de 2026-11 aún no existe. Los 14 últimos días del holdout van **sin funding** (0). Las velas diarias del perpetuo de esos días sí están (archivo diario) |
| Limitación: comienzo en 2020 | El panel empieza el 2020-01-01. Las estrategias que exigen 365 días de historia (F3 top 20) no operan en 2020 |
| Limitación: cambios de ticker | Los cambios como MATIC → POL se tratan como retiradas, con un descuento del 10 %. Es una hipótesis conservadora |
| Limitación: *spread* y libro de órdenes | No hay histórico. Se modelan por tramos de liquidez más un impacto √ (pre-registro §4) |

## 2. Motor: pruebas antes de los resultados (`research/edge3/test_engine.py`, 7 de 7 OK)

1. **Anticipación.** Un oráculo que conoce el retorno de mañana gana más del doble que la misma señal conocida a tiempo:
   el motor no deja usar el futuro.
2. Ejecución a la apertura del día **siguiente** a la señal.
3. Costes de ida y vuelta exactos según la fórmula.
4. Ejecución parcial cuando la orden supera el 1 % del volumen.
5. Retirada definitiva con su descuento.
6. Identidad contable: la suma del PnL por activo es igual al PnL de la curva.
7. Cobertura con perpetuo neutral al precio, que cobra el funding.

**Auditoría de anticipación de las estrategias** (`run3.py`, `lookahead_audit`):
- Las 33 estrategias con pesos propios se recalculan con el panel **cortado** el 2022-06-30 y el 2024-03-31.
- Sus pesos de esa fecha coinciden exactamente con los del panel completo: **OK**.
- Si no coincidieran, el programa se detiene (regla 12).

## 3. Separación temporal

| Conjunto | Fechas | Uso real |
| --- | --- | --- |
| Desarrollo | 2020-01-01 a 2023-06-30 | Elegir una configuración por familia (máximo Sharpe con ≥ 30 episodios) |
| Validación | 2023-07-01 a 2025-03-31 | Filtro: Sharpe > 0,5 y retorno > 0 |
| Holdout | 2025-04-01 a 2026-11-14 | **Una ejecución**, el 2026-11-16T01:08:55Z, con el código y la selección congelados (hashes en `HOLDOUT_V3.lock`) |

- Cada conjunto se simula **desde cero**: sin posiciones heredadas, pero con señales que usan la historia anterior.
  Así no se mezclan operaciones entre conjuntos (embargo).
- Ninguna decisión se tomó mirando el holdout. Tras él no se ha cambiado nada.
- **Advertencia:** ese periodo ya se había visto en rondas anteriores, así que no es virgen (pre-registro §0).

## 4. Walk-forward semestral (2021-07 a 2025-03)

Cada semestre elige, dentro de la familia, la configuración con mejor Sharpe de los 18 meses anteriores.

| Familia | Sharpe OOS | Retorno OOS |
| --- | --- | --- |
| F1 TSMOM | 0,22 | −22,7 % |
| F2 XSMOM | −0,34 | −86,1 % |
| F3 Donchian | 0,74 | +40,6 % |
| F4 Reversión | −0,84 | −98,9 % |
| F5 Volatilidad | −0,02 | −30,8 % |
| F6 Funding/basis | 0,67 | +38,9 % |
| F7 Adaptativa | −0,25 | −70,9 % |
| F8 Conjunto | 0,49 | +37,1 % |

F3, F6 y F8 tienen un walk-forward positivo antes de 2025. Ninguna lo mantiene en el holdout (§6).

## 5. Sobreajuste

**PBO por CSCV** (16 bloques sobre desarrollo y validación):

| Familia | PBO |
| --- | --- |
| F1 | 0,30 |
| F2 | 0,76 |
| F3 | 0,26 |
| F4 | 0,76 |
| F5 | 0,56 |
| F6 | 0,00 |

F7 y F8 tienen menos de 4 configuraciones: N/A. Un PBO ≥ 0,5 indica que lo mejor dentro de la muestra suele quedar por
debajo de la mediana fuera de ella.

**Deflated Sharpe Ratio** (Bailey y López de Prado, 2014):
- N = 58 pruebas: 35 de esta ronda y 23 de la v1.
- Varianza de los Sharpe de desarrollo de las 35 configuraciones.
- El Sharpe mínimo esperado por azar (SR0) sale en **3,32 anual**. Es alto porque los Sharpe de 5 a 7 del carry en
  desarrollo inflan la varianza.
- Sensibilidad (información, no cambia el veredicto):
  - quitando el carry de la varianza, SR0 = 1,31 y el mejor DSR del holdout es 0,11 (F1);
  - con SR0 = 0 (PSR simple), el mejor es 0,66 (F1).
- **Ninguna familia llega a 0,95** en ninguna de las tres variantes.

## 6. Holdout: significación y robustez

| Familia | Retorno | Sharpe | Bootstrap p | p de Holm | IC 90 % del Sharpe | Elevado | Latencia +1 día |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F1 `tsmom_L30_btc` | +8,25 % | 0,33 | 0,30 | no llegó | [−0,71; 1,41] | +2,1 % | +14,0 % |
| F3 `donchian_btc_banda` | −2,05 % | −0,08 | 0,54 | 1,00 | [−1,23; 1,08] | −3,9 % | −7,9 % |
| F5 `voltarget_ew10` | −50,19 % | −0,77 | 0,85 | 1,00 | [−2,02; 0,54] | −52,8 % | −47,1 % |
| F6 `carry_btceth_thr0` | −2,25 % | −3,65 | 0,96 | 1,00 | [−6,01; −0,70] | −6,8 % | −2,3 % |
| F8 `conjunto_igual` | −13,13 % | −0,38 | 0,70 | 1,00 | [−1,64; 0,91] | −16,5 % | −13,8 % |

- F2, F4 y F7 no pasaron la validación; su holdout está en `COMPARACION_ESTRATEGIAS.md`.
- El bootstrap es estacionario, con bloque medio de 20 días y 5 000 réplicas.
- Holm se aplica sobre las 4 familias que llegaron al holdout: F3, F5, F6 y F8.

**Por régimen.**
- El holdout fue bajista para BTC: −22,5 %, con un drawdown del 53 %.
- La validación fue alcista: BTC +110 % entre 2023-07 y 2026-11, contando también el holdout.
- Las estrategias de tendencia ganan en los tramos alcistas y lo devuelven en el bajista. Es la misma pauta de la
  ronda v1.
- El PnL por activo y por familia está en `COMPARACION_ESTRATEGIAS.md`. Ninguna familia depende de una sola moneda
  para ganar, porque ninguna gana.

## 7. Reproducibilidad

Una copia aislada del directorio, con los mismos datos, sin resultados previos y sin candado, repitió:
- `run3.py devval`;
- `run3.py holdout`.

Resultado: **idénticos** `devval_v3.json` y `holdout_v3.json`, salvo la marca de tiempo. Las semillas del bootstrap son
fijas (7).

Para reproducirlo:

```bash
python research/edge3/fetch_funding.py research/edge3/funding_simbolos.txt   # requiere /tmp/perps.txt = perpetuos_listados_2026-11-16.txt
python research/edge3/fetch_perp_nov.py
python research/edge3/test_engine.py
python research/edge3/audit_data.py
python research/edge3/run3.py devval
python research/edge3/run3.py holdout    # se niega si HOLDOUT_V3.lock existe; para reproducir, en una copia sin el candado
```

El panel spot (`data/research/panel.json.gz`) es el mismo de las rondas anteriores; no se ha modificado.
