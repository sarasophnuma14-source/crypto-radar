# Benchmark congelado (2026-11-16)

Copias exactas, sin recalcular, de:
- `data/research/backtest_pro_curve.csv` y `backtest_pro_results.json`: motor Crypto Radar 2.0, la estrategia actual
  del producto. Periodo 2020-07-19 a 2026-11-14; costes 0,1 % de comisión + 0,1 % de deslizamiento + 0,1 % de spread
  por lado; generado el 2026-11-15T03:05Z. Parámetros en `defaults` dentro del JSON.
- `research/edge/audit/v2_curvas.csv`: D_volmom_L28, simulador v2 (estrategia del paper trading), curvas de
  desarrollo, validación y holdout exploratorio.

Código congelado: `radar/quant/` y `research/backtest_pro_run.py` (motor 2.0); `radar/edge/sim.py` y
`radar/edge/strategies.py` (D_volmom). Commit de referencia: el padre de este directorio en git.
Fecha de corte de los datos: 2026-11-14. Las sumas SHA-256 están en `SHA256SUMS`.
