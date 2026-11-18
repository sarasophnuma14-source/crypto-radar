# I-1 v3 · Rediseño del ledger, permisos y reproducibilidad

Fecha: 18-nov-2026. Sustituye la propuesta D-021 de v2 (que sigue «Propuesta» en `DECISION_LOG.md`; no se aprobó). Resuelve V3-01, V3-02, V3-03, V3-16, V3-17, V3-18.
Evidencia: **DOC** manual de PostgreSQL · **EXP** consultas desechables en PostgreSQL 16.15 local el 18-nov (no son código de I-1) · **INF** inferencia de implementación · **SUP** supuesto.

## 1. Qué debe garantizar el ledger

1. Ninguna fila versionada se escribe, modifica o borra fuera de una publicación autorizada.
2. Toda publicación recibe un número de versión **sin huecos** y su efecto (filas nuevas y cierres) es atómico.
3. Una lectura registra una marca de agua que permite repetirla después con el mismo resultado, **sin depender del orden interno de commit**.
4. Reintentar una publicación no la duplica.
5. Una caída a mitad de publicación no deja estado parcial ni bloqueos retenidos.
6. Quien administra la base puede alterar todo; eso no se puede impedir desde dentro, pero sí **detectar**.

## 2. Modelo de permisos

| Rol | LOGIN | Para qué | Puede | No puede |
|---|---|---|---|---|
| `mr_owner` | No | Dueño de esquema, tablas, funciones | Todo sobre `mr` | Conectarse |
| `mr_migrator` | Sí | Ejecutar migraciones | `SET ROLE mr_owner` dentro del runner | Usarse por la aplicación; existir con contraseña en el entorno de la aplicación |
| `mr_writer` | Sí | Ingesta | `INSERT` en columnas permitidas de tablas de preparación; `EXECUTE` en `mr.publish_*`, `mr.watermark()` | `SELECT/INSERT/UPDATE/DELETE/TRUNCATE` en tablas versionadas, `write_log`, `ledger_head`; crear objetos; tablas temporales |
| `mr_reader` | Sí | Lecturas | `EXECUTE` en `mr.*_asof(...)`, `mr.watermark()`; `SELECT` en vistas de lectura | Escribir nada |
| `mr_test_fixtures` | Sí | Solo en bases de prueba | `EXECUTE` en `mr.register_synthetic_*` | Existir en bases que no sean de prueba |
| `PUBLIC` | — | — | Nada en la base `mr` | `CONNECT`, `USAGE` en `mr`, `EXECUTE` de funciones, `TEMP` |

Atributos prohibidos para cualquier rol con LOGIN salvo el migrador: `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `BYPASSRLS`, `REPLICATION`, pertenencia a `mr_owner`.

```sql
-- Ilustrativo (no es una migración del repositorio)
REVOKE ALL ON DATABASE mr_db FROM PUBLIC;
GRANT CONNECT ON DATABASE mr_db TO mr_writer, mr_reader, mr_migrator;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA mr AUTHORIZATION mr_owner;
REVOKE ALL ON SCHEMA mr FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE mr_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;  -- DOC: por defecto PUBLIC puede ejecutar funciones
GRANT USAGE ON SCHEMA mr TO mr_writer, mr_reader;
GRANT INSERT (batch_id, instrument_id, timeframe, bar_start, bar_end, open, high, low, close,
              volume, volume_kind, is_closed, source_ts, payload_ref, locator)
  ON mr.stage_candles TO mr_writer;                -- staged_by lo pone la base: session_user
