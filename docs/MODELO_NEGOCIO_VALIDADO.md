# Modelo de negocio · Crypto Radar 2.1

Fecha: 16 de noviembre de 2026. Complementa `UNIT_ECONOMICS.md`, que tiene los números.

> **Estado de validación.** Lo que está validado es **técnico**: la aplicación funciona y está probada. **Nada comercial está validado todavía:**
> - no hay un solo cobro;
> - no hay medición de retención;
> - no hay intención de pago registrada.
>
> El título dice «validado» porque cada afirmación de este documento se contrastó con el código o con una fuente pública. El modelo comercial en sí sigue siendo una **hipótesis**, y el piloto existe para confirmarla o refutarla.

## 1. Qué se vende (y qué no)

**Producto:** un panel que, cada 4 horas, ordena unos 70 criptoactivos según indicadores técnicos, de derivados, de sentimiento y de mercado. Lo complementan:

- alertas por Telegram;
- un diario de cartera con reglas de salida;
- una pestaña de memecoins que se actualiza cada hora;
- exportación CSV.

**No se vende:**

- **Una ventaja estadística.** La ronda de validación v3 probó 35 configuraciones y usó el holdout una sola vez. Resultado: **sin ventaja demostrada**. Ese resultado se mantiene publicado y no se borra.
- **Rentabilidad, señales de compra «ganadoras» ni gestión de dinero.**

**Propuesta de valor honesta:**

- ahorra el tiempo de revisar muchas fuentes;
- un solo lugar con contexto ordenado y alertas;
- transparencia sobre las limitaciones del producto.

Es una herramienta de organización y vigilancia, no de predicción.

**Implicación comercial.** El producto compite con herramientas de gráficos y datos que ya existen, no con «bots de señales». Hay que demostrar disposición a pagar por **comodidad y transparencia**, sin el gancho de la rentabilidad. Es el riesgo principal del modelo.

## 2. Para quién (hipótesis a validar en el piloto)

| Segmento (SUPUESTO) | Por qué podría pagar | Qué lo refutaría |
|---|---|---|
| Inversor minorista hispanohablante que ya sigue el mercado a diario | Ahorra tiempo; alertas en Telegram; producto en español | Uso semanal bajo (menos de 2 días por semana) en el piloto |
| Persona que opera con reglas y lleva un diario | Diario de cartera y salidas en el mismo lugar | Menos del 20 % de los activos registra posiciones |
| Creador de contenido o comunidad cripto | Ranking exportable como insumo | No pide la exportación ni la comparte |

Fuera del público: quien busca rentabilidad garantizada o copiar operaciones. El producto debe decirle «no es para ti».

## 3. Oferta inicial: solo Pro

| Elemento | Decisión preliminar | Estado en el código (MEDIDO) |
|---|---|---|
| Precio | US$15 al mes o US$149 al año | **No coincide**: el backend tiene 19/190 (`radar/billing.py`, `PRICES_USD`). Cambiarlo requiere autorización |
| Contenido | Ranking de 20 activos, Telegram, cartera, salidas, memecoins, CSV | Existe (`radar/auth.py`, `PLANS["pro"]`) |
| Élite | Diferido | Existe en el código con 39/390. Debe **ocultarse de la venta** hasta tener diferenciadores (§4) |
| Pagos | Desactivados | Imposibles durante el piloto (G-09 del piloto, pruebas `T32`) |

**Comparación de precio (PÚBLICO, 16-nov-2026; ver `BENCHMARK_COMPETITIVO.md`):**

- TradingView Essential: US$12,95 al mes en pago anual.
- CryptoQuant Advanced: US$29 al mes en pago anual.
- Glassnode Advanced: US$49 al mes en pago anual.

US$15 queda por encima de la herramienta de gráficos más conocida y por debajo de los datos *on-chain*. Se justifica solo si el usuario valora el ranking en español y las alertas integradas. **Lo mide la encuesta del piloto**; hoy no se sabe.

## 4. Élite: qué haría falta para justificarlo

**Hoy (MEDIDO):** Élite = Pro + un backtest estático.

Ese backtest muestra rentabilidades retrospectivas positivas de un motor **sin ventaja demostrada**. Venderlo como valor añadido sería engañoso. Por eso no cuenta como diferenciador, y debería **retirarse o mostrarse junto a los resultados negativos** (ver la auditoría, C-2).

**Regla del propietario:** Élite solo se lanza con **2 o más diferenciadores reales**.

Cada diferenciador debe cumplir tres condiciones:

1. Estar construido y probado, no solo prometido.
2. No depender de afirmar una ventaja estadística.
3. Haber sido pedido o usado por al menos el 20 % de los usuarios activos del piloto.

