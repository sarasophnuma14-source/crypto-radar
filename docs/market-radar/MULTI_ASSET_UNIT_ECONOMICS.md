# Unit economics multiactivo · Market Radar

Fecha: 18-nov-2026. Cifras en US$ al mes salvo que se diga otra cosa.
Base: `evolucion-saas/UNIT_ECONOMICS.md` (16-nov-2026) para la 2.1 con solo plan Pro.

Etiquetas: **MEDIDO** (código o prueba) · **PÚBLICO** (precio publicado, con fuente en `DATA_PROVIDER_RESEARCH.md`) · **SUPUESTO** (estimación propia) · **PENDIENTE** (sin dato; no se inventa).

> **Resumen.**
> - Con el plan Pro hipotético (US$15/mes o US$149/año, 40 % anual), cada usuario de pago deja **US$10,93** de contribución, **US$8,70** si el precio incluye IVA (de la base del 16-nov).
> - Cripto solo: equilibrio de datos e infraestructura con **6 a 8** usuarios de pago.
> - Añadir acciones y ETF con visualización licenciada (Twelve Data Venture, el menor precio público verificado) sube el equilibrio a **45–66** usuarios.
> - Añadir forex licenciado (Massive Currencies Business) lo sube a **144–181**; con futuros CME, **160–201**, **sin contar tarifas de bolsa por usuario, que están PENDIENTES**.
> - Con Massive Stocks Business en lugar de Twelve Data: **327–410** usuarios.
> - Conclusión: el orden de los mercados lo decide el costo de licencia, no la dificultad técnica. La Fase 3 solo tiene sentido económico si el piloto demuestra demanda de acciones/ETF.
> - Nada de esto dice si alguien pagará. Precios del producto: **no se cambian**.

## 1. Contribución por usuario (heredada)

| Concepto | Valor | Etiqueta |
|---|---|---|
| ARPU con 40 % anual | 13,97 | SUPUESTO de mezcla (UNIT_ECONOMICS §3) |
| Contribución tras comisiones y soporte | 10,93 | SUPUESTO (UNIT_ECONOMICS) |
| Contribución si el precio incluye IVA | 8,70 | SUPUESTO (UNIT_ECONOMICS) |

## 2. Costos fijos por escenario

| Escenario | Componentes | Costo fijo | Equilibrio (sin IVA / con IVA) |
|---|---|---|---|
| **S1 · Cripto (2.1 actual)** | Render web 7 + CoinGecko Basic 35 + Neon Launch 19,70 | **61,70** | **6 / 8** |
| **S2 · + acciones y ETF** (Twelve Data Venture mensual) | S1 + worker Render 7 (SUPUESTO) + Venture 499 | **567,70** | **52 / 66** |
| S2b · igual con Venture anual (−17 %) | S1 + 7 + 414,17 | 482,87 | 45 / 56 |
| **S3 · + forex y metales spot** (Massive Currencies Business) | S2 + 999 | **1.566,70** | **144 / 181** |
| **S4 · + futuros CME** (Databento Standard, sin tarifas CME) | S3 + 179 | **1.745,70** | **160 / 201** |
| S5 · acciones con Massive Stocks Business + FX | S1 + 7 + 2.499 + 999 | 3.566,70 | 327 / 410 |
| Macro y contexto (FRED, EIA, CFTC, USDA) | 0 en datos | 0 | — |
| Índices vía ETF proxy | incluido en proveedor de ETF | 0 | — |

Equilibrio = costo fijo ÷ contribución por usuario, redondeado hacia arriba. **No incluye** contador, abogado, dominio, marca ni el tiempo del propietario (PENDIENTE: sin cotizaciones; en UNIT_ECONOMICS se estimó que llevan el equilibrio de cripto a 15–65 usuarios).

## 3. Lo que falta y puede cambiar todo

| Partida | Por qué importa | Estado |
|---|---|---|
| Tarifas de bolsa por usuario (NYSE, Nasdaq, CME, ICE) | Pueden ser por usuario y mes, distintas para profesionales; convierten el costo fijo en variable | **PENDIENTE** |
| Licencia de índices (S&P DJI, Nasdaq, etc.) | Mostrar el índice real, no un ETF proxy | **PENDIENTE** (contrato) |
| ICE (Brent, café, cacao, azúcar, algodón) | No está en CME | **PENDIENTE** |
| Licencia comercial de velas de exchanges cripto | La 2.1 ya la necesita | **PENDIENTE** |
| Neon: almacenamiento y transferencia con 3.600 instrumentos | ~1–1,5 GB de velas (TARGET_ARCHITECTURE §8) | **PENDIENTE** de medir y de precio vigente |
| Proveedor de IA (Fase 7) | Costo por resumen y por pregunta | **PENDIENTE**: se medirá en tokens por respuesta y se aplicará el precio oficial vigente; tope mensual obligatorio (S-45) |
| Noticias con licencia | Benzinga vía Massive +99 exige plan Business | PÚBLICO, condicionado |

## 4. Contribución que haría falta por usuario

Cuánto debería dejar cada usuario de pago para cubrir solo los costos fijos de datos e infraestructura:

| Escenario | 50 usuarios | 100 usuarios | 250 usuarios | 500 usuarios |
|---|---|---|---|---|
| S1 | 1,23 | 0,62 | 0,25 | 0,12 |
| S2 | 11,35 | 5,68 | 2,27 | 1,14 |
| S3 | 31,33 | 15,67 | 6,27 | 3,13 |
| S4 | 34,91 | 17,46 | 6,98 | 3,49 |
| S5 | 71,33 | 35,67 | 14,27 | 7,13 |

Lectura: con la contribución actual de 10,93, S2 se cubre a partir de ~52 usuarios; S3 y S4 necesitan más de 140; S5 más de 320. Un precio Pro distinto es una decisión del propietario y **no se toma aquí**.

## 5. Costos variables por usuario (SUPUESTO)

| Partida | Estimación | Comentario |
|---|---|---|
| Infraestructura por usuario activo | < 0,10 | El escaneo es global; el costo crece con mercados, no con usuarios |
| Telegram | 0 | API gratuita (PÚBLICO) |
| IA (Fase 7) | PENDIENTE | Debe medirse; incluir tope por usuario |
| Tarifas de bolsa | PENDIENTE | Pueden dominar todo lo demás |

## 6. Recomendaciones económicas

1. **No contratar nada antes de que el piloto de la 2.1 dé datos de retención y disposición a pagar** (`evolucion-saas/PLAN_PILOTO_90_DIAS.md`).
2. Diseñar Fase 3 con **datos de cierre o con retraso** si la licencia lo abarata (pregunta 1 de `DATA_PROVIDER_RESEARCH.md` §11).
3. Usar **ETF como proxy** de índices y metales en las fases tempranas.
4. Usar fuentes públicas (FRED, EIA, CFTC, USDA) para contexto macro y catalizadores, que no tienen costo de datos.
5. Encuesta en el piloto: "¿Qué mercados además de cripto usarías?" antes de elegir el proveedor de Fase 3.
6. Revisar este documento con cotizaciones escritas; cada cifra PENDIENTE debe sustituirse antes de pedir autorización de contratación.
