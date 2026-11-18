# I-1 v3.2 · Estrategia de pruebas

Fecha: 18-nov-2026. **Amplía** `I1_TEST_STRATEGY_V3.md` y `I1_TEST_STRATEGY_V3_1.md`, que no se modifican y siguen vigentes: reglas generales, los 15 grupos de v3, TS-IDEM y los casos añadidos de TS-ADV. Diseño de referencia: `I1_LEDGER_REDESIGN_V3_2.md` (en este documento, «LEDGER §n»). Criterios: `I1_ACCEPTANCE_V3_2.md`. Hallazgos: `I1_CHANGELOG_V3_2.md`.

**Ninguna prueba existe ni se ha ejecutado. El estado de todas las pruebas de este documento es «Pendiente de ejecución».** Ningún resultado aquí descrito es un resultado observado: la columna «Esperado» es lo que la prueba debe comprobar.

## 1. Reglas que se añaden

1. Las de v3 y v3.1 siguen en vigor:
   - PostgreSQL 16 solo por socket Unix y en un espacio de red aislado;
   - Python 3.12 y 3.13 con `unittest`, sin dependencias nuevas;
   - comprobación del SQLSTATE exacto;
   - control negativo;
   - intercalados forzados con puntos de sincronización y 50 repeticiones aleatorias con semilla registrada;
   - invariantes I1–I4.
2. Toda prueba de concurrencia de TS-CLEANUP comprueba además las invariantes C1–C4 (LEDGER §4.8).
3. Los errores se comprueban por su **código propio** (LEDGER §7: `MRB02`…`MRB11`, `MRI01`…`MRI03`), no por el texto del mensaje.
4. Las pruebas de TS-BATCH-DIGEST se ejecutan **dos veces**: con el codificador de Python y con el de PostgreSQL. Ambos resultados deben ser idénticos.
5. Las pruebas de identidad usan **dos o más roles con LOGIN** (`mr_svc_test_a`, `mr_svc_test_b`) con autenticación `peer`, asignados a usuarios de sistema distintos en el arnés. Cuando el entorno no lo permita, se usa autenticación `trust` limitada al socket del arnés, y esa limitación se registra.
6. **Control negativo por grupo.** Cada grupo nuevo tiene una variante defectuosa que **debe** hacer fallar al menos una de sus pruebas. Si no falla, el grupo se considera inválido:

| Grupo | Variante defectuosa | Debe fallar en |
|---|---|---|
| TS-BATCH-ID | Identidad por contenido de v3.1 (`UUIDv5(digest)`) | TS-BATCH-ID-04 (el estado final queda en B) |
| TS-BATCH-DIGEST | Codificación `c2` con `\|` y nulos vacíos | TS-BATCH-DIGEST-11 y 16 |
| TS-CLEANUP | Limpieza por antigüedad sin bloqueo ni revalidación | TS-CLEANUP-05 (publicación sin filas o error de clave foránea) |
| TS-IDENTITY | Productor tomado de un argumento del cliente | TS-IDENTITY-01 |
| TS-CI-SEC | Flujo de ejemplo con `pull_request_target`, `permissions: write-all` y una acción por etiqueta | TS-CI-SEC-02, 03 y 05 |

## 2. Casos de v3.1 que cambian

Los resultados esperados de estos casos se precisan y **sustituyen** a los de v3.1. Los identificadores se conservan.