| Candidato | Valor sin prometer rentabilidad | Esfuerzo (SUPUESTO) | Riesgo |
|---|---|---|---|
| **Historial auditable de señales**: cada señal publicada con su fecha y su resultado posterior, **incluidos los negativos**, exportable | Transparencia verificable; nadie más lo ofrece así | M. Reutiliza el módulo prospectivo, que hoy tiene **0 hipótesis registradas** | Si los resultados son malos, se muestran igual. Es el punto |
| **Alertas personalizadas**: umbrales propios por activo y métrica (precio, *funding*, RSI, cambio de rango) | Ahorra tiempo de vigilancia | M | Carga de Telegram; límites por usuario |
| **Más activos o frecuencia mayor**: más de 70 activos, o escaneo cada hora | Más cobertura | M o A. **Sube el costo de datos** (límites de CoinGecko y Binance) | Hay que recalcular la licencia |
| **Acceso por API o webhook** al ranking | Para comunidades y creadores | M | Redistribuir datos de terceros puede violar sus licencias. **Requiere licencia** |
| **Varias carteras o asientos de equipo** | Comunidades pequeñas | M | Soporte |
| **Soporte prioritario con tiempo de respuesta escrito** | Tranquilidad | B en código; A en tiempo del responsable | Solo se puede prometer lo que se cumple |

**Recomendación (SUPUESTO):** los candidatos más sólidos son el historial auditable y las alertas personalizadas. No dependen de licencias nuevas y refuerzan la transparencia. Decidir con los datos del día 60 del piloto.

## 5. ¿Plan gratuito como adquisición?

**Existe en el código** como plan `free` («Libre»): ranking de 3 activos, sin Telegram, cartera, salidas ni memecoins.

| A favor | En contra |
|---|---|
| Baja la barrera para probar | La licencia de CoinGecko se paga igual: es **uso comercial** aunque el usuario no pague |
| Embudo para contenido orgánico | Con 3 activos el valor apenas se ve, y puede convertir mal |
| Costo marginal de cómputo muy bajo: el escaneo es global (MEDIDO) | Soporte y abuso: hay que mantener los límites de registro |

**Recomendación:**

- **Durante el piloto, no abrir un plan gratuito público.** El piloto ya es gratuito y cerrado.
- Al lanzar, probar **una de dos opciones**, no las dos a la vez:
  - **(a)** prueba de 14 días de Pro **sin tarjeta**, que hoy no existe en el código;
  - **(b)** plan gratuito permanente con ranking de 5 a 10 activos y **sin alertas**.
- Elegir con este criterio del piloto: si **más del 40 %** de los activos solo usa el ranking (no Telegram ni cartera), el gratuito limitado no les mostrará valor diferencial, y la prueba es mejor.

## 6. Ingresos y costos

- **Ingresos:** suscripción. Ver `UNIT_ECONOMICS.md` §3 sobre MRR, ARR y caja.
- **Costos fijos conocidos:** US$61,70 al mes (Render, licencia de CoinGecko y Neon Launch, este último estimado).
- **Costos variables:** comisiones del 3,8 % y soporte.
- **Sin cotizar:** contador, abogado y licencia de Binance/Bybit.
- **Margen de contribución:** del 69 % al 77 % sin IVA y del 53 % al 61 % con IVA incluido (SUPUESTO).

## 7. Licencias de datos: condición para cobrar

| Fuente | Uso en la app (MEDIDO) | Uso comercial | Acción |
|---|---|---|---|
| CoinGecko API sin clave | Capitalización y metadatos | **No incluido** en Demo/keyless. Basic US$35 al mes lo incluye, con atribución «Data provided by CoinGecko» y enlace (PÚBLICO, 16-nov-2026) | Contratar Basic **antes del primer cobro**; añadir la atribución en la UI (hoy no existe) |
| alternative.me (Fear & Greed) | Sentimiento | Permitido con atribución junto al dato (PÚBLICO) | Añadir la atribución en la UI (hoy no existe) |
| Binance API pública | Velas y derivados | **Sin respuesta oficial.** Un hilo del foro de desarrolladores no tiene respuesta del equipo | Pedir confirmación escrita; si no llega, evaluar un proveedor con licencia (costo PENDIENTE) |
| Bybit API pública | Derivados | No verificado | ídem |
| Telegram Bot API | Alertas | Permitido según los términos de la plataforma | — |

## 8. Riesgos del modelo

1. **Demanda:** la gente puede no pagar por un producto que dice no tener ventaja demostrada. Es el riesgo central. Lo mide el piloto.
2. **Licencias:** si Binance no autoriza el uso comercial, cambiar de fuente puede costar más que todo el margen a escala pequeña.
3. **Regulación:** la línea entre «información» y «asesoría de inversión» depende del país. Requiere concepto de abogado (PENDIENTE).
4. **Concentración:** un solo responsable para producto, soporte y operación.
5. **Mercado:** en un mercado bajista la cancelación sube. No hay dato para estimarla.

## 9. Próxima decisión

La decisión de lanzar no se toma con este documento. Se toma con los criterios cuantitativos de `DECISION_COMERCIAL_GO_NO_GO.md`, al terminar el piloto de `PLAN_PILOTO_90_DIAS.md` y con los requisitos de `REQUISITOS_LANZAMIENTO.md` cerrados.
