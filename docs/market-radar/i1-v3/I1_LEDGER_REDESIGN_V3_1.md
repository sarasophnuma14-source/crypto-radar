# I-1 v3.1 · Ledger: idempotencia concurrente de publicaciones

Fecha: 18-nov-2026. **Complementa** `I1_LEDGER_REDESIGN.md` (v3), que no se modifica. Todo lo de v3 sigue vigente salvo lo que este documento sustituye de forma explícita (§7). Resuelve DV3-13 y los hallazgos V3-26, V3-27 y V3-29.

Evidencia: **DOC** manual de PostgreSQL 16 · **INF** inferencia · **SUP** supuesto. En esta revisión **no se ejecutó ninguna consulta** (ni siquiera en un entorno desechable): todo lo que aquí se afirma de PostgreSQL es DOC o INF, y se verificará en M1 con las pruebas TS-IDEM.

## 1. La condición de carrera del diseño v3

`mr.publish_candles` de v3 (`I1_LEDGER_REDESIGN.md` §3) hace esto, en este orden:

1. busca `batch_id` en `write_log` → no está;
2. comprueba que existen filas de preparación del lote;
3. bloquea y avanza `ledger_head`;
4. inserta en `write_log`, cierra y añade velas, borra la preparación.

Con dos escritores A y B y el mismo `batch_id`, cuando el lote se preparó en una transacción ya confirmada:

| Paso | A | B |
|---|---|---|
| 1 | No encuentra el lote en `write_log` | No lo encuentra |
| 2 | Encuentra las filas preparadas | Las encuentra |
| 3 | Bloquea `ledger_head` y obtiene *s* | Espera el bloqueo |
| 4 | Publica, borra la preparación, confirma | Obtiene el bloqueo y *s + 1* |
| 5 | | Si `write_log.batch_id` **no** es único: inserta una segunda entrada con 0 filas → **dos versiones para un mismo lote**. Si es único: error de clave duplicada → **el reintento no devuelve la versión original** |

Las dos salidas incumplen el contrato. Hallazgo **V3-26 (P0)**. La causa es que las comprobaciones de los pasos 1 y 2 se hacen **antes** de tener cualquier bloqueo y no se repiten después.

## 2. Ciclo de vida del lote

Nueva tabla `mr.batches`, propiedad de `mr_owner`, sin privilegios directos para ningún rol con LOGIN.

| Columna | Significado |
|---|---|
| `batch_id uuid PRIMARY KEY` | Identidad del lote. **Restricción única** (es la clave primaria) |
| `declared_digest bytea NOT NULL` | SHA-256 del contenido canónico que el cliente declara al abrir |
| `kind text NOT NULL` | `candles`, `sources`, `registry`, `purge` |
| `status text NOT NULL` | `open` → `sealed` → `published` |
| `opened_by text`, `opened_xid xid8` | Quién y en qué transacción se abrió |
| `write_seq bigint UNIQUE` | Versión asignada al publicar; NULL hasta entonces |
| `opened_at`, `sealed_at`, `published_at` | Horas informativas |

Además: `write_log.batch_id` pasa a ser `UNIQUE NOT NULL` con clave foránea a `batches`.

```
             open_batch                 seal_batch                     publish
 (no existe) ─────────────▶ open ──────────────────▶ sealed ─────────────────────▶ published
                     │ stage_* solo desde la           │ contenido inmutable;             │ versión fija;
                     │ transacción que lo abrió        │ digest verificado                │ reintentos devuelven write_seq
                     └─ rollback: el lote desaparece    └─ rollback de publish: sigue sealed
```

| Transición | Quién | Regla |
|---|---|---|
| — → `open` | `mr.open_batch(batch_id, digest, kind)` | `INSERT … ON CONFLICT (batch_id) DO NOTHING`. Si otra transacción **en curso** insertó el mismo `batch_id`, esta espera a que termine (DOC: comportamiento de `INSERT … ON CONFLICT` con índices únicos). Si ya existe: devuelve su estado (ver §3) |
| Preparar filas | `INSERT` en `mr.stage_*` | Disparador: el lote debe estar `open` y `opened_xid = pg_current_xact_id()`. Solo la transacción que lo abrió puede añadir filas |
| `open` → `sealed` | `mr.seal_batch(batch_id)` | Calcula el digest de las filas preparadas; debe ser igual a `declared_digest`; si no, error y la transacción se deshace |
| `sealed` → `published` | `mr.publish(batch_id)` | §4 |
| `open` sin sellar al confirmar | — | Disparador de restricción **diferido** en `batches`: una transacción no puede confirmar con un lote suyo en `open` (DOC: los disparadores de restricción `DEFERRABLE INITIALLY DEFERRED` se evalúan al confirmar). No quedan lotes abiertos huérfanos |

