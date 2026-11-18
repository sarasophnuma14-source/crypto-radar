# Market Radar · Veredicto de preparación (segunda entrega, §8)

Fecha: 18-nov-2026. Rama: `claude/project-thread-dclqgc`. Base revisada: commit `e5a488f` (14 documentos de la primera entrega).

## 1. Veredicto

**READY FOR FOUNDATION, condicionado.**

Lo que existe hoy es **documentación**, no software. Market Radar tiene **0 líneas de código**, 0 migraciones, 0 pruebas, 0 proveedores conectados, 0 mercados habilitados. El veredicto dice que la especificación, corregida con esta entrega, alcanza para empezar a construir el núcleo aislado (I-1); no dice que el núcleo exista ni que pueda tocar datos reales.

Condiciones para que el veredicto sea válido:

1. El propietario autoriza I-1 por escrito en el hilo.
2. El propietario aprueba (o rechaza) las decisiones marcadas «Modificar» en [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md) y los 8 bloqueantes de [SPECIFICATION_GAP_ANALYSIS.md](SPECIFICATION_GAP_ANALYSIS.md) §9.
3. I-1 se trabaja solo con PostgreSQL local, sin red ni proveedores, en rama propia y PR en borrador que **no se fusiona antes del cierre de Fase 0**.

## 2. Evaluación por nivel

| Nivel | ¿Cumple? | Evidencia |
|---|---|---|
| NO READY | No aplica | Los 8 bloqueantes para I-1 tienen resolución concreta dentro del plan ([SPECIFICATION_GAP_ANALYSIS.md](SPECIFICATION_GAP_ANALYSIS.md) §9). Ninguno exige una decisión externa (licencia, proveedor, dinero) para empezar código aislado |
| **READY FOR FOUNDATION** | **Sí, condicionado** | Ver §3 |
| READY FOR MARKET DATA | **No** | Ver §4 |
| READY FOR FIRST MARKET | **No** | 0 de 14 criterios de §18 cumplidos (§5) |
| READY FOR PRODUCTION | **No** | Ningún componente existe; Fase 0 de la 2.1 abierta; NO EDGE vigente |

## 3. Criterios de READY FOR FOUNDATION

| Criterio | Estado | Evidencia |
|---|---|---|
| Alcance acotado y verificable | Cumple | [PHASE_1_IMPLEMENTATION_PLAN.md](PHASE_1_IMPLEMENTATION_PLAN.md) §1 y §11: 7 criterios de aceptación comprobables por comando |
| No toca la 2.1 | Cumple en plan | Solo carpetas nuevas (`market_radar/`, `tests/market_radar/`, `docs/market-radar/foundation/`); prueba que impide importar `radar/` (CON-03) |
| Modelo de datos sin contradicciones conocidas | Cumple tras correcciones | INC-01 (exclusión de vigencias) e INC-02 (bitemporal) resueltos en migraciones 0001–0006 |
| Contratos de proveedores y licencias definidos | Cumple | Interfaces §4.4–4.5 del plan; `LicenseGuard` fuera de los adaptadores; solo `SyntheticProvider` |
| Reversión | Cumple en plan | Migraciones con `down` y checksum; I-1 es borrable sin afectar nada (§9 del plan) |
| Sin dependencias nuevas | Cumple | Solo `psycopg`, ya presente (§8 del plan) |
| Sin costo | Cumple | Sin Neon, sin proveedores, sin IA. CI en GitHub Actions solo si el propietario lo aprueba |
| Riesgo para producción | Nulo mientras no se fusione | PR en borrador; Fase 0 compuerta la fusión (CON-01) |
| **Autorización del propietario** | **Pendiente** | Es la condición 1 |

## 4. Por qué no READY FOR MARKET DATA

| Requisito | Estado | Evidencia |
|---|---|---|
| Licencia de datos confirmada por escrito (F0-11) | **No** | [DATA_LICENSE_MATRIX.md](DATA_LICENSE_MATRIX.md): ningún mercado nuevo habilitable; [ECONOMIC_REVIEW.md](ECONOMIC_REVIEW.md): «COTIZACIÓN: hoy no existe ninguna» |
| Fase 0 de la 2.1 cerrada | **No** | P0-1…P0-6, PR #11–#15, CI en `main` y 7 días sin huecos siguen abiertos ([MULTI_ASSET_ROADMAP.md](MULTI_ASSET_ROADMAP.md) Fase 0) |
| Base de datos separada | **No** | Decisión 4 de [ARCHITECTURE_REVIEW.md](ARCHITECTURE_REVIEW.md): proyecto o rama Neon aparte, aún no creada |
| Worker y aislamiento de secretos | **No** | Decisión 9: `mr.jobs` y proceso separado, no diseñados en código |
| Pruebas de calidad de datos ejecutables | **No** | [DATA_QUALITY_TEST_PLAN.md](DATA_QUALITY_TEST_PLAN.md) define reglas; ninguna implementada |
| Núcleo I-1 terminado | **No** | No empezado |

## 5. Criterios de §18 (FIRST MARKET)

| Criterio | Estado |
|---|---|
| Fuente de datos aprobada | No |
| Licencia confirmada por escrito | No |
| Modelo de datos normalizado | Diseñado, no implementado |
| Calendario y sesiones | Diseñado, no implementado |
| Calidad medida ≥ 30 días | No (umbrales fijados en DATA_QUALITY_TEST_PLAN §4) |
| Temporalidades correctas | No |
| Indicadores con pruebas | No (los de la 2.1 no se reutilizan sin AMB-01) |
| Scanner con pruebas | No |
| Análisis profundo con trazabilidad | No |
| Errores y datos faltantes manejados | No |
| Alertas probadas | No |
| Observabilidad | Diseñada (decisión 11), no implementada |
| Procedimiento de reversión | Solo para I-1 |
| Documentación actualizada | Parcial |

**Cumplidos: 0 de 14.**

## 6. Advertencias que el veredicto no cambia

- **Investigación:** NO EDGE sigue vigente (v3: 35 configuraciones, holdout usado una vez). Un holdout de 24 meses solo detecta Sharpe ≥ 1,76 ([QUANT_VALIDATION_REVIEW.md](QUANT_VALIDATION_REVIEW.md)). Market Radar no debe venderse como señal.
- **Economía:** el equilibrio del escenario S2 pasa de 52 a 186 suscriptores con supuestos adversos combinados, y a 773 si un distribuidor cobra licencia de display ([ECONOMIC_REVIEW.md](ECONOMIC_REVIEW.md)). Ninguna cifra de proveedor es cotización.
- **Control de cambios:** esta entrega no modificó `radar/`, la 2.1, precios, pagos, secretos, holdouts ni el paper trading, y no fusionó ni desplegó nada.

## 7. Decisión que se pide al propietario

| Opción | Efecto |
|---|---|
| Autorizar I-1 | Se crea `claude/market-radar-i1` desde `release-2.1`, PR en borrador, ≈ 2 semanas, sin red ni costos; no se fusiona antes de Fase 0 |
| Autorizar I-1 tras Fase 0 | Se espera al cierre de P0/P1 de la 2.1 antes de escribir código |
| No autorizar | Market Radar queda en documentación; se mantiene el foco en la 2.1 |

Recomendación del comité: **autorizar I-1 ahora**, porque es aislado, reversible y sin costo, y permite validar el modelo de datos antes de gastar en licencias.
