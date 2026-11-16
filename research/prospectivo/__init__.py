"""Investigación cuantitativa prospectiva (independiente de la plataforma y de research/edge*).

Nada de este paquete importa ni modifica radar/quant, radar/edge, radar/paper_trading ni el ledger existente.
Módulos:
  registro      registro de hipótesis append-only encadenado por hash (antes de probar nada)
  guardia       ventanas consumidas, anticipación, fugas de información y sesgo de supervivencia
  datos         adaptadores (Binance archivo/API pública, Coinbase, Kraken, OKX, FRED) con esquema común
  costes        comisiones por exchange, spread, deslizamiento, impacto, funding y latencia
  motor         backtest por pesos para cualquier frecuencia y varios exchanges (spot y perpetuos)
  metricas      métricas, exceso sobre efectivo remunerado, DSR, PSR, PBO, bootstrap, Holm, BH, potencia
  validacion    walk-forward, k-fold purgado con embargo, CPCV
  diario        diario de señales de paper trading encadenado por hash y evaluación prospectiva
  clasificacion APROBADA / RECHAZADA / DATOS INSUFICIENTES según el pre-registro
"""
CORTE_PROSPECTIVO = "2026-11-16T00:00:00+00:00"   # todo dato anterior ya se ha visto: solo exploración/desarrollo
PRUEBAS_PREVIAS = 58                               # 23 (v1) + 35 (v3), para el DSR acumulado
