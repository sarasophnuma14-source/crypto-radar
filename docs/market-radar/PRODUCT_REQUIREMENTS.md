# Requisitos de producto · Market Radar

Versión 1.0 · 18-nov-2026. Cada requisito tiene un identificador para trazarlo en `IMPLEMENTATION_BACKLOG.md`.
Prioridad: **M** (imprescindible para habilitar la fase), **S** (debería), **C** (podría).
Fase: la de `MULTI_ASSET_ROADMAP.md` en la que se entrega.

---

## 1. Requisitos transversales de datos

| Id | Requisito | Prioridad | Fase |
|---|---|---|---|
| RD-01 | Todo activo tiene un `asset_id` interno estable; los tickers son identificadores con vigencia, nunca la clave | M | 2 |
| RD-02 | Se distingue activo subyacente de instrumento cotizable (índice ≠ ETF ≠ futuro ≠ spot) | M | 2 |
| RD-03 | Toda vela, cotización u observación guarda: proveedor, timestamp de origen, timestamp de recepción, temporalidad, versión de procesamiento y estado de calidad | M | 2 |
| RD-04 | Todo timestamp se guarda en UTC; la presentación usa la zona del usuario y la del mercado | M | 2 |
| RD-05 | Las velas diarias de mercados con sesión se cierran según el calendario del mercado, no a medianoche UTC | M | 2 |
| RD-06 | Un dato más viejo que su umbral de frescura (relativo a la sesión) reduce la confianza; por encima de un segundo umbral impide clasificar | M | 2 |
| RD-07 | Los activos por debajo del umbral de liquidez de su clase quedan excluidos del ranking (visibles en la ficha con el motivo) | M | 2 |
| RD-08 | Las acciones corporativas (splits, dividendos) se aplican con series ajustadas y no ajustadas guardadas por separado | M | 3 |
| RD-09 | Los futuros se comparan solo por contrato o mediante series continuas con regla de rollover declarada y versionada | M | 4–5 |
| RD-10 | Ningún dato se almacena ni se muestra si `provider_licenses` no lo permite para ese uso (almacenamiento, visualización, exportación, datos derivados) | M | 2 |
| RD-11 | Los huecos de datos y de escaneo generan un evento de calidad y una alerta operativa | M | 2 |
| RD-12 | Se conserva el universo histórico por fecha (incluidos deslistados) para evitar sesgo de supervivencia en investigación | M | 3 |

## 2. Motor A · Global Scanner

| Id | Requisito | Prioridad | Fase |
|---|---|---|---|
| RA-01 | Escaneo programado por mercado, alineado a su calendario (no se escanea un mercado cerrado salvo para cierre de sesión) | M | 2 |
| RA-02 | Escaneo manual por mercado o categoría (solo administrador en el piloto) | S | 3 |
| RA-03 | Filtros por liquidez, volatilidad, clase, mercado, sector y capitalización | M | 3 |
| RA-04 | Detección de anomalías de volumen, rupturas, momentum, compresión y cambio de régimen, cada una con regla documentada | M | 3 |
| RA-05 | Estado por activo y temporalidad: Acumulación potencial, Compresión, Señal temprana, Confirmación, Tendencia activa, Expansión, Agotamiento, Invalidado, Sin datos suficientes | M | 3 |
| RA-06 | Cada cambio de estado se registra en `scan_observations` con evidencia y versión; nunca se sobrescribe | M | 2 |
| RA-07 | Ranking por mercado y ranking global; el global solo incluye mercados habilitados según §18 de la especificación | M | 3/6 |
| RA-08 | Comparación de hasta N activos de mercados distintos con normalización declarada (retorno, volatilidad, z-score) | S | 6 |
| RA-09 | Cada ejecución (`scan_runs`) registra inicio, fin, universo, proveedores, fallos y duración | M | 2 |
| RA-10 | Texto fijo en la interfaz: "Los estados describen configuraciones observadas; no son garantías de movimientos futuros" | M | 3 |

## 3. Motor B · Deep Analysis (ficha de activo)

