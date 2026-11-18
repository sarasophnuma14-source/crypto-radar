# Roadmap multiactivo · Market Radar

Versión 1.0 · 18-nov-2026. Las fases no tienen fecha: avanzan cuando cumplen su criterio de salida. **No se acelera una fase que no cumple sus criterios de calidad.** Cada fase puede dividirse en entregas pequeñas (PR revisables).

Leyenda de responsables: **P** = PATRON (decisiones, contratos, accesos), **C** = Claude (código, docs, pruebas en PR), **A** = abogado/contador externo.

---

## Fase 0 · Estabilización de Crypto Radar 2.1

Objetivo: que el producto existente sea seguro, observable e integrado antes de construir encima.

| Entregable | Resp. | Ref. |
|---|---|---|
| TOTP admin inscrito, código de alta borrado | P | P0-1 |
| Rotación de `radar_app` y token de Telegram | P | P0-2 |
| Health check `/healthz` en Render | P | P0-3 |
| Revisión y fusión autorizada de PR #11 (landing), #12 (fiabilidad), #14 (instrumentación), #13 (docs) | P (autoriza), C | P0-4, P1-1…4 |
| Copia verificada + suspensión de la 2.0 | P | P0-5 (irreversible) |
| Repositorio privado | P | P0-6 (irreversible) |
| Copias automáticas cifradas | P decide almacenamiento, C implementa | P1-5 |
| Datos de privacidad completos | P + A | P1-6 / G-16 |
| Diagnóstico de los ~12 h sin escaneo (17/18-nov) | Hilo de la 2.1 | F0-8 |
| Integración de la cadena #3→#8 en `main` | P autoriza, C ejecuta | F0-9 |
| CI (3.12 y 3.13, SQLite + PostgreSQL) | C | F0-10 |
| Decisión de licencia de datos cripto | P | F0-11 |

**Criterio de salida:** P0 cerrados con evidencia · PR #11–#14 resueltos · CI verde en `main` · 7 días de escaneos sin huecos no alertados.

---

## Fase 1 · Diseño (esta entrega y la siguiente)

| Entregable | Resp. | Estado |
|---|---|---|
| 14 documentos de la especificación §20 | C | **Esta PR (borrador)** |
| Aprobación o corrección de decisiones propuestas (`DECISION_LOG.md`) | P | Pendiente |
| Preguntas de licencia enviadas a proveedores | P | Pendiente |
| Encuesta de mercados deseados en el piloto | P/C | Pendiente |
| Segunda entrega: prototipo de interfaz, contratos de adaptadores en código, modelo de datos inicial (migraciones), pruebas aisladas, estimación de costos, plan de migración, PR propuestas | C | Tras aprobación |

**Criterio de salida:** decisiones D-005…D-012 aprobadas o sustituidas · prototipo navegable revisado · contratos de adaptador con pruebas grabadas.

---

## Fase 2 · Núcleo

Objetivo: infraestructura común con **cripto** como primer cliente, en paralelo a la 2.1.

| Entregable | Requisitos |
|---|---|
| Esquema `mr` (aditivo) y migraciones | RD-01…04 |
| Asset Registry + identificadores con vigencia | RD-01, RD-02 |
| Calendarios y sesiones (cripto 24/7 + plantilla de bolsa) | RD-05 |
| Interfaz de proveedor + adaptadores cripto reescritos | §5 TARGET_ARCHITECTURE |
| `provider_licenses` con aplicación en código | RD-10 |
| Biblioteca única de features con golden tests y equivalencia con `radar/quant` | RQ-01…04 |
| Calidad de datos generalizada | RD-06, RD-11 |
| Scanner orquestador, `scan_runs`, `scan_observations` inmutables | RA-01, RA-06, RA-09 |
| Observabilidad mínima (`/livez`, `/readyz`, métricas por proveedor y escaneo) | NF-05 |
| Worker separado **solo si** la medición lo exige | TARGET_ARCHITECTURE §9 |

**Criterio de salida:** escáner nuevo en paralelo ≥ 14 días con la 2.1; diferencias de estado por activo explicadas al 100 %; cero huecos sin alerta; restauración probada del esquema `mr`.

---

## Fase 3 · Primeros mercados: cripto y acciones/ETF

