# Informe final de cierre de revisión · I-1 · Market Radar

Fecha: 18-nov-2026. Rama: `claude/project-thread-dclqgc`. Solo documentación.

**Estado del software:** Market Radar tiene **0 líneas de código**, 0 migraciones en el repositorio y 0 pruebas. Todo lo que sigue está **documentado**, no implementado. Las comprobaciones marcadas «sandbox» son consultas SQL desechables en un PostgreSQL 16.15 local temporal, hechas para verificar el diseño; no se guardaron en el repositorio y no son I-1.

## A. Correcciones realizadas

| # | Corrección pedida | Hallazgo | Decisión | Dónde | Evidencia |
|---|---|---|---|---|---|
| 1 | Bitemporalidad reproducible con escrituras concurrentes, sin depender de `MAX(recorded_at)` | INC-10 | D-021 | Plan v2 §5.3; ARCHITECTURE_REVIEW R2-1 | Sandbox, 8 escritores × 25 lotes, 60 lecturas: `MAX(recorded_at)` → **11/60** relecturas distintas; secuencia bajo candado → **0/60** |
| 2 | `btree_gist` declarada y migraciones probadas desde PostgreSQL 16 vacío | DEP-08 | D-022 | Plan v2 §5.1, prueba 6.7 | Sandbox: extensión confiable (`trusted = true`), instalada por un rol no superusuario; exclusión funcionando sin `mr` en `search_path`; `DROP SCHEMA mr CASCADE` la elimina |
| 3 | Ninguna variable de entorno puede habilitar licencias sintéticas en producción | RSK-10 | D-023 | Plan v2 §4.5, §5.2, prueba 6.5 | Se elimina `MARKET_RADAR_ENV`. Sandbox: 5/5 combinaciones prohibidas rechazadas por la base |
| 4 | Conservar el contenido original y distinguirlo de la representación canónica | INC-11 | D-024 | Plan v2 §4.4, §5.4, §5.5, prueba 6.12 | Diseño: bytes exactos + `body_sha256`, frente a codificación `c1` + `canonical_sha256`; `reparse` en la conformidad |
| 5 | Fuentes primarias: prioridades, vigencias, desempates y ausencia de fuente | INC-03 (sube a B) | D-025 | Plan v2 §4.2, §5.2, prueba 6.3 | Diseño: empates imposibles por restricción de exclusión; `PRIMARY` / `FALLBACK` / `NO_SOURCE` |
| 6 | Sensibilidad cambiaria correcta | FOR-05, FOR-06 | D-027 | ECONOMIC_REVIEW §4 y §7 | Error encontrado: la devaluación no se aplicaba a la comisión. Cifras corregidas 70 → 69, 186 → 181, 773 → 751 |
| — | Encontrado al revisar: la prueba «sin red» bloqueaba también PostgreSQL local | INC-12 | D-026 | Plan v2 §6.9 | Ahora permite solo socket Unix y loopback |
| — | Encontrado al revisar: «no conectar a Neon» no tenía mecanismo | INC-13 | D-026 | Plan v2 §3, prueba 6.13 | Guardia de conexión solo local |

Los textos sustituidos se conservan tachados con el Id que los corrige. Ningún hallazgo se borró.

## B. Hallazgos aún pendientes

Detalle en `SPECIFICATION_GAP_ANALYSIS.md` §12 (61 hallazgos).

| Grupo | Cantidad | Ids | ¿Bloquea I-1? |
|---|---|---|---|
| Bloqueantes resueltos en documentación | 15 | CON-01…03, INC-01…03, INC-10…13, JUS-01, DEP-01, DEP-08, RSK-10, AMB-01 | Ya no; se verifican al implementar |
| Pendientes antes de la fase que los usa | 21 | CON-04, CON-05, CON-08, INC-04…07, JUS-02, DEP-02…06, AMB-02…04, VER-01…05 | No |
| Pendientes menores | 9 | CON-06, CON-07, CON-09, INC-08, INC-09, JUS-03, AMB-05, AMB-06, FOR-06 | No |
| Riesgos abiertos | 9 | RSK-01…RSK-09 | No |
| Dependen de terceros o del propietario | — | `btree_gist` en Neon (NO VERIFICADO), licencia cripto F0-11, tarifas de Wompi y bancarias, mezcla de medios de pago | No para I-1; sí para I-2 y la economía |
| Fase 0 de la 2.1 | — | P0-1…P0-6, PR #11–#15, CI, 7 días sin huecos | No para empezar; **sí para fusionar** |