**Identificador determinista (recomendado):** `batch_id = UUIDv5(espacio fijo de Market Radar, declared_digest)`. Un reintento con el mismo contenido genera el mismo `batch_id` aunque el cliente haya perdido su estado. Dos contenidos distintos nunca comparten `batch_id`, salvo colisión de SHA-256.

## 3. `open_batch`: resultados posibles

| Situación al abrir | Resultado devuelto | Qué hace el cliente |
|---|---|---|
| No existe | `('opened', NULL)` | Prepara filas, sella, publica |
| Existe `published` con el mismo digest | `('published', write_seq)` | Nada: es un reintento; usa `write_seq` |
| Existe `sealed` con el mismo digest | `('sealed', NULL)` | No vuelve a preparar; llama a `publish` |
| Existe con **distinto** digest | Error `BatchConflict` | Error de programación o de datos; se registra en `ops_events` |
| Otra transacción lo tiene `open` en curso | Espera a que termine; después, uno de los casos anteriores, o `opened` si la otra se deshizo | — |

## 4. `publish`: contrato formal

**Entrada:** `batch_id`. **Salida:** `write_seq` (entero). **Precondición:** la transacción debe estar en `READ COMMITTED`.

Pasos, todos dentro de la función `SECURITY DEFINER` con `search_path = pg_catalog, pg_temp`:

1. **Aislamiento.** Si `current_setting('transaction_isolation') <> 'read committed'` → error `PublishRequiresReadCommitted` (V3-27, §5).
2. **Bloqueo del lote.** `SELECT … FROM mr.batches WHERE batch_id = $1 FOR UPDATE`. Si otra transacción tiene el lote bloqueado, espera. Al obtenerlo, PostgreSQL devuelve la **versión más reciente confirmada** de la fila (DOC: en READ COMMITTED, `SELECT FOR UPDATE` que espera a una transacción concurrente que modificó la fila trabaja con la versión actualizada).
3. **Primera validación.** No existe → `UnknownBatch`. `published` → **devolver `write_seq` original** (idempotencia). `open` y abierto en otra transacción → `BatchNotSealed`. `sealed` → continuar.
4. **Bloqueo del ledger.** `SELECT last_seq FROM mr.ledger_head FOR UPDATE`.
5. **Revalidación después del bloqueo del ledger.** Se vuelve a leer el lote y se busca `batch_id` en `write_log` (sentencias nuevas: en READ COMMITTED cada una ve lo confirmado hasta ese momento, DOC). Si ya está publicado → devolver ese `write_seq` sin avanzar el contador. Con el bloqueo del paso 2 esto no debería ocurrir nunca; es la segunda barrera exigida por DV3-13 y protege a futuras variantes de publicación que no tomen el bloqueo del lote.
6. **Asignación.** `s = last_seq + 1`; `UPDATE ledger_head SET last_seq = s`.
7. **Registro.** `INSERT INTO write_log (write_seq, batch_id, …)`. La restricción única de `batch_id` es la **tercera barrera**: si por un error lógico llegara aquí un lote ya publicado, la sentencia falla y la transacción se deshace entera.
8. **Aplicación.** Cierres (`superseded_seq = s`) y altas (`write_seq = s`) desde la preparación del lote; borrado de la preparación.
9. **Cierre del lote.** `UPDATE batches SET status = 'published', write_seq = s`.
10. Devolver `s`. La publicación es visible solo cuando el cliente confirma.

**Orden de bloqueos fijo:** fila del lote → fila de `ledger_head`. Si en el futuro una transacción publica varios lotes, los bloquea en orden de `batch_id` antes de tocar `ledger_head`. Con un orden total fijo no hay interbloqueos entre publicadores (INF: argumento estándar de orden de adquisición; TS-IDEM-12 lo comprueba).

**Garantías y su fuente**

| Propiedad | Fuente |
|---|---|
| Un `batch_id` se publica a lo sumo una vez | DOC: restricción única en `batches` y en `write_log.batch_id` |
| Dos publicadores concurrentes del mismo lote: uno publica, el otro devuelve la misma versión | DOC: espera de `FOR UPDATE` y lectura de la versión actualizada en READ COMMITTED; pasos 2–3 |
| Rollback o desconexión de un publicador no deja rastro y el otro puede publicar | DOC: atomicidad de la transacción; liberación de bloqueos al terminar |
| Un reintento tras un `COMMIT` de resultado desconocido devuelve la versión original | Pasos 2–3 + `mr.batch_status` (§6) |
| Versiones confirmadas sin huecos | v3 §4 (contador en fila); sin cambios |