| Caso | v3.1 | v3.2 | Motivo |
|---|---|---|---|
| TS-ADV-15 | `BatchNotSealed` | `MRB02 UnknownBatch`: un lote abierto por otra transacción no es visible | V3-32 |
| TS-ADV-16 | Error del disparador (`opened_xid`) | `MRB07 BatchNotOpenInThisTransaction` (disparador `BEFORE INSERT`) | V3-32 |
| TS-ADV-19 | «Sin resultado» | Conjunto vacío, indistinguible del de un lote inexistente | V3-46 |
| TS-ADV-20 | «Devuelve error o nada» | `MRB02`; el contador no avanza; ningún evento atribuido al otro productor | V3-46 |
| TS-IDEM-10 | `BatchConflict` como error | Resultado `conflict` + evento `batch_conflict` conservado tras el `COMMIT` | V3-33 |
| TS-IDEM-15 | Mismo `batch_id` determinista (UUIDv5) desde dos procesos | Mismo (`producer_id`, `idem_key`) desde dos procesos del mismo productor → un solo lote y una publicación | V3-30 |
| TS-IDEM-16 | Espera acotada por `idle_in_transaction_session_timeout` | Se mantiene, y se añade una variante en la que el cliente pone ese parámetro a 0 (TS-CLEANUP-13). Además, debe registrar si `lock_timeout` corta la espera de `ON CONFLICT` (V3-45) y si `statement_timeout` en la cláusula `SET` de la función tiene efecto (V3-50) | V3-45, V3-47, V3-50 |
| TS-PRIV-01 | Inventario de privilegios por rol | Añade `pg_hba_file_rules` y `pg_ident_file_mappings` contra una lista blanca: solo socket local, `peer` y mapas uno a uno usuario de sistema → rol | V3-49 |

## 3. TS-BATCH-ID · Identidad del lote (MR-01)

**Estado de todas: Pendiente de ejecución.** Preparación común: base `test` nueva; productores `p_a` (rol `mr_svc_test_a`) y `p_b` (rol `mr_svc_test_b`), ambos `synthetic`, con tipo `candles`; codificador MRC-1 de Python. Evidencia común: salida completa y estado de `batches`, `write_log` y `ops_events` al final.

| Id | Objetivo | Preparación | Actor | Secuencia | Esperado | Error | Evidencia | Crit. |
|---|---|---|---|---|---|---|---|---|
| TS-BATCH-ID-01 | Reintento con la misma clave y el mismo digest | Lote L publicado con `s` | `p_a` | `open_batch(k, D)` otra vez | `('published', L, s)`; ninguna fila nueva en `batches` ni en `write_log` | — | Recuento antes y después | A16 |
| TS-BATCH-ID-02 | Misma clave, digest distinto | Como 01 | `p_a` | `open_batch(k, D′)`, con D′ ≠ D | `('conflict', L, NULL)`; L sin cambios (todas sus columnas iguales); un evento `batch_conflict` con D y D′, **presente tras el `COMMIT`** | — | Fila de L antes y después; evento | A16 |
| TS-BATCH-ID-03 | Colisión simulada del identificador con digest distinto | El arnés (como `mr_owner`, solo en la prueba) inserta un lote con clave k₁ y digest D₁ que **simula** una colisión: no se puede producir una colisión real de SHA-256 ni de UUIDv5 | `p_a` | `open_batch(k₁, D₂)` | `conflict`; ningún cambio en el lote existente; nada se prepara ni se publica con k₁ | `MRB07` si el cliente intenta preparar filas | Fila antes y después | A16 |
| TS-BATCH-ID-04 | Contenido repetido legítimo (A → B → A) | Vela X | `p_a` | Publica A (`k₁`), B (`k₂`) y otra vez A (`k₃`) | Tres versiones; el estado vigente final es A; en lectura (W, H), cada versión muestra su valor | — | `write_log`, lectura `_asof` en las tres marcas | A16 |
| TS-BATCH-ID-05 | Comparación del digest completo | Lote con D | `p_a` | `open_batch(k, D″)`, con D″ distinto de D solo en el **último** byte; repetir con diferencia solo en el primer byte y solo en `semantic_digest` | `conflict` en los tres casos | — | Salida | A16 |
| TS-BATCH-ID-06 | Longitud y formato de los digests | — | `p_a` | `open_batch` con digest de 31 y de 33 bytes, y con `digest_format = 99` | Rechazo | `MRB09` | SQLSTATE | A16 |
| TS-BATCH-ID-07 | Conflicto concurrente | Punto de sincronización tras el `INSERT` de A | `p_a` en dos sesiones | A abre `(k, D)` y espera; B abre `(k, D′)` y queda en espera; (i) A confirma; (ii) en otra ejecución, A se deshace | (i) B recibe `conflict`; (ii) B recibe `opened`, y después prepara, sella y publica | — | Intercalado, tiempos, 50 repeticiones | A16 |
| TS-BATCH-ID-08 | La clave es por productor | — | `p_a` y `p_b` | Ambos abren `(k, D)` con la misma clave y el mismo contenido | Dos lotes distintos y dos versiones; ningún conflicto | — | `batches`, `write_log` | A16 |
| TS-BATCH-ID-09 | Reintento con el estado perdido y expiración intermedia | Lote `sealed` (modo de dos transacciones) envejecido más allá del TTL y expirado | `p_a` | El cliente recalcula `k` desde sus datos duraderos; `open_batch` → `reopened`; prepara, sella y publica | Una sola versión; `reopen_count = 1`; I1–I4, C1–C4 | — | Eventos, invariantes | A16, A18 |
| TS-BATCH-ID-10 | El cliente no elige `batch_id` | — | `p_a` | `INSERT` directo en `mr.batches`; intento de pasar un `batch_id` a `open_batch` (no existe ese parámetro); `UPDATE batches SET batch_id` | `permission denied` / error de firma | 42501 / 42883 | SQLSTATE | A16 |

