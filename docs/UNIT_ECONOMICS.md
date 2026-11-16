# Unit economics · Crypto Radar 2.1 (solo plan Pro)

Fecha: 16 de noviembre de 2026. Cifras en dólares estadounidenses salvo que se diga otra cosa.

Este documento **reemplaza** los números de `ANALISIS_COSTOS_Y_RENTABILIDAD.md`, que suponían una mezcla Pro/Élite. La decisión preliminar del propietario es lanzar **solo Pro, a US$15 al mes o US$149 al año**, y dejar Élite para más adelante.

Cada cifra lleva una etiqueta:

| Etiqueta | Significado |
|---|---|
| **MEDIDO** | Leído en el código, en Render o en una prueba ejecutada en esta sesión. |
| **PÚBLICO** | Precio publicado por el proveedor, con fuente y fecha de consulta. |
| **SUPUESTO** | Estimación propia. No es una medición y debe reemplazarse con datos del piloto o con cotizaciones. |
| **PENDIENTE** | No hay dato y no se inventa. Se deja como variable de sensibilidad. |

> **Resumen.**
> - Con 40 % de clientes en plan anual, el ingreso medio es **US$13,97 por usuario y mes** (SUPUESTO de mezcla).
> - Después de comisiones y del tiempo de soporte quedan **US$10,93**. Si el precio incluye IVA, quedan **US$8,70**.
> - Los costos fijos mínimos para poder cobrar legalmente por los datos son unos **US$62 al mes**: Render, licencia comercial de CoinGecko y Neon Launch.
> - El equilibrio está entre 6 y 65 usuarios de pago, según lo que cuesten contador y abogado, que hoy **no están cotizados**.
> - Nada de esto dice si alguien pagará. Eso solo lo mide el piloto (`PLAN_PILOTO_90_DIAS.md`).

## 1. Correcciones a los documentos anteriores