| Id | Requisito | Prioridad | Fase |
|---|---|---|---|
| RB-01 | Identificación: nombre, símbolo, clase, mercado, proveedor, moneda, horario, estado de cotización | M | 3 |
| RB-02 | Datos: último precio con fecha y hora, OHLCV por temporalidad, volumen, liquidez, spread, calidad y frescura | M | 3 |
| RB-03 | Técnico: tendencia, momentum, soportes/resistencias estimados, ATR, RSI, MACD, medias, bandas, rupturas, divergencias, estructura | M | 3 |
| RB-04 | Cuantitativo: retornos, volatilidad realizada, drawdown, correlación, distribución, comportamiento por régimen, benchmark | M | 3 |
| RB-05 | Contexto: noticias, resultados, calendario macro, sector, oferta/demanda (según licencias) | S | 6–7 |
| RB-06 | Escenarios alcista, bajista y neutral, cada uno con condiciones de confirmación e invalidación y riesgos | M | 3 |
| RB-07 | Historial: observaciones previas, cambios de estado, resultado posterior medido a horizontes fijos, datos faltantes | M | 3 |
| RB-08 | Toda cifra de la ficha enlaza su procedencia (proveedor, timestamp, versión) | M | 3 |

## 4. Motores cuantitativos

| Id | Motor | Salida mínima | Fase |
|---|---|---|---|
| RQ-01 | Trend | alcista / bajista / lateral / ruptura / reversión potencial / cambio de régimen, con regla y valores | 2–3 |
| RQ-02 | Momentum | fuerza, aceleración, desaceleración, divergencias, persistencia | 2–3 |
| RQ-03 | Volume | volumen relativo por sesión comparable, anomalías, confirmación | 2–3 |
| RQ-04 | Volatility | volatilidad histórica y realizada, ATR, compresión, expansión, eventos extremos | 2–3 |
| RQ-05 | Liquidity | spread, volumen negociado, profundidad si existe, deslizamiento estimado | 3 |
| RQ-06 | Risk | volatilidad, drawdown, gap, concentración, correlación, evento, calidad de datos | 3 |
| RQ-07 | Correlation | estática, dinámica (ventanas), por régimen, exposición común | 6 |
| RQ-08 | Regime | tendencia, lateral, alta/baja volatilidad, estrés, transición, por mercado y global | 3/6 |
| RQ-09 | Catalyst | eventos con fuente y fecha | 6–7 |

Reglas comunes (M): funciones puras y causales (el valor en *t* solo usa datos ≤ *t*); entrada y salida tipadas; versión semántica por motor; pruebas con valores de referencia; misma implementación en producto y en investigación.

## 5. Market Opportunity Score

| Id | Requisito | Prioridad |
|---|---|---|
| RS-01 | Score 0–100 por activo y temporalidad, con componentes: tendencia, momentum, volumen, volatilidad, liquidez, contexto, calidad de datos, evidencia histórica | M |
| RS-02 | Ponderación configurable por clase de activo, guardada como versión inmutable (`model_versions`) | M |
| RS-03 | La interfaz muestra los componentes y la versión, no solo el número | M |
| RS-04 | Texto fijo: "El score no es una probabilidad de ganancia ni una recomendación" | M |
| RS-05 | Calidad de datos por debajo del umbral → score no calculado ("Sin datos suficientes") | M |
| RS-06 | El componente "evidencia histórica" vale 0 y se muestra "sin evidencia validada" hasta que exista una hipótesis aprobada según `QUANT_RESEARCH_PROTOCOL.md` | M |
| RS-07 | Probabilidades solo tras evento, horizonte y calibración validados fuera de muestra, con intervalo | M (restricción) |

## 6. Inteligencia artificial

| Id | Requisito | Prioridad | Fase |
|---|---|---|---|
| RI-01 | Cuatro servicios separados: AI Market Analyst, News Intelligence, Portfolio Intelligence, Research Assistant | M | 7 |
| RI-02 | La IA solo recibe datos ya calculados por los motores, con fuente y fecha; no calcula precios ni indicadores | M | 7 |
| RI-03 | Cada respuesta separa hechos, interpretaciones e hipótesis y cita fuente y fecha | M | 7 |
| RI-04 | Se registra modelo, versión, prompt de sistema (hash), entradas (referencias) y salida | M | 7 |
| RI-05 | El contenido externo (noticias, páginas) se trata como datos; defensa contra inyección de instrucciones (`SECURITY_AND_PRIVACY_REQUIREMENTS.md` §6) | M | 7 |
| RI-06 | Validación posterior: toda cifra en la respuesta debe coincidir con un dato de la entrada; si no, la respuesta se descarta | M | 7 |
| RI-07 | Sin probabilidades salvo modelo validado (RS-07) | M | 7 |

## 7. Radar global e intermercado

