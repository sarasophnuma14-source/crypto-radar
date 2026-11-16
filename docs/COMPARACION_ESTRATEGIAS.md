# Comparación de estrategias · investigación de edge v3

Fecha: 2026-11-16. Todos los números salen de los archivos de resultados:
- `research/edge3/results/holdout_v3.json`;
- `research/edge3/results/devval_v3.json`.

La repetición en una copia aislada dio resultados idénticos byte a byte. **Ninguna cifra es estimada ni inventada.**

Condiciones comunes:
- capital de 10 000 USD;
- costes BASE (comisión *taker* del 0,10 %, más *spread*, deslizamiento e impacto por tramo de liquidez);
- ejecución a la apertura del día siguiente a la señal;
- universo histórico en cada fecha, con las monedas retiradas incluidas;
- solo largo en spot, salvo la cobertura con perpetuo de F6.

Reglas de lectura:
- «DSR» es el Deflated Sharpe Ratio, con N = 58 pruebas declaradas.
- «Resultado» es el veredicto pre-registrado (`research/edge3/PREREGISTRO_V3.md` §6) y, entre paréntesis, los
  criterios cumplidos.
- Una familia que no pasó la validación queda rechazada aunque se informe su holdout.
- En el Crypto Radar actual y en D_volmom, el CAGR y el factor de beneficio son N/D porque se recortan de sus curvas
  congeladas. Para el motor 2.0, el factor de beneficio de su propio periodo fuera de muestra (2024-01 a 2026-11)
  fue 0,72 (`benchmark/crypto_radar_2_0_resultados.json`).

### Holdout 2025-04-01 a 2026-11-14 (una sola ejecución)

| Estrategia | Configuración congelada | CAGR neto | Sharpe | Sortino | Max DD | PF | DSR (N=58) | Costes (USD, capital 10 000) | Resultado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Crypto Radar actual (motor 2.0) | congelada | -1,26 % | -0,15 | -0,22 | -7,3 % | N/D | — | incl. en la curva | Benchmark: sin edge |
| D_volmom_L28 v2 (paper trading) | congelada | N/D | -1,45 | N/D | -13,6 % | N/D | — | incl. en la curva | Benchmark: sin edge |
| BTC comprar y mantener | — | -14,49 % | -0,16 | -0,23 | -53,0 % | — | — | 17 | Benchmark |
| Equiponderada top 50 (mensual) | — | -57,94 % | -0,87 | -1,18 | -83,2 % | — | — | 224 | Benchmark |
| Momentum de serie temporal (F1) | `F1_tsmom_L30_btc` | 5,00 % | 0,33 | 0,45 | -27,1 % | 1,11 | 0,0000 | 695 | RECHAZADA (no pasó validación) (4/12) |
| Momentum transversal gestionado (F2) | `F2_xsmom_L28_vol` | -61,62 % | -1,90 | -2,46 | -82,0 % | 0,48 | 0,0000 | 726 | RECHAZADA (no pasó validación) (0/12) |
| Trend following Donchian (F3) | `F3_donchian_btc_banda` | -1,27 % | -0,08 | -0,11 | -14,6 % | 0,63 | 0,0000 | 190 | DATOS INSUFICIENTES (3/12) |
| Mean reversion (F4) | `F4_reversion_k7_btc` | -61,91 % | -1,35 | -1,72 | -81,7 % | 0,60 | 0,0000 | 2.108 | RECHAZADA (no pasó validación) (0/12) |
| Volatility targeting (F5) | `F5_voltarget_ew10` | -34,88 % | -0,77 | -1,04 | -64,9 % | 0,38 | 0,0000 | 465 | RECHAZADA (1/12) |
| Funding/basis (F6) | `F6_carry_btceth_thr0` | -1,39 % | -3,65 | -3,72 | -2,4 % | 0,24 | 0,0008 | 473 | RECHAZADA (3/12) |
| Régimen adaptativo (F7) | `F7_adaptativo_a` | -6,68 % | 0,04 | 0,06 | -33,3 % | 0,86 | 0,0000 | 764 | RECHAZADA (no pasó validación) (1/11) |
| Ensemble (F8) | `F8_conjunto_igual` | -8,30 % | -0,38 | -0,51 | -25,9 % | 0,47 | 0,0000 | 393 | RECHAZADA (2/11) |