## 4. TS-BATCH-DIGEST · Digest canónico (MR-02)

**Estado de todas: Pendiente de ejecución.** Preparación común: instrumentos sintéticos `BTCUSDT` y `BTCUSD`, proveedores `prov_x` y `prov_y`, y el codificador de Python y el de PostgreSQL (`seal_batch` y, solo en la prueba, la función interna de digest). Evidencia común: los dos digests (hexadecimal) de cada implementación y su igualdad. Los vectores conceptuales de esta sección **no son** una demostración de ausencia de colisiones: demuestran que los casos probados se distinguen o coinciden como se espera.

Notación: «=» significa los mismos `semantic_digest` y `batch_digest`; «≠» significa distinto `semantic_digest` (y por tanto distinto `batch_digest`); «≠ₚ» significa igual `semantic_digest` y distinto `batch_digest`.

| Id | Objetivo | Vector (A frente a B) | Actor | Secuencia | Esperado | Error | Evidencia | Crit. |
|---|---|---|---|---|---|---|---|---|
| TS-BATCH-DIGEST-01 | El orden no importa en un lote `set` | Mismas 5 velas, en orden de entrada distinto | Python y PG | Calcular en ambos | = | — | Hex de los dos | A17 |
| TS-BATCH-DIGEST-02 | El orden importa en un lote `sequence` | Lote `registry`: «cerrar vigencia, abrir vigencia» frente al orden inverso | Python y PG | Calcular | ≠ | — | Hex | A17 |
| TS-BATCH-DIGEST-03 | Instrumento distinto | Mismos números en BTC/USDT y BTC/USD | Python y PG | Calcular | ≠ | — | Hex | A17 |
| TS-BATCH-DIGEST-04 | Tipo de volumen | `volume = 10` con `base_units` frente a `quote_notional` | Python y PG | Calcular | ≠ | — | Hex | A17 |
| TS-BATCH-DIGEST-05 | Base de precio | `raw` frente a `split_adjusted`; `adjustment_version` nulo frente a `"v1"` | Python y PG | Calcular | ≠ en ambos | — | Hex | A17 |
| TS-BATCH-DIGEST-06 | Espacio de nombres | Lote `real` frente a `synthetic`, con los mismos registros (instrumentos equivalentes en cada espacio) | Python y PG | Calcular; además, `seal` de un lote cuyo instrumento es de otro espacio | ≠; mezcla rechazada | `MRI03` | Hex, SQLSTATE | A17 |
| TS-BATCH-DIGEST-07 | Proveedor | `prov_x` frente a `prov_y` | Python y PG | Calcular | ≠ | — | Hex | A17 |
| TS-BATCH-DIGEST-08 | Temporalidad | H1 frente a D1 con el mismo `bar_start` y los mismos números | Python y PG | Calcular | ≠ | — | Hex | A17 |
| TS-BATCH-DIGEST-09 | Tipo de lote | Registros con los mismos bytes en `candles` frente a `sources` (forzado en la prueba) | Python y PG | Calcular | ≠ | — | Hex | A17 |
| TS-BATCH-DIGEST-10 | Decimales | `1.10` / `1.1` / `1.100` / `01.1` →=; `-0` / `0` / `0.000` →=; `1E-9` / `0.000000001` →=; `123456789012345678901234567890.123456789` sin pérdida; `100` frente a `1E+2` →= | Python y PG | Calcular; además, comprobar que la salida textual de PG no usa exponente | = donde se indica; la forma canónica es idéntica en ambos | — | Forma canónica y hex | A17 |
| TS-BATCH-DIGEST-11 | Nulos frente a vacíos | `volume` nulo con `none` frente a `0` con `base_units`; `adjustment_version` nulo frente a `""` | Python y PG | Calcular | ≠ en ambos (con `c2`, el segundo par daba =: control negativo) | — | Hex | A17 |
| TS-BATCH-DIGEST-12 | Instantes y zonas | El mismo instante dado como `+00:00` y como `-05:00` →=; resolución de microsegundo (`.000001` frente a `.000002` →≠); instante anterior a 1970; `datetime` sin zona; `infinity` | Python y PG | Calcular | = / ≠ como se indica; los dos últimos se rechazan | `MRB09` | Hex, SQLSTATE | A17 |
| TS-BATCH-DIGEST-13 | Versiones | Mismos registros con `kind_schema_version` 1 frente a 2, y con `digest_format` 1 frente a 2 (este último solo en la prueba) | Python y PG | Calcular | ≠ | — | Hex | A17 |
| TS-BATCH-DIGEST-14 | Duplicados | (a) Dos registros idénticos; (b) misma clave y distinto `close` | Python y PG | Declarar y sellar | Rechazo en ambos casos, en Python antes de enviar y en PG al sellar | `MRB08` | SQLSTATE | A17 |
| TS-BATCH-DIGEST-15 | Campos excluidos y procedencia | (a) Distinto `application_name`, hora de apertura, número de reintento o rol que prepara →=; (b) distinto `body_sha256` del cuerpo o `adapter_version` →≠ₚ | Python y PG | Calcular | (a) =; (b) ≠ₚ | — | Hex de los dos digests | A17 |
| TS-BATCH-DIGEST-16 | Codificación sin ambigüedad | (a) `provider_id` `"ab"` + `timeframe` `"c"` frente a `"a"` + `"bc"` (forzado en la prueba); (b) texto con `\|`; (c) texto no ASCII en un campo de identidad; (d) texto libre no NFC; (e) NUL en el texto | Python y PG | Calcular o declarar | (a) ≠ (con `c2` daba =: control negativo); (b) se rechaza por el dominio del campo; (c), (d) y (e) se rechazan | `MRB09` | Hex, SQLSTATE | A17 |
| TS-BATCH-DIGEST-17 | Equivalencia entre Python y PG | 10 000 lotes aleatorios (semilla registrada): 1–500 registros, decimales con 0–18 decimales, nulos y fechas de 1900 a 2100 | Python y PG | Calcular en ambos y comparar; además, sellar 200 de ellos y alterar una fila en otros 50 antes de sellar | 0 diferencias; 200 sellados correctamente; 50 rechazados | `MRB06` en los 50 | Semilla, recuento, diferencias | A17 |
| TS-BATCH-DIGEST-18 | Vectores congelados | Los hex de 01–16 se guardan en `tests/market_radar/` en M1 | Python y PG | Recalcular | Iguales a los guardados; cambiar el codificador sin cambiar la versión hace fallar la prueba | — | Diferencias | A17 |

