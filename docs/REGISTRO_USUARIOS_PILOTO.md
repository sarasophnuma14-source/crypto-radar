# Registro de usuarios del piloto cerrado · Crypto Radar 2.1.0

Fecha: 2026-11-15. Rama `claude/preparacion-piloto`. Este documento recoge la decisión del responsable sobre los
usuarios, lo que se implementó para cumplirla y el procedimiento de altas durante el piloto.

## 1. Decisión: la 2.1.0 empieza como plataforma nueva

**Decisión del responsable (2026-11-15):** no se migran los usuarios de la 2.0.0. Habrá un único administrador
inicial, creado mediante el bootstrap seguro y con TOTP obligatorio. Los usuarios se registran desde cero y cada
registro necesita la aprobación del administrador.

### 1.1 Cómo se garantiza

La implementación está en `radar/db.py`, en `init_platform()`, y se ejecuta en cada arranque dentro de `db.init()`.

| Situación de la base | Qué hace el primer arranque de 2.1 |
| --- | --- |
| Vacía (recomendado: base nueva en Neon) | Deja la marca `platform_meta: platform = 2.1`, con `initialized = nueva` |
| Con datos de la 2.0.0 | En **una sola transacción**: copia cada fila de `users`, `sessions`, `telegram_links`, `positions`, `payments` y `activity` a `legacy_archive`, las borra de las tablas activas, vacía `rate_limits` y deja la marca `initialized = archivada_2_0`. Si algo falla a mitad, no cambia nada |
| Con cuentas de 2.1 pero sin la marca | **No toca nada y no arranca.** Solo con `CRYPTO_RADAR_PLATFORM_ADOPT=1` se marca tal como está |
| Ya marcada | Nada. La conversión no se repite nunca |

Cómo se distingue una base de la 2.0.0 de una de 2.1 sin marca: la 2.0.0 nunca escribió aprobaciones,
consentimientos, TOTP, estados `pending` o `rejected`, ni códigos de alta. Cualquiera de esas huellas impide el
archivado.

Lo que **no** se conserva, ni siquiera en el archivo: hashes de contraseña, semillas TOTP, hashes de token de sesión,
tokens CSRF y códigos de vinculación de Telegram. No tienen valor legal ni contable, y conservarlos solo añadiría
riesgo. La copia firmada que se hace **antes** del despliegue (`PROCEDIMIENTO_LANZAMIENTO_PILOTO.md` §2) guarda la base
de la 2.0.0 completa, por si se necesitara.

Lo que **sí** se conserva:
- en `legacy_archive`, con la fila original en JSON: usuarios (sin credenciales), pagos, actividad, posiciones y
  sesiones (solo fecha, IP y navegador);
- en `kv`, los documentos del sistema (informes y ajustes del escáner).

Ninguna consulta de autenticación, sesión, permisos, planes, Telegram ni pagos lee `legacy_archive`.

### 1.2 Pruebas ejecutadas

| Requisito | Prueba | Resultado |
| --- | --- | --- |
| Un usuario antiguo no puede iniciar sesión | `plataforma_nueva.py`: administrador y cliente de la 2.0.0 reciben 401 con el mismo mensaje que un usuario inexistente | OK (SQLite y PostgreSQL) |
| Token antiguo rechazado | Código de Telegram de la 2.0.0: «Código no válido» | OK |
| Sesión antigua rechazada | Cookie `cr_session` de la 2.0.0 en `/api/me`: 401 | OK |
| La suscripción antigua no se hereda | El cliente con plan Pro pagado vuelve a registrarse con el mismo nombre: queda pendiente y, aprobado, tiene plan Libre y ningún pago visible | OK |
| Un usuario nuevo puede registrarse | Solicitud con 200 y estado pendiente | OK |
| Un usuario nuevo no puede obtener rol administrativo | Solicitud con `is_admin`, `plan`, `status` y `plan_until` inyectados: se ignoran. Nombres reservados (`admin`, `root`, `soporte`, `administrador`, el del entorno): 409. Aprobar con plan Élite, crear desde el panel o guardar ajustes con `is_admin`: no da el rol (`T30…new_users_never_get_admin`) | OK |
| Solo el administrador autorizado accede al panel | Un usuario normal recibe 403 en las 7 rutas de administración. El administrador sin TOTP también recibe 403 | OK |
| Reiniciar no reactiva usuarios antiguos | Dos reinicios: el archivo no cambia y el antiguo sigue en 401 | OK |
| Dos inicializaciones no duplican administradores | Tras cada reinicio, `count(is_admin) = 1`. Una segunda cuenta con `is_admin` escrita a mano en la base pierde el rol al arrancar (`T30…extra_admin…`) | OK |
| Atomicidad | Fallo a mitad del archivado: no se archiva ni se borra nada y no queda la marca (`T30…cutover_is_atomic`) | OK |
| Concurrencia | 4 procesos arrancan a la vez sobre la base heredada: se archiva una sola vez, sin errores (PostgreSQL) | OK. Corrigió el fallo F-10 (§5) |
| Copia y restauración | La marca viaja en la copia. La base restaurada no se toma por heredada (`T31…keeps_platform_marker`) | OK |