### Fuera de muestra completo: validación + holdout, 2023-07-01 a 2026-11-14

| Estrategia | Configuración congelada | CAGR neto | Sharpe | Sortino | Max DD | PF | DSR (N=58) | Costes (USD, capital 10 000) | Resultado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Crypto Radar actual (motor 2.0) | congelada | -3,01 % | -0,30 | -0,43 | -20,3 % | N/D | — | incl. en la curva | Benchmark: sin edge |
| D_volmom_L28 v2 (paper trading) | congelada | N/D | -0,38 | N/D | -19,6 % | N/D | — | incl. en la curva | Benchmark: sin edge |
| BTC comprar y mantener | — | 24,62 % | 0,71 | 1,07 | -53,0 % | — | — | 17 | Benchmark |
| Equiponderada top 50 (mensual) | — | -36,46 % | -0,27 | -0,37 | -90,8 % | — | — | 619 | Benchmark |
| Momentum de serie temporal (F1) | `F1_tsmom_L30_btc` | -3,99 % | 0,17 | 0,24 | -66,2 % | 0,96 | 0,0000 | 1.990 | RECHAZADA (no pasó validación) (4/12) |
| Momentum transversal gestionado (F2) | `F2_xsmom_L28_vol` | -41,06 % | -0,96 | -1,31 | -86,6 % | 0,74 | 0,0000 | 1.580 | RECHAZADA (no pasó validación) (0/12) |
| Trend following Donchian (F3) | `F3_donchian_btc_banda` | 13,08 % | 0,90 | 1,44 | -14,6 % | 6,15 | 0,0000 | 505 | DATOS INSUFICIENTES (3/12) |
| Mean reversion (F4) | `F4_reversion_k7_btc` | -67,99 % | -1,33 | -1,74 | -98,3 % | 0,73 | 0,0000 | 4.136 | RECHAZADA (no pasó validación) (0/12) |
| Volatility targeting (F5) | `F5_voltarget_ew10` | -2,90 % | 0,15 | 0,21 | -64,9 % | 0,95 | 0,0000 | 1.584 | RECHAZADA (1/12) |
| Funding/basis (F6) | `F6_carry_btceth_thr0` | 0,56 % | 1,42 | 1,77 | -2,5 % | 1,44 | 0,0008 | 807 | RECHAZADA (3/12) |
| Régimen adaptativo (F7) | `F7_adaptativo_a` | -13,32 % | 0,01 | 0,01 | -74,6 % | 0,92 | 0,0000 | 4.155 | RECHAZADA (no pasó validación) (1/11) |
| Ensemble (F8) | `F8_conjunto_igual` | 4,75 % | 0,32 | 0,46 | -30,2 % | 1,22 | 0,0000 | 1.106 | RECHAZADA (2/11) |

### Criterios por familia (holdout)

| Familia | Config | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 | C11 | C12 | Veredicto |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | 
| F1 | `F1_tsmom_L30_btc` | ✓ | ✗ | ✓ | ✗ | ✓ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✓ | RECHAZADA (no pasó validación) |
| F2 | `F2_xsmom_L28_vol` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | RECHAZADA (no pasó validación) |
| F3 | `F3_donchian_btc_banda` | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | DATOS INSUFICIENTES |
| F4 | `F4_reversion_k7_btc` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | RECHAZADA (no pasó validación) |
| F5 | `F5_voltarget_ew10` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | RECHAZADA |
| F6 | `F6_carry_btceth_thr0` | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | ✓ | ✗ | ✓ | ✓ | ✗ | RECHAZADA |
| F7 | `F7_adaptativo_a` | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | N/A | ✗ | ✗ | ✓ | ✗ | RECHAZADA (no pasó validación) |
| F8 | `F8_conjunto_igual` | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ | ✗ | N/A | ✗ | ✗ | ✓ | ✗ | RECHAZADA |