## 5. TS-CLEANUP · Publicación, limpieza y estado (MR-03)

**Estado de todas: Pendiente de ejecución.** Preparación común: productor `p_a`; rol de mantenimiento `mr_svc_maint`; TTL mínimo de prueba configurable **solo** en la instancia `test` (p. ej. 2 s); envejecimiento simulado con `sealed_at` fijado por el arnés como `mr_owner`, solo en la prueba; puntos de sincronización deterministas. Evidencia común: intercalado, invariantes C1–C4 e I1–I4, eventos y 50 repeticiones aleatorias con semilla en las pruebas concurrentes.

| Id | Objetivo | Preparación | Actor | Secuencia | Esperado | Error | Evidencia | Crit. |
|---|---|---|---|---|---|---|---|---|
| TS-CLEANUP-01 | Expiración normal | Lote `sealed` envejecido | `mr_svc_maint` | `expire_batches(ttl, 10)` | 1 expirado; preparación borrada; `status = 'expired'`; 1 evento | — | Recuentos, evento | A18 |
| TS-CLEANUP-02 | No toca lotes recientes | Lote `sealed` recién sellado | `mr_svc_maint` | `expire_batches` | 0 expirados; preparación intacta | — | Recuentos | A18 |
| TS-CLEANUP-03 | No toca lotes publicados | Lote `published` envejecido | `mr_svc_maint` | `expire_batches` | 0 expirados; la versión es legible igual | — | Recuentos, lectura `_asof` | A18 |
| TS-CLEANUP-04 | Publicación primero | Lote `sealed` envejecido | `p_a`, `mr_svc_maint` | P bloquea el lote (sincronización) → L ejecuta → P confirma → L otra vez | L salta el lote (`SKIP LOCKED`) sin esperar más de 100 ms; P publica; la segunda L no lo selecciona | — | Intercalado, tiempos | A18 |
| TS-CLEANUP-05 | Limpieza primero | Ídem | `mr_svc_maint`, `p_a` | L bloquea → P llama `publish` y espera → L confirma | P recibe `MRB04`; `ledger_head` sin cambios; ninguna entrada en `write_log` | `MRB04` | Contador antes y después | A18 |
| TS-CLEANUP-06 | `batch_status` no se bloquea | Lote `sealed` | `p_a` (S), `mr_svc_maint` (L), `p_a` (P) | S durante una L en curso; S durante una P en curso | S responde en < 100 ms con `sealed` en ambos; tras confirmar, `expired` y `published, s` | — | Tiempos y respuestas | A18 |
| TS-CLEANUP-07 | Interrupción | Lote `sealed` envejecido | `mr_svc_maint` | L borra la preparación; se termina su conexión antes de confirmar (`pg_terminate_backend` desde el arnés); variante: P bloqueada detrás de L | El lote sigue `sealed` con todas sus filas; el digest recalculado es igual al declarado; la P bloqueada continúa y publica | — | Recuentos, digests | A18 |
| TS-CLEANUP-08 | Idempotencia | Tras 01 | `mr_svc_maint` | Ejecutar `expire_batches` dos veces más | 0 y 0; sin eventos duplicados | — | Recuentos | A18 |
| TS-CLEANUP-09 | Reapertura | Lote `expired` | `p_a` en dos sesiones | (a) Reabrir con el mismo digest, preparar, sellar y publicar; (b) reabrir con otro digest; (c) dos reaperturas concurrentes | (a) una versión, `reopen_count = 1`; (b) `conflict`; (c) la segunda espera y después ve el estado del primero | — | Intercalado | A18 |
| TS-CLEANUP-10 | `COMMIT` desconocido con limpieza | Modo de dos transacciones; corte tras enviar `COMMIT` de T2 (v3.1 TS-IDEM-08/09) | `p_a`, `mr_svc_maint` | Variantes: (i) el `COMMIT` se confirmó; (ii) no se confirmó y L expira el lote antes del reintento; (iii) el cliente ve «no existe» con un `COMMIT` original aún en curso y repite `open_batch` | (i) `published, s` y ninguna versión nueva; (ii) `expired` → reapertura → una versión; (iii) `open_batch` espera y devuelve `('published', s)` | — | Intercalado, invariantes | A18, A12 |
| TS-CLEANUP-11 | Limpiezas concurrentes | 50 lotes envejecidos | 2 × `mr_svc_maint` | Ejecución simultánea con `max_batches = 10`, repetida | Cada lote expira una vez; 50 eventos; sin `deadlock detected` | — | Eventos, registro del servidor | A18, A13 |
| TS-CLEANUP-12 | Sin huérfanos ni borrados | Estado tras 01–11 | `mr_owner` (sin desactivar disparadores), `mr_svc_maint`, `p_a` | `DELETE FROM mr.batches` como cada actor; consulta de C1–C4 | Owner: error del disparador; los demás: `permission denied`; C1–C4 se cumplen | Disparador / 42501 | SQLSTATE, consultas | A18 |
| TS-CLEANUP-13 | Retención maliciosa del bloqueo | El cliente ejecuta `SET idle_in_transaction_session_timeout = 0` y `SET lock_timeout = 0` | `p_a` (atacante), `p_a` (víctima) | El atacante llama `publish` y queda inactivo sin confirmar; la víctima llama `publish` sobre otro lote | La víctima recibe el error de `lock_timeout` de la **función** dentro de su cota (no espera indefinidamente). Con DV3-20 aprobada: el vigilante termina al atacante en ≤ *N* s y la víctima publica. Sin DV3-20: se registra que el atacante retiene el ledger (riesgo RR-05 demostrado) | 55P03 (`lock_not_available`) para la víctima | Tiempos, registro | A13, A18 |

