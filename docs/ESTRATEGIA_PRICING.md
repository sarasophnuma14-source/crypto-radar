# Estrategia de pricing · Crypto Radar

Fecha: 16 de noviembre de 2026.

**Estado: propuesta. No hay tarifas aprobadas ni pagos activos.** Los precios no se han probado con experimentos de mercado.

## 1. Propuesta evaluada

| Plan | Mensual | Precio de referencia | Anual | Equivalente al mes | Ahorro frente a 12 meses | % |
|---|---|---|---|---|---|---|
| Pro | US$15 | US$19 | US$149 | US$12,42 | US$31 | 17,2 % |
| Élite | US$29 | US$39 | US$299 | US$24,92 | US$49 | 14,1 % |

Cálculos verificados en `tests/ventas/prueba_landing_honesta.js`.

## 2. Evaluación

1. **Frente al mercado los precios son razonables, no baratos.** Ver `BENCHMARK_COMPETITIVO.md`:
   - TradingView Essential cuesta US$12,95/mes en pago anual.
   - CryptoQuant Advanced, US$29 al mes en pago anual y US$39 en pago mensual.
   - Glassnode Advanced, US$49/mes en pago anual.

   Crypto Radar no tiene datos on-chain ni historial verificable. Su valor diferencial es el análisis en español, solo spot y con transparencia. Pro a US$15 compite con herramientas de gráficos establecidas, así que **hay que demostrar valor durante el piloto antes de cobrar**.
2. **Élite a US$29 no se sostiene hoy.** En el código, Élite solo añade los resultados estáticos del backtest (`MATRIZ_FUNCIONALIDADES_PLANES.md`). Cobrar el doble por eso sería difícil de justificar.

   Opciones:
   - (a) lanzar solo Pro y abrir Élite cuando existan sus funciones;
   - (b) desarrollar primero los diferenciadores de Élite, con costo estimado en la matriz;
   - (c) bajar Élite.

   **Recomendación: (a).**
3. **Precio de referencia.** Mostrar US$19 tachado frente a US$15 cuando nunca se ha cobrado US$19 puede considerarse un precio de referencia engañoso. Conviene confirmarlo con el abogado, según el Estatuto del Consumidor (Ley 1480 de 2011).

   La landing del PR #11 lo muestra como "precio previsto después del lanzamiento". Si se usa, debe cumplirse: los precios suben a US$19 tras una fecha publicada, y quien ya está suscrito conserva el suyo.
4. **Anual.** Un descuento del 14 al 17 % es moderado: TradingView y CryptoQuant ofrecen entre el 17 y el 25 %. Mantenerlo es razonable y mejora la retención. El pago anual solo debe ofrecerse con una política de reembolso escrita.
5. **Plan gratuito.** El código tiene un plan Libre (top 3). No se publica mientras el piloto siga cerrado; podría servir como embudo después.

## 3. Condiciones que deben existir antes de cobrar

Ninguna está hecha hoy:

- Renovación automática explícita, con aviso previo al cobro.
- Cancelación en un clic desde el panel.
- Política de reembolso: proporcional en el plan anual, o 7 días en el primer pago; la decide PATRON con el abogado.
- Que un reembolso o contracargo revoque el plan. Hoy **no** lo hace (riesgo conocido de la auditoría del piloto).
- Facturación conforme a la DIAN (factura electrónica si aplica), lo que requiere contador.
- Prueba real en el sandbox de Wompi y NOWPayments (`CRYPTO_RADAR_PAYMENTS=sandbox`).
- Precios de `radar/billing.py` actualizados: hoy son 19/190 y 39/390. Cambiarlo es un cambio de una línea, pero solo tras la aprobación.

## 4. Recomendación

1. Mantener el piloto cerrado y gratuito de 60 a 90 días.
2. Medir activación y retención (ver `PLAN_COMERCIAL.md`) y preguntar la disposición a pagar con una encuesta dentro del panel.
3. Lanzar solo **Pro a US$15 mensual / US$149 anual** si la retención a 30 días supera el 40 % de los aprobados (umbral SUPUESTO, ajustable).
4. Abrir Élite cuando tenga al menos dos funciones exclusivas reales.
