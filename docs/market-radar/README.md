# Market Radar · Primera entrega (especificación §20)

Fecha: 18-nov-2026. Rama: `claude/project-thread-dclqgc` (desde `release-2.1`). Solo documentación: no cambia código, producción, secretos, precios, pagos, holdout ni el paper trading en curso.

| # | Documento | Contenido |
|---|---|---|
| 1 | [AUDIT_CURRENT_ARCHITECTURE.md](AUDIT_CURRENT_ARCHITECTURE.md) | Auditoría de la 2.1, deuda que bloquea multiactivo, Fase 0 |
| 2 | [PRODUCT_VISION.md](PRODUCT_VISION.md) | Visión, público, principios, qué no haremos |
| 3 | [PRODUCT_REQUIREMENTS.md](PRODUCT_REQUIREMENTS.md) | Requisitos con identificador, criterios §18 |
| 4 | [TARGET_ARCHITECTURE.md](TARGET_ARCHITECTURE.md) | Monolito modular, paquetes, contrato de adaptador, criterios de infraestructura |
| 5 | [ASSET_DATA_MODEL.md](ASSET_DATA_MODEL.md) | Activo / instrumento / serie, tablas, procedencia |
| 6 | [DATA_PROVIDER_RESEARCH.md](DATA_PROVIDER_RESEARCH.md) | Proveedores por mercado con fuentes y fecha |
| 7 | [DATA_LICENSE_MATRIX.md](DATA_LICENSE_MATRIX.md) | Qué permite cada licencia; ningún mercado nuevo habilitable hoy |
| 8 | [QUANT_RESEARCH_PROTOCOL.md](QUANT_RESEARCH_PROTOCOL.md) | Pre-registro, holdout por clase, métricas, aprobación |
| 9 | [SECURITY_AND_PRIVACY_REQUIREMENTS.md](SECURITY_AND_PRIVACY_REQUIREMENTS.md) | Bloqueos heredados y requisitos nuevos |
| 10 | [MULTI_ASSET_ROADMAP.md](MULTI_ASSET_ROADMAP.md) | Fases 0–8 con criterios de salida |
| 11 | [MULTI_ASSET_UNIT_ECONOMICS.md](MULTI_ASSET_UNIT_ECONOMICS.md) | Costos de datos por escenario y equilibrio |
| 12 | [RISK_REGISTER.md](RISK_REGISTER.md) | Riesgos con probabilidad, impacto y mitigación |
| 13 | [IMPLEMENTATION_BACKLOG.md](IMPLEMENTATION_BACKLOG.md) | Épicas e historias por fase |
| 14 | [DECISION_LOG.md](DECISION_LOG.md) | Decisiones aprobadas, propuestas y pendientes |

## Segunda entrega · Revisión de arquitectura y preparación (18-nov-2026)

Revisión crítica de los 14 documentos anteriores, que no se editaron (el análisis de brechas actúa como fe de erratas).

| # | Documento | Contenido |
|---|---|---|
| 15 | [SPECIFICATION_GAP_ANALYSIS.md](SPECIFICATION_GAP_ANALYSIS.md) | 53 hallazgos, 8 bloqueantes para I-1 con su resolución |
| 16 | [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) | 12 decisiones: Mantener / Modificar / Rechazar con impacto, riesgo y alternativa |
| 17 | [DATA_QUALITY_TEST_PLAN.md](DATA_QUALITY_TEST_PLAN.md) | Reglas de calidad con umbrales, fixtures sintéticos, cobertura por incremento |
| 18 | [QUANT_VALIDATION_REVIEW.md](QUANT_VALIDATION_REVIEW.md) | Separación de datos, holdout, sesgos, costos, potencia estadística |
| 19 | [ECONOMIC_REVIEW.md](ECONOMIC_REVIEW.md) | Escenarios recalculados, costos omitidos, sensibilidad |
| 20 | [PHASE_1_IMPLEMENTATION_PLAN.md](PHASE_1_IMPLEMENTATION_PLAN.md) | Incremento I-1: núcleo de activos y contratos, sin proveedores ni señales |
| 21 | [READINESS_VERDICT.md](READINESS_VERDICT.md) | Veredicto: READY FOR FOUNDATION (condicionado); 0 líneas de código existen |

## Cierre de revisión · Preparación de I-1 (18-nov-2026)

Seis correcciones obligatorias aplicadas sobre `ARCHITECTURE_REVIEW`, `SPECIFICATION_GAP_ANALYSIS`, `PHASE_1_IMPLEMENTATION_PLAN` (v2), `DECISION_LOG` (D-021…D-027) y `ECONOMIC_REVIEW` (§7), con trazabilidad por Id.

| # | Documento | Contenido |
|---|---|---|
| 22 | [I1_READINESS_REPORT.md](I1_READINESS_REPORT.md) | Informe final A–H: correcciones, pendientes, riesgos, arquitectura, estimación, archivos, veredicto **READY FOR I-1** y solicitud de autorización |
