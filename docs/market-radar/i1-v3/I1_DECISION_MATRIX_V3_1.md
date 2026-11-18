# I-1 v3.1 · Matriz de decisiones

Fecha: 18-nov-2026. Sustituye como referencia a `I1_DECISION_MATRIX.md` (v3), que **no se modifica** y queda como historial.

**Estado de la matriz:** el propietario aceptó la matriz v3 **como base de revisión** el 18-nov-2026 (mensaje en el hilo). Eso **no** es autorización de implementación ni aprobación individual de ninguna decisión. Ninguna decisión del propietario (DP) figura como aprobada.

## 1. Decisiones técnicas recomendadas

| Id | Decisión | Origen | Estado |
|---|---|---|---|
| DV3-01 | Ledger preparar → publicar, contador sin huecos, marca (W, H) | V3-01, V3-03 | Propuesta (en la base de revisión aceptada) |
| DV3-02 | Roles `mr_owner`/`mr_migrator`/`mr_writer`/`mr_reader`/`mr_test_fixtures`; funciones `SECURITY DEFINER` con `search_path` fijo | V3-02 | Ídem |
| DV3-03 | Cadena de hashes en `write_log` | V3-17 | Ídem |
| DV3-04 | Matriz temporal; lecturas por `_asof(W, H)`; atributos definitorios inmutables | V3-05, V3-20 | Ídem |
| DV3-05 | Licencias: campos completos, desconocido = restrictivo | V3-12 | Ídem |
| DV3-06 | Sintéticos por `namespace` + rol + instancia inmutable | V3-11 | Ídem |
| DV3-07 | Crudos: cuerpo decodificado + huella de transporte; JSON estricto | V3-13 | Ídem |
| DV3-08 | Velas: `price_domain`, `price_kind`, `price_basis`, volumen nulo + `volume_kind`, `numeric`; hash `c2` | V3-07…09, V3-14 | Ídem |
| DV3-09 | Calendario con `trading_date` e intervalos; política de alineación | V3-10 | Ídem |
| DV3-10 | Solo socket Unix; limpieza de `PG*`; suite en espacio de red aislado | V3-06 | Ídem |
| DV3-11 | Migraciones transaccionales con manifiesto, sin `CASCADE`, `down` solo en instancia `test` | V3-04, V3-15 | Ídem |
| DV3-12 | Hito M1 con revisión del propietario antes de continuar | — | Ídem |
| **DV3-13** | **Idempotencia concurrente de publicaciones**: `mr.batches` con `batch_id` como clave primaria; `write_log.batch_id` `UNIQUE`; ciclo `open → sealed → published`; bloqueo del lote y después del ledger, en ese orden; **revalidación después de adquirir el bloqueo de `ledger_head`**; una sola publicación ante escritores concurrentes; los reintentos devuelven la secuencia original; `publish` exige `READ COMMITTED`; `batch_id` determinista (UUIDv5 del digest) | V3-26, V3-27, V3-29; petición del propietario | **Nueva · Propuesta** |
| **DV3-14** | **Límites de seguridad de GitHub Actions** (§3): permisos mínimos, sin secretos, sin despliegues, sin disparadores privilegiados, acciones fijadas por SHA, pruebas en red aislada | DP-03; petición del propietario | **Nueva · Propuesta**, condicionada a DP-03 |
| **DV3-15** | **Excepción de ruta única**: si DP-03 = Sí, el único archivo permitido fuera de las tres carpetas es `.github/workflows/market-radar-i1.yml` | V3-28; petición del propietario | **Nueva · Propuesta**, condicionada a DP-03 |

Se conservan sin cambios D-001…D-027 de `DECISION_LOG.md` con su estado (D-021 y D-023 siguen como propuestas de v2 sustituidas técnicamente por DV3-01 y DV3-06; el registro original no se edita).

## 2. Decisiones del propietario (ninguna aprobada)

| Id | Pregunta | Opciones | Recomendación técnica | Estado |
|---|---|---|---|---|
| DP-01 | ¿Se autoriza escribir código? | (a) Solo M1; (b) I-1 completo; (c) No por ahora | (a) | **Pendiente** |
| DP-02 | ¿Se aprueban DV3-01…DV3-15 individualmente? | Todas / algunas / ninguna | Todas | **Pendiente** (la aceptación como base de revisión no equivale a aprobación) |
| DP-03 | ¿Se añade CI en GitHub Actions solo para Market Radar? | Sí, con DV3-14 y DV3-15 / No | Sí: da evidencia reproducible fuera del entorno local | **Pendiente** |
| DP-04 | ¿El desarrollo puede empezar antes de cerrar la Fase 0 de la 2.1? | Sí, **solo como desarrollo aislado** / No | Sí, con los límites de abajo | **Pendiente** |

