# Revisión de arquitectura · Market Radar

Fecha: 18-nov-2026. Objeto: `TARGET_ARCHITECTURE.md`, `ASSET_DATA_MODEL.md` y decisiones D-005…D-013 de `DECISION_LOG.md`.
Veredictos posibles: **Mantener** · **Modificar** · **Rechazar**. Cada uno con justificación, impacto, riesgo y alternativa.

## Resumen

| # | Decisión | Veredicto |
|---|---|---|
| 1 | Separación `radar/` y `market_radar/` | **Modificar** (frontera más estricta) |
| 2 | Monolito modular | **Mantener** |
| 3 | Separación activo / instrumento / serie | **Mantener**, con 2 añadidos |
| 4 | Esquema PostgreSQL `mr` en la base de la 2.1 | **Modificar** (base separada hasta Fase 3) |
| 5 | Contrato de proveedores | **Modificar** (precisar semántica) |
| 6 | Calendarios | **Modificar** (no escribirlos a mano) |
| 7 | Normalización | **Modificar** (capa cruda y capa normalizada) |
| 8 | Persistencia histórica | **Modificar** (bitemporal) |
| 9 | Workers | **Modificar** (cola en base; separación también por secretos) |
| 10 | Escalabilidad | **Mantener** los criterios, **corregir** las cifras |
| 11 | Observabilidad | **Modificar** (SLO concretos y sondeo externo) |
| 12 | Redis, colas, microservicios | **Rechazar** por ahora (se mantiene la decisión) |

---

## 1. Separación entre `radar/` y `market_radar/` — **Modificar**