## C. Riesgos residuales

| Riesgo | Nivel | Mitigación |
|---|---|---|
| La reproducibilidad depende de que PostgreSQL libere el candado de transacción después de hacer visible el commit: es el comportamiento interno, no una garantía escrita del manual | Bajo | Ensayo concurrente con control negativo en cada ejecución de la suite (6.10) |
| Escrituras versionadas serializadas | Bajo en I-1/I-2 | Medir espera del candado; umbral 50 ms p95; plan B descrito |
| Alguien crea un mercado real con prefijo `zz-test-` | Bajo | Convención documentada; habilitar un mercado real exige la lista §18 |
| Almacenamiento de bytes originales mayor de lo previsto | Medio | Retención por licencia; tope de 8 MiB por respuesta; estimación real en I-2 con un formato concreto |
| Estimación de 3,5 semanas sin velocidad histórica comparable | Medio | Ruta crítica explícita; revisión al terminar T05 |
| Divergencia entre esta rama y otras que parten de `release-2.1` | Bajo | Solo carpetas nuevas |
| Sesgo de revisión: el mismo equipo diseña y revisa | Medio | Cada afirmación lleva evidencia; las de PostgreSQL se ejecutaron |
| NO EDGE sigue vigente; la economía multiactivo no tiene cotizaciones | Alto para el negocio, nulo para I-1 | I-1 no cuesta dinero ni promete señales |

## D. Arquitectura final de I-1

- **Paquete nuevo `market_radar/`** con `core`, `registry`, `calendars`, `providers`, `quality`, `storage`, `migrations` y un único `config.py` que lee solo `MARKET_RADAR_DSN`. Fronteras comprobadas por prueba; terceros: solo `psycopg`.
- **Sin acceso a la 2.1:** no importa `radar/`, `web/`, `research/` ni `main`; nada de eso importa `market_radar`; ningún archivo existente cambia.
- **Solo PostgreSQL 16 local:** guardia de conexión que rechaza cualquier DSN no local; la suite bloquea la red salvo socket Unix y loopback.
- **Datos sintéticos:** el proveedor sintético y sus licencias viven solo en `tests/`; las licencias sintéticas solo pueden cubrir mercados `zz-test-*`.
- **Migraciones 0001–0009** con `up`/`down`, checksum y candado: base y `btree_gist` → libro de escrituras → registro → proveedores y licencias → fuentes → calendarios → bytes originales → velas canónicas → eventos operativos.
- **Bitemporalidad:** secuencia `mr.write_seq` bajo candado; lectura as-of por entero; disparador que impide escribir sin `begin_write`.
- **Datos crudos y canónicos:** `raw_payloads` (bytes) → `candles` (canónica, versionada).
- **Fuentes:** `instrument_sources` sin empates posibles; selección pura y determinista.
- **~145 pruebas en 14 grupos**; 12 criterios de aceptación comprobables por comando (plan v2 §11).

## E. Estimación revisada

| | v1 | v2 |
|---|---|---|
| Esfuerzo | ≈ 2 semanas | **≈ 17 días ≈ 3,5 semanas** (rango 14–21) |
| Pruebas | ~120 | ~145 |
| Migraciones | 6 | 9 |
| Costo en dinero | 0 | 0 (sin Neon, Render, proveedores ni IA; CI de GitHub solo si se aprueba) |

Desglose en 14 tareas con dependencias y ruta crítica: plan v2 §10. SUPUESTO: no hay velocidad histórica comparable.

## F. Archivos modificados