### Desarrollo y validación de las 35 configuraciones (BASE)

| Configuración | Dev: retorno | Dev: Sharpe | Dev: DD | Dev: episodios | Val: retorno | Val: Sharpe | Val: DD | Holdout (informativo): retorno | Holdout: Sharpe |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `F1_tsmom_L30_sin` | 447,5 % | 1,00 | -78,2 % | 633 | 40,2 % | 0,62 | -56,0 % | -68,4 % | -0,97 |
| `F1_tsmom_L30_btc` | 778,8 % | 1,28 | -52,4 % | 406 | -19,4 % | 0,06 | -64,0 % | 8,2 % | 0,33 |
| `F1_tsmom_L90_sin` | 43,4 % | 0,55 | -91,3 % | 462 | 37,1 % | 0,60 | -52,8 % | -73,7 % | -1,26 |
| `F1_tsmom_L90_btc` | 588,4 % | 1,19 | -55,0 % | 353 | -19,4 % | 0,09 | -64,8 % | -25,5 % | -0,23 |
| `F1_tsmom_L180_sin` | 52,5 % | 0,57 | -90,5 % | 398 | 9,5 % | 0,41 | -61,1 % | -64,1 % | -1,05 |
| `F1_tsmom_L180_btc` | 541,0 % | 1,16 | -54,2 % | 348 | -36,7 % | -0,12 | -74,9 % | -33,8 % | -0,49 |
| `F1_tsmom_L90_btc_liq50M` | 539,8 % | 1,19 | -53,4 % | 185 | -42,1 % | -0,27 | -65,8 % | -30,8 % | -0,42 |
| `F2_xsmom_L7_sin` | -36,0 % | 0,39 | -97,9 % | 1202 | -54,5 % | -0,14 | -71,2 % | -86,0 % | -1,11 |
| `F2_xsmom_L7_vol` | 48,0 % | 0,47 | -74,1 % | 1202 | -15,7 % | -0,00 | -38,9 % | -70,6 % | -1,38 |
| `F2_xsmom_L28_sin` | 1,4 % | 0,52 | -95,7 % | 592 | -50,1 % | -0,05 | -70,7 % | -94,1 % | -1,68 |
| `F2_xsmom_L28_vol` | 87,0 % | 0,62 | -72,7 % | 592 | -20,6 % | -0,08 | -37,2 % | -78,9 % | -1,90 |
| `F2_xsmom_L90_sin` | -58,7 % | 0,27 | -96,8 % | 366 | -50,0 % | -0,04 | -74,4 % | -96,7 % | -2,23 |
| `F2_xsmom_L90_vol` | 25,6 % | 0,37 | -75,8 % | 366 | -20,6 % | -0,08 | -41,5 % | -83,5 % | -2,32 |
| `F3_donchian_btc_diario` | 61,2 % | 1,12 | -19,7 % | 36 | 48,7 % | 1,34 | -10,5 % | -3,4 % | -0,15 |
| `F3_donchian_btc_banda` | 62,1 % | 1,14 | -19,8 % | 36 | 54,6 % | 1,46 | -9,9 % | -2,0 % | -0,08 |
| `F3_donchian_top20_diario` | 11,3 % | 0,52 | -10,9 % | 831 | 21,6 % | 1,28 | -8,8 % | -3,8 % | -0,36 |
| `F3_donchian_top20_banda` | 11,3 % | 0,52 | -10,6 % | 831 | 22,0 % | 1,29 | -8,8 % | -3,7 % | -0,35 |
| `F4_reversion_k3_sin` | -99,1 % | -0,62 | -99,6 % | 2592 | -75,9 % | -0,51 | -79,8 % | -98,2 % | -2,26 |
| `F4_reversion_k3_btc` | -72,7 % | -0,10 | -85,7 % | 1528 | -82,3 % | -0,89 | -86,0 % | -72,6 % | -0,90 |
| `F4_reversion_k7_sin` | -98,6 % | -0,53 | -99,5 % | 1653 | -85,0 % | -0,86 | -87,0 % | -98,5 % | -2,49 |
| `F4_reversion_k7_btc` | -57,2 % | 0,07 | -83,6 % | 1012 | -89,8 % | -1,34 | -92,0 % | -79,2 % | -1,35 |
| `F5_voltarget_btc_sin` | 115,4 % | 0,72 | -64,6 % | 1 | 156,8 % | 1,52 | -21,3 % | -26,0 % | -0,30 |
| `F5_voltarget_btc_sma200` | 168,8 % | 1,10 | -45,3 % | 11 | 76,5 % | 1,06 | -25,1 % | 7,4 % | 0,30 |
| `F5_voltarget_ew10` | 94,0 % | 0,67 | -65,6 % | 167 | 81,7 % | 1,00 | -30,8 % | -50,2 % | -0,77 |
| `F5_volexpansion_top30` | 11,1 % | 0,37 | -79,5 % | 204 | 95,2 % | 0,95 | -40,6 % | -75,0 % | -1,48 |
| `F6_carry_btceth_thr0` | 17,3 % | 5,28 | -3,3 % | 62 | 4,2 % | 5,91 | -1,0 % | -2,2 % | -3,65 |
| `F6_carry_top10_thr0` | 1,6 % | 0,25 | -20,5 % | 434 | -8,7 % | -4,63 | -8,7 % | -23,6 % | -15,25 |
| `F6_carry_btceth_thr10` | 20,8 % | 6,73 | -0,9 % | 28 | 5,3 % | 9,27 | -0,2 % | 0,1 % | 0,42 |
| `F6_carry_top10_thr10` | 18,8 % | 2,70 | -8,3 % | 251 | 0,9 % | 0,61 | -2,6 % | -6,0 % | -5,81 |
| `F6_tsmom_filtro_funding` | 614,7 % | 1,21 | -55,4 % | 455 | -13,7 % | 0,14 | -62,9 % | -30,5 % | -0,36 |
| `F6_funding_contrario` | 535,2 % | 1,11 | -61,4 % | 187 | -74,8 % | -0,76 | -74,8 % | -40,1 % | -0,32 |
| `F7_adaptativo_a` | -38,1 % | 0,17 | -77,2 % | 1248 | -31,0 % | -0,02 | -70,2 % | -10,6 % | 0,04 |
| `F7_adaptativo_b` | -78,1 % | -0,61 | -92,2 % | 513 | 7,4 % | 0,35 | -49,8 % | -74,8 % | -1,29 |
| `F8_conjunto_igual` | 148,0 % | 1,18 | -31,9 % | 1436 | 34,0 % | 0,80 | -24,1 % | -13,1 % | -0,38 |
| `F8_conjunto_invvol` | 35,4 % | 1,29 | -6,5 % | 1436 | 2,7 % | 0,41 | -5,5 % | -6,5 % | -1,13 |

