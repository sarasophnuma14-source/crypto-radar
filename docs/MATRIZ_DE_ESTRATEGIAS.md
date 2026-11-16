# Matriz de estrategias (fase prospectiva)

Estado a 2026-11-16. **Ninguna línea tiene evidencia prospectiva todavía**, así que todas están en **DATOS INSUFICIENTES**. Las familias v3 ya rechazadas (F1–F8) **no se integran**. Si una línea nueva se parece a una de ellas, hereda su historial, y eso se declara en el registro.

La primera decisión posible es al día 90 desde el registro (2027-02-14 si se registrara hoy), y solo con un efecto muy grande (z ≥ 3,78). Con un Sharpe real de 1, harían falta unos 6 años para confirmarlo (`INFORME_INVESTIGACION_PROSPECTIVA.md` §4).

| # | Línea | Antecedente en v1/v3 | Datos necesarios | ¿Disponibles? | Frecuencia | Riesgo principal | Clase |
|---|---|---|---|---|---|---|---|
| L1 | Momentum intradía y multi-marco (1 h–4 h, confirmación diaria) | F1/F2 diarios rechazados (TSMOM holdout +8 %, sin validar) | klines 1 h/4 h spot y perp | Sí (archivo Binance, Coinbase, Kraken, OKX) | 1 h–4 h | Los costes se comen el margen (rotación alta) | DATOS INSUFICIENTES |
| L2 | Rupturas de volatilidad (compresión → expansión) | F5 volexpansion rechazada (diaria) | klines 1 h, volatilidad realizada | Sí | 1 h–1 d | Pocas operaciones independientes | DATOS INSUFICIENTES |
| L3 | Cambios de régimen (volatilidad o tendencia de BTC como filtro) | F7 adaptativa rechazada | klines diarias y 4 h, funding | Sí | 1 d | Pocos cambios de régimen al año, lo que deja muy poca potencia | DATOS INSUFICIENTES |
| L4 | Flujo de órdenes y desequilibrio del libro | Ninguno | aggTrades (OFI), bookDepth perp, libro spot grabado | aggTrades y bookDepth perp sí; **el libro spot hay que grabarlo hacia delante** | 5 m–1 h | Latencia y paper muy optimista frente a lo real; necesita un proceso persistente | DATOS INSUFICIENTES |
| L5 | Funding y basis (carry delta-neutral, basis spot-perp) | F6 carry: Sharpe 5–9 en 2020–24, holdout −2,25 % (funding comprimido) | funding, klines spot y perp, metrics (OI) | Sí; el funding de nov-2026 llega a mes vencido (archivo mensual) | 8 h–1 d | Régimen de funding comprimido; riesgo de exchange | DATOS INSUFICIENTES |
| L6 | Arbitraje estadístico (pares o cestas cointegradas; diferencias entre exchanges) | Ninguno | klines 1 h de varios exchanges, perps para el corto | Sí (Binance, Coinbase, Kraken, OKX) | 1 h | Ruptura de la cointegración; el corto solo es posible en perps | DATOS INSUFICIENTES |
| L7 | Reversión a la media condicionada al régimen | F4 reversión rechazada | klines 1 h/1 d, régimen | Sí | 1 h–1 d | Riesgo de cola en tendencias fuertes | DATOS INSUFICIENTES |
| L8 | Señales de liquidez y volumen (picos de volumen, taker-buy ratio, OI) | Ninguno | klines (taker_buy_volume), metrics OI | Sí | 1 h–1 d | Señal ruidosa; fácil de sobreajustar | DATOS INSUFICIENTES |
| L9 | Combinación de señales independientes | F8 conjunto rechazado | Las de sus componentes | Sí | — | Solo combina componentes que hayan pasado por separado; si no, multiplica N | DATOS INSUFICIENTES |

## Reglas para pasar de DATOS INSUFICIENTES

- **A RECHAZADA:** por futilidad, por fallar una guardia o al llegar al último punto de control sin cumplir los criterios.
- **A APROBADA:** solo si cumple los 13 criterios de `PREREGISTRO_PROSPECTIVO.md` §4.
- **Recomendación de orden:** registrar pocas hipótesis (cada prueba encarece el DSR de todas). Priorizar las líneas cuyo efecto, si existe, sería grande y frecuente (L1, L4, L5, L6), porque son las únicas con potencia razonable en uno o dos años.