## 6. TS-IDENTITY · Identidad y autorización (MR-04)

**Estado de todas: Pendiente de ejecución.** Preparación común: roles `mr_svc_test_a` → `p_a`, `mr_svc_test_b` → `p_b`, `mr_svc_test_a2` → `p_a` (segundo proceso del mismo productor) y `mr_svc_unbound` (miembro de `mr_writer`, sin vínculo). Evidencia común: SQLSTATE, filas de auditoría y verificación de la cadena.

| Id | Objetivo | Preparación | Actor | Secuencia | Esperado | Error | Evidencia | Crit. |
|---|---|---|---|---|---|---|---|---|
| TS-IDENTITY-01 | El productor no lo pone el cliente | — | `mr_svc_test_a` | `SET application_name = 'p_b'`; abre, sella y publica | El lote y la entrada de `write_log` son de `p_a`; `client_context_untrusted = 'p_b'`, marcado como no fiable | — | Filas | A19 |
| TS-IDENTITY-02 | Rol sin vínculo | — | `mr_svc_unbound` | `open_batch`, `publish`, `batch_status` | Rechazo | `MRI01` | SQLSTATE | A19 |
| TS-IDENTITY-03 | Sin cambio de rol a otro servicio | — | `mr_svc_test_a` | `SET ROLE mr_svc_test_b`; `SET ROLE mr_writer` | Ambos rechazados (sin pertenencia o con `SET FALSE`) | 42501 | SQLSTATE | A19 |
| TS-IDENTITY-04 | Aislamiento entre productores | Lote L de `p_b` | `mr_svc_test_a` | `publish(L)`, `seal_batch(L)`, `batch_status(L)` | `MRB02` en los dos primeros y vacío en el tercero, indistinguibles de un lote inexistente; L sin cambios | `MRB02` | SQLSTATE, fila | A19 |
| TS-IDENTITY-05 | Varios roles para un productor | — | `mr_svc_test_a` (T1), `mr_svc_test_a2` (T2) | T1: abre, prepara y sella; T2: publica | Permitido; `batches.opened_by_role` = a, `write_log.published_by_role` = a2, ambos con productor `p_a` | — | Filas | A19 |
| TS-IDENTITY-06 | Tipo no permitido | `p_a` solo con `candles` | `mr_svc_test_a` | `open_batch(kind = 'registry')` | Rechazo | `MRI02` | SQLSTATE | A19 |
| TS-IDENTITY-07 | Espacio de nombres | `p_a` es `synthetic` | `mr_svc_test_a` | `open_batch(namespace = 'real')` | Rechazo | `MRI03` | SQLSTATE | A19 |
| TS-IDENTITY-08 | Auditoría completa y protegida | 20 publicaciones de varios roles | `mr_owner` (solo en la prueba) | Comprobar las columnas de auditoría; alterar `producer_id` de una entrada (con el disparador desactivado como dueño); verificar la cadena | Todas las entradas con OID, nombre de rol, productor y PID; la verificación de la cadena falla en la entrada alterada | — | Consulta, verificación | A19 |
| TS-IDENTITY-09 | Credenciales compartidas (limitación) | Dos procesos con `mr_svc_test_a` | `mr_svc_test_a` × 2 | Ambos publican lotes distintos | Autorización idéntica; la auditoría solo los distingue por PID y hora de sesión. La prueba **documenta** esta limitación; no la presenta como garantía | — | Filas | A19 |
| TS-IDENTITY-10 | Cambio de vínculos | Lote `sealed` de `p_a` | `mr_owner`, `mr_svc_test_a` | Desactivar el vínculo de `mr_svc_test_a`; publicar; intentar cambiar vínculos como `mr_svc_test_a` | `publish` → `MRI01`; el cambio como escritor → `permission denied`; el cambio de vínculo deja un evento | `MRI01`, 42501 | SQLSTATE, evento | A19 |