Evidencia: `docs/evidencia_piloto/preparacion/plataforma_nueva.json`, 41/41 pasos.

## 2. Un único administrador

- Solo lo crea el arranque, a partir de `CRYPTO_RADAR_ADMIN_USER` y `_PASSWORD` (`auth.ensure_admin`).
  - Si una cuenta normal ya tiene ese nombre, nunca se promueve: el servidor no arranca, o con `_TAKEOVER=1` esa cuenta
    pasa a cuarentena.
- **Ninguna otra vía da `is_admin`.** Lo revisé en todos los `INSERT INTO users` y `UPDATE users` del código (§5):
  - `_create` solo recibe `is_admin=1` desde `ensure_admin`;
  - las solicitudes, la aprobación, la creación desde el panel, los ajustes, los pagos y Telegram nunca escriben
    `is_admin`.
- **Exactamente uno.** Después de crear o verificar al administrador, el arranque retira el rol a cualquier otra cuenta
  que lo tenga, la desactiva y cierra sus sesiones (`admin_bootstrap_demoted` en la actividad). Si aun así no queda
  exactamente uno, no arranca. Esto cubre el cambio de `CRYPTO_RADAR_ADMIN_USER`: el anterior deja de ser
  administrador.
- El administrador no puede tocar a otro administrador desde el panel. Ninguna acción administrativa funciona sin TOTP.
- Alta del TOTP con un código de un solo uso: `BOOTSTRAP_ADMIN.md`.

## 3. Flujo del piloto

| Paso | Qué ocurre | Dónde | Prueba |
| --- | --- | --- | --- |
| 1. Solicitud | El usuario elige un usuario (3 a 32 caracteres, `[a-z0-9._-]`) y una contraseña de 10+ caracteres; contacto y mensaje son opcionales. Acepta la política (versión guardada) | `/entrar#solicitar` → `auth.request_access` | `test_request_does_not_log_in_and_pending_cannot_enter` |
| 2. Validación | Formato, contraseña distinta del usuario y no trivial, nombre no reservado ni existente, consentimiento, 3 solicitudes por IP y hora, 60 por hora en total, como mucho 300 pendientes | `auth.validate_credentials` | `test_registration_rate_limited_per_ip`, `test_pending_requests_capped`, `test_a08_duplicate_username_race_returns_409` |
| 3. Pendiente | La cuenta existe con `status = pending` y no puede entrar (403 solo si la contraseña es correcta) | `auth.login` | ídem |
| 4. El administrador la ve | Panel «Usuarios y solicitudes de acceso», con contacto y mensaje | `/api/admin/users` (solo administrador con TOTP) | `test_admin_api_approve_create_reset` |
| 5. Aprueba o rechaza | Aprobar con plan y días, o rechazar | `/api/admin/user` | `test_full_account_lifecycle` |
| 6. Aprobado | Entra con su contraseña | — | ídem |
| 7. Rechazado | No entra (403) | — | `test_rejected_and_disabled_users` |
| 8. Registro | Cada acción queda en `activity` (`admin_user_approve`, `_reject`, `_disable`, `_create`, `_reset_password`, `admin_bootstrap_*`) con el administrador, el usuario afectado y la IP | `auth.log` | `test_activity_log` |

