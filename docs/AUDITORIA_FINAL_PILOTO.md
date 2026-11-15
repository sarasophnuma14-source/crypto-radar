# Auditoría final antes del piloto cerrado · Crypto Radar 2.1.0

Fecha: 2026-11-15.

Alcance: código de la rama `claude/auditoria-produccion` (`8476715`, PR #4) y su base (PR #3).

Reglas cumplidas:
- No se desplegó, no se fusionó ningún PR y no se tocó producción.
- No se activó el modo `live` de pagos.
- No se cambiaron la estrategia, sus parámetros, el paper trading, el ledger ni los resultados históricos.
- No se borraron datos ni se cambiaron credenciales reales.
- Todas las bases usadas fueron temporales y locales.

Informes que acompañan a este:
- `docs/PRUEBAS_RENDIMIENTO.md`
- `docs/RECUPERACION_DESASTRES.md`
- `docs/MATRIZ_RIESGOS_PENDIENTES.md`

Evidencia en bruto (JSON y texto): `docs/evidencia_piloto/`.

## Veredicto

**C. APTO PARA PILOTO CERRADO, con condiciones de arranque.**

El código supera las pruebas de seguridad, pagos (en modo apagado o sandbox), recuperación y carga hasta 100 usuarios simultáneos.

**No se concede la categoría D** (producción comercial) porque:
- los pagos no se han probado con los sandbox reales;
- la política de privacidad está incompleta;
- no hay evidencia de la configuración real de Render y Neon;
- la estrategia no tiene ventaja validada (R-12).

**Condiciones para invitar al primer usuario.** Todas son verificables con `python main.py preflight --db`, que hoy falla en la primera:
1. Completar los datos del responsable en `/privacidad` y pasar la revisión de un abogado (R-01).
2. Fusionar los PR en orden y desplegar con `CRYPTO_RADAR_PAYMENTS=off` (R-17).
3. Activar el TOTP del administrador justo después del primer arranque (R-02).
4. Neon con pooler y `sslmode=require`, y una primera copia firmada y verificada (R-10, R-11).
5. Que `preflight --db` termine con 0 fallos.

## Fase 1 · Git

| Comprobación | Resultado |
| --- | --- |
| Ramas | `main` `9176b36` → PR #3 `claude/project-thread-i8udp5` `2d72a2b` (4 commits) → PR #4 `claude/auditoria-produccion` `8476715` (2 commits) → PR #5 de esta auditoría |
| Dependencia | En cadena: la base del #4 es la cabeza del #3 (`merge-base` = `2d72a2b`). Hay que fusionarlos en orden #3 → #4 → #5 |
| Conflictos | Ninguno. Fusión de prueba en memoria (`git merge-tree`) de la cabeza del #4 sobre `main`: sin conflictos. No se fusionó nada |
| Cambios duplicados | Ninguno. Cada PR añade commits sobre el anterior y no hay commits repetidos (cherry-picks) |
| Estrategia, paper trading y ledger | `git diff origin/main HEAD -- research radar/quant radar/edge radar/paper_trading` vacío. SHA-256 de `ledger.jsonl` idéntico al de `main` (`104be2ce…`). `radar/scanner.py` y `radar/config.py` sin cambios |

## Hallazgos y correcciones

Cada hallazgo tiene una prueba reproducible que muestra el fallo con el código anterior y el arreglo con el actual.

| ID | Severidad | Hallazgo | Evidencia (antes → después) | Corrección | Prueba |
| --- | --- | --- | --- | --- | --- |
| F-04 | **Alta** (disponibilidad) | Cola de escucha de 5: en ráfagas se rechazaban conexiones | 18/50 y 23/100 inicios de sesión con `ConnectionResetError` → 0 | `PooledHTTPServer` con cola de 128 | `T27.test_burst_without_resets_and_bounded_threads`, `tests/piloto/carga.py` |
| F-01 | Media | Copias de seguridad falsificables: los hashes no llevan clave, así que se puede cambiar `is_admin` y recalcularlos | `ataque_backup.py`: «NO DETECTADO, is_admin=1» → con clave: «DETECTADO» | HMAC-SHA256 con `CRYPTO_RADAR_BACKUP_KEY`; `verify` y `restore` exigen la firma si hay clave | `T25.test_forged_backup_with_recomputed_hashes`, `T25.test_backup_signature_wrong_key_rejected`, simulacro paso 6 |
| F-03 | Media (cobros) | IPN legítimas de NOWPayments rechazadas: se verificaba sobre JSON de Python, no sobre el `JSON.stringify` que firma el proveedor | `firma_nowpayments.py`: 2/4 aceptadas (tildes y `1e-7` rechazadas) → 4/4 | `_js_json` y verificación sobre ambas formas | `T26.test_nowpayments_js_style_signatures_accepted` |
| F-05 | Media | Una conexión a PostgreSQL por petición y memoria creciente | 2307 conexiones en 2334 peticiones y 514 MB → 15 conexiones en total y 345 MB | 16 hilos fijos (`CRYPTO_RADAR_WORKERS`) | `T27`, `carga_antes.json` / `carga_despues.json` |
| F-06 | Media | Tras un corte de PostgreSQL o Neon fallaba la primera consulta de cada conexión. Con F-05 eso era una petición fallida por hilo | `entorno.py`: 16/40 fallidas → 0/40; contraprueba en `8476715`: `AdminShutdown` | Reconectar si psycopg marca la conexión rota | `T27.test_pg_reconnects_after_server_terminates_connection` |
| F-02 | Baja | Códigos de vinculación de Telegram (32 bits, 15 min) sin límite de intentos por chat | `ataque_telegram.py`: 200/200 procesados → 10/200 | 10 intentos por chat y hora | `T25.test_telegram_link_codes` |

Sobre F-06:
- La causa estaba en el código anterior: `db.execute` solo reintentaba si el error decía «closed».
- Quedó al descubierto con la corrección F-05.
- La detectó la propia prueba de entorno antes del commit.

**Sin hallazgos (pruebas superadas):**
- **Sesiones:** cookie `HttpOnly` y `SameSite=Lax`; el token se invalida en el servidor al salir; se rota al entrar; los tokens falsos se rechazan.
- **TOTP:** 8 inicios de sesión simultáneos con el mismo código dan exactamente 1 éxito. No se puede reinscribir con sesión y contraseña (409).
- **Recuperación del administrador:** `ADMIN_RESET` cierra las sesiones del atacante y anula la contraseña anterior.
- **CSRF:** se rechazan las peticiones sin token, con el token de otra sesión, desde otro origen o como `text/plain`.
- **XSS almacenado en el navegador real (Chromium):**
  - prueba: `<img onerror>`, `<script>` y `<svg onload>` en «contacto» y «mensaje», con el panel de administración abierto;
  - nada se ejecuta y el texto se ve literal (`tests/piloto/xss_navegador.py`);
  - la CSP no tiene `unsafe-inline` en `script-src`.
- **Escalada de privilegios:**
  - `is_admin`, `plan` y `totp_enabled` no se pueden cambiar desde `/api/me/settings`;
  - todas las rutas de administración responden 403 a un usuario normal.
- **Aislamiento entre usuarios:**
  - el usuario B recibe 404 al cerrar, editar o borrar posiciones de A;
  - no ve la actividad ni los pagos de A.
- **Telegram:** el código es de un solo uso, caduca y un chat solo queda ligado a una cuenta.
- **Secretos:**
  - las respuestas no incluyen hashes, secretos TOTP ni claves;
  - los registros del servidor no muestran contraseñas;
  - el historial de las 40 confirmaciones de todas las ramas no tiene secretos reales (solo ejemplos ficticios en pruebas y documentación).

## Fase 3 · Pagos

Pruebas en `T26_PagosAdversarial` (9) más las de `T14`, `T22` y la autoprueba (`main.py payments-selftest`, 16/16).

Wompi:

| Caso | Resultado |
| --- | --- |
| Firma falsa o lista de propiedades vacía | 401 |
| Referencia cambiada en un evento con firma válida (la firma no la cubre) | 409: la consulta a la API la detecta |
| Moneda distinta o estado distinto en la API | 409 |
| Pago PENDING y luego APPROVED | Primero se registra sin activar; luego activa |
| 10 entregas simultáneas y 5 reintentos del mismo webhook | Todas 200; el plan se concede una sola vez (+30 días, 1 registro) |
| Reembolso o anulación tras aprobar | El plan **no** se retira (R-04, documentado) |

NOWPayments:

| Caso | Resultado |
| --- | --- |
| Estados waiting, confirming, partially_paid, failed, refunded y expired | No activan el plan |
| Firma falsa | 401 |
| Moneda EUR, monto inferior, estado parcial en la API, pago de otro pedido reutilizado | 409 |
| Firma en mayúsculas | Aceptada |
| Reintento de un IPN ya aplicado | Idempotente |
| Referencia de Wompi enviada como IPN | 404 |

**No verificable sin credenciales de sandbox:** la conexión real con Wompi y NOWPayments, el formato exacto de sus eventos actuales y los reembolsos reales. El modo `live` sigue sin activarse.

## Fase 4 · Recuperación

18/18 pasos OK en el simulacro. Ver `docs/RECUPERACION_DESASTRES.md`.

## Fase 5 · Rendimiento

Con 100 usuarios simultáneos:
- 0 errores;
- 99 peticiones por segundo;
- p95 de 66 ms y p99 de 381 ms en el panel;
- 345 MB de memoria;
- ninguna espera por bloqueos ni consultas de más de 50 ms.

Ver `docs/PRUEBAS_RENDIMIENTO.md`.

## Fase 6 · Entorno

| Comprobación | Resultado |
| --- | --- |
| Python | 3.12.3 (Render usa 3.12.7) y 3.13.18: suite completa OK en ambos |
| Dependencias | Fijadas con versión exacta (`psycopg[binary]==3.3.9`, `numpy==2.5.3`, `pandas==3.0.5`). Sin conflictos de dependencias. Todos los módulos se importan |
| Migraciones reales | Desde `main` 2.0.0: 12 → 22 columnas en `users`. Desde el PR #3: 17 → 22. Los usuarios y sus contraseñas se conservan |
| Health check | `/healthz` 200; con la base caída, 500 |
| Persistencia | Sesiones, usuarios, pagos y límites en PostgreSQL; recuperación verificada |
| Registros | Sin contraseñas ni URL con clave |
| `render.yaml` | Secretos `sync: false`; `CRYPTO_RADAR_PAYMENTS="off"`, `CRYPTO_RADAR_ADMIN_TOTP=required` y `MALLOC_ARENA_MAX="2"` |
| Render y Neon reales | **No verificados**: sin acceso y prohibido tocar producción (R-11) |

## Fase 7 · Producto

| Comprobación | Resultado |
| --- | --- |
| El radar genera señales | Escaneo **real de solo lectura** desde este entorno: 165 s, 150 monedas de CoinGecko, 518 pares de Binance, 74 activos analizados, régimen NEUTRAL, 3 en el ranking (`docs/evidencia_piloto/escaneo_real.txt`). Escaneo sintético: OK |
| No se envían órdenes reales | No hay rutas de órdenes ni claves de exchange en el código. La única llamada a `fapi.binance.com` es `premiumIndex`, de solo lectura. `paper_trading.execution.place_real_order()` siempre falla y `REAL_ORDERS_ENABLED` es False. Los únicos POST salientes son las facturas de NOWPayments (pagos `off`) |
| Planes Libre, Pro y Élite | Matriz completa en `T18.test_entitlements_matrix` (OK). En la carga con 100 usuarios, 159 respuestas 402 correctas a usuarios del plan Libre |
| Datos entre usuarios | Posiciones, actividad, pagos y Telegram aislados (`T25`). El informe de mercado es común y se recorta según el plan |
| Paper trading aislado | Solo administradores con TOTP (`/api/paper/report`), carpeta propia, sin red de órdenes; 39 pruebas OK |

## Pruebas ejecutadas

| Comando | Resultado |
| --- | --- |
| `TEST_DATABASE_URL=… python3.12 tests/test_suite.py -v` | **258 OK, 0 omitidas** (35,6 s) |
| `TEST_DATABASE_URL=… python3.13 tests/test_suite.py -v` | **258 OK, 0 omitidas** (29,7 s) |
| `tests/test_edge.py` y `tests/test_paper.py` (3.12 y 3.13) | 29 OK y 39 OK |
| `python main.py payments-selftest` | 16/16, TODO OK |
| `tests/piloto/xss_navegador.py` | Sin ejecución de código |
| `tests/piloto/ataque_backup.py` (sin clave / con clave) | NO DETECTADO (R-09) / DETECTADO |
| `tests/piloto/ataque_telegram.py` | 10 de 200 procesados |
| `tests/piloto/firma_nowpayments.py` | 4/4 |
| `tests/piloto/simulacro_recuperacion.py` | 18/18 |
| `tests/piloto/entorno.py` | 11/11 |
| `tests/piloto/carga.py` (5 variantes) | Ver `PRUEBAS_RENDIMIENTO.md` |
| `node --check web/app.js web/entrar.js` | OK |

27 pruebas nuevas en la suite: `T25` 14, `T26` 9 y `T27` 4. Antes había 231.

**Resultado negativo durante la auditoría:** la primera corrida completa dio 4 errores en `T19`. La prueba sustituía `ThreadingHTTPServer` por un servidor falso y el nuevo `PooledHTTPServer` arrancaba de verdad. Se corrigió el arnés de la prueba y no la lógica de arranque.

## Archivos modificados

- **Código:**
  - `radar/server.py` (`PooledHTTPServer`)
  - `radar/db.py` (reconexión)
  - `radar/backup.py` (firma HMAC)
  - `radar/billing.py` (firma de NOWPayments)
  - `radar/telegram_bot.py` (límite de intentos)
- **Configuración:** `render.yaml` (`MALLOC_ARENA_MAX`).
- **Pruebas:**
  - `tests/test_suite.py` (`T25`–`T27` y el arnés de `T19`)
  - `tests/piloto/` (8 scripts nuevos)
- **Documentación:**
  - `docs/AUDITORIA_FINAL_PILOTO.md`, `docs/PRUEBAS_RENDIMIENTO.md`, `docs/RECUPERACION_DESASTRES.md`, `docs/MATRIZ_RIESGOS_PENDIENTES.md` y `docs/evidencia_piloto/`
  - actualizados: `docs/SEGURIDAD.md`, `docs/INSTALACION_Y_DESPLIEGUE.md`, `CHANGELOG.md`

## Estado de los PR

| PR | Rama | Base | Estado |
| --- | --- | --- | --- |
| #3 | `claude/project-thread-i8udp5` | `main` | Abierto, sin fusionar |
| #4 | `claude/auditoria-produccion` | rama del #3 | Abierto, sin fusionar |
| #5 | `claude/auditoria-final-piloto` (este trabajo) | rama del #4 | Abierto, sin fusionar |

El commit de esta auditoría figura en la descripción del PR #5.