| Archivo | Cambio |
|---|---|
| `docs/market-radar/PHASE_1_IMPLEMENTATION_PLAN.md` | Reescrito como v2 con tabla de cambios §0 |
| `docs/market-radar/ARCHITECTURE_REVIEW.md` | Resumen y §7, §8 con texto sustituido tachado; sección «Revisión 2» R2-1…R2-6; riesgos residuales |
| `docs/market-radar/SPECIFICATION_GAP_ANALYSIS.md` | Resumen con conteo rev. 1 y rev. 2; INC-03 a B; DEP-07 sustituido; RSK-01 corregido; §9 ampliado; §11 hallazgos nuevos; §12 estado de los 61 |
| `docs/market-radar/DECISION_LOG.md` | D-021…D-027 (Propuestas) y detalle de D-021, D-023, D-024 |
| `docs/market-radar/ECONOMIC_REVIEW.md` | Resumen punto 5 y tabla §4 corregidos (tachado); §7 sensibilidad cambiaria |
| `docs/market-radar/READINESS_VERDICT.md` | Cifras económicas corregidas y remisión a este informe |
| `docs/market-radar/README.md` | Índice con este informe |
| `docs/market-radar/I1_READINESS_REPORT.md` | Nuevo (este documento) |

No se modificó nada fuera de `docs/market-radar/`. No se tocó `radar/`, la 2.1, precios, pagos, secretos, variables de producción, Neon, Render, proveedores, holdouts ni paper trading. No se fusionó ni desplegó nada.

## G. Veredicto final

**READY FOR I-1.**

| Criterio | Estado | Evidencia |
|---|---|---|
| Las 6 correcciones obligatorias están resueltas y trazadas | Cumple | §A; Ids en los 5 documentos |
| Los 15 bloqueantes de I-1 tienen resolución documentada | Cumple | GAP_ANALYSIS §9 y §12 |
| Las afirmaciones de PostgreSQL que sostienen el diseño están comprobadas | Cumple en sandbox | Concurrencia 0/60 frente a 11/60; `btree_gist` sin superusuario; 5/5 combinaciones de licencia rechazadas |
| Aislamiento de la 2.1 y de producción con mecanismo, no solo con reglas | Cumple en diseño | Guardia de conexión, bloqueo de red, prueba de importaciones, `git diff` solo con altas |
| Reversión completa | Cumple en diseño | Plan §9; `up`→`down`→`up` sin restos como criterio |
| Criterios de aceptación objetivos | Cumple | 12 criterios con su comando |
| Costo | 0 | Sin servicios externos |
| Software implementado | **No existe** | El veredicto autoriza empezar, no afirma que algo funcione |

No cambia: Market Radar sigue **no listo** para datos de mercado reales, para un primer mercado (0/14 criterios de §18) y para producción.

## H. Solicitud de autorización

**Solicito al propietario autorización explícita para empezar a escribir el código de I-1** en estas condiciones:

1. Rama nueva `claude/market-radar-i1` desde `release-2.1`, PR **en borrador**.
2. Solo archivos nuevos en `market_radar/`, `tests/market_radar/` y `docs/market-radar/foundation/`.
3. Solo PostgreSQL 16 local y datos sintéticos; ninguna conexión a Neon, Render ni proveedores.
4. Sin fusionar hasta que cierre la Fase 0 **y** el propietario lo autorice de nuevo.
5. Alcance y criterios del plan v2; cualquier cambio de alcance vuelve a pedir autorización.

Decisiones que acompañan la autorización:

| Decisión | Pregunta |
|---|---|
| D-021…D-027 | ¿Se aprueban (pasan de Propuesta a Aprobada)? |
| CI | ¿Se permite añadir un workflow de GitHub Actions limitado a Market Radar (archivo nuevo en `.github/`)? Si no, la evidencia será la salida local adjunta a la PR |

Respuestas posibles: **autorizar I-1 ahora**, **autorizar I-1 tras la Fase 0**, o **no autorizar**. Hasta recibir una de ellas no se escribe código.
