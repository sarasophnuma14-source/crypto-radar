# I-1 v3.1 · Estrategia de pruebas

Fecha: 18-nov-2026. **Amplía** `I1_TEST_STRATEGY_V3.md` (v3, no modificado): sus 15 grupos y reglas generales siguen vigentes. Se añaden **TS-IDEM** (idempotencia concurrente, DV3-13) y **TS-CI** (límites de GitHub Actions, DV3-14/15), y se amplía TS-ADV. **Ninguna prueba existe ni se ha ejecutado.**

## 1. Reglas que se añaden

1. Las pruebas de concurrencia de TS-IDEM coordinan los escritores con **puntos de sincronización deterministas** (un candado consultivo o una tabla de señal **solo de pruebas**, en la base de prueba) para forzar cada intercalado, no solo con pausas aleatorias. Cada caso se repite además 50 veces con pausas aleatorias y semilla registrada.
2. Toda prueba TS-IDEM comprueba **cuatro invariantes** al final:
   - I1: `count(*) FROM write_log WHERE batch_id = X` ≤ 1;
   - I2: todas las llamadas que terminaron bien devolvieron **la misma** versión;
   - I3: las versiones confirmadas no tienen huecos (`max(write_seq) = count(*)`);
   - I4: las filas publicadas del lote coinciden con su contenido declarado (digest).
3. **Control negativo** obligatorio: una variante de `publish` sin el bloqueo del lote ni la revalidación (el diseño v3) debe **fallar** en TS-IDEM-02 y TS-IDEM-05 (dos versiones o error de clave duplicada). Si la variante defectuosa pasa, la prueba no detecta la carrera y se considera inválida.

## 2. TS-IDEM · Idempotencia concurrente

Objetivo: demostrar DV3-13. Evidencia: salida completa, intercalado forzado de cada caso, semillas y las cuatro invariantes. Aceptación: 100 % en Python 3.12 y 3.13; control negativo detecta el fallo.

| Id | Escenario | Intercalado forzado | Resultado esperado |
|---|---|---|---|
| TS-IDEM-01 | Reintento simple | A publica y confirma; A vuelve a llamar `publish` | Misma versión; I1–I4 |
| TS-IDEM-02 | **Dos escritores, mismo `batch_id`, modo dos transacciones** | A y B leen el lote `sealed`; A bloquea; B espera; A publica y confirma; B continúa | A y B devuelven la misma versión; una sola entrada en `write_log` |
| TS-IDEM-03 | Ídem, A hace **rollback** | A bloquea y avanza el ledger; B espera; A deshace | B publica con la versión que A no consumió (sin huecos); una entrada |
| TS-IDEM-04 | Ídem, A se **desconecta** | A bloquea; se termina su conexión (`pg_terminate_backend`) | B publica; una entrada; sin huecos |
| TS-IDEM-05 | **Dos escritores, mismo `batch_id`, modo una transacción** | A y B llaman `open_batch` a la vez; B espera en el índice único | Si A confirma: B recibe `('published', s)` y no prepara nada. Si A deshace: B recibe `('opened', NULL)` y publica |
| TS-IDEM-06 | Revalidación tras el bloqueo del ledger | Se inyecta (solo en la prueba) una variante de publicación que no toma el bloqueo del lote; otra transacción publica el lote mientras la primera espera el ledger | La primera, al revalidar, devuelve la versión ya publicada sin avanzar el contador |
| TS-IDEM-07 | Barrera de restricción única | Se desactiva (solo en la prueba) la revalidación y el bloqueo del lote | La inserción en `write_log` falla por `UNIQUE`, la transacción se deshace, no hay segunda versión |
| TS-IDEM-08 | **Reintento tras `COMMIT` desconocido (se confirmó)** | A confirma; la conexión se corta antes de leer la respuesta (cierre del socket del cliente tras enviar `COMMIT`) | Conexión nueva: `batch_status` → `published, s`; `publish` → `s`; ninguna versión nueva |
| TS-IDEM-09 | **Reintento tras `COMMIT` desconocido (no se confirmó)** | Se termina la conexión de A antes de que el `COMMIT` llegue al servidor | Conexión nueva: `batch_status` → no existe (modo una transacción) o `sealed` (modo dos transacciones); el reintento con el mismo `batch_id` publica una vez |
| TS-IDEM-10 | Mismo `batch_id`, distinto contenido | B abre con otro digest | `BatchConflict`; nada publicado por B; evento operativo |
| TS-IDEM-11 | `publish` en `REPEATABLE READ` | Cliente abre la transacción en RR | `PublishRequiresReadCommitted`; nada cambia |
| TS-IDEM-12 | Sin interbloqueos | 2 lotes X e Y, publicadores cruzados en orden opuesto de llamada; variante multi-lote | Ningún `deadlock detected`; ambos publicados una vez |
| TS-IDEM-13 | Tormenta | 32 escritores, 200 lotes, cada lote enviado por 2–4 escritores a la vez, 10 % de rollbacks, 20 desconexiones | `count(write_log) = count(DISTINCT batch_id confirmados)`; I1–I4 en todos |
| TS-IDEM-14 | Lote abierto sin sellar al confirmar | Cliente hace `open_batch` + preparación y `COMMIT` sin sellar | El `COMMIT` falla (disparador diferido); el lote no existe después |
| TS-IDEM-15 | `batch_id` determinista | Mismo contenido canónico desde dos procesos independientes | Mismo `batch_id`; una publicación |
| TS-IDEM-16 | Espera acotada | A abre el lote y queda inactivo en la transacción | `idle_in_transaction_session_timeout` corta a A; B continúa dentro del tiempo límite |