**Límites de DP-04 (si se aprueba):** solo desarrollo aislado en una rama nueva; sin fusionar; sin desplegar; sin modificar ningún archivo existente; sin interactuar con servicios de producción (Neon, Render, Telegram, proveedores, pagos); sin tocar la 2.1, secretos, holdout ni paper trading. Fusionar exige, además, el cierre de la Fase 0 y una autorización nueva y expresa.

## 3. DV3-14 · Límites de GitHub Actions

| Área | Regla |
|---|---|
| Archivo | Uno solo: `.github/workflows/market-radar-i1.yml` (DV3-15). El repositorio no tiene hoy ninguna carpeta `.github` (comprobado el 18-nov en `HEAD` y en `release-2.1`), así que no hay flujos existentes que se vean afectados |
| Disparadores | Solo `pull_request` (tipos `opened`, `synchronize`, `reopened`) con filtro de rutas `market_radar/**`, `tests/market_radar/**` y el propio archivo. **Prohibidos:** `pull_request_target`, `workflow_run`, `push` a ramas protegidas, `schedule`, `workflow_dispatch`, `repository_dispatch` |
| Permisos | `permissions: {}` a nivel de flujo; el trabajo pide solo `contents: read`. Ningún otro permiso (`id-token`, `packages`, `deployments`, `pull-requests: write`, etc.) |
| Secretos | Ninguna referencia a `secrets.*` salvo el `GITHUB_TOKEN` implícito de solo lectura. Ninguna variable `vars.*`. Ningún `environment:`. Ninguna URL de Neon, Render ni de proveedores |
| Despliegue | Ningún paso que despliegue, publique paquetes, cree versiones, escriba comentarios o etiquetas, ni llame a APIs externas |
| Código de terceros | Acciones fijadas por **SHA completo** de commit (no por etiqueta); solo `actions/checkout` y `actions/setup-python` (y `actions/upload-artifact` para la evidencia). `checkout` con `persist-credentials: false`. Los SHA concretos se registran al implementar (hoy **NO VERIFICADOS**) |
| Dependencias | Solo `psycopg[binary]==3.3.9` (ya en `requirements.txt`), instalada con hashes (`--require-hashes`); los hashes se registran al implementar |
| Ejecutor | GitHub-hosted, efímero (`ubuntu-24.04`). Prohibidos los ejecutores propios |
| Base de datos | PostgreSQL 16 instalado dentro del trabajo, escuchando **solo** en socket Unix (`listen_addresses = ''`); sin contenedores de servicio con puertos TCP |
| Aislamiento de red | La instalación (paquetes) ocurre antes; **las pruebas** se ejecutan dentro de un espacio de red sin interfaces salvo loopback (`sudo unshare --net`) o, si no fuera posible, en un contenedor `--network none`. Que el ejecutor permita `unshare` es **SUP** y se comprueba en M1 |
| Límites | `timeout-minutes: 20`; `concurrency` por PR con cancelación del anterior |
| Evidencia | Se sube como artefacto solo la salida de pruebas y el inventario de privilegios, retención 7 días; sin volcados de base |
| Contribuciones externas | El repositorio es público (RSK-09): recomendado exigir aprobación manual para ejecutar flujos de colaboradores externos. Es un ajuste del repositorio que **solo puede hacer el propietario**; no se toca |

Verificación: grupo TS-CI de `I1_TEST_STRATEGY_V3_1.md` (análisis estático del archivo y prueba de control de red dentro del trabajo).

## 4. Discrepancia de carpetas (V3-28) y su resolución

`I1_IMPLEMENTATION_PLAN_V3.md` §1 limita I-1 a tres carpetas nuevas, pero DP-03 implica un archivo en `.github/`. Resolución documental (DV3-15): la lista de rutas permitidas pasa a ser **tres carpetas + una ruta exacta**, y la ruta exacta solo es válida si DP-03 = Sí. Cualquier otro archivo en `.github/` o fuera de las tres carpetas hace fallar el criterio de aceptación de rutas.
