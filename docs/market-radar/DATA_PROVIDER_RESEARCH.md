# Investigación de proveedores de datos · Market Radar

Fecha de consulta: **18 de noviembre de 2026** (salvo que se indique otra).
Método: solo fuentes públicas (páginas de precios, bases de conocimiento y términos de los proveedores). **No se contrató, no se creó ninguna cuenta y no se pidió ninguna cotización.**

Etiquetas:

| Etiqueta | Significado |
|---|---|
| **VERIFICADO** | Leído hoy en una página oficial del proveedor (enlace incluido) |
| **VERIFICADO (16-nov)** | Leído en la auditoría del 16-nov-2026 |
| **SECUNDARIO** | Lo dice una página de un tercero o de un competidor; hay que confirmarlo con el proveedor |
| **NO VERIFICADO** | No se encontró o no se pudo leer; no debe usarse para decidir |

> **Advertencia general.** Los precios y términos de datos de mercado cambian a menudo y casi siempre dependen de: (a) si el usuario final es "profesional" o "no profesional"; (b) si los datos se **muestran** a terceros (*display*); (c) si se **redistribuyen**; (d) si se publican **datos derivados**. Además, muchas bolsas cobran tarifas propias por usuario, aparte del proveedor. Antes de activar cualquier proveedor hay que obtener los términos **por escrito** para el caso de uso concreto de Market Radar: aplicación web de pago, usuarios no profesionales en varios países, visualización con retraso o de cierre, alertas por Telegram, sin redistribución en bruto.

---

## 1. Criterios de evaluación

Cobertura · calidad · latencia · historial · disponibilidad · precio · derechos de visualización · uso comercial · redistribución · datos derivados · límites de usuarios · SLA · atribución (especificación §15). En la tabla resumen de cada mercado se puntúan solo los criterios con evidencia; el resto queda "?".

---

## 2. Criptomonedas