Precondición: licencia de acciones/ETF **confirmada por escrito** y contratación **autorizada por P**.

| Entregable | Requisitos |
|---|---|
| Cripto habilitado en Market Radar (lista §18 completa) | §18 |
| Acciones EE. UU. y ETF: universo histórico con deslistados, acciones corporativas, series ajustadas y sin ajustar | RD-08, RD-12 |
| Estados del Scanner, Market Opportunity Score v1 (descriptivo) | RA-05, RS-01…07 |
| Ficha de activo completa (A–D, F, G) | RB-01…08 |
| Watchlists y alertas Telegram con `alert_deliveries` | RT-01…06 |
| Interfaz: Dashboard, Scanner, Mercados, Explorador, Watchlists, Alertas, Historial | RU-01…07 |

**Criterio de salida por mercado:** lista §18 (14 puntos) con evidencia adjunta a la PR de habilitación + 30 días de calidad medida.

---

## Fase 4 · Mercados macro: forex, índices y metales preciosos

| Entregable | Nota |
|---|---|
| Forex mayores y cruces con sesiones (Sídney, Tokio, Londres, Nueva York) | Proveedor según licencia |
| Fortaleza relativa de monedas | |
| Índices: valor de referencia (si hay licencia) separado de ETF y futuros asociados | Si no hay licencia: ETF proxy etiquetado |
| Oro y plata: spot, futuros y ETF como instrumentos distintos; ratio oro/plata | RD-02, RD-09 |
| Calendario macroeconómico (fuentes públicas) | FRED, organismos oficiales |

---

## Fase 5 · Energía y agricultura

| Entregable | Nota |
|---|---|
| WTI, Brent, gas natural: contratos, series continuas con `roll_rules`, curva de futuros, contango/backwardation | RD-09 |
| Inventarios EIA, COT de la CFTC, informes USDA | Fuentes públicas con atribución |
| Agrícolas: maíz, trigo, soja (CME); café, cacao, azúcar, algodón (ICE) | ICE requiere licencia propia |
| Estacionalidad por contrato | |

---

## Fase 6 · Inteligencia global

| Entregable | Requisitos |
|---|---|
| Global Radar: fortaleza relativa por clase y sector | RG-01 |
| Correlation Engine (estática, dinámica, por régimen) | RQ-07, RG-02 |
| Regime Detection global | RQ-08 |
| Exposición al dólar, sensibilidad a tipos, energía vs financieros | RG-03 |
| Risk Center y Cartera (solo lectura, sin órdenes) | RQ-06 |

Precondición: cada mercado participante habilitado (§18).

---

## Fase 7 · IA

| Entregable | Requisitos |
|---|---|
| AI Market Analyst | RI-01…07 |
| News Intelligence (con licencia de noticias) | RI-05, S-40…45 |
| Portfolio Intelligence | S-43 |
| Research Assistant | RI-06 |
| Presupuesto y tope de costo | S-45 |

---

## Fase 8 · Validación

| Entregable | Nota |
|---|---|
| Seguimiento descriptivo de observaciones a 5/20/60 sesiones, publicado con benchmark e intervalos | QUANT_RESEARCH_PROTOCOL §9 |
| Hipótesis pre-registradas por clase con holdout nuevo | §4 del protocolo |
| Paper trading separado de producción, cohortes, estabilidad | Sin ejecución real |
| Revisión de resultados con el propietario | Incluye negativos |

---

## Camino crítico

```
Fase 0 ─► Fase 1 (decisiones + preguntas de licencia) ─► Fase 2 (núcleo con cripto)
                         │                                      │
                         └── respuestas de proveedores ─────────┴─► Fase 3 (acciones/ETF)
                                                                       ─► 4 ─► 5 ─► 6 ─► 7 ─► 8
```

Las licencias y la demanda medida en el piloto, no el código, determinan cuándo empieza la Fase 3.

## Restricciones vigentes en todas las fases

2.1 estable · NO EDGE vigente · piloto cerrado · pagos apagados · no fusionar ni desplegar sin autorización · no cambiar precios ni secretos · no activar proveedores sin licencia · no tocar el holdout · no trading real · no suspender ni borrar servicios sin autorización.