### Walk-forward semestral 2021-07 a 2025-03 (elige con los 18 meses previos)

| Familia | Sharpe OOS | Retorno OOS |
| --- | --- | --- |
| F1 | 0,22 | -22,7 % |
| F2 | -0,34 | -86,0 % |
| F3 | 0,74 | 40,6 % |
| F4 | -0,84 | -98,9 % |
| F5 | -0,02 | -30,8 % |
| F6 | 0,67 | 38,9 % |
| F7 | -0,25 | -70,9 % |
| F8 | 0,49 | 37,0 % |

### Estadística del holdout por familia

| Familia | Bootstrap p (unilateral) | p de Holm | IC 90 % del Sharpe | DSR N=58 | SR0 anual (N=58) | DSR N=100 | PBO (CSCV) | Elevado: retorno | Estrés: Sharpe | Latencia +1 día: retorno | Maker: retorno | Capital 1 M: retorno |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | 
| F1 | 0,3024 | no llegó | [-0,71; 1,41] | 0,0000 | 3,32 | 0,0000 | 0,303 | 2,1 % | 0,15 | 14,0 % | 14,1 % | 8,1 % |
| F2 | 0,9964 | no llegó | [-3,06; -0,76] | 0,0000 | 3,32 | 0,0000 | 0,762 | -81,2 % | -2,23 | -80,7 % | -76,5 % | -79,3 % |
| F3 | 0,5390 | 1,0000 | [-1,23; 1,08] | 0,0000 | 3,32 | 0,0000 | 0,258 | -3,9 % | -0,31 | -7,9 % | -0,4 % | -2,1 % |
| F4 | 0,9596 | no llegó | [-2,46; -0,23] | 0,0000 | 3,32 | 0,0000 | 0,756 | -85,2 % | -2,08 | -81,8 % | -71,4 % | -80,1 % |
| F5 | 0,8470 | 1,0000 | [-2,02; 0,54] | 0,0000 | 3,32 | 0,0000 | 0,559 | -52,8 % | -0,92 | -47,1 % | -47,7 % | -50,4 % |
| F6 | 0,9588 | 1,0000 | [-6,01; -0,70] | 0,0008 | 3,32 | 0,0001 | 0,000 | -6,8 % | -6,81 | -2,3 % | 1,8 % | -2,5 % |
| F7 | 0,4754 | no llegó | [-1,14; 1,29] | 0,0000 | 3,32 | 0,0000 | N/A | -17,1 % | -0,20 | -22,6 % | -4,3 % | -11,7 % |
| F8 | 0,6974 | 1,0000 | [-1,64; 0,91] | 0,0000 | 3,32 | 0,0000 | N/A | -16,5 % | -0,66 | -13,8 % | -10,1 % | -13,5 % |