| Proveedor | Qué ofrece | Licencia / uso comercial | Estado |
|---|---|---|---|
| **CoinGecko** | Capitalización, universo, categorías, precios agregados | Sin clave (Demo) **no incluye uso comercial**. Plan Basic **US$35/mes** con licencia comercial y **atribución obligatoria** | VERIFICADO (16-nov), [coingecko.com/en/api/pricing](https://www.coingecko.com/en/api/pricing) |
| **Binance** (spot, futuros, `data.binance.vision`) | Velas, libro, funding, open interest; archivo histórico diario | No hay política oficial publicada sobre uso comercial de la API pública; una consulta en el foro de desarrolladores quedó sin respuesta oficial. `data.binance.vision` tiene un PDF de términos propio que **no se leyó** | NO VERIFICADO. [Foro](https://dev.binance.vision/t/public-rest-api-for-commercial-use-case/23067), [Términos Binance Vision](https://data.binance.vision/Binance_Vision-Terms_of_Use.pdf) |
| **Bybit, OKX** | Velas de respaldo | Términos de uso de datos no revisados | NO VERIFICADO |
| **Coinbase, Kraken** | Velas spot USD | Accesibles desde la nube el 16-nov; términos no revisados | NO VERIFICADO |
| **Agregadores de pago** (CoinAPI, Kaiko, CryptoCompare/CCData, Amberdata) | Datos normalizados multi-exchange, licencias comerciales explícitas | CoinAPI publica una política de uso comercial ([enlace](https://www.coinapi.io/usage-policy)) que no se leyó en detalle | NO VERIFICADO |

**Observaciones técnicas (MEDIDO en la 2.1):** CoinGecko limita mucho las IPs compartidas de Render (fallback a caché de 24 h en `scanner.py`); `api.binance.com` devuelve 451 desde EE. UU. (la 2.1 usa región Frankfurt y `data-api.binance.vision`).

**Recomendación preliminar:** mantener exchanges como fuente de velas solo tras confirmar por escrito el uso comercial con al menos uno (o pasar a un agregador con licencia explícita); CoinGecko Basic para universo y capitalización.

---

## 3. Acciones y ETF (EE. UU.)

| Proveedor | Planes individuales | Planes con visualización a terceros | Notas | Estado |
|---|---|---|---|---|
| **Massive** (antes Polygon.io) | US$29 / 79 / 199 al mes por mercado, **solo uso personal** | **Business obligatorio en cuanto alguien distinto de ti ve los datos, incluidos testers y staging.** Business autoservicio: Stocks **US$2.499/mes**, Currencies **US$999/mes**, Options US$1.999/mes. Futuros por ventas | Fundamentals +US$29/mes; noticias Benzinga +US$99/mes. Usar los datos para un trabajo o una empresa (incluida una LLC) te hace "profesional" | VERIFICADO: [qué plan necesito](https://massive.com/knowledge-base/article/which-plan-do-i-need-to-show-massive-data-in-my-app). Precios: página comparativa de Massive fechada 23-oct-2026, [enlace](https://massive.com/compare/massive-vs-tiingo) |
| **Twelve Data** | Grow, Pro, Ultra: uso personal o interno, **sin visualización comercial** | **Venture US$499/mes** ("external display"; tiempo real EE. UU., tiempo real UE, Australia con retraso, cierre de acciones y ETF globales, materias primas, renta fija, fundamentales). **Enterprise US$1.099/mes** ("external distribution", +datos de ETF y análisis). Enterprise+ a medida (white-label). Anual −17 % | Datos de precio no estadounidenses requieren aprobación adicional para uso comercial. Datos derivados públicos exigen atribución. ASX solo interno salvo licencia ASX. Basic US$0 = "internal non-display" | VERIFICADO: [uso comercial](https://support.twelvedata.com/en/articles/5332349-commercial-and-personal-usage), [precios business](https://twelvedata.com/pricing-business). Cobertura de forex, cripto e índices en Venture **no confirmada** |
| **Tiingo** | Power US$30/mes; uso comercial interno US$50/mes | "Planes solo de uso interno"; mostrar a terceros exige licencia de redistribución aparte, sin precio público | | SECUNDARIO (página de Massive). [api.tiingo.com](https://api.tiingo.com) |
| **Financial Modeling Prep** | Planes individuales | La visualización pública exige un **Data Display and Licensing Agreement**, también con acceso gratuito | Sin precio publicado del acuerdo | VERIFICADO: [enlace](https://site.financialmodelingprep.com/insights/platform/can-you-use-fmp-data-in-a-public-app-website-or-client-dashboard) |
| **EODHD** | Planes personales solo para uso personal | Planes comerciales por cotización; EODHD informa a las bolsas de los usuarios comerciales; alta en ~3 días hábiles | Clasificación profesional/no profesional según las bolsas | VERIFICADO: [enlace](https://eodhd.com/financial-apis/commercial-vs-personal-license-use) |
| **Alpaca, Alpha Vantage, Nasdaq Data Link, Intrinio** | — | — | No revisados | NO VERIFICADO |

**Conclusión preliminar:** no existe una vía barata y limpia para mostrar precios de acciones a usuarios de pago. El menor precio público verificado con visualización externa es **Twelve Data Venture, US$499/mes** (US$414/mes en anual), y aún así hay que confirmar tarifas de bolsa por usuario y el alcance de "display".

---

## 4. Forex

| Proveedor | Datos | Licencia | Estado |
|---|---|---|---|
| Massive Currencies Business | FX y cripto, tiempo real | US$999/mes con display | VERIFICADO (página de Massive) |
| Twelve Data | FX en plan Basic (interno); en Venture **no confirmado** | — | NO VERIFICADO para display |
| OANDA Exchange Rates API | Tipos de cambio históricos y actuales | Página de precios existe; no se leyó | NO VERIFICADO ([enlace](https://www.oanda.com/foreign-exchange-data-services/en/exchange-rates-api/api-pricing/)) |
| BCE (tipos de referencia diarios), FRED (series de la Fed) | Cierres diarios de referencia, no negociables | FRED: ver §8 | Parcial |

**Nota técnica:** el forex es OTC; cada proveedor da precios distintos. El sistema debe guardar el proveedor y no mezclar fuentes en una misma serie.

---

## 5. Metales preciosos

| Fuente | Instrumento | Estado |
|---|---|---|
| Futuros COMEX (GC, SI) vía Databento u otro distribuidor CME | Futuros | Ver §6 |
| XAU/USD, XAG/USD spot OTC (Massive Currencies, Twelve Data, OANDA) | Spot | NO VERIFICADO que incluyan metales con display |
| ETF (GLD, SLV, IAU…) | ETF | Mismo proveedor que acciones/ETF |
| Precio de referencia LBMA | Referencia | Licenciado por LBMA/ICE; **NO VERIFICADO** |

---

## 6. Futuros (energía, metales, agrícolas, índices)

| Proveedor | Precio público | Licencia | Estado |
|---|---|---|---|
| **Databento (CME Globex MDP 3.0)** | Plan **Standard US$179/mes** (anuncio del 16-abr-2025); un anuncio posterior habla de datos CME en vivo "desde US$32,65/mes" | Los términos de visualización, redistribución y tarifas profesional/no profesional **no están en la página leída**. CME cobra tarifas de bolsa propias | Precio VERIFICADO (anuncio de Databento, [enlace](https://databento.com/blog/introducing-new-cme-pricing-plans)); licencia NO VERIFICADA. Databento tiene un programa para startups ([enlace](https://databento.com/startups)) no revisado |
| Massive Futures | Por ventas | Business por ventas | VERIFICADO que es por ventas |
| ICE (Brent, café, cacao, azúcar, algodón) | — | ICE Futures Europe/US con licencias propias | NO VERIFICADO |

**Consecuencia:** Brent, café, cacao, azúcar y algodón cotizan principalmente en ICE, no en CME. Un solo distribuidor CME no cubre todas las materias primas de la especificación.

---

## 7. Índices

| Fuente | Hallazgo | Estado |
|---|---|---|
| S&P Dow Jones Indices | Licencia los valores en tiempo real de sus índices a medios para mostrarlos en webs y apps; la página no aclara retraso ni cierre | VERIFICADO parcial: [enlace](https://www.spglobal.com/spdji/en/about-us/data-index-licensing) |
| CME Group | Tiene una FAQ sobre por qué CME gestiona la licencia de los índices S&P y Dow Jones intradía (título del resultado de búsqueda; **no se leyó**) | NO VERIFICADO ([enlace](https://www.cmegroup.com/articles/faqs/sp-indices-and-dow-jones-indices-licensing-faq.html)) |
| Nasdaq, FTSE Russell, STOXX/DAX, Nikkei | Cada familia de índices tiene su propio licenciante | NO VERIFICADO |

**Alternativa de bajo costo a evaluar:** mostrar ETF asociados (SPY, QQQ, DIA, IWM, EWG, EWU, EWJ) en lugar del índice, con el proveedor de acciones/ETF, y etiquetarlos como "proxy negociable", no como el índice.

---

## 8. Macro, energía y agricultura (fuentes públicas)

| Fuente | Datos | Términos | Estado |
|---|---|---|---|
| **FRED (Fed de San Luis)** | Tipos, dólar, inflación, empleo | No prohíbe uso comercial en general, pero: series de terceros con "Copyright" en las notas requieren permiso del propietario; no se puede replicar la experiencia de FRED; aviso obligatorio "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis"; enlace a sus términos si otros usan la app | VERIFICADO: [términos](https://fred.stlouisfed.org/docs/api/terms_of_use.html) |
| **EIA** | Inventarios de crudo y gas, precios spot de referencia | Permite desarrollar servicios para mostrar y analizar sus datos; atribución obligatoria ("EIA" / "U.S. Energy Information Administration"); no implicar respaldo; límites de uso a discreción | VERIFICADO: [términos](https://www.eia.gov/opendata/terms-of-service.php) |
| **CFTC COT** | Posiciones semanales por mercado de futuros | Libre en cftc.gov desde 1995; se publica los viernes 15:30 ET con datos del martes; la página no indica restricciones de uso | VERIFICADO parcial: [enlace](https://www.cftc.gov/MarketReports/CommitmentsofTraders/AbouttheCOTReports/index.htm) |
| **USDA (WASDE, NASS)** | Oferta y demanda agrícola, cosechas | Probablemente de dominio público como obra del gobierno de EE. UU. | NO VERIFICADO |
| **NOAA / Copernicus** (clima) | Clima para agrícolas | — | NO VERIFICADO |
| **BCE, Banco de la República** | Tipos de referencia | — | NO VERIFICADO |

Estas fuentes son la base más barata y defendible para contexto macro y catalizadores (Fases 4–6), pero **no dan precios negociables**.

---

## 9. Noticias

| Fuente | Precio | Licencia | Estado |
|---|---|---|---|
| Benzinga vía Massive | +US$99/mes sobre un plan Massive | Hereda la licencia del plan base (individual ≠ display) | VERIFICADO (página de Massive) |
| Tiingo News API | — | — | NO VERIFICADO ([enlace](https://api.tiingo.com/products/news-api)) |
| GDELT, RSS de emisores y organismos oficiales | Gratis | Uso de titulares y enlaces; textos completos con derechos de autor | NO VERIFICADO |

Regla de diseño: guardar título, enlace, fecha y fuente; resumir solo si la licencia lo permite; nunca republicar el texto completo.

---

## 10. Combinaciones candidatas por fase

| Fase | Combinación mínima candidata | Costo de datos público verificado | Lo que falta confirmar |
|---|---|---|---|
| 2–3 cripto | CoinGecko Basic + exchange(s) con uso comercial confirmado | US$35/mes | Términos de Binance/Coinbase/Kraken |
| 3 acciones/ETF | Twelve Data Venture | US$499/mes (≈US$414 anual) | Tarifas de bolsa por usuario, alcance de display con retraso, alertas por Telegram |
| 3 alternativa | Massive Stocks Business | US$2.499/mes | Igual |
| 4 forex + metales spot | Massive Currencies Business o Twelve Data (si Venture lo incluye) | US$999/mes o incluido | Cobertura de metales; display |
| 4 índices | ETF proxy (sin costo adicional) | 0 adicional | Etiquetado correcto |
| 4–5 futuros CME | Databento | desde US$179/mes + tarifas CME | Display, no profesionales, ICE |
| 4–6 macro | FRED + EIA + CFTC + USDA | 0 | Series con copyright en FRED |

Las cifras alimentan `MULTI_ASSET_UNIT_ECONOMICS.md`. **Ninguna se contrata en esta etapa.**

---

## 11. Preguntas para enviar a cada proveedor (borrador, no enviado)

1. Caso: aplicación web de suscripción, usuarios no profesionales, mayoría en Latinoamérica, datos mostrados con X minutos de retraso o al cierre. ¿Qué plan lo cubre?
2. ¿Hay tarifas de bolsa por usuario además del plan? ¿Cuánto por usuario no profesional?
3. ¿Se pueden mostrar **datos derivados** (indicadores, scores, estados) sin mostrar el precio en bruto? ¿Con qué atribución?
4. ¿Se pueden enviar alertas por Telegram con el precio o solo con el estado derivado?
5. ¿Cuánto tiempo podemos almacenar velas diarias e intradía? ¿Se pueden usar para investigación interna después de cancelar?
6. ¿Staging y testers cuentan como visualización?
7. ¿SLA, límites de llamadas, historial disponible y política de correcciones?