| | |
|---|---|
| Propuesta original | Paquete nuevo; reutilizar `radar/auth.py`, `radar/db.py`, `radar/quant/*` importándolos |
| Justificación del cambio | Importar `radar/` desde el núcleo hace que cualquier cambio de la 2.1 (que tiene PR abiertos #12–#15) pueda romper Market Radar, y viceversa. La 2.1 además ejecuta lógica en el arranque (archivo de usuarios heredados, degradación de administradores) |
| Nueva regla | `market_radar/` **no importa `radar/`**, salvo un único módulo `market_radar/compat/` que se crea cuando haga falta autenticación (no en I-1). Lo que se reutilice de `radar/quant` se **porta** con pruebas de equivalencia numérica, no se importa |
| Impacto | Algo de duplicación temporal (p. ej. RSI existe en dos sitios hasta que la 2.1 se retire o migre) |
| Riesgo | Divergencia entre copias; se controla con pruebas de equivalencia (criterio AMB-01) |
| Alternativa considerada | Extraer primero una biblioteca común de `radar/` (rechazada ahora: obliga a modificar `radar/`, prohibido) |
| Verificación | Prueba que recorre el AST de `market_radar/` y falla si encuentra `import radar` fuera de `compat/` |

## 2. Monolito modular — **Mantener**

| | |
|---|---|
| Justificación | Un solo responsable, presupuesto limitado, ningún componente con escala independiente medida. Las fronteras entre paquetes dan la mayor parte del beneficio de los microservicios sin su costo |
| Ajuste | Las fronteras se **comprueban automáticamente** (prueba de dependencias permitidas entre paquetes) |
| Impacto | Despliegue único; pruebas de integración sencillas |
| Riesgo | Erosión de fronteras con el tiempo |
| Alternativa | Microservicios por motor: rechazada (costo operativo, latencia, más secretos que gestionar) |

## 3. Activo / instrumento / serie — **Mantener**, con añadidos

| | |
|---|---|
| Justificación | Es la única forma limpia de cumplir "no mezclar índice, ETF, futuro y spot" y "no comparar vencimientos sin normalización" |
| Añadido A | `instrument_sources` (instrumento, proveedor, prioridad, vigencia): define la **fuente primaria** (INC-03) |
| Añadido B | Vigencias de identificadores sin solapamiento, garantizado por restricción de exclusión (INC-01) |
| Añadido C | Tipos cripto en `corporate_actions` (INC-06) |
| Impacto | 1 tabla más; consultas más explícitas |
| Riesgo | Modelado excesivo para cripto, donde activo ≈ instrumento por exchange. Aceptable: el costo es bajo |
| Alternativa | Tabla única con `kind`: rechazada (precios incompatibles en la misma fila lógica) |

## 4. Esquema `mr` en la base de producción — **Modificar**

| | |
|---|---|
| Propuesta original | Esquema `mr` en la misma base Neon que la 2.1 |
| Problema | Comparte cómputo (CU), almacenamiento, ventana de historial, copias y límites de conexiones con producción. La ingesta de velas es la carga más pesada del sistema. Un error de migración o un bucle de ingesta degradaría la 2.1, que está en piloto |
| Nueva regla | **I-1: solo PostgreSQL local** (versión 16, la de Neon). **Fase 2: proyecto o rama de Neon separada**, con roles propios. **Fase 3 o posterior:** decidir si se une a la base de la 2.1, con datos medidos |
| Migraciones | SQL numeradas (`0001_*.up.sql` / `.down.sql`), tabla `mr.schema_migrations` con checksum SHA-256; un runner de ~100 líneas sobre `psycopg` (ya es dependencia) |
| Impacto | Un costo adicional de Neon en Fase 2 (pequeño si escala a cero; ver ECONOMIC_REVIEW §5) |
| Riesgo | Unir después dos bases exige una migración; se mitiga con esquemas ya separados por nombre |
| Alternativa | Misma base con rol y `statement_timeout` limitados: viable más adelante, no recomendable mientras la 2.1 está en piloto |

## 5. Contrato de proveedores — **Modificar**

La interfaz de `TARGET_ARCHITECTURE` §5 es correcta en espíritu. Faltan precisiones que, sin ellas, cada adaptador interpretaría distinto.

| Punto | Cambio |
|---|---|
| Descriptor estático vs. estado | Separar `ProviderDescriptor` (id, versión, capacidades, temporalidades, límites declarados; inmutable y versionado) de `ProviderHealth` (dinámico) |
| Semántica temporal | Toda vela: `bar_start` inclusivo, `bar_end` exclusivo, en UTC, con `is_closed`. El adaptador **no** decide si una vela está cerrada a partir del reloj local: recibe un `Clock` inyectado |
| Paginación | `candles()` devuelve un iterador de lotes con `next_cursor`; la ingesta es reanudable |
| Correcciones | El adaptador marca `revision` si el proveedor declara correcciones; si no, la ingesta las detecta por hash del contenido |
| Errores | Jerarquía cerrada: `RateLimited(retry_after)`, `NotEntitled`, `NotFound`, `ProviderUnavailable`, `InvalidResponse`, `ContractViolation` |
| Licencia | La comprobación vive **fuera** del adaptador (`LicenseGuard` en la ingesta), para que un adaptador mal escrito no pueda saltársela |
| Pruebas | Toda implementación pasa la misma batería de conformidad (`tests/contract/`), alimentada con datos sintéticos, sin red |
| Impacto | Contrato algo más largo; adaptadores más simples de revisar |
| Riesgo | Sobrediseño si solo hay 1–2 proveedores: aceptable, el contrato es el producto de I-1 |
| Alternativa | Usar una biblioteca existente (p. ej. CCXT para cripto): útil **dentro** de un adaptador, no como contrato del sistema (no cubre acciones, licencias ni calendarios) |

## 6. Calendarios — **Modificar**

| | |
|---|---|
| Problema | La propuesta genera `market_sessions` 12 meses por adelantado pero no dice de dónde salen los festivos, horarios parciales ni cambios de horario de verano (DEP-02) |
| Nueva regla | Interfaz `MarketCalendar` con `sessions(start, end)`, `is_open(ts)`, `session_for(ts)`, `previous_close(ts)`. Implementaciones: `Continuous24x7` (cripto, cierre diario 00:00 UTC) y `TableCalendar` (lee `market_sessions`). La tabla se alimenta desde una fuente externa versionada, nunca a mano en producción |
| Fuente candidata | Biblioteca `exchange_calendars` (código abierto). **Licencia, mantenimiento y exactitud NO VERIFICADOS**: se evalúan en I-2 comparando contra el calendario oficial publicado por la bolsa para 2026–2027 |
| Zonas horarias | `zoneinfo` (biblioteca estándar); en sistemas sin base de zonas, paquete `tzdata` |
| I-1 | `Continuous24x7` real + `TableCalendar` con un calendario **ficticio de prueba** (no representa ninguna bolsa) para ejercitar festivos, medias sesiones y cambio de hora |
| Impacto | Calendarios correctos sin escribirlos a mano |
| Riesgo | Error en la fuente → velas mal fechadas. Mitigación: prueba DQ-SES de `DATA_QUALITY_TEST_PLAN` |
| Alternativa | Calendarios del proveedor de datos: dependen del proveedor y su licencia; útiles como validación cruzada |

## 7. Normalización — **Modificar**

| | |
|---|---|
| Problema | `candles` mezcla el dato recibido con el dato procesado (`processing_version` en la misma fila). No se puede auditar qué envió el proveedor ni reprocesar |
| Nueva regla | Dos capas. **Cruda** (`raw_candles`): exactamente lo recibido, con hash del contenido, solo inserción. **Normalizada** (`candles`): unidades, moneda, zona horaria y sesión resueltas; enlaza con la fila cruda. Ajustes por acciones corporativas y series continuas se calculan como **derivados versionados** sobre la capa normalizada, nunca sobrescribiéndola |
| Retención | La capa cruda respeta `max_storage_days` de la licencia igual que la normalizada |
| Impacto | ~1,6–2× almacenamiento de velas (ECONOMIC_REVIEW §5: céntimos al mes con los volúmenes previstos) |
| Riesgo | Más tablas que mantener |
| Alternativa | Guardar el JSON crudo en un archivo externo: rechazada (otra infraestructura) |

## 8. Persistencia histórica — **Modificar**

| | |
|---|---|
| Problema | NF-04 (reproducibilidad) es imposible si las velas se actualizan en sitio (INC-02) |
| Nueva regla | **Bitemporal**: cada fila normalizada tiene `recorded_at` y `superseded_at` (nulo si vigente). Una corrección inserta una fila nueva y cierra la anterior. Cada `scan_run` guarda `data_watermark = max(recorded_at)` leído; reproducir = leer filas con `recorded_at ≤ watermark` y (`superseded_at` nulo o > watermark) |
| Índices | Índice parcial sobre filas vigentes (`WHERE superseded_at IS NULL`) para las lecturas normales |
| Particionado | No en I-1. Particionar por rango de `bar_start` cuando `candles` supere ~10 M filas o las consultas p95 > 300 ms |
| Investigación | Exportación a Parquet fuera de producción (sin cambios) |
| Impacto | Pocas correcciones esperadas → sobrecoste bajo |
| Riesgo | Consultas más complejas; se encapsulan en funciones de acceso con pruebas |
| Alternativa | Instantáneas completas por escaneo: rechazada (duplica todo) |

## 9. Workers — **Modificar**

| | |
|---|---|
| Propuesta original | Worker separado solo si CPU/memoria lo exigen; planificador en hilos como la 2.1 |
| Cambios | (a) Las tareas se registran en una tabla `mr.jobs` y se toman con `SELECT … FOR UPDATE SKIP LOCKED`: idempotentes, reanudables, visibles. (b) La planificación (crear tareas según calendario) la hace un solo líder, con el patrón de candado de la PR #12. (c) El servicio worker separado se crea **al activar el primer proveedor con clave**, por aislamiento de secretos (CON-05), aunque la carga no lo exija |
| I-1 | Sin worker ni planificador: solo biblioteca y línea de comandos |
| Impacto | +US$7/mes de Render al llegar a ese punto (SUPUESTO, plan starter) |
| Riesgo | Contención en `mr.jobs` con muchos workers: irrelevante con 1–2 |
| Alternativa | Redis/RQ o Celery: rechazada hasta que `mr.jobs` mida > 20 ms p95 por toma de tarea |

## 10. Escalabilidad — **Mantener criterios, corregir cifras**

| Cifra original | Corrección | Fuente |
|---|---|---|
| 120 B por fila de vela | ≈ 250 B con índice (FOR-01) | Cálculo en SPECIFICATION_GAP_ANALYSIS |
| ~1,1 GB de velas diarias para 3.600 instrumentos y 10 años | ≈ 9,46 M filas × 250 B ≈ **2,4 GB** normalizadas; con capa cruda ≈ 4–5 GB | Cálculo |
| — | El cuello de botella real son los **límites de llamadas** de los proveedores, no la base: 3.000 acciones × 1 petición diaria = 3.000 llamadas, salvo endpoints por lotes | Por medir con el proveedor elegido |

## 11. Observabilidad — **Modificar**

| | |
|---|---|
| Problema | Se listan métricas pero no objetivos ni dónde se guardan. Render solo ofrece registros y métricas básicas |
| Nueva regla | SLO iniciales: (1) escaneo completado por mercado habilitado dentro de 2 ventanas; (2) frescura de datos según AMB-03; (3) disponibilidad web 99 % medida por **sondeo externo** (DEP-04). Eventos operativos en `mr.ops_events` (tabla pequeña, retención 90 días), registros JSON en stdout |
| I-1 | Solo el formato de evento y la función que lo escribe, probados localmente |
| Alternativa | Prometheus/Grafana: rechazada por costo y operación en esta etapa |

## 12. Redis, colas, microservicios — **Rechazar (por ahora)**

Se mantiene D-005. Criterios de entrada numéricos en `TARGET_ARCHITECTURE` §9, con la corrección de §9 de este documento.

---

## Riesgos residuales de arquitectura

| Riesgo | Nivel | Mitigación |
|---|---|---|
| Código portado de `radar/quant` diverge del original | Medio | Pruebas de equivalencia numérica en I-2 |
| Fuente de calendarios inexacta | Medio | DQ-SES y comparación con calendario oficial |
| Bitemporalidad mal implementada | Medio | Pruebas de reproducción en I-1 |
| Base separada aumenta costo y operación | Bajo | Escala a cero; se reevalúa en Fase 3 |