### Métricas completas del holdout (configuración congelada)

| Métrica | F1 | F2 | F3 | F4 | F5 | F6 | F7 | F8 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | 
| retorno_neto_pct | 8,25 | -78,90 | -2,05 | -79,16 | -50,19 | -2,25 | -10,62 | -13,13 |
| cagr_pct | 5,00 | -61,62 | -1,27 | -61,91 | -34,88 | -1,39 | -6,68 | -8,30 |
| sharpe | 0,33 | -1,90 | -0,08 | -1,35 | -0,77 | -3,65 | 0,04 | -0,38 |
| sortino | 0,45 | -2,46 | -0,11 | -1,72 | -1,04 | -3,72 | 0,06 | -0,51 |
| calmar | 0,18 | -0,75 | -0,09 | -0,76 | -0,54 | -0,59 | -0,20 | -0,32 |
| profit_factor | 1,11 | 0,48 | 0,63 | 0,60 | 0,38 | 0,24 | 0,86 | 0,47 |
| max_dd_pct | -27,09 | -81,96 | -14,62 | -81,71 | -64,88 | -2,36 | -33,30 | -25,93 |
| vol_anual_pct | 41,48 | 44,96 | 10,00 | 58,49 | 43,36 | 0,38 | 41,32 | 18,30 |
| win_rate_pct | 45,20 | 30,90 | 12,50 | 45,30 | 31,00 | 15,80 | 35,10 | 16,40 |
| ganancia_media | 108,83 | 70,16 | 175,20 | 61,27 | 114,45 | 12,15 | 95,39 | 10,42 |
| perdida_media | -80,93 | -64,92 | -39,67 | -83,98 | -135,15 | -9,31 | -60,31 | -4,29 |
| expectancy | 4,91 | -23,21 | -12,81 | -18,20 | -57,69 | -5,92 | -5,65 | -1,88 |
| rotacion_x_anual | 15,57 | 25,08 | 6,78 | 96,43 | 15,09 | 22,93 | 21,42 | 14,32 |
| episodios | 168,00 | 340,00 | 16,00 | 435,00 | 87,00 | 38,00 | 188,00 | 813,00 |
| exposicion_media_pct | 41,80 | 53,70 | 21,50 | 46,60 | 67,80 | 32,40 | 44,90 | 44,70 |
| tiempo_en_mercado_pct | 45,70 | 100,00 | 75,90 | 46,50 | 100,00 | 88,20 | 46,50 | 100,00 |
| costes_totales | 695,19 | 725,80 | 190,37 | 2.108,34 | 464,77 | 472,93 | 764,50 | 392,54 |
| deslizamiento | 394,64 | 457,77 | 79,03 | 1.325,21 | 238,23 | 196,52 | 427,50 | 196,35 |
| funding | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 | 245,03 | 0,00 | 65,69 |

