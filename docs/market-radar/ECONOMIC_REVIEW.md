# Revisión económica · Market Radar

Fecha: 18-nov-2026. Objeto: `MULTI_ASSET_UNIT_ECONOMICS.md` (primera entrega) y su base `evolucion-saas/UNIT_ECONOMICS.md` (PR #13).
No se cambian precios, no se contrata nada y no se pidió ninguna cotización.

## 0. Etiquetas

| Etiqueta | Significado |
|---|---|
| **PÚBLICO** | Precio publicado por el proveedor, con fuente y fecha |
| **COTIZACIÓN** | Precio ofrecido por escrito al proyecto. **Hoy no existe ninguna** |
| **SUPUESTO** | Estimación propia, con fórmula |
| **PENDIENTE** | No hay dato; no vale cero y no entra en los totales |

> **Resumen.**
> 1. Los equilibrios de la primera entrega se reproducen con diferencias de redondeo (≤ 1 usuario).
> 2. Faltaban costos que pueden ser mayores que el propio plan de datos: las **tarifas de bolsa**. Ejemplo público verificado: Nasdaq Basic cobra US$1,00 por usuario no profesional y tiene tarifas de distribuidor externo de US$2.140 y de licencia de datos derivados de US$1.500 por empresa. Si recayeran sobre el proyecto, el equilibrio de acciones/ETF pasaría de **52 a 273–424 usuarios**.
> 3. El costo de Neon no es fijo: el plan Launch no tiene mínimo y cobra por uso. Con el worker manteniendo la base despierta, 0,25 CU todo el mes ≈ US$19,35.
> 4. La IA es barata frente a los datos: entre US$0,05 y 2,00 por usuario y mes según modelo y uso (SUPUESTO de uso).
> 5. Con una devaluación del 20 % del COP o con IVA sobre servicios importados, el equilibrio sube 10–25 %.
> 6. **Ningún escenario multiactivo es viable sin cotizaciones escritas.** La única cifra sólida es cripto: 6–8 usuarios para costos de datos e infraestructura, 15–65 con costos de negocio.

---

## 1. Contribución por usuario (recalculada)

| Concepto | Fórmula | Valor | Etiqueta |
|---|---|---|---|
| ARPU | 0,6 × 15 + 0,4 × 149/12 | **13,97** | SUPUESTO de mezcla 60/40 sobre precios hipotéticos |
| Comisiones de cobro | 3,8 % × ARPU | 0,531 | PÚBLICO (tarifas) + SUPUESTO (mezcla) |
| Soporte | 15 min × US$10/h | 2,50 | SUPUESTO |
| **Contribución sin IVA (c)** | ARPU − comisiones − soporte | **10,94** | La primera entrega decía 10,93 (redondeo de comisiones a 0,54) |
| **Contribución con IVA incluido (cᵢ)** | ARPU / 1,19 − comisiones − soporte | **8,71** | La primera entrega decía 8,70 |

Equilibrio: **N = ⌈F / c⌉**, con F = costos fijos mensuales.

## 2. Escenarios recalculados

Costos fijos (US$/mes):

| Escenario | Fórmula de F | F | Etiquetas |
|---|---|---|---|
| S1 cripto | Render 7 + CoinGecko Basic 35 + Neon 19,70 | 61,70 | PÚBLICO, PÚBLICO, SUPUESTO |
| S2 + acciones/ETF | S1 + worker 7 + Twelve Data Venture 499 | 567,70 | SUPUESTO, PÚBLICO |
| S2b ídem anual | S1 + 7 + 499 × (1 − 0,17) | 482,87 | El "−17 %" es PÚBLICO; aplicarlo como × 0,83 es SUPUESTO |
| S3 + forex | S2 + Massive Currencies Business 999 | 1.566,70 | PÚBLICO (página comparativa de Massive, 23-oct-2026) |
| S4 + futuros CME | S3 + Databento Standard 179 | 1.745,70 | PÚBLICO (anuncio de abril de 2025; **no reconfirmado hoy**) |
| S5 acciones con Massive | S1 + 7 + 2.499 + 999 | 3.566,70 | PÚBLICO |

Equilibrio por costos de negocio F_neg (contador, abogado, dominio, etc.; PENDIENTE, se usa como sensibilidad):

| Escenario | F_neg = 0 | 100 | 250 | 500 |
|---|---|---|---|---|
| S1 | 6 / 8 | 15 / 19 | 29 / 36 | 52 / 65 |
| S2 | 52 / 66 | 62 / 77 | 75 / 94 | 98 / 123 |
| S2b | 45 / 56 | 54 / 67 | 67 / 85 | 90 / 113 |
| S3 | 144 / 180 | 153 / 192 | 167 / 209 | 189 / 238 |
| S4 | 160 / 201 | 169 / 212 | 183 / 230 | 206 / 258 |
| S5 | 327 / 410 | 336 / 422 | 349 / 439 | 372 / 467 |

(sin IVA / con IVA incluido en el precio). Diferencia con la primera entrega: S3 con IVA 181 → **180** por el redondeo de cᵢ. El resto coincide.

## 3. Costos omitidos en la primera entrega

### 3.1 Tarifas de bolsa por usuario y por empresa

Ejemplo verificado: **lista de precios de Nasdaq para renta variable de EE. UU. 2025–2027** ([PDF oficial](https://www.nasdaqtrader.com/content/ProductsServices/PriceList/Nasdaq_US_Equities_Price_List_2025_2026_2027.pdf), consultada el 18-nov-2026):

| Concepto (Nasdaq Basic, 2026) | Valor | Etiqueta |
|---|---|---|
| Usuario no profesional | US$1,00 por usuario (otra tabla de uso: US$0,60 entre 1 y 9.999 usuarios) | PÚBLICO; **cuál aplica depende del producto y del distribuidor: NO VERIFICADO** |
| Usuario profesional | US$28,50 por usuario | PÚBLICO |
| Distribuidor externo | US$2.140 por empresa | PÚBLICO; periodicidad no confirmada en el extracto leído (**probablemente mensual, NO VERIFICADO**) |
| Licencia de datos derivados no profesionales | US$1.500 por empresa | PÚBLICO; ídem |

**Quién paga esto es la pregunta clave:** si el proveedor (Twelve Data, Massive) actúa como distribuidor y lo incluye, el proyecto solo paga el plan; si el proyecto es el distribuidor externo, paga además estas tarifas. **PENDIENTE de respuesta escrita** (pregunta 2 de `DATA_PROVIDER_RESEARCH` §11).

Efecto en S2 (sin IVA):

| Supuesto | Fórmula | Equilibrio |
|---|---|---|
| Plan incluye todo | 567,70 / 10,94 | 52 |
| + US$0,60 por usuario | 567,70 / (10,94 − 0,60) | 55 |
| + US$1,00 por usuario | 567,70 / (10,94 − 1,00) | 58 |
| + distribuidor externo mensual | (567,70 + 2.140) / 9,94 | **273** |
| + distribuidor + datos derivados | (567,70 + 2.140 + 1.500) / 9,94 | **424** |

NYSE, CME e ICE tienen listas propias: **PENDIENTE**.

### 3.2 Licencias de visualización y redistribución

| Concepto | Estado |
|---|---|
| Display en Twelve Data | Incluido en Venture (PÚBLICO); datos no estadounidenses requieren aprobación aparte (PÚBLICO) |
| Redistribución (exportación, Telegram) | Twelve Data: acuerdo aparte (PÚBLICO); precio PENDIENTE |
| Índices (S&P DJI y otros) | Contrato; PENDIENTE |
| Velas de exchanges cripto | PENDIENTE (ya bloquea la 2.1) |

### 3.3 Datos históricos

| Concepto | Estado |
|---|---|
| Historial incluido en los planes | No confirmado para Venture ni Massive Business: PENDIENTE |
| Databento | Cobra el histórico por uso además del plan (PÚBLICO: "usage-based historical data" sigue disponible); importe PENDIENTE |
| Historial con deslistados (necesario para investigación) | PENDIENTE: puede ser un producto aparte |

### 3.4 Almacenamiento (Neon)

Precios PÚBLICOS ([neon.com/pricing](https://neon.com/pricing), consultado el 18-nov-2026): Launch sin mínimo; cómputo US$0,106/CU-h; almacenamiento US$0,35/GB-mes; 500 GB de transferencia incluidos, luego US$0,10/GB. Free: 1 GB por proyecto, 100 CU-h/mes, suspensión del cómputo si se exceden.

| Partida | Fórmula | Valor |
|---|---|---|
| Filas de velas diarias (10 años, 3.600 instrumentos) | 300×365×10 + 3.000×252×10 + 300×252×10 | ≈ 9,46 M |
| Tamaño normalizado | 9,46 M × 250 B | ≈ 2,4 GB |
| Con capa cruda | × 1,6–2 | ≈ 3,8–4,7 GB |
| Costo de almacenamiento | 4,7 × 0,35 | ≈ **US$1,65/mes** |
| Cómputo, 0,25 CU todo el mes | 0,25 × 730 × 0,106 | **US$19,35/mes** |
| Cómputo, 0,5 CU todo el mes | 0,5 × 730 × 0,106 | US$38,69/mes |
| Cómputo, 1 CU todo el mes | 730 × 0,106 | US$77,38/mes |

Conclusión: el almacenamiento es irrelevante; **el cómputo domina** y depende de si la base puede escalar a cero. Un worker que consulte cada pocos segundos la mantiene despierta (como pasó con `latest.json`). Base separada para `mr` (ARCHITECTURE_REVIEW §4) = un segundo cómputo: +US$0 si escala a cero entre ingestas, hasta +US$19–39 si no.

### 3.5 Inteligencia artificial (Fase 7)

Precios por millón de tokens (PÚBLICO, lista de precios de Anthropic incluida en su SDK, actualizada el 3-nov-2026; **verificar en la página oficial antes de presupuestar**): Haiku 5.5 US$0,10 / 0,50; Sonnet 5.5 US$2 / 10; Opus 5.5 US$4 / 20 (entrada / salida). El razonamiento interno del modelo se factura como salida.

Fórmula: costo = Σ (tokens de entrada × p_entrada + tokens de salida × p_salida).

| Uso (SUPUESTO) | Tokens | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|---|
| Resumen de mercado | 6.000 entrada + 2.400 salida | 0,002 | 0,036 | 0,072 |
| Pregunta de investigación | 10.000 entrada + 3.000 salida | 0,003 | 0,050 | 0,100 |
| Resúmenes globales: 8 mercados × 2/día × 30 días = 480 | — | 0,86/mes | 17,28/mes | 34,56/mes |
| Asistente: 20 preguntas por usuario y mes | — | 0,05/usuario | 1,00/usuario | 2,00/usuario |

Con el asistente en Sonnet 5.5, c baja de 10,94 a 9,94 (−9 %). La caché de prompts puede reducir la entrada repetida; no se ha medido.

### 3.6 Soporte

US$2,50/usuario (SUPUESTO heredado) supone 15 min al mes. Un producto con 8 mercados genera más preguntas. Sensibilidad: con 30 min (US$5,00), c = 8,44 y el equilibrio de S2 pasa de 52 a 68.

### 3.7 Impuestos

| Concepto | Estado |
|---|---|
| IVA sobre el precio de venta | PENDIENTE (contador); ya modelado como cᵢ |
| IVA sobre servicios digitales comprados en el exterior (Render, Neon, proveedores de datos) | PENDIENTE (contador). Si aplica 19 % sobre todo F: S2 = 675,56 → equilibrio **62**; S3 = 1.864,37 → **171** |
| Retenciones en la fuente por pagos al exterior | PENDIENTE |
| Impuesto de renta, ICA | Fuera de la contribución; PENDIENTE |

### 3.8 Otros costos omitidos

| Concepto | Estado |
|---|---|
| Monitor externo de disponibilidad (DEP-04) | Hay planes gratuitos; PENDIENTE elegir |
| Almacenamiento externo de copias (PR #15) | PENDIENTE (sin cotizar) |
| Render: cuota del workspace | 0 o 25; PENDIENTE (no visible con el conector) |
| Proveedor de noticias | Benzinga +US$99 sobre Massive Business (PÚBLICO); otros PENDIENTE |
| Seguro de responsabilidad, marca | PENDIENTE |

## 4. Sensibilidad combinada (S2, sin IVA)

| Variable | Base | Escenario adverso | Equilibrio |
|---|---|---|---|
| Base | — | — | 52 |
| Soporte | 2,50 | 5,00 | 68 |
| IA (Sonnet 5.5, asistente) | 0 | 1,00/usuario | 58 |
| Tarifa de bolsa por usuario | 0 | 1,00/usuario | 58 |
| COP se deprecia 20 % (ingreso en COP, costos en USD) | c = 10,94 | c ≈ 13,97 × 0,8 − 0,53 − 2,50 = 8,15 | 70 |
| IVA sobre servicios importados | 0 % | 19 % | 62 |
| **Todo lo anterior junto** | — | c = 13,97 × 0,8 − 0,53 − 5,00 − 1,00 − 1,00 = 3,65; F = 675,56 | **186** |
| + distribuidor externo Nasdaq | — | F = 675,56 + 2.140 | **773** |

La variable que más mueve el resultado es la tarifa de distribuidor; la segunda, la combinación de soporte y moneda.

## 5. Escenario mínimo recomendado para decidir

1. Mantener cripto (S1) como único mercado con cifras sólidas.
2. Para acciones/ETF, pedir por escrito a dos proveedores el precio **todo incluido** (plan + bolsas + derivados + Telegram) para: datos de cierre o con 15 min de retraso, usuarios no profesionales, 100 y 1.000 usuarios.
3. Recalcular S2 con esas **cotizaciones** antes de cualquier decisión de Fase 3.
4. Encuesta del piloto: qué mercados usarían y si pagarían más por ellos.

## 6. Conclusión

El primer incremento técnico (I-1) **no tiene costo de datos ni de infraestructura**: se ejecuta en local con PostgreSQL y datos sintéticos. La decisión económica real llega antes de la Fase 3 y depende de cotizaciones que hoy no existen.