## 3. TS-ADV · Casos añadidos

| Id | Ataque (como `mr_writer`) | Resultado esperado |
|---|---|---|
| TS-ADV-15 | Publicar un lote abierto por otra transacción | `BatchNotSealed` |
| TS-ADV-16 | Insertar filas de preparación en un lote abierto por otra transacción | Error del disparador (`opened_xid`) |
| TS-ADV-17 | Modificar o borrar filas de preparación de un lote `sealed` | Error del disparador |
| TS-ADV-18 | `UPDATE mr.batches SET status = 'published'` / fijar `write_seq` | `permission denied` |
| TS-ADV-19 | `batch_status` de un lote de otro rol | Sin resultado |
| TS-ADV-20 | Llamar `publish` con un `batch_id` de un lote ya publicado por otro rol | Devuelve error o nada; nunca otra versión |

## 4. TS-CI · Límites de GitHub Actions (solo si DP-03 = Sí)

Objetivo: demostrar DV3-14 y DV3-15. Evidencia: salida del análisis estático y registro del trabajo. Aceptación: todos los casos al 100 %.

| Id | Comprobación | Resultado esperado |
|---|---|---|
| TS-CI-01 | `git diff --name-status release-2.1...HEAD` | Solo altas en las tres carpetas y, como mucho, `.github/workflows/market-radar-i1.yml` |
| TS-CI-02 | Disparadores del archivo | Solo `pull_request`; ninguno de la lista prohibida |
| TS-CI-03 | Permisos | `permissions: {}` global y solo `contents: read` en el trabajo |
| TS-CI-04 | Secretos y variables | Ninguna aparición de `secrets.`, `vars.`, `environment:`, `neon.tech`, `render.com` |
| TS-CI-05 | Acciones de terceros | Todas fijadas por SHA de 40 caracteres; solo las permitidas; `persist-credentials: false` |
| TS-CI-06 | Ejecutor | `ubuntu-24.04` alojado por GitHub; ningún `self-hosted` |
| TS-CI-07 | Red durante las pruebas | Dentro del espacio aislado, la conexión a 192.0.2.1 y la resolución de un nombre público fallan (registro del trabajo) |
| TS-CI-08 | PostgreSQL del trabajo | `inet_server_addr()` nulo; `listen_addresses` vacío |

Implementación del análisis estático: una prueba de `tests/market_radar/` que lee el archivo YAML como texto y aplica las reglas (sin dependencias nuevas).

## 5. Recuento

| Grupo | v3 | v3.1 |
|---|---|---|
| 15 grupos de v3 (TS-ADV con 14) | ≈ 179 | ≈ 179 |
| TS-ADV, casos añadidos | — | 6 |
| TS-IDEM | — | 16 |
| TS-CI (condicional) | — | 8 |
| **Total** | **≈ 179** | **≈ 209** (≈ 201 si DP-03 = No) |