## 7. TS-CI-SEC · Seguridad del flujo de GitHub Actions (MR-05; solo si DP-03 = Sí)

**Estado de todas: Pendiente de ejecución.**

- **Sustituye** a TS-CI-01…08 de v3.1, cuyo contenido se conserva dentro de TS-CI-SEC-01…08.
- Las pruebas estáticas se implementan en `tests/market_radar/` y leen el YAML **como texto**, sin dependencias nuevas.
- **Limitación (V3-35):** estas pruebas son **controles de regresión**. Una PR maliciosa puede modificarlas, de modo que no protegen frente a ella. Esa protección está en lo que el trabajo no tiene (secretos, escritura) y en la configuración R-01…R-08 del propietario (LEDGER §6.3).

Preparación común: el archivo `.github/workflows/market-radar-i1.yml` y `tests/market_radar/ci/requirements-ci.lock`. Evidencia común: salida de la prueba y, en las de ejecución, el registro del trabajo.

| Id | Objetivo | Tipo | Comprobación | Esperado | Evidencia | Crit. |
|---|---|---|---|---|---|---|
| TS-CI-SEC-01 | Rutas | Estática (`git`) | `git diff --name-status release-2.1...HEAD` | Solo altas (`A`) en las tres carpetas permitidas y, como mucho, el archivo del flujo | Salida | A14, A21 |
| TS-CI-SEC-02 | Disparadores | Estática | Claves `on:` | Solo `pull_request` (`opened`, `synchronize`, `reopened`) con filtro de rutas; ninguna de las prohibidas | Salida | A20 |
| TS-CI-SEC-03 | Permisos | Estática | `permissions` | `{}` en el flujo; solo `contents: read` en el trabajo; ninguna otra clave de permisos | Salida | A20 |
| TS-CI-SEC-04 | Secretos y datos | Estática | Texto del flujo | Ninguna aparición de `secrets.`, `vars.`, `environment:`, `github.token`, `neon.tech`, `render.com`, `postgres://`, `printenv`, `env` como orden ni `set -x` | Salida | A20 |
| TS-CI-SEC-05 | Acciones de terceros | Estática | `uses:` | Solo las de la lista blanca (`actions/checkout`, `actions/setup-python`, `actions/upload-artifact`); cada una con SHA de 40 caracteres igual al de la lista blanca, que registra la etiqueta oficial verificada al implementar; `persist-credentials: false` | Salida + lista blanca | A20 |
| TS-CI-SEC-06 | Ejecutor | Estática | `runs-on`, `services`, `container` | `ubuntu-24.04`; sin `self-hosted`; sin `services` con puertos | Salida | A20 |
| TS-CI-SEC-07 | Red y privilegios en las pruebas | Ejecución | Dentro del espacio aislado: `id -u`, conexión a 192.0.2.1 y resolución de un nombre público | `id -u` ≠ 0; la conexión y la resolución fallan | Registro del trabajo | A20, A6 |
| TS-CI-SEC-08 | PostgreSQL del trabajo | Ejecución | `inet_server_addr()`, `listen_addresses`, `server_version_num`, permisos del directorio de sockets | NULL; vacío; 16xxxx; 0700 | Registro | A20 |
| TS-CI-SEC-09 | Sin cachés | Estática | `actions/cache`, `cache:` en `setup-python` y cualquier `restore` | Ninguno | Salida | A20 |
| TS-CI-SEC-10 | Dependencias | Estática + ejecución | La orden de `pip` y el bloqueo; tras instalar, la lista de paquetes | `--require-hashes`, `--only-binary :all:`; cada dependencia transitiva con hash en el bloqueo; lo instalado es exactamente lo del bloqueo | Salida, `pip list` | A20 |
| TS-CI-SEC-11 | Artefactos | Estática + ejecución | `upload-artifact`: rutas y `retention-days`; búsqueda de patrones de secreto y de volcados en el contenido | Solo la salida de pruebas y el inventario de privilegios; `retention-days` ≤ 7; sin coincidencias de patrones; sin archivos de `pg_dump` | Salida | A20 |
| TS-CI-SEC-12 | Límites | Estática | `timeout-minutes`, `concurrency` | ≤ 20; grupo por PR con `cancel-in-progress: true` | Salida | A20 |
| TS-CI-SEC-13 | Sin escrituras ni despliegues | Estática | Pasos `run:` y `uses:` | Ninguna llamada a `gh`, `git push`, `curl`/`wget` con escritura, publicación de paquetes, comentarios, etiquetas, versiones ni despliegues | Salida | A20 |
| TS-CI-SEC-14 | Fallo explícito sin aislamiento | Estática + ejecución simulada | El paso de aislamiento no tiene `continue-on-error` ni `\|\| true`; ejecución forzada sin `unshare` ni contenedor (en una rama de prueba) | El trabajo **falla** con el mensaje de aislamiento no disponible; nunca termina en verde | Salida, registro | A20 |