El administrador no recibe un aviso cuando llega una solicitud: la ve en el panel. Para 3 a 10 personas basta con
revisarlo a diario. Avisar por Telegram es una mejora opcional.

## 4. Controles de la cuenta

| Control | Comportamiento | Prueba |
| --- | --- | --- |
| Recuperación de contraseña | **No hay autoservicio:** no hay correo. El administrador la restablece desde el panel (también borra el TOTP y cierra las sesiones) y la entrega por un canal acordado. El administrador recupera la suya con `CRYPTO_RADAR_ADMIN_RESET=1` (`BOOTSTRAP_ADMIN.md` §4) | `test_admin_api_approve_create_reset` |
| Cierre de sesión | Borra la sesión en el servidor. La cookie deja de valer aunque se conserve | `test_logout_invalidates_session`, `test_cookie_flags_and_server_side_logout` |
| Revocación | «Cerrar todas las sesiones» (`/api/auth/logout_all`). Desactivar, rechazar o cambiar la contraseña cierra todas las sesiones de esa cuenta | `test_rejected_and_disabled_users` |
| Bloqueo temporal | 5 fallos bloquean la cuenta 15 min. 20 fallos por IP cada 15 min. Modo estricto ante ataques repartidos | `test_account_lockout`, `test_ip_failure_limit_*`, `test_concurrent_guesses_never_exceed_failure_limit` |
| Cuentas duplicadas | `UNIQUE` en la base y 409 con el mismo texto para un nombre reservado o ya usado | `test_a08_duplicate_username_race_returns_409` |
| Enumeración en el inicio de sesión | Mismo mensaje y mismo tiempo (scrypt simulado) para un usuario inexistente o una contraseña errónea. El bloqueo aparente también afecta a nombres inexistentes. El estado (pendiente o rechazado) solo se revela a quien tiene la contraseña | `test_same_error_for_unknown_user_and_wrong_password`, `test_a06_lockout_message_does_not_reveal_existence` |
| Enumeración en la solicitud | **Residual:** al elegir un nombre ya usado la respuesta es 409 («no disponible»). Es inherente a dejar elegir el usuario. Lo limitan las 3 solicitudes por IP y hora | `test_registration_rate_limited_per_ip` |
| Sesiones | Cookie `HttpOnly`, `SameSite=Lax`, `Secure` tras HTTPS. Token aleatorio de 32 bytes guardado como SHA-256. 14 días. Rotación al iniciar sesión | `test_cookie_flags_and_server_side_logout` |
| CSRF | `X-CSRF-Token` obligatorio en cada POST autenticado y comprobación de origen | `test_csrf_required`, `test_csrf_variants_rejected`, `test_foreign_origin_blocked` |
| Permisos por plan | Matriz completa por plan y ruta | `test_entitlements_matrix` |

## 5. Hallazgos de esta fase

- **F-10. Arranque simultáneo en PostgreSQL.** Dos procesos arrancando a la vez sobre una base vacía chocaban en el
  catálogo (`CREATE TABLE IF NOT EXISTS`: `pg_type_typname_nsp_index`) y uno caía. Se corrigió con un bloqueo
  consultivo en `db.init()`. La prueba de 4 procesos lo demuestra.
- **N-01. La migración heredaba usuarios.** Antes de este cambio, las cuentas de la 2.0.0 quedaban `active` y podían
  entrar con su contraseña de siempre, sin aprobación (R-22). Corregido por el §1.
- **N-02. Cambiar el administrador del entorno dejaba dos administradores.** Corregido por el §2.

## 6. Procedimiento para las solicitudes de los titulares (Ley 1581)

Mientras no exista exportación ni supresión automáticas:

1. Recibir la solicitud en el correo de la política.
2. Comprobar que quien escribe es el titular de la cuenta: por ejemplo, que escriba desde el contacto registrado o
   desde su sesión.
3. **Consulta.** Responder en 10 días hábiles con los datos de la cuenta y su actividad; el administrador los obtiene
   del panel o de la base.
4. **Rectificación o supresión.** Para suprimir, desactivar la cuenta, cerrar sus sesiones y borrar sus filas. Ese paso
   es manual y queda **pendiente de automatizar** antes de ampliar el piloto (`GO_NO_GO_PILOTO.md`, G-19).
5. Dejar constancia de la solicitud y de la respuesta.
