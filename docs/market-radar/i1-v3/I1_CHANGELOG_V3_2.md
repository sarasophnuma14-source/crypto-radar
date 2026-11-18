# I-1 v3.2 · Registro de cambios, decisiones, plan y auditoría independiente

Fecha: 18-nov-2026. Rama documental `claude/project-thread-dclqgc` (PR #16 en borrador). Revisión **solo documental**.

No se escribió código y no se crearon migraciones. No se ejecutaron consultas SQL ni pruebas, y no se crearon prototipos. No se inició M1. No se usaron credenciales ni se conectó Neon, Render, Telegram ni ningún proveedor. No se fusionó ni se desplegó nada.

Documentos de v3.2:
- `I1_LEDGER_REDESIGN_V3_2.md` (en este documento, «LEDGER»);
- `I1_TEST_STRATEGY_V3_2.md` («TS»);
- `I1_ACCEPTANCE_V3_2.md` («ACC»);
- este registro.

Por instrucción del propietario solo se crean estos cuatro archivos. Por eso la actualización del plan de implementación (§8) y las decisiones propuestas (§5) viven en este registro y no en un `PLAN` o una `MATRIX` v3.2.

## 1. Archivos

| Archivo | Acción |
|---|---|
| `docs/market-radar/i1-v3/I1_LEDGER_REDESIGN_V3_2.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_TEST_STRATEGY_V3_2.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_ACCEPTANCE_V3_2.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_CHANGELOG_V3_2.md` | Nuevo (este) |
| Cualquier otro archivo | **Sin cambios.** Los documentos v3 y v3.1 se conservan como historial y v3.2 los complementa. Comprobación antes del commit: `git status` muestra solo estos cuatro archivos nuevos |

**Documentos revisados.** Se leyeron íntegros estos doce:
- `I1_CRITICAL_REVIEW`, `I1_LEDGER_REDESIGN`, `I1_TEMPORAL_MODEL`, `I1_SECURITY_THREAT_MODEL`, `I1_TEST_STRATEGY_V3` e `I1_IMPLEMENTATION_PLAN_V3`;
- `I1_DECISION_MATRIX_V3_1`, `I1_LEDGER_REDESIGN_V3_1`, `I1_TEST_STRATEGY_V3_1`, `I1_ACCEPTANCE_V3_1`, `I1_IMPLEMENTATION_PLAN_V3_1` e `I1_CHANGELOG_V3_1`.

También se leyeron `I1_ACCEPTANCE_V3` e `I1_DATA_CONTRACT_REVIEW`, necesarios para `c2`.

Se consultaron las secciones pertinentes de:
- `DECISION_LOG.md` (D-001…D-027);
- `ARCHITECTURE_REVIEW.md`;
- `SPECIFICATION_GAP_ANALYSIS.md`;
- `ASSET_DATA_MODEL.md`;
- `SECURITY_AND_PRIVACY_REQUIREMENTS.md` (S-13, S-60, S-64);
- `DATA_QUALITY_TEST_PLAN.md` (DQ-DUP);
- `DATA_LICENSE_MATRIX.md`.

Todos existen. Ninguno faltó.

## 2. Hallazgos MR-01…MR-05 y su resolución

| Hallazgo original | Documento v3.1 afectado | Corrección v3.2 | Pruebas | Criterio | Estado | Riesgo residual |
|---|---|---|---|---|---|---|
| **MR-01** UUIDv5 y colisiones de identidad | `I1_LEDGER_REDESIGN_V3_1.md` §2 («Identificador determinista»); `I1_DECISION_MATRIX_V3_1.md` DV3-13 («`batch_id` determinista (UUIDv5 del digest)»); `I1_TEST_STRATEGY_V3_1.md` TS-IDEM-15 | LEDGER §2. Propiedades reales de UUIDv5 (SHA-1, 122 bits, colisión independiente de SHA-256; ninguna función hash da unicidad). Comparación de cinco alternativas por criterios. Recomendación: identidad = (`producer_id`, `idem_key`) única, `batch_id` generado por la base y comparación **completa** de los dos digests. Un conflicto devuelve `conflict` y no toca el lote. Se descubrió V3-30 (P0) | TS-BATCH-ID-01…10; TS-IDEM-15 redefinida | A16 | Corregido documentalmente | RR-01, RR-02 |
| **MR-02** Identidad semántica y digest canónico | `I1_LEDGER_REDESIGN_V3_1.md` §2 (`declared_digest` sin definir); v3 `I1_DATA_CONTRACT_REVIEW.md` §5 (`c2`) | LEDGER §3. Contrato MRC-1: codificación binaria inyectiva con separación de dominio; clasificación de campos en semánticos, de procedencia y operativos; `semantic_digest` y `batch_digest` en dos niveles; orden por bytes; duplicados rechazados; decimales, nulos e instantes definidos; política de versiones; `c3` y `entry_hash` v2 | TS-BATCH-DIGEST-01…18 | A17 | Corregido documentalmente | RR-02, RR-03 |
| **MR-03** Publicación, limpieza y consulta concurrentes | `I1_LEDGER_REDESIGN_V3_1.md` §6–§7 (limpieza a las 24 h sin protocolo); v3 §6 | LEDGER §4. Estado `expired` (lápida) con reapertura; `expire_batches` con `FOR UPDATE SKIP LOCKED`, revalidación, sin `ledger_head` y con un evento por lote. Tabla de bloqueos por función, estados observables, argumento contra interbloqueos, 13 intercalados e invariantes C1–C4. `batch_status` es orientativo y cualquier acción sobre una respuesta caducada es segura | TS-CLEANUP-01…13 | A18, A13 | Corregido documentalmente | RR-04, RR-05, RR-10, RR-11 |
| **MR-04** Identidad del rol, servicio y productor | `I1_LEDGER_REDESIGN_V3_1.md` §2 (`opened_by text`), §6 y §9 (filtro por `session_user`); v3 §2 (`mr_writer` con LOGIN) | LEDGER §5. Tres niveles: el rol lo autentica PostgreSQL; el proceso no es fiable; el productor lo deriva la base. `mr_writer` pasa a grupo; un rol con LOGIN por servicio (`INHERIT TRUE, SET FALSE`); vínculos rol → productor administrados por `mr_owner`; auditoría por OID y nombre, con productor y PID; `application_name` solo como dato no fiable | TS-IDENTITY-01…10 | A19 | Corregido documentalmente | RR-01, RR-12 |
| **MR-05** Seguridad de GitHub Actions y cadena de suministro | `I1_DECISION_MATRIX_V3_1.md` §3 (DV3-14); `I1_TEST_STRATEGY_V3_1.md` §4 (TS-CI) | LEDGER §6. Se mantienen todas las restricciones de DV3-14/15 y se analizan los 12 puntos pedidos. Controles separados en implementables en el flujo, configuración del propietario (R-01…R-08) y supuestos pendientes. Las pruebas no corren como root; bloqueo de dependencias con todas las transitivas; sin caché; fallo explícito sin aislamiento | TS-CI-SEC-01…14 (sustituye TS-CI-01…08) | A20, A20b, A21 | Corregido documentalmente | RR-07, RR-08 |

## 3. Hallazgos nuevos (revisión crítica de v3.1)

| Id | Sev. | Documento / sección | Evidencia | Problema | Impacto | Corrección v3.2 | Prueba | Estado |
|---|---|---|---|---|---|---|---|---|
| V3-30 | **P0** | `I1_LEDGER_REDESIGN_V3_1.md` §2 | Análisis A → B → A (LEDGER §1); contraste con v3 §6. No ejecutado | Con identidad por contenido, una operación nueva con contenido ya publicado se trata como reintento | Correcciones y reversiones legítimas no se publican nunca: pérdida silenciosa de información | Identidad por operación (LEDGER §2) | TS-BATCH-ID-04 + control negativo | Corregido documentalmente |
| V3-31 | P1 | v3 `I1_DATA_CONTRACT_REVIEW.md` §5 (`c2`) | Texto: separador `\|` y «nulos como cadena vacía» | Codificación ambigua: `adjustment_version` nulo y `''` dan el mismo hash | Una corrección del proveedor puede no generar revisión | `c3` sobre MRC-1 (LEDGER §3.8) | TS-BATCH-DIGEST-11, 16 | Corregido documentalmente |
| V3-32 | P2 | `I1_LEDGER_REDESIGN_V3_1.md` §4 paso 3; `I1_TEST_STRATEGY_V3_1.md` TS-ADV-15/16 | DOC: las inserciones no confirmadas no son visibles para otras transacciones | Resultados esperados basados en un estado que el MVCC no deja observar | Pruebas que no podrían pasar tal como estaban escritas | Errores deterministas `MRB02` / `MRB07` (LEDGER §4.3) | TS-ADV-15/16 (redefinidas) | Corregido documentalmente |
| V3-33 | P2 | `I1_LEDGER_REDESIGN_V3_1.md` §3 | DOC: una excepción deshace la transacción, incluido el evento insertado | «Error `BatchConflict` + evento operativo» es contradictorio | Conflictos sin rastro de auditoría | `conflict` como resultado y evento conservado (LEDGER §2.6) | TS-BATCH-ID-02 | Corregido documentalmente |
| V3-34 | P2 | `I1_LEDGER_REDESIGN_V3_1.md` §2 (disparador diferido) | INF: la fila `NEW` de un disparador diferido es la imagen del momento de la inserción | Si el disparador usa `NEW.status`, verá `open` aunque el lote se haya sellado | Ningún lote se podría confirmar | Volver a leer el estado por `batch_id` (LEDGER §4.1) | TS-IDEM-14 y todas las publicaciones | Corregido documentalmente |
| V3-35 | P1 | `I1_TEST_STRATEGY_V3_1.md` §4; `I1_DECISION_MATRIX_V3_1.md` §3 | DOC-GH: `pull_request` usa el flujo de la PR | El análisis estático corre desde la propia PR, que puede cambiarlo | Falsa sensación de control frente a PRs externas | Reclasificado como regresión; control real en R-01…R-08 (LEDGER §6.1) | TS-CI-SEC (limitación declarada) | Corregido documentalmente |
| V3-36 | P1 | `I1_DECISION_MATRIX_V3_1.md` §3 (`sudo unshare --net`) | DOC: PostgreSQL no se ejecuta como root; `peer` usa el usuario del sistema | Las pruebas correrían como root | Arranque imposible o identidad falsa en las pruebas de privilegios | Bajar privilegios dentro del espacio aislado; comprobar `id -u ≠ 0` | TS-CI-SEC-07 | Corregido documentalmente |
| V3-37 | P2 | `I1_DECISION_MATRIX_V3_1.md` §3 («Solo `psycopg[binary]==3.3.9` … con hashes») | DOC de pip: `--require-hashes` exige hash para todas las dependencias | Faltan las dependencias transitivas | La instalación fallaría o habría que relajar la verificación | Bloqueo completo en `tests/market_radar/ci/` | TS-CI-SEC-10 | Corregido documentalmente |
| V3-38 | P2 | Ídem («acciones fijadas por SHA») | INF: `setup-python` descarga el intérprete en tiempo de ejecución | El SHA no cubre esa descarga | Superficie de cadena de suministro no declarada | Declarada como residual (RR-07); alternativa con Python del sistema | TS-CI-SEC-05 | Corregido documentalmente (riesgo aceptado, pendiente del propietario) |
| V3-39 | P2 | v3 `I1_LEDGER_REDESIGN.md` §3 (`payload_ref`) + v3.1 §2 | Análisis | Si el lote referencia el cuerpo por un `payload_id` aleatorio, dos reintentos tienen digests distintos | Reintentos tratados como conflicto | Referencia por `body_sha256` (LEDGER §3.2) | TS-BATCH-DIGEST-15 | Corregido documentalmente |
| V3-40 | P2 | v3 `I1_LEDGER_REDESIGN.md` §7 (`entry_hash`) | Texto: «‖» sin codificación definida | Cadena de hashes ambigua; no cubre la auditoría del productor | Alterar la auditoría no rompería la cadena | `entry_hash` v2 sobre MRC-1 con productor y rol (LEDGER §3.8) | TS-IDENTITY-08 | Corregido documentalmente |
| V3-41 | P3 | LEDGER §4 (nuevo) | Diseño | Las lápidas `expired` crecen sin límite | Tabla `batches` grande con el tiempo | Aceptado en I-1; medir en I-2 (RR-10) | — | Abierto (aceptado) |
| V3-42 | P2 | `I1_LEDGER_REDESIGN_V3_1.md` §2 (`opened_by text`) | DOC: los roles se pueden renombrar | Auditoría por nombre, mutable | Atribución ambigua tras un cambio de nombre | OID + nombre (LEDGER §5.6) | TS-IDENTITY-08 | Corregido documentalmente |
| V3-43 | P2 | v3 `I1_LEDGER_REDESIGN.md` §2 (`mr_writer` con LOGIN) | Texto | Todos los procesos comparten una credencial | Indistinguibles para autorizar y auditar | Un rol por servicio (LEDGER §5.2) | TS-IDENTITY-05, 09 | Corregido documentalmente |
| V3-44 | P2 | `SECURITY_AND_PRIVACY_REQUIREMENTS.md` S-13, S-64 frente a DV3-14 | Texto | Escaneo de secretos y `pip-audit` en CI necesitan red o dependencias nuevas | Requisitos de seguridad sin cubrir ni aplazar | S-13 vía R-06 y A9; S-64 aplazado a I-2 (LEDGER §6.4) | — | Corregido documentalmente; la decisión es del propietario |
| V3-45 | P2 | `I1_LEDGER_REDESIGN_V3_1.md` §10 | INF | Que `lock_timeout` acote la espera de `INSERT … ON CONFLICT` sobre una transacción en curso no está documentado de forma explícita | Esperas posiblemente no acotadas | Comprobación obligatoria en M1; si falla, parada (§8.5) | TS-IDEM-16, TS-CLEANUP-13 | Abierto hasta M1 |
| V3-46 | P3 | `I1_TEST_STRATEGY_V3_1.md` TS-ADV-19/20 | Texto «error o nada» | Resultado no verificable | Prueba ambigua | `MRB02` / vacío (TS §2) | TS-ADV-19/20 | Corregido documentalmente |
| V3-47 | P1 | v3 `I1_SECURITY_THREAT_MODEL.md` T-13; v3 `I1_LEDGER_REDESIGN.md` §6 | DOC: `idle_in_transaction_session_timeout`, `lock_timeout` y `statement_timeout` son de contexto `user` | Un escritor puede desactivar los tiempos límite y retener `ledger_head` | Denegación de servicio de las publicaciones; T-13 presentaba como protección algo que no lo es | Cotas en la cláusula `SET` de las funciones; vigilante opcional DV3-20; riesgo RR-05 declarado | TS-CLEANUP-13 | Corregido documentalmente (parcial: disponibilidad) |

## 4. Lo que se conserva

- Los 25 hallazgos de v3 (V3-01…V3-25) y los 4 de v3.1 (V3-26…V3-29), con su severidad y estado. Ninguno se cierra, se rebaja ni pasa a «Implementado» o «Verificado».
- DV3-01…DV3-15 en estado **Propuesta**. La matriz v3 está aceptada solo como base de revisión.
- D-001…D-027 de `DECISION_LOG.md` sin cambios.
- DP-01…DP-04 **pendientes**. Ninguna figura como aprobada.
- A1–A15 y B1–B6.
- Restricciones: no tocar `radar/`, la 2.1, `main.py`, `web/`, `render.yaml`, `requirements.txt`, precios, pagos, secretos, Neon, Render, Telegram, proveedores, holdout ni paper trading; no fusionar ni desplegar; nada irreversible.
- NO EDGE.

## 5. Decisiones técnicas propuestas en v3.2 (todas en estado Propuesta)

| Id | Decisión | Relación |
|---|---|---|
| DV3-16 | Identidad del lote = (`producer_id`, `idem_key`) única + `batch_id` generado por la base + comparación completa de `batch_digest` y `semantic_digest`. Alternativa admisible si el propietario prefiere UUID: E (UUIDv5 del descriptor de la operación) | **Modifica DV3-13** en su parte «`batch_id` determinista (UUIDv5 del digest)». El resto de DV3-13 se mantiene |
| DV3-17 | Contrato MRC-1, digests en dos niveles, `c3` sustituye a `c2`, `entry_hash` v2 | Nueva; modifica `I1_DATA_CONTRACT_REVIEW.md` §5 (propuesta) |
| DV3-18 | Estado `expired` con reapertura y protocolo de limpieza de LEDGER §4.4 | Precisa DV3-13 |
| DV3-19 | Tres niveles de identidad; `mr_writer` como grupo; rol con LOGIN por servicio; `mr_maintainer`; vínculos rol → productor; auditoría por OID | Modifica DV3-02 (propuesta) |
| DV3-20 | Vigilante `mr_watchdog` con `pg_signal_backend`, solo en instancia `test` en I-1 (**opcional**) | Nueva; mitiga V3-47 |
| DV3-21 | Ampliación de DV3-14: pruebas sin root, bloqueo completo con hashes, sin caché, lista blanca de SHA con etiqueta verificada, fallo explícito sin aislamiento, artefactos revisados; S-13 vía R-06 y S-64 aplazado | Condicionada a DP-03 |

**Contradicción que debe resolver el propietario:** DV3-13 (v3.1) y DV3-16 (v3.2) son ambas propuestas, e incompatibles en la forma de calcular `batch_id`. La recomendación técnica es aprobar DV3-13 **modificada por DV3-16**.

## 6. Auditoría independiente (segunda revisión de v3.2)

Desde el rol de auditor independiente se intentó **refutar** cada propuesta de v3.2. Sesgo declarado: el mismo equipo diseñó v3, v3.1 y v3.2. No se ejecutó nada, así que ninguna refutación ni confirmación es experimental.

| # | Intento de refutación | Resultado | Clasificación |
|---|---|---|---|
| AU-01 | Carrera entre reapertura, limpieza y publicación | Las tres serializan en el bloqueo de la fila del lote y revalidan después; la limpieza no espera. Sin contraejemplo | — |
| AU-02 | Interbloqueos | Solo posible si una transacción abre varios lotes nuevos en orden distinto. PostgreSQL lo detecta y aborta, lo que es seguro pero no idempotente | P3 (RR-04) |
| AU-03 | Reintentos no idempotentes | Si el productor reutiliza `idem_key` para otra operación con contenido idéntico, la base lo trata como reintento. No es detectable por la base | P2 (RR-01) |
| AU-04 | Reintento después del TTL sin el contenido | Es una operación nueva: crea una versión, sin filas nuevas si nada cambió. Documentado | P3 (RR-11) |
| AU-05 | Suplantación de identidad | `application_name`: sin efecto en la autorización. `SET ROLE`: bloqueado por `SET FALSE`. `SET SESSION AUTHORIZATION`: solo superusuario (fuera de alcance). **Hueco nuevo:** la cadena de identidad depende de `pg_hba.conf` y `pg_ident.conf`. Una regla `peer` con un mapa demasiado amplio permitiría a cualquier usuario del sistema entrar como cualquier rol, y ninguna prueba de v3 ni de v3.1 inventaría esos archivos | **P2 → V3-49.** Corrección: TS-PRIV-01 añade el inventario de `pg_hba_file_rules` y `pg_ident_file_mappings` (vistas de PG16, DOC) contra una lista blanca; sin cambio en el número de casos |
| AU-06 | Digests ambiguos | Unicode: se valida y no se normaliza, así que una diferencia de versión produce un rechazo, no dos digests distintos. Decimales e instantes: los cubren TS-BATCH-DIGEST-10/12. Sin contraejemplo | — |
| AU-07 | Supuestos incorrectos de PostgreSQL: tamaño | Calcular el digest sobre la concatenación de todo el lote choca con el tope de 1 GB de `bytea` y con la memoria | **P1 → V3-48.** Corregido en LEDGER §3.5 (dos niveles, 32 bytes por registro) |
| AU-08 | Supuesto: `lock_timeout` sobre las esperas de transacción | No documentado de forma explícita | P2 (V3-45), abierto hasta M1 |
| AU-09 | Supuesto: la cláusula `SET statement_timeout` de una función acota esa misma llamada | INF: `statement_timeout` se arma al empezar la sentencia de nivel superior, de modo que cambiarlo dentro de la función probablemente **no** afecta a la sentencia en curso. `lock_timeout` sí se lee al empezar cada espera de bloqueo. LEDGER §4.2 y §4.7 lo daban por hecho | **P2 → V3-50.** Corrección: la cota fiable dentro de las funciones es `lock_timeout`; `statement_timeout` en la función queda como INF que M1 debe comprobar, y no se cuenta como garantía. Se recoge en la §4.2 corregida de LEDGER |
| AU-10 | Errores de privilegios | `mr_maintainer` solo ejecuta una función. El vigilante (DV3-20) con `pg_signal_backend` puede terminar sesiones de cualquier rol no superusuario del clúster | P2 (RR-06): solo en `test`, y clúster separado en I-2 |
| AU-11 | Riesgos de CI | Las pruebas son autorreferentes (V3-35). Una PR externa puede abusar de recursos y sus registros son públicos. La descarga de `setup-python` no está fijada. Un SHA «impostor» de un fork | P1 (V3-35) y P2 (RR-07, RR-08). El impostor se mitiga verificando cada SHA contra la etiqueta oficial al implementar (TS-CI-SEC-05) |
| AU-12 | Contradicciones entre documentos | DV3-13 frente a DV3-16 (§5). TS-ADV-15/16/19/20 y TS-IDEM-10/15/16 redefinidas (TS §2). `write_log.batch_id` pasa de `uuid` a `bigint` (LEDGER §2.4). Ninguna otra encontrada | Resuelto documentalmente; la elección es del propietario |
| AU-13 | Criterios imposibles de verificar | A20b (configuración del repositorio) y RR-01 (productores reales) no se pueden verificar con código: se declaran como declaración del propietario y como limitación (ACC §5). TS-ADV-20 era ambiguo (V3-46) | Resuelto documentalmente |
| AU-14 | Nuevo P0 en v3.2 | **No se encontró ningún P0 nuevo sin solución documentada** en esta segunda revisión. Esto **no demuestra que no exista**: la revisión es del mismo equipo y no se apoya en ejecución | — |

Hallazgos de la auditoría que se suman a §3:

| Id | Sev. | Problema | Corrección | Prueba | Estado |
|---|---|---|---|---|---|
| V3-48 | P1 | El digest sobre la concatenación del lote no cabe en `bytea` para lotes grandes | Dos niveles (LEDGER §3.5) | TS-BATCH-DIGEST-17 (lotes de hasta 500 registros) + prueba de volumen en T12 | Corregido documentalmente |
| V3-49 | P2 | `pg_hba.conf` / `pg_ident.conf` fuera del inventario | TS-PRIV-01 ampliado | TS-PRIV-01 | Corregido documentalmente |
| V3-50 | P2 | `statement_timeout` en la cláusula `SET` de la función, probablemente sin efecto en la llamada en curso | Solo `lock_timeout` cuenta como cota | TS-IDEM-16, TS-CLEANUP-13 | Corregido documentalmente; pendiente de verificación en M1 |

Recuento de hallazgos nuevos en v3.2: **21** (V3-30…V3-50). Por severidad: 1 P0 (V3-30), 5 P1, 13 P2 y 2 P3. Total acumulado de v3, v3.1 y v3.2: 50.

## 7. Riesgos residuales

| Id | Riesgo | Sev. | Por qué queda |
|---|---|---|---|
| RR-01 | Un productor reutiliza `idem_key` para otra operación con contenido idéntico | P2 | La base no puede distinguirlo de un reintento |
| RR-02 | Colisión de SHA-256 | P3 | Teórica; ninguna función hash da unicidad |
| RR-03 | Los digests de lote no son comparables entre instancias | P3 | `instrument_id` es local; para comparar entre instancias se usa `c3` |
| RR-04 | Interbloqueo al abrir varios lotes desordenados en una transacción | P3 | Se detecta y aborta: seguro, no idempotente |
| RR-05 | Un escritor retiene `ledger_head` con los tiempos límite desactivados | P2 | Sin DV3-20, no hay cota desde la base. Es un riesgo de disponibilidad, no de integridad |
| RR-06 | Poder del vigilante en un clúster compartido | P2 | Si se aprueba DV3-20 |
| RR-07 | La descarga del intérprete por `setup-python` y el software de la imagen del ejecutor | P2 | Fuera del alcance de la fijación por SHA |
| RR-08 | Una PR externa ejecuta código arbitrario (abuso de recursos, registros públicos) | P2 | Inherente a `pull_request`; se mitiga con R-01 |
| RR-09 | Dueño, migrador o superusuario alteran la historia | P2 | Solo detección por la cadena (v3) |
| RR-10 | Crecimiento de las lápidas | P3 | V3-41 |
| RR-11 | Un reintento posterior al TTL sin el contenido crea una versión nueva | P3 | Comportamiento documentado |
| RR-12 | Las credenciales compartidas no se distinguen | P3 | Limitación de PostgreSQL; regla de un rol por servicio |

## 8. Plan de implementación (sustituye como referencia a `I1_IMPLEMENTATION_PLAN_V3_1.md` §3; ese archivo no se modifica)

Días de trabajo con revisión. SUPUESTO: no hay velocidad histórica comparable. **No autorizado. No existe código. M1 no ha empezado.**

### 8.1 Estimación

| Tarea | Contenido v3.2 | Depende de | v3.1 | Adicional | v3.2 | Justificación del adicional |
|---|---|---|---|---|---|---|
| T01 | + Codificador MRC-1 en Python, digests, `idem_key`, vectores relacionales | — | 1,5 | +0,5 | 2,0 | Codificación con decimales, instantes y validaciones de texto |
| T02 | Sin cambios | T01 | 1,5 | 0 | 1,5 | — |
| T03 | Sin cambios | T02 | 2,5 | 0 | 2,5 | — |
| T04 | + Roles de grupo y por servicio con opciones de PG16, `mr_maintainer`, vínculos, inventario de `pg_hba`/`pg_ident` (V3-49) | T03 | 1,5 | +0,5 | 2,0 | Más roles y lista blanca ampliada |
| T05 | + Codificador MRC-1 en PostgreSQL y verificación al sellar en dos niveles; identidad del productor y auditoría; estado `expired`, reapertura y `expire_batches`; catálogo de errores | T04 | 4,0 | +1,5 | 5,5 | Segunda implementación independiente del digest (0,75), protocolo de limpieza (0,5), identidad (0,25) |
| T06 | + TS-BATCH-ID (10), TS-BATCH-DIGEST (18, con 10 000 lotes cruzados), TS-CLEANUP (13, con intercalados forzados), TS-IDENTITY (10, con varios roles), controles negativos | T05 | 4,0 | +2,5 | 6,5 | 51 casos nuevos, de los que unos 25 son concurrentes y necesitan puntos de sincronización |
| T15 | + Bajada de privilegios, bloqueo con dependencias transitivas, verificación de SHA, alternativa con contenedor, TS-CI-SEC (14) (solo si DP-03 = Sí) | T02, T03 | 1,0 | +1,0 | 2,0 | 6 casos más y dos problemas nuevos (V3-36, V3-37) |
| **M1** | Evidencia de T01–T06 (+ T15) revisada por el propietario | T06 (+ T15) | 15,0 (16,0 con CI) | +5,0 (+6,0 con CI) | **20,0** (22,0 con CI) | |
| T07–T11, T13, T14 | Sin cambios respecto a v3 | M1 | 14,5 | 0 | 14,5 | — |
| T12 | + Velas con `c3` (reutiliza MRC-1) y prueba de volumen del digest (V3-48) | T09, T10, T11 | 3,0 | +0,5 | 3,5 | Cambio de codificación y medición |
| **I-1 completo** | | | ≈ 32,5 (≈ 33,5 con CI) | +5,5 (+6,5 con CI) | **≈ 38** (≈ 40 con CI) | Rango 33–48 (SUP: −15 % / +25 %) |

No se ha reducido el tiempo de pruebas para conservar la estimación anterior. El aumento viene sobre todo de T06 (pruebas) y T05 (la segunda implementación del digest).

### 8.2 Dependencias

| Dependencia | Estado |
|---|---|
| PostgreSQL 16 con `sha256`, `trim_scale`, `extract` en `numeric`, opciones `INHERIT`/`SET` de `GRANT`, vistas `pg_hba_file_rules` y `pg_ident_file_mappings` | DOC (manual de PG16); se comprueba en M1 |
| Comportamientos INF de V3-45 y V3-50 | Se verifican en T06; condicionan TS-IDEM-16 y TS-CLEANUP-13 |
| `sudo unshare --net` con bajada de privilegios, Python 3.12 del sistema y PostgreSQL 16 en `ubuntu-24.04` | SUP; se comprueban en T15 |
| Dependencias transitivas de `psycopg[binary]==3.3.9` y sus hashes; SHA de las acciones | **NO VERIFICADOS**; se registran al implementar |
| Configuración R-01…R-08 | Solo el propietario (DP-05) |
| Autorización del propietario | **Pendiente** (DP-01…DP-05) |

### 8.3 Ruta crítica

T01 → T02 → T03 → T04 → T05 → T06 → M1 → T07 → T08 → T11 → T12 → T13 → T14.

T15 va en paralelo a T04–T06. Entra en la ruta crítica si DP-03 = Sí y la comprobación del aislamiento de red falla o se retrasa, porque M1 exige A20.

### 8.4 Riesgos de calendario

| Riesgo | Efecto |
|---|---|
| Divergencias entre Python y PostgreSQL en el digest (decimales, instantes) | +0,5 a 2 días en T05/T06 |
| Pruebas concurrentes inestables o difíciles de forzar | +1 a 3 días en T06 |
| V3-45 o V3-50 resultan falsos | Rediseño de las cotas de espera; parada (§8.5) |
| `unshare` no disponible en el ejecutor | Alternativa con contenedor (+0,5 a 1 día) o decisión del propietario |
| Retirada de versiones de Node en las acciones fijadas | Mantenimiento de los SHA |
| Tiempo de revisión del propietario en M1 | No incluido en los días |

### 8.5 Condiciones que obligan a detenerse

1. Un control negativo **no** falla: la prueba no detecta lo que dice detectar.
2. Python y PostgreSQL dan digests distintos y la causa no se explica en 1 día.
3. V3-45 o V3-50 resultan falsos y no hay una cota de espera documentada alternativa.
4. Falla A → B → A o alguna invariante C1–C4 o I1–I4.
5. Aparece un P0 nuevo.
6. Una prueba exigiría modificar un archivo existente, acceder a la red o tocar la 2.1, Neon, Render, Telegram, proveedores, pagos, holdout o paper trading.
7. Ningún método de aislamiento de red funciona en CI: la parte de CI se detiene y decide el propietario.

## 9. Decisiones del propietario pendientes

| Id | Pregunta | Recomendación técnica | Estado |
|---|---|---|---|
| DP-01 | ¿Se autoriza escribir código? | Solo M1 | **Pendiente** |
| DP-02 | ¿Se aprueban DV3-01…DV3-21 individualmente? (DV3-13 modificada por DV3-16) | Todas; DV3-20 opcional | **Pendiente** |
| DP-03 | ¿CI en GitHub Actions solo para Market Radar? | Sí, con DV3-14, DV3-15 y DV3-21, y solo tras aplicar DP-05 | **Pendiente** |
| DP-04 | ¿Desarrollo antes del cierre de la Fase 0? | Sí, solo como desarrollo aislado | **Pendiente** |
| DP-05 (nueva) | Si DP-03 = Sí, ¿aplica el propietario la configuración R-01…R-08 antes de activar el flujo? | Sí | **Pendiente** |

Esta tarea no aprueba ninguna decisión.

## 10. Efecto en las cifras

| | v3 | v3.1 | v3.2 |
|---|---|---|---|
| Hallazgos acumulados | 25 | 29 | 50 |
| P0 acumulados (todos corregidos solo documentalmente) | 6 | 7 | 8 |
| Pruebas | ≈ 179 | ≈ 209 (≈ 201 sin CI) | **≈ 266** (≈ 252 sin CI) |
| M1 | ≈ 12,5 días | ≈ 15 (16 con CI) | **≈ 20** (22 con CI) |
| I-1 completo | ≈ 30 | ≈ 32,5 (33,5 con CI) | **≈ 38** (40 con CI) |
| Veredicto | NO READY | NO READY | **NO READY** |
