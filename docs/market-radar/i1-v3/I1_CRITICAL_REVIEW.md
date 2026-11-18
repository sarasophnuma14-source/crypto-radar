# I-1 v3 · Auditoría crítica del diseño v2

Fecha: 18-nov-2026. Objeto: `docs/market-radar/PHASE_1_IMPLEMENTATION_PLAN.md` v2 (commit `caea0d8`) y los documentos que lo sostienen.
Rama: `claude/project-thread-dclqgc` (documental, sin código; PR #16 en borrador). Esta revisión **no modifica ningún archivo existente**; solo añade la carpeta `docs/market-radar/i1-v3/`.

## 0. Cómo leer este documento

**Tipos de evidencia** (se indica en cada hallazgo):

| Etiqueta | Significado |
|---|---|
| **DOC** | Garantía escrita en el manual de PostgreSQL o en una especificación pública |
| **EXP** | Evidencia experimental: consultas SQL desechables ejecutadas el 18-nov en un PostgreSQL 16.15 local temporal (borrado al terminar), **no** código de I-1 ni prueba de integración |
| **INF** | Inferencia sobre la implementación (código fuente o comportamiento conocido), no garantizada |
| **SUP** | Supuesto no verificado |

**Estados:** Abierto · Corregido documentalmente · Implementado · Verificado. En esta revisión **ningún hallazgo pasa de «Corregido documentalmente»**: no existe código.

**Severidad:** P0 bloqueante (integridad, seguridad o reproducibilidad) · P1 alto · P2 medio · P3 bajo.

## 1. Inventario verificado

| Documento | Existe | Último commit |
|---|---|---|
| PHASE_1_IMPLEMENTATION_PLAN.md | Sí (564 líneas, v2) | `caea0d8` |
| DECISION_LOG.md | Sí | `caea0d8` |
| SPECIFICATION_GAP_ANALYSIS.md | Sí | `caea0d8` |
| ARCHITECTURE_REVIEW.md | Sí | `caea0d8` |
| DATA_QUALITY_TEST_PLAN.md | Sí | `63d2e2c` |
| QUANT_VALIDATION_REVIEW.md | Sí | `63d2e2c` |
| ECONOMIC_REVIEW.md | Sí | `caea0d8` |
| SECURITY_AND_PRIVACY_REQUIREMENTS.md | Sí | `e5a488f` |
| ASSET_DATA_MODEL.md | Sí | `e5a488f` |
| PRODUCT_REQUIREMENTS.md | Sí | `e5a488f` |
| TARGET_ARCHITECTURE.md | Sí | `e5a488f` |
| MULTI_ASSET_ROADMAP.md | Sí | `e5a488f` |

Estado del repositorio: rama al día con `origin`, árbol limpio antes de esta revisión. Código de Market Radar: **ninguno** (`market_radar/` no existe).

## 2. Resumen

| Severidad | Cantidad | Ids |
|---|---|---|
| P0 | 6 | V3-01 … V3-06 |
| P1 | 9 | V3-07 … V3-15 |
| P2 | 7 | V3-16 … V3-22 |
| P3 | 3 | V3-23 … V3-25 |
| **Total** | **25** | |

**Juicio:** el diseño v2 tiene la dirección correcta (aislamiento, bitemporalidad, separación crudo/canónico, licencias en base) pero **su mecanismo de integridad se puede falsificar con permisos que el propio plan da al rol de aplicación**, su garantía de orden se apoya en un detalle no documentado, su reversión puede borrar objetos ajenos, su historia solo cubre velas y fuentes, y su guardia de red se puede saltar. Seis problemas P0. v2 no debe implementarse tal como está.

## 3. Hallazgos P0

### V3-01 · El ledger de v2 se puede falsificar
- **Severidad:** P0
- **Documento/sección:** PHASE_1_IMPLEMENTATION_PLAN v2 §5.3 (`mr.begin_write`, «Disparador … debe ser igual a `current_setting('mr.write_seq')`»).
- **Evidencia (EXP):** réplica mínima de v2 con el rol de aplicación como dueño. Antes del ataque, la lectura as-of W=1 devolvía la vela `{1}`. Ataques ejecutados sin error: (A1) `SELECT set_config('mr.write_seq','1',true)` seguido de `INSERT` con `write_seq = 1`; (A2) `UPDATE … SET superseded_seq = 1` directo; (A3) `ALTER TABLE … DISABLE TRIGGER`. Después, la misma lectura as-of W=1 devolvió `{99}`: la historia publicada cambió.
- **Problema:** `set_config` lo puede llamar cualquier sesión (DOC: los parámetros personalizados con punto son de usuario). El disparador comprueba un valor que el atacante controla. Además, el rol tiene `INSERT/UPDATE` directo y es dueño de las tablas.
- **Impacto:** cualquier código con la conexión de aplicación (o una inyección SQL) reescribe el pasado sin dejar rastro. NF-04 queda sin garantía.
- **Corrección:** `I1_LEDGER_REDESIGN.md`: roles separados; tablas versionadas sin privilegios de escritura para ningún rol con LOGIN; única vía `mr.publish()` `SECURITY DEFINER` con `search_path` fijo; disparadores que validan contra `mr.write_log` por `pg_current_xact_id()` (dato que el escritor no puede crear), no contra una variable de sesión.
- **Prueba:** TS-ADV-01…14 de `I1_TEST_STRATEGY_V3.md`. EXP preliminar: los mismos ataques contra el diseño alternativo fallaron con `permission denied` o con el error del disparador.
- **Estado:** Corregido documentalmente.

### V3-02 · Sin separación de roles: la aplicación es dueña de todo
- **Severidad:** P0
- **Documento/sección:** v2 §5.1 («rol no superusuario dueño de la base»), §6 («las pruebas … con un rol no superusuario con `CREATEDB`»); SECURITY S-60 pide separación, v2 no la aplica en `mr`.
- **Evidencia (EXP):** como dueño, el rol de v2 pudo desactivar el disparador (A3) y, en otra prueba, borrar el esquema entero.
- **Problema:** el dueño de un objeto puede alterarlo, desactivar disparadores y borrarlo (DOC). Un disparador no protege contra su dueño.
- **Impacto:** todos los controles de base de v2 son decorativos frente a la propia aplicación.
- **Corrección:** `mr_owner` (NOLOGIN, dueño), `mr_migrator` (LOGIN, miembro de `mr_owner`, solo para migrar), `mr_writer`, `mr_reader`, `mr_test_fixtures` (solo en bases de prueba). `REVOKE` de `PUBLIC` en base, esquema y funciones; `ALTER DEFAULT PRIVILEGES` para que las funciones nuevas no sean ejecutables por `PUBLIC` (DOC: por defecto lo son). Detalle en `I1_LEDGER_REDESIGN.md` §2.
- **Prueba:** TS-PRIV-01…10 (inventario de privilegios contra una lista blanca).
- **Estado:** Corregido documentalmente.

### V3-03 · La garantía de orden depende de un detalle interno no documentado
- **Severidad:** P0
- **Documento/sección:** v2 §5.3 («se apoya en el orden interno de `CommitTransaction` (no documentado como garantía en el manual)»).
- **Evidencia:** EXP a favor (0/60 relecturas distintas el 18-nov), pero un ensayo no es garantía. El propio v2 lo admite.
- **Problema:** si el lector ve confirmada la secuencia *n* pero no la *n−1*, la reproducción falla en silencio. Además, `nextval` no es transaccional (DOC): un rollback deja un hueco indistinguible de una transacción en curso.
- **Impacto:** reproducibilidad sostenida por una inferencia.
- **Corrección:** contador **sin huecos** en una fila (`mr.ledger_head`) actualizado dentro de la transacción de publicación (DOC: actualización transaccional y espera por bloqueo de fila), y marca de agua **(W, H)** donde H son las secuencias ≤ W no visibles en la instantánea del lector. La lectura excluye H. La corrección deja de depender del orden interno: ese orden solo decide si H está vacío (lo esperado) o no. Ver `I1_LEDGER_REDESIGN.md` §4.
- **Prueba:** TS-CONC-01…08, incluida la verificación de H y del contador sin huecos con terminación forzada de conexiones. EXP preliminar: 200 intentos, 20 conexiones terminadas, rollbacks voluntarios, 160 publicaciones con secuencias 179–338 sin huecos, 60/60 lecturas reproducidas, H siempre vacío.
- **Estado:** Corregido documentalmente.

### V3-04 · La reversión puede borrar objetos que I-1 no creó
- **Severidad:** P0
- **Documento/sección:** v2 §5.1 (`0001_base.down.sql`: `DROP SCHEMA mr CASCADE`).
- **Evidencia (EXP):** una vista `public.informe_ajeno` sobre `mr.candles` y una clave foránea de `public.tabla_ajena` hacia `mr.write_log` fueron **eliminadas** por `DROP SCHEMA mr CASCADE` (NOTICE: «drop cascades to view informe_ajeno», «drop cascades to constraint tabla_ajena_x_fkey»). La comprobación «objetos fuera de los creados» de v2 solo miraba dentro de `mr`.
- **Problema:** `CASCADE` sigue dependencias hacia otros esquemas (DOC).
- **Impacto:** un `down` puede destruir trabajo ajeno y, en una base con datos, información irrecuperable.
- **Corrección:** `down` sin `CASCADE`, objeto por objeto en orden inverso; manifiesto de objetos creados por cada migración (`pg_identify_object`); `down` aborta si hay objetos no inventariados o dependencias externas (`pg_depend`); `down` prohibido en instancias que no sean de prueba. Ver `I1_IMPLEMENTATION_PLAN_V3.md` §5.
- **Prueba:** TS-MIG-04…09.
- **Estado:** Corregido documentalmente.

### V3-05 · La historia solo cubre velas y fuentes: una consulta histórica mezcla pasado y presente
- **Severidad:** P0
- **Documento/sección:** v2 §5 (solo `candles`, `instrument_sources` y `raw_payloads` llevan `write_seq`); `ASSET_DATA_MODEL` §4 (instrumentos, identificadores, calendarios sin versión de registro).
- **Evidencia (DOC del propio plan):** `markets`, `instruments`, `provider_licenses`, `market_sessions` se modifican en sitio.
- **Problema:** reproducir «qué sabía el sistema en W sobre T» exige también los metadatos de W. Con v2, corregir la moneda de cotización o una sesión cambia retroactivamente el significado de velas antiguas.
- **Impacto:** reproducibilidad parcial y engañosa.
- **Corrección:** `I1_TEMPORAL_MODEL.md`: matriz entidad × temporalidad; todas las lecturas históricas pasan por funciones `*_asof(W)` con W obligatorio; atributos definitorios de un instrumento inmutables (un cambio crea otro instrumento con enlace de sucesión).
- **Prueba:** TS-REPRO-01…08.
- **Estado:** Corregido documentalmente.

### V3-06 · La guardia de conexión y la prueba «sin red» se pueden saltar
- **Severidad:** P0
- **Documento/sección:** v2 §3 (guardia «analiza el DSN y rechaza cualquier host que no sea…»), §6.9, §6.13.
- **Evidencia (EXP):** con libpq 16: `host=localhost hostaddr=192.0.2.1` conectó a 192.0.2.1 («connection to server at "192.0.2.1"…»); un DSN sin host con `PGHOSTADDR=192.0.2.1` en el entorno también; `host=localhost,192.0.2.1` intentó ambos. (INF) El bloqueo de `socket.socket` de Python no intercepta los sockets que libpq abre en C; no verificado aquí porque `psycopg` no está instalado en este entorno.
- **Problema:** validar el texto del campo `host` no describe a dónde conecta libpq (DOC: `hostaddr` prevalece para la conexión; variables `PG*`, `service` y archivo de servicios completan parámetros ausentes).
- **Impacto:** el objetivo «ninguna conexión a Neon» no tiene mecanismo real; las credenciales de producción, si estuvieran en el entorno, podrían usarse.
- **Corrección:** I-1 usa **solo socket Unix**; la conexión se construye desde parámetros estructurados, se rechazan `hostaddr`, `service`, `passfile`, multi-host y cualquier `host` que no sea una ruta absoluta; el proceso elimina `PG*` del entorno antes de conectar; tras conectar se comprueba `inet_server_addr() IS NULL` y el marcador `mr.instance`. La prueba de red real se hace **a nivel de sistema**: la suite corre dentro de un espacio de red sin interfaces salvo loopback (`unshare -n` o contenedor `--network none`). Ver `I1_SECURITY_THREAT_MODEL.md` §5.
- **Prueba:** TS-NET-01…08.
- **Estado:** Corregido documentalmente.

## 4. Hallazgos P1

### V3-07 · `low > 0` excluye mercados del alcance aprobado
- **Documento/sección:** v2 §5.5 `CHECK (low > 0 …)`; DATA_QUALITY_TEST_PLAN DQ-BAR-02 («Precios > 0»).
- **Evidencia:** hecho público ampliamente documentado: el contrato de WTI de mayo de 2020 liquidó en −37,63 USD/barril el 20-abr-2020 (no reverificado en esta sesión, SUP). Diferenciales y algunos instrumentos de tasas también pueden ser negativos.
- **Problema e impacto:** el contrato universal rechaza datos válidos de petróleo y gas, que están en el alcance.
- **Corrección:** dominio de precio por instrumento (`price_domain`: `positive` | `any`); la base solo exige coherencia OHLC; la positividad es una regla de calidad condicionada al dominio. `I1_DATA_CONTRACT_REVIEW.md` §3.
- **Prueba:** TS-DATA-03.
- **Estado:** Corregido documentalmente.

### V3-08 · Volumen obligatorio y sin tipo
- **Documento/sección:** v2 §5.5 `volume numeric(38,10) NOT NULL`, `volume >= 0`.
- **Problema:** forex OTC e índices no tienen volumen negociado; muchos proveedores dan *tick volume*; cripto distingue volumen en base y en cotización.
- **Impacto:** el adaptador inventaría ceros o mezclaría magnitudes incomparables.
- **Corrección:** `volume` admite NULL y `volume_kind` obligatorio (`base_units`, `quote_notional`, `contracts`, `shares`, `tick_count`, `none`); `CHECK ((volume IS NULL) = (volume_kind = 'none'))`.
- **Prueba:** TS-DATA-04. **Estado:** Corregido documentalmente.

### V3-09 · `canonical_sha256` no identifica el significado de la vela
- **Documento/sección:** v2 §4.4 (codificación `c1`: sin proveedor, moneda, tipo de precio, base de ajuste, tipo de volumen, tipo de sesión).
- **Problema:** dos velas con los mismos números pero distinta moneda o ajuste tendrían el mismo hash y la ingesta las trataría como «sin cambios».
- **Corrección:** codificación `c2` con todos los campos que cambian el significado. `I1_DATA_CONTRACT_REVIEW.md` §5.
- **Prueba:** TS-UNIT-HASH-01…06. **Estado:** Corregido documentalmente.

### V3-10 · `Timeframe.align(ts)` y `Session` no sirven para mercados con sesión
- **Documento/sección:** v2 §4.1 (`.align(ts)`), §4.3 (`Session` con un solo `open_ts/close_ts`).
- **Problema:** D1 en acciones es una sesión, no 24 h; futuros CME y forex tienen sesiones que cruzan medianoche y pausas diarias; la alineación intradía depende del proveedor (reloj UTC o apertura de sesión).
- **Corrección:** `align` se elimina de `Timeframe`; las fronteras las da el calendario (`calendar.bar_boundaries(tf, …)`) con una política de alineación por (instrumento, proveedor, temporalidad); `Session` con `trading_date` y lista de intervalos. `I1_DATA_CONTRACT_REVIEW.md` §6.
- **Prueba:** TS-CAL-01…12. **Estado:** Corregido documentalmente.

### V3-11 · El prefijo `zz-test-` es una convención, no una frontera
- **Documento/sección:** v2 §4.5 regla 3, §5.2.
- **Problema:** cualquiera con permiso de insertar mercados puede usar el prefijo; la restricción solo impide combinaciones, no quién las crea ni en qué base.
- **Corrección:** espacio de nombres explícito (`namespace`: `real` | `synthetic`) independiente del nombre; registro de lo sintético solo vía funciones que exige el rol `mr_test_fixtures` (inexistente en bases no de prueba) y una instancia marcada `test` de forma inmutable; las vistas de producto filtran `namespace = 'real'`. `I1_SECURITY_THREAT_MODEL.md` §4.
- **Prueba:** TS-LIC-SYN-01…08. **Estado:** Corregido documentalmente.

### V3-12 · El modelo de licencias solo controla el almacenamiento
- **Documento/sección:** v2 §4.5 (`LicenseGuard.require` por uso, sin ciclo de vida); ASSET_DATA_MODEL §4 (campos que v2 no trasladó: `allows_export`, `max_users`, `professional_users_allowed`).
- **Problema:** no hay reglas para licencia vencida después de guardar, revocación, derivados, audiencia, territorio, retención posterior a la terminación.
- **Corrección:** `I1_LICENSE_ENFORCEMENT.md` (matriz completa; I-1 implementa los campos y las comprobaciones de recepción, almacenamiento, lectura y purga; las de visualización, alertas y exportación se especifican y se prueban como funciones puras, sin UI).
- **Prueba:** TS-LIC-01…20. **Estado:** Corregido documentalmente.

### V3-13 · Datos crudos: niveles mezclados y casos límite sin definir
- **Documento/sección:** v2 §4.4 (`body` «tras decodificar el transporte»), §5.4.
- **Problema:** no se distingue bytes de transporte, cuerpo decodificado, interpretación del adaptador y forma canónica; no se dice qué pasa con claves JSON duplicadas, juegos de caracteres distintos de UTF-8 o respuestas que no se pueden interpretar.
- **Corrección:** `I1_DATA_CONTRACT_REVIEW.md` §4: se persisten el cuerpo decodificado y la huella del transporte; claves duplicadas → respuesta rechazada pero cuerpo conservado con `parse_status = 'rejected'`; solo UTF-8 para JSON.
- **Prueba:** TS-RAW-01…10. **Estado:** Corregido documentalmente.

### V3-14 · `numeric(28,10)` es insuficiente para algunos activos
- **Documento/sección:** v2 §5.5; ASSET_DATA_MODEL §5.
- **Problema:** tokens con precio del orden de 1e-9 pierden dígitos significativos con 10 decimales.
- **Corrección:** `numeric` sin modificador en base; escala máxima validada por instrumento (`price_scale`, `volume_scale`) en la ingesta. **Estado:** Corregido documentalmente. **Prueba:** TS-DATA-05.

### V3-15 · El runner de migraciones no es seguro frente a fallos ni a instancias reales
- **Documento/sección:** v2 §5.1 («candado `pg_advisory_lock` de migración»; `down` disponible siempre).
- **Problema:** un candado de sesión queda tomado si el proceso cuelga; `down` en una base con datos es destructivo e irreversible; los checksums de `down` no se registran.
- **Corrección:** cada migración en una transacción con `pg_advisory_xact_lock`, `lock_timeout` y `statement_timeout`; checksum de `up` y `down`; `down` solo si `mr.instance.kind = 'test'`. **Prueba:** TS-MIG-01…12. **Estado:** Corregido documentalmente.

## 5. Hallazgos P2

| Id | Documento/sección | Evidencia | Problema | Impacto | Corrección | Prueba | Estado |
|---|---|---|---|---|---|---|---|
| V3-16 | v2 §5.3 `pg_advisory_xact_lock(hashtext('mr.write'))` | DOC: cualquier rol puede tomar candados consultivos | Cualquier sesión puede bloquear las escrituras; colisión de claves con otras aplicaciones de la misma base | Denegación de servicio | Bloqueo de fila en `mr.ledger_head`, accesible solo vía `mr.publish` | TS-ADV-09 | Corregido documentalmente |
| V3-17 | v2 (no tratado) | — | El dueño, el migrador y el superusuario pueden reescribir la historia | Manipulación indetectable por quien administra la base | Cadena de hashes en `write_log` (cada entrada incluye el hash de la anterior y del contenido); verificación periódica. Evidencia de manipulación, no prevención | TS-ADV-13 | Corregido documentalmente |
| V3-18 | v2 §5.3 | — | Sin límites de tiempo: una publicación colgada retiene el bloqueo indefinidamente | Ingesta detenida | `idle_in_transaction_session_timeout`, `lock_timeout`, `statement_timeout` para `mr_writer`; limpieza de lotes de preparación huérfanos | TS-REC-01…04 | Corregido documentalmente |
| V3-19 | v2 §10 (≈ 17 días, ~145 casos) | — | La estimación no incluía permisos, manifiesto de migraciones, temporalidad del registro ni aislamiento de red real | Planificación optimista | `I1_IMPLEMENTATION_PLAN_V3.md` §8 | — | Corregido documentalmente |
| V3-20 | ASSET_DATA_MODEL §4; v2 §4.2 | — | Cambios de moneda, bolsa o tamaño de contrato modelados como edición | Series que mezclan magnitudes | Atributos definitorios inmutables; sucesión `instrument_successions` | TS-REPRO-05 | Corregido documentalmente |
| V3-21 | DATA_QUALITY_TEST_PLAN DQ-BAR-02 | Texto «Precios > 0» | Contradice V3-07 | Regla de calidad rechazaría datos válidos | Condicionar a `price_domain`; el documento original no se edita (esta revisión no modifica archivos existentes) | TS-DATA-03 | Abierto en el documento original; corregido aquí |
| V3-22 | v2 §4.2 (`provider_quarantine` «misma semántica bitemporal») | — | Semántica de cuarentena retroactiva sin definir | Selección de fuente irreproducible | `I1_TEMPORAL_MODEL.md` §4, escenario 9 | TS-REPRO-07 | Corregido documentalmente |

## 6. Hallazgos P3

| Id | Documento/sección | Problema | Corrección | Estado |
|---|---|---|---|---|
| V3-23 | v2 §5.5 `recorded_at` | Puede confundirse con el tiempo de registro | Renombrar a `published_at` en `write_log`; quitarlo de las filas | Corregido documentalmente |
| V3-24 | v2 §6.7 «rol superusuario → error» | No comprueba `BYPASSRLS`, `CREATEROLE` ni pertenencia a `mr_owner` del rol de aplicación | Inventario de atributos de rol (TS-PRIV-02) | Corregido documentalmente |
| V3-25 | v2 §5.3 | La marca de agua se calcula recorriendo todo `write_log` | Con un contador sin huecos basta comprobar las últimas K secuencias; optimización, no correctitud | Corregido documentalmente |

## 7. Lo que se mantiene de v2

| Decisión | Por qué se mantiene |
|---|---|
| Monolito modular en Python, paquete `market_radar/` aislado de `radar/` | Sin requisito que justifique más procesos; el aislamiento es comprobable |
| PostgreSQL 16 local, sin Neon, sin proveedores reales, sin red, sin UI ni IA en I-1 | Coherente con las restricciones del propietario |
| Restricciones de exclusión con `btree_gist` para vigencias | EXP: funciona sin superusuario; DOC: extensión confiable |
| Separar datos recibidos y representación canónica | Necesario para auditar y re-procesar; se precisa en V3-13 |
| Reglas de selección de fuente sin empates por restricción | Correctas; se completan con la temporalidad de V3-05 y V3-22 |
| Ningún interruptor de entorno para licencias | Correcto; se refuerza con V3-11 |

## 8. Sesgo de revisión

El mismo equipo diseñó v1, v2 y escribe esta revisión. Para compensarlo: cada P0 se intentó demostrar con un ataque o un contraejemplo ejecutado, no con razonamiento; y los resultados favorables al diseño nuevo se presentan como EXP preliminar, no como garantía.