### PnL por activo en el holdout (3 mejores y 3 peores de cada familia, USD)

- **F1**: mejores ZEC 1.054, BNB 553, ZEN 459; peores CAKE -674, STRK -390, INJ -385
- **F2**: mejores PENGU 640, ZEC 544, ALLO 359; peores TUT -574, ALPINE -509, FLOKI -358
- **F3**: mejores BTC -205; peores BTC -205
- **F4**: mejores OP 563, PNUT 498, ETHFI 469; peores FUN -1.211, OM -791, FORM -686
- **F5**: mejores ZEC 998, PENGU 234, BNB 215; peores SUI -1.011, BANK -690, PEPE -671
- **F6**: mejores BTC -43, ETH -182; peores ETH -182, BTC -43
- **F7**: mejores NEAR 488, PUMP 425, ZEC 381; peores SOL -397, DOGE -278, HBAR -273
- **F8**: mejores ZEC 148, BNB 111, ZEN 105; peores BTC -665, SOL -115, WLD -102

## Lectura

- **Ninguna familia cumple los criterios de edge.** En el holdout, la única con retorno positivo es F1: +8,25 %,
  Sharpe 0,33, con un bootstrap p = 0,30. Pero ya había quedado fuera en la validación, y no supera ni el Sharpe
  exigido ni el control de pruebas múltiples.
- **La estrategia actual tampoco demuestra edge.** Fuera de muestra (2023-07 a 2026-11), el motor 2.0 da Sharpe −0,30
  y en el holdout −0,15. D_volmom (paper trading) da −0,38 y −1,45.
- **BTC comprar y mantener es el benchmark más exigente fuera de muestra** (Sharpe 0,71 de 2023-07 a 2026-11), pero
  con un drawdown del 53 %. En el holdout, BTC pierde un 22,5 % y aun así ninguna estrategia lo supera con un margen
  significativo.
- **El carry de funding (F6)** es la única familia con un perfil distinto: neutral al precio, con drawdown < 3 %.
  - Fuera de muestra rinde un 0,56 % anual; en el holdout, −2,25 % neto.
  - El funding de BTC y ETH se comprimió en 2025-2026 y ya no cubre los costes de entrar y salir.
  - Aunque su Sharpe de validación más holdout sea 1,42, su rendimiento queda por debajo del de mantener efectivo en
    letras del Tesoro o en préstamos de stablecoins en ese periodo. El motor asume un efectivo que no rinde nada, lo
    que **favorece** al carry.
- **F3 en BTC** (tendencia con canales Donchian) va bien en la validación: Sharpe 1,46 con solo 4 episodios. En el
  holdout pierde un 2 % con 16 episodios. Muy pocas operaciones para concluir nada, y depende de una sola moneda.