**Configuración del propietario (R-01…R-08, LEDGER §6.3).** No son pruebas: ningún código del repositorio puede verificarlas. Se acreditan con la lista de comprobación de A20b (`I1_ACCEPTANCE_V3_2.md`).

## 8. Recuento

| Grupo | v3.1 | v3.2 |
|---|---|---|
| Grupos de v3 + TS-ADV ampliado + TS-IDEM (sin CI) | ≈ 201 | ≈ 201 (8 casos precisados o ampliados, §2; sin casos nuevos) |
| TS-BATCH-ID | — | 10 |
| TS-BATCH-DIGEST | — | 18 |
| TS-CLEANUP | — | 13 |
| TS-IDENTITY | — | 10 |
| TS-CI (v3.1) → TS-CI-SEC (condicional) | 8 | 14 (sustituye a los 8) |
| **Total** | **≈ 209** (≈ 201 sin CI) | **≈ 266** (≈ 252 sin CI) |

## 9. Lo que estas pruebas no demuestran

- Ausencia de colisiones de SHA-256 ni de errores en las funciones privilegiadas.
- Que los productores reales deriven bien su `idem_key` (RR-01): solo se prueba el productor sintético.
- Que una PR externa sea inofensiva: TS-CI-SEC solo detecta regresiones en PRs propias.
- La configuración del repositorio (R-01…R-08).
- Rendimiento con volúmenes reales.
