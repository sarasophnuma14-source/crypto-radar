# I-1 v3.2 · Ledger: identidad de lotes, digest canónico, limpieza concurrente, identidad del productor y CI

Fecha: 18-nov-2026. Rama documental `claude/project-thread-dclqgc` (PR #16 en borrador).

**Complementa** `I1_LEDGER_REDESIGN.md` (v3) y `I1_LEDGER_REDESIGN_V3_1.md` (v3.1). Ninguno de los dos se modifica. Todo lo que dicen sigue vigente salvo lo que este documento sustituye expresamente en §0.2.

Documentos hermanos de v3.2:
- `I1_TEST_STRATEGY_V3_2.md`: pruebas TS-BATCH-ID, TS-BATCH-DIGEST, TS-CLEANUP, TS-IDENTITY y TS-CI-SEC.
- `I1_ACCEPTANCE_V3_2.md`: criterios A16–A23 y veredicto.
- `I1_CHANGELOG_V3_2.md`: hallazgos, decisiones propuestas, efecto en el plan y auditoría independiente.

## 0. Cómo leer este documento

### 0.1 Evidencia

| Etiqueta | Significado |
|---|---|
| **DOC** | Garantía escrita en el manual de PostgreSQL 16 o en un estándar público (RFC 9562 para UUID, FIPS 180-4 para SHA) |
| **DOC-GH** | Documentación pública de GitHub. **No se reverificó en esta sesión**: se comprueba al implementar |
| **INF** | Inferencia sobre el comportamiento o la implementación, no garantizada |
| **SUP** | Supuesto no verificado |

En esta revisión **no se escribió código, no se ejecutó ninguna consulta ni prueba y no se creó ningún prototipo**. Nada de lo que aquí se afirma está verificado. Ningún hallazgo pasa de «Corregido documentalmente».

### 0.2 Qué sustituye v3.2

| Elemento de v3 / v3.1 | Sustituido por (v3.2) | Motivo |
|---|---|---|
| v3.1 §2: `batch_id = UUIDv5(espacio fijo, declared_digest)` y la frase «dos contenidos distintos nunca comparten `batch_id`, salvo colisión de SHA-256» | §2: identidad del lote = (`producer_id`, `idem_key`); `batch_id` lo genera la base | MR-01; hallazgo V3-30 |
| v3.1 §2: columna única `declared_digest` con contenido sin definir | §3: `batch_digest` y `semantic_digest` según el contrato MRC-1 | MR-02 |
| v3 `I1_DATA_CONTRACT_REVIEW.md` §5: codificación `c2` con separador `\|` y nulos como cadena vacía | §3.8: codificación `c3` sobre MRC-1 | V3-31 |
| v3 §7: `entry_hash` como concatenación sin codificación definida | §3.8: `entry_hash` sobre MRC-1, incluyendo al productor | V3-40 |
| v3.1 §7: «limpieza de lotes `sealed` con más de 24 h», sin protocolo | §4: estado `expired`, protocolo de limpieza con bloqueos y reapertura | MR-03 |
| v3.1 §2: `opened_by text` y filtro por `session_user` | §5: tres niveles de identidad, vínculo rol → productor y auditoría por OID | MR-04 |
| v3 §2: `mr_writer` como rol con LOGIN compartido por todos los procesos | §5.2: `mr_writer` pasa a rol de grupo NOLOGIN; un rol con LOGIN por servicio | MR-04 |
| v3.1 §4 paso 3 y TS-ADV-15/16: «lote abierto por otra transacción → `BatchNotSealed`» | §4.3: ese estado no es observable desde otra transacción; los errores son `MRB02` y `MRB07` | V3-32 |
| v3.1 §3: `BatchConflict` como error **y** evento operativo | §2.6: el conflicto es un resultado y el evento se conserva | V3-33 |
| v3.1 DV3-14 (límites de Actions) | §6: se mantienen y se amplían | MR-05 |

Todo lo demás de v3.1 sigue vigente sin cambios:
- el contrato de `publish` (§4 de v3.1), con su orden de bloqueos lote → `ledger_head`, la revalidación tras el segundo bloqueo y la exigencia de READ COMMITTED;
- `write_log.batch_id` `UNIQUE NOT NULL`;
- los dos modos de uso;
- el disparador diferido que impide confirmar lotes abiertos.

## 1. Revisión crítica de v3.1: qué estaba mal

El detalle de cada hallazgo, con su id, está en `I1_CHANGELOG_V3_2.md` §3. Lo esencial es esto:

1. **La identidad por contenido pierde datos legítimos (V3-30, P0).** Con `batch_id = UUIDv5(digest)`, publicar dos veces el mismo contenido se trata como un reintento. Ejemplo: un proveedor publica A, corrige a B y vuelve a A. El tercer lote tiene el mismo contenido que el primero y recibe su `batch_id`. `open_batch` devuelve `('published', s₁)` y la vuelta a A **no se publica nunca**: el estado vigente se queda en B. Lo mismo ocurre con el registro (un atributo pasa de 1 a 2 y vuelve a 1). v3 no tenía este problema, porque su `batch_id` era aleatorio («mismo contenido en otro lote: se publica una versión sin filas nuevas», v3 §6). v3.1 lo introdujo.
2. **La afirmación sobre colisiones era incorrecta (MR-01).** UUIDv5 no hereda la resistencia de SHA-256 (§2.1).
3. **El digest no estaba definido (MR-02).** Su contenido, su orden y su codificación no estaban especificados, y `c2` es ambiguo (V3-31).
4. **La limpieza no tenía protocolo (MR-03).** Una limpieza por antigüedad sin bloqueo puede borrar la preparación de un lote que otra transacción está publicando.
5. **La identidad se confundía (MR-04).** `session_user` identifica un rol de PostgreSQL, no un proceso, un productor ni una persona.
6. **Las pruebas de CI no protegen frente a una PR maliciosa (MR-05, V3-35).** El análisis estático del flujo se ejecuta desde la propia PR, que puede modificarlo.
7. **Un estado inobservable figuraba como observable (V3-32).** Varios resultados esperados de v3.1 (TS-ADV-15, TS-ADV-16 y la redacción de TS-ADV-20) suponían un estado que el MVCC no deja ver o eran ambiguos.
8. **Los tiempos límite los puede desactivar el cliente (V3-47).** v3 los presentaba como protección. `idle_in_transaction_session_timeout`, `lock_timeout` y `statement_timeout` son parámetros que cualquier sesión puede cambiar con `SET` (DOC: contexto `user`).

## 2. MR-01 · Identidad del lote y colisiones

### 2.1 Propiedades reales de UUIDv5

| Propiedad | Detalle | Fuente |
|---|---|---|
| Algoritmo | SHA-1 de (espacio de nombres ‖ nombre). Se toman los primeros 128 bits y se sobrescriben 4 bits de versión y 2 de variante | DOC (RFC 9562 §5.5) |
| Bits efectivos | **122** | DOC |
| Colisión accidental | Por la paradoja del cumpleaños, la probabilidad con *n* lotes es ≈ *n*² / 2¹²³. Es despreciable en la práctica (≈ 10⁻¹⁹ con 10⁹ lotes), pero **no es cero** y es **independiente** de la de SHA-256: dos digests SHA-256 distintos pueden dar el mismo UUIDv5 | DOC + cálculo |
| Colisión provocada | SHA-1 no es resistente a colisiones: se han publicado colisiones prácticas (2017) y de prefijo elegido (2020). Además, la truncación a 122 bits deja un ataque genérico de cumpleaños de ≈ 2⁶¹ operaciones. Un atacante que controle el contenido de los lotes no controla directamente el digest SHA-256 que entra en UUIDv5, lo que dificulta explotar las colisiones de SHA-1. **No se puede afirmar** que sea imposible | DOC (publicaciones públicas sobre SHA-1) + INF |
| Unicidad | **Ninguna** función hash da unicidad matemática. La unicidad del identificador solo la garantiza la restricción `UNIQUE` / `PRIMARY KEY` de la base, que **rechaza** el duplicado; no lo evita | DOC |

Corrección de la frase de v3.1: dos contenidos distintos pueden compartir un UUIDv5 por **dos** caminos, una colisión de SHA-256 o una colisión del UUIDv5 de 122 bits. En v3.1, una colisión del UUID con distinto digest acababa en `BatchConflict` (el digest completo se comparaba), así que **no** reutilizaba el lote. Pero el contenido legítimo quedaba sin poder publicarse con ese identificador.

### 2.2 El problema de fondo: reintento frente a operación nueva

Un reintento es **la misma operación** enviada otra vez. Una operación nueva con el mismo contenido es **otra observación** que hay que registrar. La identidad por contenido no distingue entre las dos (V3-30). La identidad del lote tiene que identificar **la operación**. El contenido se verifica aparte, con el digest completo.

### 2.3 Alternativas comparadas

Criterios, en orden de importancia para un ledger: (1) correctitud ante contenido repetido legítimo; (2) idempotencia del reintento aunque el cliente pierda su estado; (3) qué pasa ante una colisión; (4) dependencia de primitivas débiles; (5) aislamiento entre productores; (6) complejidad.

| | (1) Contenido repetido legítimo | (2) Reintento sin estado del cliente | (3) Colisión | (4) Primitivas | (5) Aislamiento entre productores | (6) Complejidad |
|---|---|---|---|---|---|---|
| **A.** v3.1: `UUIDv5(digest)` | **Falla** (V3-30) | Sí | `BatchConflict`; el contenido legítimo no se puede publicar | SHA-1 truncado a 122 bits | No: un productor puede «ocupar» el `batch_id` de un contenido de otro productor | Baja |
| **B.** El digest SHA-256 completo como clave | **Falla** (V3-30) | Sí | Solo por colisión de SHA-256 | SHA-256 | No | Baja |
| **C.** UUIDv4 aleatorio del cliente | Correcto | **No**: si el cliente pierde el UUID antes de confirmar, repite la operación con otro y publica dos veces | Despreciable; la clave primaria la rechaza | Generador aleatorio del cliente | No | Baja |
| **D.** (`producer_id`, `idem_key`) único + `batch_id` generado por la base + digest completo comparado | Correcto, si el productor cumple §2.5 | Sí, si `idem_key` se deriva de datos duraderos (§2.5) | Misma clave con distinto digest → `conflict`, nada cambia; colisión de `idem_key` entre operaciones → conflicto detectado | SHA-256 | **Sí**: la clave es por productor | Media |
| **E.** `UUIDv5(descriptor de la operación)` + digest completo | Correcto, como D | Sí, como D | Como A, más la colisión del UUID | SHA-1 truncado | No, salvo que el espacio de nombres incluya al productor | Media |

**Recomendación: D.**
- Es la única que cumple los cinco primeros criterios a la vez. E tiene la misma semántica, pero añade SHA-1 y 122 bits sin ventaja.
- A y B se descartan por (1), un fallo de integridad.
- C se descarta por (2), que es el objetivo de DV3-13.

Se recomienda por esos criterios, no por preferencia.

Estado: **Propuesta** (DV3-16 en `I1_CHANGELOG_V3_2.md` §5). Sustituye la parte «`batch_id` determinista (UUIDv5 del digest)» de DV3-13. Si el propietario prefiere mantener UUIDv5, la alternativa admisible es E, y el texto de v3.1 debe corregirse en el sentido de §2.1.

### 2.4 Diseño D

| Elemento | Definición |
|---|---|
| `batch_id` | `bigint` generado por la base (`GENERATED ALWAYS AS IDENTITY`). Único por la clave primaria. **El cliente no lo elige** (sin privilegio de columna, TS-BATCH-ID-10). Los huecos en `batch_id` no importan: el número sin huecos es `write_seq` |
| `producer_id` | Productor lógico, **derivado por la base** del rol de la sesión (§5). Nunca lo envía el cliente como dato de autorización |
| `idem_key` | 32 bytes = SHA-256(MRC-1(`"mr.op.v1"`, `producer_id`, descriptor de la operación)) (§3.3). Lo calcula el productor |
| Restricción | `UNIQUE (producer_id, idem_key)` |
| `batch_digest`, `semantic_digest` | 32 bytes cada uno (§3.4); se comparan **completos**, byte a byte |
| `digest_format` | Versión del contrato de digest (1 en v3.2) |

En v3.2, `write_log.batch_id` es `bigint UNIQUE NOT NULL` con clave foránea a `mr.batches`.

### 2.5 Obligaciones del productor sobre `idem_key`

1. Una **operación lógica** tiene una sola `idem_key` en todos sus reintentos.
2. Dos operaciones lógicas distintas **nunca** comparten `idem_key`, aunque su contenido sea idéntico.
3. El descriptor se deriva de datos duraderos del productor, para poder recalcularlo tras perder el estado en memoria.
   - **Ingesta:** (`provider_id`, huella de la petición, `body_sha256` del cuerpo recibido, hora de recepción en microsegundos). La hora de recepción se registra al recibir y se guarda junto al cuerpo.
   - **Registro:** id del cambio de configuración.
   - **Pruebas:** id del caso y número de operación.
4. Si el productor perdió el cuerpo y vuelve a pedirlo al proveedor, eso es **una observación nueva**, con `idem_key` nueva. Su publicación crea una versión. Si nada cambió, la versión no tiene filas nuevas (comportamiento de v3 §6). Esto **no** es un duplicado: es una observación más, y queda registrada.

La base **no puede verificar** que un productor cumpla 1–3. Si reutiliza una `idem_key` para otra operación con contenido idéntico, la base la trata como reintento. Es el riesgo residual RR-01 (`I1_CHANGELOG_V3_2.md` §7). Se mitiga con la regla 3 y con las pruebas de contrato del productor sintético (TS-BATCH-ID-04).

### 2.6 Comportamiento ante conflictos

`mr.open_batch` (§7) busca (`producer_id`, `idem_key`):

| Encuentra | Digest declarado | Resultado | Efecto |
|---|---|---|---|
| Nada | — | `('opened', batch_id, NULL)` | Crea el lote en `open` |
| Lote `published` | Igual (los dos digests, completos) | `('published', batch_id, write_seq)` | Ninguno. Es un reintento |
| Lote `sealed` | Igual | `('sealed', batch_id, NULL)` | Ninguno. El cliente llama a `publish` |
| Lote `expired` | Igual | `('reopened', batch_id, NULL)` | Pasa a `open` en esta transacción (§4.4) |
| Cualquier lote | **Distinto** en cualquier byte de `batch_digest` o de `semantic_digest`, o distinto `kind`, `namespace`, `digest_format` o versión de esquema | `('conflict', batch_id, NULL)` | **Ningún cambio en el lote existente.** Inserta un evento `batch_conflict` en `ops_events` con los dos digests y el rol. No lanza excepción, para que el evento se conserve (V3-33) |

Garantías:
- Un conflicto **nunca** reutiliza el lote existente (el cliente no puede preparar filas en él: no está `open` en su transacción, `MRB07`).
- Un conflicto **nunca** lo modifica: la rama de conflicto solo lee el lote y escribe en `ops_events`.
- Un cliente que ignore `conflict` y siga adelante recibe `MRB07` al preparar y `MRB02` al publicar.

### 2.7 Colisiones, reintentos y concurrencia

| Caso | Comportamiento |
|---|---|
| Colisión de `idem_key` entre dos operaciones de un mismo productor con contenido distinto (SHA-256 o error del productor) | `conflict`. La segunda operación no se publica con esa clave. El productor la registra como error y no la reintenta con la misma clave. Probabilidad accidental ≈ *n*²/2²⁵⁷ |
| Colisión de `batch_id` | Imposible: lo asigna una identidad de la base |
| Reintento con el estado del cliente perdido | Recalcula `idem_key` (§2.5.3) → `published` o `sealed` o `reopened` |
| Dos escritores, misma clave y mismo digest, a la vez | El segundo `INSERT … ON CONFLICT` espera a que la transacción del primero termine (DOC). Si el primero confirma, el segundo ve `published` o `sealed`. Si se deshace, el segundo abre (TS-IDEM-05) |
| Dos escritores, misma clave y digest distinto, a la vez | Igual, pero el segundo obtiene `conflict` si el primero confirmó, u `opened` si el primero se deshizo (TS-BATCH-ID-07) |
| Dos productores, misma clave | Lotes independientes: la clave es por productor (TS-BATCH-ID-08) |

## 3. MR-02 · Contenido del lote y digest canónico (contrato MRC-1)

### 3.1 Qué es el contenido de un lote

Cada dato que pasa por un lote cae en una de tres clases:

| Clase | Definición | ¿Entra en el digest? |
|---|---|---|
| **Semántico** | Cambia el significado de la información: con otro valor, el dato dice algo distinto del mundo | Sí: `semantic_digest` y `batch_digest` |
| **Procedencia publicada** | No cambia el significado, pero se escribe en las tablas versionadas y queda en la historia (de dónde viene, con qué licencia, con qué versión de adaptador) | Solo `batch_digest` |
| **Operativo** | No se publica, o lo asigna el servidor al publicar, o describe el proceso y no el dato | **No** |

- `semantic_digest` responde a «¿es la misma información?».
- `batch_digest` responde a «¿es exactamente lo que se va a escribir?». Es el que se verifica al sellar y el que decide un conflicto.

Tener dos digests evita una contradicción. Si la procedencia quedara fuera del único digest, se podría sellar un lote y publicar con una procedencia distinta de la declarada. Si entrara en el único digest, «misma información» dejaría de dar el mismo digest cuando cambia solo la procedencia.

### 3.2 Campos de un registro de vela

| Campo | Clase | Justificación |
|---|---|---|
| `instrument_id` | Semántico | Fija activo, bolsa, moneda de cotización, unidad, tipo y dominio de precio (atributos definitorios e **inmutables**, `I1_TEMPORAL_MODEL.md` §3). BTC/USDT y BTC/USD son instrumentos distintos |
| `provider_id` | Semántico | Dos proveedores son dos observaciones distintas; forma parte de la clave de la vela (`I1_TEMPORAL_MODEL.md` §3) |
| `timeframe` | Semántico | H1 y D1 con los mismos números no son la misma información |
| `bar_start`, `bar_end` | Semántico | Intervalo válido |
| `price_kind` | Semántico | `trade`, `bid`, `mid`… |
| `price_basis`, `adjustment_version` | Semántico | Precio sin ajustar frente a ajustado |
| `open`, `high`, `low`, `close` | Semántico | |
| `volume`, `volume_kind` | Semántico | El volumen en unidades base y en cotización son magnitudes distintas |
| `trade_count` | Semántico | Dato del mercado; nulo permitido |
| `session_kind`, `is_closed` | Semántico | Una vela parcial no equivale a una cerrada |
| `source_ts` | Procedencia | Hora del proveedor; no cambia el precio |
| `body_sha256` del cuerpo crudo + `locator` | Procedencia | Referencia **por contenido**. **No** se usa `payload_id`: si fuera aleatorio en el cliente, dos reintentos tendrían digests distintos (V3-39) |
| `license_id` | Procedencia | Gobierna el uso, no el significado |
| `adapter_version` | Procedencia | |
| `quality_status`, `canonical_sha256` | Operativo (derivado) | Lo calcula el servidor al publicar |
| `write_seq`, `superseded_seq`, `published_at`, `staged_by`, `opened_at`, `xid` | Operativo | Los asigna el servidor |
| `application_name`, PID, reintentos, latencia | Operativo | Describen el proceso, no el dato |

### 3.3 Qué identidad va en la cabecera y qué va en el registro

| Candidato | Dónde | Por qué |
|---|---|---|
| Separación de dominio | Cabecera: cadena `"mr.batch.v1"` | Un digest de lote no puede coincidir por construcción con un `idem_key`, un `entry_hash` o un hash de vela, porque cada uno empieza con una etiqueta distinta |
| Versión del formato (`digest_format`) | Cabecera | Cambiar la codificación cambia la etiqueta y la versión. Los digests de versiones distintas nunca se comparan entre sí |
| Tipo de lote (`kind`) | Cabecera | Los mismos bytes en un lote `candles` y en uno `registry` son operaciones distintas |
| Versión del esquema del tipo (`kind_schema_version`) | Cabecera | La lista y el orden de campos del registro dependen de ella |
| `namespace` | Cabecera | `real` frente a `synthetic`. Un lote no mezcla espacios de nombres: los instrumentos de un lote deben ser de su `namespace` |
| Modo de orden (`set` / `sequence`) | Cabecera | Lo fija el tipo; se incluye para que un error de configuración cambie el digest |
| Número de registros | Cabecera | Robustez frente a truncamientos |
| Instrumento, proveedor, temporalidad | **Registro** | Un lote puede contener varias series |
| Mercado | **No** | Se deriva del instrumento, cuyo vínculo con el mercado es inmutable. Incluirlo sería redundante |
| Productor | **No** | Es **quién**, no **qué**. Forma parte de la identidad del lote (§2.4) y de la auditoría (§5), no del contenido. La misma información enviada por dos productores es la misma información |
| Versión de contrato del productor o adaptador | Procedencia (`adapter_version`) | No cambia el significado si el canónico es igual |

**Limitación:** `instrument_id` es un UUID de cada instancia, así que el mismo dato en dos instancias da digests distintos. El digest se garantiza reproducible **dentro de una instancia**, entre Python y PostgreSQL. La comparación entre instancias usa el hash de vela `c3` (§3.8), que copia `quote_ccy` y `price_unit`, como hacía `c2`.

### 3.4 Codificación MRC-1

MRC-1 es una codificación binaria **inyectiva** (dos estructuras distintas dan siempre bytes distintos). Esto se demuestra por construcción: cada valor lleva su marca de presencia y su longitud, de modo que existe un decodificador sin ambigüedad. **No** se usa JSON: el orden de claves, los números y los nulos son ambiguos entre implementaciones, y RFC 8785 (JCS) representa los números como IEEE-754 doble, lo que pierde precisión decimal.

| Tipo | Codificación |
|---|---|
| Nulo | Byte `0x00` |
| Presente | Byte `0x01` seguido del valor |
| Entero | 8 bytes con signo, big-endian |
| Booleano | `0x00` / `0x01` |
| Texto | Longitud en 4 bytes big-endian + bytes UTF-8. Los campos de identidad (`provider_id`, códigos, enumeraciones) solo admiten ASCII `[a-z0-9._-]` y se **rechazan**, no se normalizan, si no cumplen. El texto libre (nombres en lotes de registro) debe estar en NFC; si no lo está, se rechaza en Python (`unicodedata.is_normalized`) y en PostgreSQL (`IS NFC NORMALIZED`). Se valida y no se normaliza para que una diferencia de versión de Unicode entre Python y PostgreSQL produzca un rechazo, nunca dos digests distintos (INF) |
| Decimal | Forma textual canónica, codificada como texto. Sin exponente; sin `+`; sin ceros a la izquierda salvo un `0` antes del punto; sin ceros finales en la parte fraccionaria ni punto final; `-0` → `0`. `NaN` e `±Infinity` se rechazan. En Python: a partir de signo, dígitos y exponente de `Decimal`, no con `str()` ni `normalize()`, que pueden producir exponentes. En PostgreSQL: `trim_scale()` (desde PG13, DOC) y salida textual de `numeric`, que no usa notación exponencial (DOC; se comprueba en TS-BATCH-DIGEST-10) |
| Instante | Microsegundos desde 1970-01-01 UTC, entero de 8 bytes. Python exige `datetime` con zona (los ingenuos se rechazan) y calcula con enteros, nunca con `float`. PostgreSQL usa `extract(epoch …)`, que desde PG14 devuelve `numeric` exacto (DOC), multiplicado por 10⁶. Los valores `±infinity` se rechazan. Resolución: microsegundo, la de `timestamptz` (DOC) |
| UUID | 16 bytes |
| Bytes (digests) | Longitud en 4 bytes + bytes |
| Registro | Longitud en 4 bytes + los campos en el orden fijo de su `kind_schema_version` |

Separación de dominio: toda cadena que se pasa a SHA-256 empieza por una **etiqueta** MRC-1 de texto: `"mr.batch.v1"`, `"mr.rec.v1"`, `"mr.op.v1"`, `"mr.c3"` o `"mr.chain.v2"`.

### 3.5 Estructura del digest

Se calcula en dos niveles para que PostgreSQL no tenga que construir en memoria una cadena del tamaño del lote. Los valores `bytea` tienen un tope de 1 GB por campo (DOC). Este problema de v3.1 lo encontró la auditoría (V3-48).

1. Por cada registro: `rec_sem = SHA-256(MRC-1("mr.rec.v1", "sem", kind, kind_schema_version, campos semánticos))` y `rec_prov = SHA-256(MRC-1("mr.rec.v1", "prov", campos de procedencia))`.
2. **Clave de orden:** los bytes MRC-1 de la clave de negocio del registro. Para velas son (`instrument_id`, `provider_id`, `timeframe`, `price_basis`, `bar_start`).
3. `semantic_digest = SHA-256(MRC-1("mr.batch.v1", "sem", digest_format, kind, kind_schema_version, namespace, modo de orden, número de registros) ‖ rec_sem₁ ‖ … ‖ rec_semₙ)`.
4. `batch_digest = SHA-256(MRC-1("mr.batch.v1", "full", semantic_digest) ‖ rec_prov₁ ‖ … ‖ rec_provₙ)`. Los `rec_prov` van en el mismo orden que en el paso 3.

Las partes concatenadas tienen longitud fija (32 bytes), así que la concatenación es inyectiva. La memoria es de 32 bytes por registro.

### 3.6 Orden canónico y duplicados

| Modo | Tipos de lote en I-1 | Orden | Duplicados |
|---|---|---|---|
| `set` | `candles`, `sources`, `purge` | Ascendente por los **bytes** de la clave de orden: comparación de `bytea` en PostgreSQL, que es byte a byte (DOC), y de `bytes` en Python. **Nunca** por texto con intercalación (*collation*), que depende de la configuración regional | Dos registros con la misma clave de negocio: el lote se **rechaza** (`MRB08`), sean iguales o distintos. No se deduplica en silencio |
| `sequence` | `registry`: operaciones que se aplican en orden, como cerrar una vigencia y abrir otra sobre la misma clave | El orden de entrada. Cada registro lleva su índice, que entra en `rec_sem` | Permitidos: el índice los distingue |

### 3.7 Reproducibilidad entre Python y PostgreSQL

- Python calcula los dos digests al **declarar** el lote. PostgreSQL los recalcula en `seal_batch` sobre las filas preparadas y exige igualdad completa (`MRB06`).
- Hay **dos implementaciones independientes**. Las pruebas exigen igualdad sobre vectores fijos y sobre 10 000 lotes aleatorios con semilla registrada (TS-BATCH-DIGEST-17).
- Los vectores con sus valores hexadecimales se generan y congelan **en M1**. Hoy no existe ninguno, porque esta tarea no permite ejecutar.
- Las funciones de PostgreSQL usadas son nativas de PG16 (DOC): `sha256(bytea)`, `int8send`, `uuid_send`, `convert_to(…, 'UTF8')`, `trim_scale`, `extract`. Que la composición dé exactamente los mismos bytes que Python es **INF** hasta M1.

### 3.8 Hashes derivados

| Hash | v3.2 |
|---|---|
| `c3` (vela) | `SHA-256(MRC-1("mr.c3", namespace, provider_id, instrument_id, timeframe, bar_start, bar_end, price_kind, price_basis, adjustment_version, quote_ccy, price_unit, open, high, low, close, volume, volume_kind, trade_count, session_kind, is_closed))`. Sustituye a `c2`, que con `\|` como separador y los nulos como cadena vacía es ambiguo (V3-31). Ejemplo: `adjustment_version` nulo y `''` dan el mismo hash. `canonical_version = 'c3'` |
| `entry_hash` (cadena de `write_log`) | `SHA-256(MRC-1("mr.chain.v2", write_seq, batch_id, producer_id, published_by_role_oid, batch_digest, prev_hash))`. Añade el productor y el rol, de modo que alterar la auditoría rompe la cadena (V3-40) |

### 3.9 Evolución del formato

1. Un cambio de codificación, de campos o de orden exige `digest_format` nuevo **o** `kind_schema_version` nuevo, y la etiqueta cambia con él.
2. Los lotes históricos conservan su versión en `mr.batches`. La verificación usa la versión registrada, y **nunca** se recalculan ni reescriben digests antiguos.
3. Cada versión tiene sus vectores congelados. Cambiar el codificador sin cambiar la versión hace fallar TS-BATCH-DIGEST-18.
4. Una versión se retira solo cuando ningún lote `sealed` la usa. Los `published` la conservan para la verificación.

### 3.10 Lo que el digest no garantiza

- No hay prueba de ausencia de colisiones de SHA-256. Las pruebas demuestran que **los casos probados** se distinguen, no que todos los posibles lo hagan.
- No prueba que el contenido sea **verdadero**; solo que es el declarado.
- No es reproducible entre instancias (§3.3).

## 4. MR-03 · Publicación, limpieza y consulta concurrentes

### 4.1 Estados

```
                 open_batch                 seal_batch                publish
 (no existe) ──────────────▶ open ─────────────────────▶ sealed ───────────────────▶ published (terminal)
                               │                          │   ▲
                 rollback: el  │          expire_batches  │   │  open_batch (reapertura,
                 lote no existe│          (§4.4)          ▼   │  mismo digest) → open → seal
                               ▼                         expired
```

- `open` **nunca** se confirma (disparador diferido, v3.1), así que otra transacción no puede verlo.
- `published` es **terminal**: ninguna función lo cambia, y un disparador en `mr.batches` rechaza cualquier transición que no esté en el diagrama y cualquier `DELETE`.
- `expired` es una lápida: el lote se conserva y su preparación se borra.

Requisito de implementación (V3-34): el disparador diferido debe **volver a leer** el estado actual del lote por `batch_id` al confirmar. La fila `NEW` que recibe corresponde al momento de la inserción, cuando el lote estaba `open`.

### 4.2 Bloqueos de cada función

Todas las funciones son `SECURITY DEFINER` con `search_path = pg_catalog, pg_temp`. Todas llevan la cláusula `SET lock_timeout` **de la propia función** (DOC: la cláusula `SET` de `CREATE FUNCTION` se aplica al entrar en la función y se restaura al salir), para que la espera por bloqueos **dentro** de la función esté acotada aunque el cliente haya cambiado ese parámetro (V3-47). Corrección de la auditoría (V3-50): **no** se cuenta con `SET statement_timeout` en la función como cota de la propia llamada. Probablemente no afecta a la sentencia de nivel superior ya en curso, porque su temporizador se arma al empezar esa sentencia (INF). M1 lo comprueba.

| Función | Bloqueos, en este orden | Espera a | Nunca toma |
|---|---|---|---|
| `open_batch` | (a) entrada en el índice único (`producer_id`, `idem_key`): espera a la transacción en curso que insertó la misma clave (DOC); (b) si la fila existe: `FOR UPDATE` sobre esa fila | Transacción concurrente con la misma clave | `ledger_head` |
| Preparación (`INSERT` en `stage_*`) | Ninguno sobre el lote: el disparador `BEFORE INSERT` lee el lote, que está sin confirmar y es de esta transacción. La clave foránea toma `FOR KEY SHARE` sobre la fila del lote (DOC), de la propia transacción | — | `ledger_head` |
| `seal_batch` | Actualiza la fila del lote, de esta transacción | — | `ledger_head` |
| `publish` | (1) `FOR UPDATE` del lote; (2) `FOR UPDATE` de `ledger_head`; (3) filas de las tablas versionadas (con el bloqueo 2 ya tomado) | Lote (otro publicador o una limpieza); `ledger_head` (otro publicador) | — |
| `batch_status` | **Ninguno**: lectura MVCC sin `FOR …`. No bloquea ni es bloqueada por bloqueos de fila (DOC) | — | Todos |
| `expire_batches` (limpieza) | `FOR UPDATE SKIP LOCKED` de lotes candidatos en orden de `batch_id`, con `LIMIT` | **Nunca espera** por un lote: si está bloqueado, lo salta (DOC) | `ledger_head` |

**Invariante de guarda:** toda modificación de la fila de un lote o de sus filas de preparación exige tener antes el bloqueo de esa fila del lote. La única excepción es la transacción que lo abrió mientras sigue sin confirmar, porque nadie más puede verlo.

### 4.3 Qué estados ve cada transacción

| Quién observa | Puede ver |
|---|---|
| La transacción que abrió el lote | `open` (suyo), y después `sealed` y `published` dentro de la misma transacción |
| Cualquier otra transacción | Inexistente, `sealed`, `published` o `expired`. **Nunca** `open` |

Consecuencias:
- Publicar un lote que otra transacción tiene abierto y sin confirmar devuelve `MRB02 UnknownBatch`, porque no lo ve. No devuelve `BatchNotSealed` como decía v3.1 (V3-32).
- Insertar preparación en ese lote: el disparador `BEFORE INSERT` se ejecuta antes que la comprobación de clave foránea (los disparadores `BEFORE` de fila van antes que las restricciones; DOC) y rechaza con `MRB07 BatchNotOpenInThisTransaction`.
- `MRB03 BatchNotSealed` queda solo para la propia transacción que llama `publish` sobre su lote todavía `open`.

### 4.4 Contrato de limpieza

**Rol:** `mr_maintainer`, de grupo y NOLOGIN, con un rol con LOGIN propio para la tarea de mantenimiento (§5.2). Su único privilegio es `EXECUTE` en `mr.expire_batches`.

**`mr.expire_batches(ttl interval, max_batches int) → (expirados int)`**, en una transacción READ COMMITTED (se exige igual que en `publish`):

1. Selecciona hasta `max_batches` lotes con `status = 'sealed' AND sealed_at < now() − ttl`, ordenados por `batch_id`, con `FOR UPDATE SKIP LOCKED`. En READ COMMITTED, si una fila cambió y se confirmó entre la instantánea y el bloqueo, la condición se reevalúa sobre la versión nueva (DOC). Un lote recién publicado deja de cumplir `status = 'sealed'` y no se toca.
2. Para cada lote bloqueado:
   - revalida el estado y la edad;
   - borra sus filas de `stage_*`;
   - `UPDATE status = 'expired', expired_at = now()`;
   - inserta un evento `batch_expired` en `ops_events` con `batch_id`, productor, digests, edad, número de filas borradas y rol de mantenimiento.
3. Devuelve el número de lotes expirados.

`ttl` tiene un **mínimo** fijado en la función (24 h en I-1, como v3/v3.1; SUP). Debe superar la ventana máxima de reintento de un productor.

| Propiedad | Cómo se consigue |
|---|---|
| Nunca borra un lote en publicación | `publish` tiene el bloqueo de la fila → `SKIP LOCKED` lo salta |
| Nunca borra un lote publicado | Filtro y revalidación de `status = 'sealed'`; `published` es terminal; el disparador prohíbe `DELETE` en `batches` |
| Nunca deja una referencia huérfana en `write_log` | Las filas de `batches` **no se borran nunca** (lápida); `write_log.batch_id` tiene clave foránea `RESTRICT` |
| Nunca expira solo por antigüedad | Filtro + bloqueo + revalidación |
| Idempotente | Una segunda ejecución no encuentra `sealed` antiguos; no duplica eventos |
| Interrupción a mitad | La transacción se deshace entera: el lote sigue `sealed`, con toda su preparación (DOC: atomicidad) |
| Auditable | Un evento por lote expirado, en la misma transacción que la expiración |
| Sin interbloqueos con `publish` | Nunca espera por un lote y nunca toma `ledger_head` (§4.5) |

**Reapertura:** `open_batch` sobre un lote `expired` con la misma clave y los mismos digests lo pasa a `open` en la transacción que llama (nuevo `opened_xid`, `reopen_count + 1`, evento `batch_reopened`). Con digests distintos devuelve `conflict`. Así, un reintento posterior a la expiración sigue siendo idempotente, siempre que el productor conserve el contenido.

### 4.5 Ausencia de interbloqueos (argumento)

Los recursos son las filas de lote (B) y la fila de `ledger_head` (L).

1. Toda función que toma L ya tiene B. Ninguna toma B después de L.
2. Solo `publish` toma L.
3. La limpieza toma varios B, pero **sin esperar** (`SKIP LOCKED`).
4. Varios lotes en una transacción (publicación múltiple, futura) se bloquean en orden ascendente de `batch_id`.
5. Las filas de las tablas versionadas solo se bloquean con L ya tomado, así que los publicadores se serializan en L.

Con un orden total y sin esperas en sentido contrario no hay ciclo (INF: argumento estándar de orden de adquisición).

**Excepción conocida:** una transacción que abre dos lotes nuevos en orden distinto al de otra transacción puede interbloquearse en el índice único. PostgreSQL lo detecta y aborta una de las dos (DOC), lo que es seguro pero no idempotente. Regla: un lote por transacción en I-1, o claves en orden ascendente (TS-IDEM-12). Riesgo residual RR-04.

### 4.6 Intercalados concurrentes

| # | Intercalado | Resultado esperado | Prueba |
|---|---|---|---|
| 1 | P (publish) bloquea el lote → L (limpieza) llega | L salta el lote; P publica; la siguiente limpieza no lo selecciona | TS-CLEANUP-04 |
| 2 | L bloquea el lote → P llega | P espera (acotado por `lock_timeout` de la función); L expira y confirma; P ve `expired` → `MRB04 BatchExpired`, sin tocar `ledger_head` (contador sin cambios) | TS-CLEANUP-05 |
| 3 | L bloquea; P espera; L se deshace | P obtiene el lote `sealed` y publica | TS-CLEANUP-07 |
| 4 | L borra la preparación y su conexión se termina antes de confirmar | El lote sigue `sealed` con todas sus filas; el digest recalculado coincide | TS-CLEANUP-07 |
| 5 | S (`batch_status`) durante una L en curso | S devuelve `sealed` (sin esperar); tras confirmar L, `expired` | TS-CLEANUP-06 |
| 6 | S durante una P en curso | S devuelve `sealed`; tras confirmar P, `published, s` | TS-CLEANUP-06 |
| 7 | El cliente decide con una S ya caducada: vio `sealed` y llama `publish` mientras otro publicó | `publish` espera, revalida y devuelve el `s` original | TS-IDEM-02 |
| 8 | El cliente vio «no existe» y repite `open_batch` mientras el `COMMIT` original seguía en curso | `ON CONFLICT` espera; tras el `COMMIT`, `('published', s)` | TS-CLEANUP-10 |
| 9 | `COMMIT` de resultado desconocido; mientras tanto el lote expiró | S → `expired` → `open_batch` (reapertura) → `seal` → `publish` → una sola versión | TS-CLEANUP-10 |
| 10 | Dos limpiezas a la vez | Cada lote lo expira una sola; un evento por lote; sin esperas | TS-CLEANUP-11 |
| 11 | Dos publicadores del mismo lote | Uno publica; el otro devuelve el mismo `s` (v3.1) | TS-IDEM-02 |
| 12 | Conexión de P terminada a mitad | Rollback; el lote sigue `sealed`; el contador no avanza; otro P o una L posterior proceden | TS-IDEM-04, TS-CLEANUP-07 |
| 13 | Reapertura concurrente de un `expired` por dos clientes | El segundo espera por el bloqueo de la fila; luego ve `sealed` o `published` (si el primero selló o publicó y confirmó) o `expired` (si se deshizo) | TS-CLEANUP-09 |

`batch_status` es **orientativo**: su respuesta puede quedar caducada inmediatamente. El diseño garantiza que cualquier acción tomada sobre una respuesta caducada es segura:
- `published` es terminal;
- `sealed` lleva a `publish`, que revalida bajo bloqueo;
- «no existe» y `expired` llevan a `open_batch`, que espera o reabre bajo bloqueo.

### 4.7 Esperas acotadas: lo que se puede y lo que no se puede garantizar

| Espera | Cota | Fuente |
|---|---|---|
| Esperas por bloqueo dentro de `open_batch`, `publish` y `expire_batches` | `lock_timeout` de la cláusula `SET` de la función | DOC (cláusula `SET`). **INF:** que `lock_timeout` también corte la espera a una transacción en curso en `INSERT … ON CONFLICT` y en `FOR UPDATE`, que internamente son esperas por un bloqueo de transacción (V3-45). `statement_timeout` dentro de la función no cuenta como cota (V3-50). Ambos puntos se comprueban en M1 (TS-IDEM-16, TS-CLEANUP-13). Si fallan, se aplica la condición de parada 3 de `I1_CHANGELOG_V3_2.md` §8.5 |
| Un cliente que, **después** de `publish`, se queda inactivo sin confirmar y retiene el lote y `ledger_head` | **No acotable desde la base por el propio cliente**: `idle_in_transaction_session_timeout` lo puede desactivar el propio cliente con `SET` (DOC: contexto `user`) | V3-47 |

Mitigación propuesta para la segunda fila (DV3-20, opcional): un rol vigilante (`mr_watchdog`) miembro de `pg_signal_backend` (DOC: puede terminar sesiones de roles no superusuario). Ejecuta una función que termina las sesiones de `mr_writer` inactivas en transacción durante más de *N* segundos mientras retienen bloqueos de `mr.ledger_head` o `mr.batches`.
- En un clúster compartido, ese rol podría terminar sesiones de otras aplicaciones. Por eso, en I-1 se limita a la instancia `test`, y para I-2 se exige un clúster separado (decisión del propietario).
- Sin vigilante, el riesgo es de **disponibilidad**, no de integridad: el actor ya tiene credenciales de escritor (RR-05).

### 4.8 Invariantes comprobables (para todas las pruebas TS-CLEANUP)

- **C1:** todo `write_log.batch_id` existe en `batches` con `status = 'published'` y el mismo `write_seq`.
- **C2:** ningún lote `published` ni `expired` tiene filas de preparación.
- **C3:** todo lote `expired` tiene exactamente un evento `batch_expired` por expiración, y `reopen_count` coincide con sus eventos `batch_reopened`.
- **C4:** las invariantes I1–I4 de v3.1 (`I1_TEST_STRATEGY_V3_1.md` §1).

## 5. MR-04 · Identidad y autorización

### 5.1 Tres niveles

| Nivel | Qué es | Quién la establece | ¿Se puede falsificar desde el cliente? |
|---|---|---|---|
| 1. Rol de PostgreSQL | El rol con LOGIN autenticado: `session_user` | **PostgreSQL**. En I-1 con autenticación `peer` sobre socket Unix, el servidor obtiene el usuario del sistema operativo del proceso cliente a través del núcleo (DOC: `peer` solo en conexiones locales) y lo asigna a un rol con `pg_ident.conf` | No, para roles no superusuario. `session_user` no cambia con `SET ROLE`, y `SET SESSION AUTHORIZATION` exige superusuario (DOC) |
| 2. Servicio o proceso | El programa que se ejecuta con ese rol | Hoy, nadie de forma fiable. Señales que el servidor observa: PID del backend, hora de inicio de la sesión. Señales que pone el cliente: `application_name` | `application_name`: **sí**, cualquier cliente lo fija. El PID solo identifica la conexión, no el programa |
| 3. Productor lógico | La entidad responsable del contenido: «ingesta cripto del proveedor X», «fixtures de prueba» | **La base**, por vínculo rol → productor que administra `mr_owner` | No: se deriva del nivel 1 |

Ninguno de los tres niveles es una persona. `session_user` es un rol de servicio. En I-1 ninguna persona publica. Si en el futuro una persona publica a mano, tendrá su propio rol con LOGIN y su propio productor `manual:<persona>`, fuera del alcance de I-1.

### 5.2 Roles (cambios sobre v3 §2)

| Rol | LOGIN | Cambio en v3.2 |
|---|---|---|
| `mr_owner`, `mr_migrator`, `mr_reader`, `mr_test_fixtures` | Como en v3 | Sin cambios |
| `mr_writer` | **No** (pasa a rol de grupo) | Sigue teniendo los `EXECUTE` de v3.1 §8. Ya no se usa para conectarse |
| `mr_svc_<servicio>` (p. ej. `mr_svc_test_a`, `mr_svc_test_b` en I-1) | Sí | Uno por servicio. Miembro de `mr_writer` con `INHERIT TRUE, SET FALSE` (opciones de `GRANT` de PG16, DOC). No puede hacer `SET ROLE` a otro servicio |
| `mr_maintainer` + `mr_svc_maint` | No / Sí | `EXECUTE` en `mr.expire_batches` |
| `mr_watchdog` | Sí | Solo si se aprueba DV3-20; solo en instancia `test` en I-1 |

TS-PRIV (v3) actualiza su lista blanca con estos roles. TS-PRIV-01 añade el inventario de `pg_hba_file_rules` y `pg_ident_file_mappings` (vistas de PG16, DOC): la identidad de nivel 1 depende de esa configuración (V3-49). Atributos prohibidos para cualquier rol con LOGIN salvo el migrador (como en v3): `SUPERUSER`, `CREATEROLE`, `CREATEDB`, `BYPASSRLS`, `REPLICATION`.

### 5.3 Productores y vínculos

| Tabla (dueño `mr_owner`, sin privilegios para roles con LOGIN) | Contenido |
|---|---|
| `mr.producers` | `producer_id` (ASCII), `namespace`, `kinds` permitidos, estado (`active` / `disabled`) |
| `mr.producer_roles` | `role_oid` (único) → `producer_id`. Varios roles pueden servir a un productor (dos procesos del mismo servicio con credenciales separadas); un rol sirve a un solo productor |

Los cambios en estas tablas solo los hace `mr_owner` (migración o función de administración) y cada cambio deja un evento en `ops_events`. Si un rol se borra y se crea de nuevo, recibe otro OID y pierde el vínculo; en ese caso el sistema **falla cerrado**.

En cada función:
1. Se resuelve el productor desde el OID de `session_user`. Si no hay vínculo activo → `MRI01 NotAProducer`.
2. Se comprueban `kind` y `namespace` contra el productor (`MRI02`, `MRI03`).
3. `open_batch`, `seal_batch`, `publish` y `batch_status` solo operan sobre lotes de **su** productor. Un lote de otro productor se trata como inexistente (`MRB02`), sin dar pistas de que existe. Esto concreta TS-ADV-19/20 de v3.1 (V3-46).

### 5.4 Qué identidad suministra y en cuál confía cada parte

| Identidad | ¿La envía el cliente? | ¿Autoriza? | ¿Se audita? |
|---|---|---|---|
| Rol (`session_user`, OID y nombre) | No (la autentica el servidor) | **Sí** (privilegios + vínculo) | Sí |
| Productor | No (se deriva). Si una API futura lo recibiera, solo se comprobaría que coincide con el derivado | **Sí** (alcance de claves y lotes) | Sí |
| `idem_key`, digests | Sí | No: son datos, no credenciales | Sí |
| `application_name`, nombre de host, versión del cliente | Sí | **Nunca** | Sí, en la columna `client_context_untrusted`, marcada como no fiable |
| PID del backend, hora de inicio de la sesión | No (los observa el servidor) | No | Sí: distinguen conexiones con credenciales compartidas |

### 5.5 Credenciales compartidas

Si dos procesos usan el mismo rol, PostgreSQL **no puede distinguirlos**: autorización idéntica, auditoría distinguible solo por PID y hora de sesión. Regla de I-1: **un rol por servicio**, sin compartir credenciales entre servicios. Con `peer`, cada servicio corre con su propio usuario de sistema. TS-IDENTITY-09 documenta y comprueba esta limitación, no la oculta.

### 5.6 Auditoría

| Dónde | Columnas (las pone el servidor) |
|---|---|
| `mr.batches` | `producer_id`; `opened_by_role_oid`, `opened_by_rolname`; `opened_backend_pid`, `opened_backend_start`; `sealed_by_role_oid`; `client_context_untrusted` |
| `mr.write_log` | `producer_id`; `published_by_role_oid`, `published_by_rolname`; `published_backend_pid`, `published_backend_start`; `client_context_untrusted`. Productor y rol entran en `entry_hash` (§3.8) |
| `mr.ops_events` | Conflictos, expiraciones, reaperturas y cambios de vínculos, con rol y productor |

Se guardan OID **y** nombre: un rol se puede renombrar (`ALTER ROLE … RENAME`, DOC). El OID identifica el rol y el nombre conserva lo que se veía en ese momento.

## 6. MR-05 · GitHub Actions y cadena de suministro

DV3-14 y DV3-15 de v3.1 **se mantienen**:
- solo `pull_request`, sin `pull_request_target`, `workflow_run` ni `workflow_dispatch`;
- sin despliegues, secretos ni permisos de escritura;
- solo ejecutores alojados por GitHub, sin servicios externos y sin red durante las pruebas;
- acciones fijadas por SHA completo y `persist-credentials: false`;
- un único archivo `.github/workflows/market-radar-i1.yml`, y solo si DP-03 = Sí.

Esta sección analiza lo que v3.1 no trataba.

### 6.1 Principio

Toda PR ejecuta **código que controla su autor**, incluidas las pruebas y el propio archivo del flujo. Con `pull_request`, GitHub usa el flujo de la versión fusionada de la PR (DOC-GH). Por tanto:
- Un ejecutor efímero **no** hace segura una PR externa. Limita lo que persiste, no lo que el código hace mientras corre.
- Las comprobaciones TS-CI-SEC que corren en la PR son **controles de regresión** para PRs propias. **No** son controles contra una PR maliciosa, que puede modificarlas (V3-35).
- La defensa frente a PRs externas está en **lo que el trabajo no tiene**: secretos y permisos de escritura. También está en la **configuración del repositorio**, que solo puede cambiar el propietario.

### 6.2 Análisis de los doce puntos

| # | Tema | Análisis | Control |
|---|---|---|---|
| 1 | Contribuciones externas | Una PR desde un fork ejecuta código arbitrario en el ejecutor, con token de solo lectura y sin secretos (DOC-GH). Puede consumir minutos, intentar exfiltrar lo que el trabajo vea (nada sensible: repositorio público, sin secretos) o modificar el flujo | Propietario: aprobación manual para todos los colaboradores externos (R-01). Flujo: nada sensible en el trabajo |
| 2 | Aislamiento entre trabajos y ejecuciones | Cada trabajo en un ejecutor alojado usa una máquina virtual nueva (DOC-GH). Entre ejecuciones solo persisten la caché y los artefactos | Flujo: **sin caché** (ni `actions/cache` ni `cache:` en `setup-python`); artefactos que ningún otro flujo consume (no hay `workflow_run`) |
| 3 | Permisos efectivos de `GITHUB_TOKEN` | Se **supone** que cualquier código del trabajo puede obtener el token: el código de la PR corre en la misma máquina, con `sudo` disponible en los ejecutores alojados (DOC-GH; INF). Por eso solo importa qué permite el token. Con `permissions: {}` global y `contents: read` en el trabajo, en un repositorio público no da acceso a nada que no sea ya público. En PRs desde forks, el token es de solo lectura siempre (DOC-GH) | Flujo: permisos mínimos. Propietario: permisos por defecto de flujos en «solo lectura» (R-02) y sin permitir que Actions cree o apruebe PRs (R-03) |
| 4 | Dependencias transitivas de las acciones | `actions/checkout`, `actions/setup-python` y `actions/upload-artifact` son acciones JavaScript que incluyen su código empaquetado en el commit (INF: estructura publicada de esas acciones), así que fijar el SHA fija ese código. **Pero** `setup-python` **descarga en tiempo de ejecución** el intérprete desde los repositorios de GitHub de versiones de Python, y eso no lo cubre el SHA (V3-38). Un SHA de un fork puede resolverse a través de la ruta del repositorio original («commit impostor», INF) | Flujo: lista blanca de SHA, cada uno asociado a la etiqueta oficial verificada al implementar. Residual: la descarga del intérprete, aceptada y documentada (RR-07). Alternativa: Python 3.12 del sistema (ubuntu-24.04 lo trae, SUP) y `setup-python` solo para 3.13 |
| 5 | Paquetes desde índices externos | La instalación desde PyPI depende del índice y de la red de distribución | Flujo: `pip install --require-hashes --only-binary :all:` desde un archivo de bloqueo con **todas** las dependencias transitivas (V3-37): `psycopg[binary]==3.3.9`, `psycopg-binary`, `typing-extensions` y las que resulten, SUP hasta verificarlo al implementar. El archivo vive en `tests/market_radar/ci/requirements-ci.lock`, dentro de las carpetas permitidas: DV3-15 no cambia. Sin compilar distribuciones fuente (no se ejecuta `setup.py`) |
| 6 | Verificación de hashes | `--require-hashes` rechaza cualquier archivo con otro hash y exige hash para cada dependencia (DOC de pip). Protege frente a la manipulación del índice; **no** frente a una versión maliciosa publicada antes de fijarla | Flujo: TS-CI-SEC-10 compara lo instalado con el bloqueo. Proceso: los hashes se toman de PyPI y se revisan en la PR |
| 7 | Artefactos y exposición de datos | En un repositorio público, los artefactos y los registros de ejecución son visibles para terceros (DOC-GH). I-1 no tiene secretos ni datos reales; aun así, nada de la base debe salir | Flujo: solo salida de pruebas e inventario de privilegios; sin `pg_dump` ni volcados; búsqueda de patrones de secreto antes de subir; nunca imprimir el entorno (`env`, `printenv`) |
| 8 | Retención de artefactos | Configurable por artefacto, con un máximo según el tipo de repositorio (DOC-GH) | Flujo: `retention-days: 7`. Propietario: retención por defecto del repositorio (R-07) |
| 9 | Contaminación de cachés | Una caché escrita por una ejecución puede restaurarse en otra. El vector clásico combina disparadores privilegiados y cachés compartidas (DOC-GH; INF) | Flujo: sin cachés de ningún tipo (TS-CI-SEC-09) |
| 10 | Instalación de PostgreSQL | Paquetes del archivo de Ubuntu 24.04 vía `apt`, que verifica firmas del repositorio (DOC de Debian/Ubuntu). La imagen del ejecutor puede traer PostgreSQL 16 preinstalado (SUP) | Flujo: se exige versión mayor 16 y se registra la versión exacta del paquete; `initdb` en un directorio temporal propiedad del usuario del ejecutor; `listen_addresses = ''`; directorio de sockets en modo 0700; autenticación `peer`; sin contraseñas |
| 11 | Espacio de red aislado | `sudo unshare --net` crea el espacio como root, y las pruebas **no deben** correr como root (V3-36): PostgreSQL rechaza ejecutarse como root (DOC), y root cambiaría la identidad `peer` (§5.1). Hace falta bajar privilegios dentro del espacio (`setpriv` o `sudo -u` al usuario del ejecutor). El servidor puede arrancarse fuera del espacio aislado: un socket Unix con ruta del sistema de archivos es accesible desde otro espacio de red (INF) | Flujo: las pruebas comprueban `id -u ≠ 0` y el fallo de la prueba de control de red (TS-CI-SEC-07). En Ubuntu 24.04 los espacios de nombres de usuario sin privilegios están restringidos por AppArmor (SUP), así que se usa `sudo` |
| 12 | Si `unshare --net` no está disponible | Alternativa 1: contenedor `docker run --network none` con imagen fijada por **digest**, descargada antes de aislar. Alternativa 2: ninguna | Si ninguna funciona, el trabajo **falla** (rojo) con un mensaje explícito. **Nunca** omite el aislamiento ni se pone verde sin él: sin `continue-on-error` ni `\|\| true` (TS-CI-SEC-14). La evidencia de red de A6 se aporta entonces en local y el propietario decide (DP-03) |

### 6.3 Clasificación de controles

| Tipo | Controles |
|---|---|
| **Implementables en el flujo** (TS-CI-SEC los comprueba como regresión) | Disparadores; `permissions`; sin secretos, `vars`, `environment` ni URLs de producción; acciones por SHA en lista blanca; `persist-credentials: false`; ejecutor `ubuntu-24.04` alojado; sin caché; dependencias con `--require-hashes` y bloqueo completo; PostgreSQL solo por socket; espacio de red aislado con bajada de privilegios y fallo explícito; artefactos limitados, revisados y con retención de 7 días; `timeout-minutes: 20`; `concurrency` por PR |
| **Configuración del repositorio** (solo el propietario; no los comprueba ninguna prueba del repositorio) | R-01 aprobación manual de flujos para **todos** los colaboradores externos · R-02 permisos por defecto de `GITHUB_TOKEN` de solo lectura · R-03 Actions no puede crear ni aprobar PRs · R-04 acciones permitidas limitadas a las de GitHub (`actions/*`) y, si la opción existe, exigir fijación por SHA (SUP) · R-05 reglas de protección en `release-2.1` y `main`, con revisión obligatoria de cambios en `.github/` (CODEOWNERS) · R-06 escaneo de secretos con protección al enviar, y alertas de dependencias · R-07 retención de artefactos y registros · R-08 no registrar ejecutores propios |
| **Supuestos pendientes de verificar** (en T15) | `sudo unshare --net` funciona en el ejecutor; Python 3.12 preinstalado; PostgreSQL 16 disponible; la lista exacta de dependencias transitivas de `psycopg[binary]==3.3.9` en Linux; SHA de las tres acciones; disponibilidad de la opción de R-04; el comportamiento de la descarga de `setup-python` |

### 6.4 Requisitos de seguridad del repositorio que v3.1 no cubría

`SECURITY_AND_PRIVACY_REQUIREMENTS.md` pide escaneo de secretos en CI (S-13, p. ej. gitleaks) y `pip-audit` en CI (S-64). Ambos necesitan red o dependencias nuevas, y eso choca con las restricciones de I-1 (V3-44). Propuesta:
- S-13 se cubre con R-06 (escaneo de secretos de GitHub, configuración del propietario) y con la búsqueda de patrones de A9, que no necesita red.
- S-64 se aplaza a I-2, con su propia decisión.

No se añaden herramientas al flujo de I-1.

## 7. Contratos de funciones (v3.2)

| Función | Entrada | Salida | Errores |
|---|---|---|---|
| `mr.open_batch` | `idem_key`, `kind`, `kind_schema_version`, `namespace`, `digest_format`, `batch_digest`, `semantic_digest` | (`status`, `batch_id`, `write_seq`), con `status` ∈ {`opened`, `published`, `sealed`, `reopened`, `conflict`} | MRI01–03, MRB09 |
| `mr.seal_batch` | `batch_id` | — | MRB02, MRB06, MRB07, MRB08, MRB09 |
| `mr.publish` | `batch_id` | `write_seq` | MRB02, MRB03, MRB04, MRB05, MRI01 |
| `mr.batch_status` | `batch_id` o (`idem_key`) | (`status`, `batch_id`, `write_seq`) o vacío | MRI01 |
| `mr.expire_batches` | `ttl`, `max_batches` | número de expirados | MRB05, MRB11 |

Catálogo de errores. Códigos SQLSTATE propios: cinco caracteres, clase `MR`, fuera de las clases estándar. Cada prueba comprueba el código exacto.

| Código | Nombre | Cuándo |
|---|---|---|
| MRB02 | `UnknownBatch` | No existe o es de otro productor |
| MRB03 | `BatchNotSealed` | La propia transacción publica su lote `open` |
| MRB04 | `BatchExpired` | Publicar un lote `expired` |
| MRB05 | `RequiresReadCommitted` | `publish` o `expire_batches` fuera de READ COMMITTED |
| MRB06 | `DigestMismatch` | Al sellar, las filas preparadas no dan los digests declarados |
| MRB07 | `BatchNotOpenInThisTransaction` | Preparar filas en un lote que no está `open` en esta transacción |
| MRB08 | `DuplicateRecordKey` | Clave de negocio repetida en un lote `set` |
| MRB09 | `InvalidCanonicalValue` | Valor no representable en MRC-1 (NaN, instante ingenuo o infinito, texto no ASCII en campo de identidad, NFC inválido, digest de longitud distinta de 32) |
| MRB10 | `OpenBatchAtCommit` | Disparador diferido |
| MRB11 | `TtlBelowMinimum` | `ttl` menor que el mínimo |
| MRI01 | `NotAProducer` | Rol sin vínculo activo |
| MRI02 | `KindNotAllowed` | Tipo de lote no permitido al productor |
| MRI03 | `NamespaceNotAllowed` | Espacio de nombres distinto del del productor |

`conflict` no es un error: es un resultado de `open_batch` (§2.6).

## 8. Privilegios v3.2

| Rol | Privilegios en el ledger |
|---|---|
| `mr_writer` (grupo) | `EXECUTE` en `open_batch`, `seal_batch`, `publish`, `batch_status`, `watermark`; `INSERT` en las columnas permitidas de `stage_*`. Ninguno sobre `batches`, `producers`, `producer_roles`, `write_log`, `ledger_head` ni sobre las tablas versionadas |
| `mr_maintainer` (grupo) | `EXECUTE` en `expire_batches`. Nada más |
| `mr_svc_*` | Solo la pertenencia a su grupo (`INHERIT TRUE, SET FALSE`) |
| `PUBLIC` | Nada (v3) |

## 9. Lo que sigue sin garantía

- Nada de este documento se ha ejecutado. Todo lo que dice de PostgreSQL es DOC o INF; todo lo que dice de GitHub es DOC-GH sin reverificar o SUP.
- La correctitud de las funciones `SECURITY DEFINER` depende de su implementación y de la revisión línea a línea (A8 de v3).
- La correcta derivación de `idem_key` depende del productor (RR-01).
- La retención maliciosa de bloqueos por un escritor es un riesgo de disponibilidad sin cota desde la base, salvo con DV3-20 (RR-05).
- Ninguna PR externa es «segura» por correr en un ejecutor efímero (§6.1).
- La lista completa de riesgos residuales está en `I1_CHANGELOG_V3_2.md` §7.