| Documento anterior | Qué decía | Corrección | Evidencia |
|---|---|---|---|
| `ANALISIS_COSTOS_Y_RENTABILIDAD.md` §3 | ARPU US$17,99 con 70 % Pro y 30 % Élite | Con solo Pro y 40 % anual, el ARPU es **US$13,97** | Cálculo en §3 |
| ídem §1 | Licencia de datos «NO VERIFICADA», costo US$0 | CoinGecko sin clave (*Demo/keyless*) **no incluye uso comercial**. El plan Basic cuesta **US$35 al mes**, con licencia comercial y atribución obligatoria | PÚBLICO, [coingecko.com/en/api/pricing](https://www.coingecko.com/en/api/pricing), consultado el 16-nov-2026 |
| ídem §1, riesgo de Neon | Solo consideraba el cómputo (CU-h) | También se agota la **transferencia** del plan Free (5 GB al mes): el planificador descargaba `latest.json` entero cada 30 s | §5 de este documento |
| ídem §4 | Margen bruto cercano al 80 % | Con solo Pro y la licencia de datos, el margen es del **69 % al 77 %** sin IVA y del **53 % al 61 %** con IVA incluido en el precio | §6 |
| ídem §5 | Equilibrio de unos 12 usuarios con US$150 de costos fijos | Con el ARPU de solo Pro y la licencia de datos, son **15 a 19 usuarios** con US$100 de costos de negocio | §7 |
| Backend, `radar/billing.py` línea 20 | `PRICES_USD` = Pro 19/190 y Élite 39/390 | **No coincide** con la propuesta 15/149. No se cambia: las reglas prohíben tocar precios del backend. Habrá que cambiarlo, con autorización, antes de activar cobros | MEDIDO |

## 2. Qué incluye hoy el plan Pro (MEDIDO en el código)

Definido en `radar/auth.py`, `PLANS`, rama `release-2.1`:

| Plan | Ranking | Telegram | Cartera | Salidas | Memecoins | Backtest |
|---|---|---|---|---|---|---|
| `free` («Libre») | 3 activos | no | no | no | no | no |
| `pro` | 20 activos | sí | sí | sí | sí | no |
| `elite` | 20 activos | sí | sí | sí | sí | sí (estático) |

La exportación CSV y el límite de 50 activos en la lista de seguimiento son iguales en todos los planes.

**Élite solo se diferencia de Pro por un backtest estático**, y ese backtest pertenece a un motor sin ventaja estadística demostrada (`crypto-radar-edge-v3`: NO EDGE). Hoy no es un diferenciador vendible; ver `MODELO_NEGOCIO_VALIDADO.md` §4.

## 3. Ingreso por usuario (ARPU)

Precios propuestos: US$15 al mes; US$149 al año, que equivalen a US$12,42 al mes (17,2 % de descuento). **No están en el backend.**

| Clientes en plan anual (SUPUESTO) | ARPU mensual |
|---|---|
| 20 % | US$14,48 |
| **40 % (base)** | **US$13,97** |
| 60 % | US$13,45 |

### MRR, ARR y caja no son lo mismo

- **MRR** (ingreso recurrente mensual): un plan anual cuenta como US$149 / 12 = US$12,42 al mes.
- **ARR = MRR × 12.** Es una tasa anualizada, **no dinero cobrado**. Supone que nadie cancela durante 12 meses.
- **Caja:** el plan anual se cobra completo el primer día (US$149). Contablemente es ingreso diferido: si hay reembolso, se devuelve. El mensual se cobra mes a mes y deja de entrar cuando el cliente cancela.

Ejemplo con 100 clientes nuevos en el mes 0 y 8 % de cancelación mensual (SUPUESTO):

| Indicador | Valor |
|---|---|
| ARR en el mes 0 | US$16.760 |
| Caja cobrada en 12 meses | unos US$13.090: 60 clientes mensuales × US$15 × 7,92 meses medios + 40 anuales × US$149 |

La diferencia es del 22 %. Nunca se debe presentar el ARR como dinero cobrado.

## 4. Comisiones de cobro

Los pagos están **desactivados** y siguen así. Las cifras sirven solo para planificar.

| Medio | Fórmula | Pro mensual US$15 | Pro anual US$149 | Fuente |
|---|---|---|---|---|
| Wompi (tarjeta, PSE, Nequi) | 2,65 % + COP 700, más 19 % de IVA sobre la comisión | US$0,68 (4,5 %) | US$4,91 (3,3 %) | PÚBLICO, [enter.co, 3-oct-2026](https://www.enter.co/fintech/wompi-baja-la-tarifa-del-qr-al-1-y-amplia-los-pagos-desde-el-celular/). La tasa COP 4.000/US$ es SUPUESTO |
| NOWPayments (USDT) | 1 % (1,5 % con conversión) + red | US$0,65 | US$1,99 | PÚBLICO, [nowpayments.io](https://nowpayments.io/help/about-nowpayments/about/what-are-your-fees), 16-nov-2026. Red US$0,50: SUPUESTO |

Con 70 % de cobros con tarjeta y 30 % en USDT (SUPUESTO), la comisión media es **US$0,54 por usuario y mes (3,8 %)**.

No incluido: contracargos, retenciones de la pasarela y costos de conversión bancaria (**PENDIENTE**, hay que preguntar a Wompi y al contador).

## 5. Neon: consumo real y efecto del sondeo de 30 segundos

**Lo que no se pudo medir.** Esta sesión no tiene acceso a la consola ni a la API de Neon. **El consumo real de CU-h y de transferencia no está medido.** PATRON debe leerlo en *Neon Console → Billing / Usage* del proyecto `mute-sky-79699743`.

**Lo que sí se midió en el código (MEDIDO):**

1. `radar/server.py`, `scheduler()`, llama a `next_scan_time()` cada 30 s. Esa función ejecutaba `storage.read("latest.json")`, y con `DATABASE_URL` cada lectura descarga el documento **entero** desde Neon.
2. Un escaneo sintético de 40 activos generó un `latest.json` de unos 158 KB. El real tiene 70 activos según `/healthz`, así que debe ser más grande.
3. Render consulta `/healthz` periódicamente, y esa ruta también leía el informe entero. En la PR #12 queda en caché 60 s.
4. Con lecturas cada 30 s, Neon **nunca entra en suspensión** (se suspende tras 5 minutos sin actividad). El bloqueo de líder de la PR #12 hace además `SELECT 1` cada 15 s, así que tampoco dejaría suspender.

**Estimaciones (SUPUESTO, derivadas del tamaño sintético):**

| Concepto | Antes de la corrección | Después de la corrección (PR #12) |
|---|---|---|
| Transferencia por el sondeo | 2.880 lecturas al día × 0,3 a 0,6 MB ≈ **0,9 a 1,7 GB al día, 26 a 52 GB al mes** | 2.880 lecturas × unos 100 bytes ≈ **menos de 10 MB al mes** |
| Cómputo (0,25 CU siempre encendido) | 0,25 × 730 h ≈ **182 CU-h al mes** | Igual: la base sigue despierta |

**Consecuencias según el plan de Neon:**

| Plan de Neon | Antes de la corrección | Con la corrección |
|---|---|---|
| **Free** | Los 5 GB de transferencia se agotarían en 3 a 6 días. Las 100 CU-h se agotarían hacia el día 16. En ambos casos la base **se suspende** y la app deja de funcionar | La transferencia deja de ser problema. El cómputo se sigue agotando hacia el día 16: **el plan Free no sirve para un servicio siempre encendido** |
| **Launch** | 500 GB incluidos, sin costo extra. Cómputo 182 × US$0,106 ≈ **US$19,35 al mes** | Igual: unos **US$19,70 al mes** con menos de 1 GB de almacenamiento (US$0,35 por GB-mes) |

Fuente de precios: PÚBLICO, [neon.com/pricing](https://neon.com/pricing), consultado el 16-nov-2026.

**Corrección hecha (sin desplegar):** commit `a48500e` en la PR #12.

- `db.get_kv_fields` extrae en SQL solo las claves necesarias (`jsonb ->` en PostgreSQL, `json_extract` en SQLite).
- `next_scan_time()` y `/healthz` ya no descargan el informe.
- Pruebas: `tests/test_fiabilidad.py`, clase `LecturaParcial`, sobre archivos, SQLite y PostgreSQL 16. Suites: 20/20, 309/309, 29/29 y 39/39 en verde.

**Verificación pendiente después del despliegue:** comparar la transferencia diaria en la consola de Neon de los 3 días anteriores con los 3 posteriores.

## 6. Costos fijos y escenarios

### Costos fijos mínimos para cobrar

| Concepto | US$/mes | Tipo |
|---|---|---|
| Render, web `crypto-radar-2-1` (starter) | 7,00 | MEDIDO (plan) + PÚBLICO (precio) |
| Render, servicio 2.0 (todavía activo) | 7,00 | MEDIDO. **Se elimina al suspender la 2.0**; no se cuenta |
| Render, cuota del workspace | 0 o 25 | PENDIENTE (no visible con el conector) |
| CoinGecko Basic (licencia comercial) | 35,00 | PÚBLICO. Obligatorio para cobrar mientras se use CoinGecko. El límite de llamadas del plan debe verificarse contra el uso real |
| Neon Launch | 19,70 | SUPUESTO (§5) |
| Binance, Bybit (velas y derivados) | ? | **PENDIENTE.** No hay respuesta oficial sobre uso comercial; hace falta confirmación escrita o un proveedor con licencia |
| alternative.me (Fear & Greed) | 0 | PÚBLICO: uso comercial permitido con atribución junto al dato |
| Telegram Bot API | 0 | PÚBLICO |
| **Total mínimo conocido** | **61,70** | |

### Costos de negocio sin cotizar (PENDIENTE)

- contador y facturación electrónica DIAN;
- abogado para términos y privacidad (G-16);
- dominio y correo;
- registro de marca;
- tiempo del responsable.

**No se inventan.** En §7 se tratan como una variable F de 0, 100, 250 o 500 al mes.

### Escenarios por usuarios de pago

Bases (SUPUESTO):

- ARPU US$13,97 y comisiones del 3,8 %.
- Soporte: 15 minutos por usuario al mes a US$10/h, es decir, US$2,50 por usuario.
- Infraestructura por escenario: la misma de `ANALISIS_COSTOS_Y_RENTABILIDAD.md` §4. Las pruebas de 100 usuarios fueron locales y **no prueban capacidad en Render**.
- CoinGecko Basic en todos los escenarios. El escaneo es global, así que las llamadas no crecen con los usuarios, pero hay que verificarlo.

| Usuarios de pago | MRR | ARR (no es caja) | Comisiones | Infraestructura | Datos | Soporte | Contribución sin IVA | % | Contribución con IVA incluido | % |
|---|---|---|---|---|---|---|---|---|---|---|
| 50 | 698 | 8.380 | 27 | 27 | 35 | 125 | 484 | 69 % | 373 | 53 % |
| 100 | 1.397 | 16.760 | 54 | 27 | 35 | 250 | 1.031 | 74 % | 808 | 58 % |
| 250 | 3.492 | 41.900 | 134 | 62 | 35 | 625 | 2.635 | 75 % | 2.078 | 60 % |
| 500 | 6.983 | 83.800 | 269 | 120 | 35 | 1.250 | 5.310 | 76 % | 4.195 | 60 % |
| 1.000 | 13.967 | 167.600 | 538 | 170 | 35 | 2.500 | 10.724 | 77 % | 8.494 | 61 % |

«Con IVA incluido» supone que todos los clientes son colombianos y que el precio de US$15 ya incluye el 19 % de IVA. Si se cobra encima del precio, se aplica la columna sin IVA. **Si el IVA aplica, y a qué clientes, lo decide el contador** (PENDIENTE). No se asume ninguna exención.

No incluido: impuesto de renta, ICA, costos de negocio (F) ni adquisición de clientes.

## 7. Contribución, equilibrio, LTV y CAC

**Contribución por usuario y mes** (SUPUESTO), igual a ARPU menos comisiones menos soporte:

| Caso | Contribución |
|---|---|
| Sin IVA | **US$10,93** |
| Con IVA incluido en el precio | **US$8,70** |

**Punto de equilibrio**, en usuarios de pago, con costos fijos de US$61,70 + F:

| F (costos de negocio, PENDIENTE) | Sin IVA | Con IVA incluido |
|---|---|---|
| 0 | 6 | 8 |
| 100 | 15 | 19 |
| 250 | 29 | 36 |
| 500 | 52 | 65 |

**LTV y CAC.** No hay datos de cancelación ni de costo de adquisición: los dos son **PENDIENTE** hasta el piloto. La tabla muestra el rango.

| Cancelación mensual (SUPUESTO) | Vida media | LTV sin IVA | CAC máximo sano (LTV/3) | LTV con IVA | CAC máximo con IVA |
|---|---|---|---|---|---|
| 5 % | 20 meses | US$219 | US$73 | US$174 | US$58 |
| 8 % | 12,5 meses | US$137 | US$46 | US$109 | US$36 |
| 12 % | 8,3 meses | US$91 | US$30 | US$72 | US$24 |
| 15 % | 6,7 meses | US$73 | US$24 | US$58 | US$19 |
| 20 % | 5 meses | US$55 | US$18 | US$43 | US$14 |

Recuperar un CAC de US$30 tarda 2,7 meses; uno de US$50, 4,6 meses. Los dos sin IVA.

**Lectura:**

- A US$15 con una cancelación probable del 10 % al 15 %, la publicidad pagada solo funciona si cada cliente cuesta **menos de US$20 a US$30**. En cripto eso es poco realista con anuncios: las plataformas restringen los anuncios de cripto y la competencia por las palabras clave es alta.
- El canal inicial debe ser **orgánico** (`PLAN_PILOTO_90_DIAS.md` §6).
- El CAC orgánico no es cero: es tiempo del responsable, y debe registrarse en horas.

## 8. Qué datos reemplazan cada supuesto

| Supuesto | Dato real | Cuándo |
|---|---|---|
| CU-h y transferencia de Neon | Consola de Neon | Ya; y 3 días después de desplegar la PR #12 |
| Plan del workspace de Render | Panel de Render | Ya |
| Límites de llamadas de CoinGecko Basic | Contador de llamadas del escáner durante 7 días | Antes de contratar |
| Licencia de Binance y Bybit | Respuesta escrita o contrato | Antes de cobrar |
| IVA, renta, facturación electrónica | Concepto escrito del contador | Antes de cobrar |
| Costos legales (F) | Cotización del abogado | Antes de cobrar |
| Mezcla mensual/anual | Intención declarada en el piloto; luego cobros reales | Día 60 del piloto |
| Cancelación | Cohortes del primer trimestre de cobro | 3 meses después del lanzamiento |
| CAC | Horas y gasto por canal ÷ clientes de pago atribuidos | Desde el lanzamiento |
