# Análisis de costos y rentabilidad · Crypto Radar 2.1

> **Actualización del 16-nov-2026.** Los números de este documento suponían una mezcla Pro/Élite. Los reemplaza `UNIT_ECONOMICS.md` (solo Pro a 15/149). Correcciones principales:
> - ARPU de US$13,97 (antes US$17,99);
> - licencia comercial de CoinGecko de US$35 al mes (antes «no verificada»);
> - riesgo de transferencia de Neon por el sondeo de 30 s, corregido en la PR #12;
> - margen del 69 % al 77 % sin IVA.

Fecha: 16 de noviembre de 2026. Todas las cifras están en dólares estadounidenses.

Cada número lleva una de estas etiquetas:

- **MEDIDO**: leído hoy en Render o en el código.
- **PÚBLICO**: precio publicado por el proveedor, con fuente y fecha.
- **SUPUESTO**: estimación propia, que conviene cambiar en cuanto haya datos reales.

> Conclusión corta. La infraestructura no es el problema: cuesta poco frente al ingreso por usuario. La viabilidad depende de cuatro cosas que todavía no se conocen:
> 1. si la gente paga por un producto que declara abiertamente no tener ventaja estadística demostrada;
> 2. cuánto cuesta conseguir cada cliente;
> 3. cuántos cancelan cada mes;
> 4. los costos legales, contables y fiscales, que hoy no están medidos.

## 1. Costos actuales