GRANT EXECUTE ON FUNCTION mr.publish_candles(uuid) TO mr_writer;
GRANT EXECUTE ON FUNCTION mr.watermark() TO mr_reader, mr_writer;
```

**Frente a quién es seguro:** frente a un actor que controla la conexión de `mr_writer` o `mr_reader` (código de aplicación comprometido, inyección SQL, credencial filtrada de esos roles). **No** frente a `mr_migrator`, `mr_owner` o un superusuario: pueden desactivar disparadores o borrar tablas. Para ellos el control es de **detección** (§7) y de proceso (el migrador no vive en el entorno de la aplicación).

## 3. Escritura: preparación y publicación

Se adopta el patrón **preparar → publicar** (alternativa 2 de §5):

1. **Preparar** (sin bloqueo global): `mr_writer` inserta las filas del lote en `mr.stage_*` con un `batch_id` (UUID generado por el cliente). `staged_by` lo fija la base (`DEFAULT session_user`, sin privilegio de columna para el escritor). El cuerpo crudo va a `mr.stage_payloads`.
2. **Publicar**: `mr_writer` llama `mr.publish_candles(batch_id)`. La función, `SECURITY DEFINER` con dueño `mr_owner`:
   - fija `search_path = pg_catalog, pg_temp` y califica todos los nombres con `mr.`; no usa SQL dinámico;
   - si `batch_id` ya está en `write_log`, devuelve su versión (idempotencia);
   - comprueba que el lote existe y es de `session_user`;
   - valida licencia, coherencia y espacio de nombres del lote completo (si algo falla, aborta entera);
   - toma la siguiente versión con `UPDATE mr.ledger_head SET last_seq = last_seq + 1 RETURNING last_seq` (bloqueo de fila que dura hasta el fin de la transacción);
   - inserta la entrada de `write_log` con `xid = pg_current_xact_id()` y el hash encadenado;
   - cierra revisiones vigentes que cambian (`superseded_seq = s`) e inserta las nuevas (`write_seq = s`), en la misma transacción;
   - borra el lote de preparación.
3. El cliente confirma (`COMMIT`). Hasta entonces nada es visible.

```sql
-- Ilustrativo
CREATE FUNCTION mr.publish_candles(p_batch uuid) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE s bigint; prev bigint; prev_h bytea;
BEGIN
  SELECT w.write_seq INTO prev FROM mr.write_log w WHERE w.batch_id = p_batch;
  IF prev IS NOT NULL THEN RETURN prev; END IF;
  IF NOT EXISTS (SELECT 1 FROM mr.stage_candles c WHERE c.batch_id = p_batch AND c.staged_by = session_user) THEN
    RAISE EXCEPTION 'lote % inexistente o ajeno', p_batch; END IF;
  PERFORM mr.assert_batch_valid(p_batch);                 -- licencia, OHLC, namespace, payload presente
  UPDATE mr.ledger_head SET last_seq = last_seq + 1 RETURNING last_seq INTO s;
  SELECT l.entry_hash INTO prev_h FROM mr.write_log l WHERE l.write_seq = s - 1;   -- NULL si s = 1
  INSERT INTO mr.write_log (write_seq, kind, batch_id, xid, published_by, prev_hash, entry_hash)
  VALUES (s, 'candles', p_batch, pg_current_xact_id(), session_user, prev_h,
          mr.entry_hash(s, p_batch, mr.batch_digest(p_batch), prev_h));
  -- cierres y altas en la misma transacción (detalle en el plan v3 §5)
  ...
  DELETE FROM mr.stage_candles WHERE batch_id = p_batch;
  RETURN s;