## 5. Aislamiento exigido (V3-27)

En `REPEATABLE READ` o `SERIALIZABLE`, si el lote o `ledger_head` fueron modificados por una transacción confirmada después de la instantánea, `SELECT … FOR UPDATE` falla con error de serialización (DOC). El resultado sería seguro (nada se publica dos veces) pero **no idempotente**: el cliente recibiría un error en lugar de la versión original. Para que el contrato sea determinista, `publish` exige `READ COMMITTED` y lo comprueba. Las **lecturas** reproducibles siguen usando `REPEATABLE READ` (v3 §4); son transacciones distintas.

## 6. Reintento tras un `COMMIT` de resultado desconocido

El cliente envió `COMMIT` y perdió la conexión antes de recibir la respuesta. No sabe si se confirmó.

1. Abre una conexión nueva.
2. Llama `mr.batch_status(batch_id)` (lectura, `SECURITY DEFINER`, solo devuelve estado y versión de lotes del propio `session_user`):
   - `published, s` → la publicación ocurrió; usa `s`. **No** vuelve a publicar.
   - `sealed` → (solo modo de dos transacciones) la preparación se confirmó y la publicación no: llama a `publish`.
   - no existe → la transacción no se confirmó: repite todo con el **mismo** `batch_id` (determinista).
3. Llamar directamente a `publish(batch_id)` también es seguro: devuelve `s` si ya se publicó.

Ningún camino genera un `batch_id` nuevo para el mismo contenido.

## 7. Modos de uso y cambios respecto a v3

| Modo | Secuencia | Cuándo |
|---|---|---|
| Una transacción (recomendado en I-1) | `BEGIN` (READ COMMITTED) → `open_batch` → `INSERT stage_*` → `seal_batch` → `publish` → `COMMIT` | Lotes pequeños o medianos |
| Dos transacciones | T1: `open_batch` → `INSERT stage_*` → `seal_batch` → `COMMIT`; T2: `publish` → `COMMIT` | Cargas grandes, para no mantener el bloqueo del ledger durante la preparación |

| v3 | v3.1 |
|---|---|
| `staged_by = session_user` como propiedad del lote | Propiedad por transacción de apertura (`opened_xid`) y digest declarado |
| Comprobación de existencia antes de bloquear | Bloqueo del lote → validación → bloqueo del ledger → revalidación |
| `write_log.batch_id` sin restricción declarada en el documento | `UNIQUE NOT NULL` con clave foránea a `batches` |
| Aislamiento no especificado para `publish` | `READ COMMITTED` obligatorio y comprobado |
| Limpieza de lotes preparados con más de 24 h | Se mantiene solo para lotes `sealed` sin publicar; los `open` no pueden quedar confirmados |

## 8. Privilegios añadidos

| Rol | Nuevo privilegio |
|---|---|
| `mr_writer` | `EXECUTE` en `mr.open_batch`, `mr.seal_batch`, `mr.publish`, `mr.batch_status` |
| `mr_writer` | Sin privilegios en `mr.batches` |
| `mr_reader` | Ninguno nuevo |

## 9. Ataques nuevos y su protección

| Ataque | Protección |
|---|---|
| Publicar un lote abierto por otra transacción | `BatchNotSealed` |
| Preparar filas en un lote abierto por otra transacción | Disparador por `opened_xid` |
| Cambiar el contenido después de sellar | Las filas de preparación de un lote `sealed` no admiten `INSERT/UPDATE/DELETE` (disparador) |
| Reutilizar un `batch_id` publicado con otro contenido | `BatchConflict` en `open_batch` |
| Forzar `status = 'published'` o `write_seq` en `batches` | Sin privilegios; disparador que solo permite las transiciones del diagrama desde las funciones |
| Consultar el estado de lotes de otro rol | `batch_status` filtra por `session_user` |

## 10. Lo que sigue sin garantía

- Nada de esta sección se ha ejecutado. La correctitud se apoya en comportamientos documentados de PostgreSQL y se demuestra en M1 con TS-IDEM.
- La espera de `INSERT … ON CONFLICT` sobre una transacción en curso puede durar lo que dure esa transacción: los tiempos límite de v3 §6 (`lock_timeout`, `idle_in_transaction_session_timeout`) se aplican también aquí.
- Si un administrador manipula `batches` con privilegios de dueño, la cadena de hashes de v3 §7 lo detecta; no lo impide.