| Concepto | Valor | Tipo | Fuente |
|---|---|---|---|
| Render, servicio crypto-radar-2-1 | US$7/mes (plan `starter`, 0,5 CPU, 512 MB) | MEDIDO + PÚBLICO | API de Render (16-nov); [render.com/pricing](https://render.com/pricing.md), consultado el 16-nov-2026 |
| Render, servicio crypto-radar (2.0, todavía activo) | US$7/mes (`0.5c-512mb`) | MEDIDO | API de Render. **Se ahorra al suspenderlo** |
| Render, crypto-radar-ventas (estático) | US$0 | PÚBLICO | Los sitios estáticos no pagan cómputo |
| Render, cuota del workspace | US$0 (Hobby) o US$25/mes (Pro) | **NO VERIFICADO** | El plan del workspace no se ve con el conector |
| Render, ancho de banda | 5 GB incluidos (Hobby) y luego US$0,15/GB | PÚBLICO | ídem |
| Neon PostgreSQL | Free: 100 CU-h por proyecto. Launch: US$0,106/CU-h + US$0,35/GB-mes | PÚBLICO | [neon.com/pricing](https://neon.com/pricing), consultado el 16-nov-2026. **Plan contratado NO VERIFICADO** |
| Telegram Bot API | US$0 | PÚBLICO | — |
| Datos de mercado (CoinGecko, Binance, Bybit, alternative.me) | US$0 (API públicas o gratuitas) | MEDIDO | `/healthz` del 16-nov. **Licencia de uso comercial NO VERIFICADA** |

### Riesgo de costo detectado en Neon

El planificador consulta la base cada 30 segundos (`next_scan_time` lee `latest.json`), así que Neon nunca entra en suspensión.

Con 0,25 CU encendido todo el mes salen unas 182 CU-h. El plan Free incluye 100 CU-h por proyecto, de modo que en el plan Free el cómputo se agotaría hacia el día 16 de cada mes. En Launch serían unos US$19/mes. Las dos cifras son estimaciones y dependen del tamaño mínimo de cómputo configurado.

**Acción:** que PATRON confirme en la consola de Neon el plan y el consumo de CU-h. Si el plan es Free, conviene una de dos cosas: cachear `next_scan_time` en memoria (cambio pequeño, P1) o pasar a Launch.

## 2. Costos variables por cobro

> **SUSTITUIDO el 16-nov-2026.** Estas cifras usaban una mezcla Pro/Élite que ya no es la oferta. Se conservan como historial; las vigentes están en `UNIT_ECONOMICS.md`.

Comisiones de Wompi: 2,65 % + COP 700 + IVA del 19 % sobre la comisión (PÚBLICO, [enter.co, 3-oct-2026](https://www.enter.co/fintech/wompi-baja-la-tarifa-del-qr-al-1-y-amplia-los-pagos-desde-el-celular/)). Para la parte fija en pesos se toma COP 4.000 por dólar (SUPUESTO).

Comisiones de NOWPayments: 1 % sin conversión o 1,5 % con conversión (PÚBLICO, [base de conocimiento de NOWPayments](https://nowpayments.io/help/about-nowpayments/about/what-are-your-fees), consultada el 16-nov-2026), más la red. Para la red se toman US$0,50 (SUPUESTO).

| Cobro | Wompi | % | NOWPayments |
|---|---|---|---|
| Pro mensual US$15 | US$0,68 | 4,5 % | US$0,65 |
| Pro anual US$149 | US$4,91 | 3,3 % | US$1,99 |
| Élite mensual US$29 | US$1,12 | 3,9 % | US$0,79 |
| Élite anual US$299 | US$9,64 | 3,2 % | US$3,49 |

Comisión media ponderada: **3,6 %** (SUPUESTO de mezcla: 70 % tarjeta y 30 % USDT).

**No incluido:**

- IVA cobrado al cliente colombiano: si el precio lo incluye, el ingreso neto baja alrededor del 16 % en esa parte de la clientela.
- Retenciones e impuesto de renta.
- Costos de Wompi por contracargos.

Requieren un **contador**. No se asume ninguna exención.

## 3. Ingreso medio por usuario (ARPU)

> **SUSTITUIDO el 16-nov-2026.** Estas cifras usaban una mezcla Pro/Élite que ya no es la oferta. Se conservan como historial; las vigentes están en `UNIT_ECONOMICS.md`.

Mezcla base (SUPUESTO): 70 % Pro y 30 % Élite; 60 % mensual y 40 % anual. Con ella, **ARPU = US$17,99/mes**.

| Pro / Élite | 20 % anual | 40 % anual | 60 % anual |
|---|---|---|---|
| 50 / 50 | 21,33 | 20,67 | 20,00 |
| 70 / 30 | 18,59 | **17,99** | 17,38 |
| 90 / 10 | 15,85 | 15,31 | 14,76 |

## 4. Escenarios por número de usuarios de pago

> **SUSTITUIDO el 16-nov-2026.** Estas cifras usaban una mezcla Pro/Élite que ya no es la oferta. Se conservan como historial; las vigentes están en `UNIT_ECONOMICS.md`.

La infraestructura por escenario es un SUPUESTO de arquitectura (ver `PLAN_ESCALABILIDAD.md`, pendiente). Las pruebas de carga de 100 usuarios fueron locales y **no demuestran capacidad en Render**.

| Usuarios | Infraestructura supuesta |
|---|---|
| 50 y 100 | Web Starter US$7 + Neon unos US$20 |
| 250 | Web Standard US$25 + Neon US$30 + worker de escaneo US$7 |
| 500 | Web US$25 + workspace Pro US$25 + Neon US$45 + worker US$25 |
| 1.000 | 2 instancias web US$50 + workspace US$25 + Neon US$70 + worker US$25 |

Soporte: 15 minutos por usuario al mes a US$10/h (SUPUESTO).

| Usuarios de pago | MRR | ARR | Comisiones | Infraestructura | Soporte | Margen bruto | Margen % |
|---|---|---|---|---|---|---|---|
| 50 | 899 | 10.790 | 32 | 27 | 125 | 715 | 80 % |
| 100 | 1.799 | 21.590 | 65 | 27 | 250 | 1.457 | 81 % |
| 250 | 4.497 | 53.960 | 161 | 62 | 625 | 3.648 | 81 % |
| 500 | 8.993 | 107.920 | 323 | 120 | 1.250 | 7.301 | 81 % |
| 1.000 | 17.987 | 215.840 | 645 | 170 | 2.500 | 14.672 | 82 % |

El margen bruto no incluye IVA, renta, abogado, contador, dominio, marca, sueldo del responsable ni adquisición de clientes.

## 5. Punto de equilibrio, churn, LTV y CAC

> **SUSTITUIDO el 16-nov-2026.** Estas cifras usaban una mezcla Pro/Élite que ya no es la oferta. Se conservan como historial; las vigentes están en `UNIT_ECONOMICS.md`.

Contribución por usuario: ARPU menos comisiones menos soporte, es decir, **US$14,84/mes** (SUPUESTO).

**Equilibrio sobre la infraestructura actual** (US$27/mes): 2 usuarios.

**Equilibrio con costos fijos de negocio:** con un ejemplo de US$150/mes (contador, legal prorrateado, dominio), unos **12 usuarios**. Es un SUPUESTO: hay que reemplazarlo con cotizaciones reales.

| Churn mensual (SUPUESTO) | Vida media | LTV (contribución) | CAC máximo sano (LTV/3) |
|---|---|---|---|
| 5 % | 20 meses | US$297 | US$99 |
| 8 % | 12,5 meses | US$186 | US$62 |
| 12 % | 8,3 meses | US$124 | US$41 |
| 15 % | 6,7 meses | US$99 | US$33 |

Recuperar un CAC de US$50 tarda unos 3,4 meses, sea cual sea el churn.

**Lectura:** con churn alto, típico de herramientas de cripto en mercados bajistas y sin un historial verificable, el CAC no debería superar unos US$35 a US$40. Eso favorece la adquisición orgánica (contenido, transparencia, referidos) frente a la publicidad pagada.

## 6. Sensibilidad

- **Proveedores de datos:** si CoinGecko exige un plan comercial, el costo sube según el plan que corresponda. El precio no se verificó y no se inventa. Es el principal riesgo de costo variable a revisar antes de cobrar.
- **Uso:** el escaneo es global, no depende de cada usuario. El costo marginal por usuario está dominado por sesiones, alertas de Telegram y consultas, todo bajo.
- **Conversión:** con una conversión de solicitud aprobada a pago del 10 % (SUPUESTO), llegar a 100 usuarios de pago exige unos 1.000 usuarios activos en el piloto.

## 7. Qué medir para cambiar los supuestos por datos

1. El plan de Neon y las CU-h reales del mes.
2. El plan del workspace de Render.
3. La licencia de CoinGecko para uso comercial.
4. Una cotización de contador y abogado.
5. Durante el piloto: solicitudes, aprobaciones, activación (primer inicio de sesión y Telegram vinculado), retención a 7 y 30 días y la intención de pago declarada.