| Id | Requisito | Fase |
|---|---|---|
| RG-01 | Fortaleza relativa por clase y por sector, normalizada por volatilidad | 6 |
| RG-02 | Matriz de correlaciones con ventana declarada y fecha | 6 |
| RG-03 | Exposición al dólar, sensibilidad a tipos, oro/plata, energía vs activos financieros | 6 |
| RG-04 | Texto fijo: "Correlación no implica causalidad" | 6 |

## 8. Experiencia de usuario

| Id | Requisito | Prioridad |
|---|---|---|
| RU-01 | Responsive, mobile-first; navegación inferior en móvil | M |
| RU-02 | Secciones: Dashboard, Global Radar, Scanner, Mercados, Explorador, Watchlists, Alertas, Cartera, Risk Center, Noticias y eventos, Historial, Análisis IA, Backtesting, Administración | M (por fases) |
| RU-03 | Cambiar de mercado conserva filtros, temporalidad y preferencias (estado por usuario en servidor) | M |
| RU-04 | Cada pantalla muestra la frescura del dato y si el mercado está abierto | M |
| RU-05 | Exportación solo para datos cuya licencia la permita; el botón no aparece si no | M |
| RU-06 | Accesibilidad AA en contraste y navegación por teclado | S |
| RU-07 | Español como idioma principal; números y fechas con formato local | M |

## 9. Telegram

| Id | Requisito | Prioridad |
|---|---|---|
| RT-01 | Tipos: nueva configuración, cambio de estado, invalidación, evento de riesgo, resumen de mercado, watchlist, cartera | M |
| RT-02 | Contenido: activo, mercado, fecha y hora, estado, score y versión, temporalidad, evidencia principal, riesgos, invalidación, fuente, enlace | M |
| RT-03 | Límite de frecuencia por usuario, deduplicación por (usuario, activo, tipo, estado), reintentos con espera y registro en `alert_deliveries` | M |
| RT-04 | Preferencias por usuario (mercados, tipos, horario silencioso) | M |
| RT-05 | Sin promesa de entrega instantánea ni ejecución de órdenes | M |
| RT-06 | No enviar a Telegram datos cuya licencia prohíba redistribución fuera de la aplicación (verificar por proveedor) | M |

## 10. Requisitos no funcionales

| Id | Requisito | Objetivo inicial (a medir) |
|---|---|---|
| NF-01 | Disponibilidad de la web | 99 % mensual en piloto (sin SLA comercial) |
| NF-02 | Retraso máximo entre cierre de vela y observación | Diario: 30 min tras el cierre de sesión; intradía: 2 × la temporalidad |
| NF-03 | Tiempo de respuesta de la ficha | p95 < 1,5 s con datos en caché |
| NF-04 | Reproducibilidad | Reejecutar un `scan_run` con la misma versión y datos da las mismas observaciones |
| NF-05 | Observabilidad | Métricas por proveedor (latencia, errores, cuota), por escaneo (duración, huecos) y por endpoint |
| NF-06 | Recuperación | RPO 24 h, RTO 4 h en piloto, con restauración probada |
| NF-07 | Costo | Ningún componente nuevo sin estimación en `MULTI_ASSET_UNIT_ECONOMICS.md` |
| NF-08 | Pruebas | Suite en CI en cada PR; cobertura de motores ≥ 90 % de ramas |

## 11. Criterios de habilitación de un mercado

Copia literal de la especificación §18, convertida en lista de verificación que se adjunta a cada PR de habilitación:

- [ ] Fuente de datos aprobada
- [ ] Licencia aplicable confirmada por escrito
- [ ] Modelo de datos normalizado
- [ ] Calendario y sesiones funcionando
- [ ] Calidad de datos medida (≥ 30 días)
- [ ] Temporalidades correctas
- [ ] Indicadores con pruebas
- [ ] Scanner con pruebas
- [ ] Análisis profundo con trazabilidad
- [ ] Errores y datos faltantes manejados
- [ ] Alertas probadas
- [ ] Observabilidad
- [ ] Procedimiento de reversión
- [ ] Documentación actualizada

El radar global se habilita solo cuando cada módulo que participa cumple la lista.

## 12. Fuera de alcance

Ejecución de órdenes, conexión a brókeres, apalancamiento, señales con probabilidad, oferta pública, pagos, opciones (no está en los ocho universos), datos de nivel 2/profundidad de bolsa en acciones.