END $$;
```

### Disparadores de defensa (segunda línea)

Sobre cada tabla versionada, `BEFORE INSERT OR UPDATE OR DELETE` y `BEFORE TRUNCATE`:

- La operación solo procede si existe en `mr.write_log` una entrada con `xid = pg_current_xact_id()` (es decir, hay una publicación abierta **en esta transacción**). El escritor no puede crear esa entrada: no tiene privilegios sobre `write_log`. **No se usa ninguna variable de sesión.**
- `INSERT`: `write_seq` debe ser la versión de esa entrada y `superseded_seq` nulo.
- `UPDATE`: solo `superseded_seq` de NULL a la versión actual; cualquier otro cambio de columna → error.
- `DELETE` y `TRUNCATE` → error siempre. La purga de cuerpos crudos es una publicación (`mr.publish_purge`) que pone `body = NULL` y deja la huella.

Protegen contra errores del propio `mr_owner` (por ejemplo, un `UPDATE` manual sin desactivar disparadores). EXP: el dueño, sin desactivar el disparador, recibió «escritura fuera de una publicación».

## 4. Lectura reproducible: marca de agua (W, H)

**Definiciones**

| Término | Definición |
|---|---|
| Tiempo válido (T) | Instante del mundo al que se refiere el dato: `[bar_start, bar_end)` de una vela; `[valid_from, valid_to)` de un identificador, licencia, sesión o fuente |
| Tiempo de registro | Versión de publicación en la que el sistema supo el dato (`write_seq`). `published_at` es solo una hora informativa |
| Versión de publicación | Entero sin huecos asignado por `mr.publish_*` |
| Revisión | Fila nueva para la misma clave de negocio con `write_seq` mayor |
| Sustitución | La revisión anterior recibe `superseded_seq` = versión de la nueva, en la misma publicación |
| Marca de agua | Par **(W, H)**: W = mayor versión visible en la instantánea del lector; H = versiones ≤ W no visibles en esa instantánea |
| Visible en (W, H) | `write_seq ≤ W ∧ write_seq ∉ H ∧ (superseded_seq IS NULL ∨ superseded_seq > W ∨ superseded_seq ∈ H)` |

**Pregunta que responde:** «¿qué sabía el sistema en (W, H) sobre el mercado en T?» = filas visibles en (W, H) cuyo tiempo válido contiene T, unidas **solo** con metadatos también visibles en (W, H) (`I1_TEMPORAL_MODEL.md`).

```sql
-- Ilustrativo: captura de la marca, en la misma transacción que las lecturas
BEGIN ISOLATION LEVEL REPEATABLE READ;      -- DOC: todas las sentencias ven la misma instantánea
SELECT w, holes FROM mr.watermark();       -- w = max(write_seq); holes = {1..w} sin entrada visible
SELECT * FROM mr.candles_asof(w, holes, :instrument, :provider, :tf, :t0, :t1);
COMMIT;
-- Reproducción, en cualquier momento posterior:
SELECT * FROM mr.candles_asof(:w, :holes, :instrument, :provider, :tf, :t0, :t1);
```

**Por qué es correcta sin depender del orden interno de commit**

- El contador vive en una fila actualizada dentro de la transacción de publicación. Si la publicación se deshace, la actualización se deshace (DOC: MVCC transaccional). Por eso las versiones **confirmadas** no tienen huecos.
- Una segunda publicación que intenta actualizar la fila espera a que la primera termine; si la primera confirmó, la segunda continúa con el valor nuevo; si la deshizo, con el anterior (DOC: comportamiento de `UPDATE` concurrente en READ COMMITTED).
- La marca registra H explícitamente. Si alguna vez un lector viera la versión *n* sin ver la *n−1* (lo que dependería del orden interno), *n−1* quedaría en H y se excluiría también al reproducir. La reproducción es idéntica en ambos casos. El orden interno solo determina si H está vacío.
- Expectativa (INF): con publicaciones serializadas, H estará vacío siempre. Un H no vacío se registra como evento operativo para investigarlo, no como error de correctitud.

**Limitación honesta:** la correctitud se apoya en garantías documentadas de MVCC, aislamiento REPEATABLE READ y bloqueo de fila, más la exclusión explícita de H. No se apoya en el ensayo. El ensayo (EXP) sirve para detectar errores de implementación.

## 5. Alternativas comparadas

| | 1. Candado consultivo + secuencia (v2) | **2. Preparar y publicar con contador sin huecos + (W, H)** (recomendada) | 3. Instantáneas de transacción (`pg_current_snapshot`, `pg_visible_in_snapshot`, `xid8`) |
|---|---|---|---|
| Garantía de reproducción | INF (orden interno de commit) + EXP | DOC (MVCC, REPEATABLE READ, bloqueo de fila) + exclusión explícita de H | DOC (funciones documentadas de instantánea) |
| Huecos | Sí: `nextval` no es transaccional; un hueco no se distingue de una transacción en curso | No en versiones confirmadas | No aplica (identifica transacciones) |
| Falsificación por el escritor | Sí en v2 (V3-01); se cierra solo con el modelo de permisos | Cerrada por permisos + disparadores contra `write_log` | Igual que 2 si se aplican los mismos permisos |
| Rendimiento | Escrituras serializadas mientras dura la transacción completa | Serializa solo la publicación; la carga masiva va a preparación sin bloqueo global | Sin serialización |
| Complejidad | Baja, pero insegura | Media | Alta: las marcas son instantáneas con listas de transacciones en curso |
| Casos de fallo | Candado consultivo tomable por cualquier rol (DoS) | Publicación colgada retiene la fila → `idle_in_transaction_session_timeout`, `lock_timeout` | Los `xid8` no se conservan entre clústeres: tras restaurar una copia lógica, los identificadores nuevos pueden chocar con los históricos |
| Facilidad de prueba | Media | Alta: contador sin huecos y H comprobables | Baja |
| Consecuencias para I-2 | Hay que rehacerla | Escala mientras la publicación de un lote dure milisegundos; plan B: publicar varios lotes por transacción | Ata la historia a un clúster físico concreto |

**Decisión recomendada:** alternativa 2. Se descarta la 3 como mecanismo principal por la portabilidad de `xid8`; puede guardarse `pg_current_snapshot()` junto a la marca como diagnóstico (P3, opcional).

## 6. Rollback, idempotencia y recuperación

| Situación | Comportamiento |
|---|---|
| Error dentro de `publish` | La transacción se deshace entera: sin versión, sin filas, sin cierres; el contador vuelve atrás |
| Conexión caída o terminada durante `publish` o antes del `COMMIT` | PostgreSQL deshace la transacción (DOC); el bloqueo de fila se libera. EXP: 20 conexiones terminadas a mitad de publicación, 0 huecos, 0 lotes huérfanos (preparación y publicación en la misma transacción) |
| Preparación confirmada en una transacción y publicación fallida en otra | El lote queda en `stage_*`. Reintento seguro: `publish` es idempotente. Limpieza: lotes sin publicar con más de 24 h se borran con una función de mantenimiento (registrada en `ops_events`) |
| Cliente no sabe si su `COMMIT` llegó | Reintenta `publish(batch_id)`: devuelve la versión existente si se confirmó, o publica si no |
| Mismo contenido en otro lote | Se publica una versión sin filas nuevas (las velas con igual `canonical_sha256` no generan revisión). Se registra el lote para trazabilidad |
| Publicación que tarda demasiado | `statement_timeout` y `lock_timeout` para `mr_writer`; `idle_in_transaction_session_timeout` (p. ej. 30 s) para que nadie retenga la fila |

## 7. Detección de manipulación por administradores

Cada entrada de `write_log` guarda `entry_hash = SHA-256(write_seq ‖ batch_id ‖ resumen del contenido publicado ‖ prev_hash)`. Una verificación (función de solo lectura) recorre la cadena y recalcula los resúmenes de contenido. Cambiar una fila publicada, aunque sea como superusuario, rompe la cadena salvo que el atacante la recalcule entera; para eso, el último hash se copia fuera de la base (en el informe de cada escaneo y en las copias). Esto **detecta**, no impide.

## 8. Pruebas adversariales del ledger

Resultados EXP preliminares del 18-nov contra un prototipo SQL desechable del diseño 2. No sustituyen a las pruebas de I-1.

| Id | Ataque (como `mr_writer` salvo indicación) | Resultado esperado | EXP 18-nov |
|---|---|---|---|
| TS-ADV-01 | `INSERT` directo en `candles` | `permission denied` | Rechazado |
| TS-ADV-02 | `set_config('mr.write_seq', …)` + `INSERT` | `permission denied` | Rechazado |
| TS-ADV-03 | `UPDATE … SET superseded_seq` | `permission denied` | Rechazado |
| TS-ADV-04 | `ALTER TABLE … DISABLE TRIGGER` | `must be owner` | Rechazado |
| TS-ADV-05 | Avanzar `ledger_head` | `permission denied` | Rechazado |
| TS-ADV-06 | Insertar en `write_log` | `permission denied` | Rechazado |
| TS-ADV-07 | Suplantar `staged_by` | `permission denied` (privilegio de columna) | Rechazado |
| TS-ADV-08 | Publicar un lote inexistente o de otro usuario | Error de la función | Rechazado |
| TS-ADV-09 | Crear objetos en `mr` | `permission denied for schema` | Rechazado |
| TS-ADV-10 | `TRUNCATE` | `permission denied` y disparador | Rechazado |
| TS-ADV-11 | Sombrear `mr.write_log` con una tabla temporal (`pg_temp`) | Sin efecto: `search_path` fijo y nombres calificados | Sin efecto (con `TEMP` concedido a propósito) |
| TS-ADV-12 | Llamar funciones internas (disparador, validadores) | `permission denied for function` | Rechazado |
| TS-ADV-13 | `mr_owner` hace `UPDATE` directo sin desactivar disparadores | Error del disparador | Rechazado |
| TS-ADV-14 | Superusuario altera una fila publicada | La verificación de la cadena falla | No probado (pendiente en I-1) |

Pruebas de concurrencia (TS-CONC-01…08 en `I1_TEST_STRATEGY_V3.md`). EXP preliminar: 8 escritores × 25 intentos con pausas dentro de la transacción, 10 % de rollbacks voluntarios y 20 terminaciones forzadas; 160 publicaciones confirmadas (versiones 179–338), 0 huecos, 60/60 marcas reproducidas, H vacío en las 60.

## 9. Lo que sigue sin garantía

- La seguridad frente a `mr_owner`, `mr_migrator` y superusuario es solo detección (§7).
- El rendimiento de la publicación serializada no está medido con volúmenes reales (SUP: suficiente para I-1 e I-2).
- La lista de comprobaciones de `assert_batch_valid` depende de los contratos de `I1_DATA_CONTRACT_REVIEW.md` y `I1_LICENSE_ENFORCEMENT.md`.
