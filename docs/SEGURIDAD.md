# Seguridad del modo cuentas (2.1.0)

Este documento resume cómo se protege el acceso y qué limitaciones quedan. Aplica al modo cuentas
(`CRYPTO_RADAR_ACCOUNTS=1`). La app no ejecuta órdenes reales ni se conecta a exchanges para operar.

## 1. Arranque del administrador

El administrador sale de `CRYPTO_RADAR_ADMIN_USER` y `CRYPTO_RADAR_ADMIN_PASSWORD`. **En modo cuentas las dos son
obligatorias**: si falta cualquiera (o está vacía), `serve()` se detiene con `SystemExit` antes de abrir la base y el
mensaje nombra la variable que falta, sin mostrar contraseñas. Si `ensure_admin()` no confirma un administrador, el
servidor tampoco arranca. No existe ningún arranque en modo cuentas sin administrador. La contraseña debe tener
12 caracteres o más y no puede contener el usuario. `auth.ensure_admin()` se ejecuta en cada arranque y el registro
del servidor muestra `Administrador: <usuario> · <resultado>`.

| Situación en la base | Resultado | Qué hace |
| --- | --- | --- |
| No existe ese usuario | `creado` | Lo crea activo, como administrador, con la contraseña del entorno (`approved_by = entorno`) |
| Existe y ya es administrador | `verificado` | No toca su contraseña (puede haberla cambiado desde la app) |
| Existe, es administrador y `CRYPTO_RADAR_ADMIN_RESET=1` | `restablecido` | Pone la contraseña del entorno y cierra todas sus sesiones |
| Existe como cuenta **normal** | el servidor **no arranca** | Nunca se promueve. Se registra `admin_bootstrap_conflict` |
| Existe como cuenta normal y `CRYPTO_RADAR_ADMIN_TAKEOVER=1` | `cuarentena` | La cuenta se renombra (`<usuario>~cuarentena~<id>`), queda rechazada y desactivada, se cierran sus sesiones y se crea un administrador **nuevo** con la contraseña del entorno. La contraseña de quien reservó el nombre no se conserva |

Cada resultado queda en la tabla `activity`: `admin_bootstrap_created`, `admin_bootstrap_verified`,
`admin_bootstrap_password_reset`, `admin_bootstrap_conflict` y `admin_bootstrap_quarantine`.

Prevención adicional:
- Nadie puede solicitar el nombre del administrador del entorno ni nombres reservados (`admin`, `administrador`,
  `root`, `soporte`, `sistema`, …). Responde 409 como si estuviera ocupado.
- Desde el panel no se puede aprobar, rechazar, desactivar, eliminar ni cambiar la contraseña de otro administrador.
  Tampoco de uno mismo.

Después de usar `CRYPTO_RADAR_ADMIN_RESET` o `CRYPTO_RADAR_ADMIN_TAKEOVER`, quítalas de Render.

## 2. Permisos por plan

Las rutas se comprueban en el servidor; ocultarlas en la interfaz no basta. La matriz completa se prueba en
`tests/test_suite.py` (`test_entitlements_matrix`).

| Ruta | Libre | Pro | Élite | Admin |
| --- | --- | --- | --- | --- |
| `/api/state` | top 3, resto bloqueado | completo | completo | completo |
| `/api/alerts` | solo su top y alertas generales; sin memecoins ni salidas | todo | todo | todo |
| `/api/journal`, `/api/scans` | solo su top | todo | todo | todo |
| `/api/candles`, `/api/history` | solo monedas de su top (402 si no) | todo | todo | todo |
| `/api/positions` (GET y POST, incluido `/api/positions/<id>/…`) | 402 | sí | sí | sí |
| `/api/memes`, `/api/memes/radar` | 402 | sí | sí | sí |
| `/api/telegram/link` | 402 | sí | sí | sí |
| `/api/backtest/results` | 402 | 402 | sí | sí |
| `/api/paper/report` (experimental) | 403 | 403 | 403 | sí |
| `/api/admin/*`, `/api/scan`, `POST /api/settings`, `/api/telegram/test`, `/api/memes/check` | 403 | 403 | 403 | sí |

Un plan de pago vencido (`plan_until` en el pasado) vuelve a Libre de inmediato.

## 3. Migraciones y esquema

- `db.migrate()` solo añade una columna si falta. El único error tolerado es «la columna ya existe» (por ejemplo,
  otra instancia la añadió a la vez). Cualquier otro error detiene el arranque con `SchemaError`.
- `db.verify_schema()` comprueba todas las columnas que el servidor necesita (`db.REQUIRED`). Si falta alguna, el
  servidor no arranca y dice cuál.
- En Render, el modo cuentas sin `DATABASE_URL` no arranca, porque el disco efímero borraría cuentas, sesiones,
  pagos y límites. Solo para pruebas se puede forzar con `CRYPTO_RADAR_ALLOW_SQLITE=1`.

## 4. Límites de intentos

### Cómo funcionan ahora
- Se guardan en la tabla `rate_limits` de la misma base (PostgreSQL en producción). Por eso **sobreviven a los
  reinicios y despliegues**, y se comparten entre instancias que usen la misma base.
- La clave se guarda con hash SHA-256; no queda la IP en claro.
- Límites:
  - inicio de sesión: 20 intentos cada 15 min por IP;
  - solicitudes de acceso: 3 por hora por IP y 60 por hora en total;
  - bloqueo de cuenta: 5 fallos seguidos bloquean 15 min, guardado en la fila del usuario.
- Además, hay un tope de 300 solicitudes pendientes.

### Limitaciones conocidas
1. **Ventana fija.** El contador se reinicia al empezar cada ventana. En el borde entre dos ventanas, un atacante
   puede hacer hasta el doble del límite en poco tiempo (por ejemplo, 40 intentos de inicio de sesión en un minuto
   alrededor del cambio de ventana).
2. **Por IP.** Un atacante con muchas IP (botnet, proxies) reparte los intentos. El bloqueo por cuenta (5 fallos)
   limita el ataque a una cuenta concreta, pero no el «password spraying» de una clave contra muchas cuentas.
3. **IP detrás del proxy.** Se usa la última dirección de `X-Forwarded-For`, la que añade el proxy de Render. Si se
   cambia de proveedor o se añade otro proxy (Cloudflare), hay que revisar `Handler._client_ip`.
4. **Respaldo en memoria.** Si la base falla, el límite usa un contador en memoria del proceso: sigue limitando, pero
   se pierde al reiniciar. El registro muestra `AVISO: límite de intentos en memoria`.
5. **Bloqueo de cuenta como denegación de servicio.** Cualquiera que conozca un usuario puede bloquearlo 15 minutos
   con 5 claves malas. Es el compromiso habitual; el administrador puede seguir entrando pasado ese tiempo o
   restablecerse con `CRYPTO_RADAR_ADMIN_RESET`.
6. **Sin CAPTCHA ni verificación de correo** en la solicitud de acceso. El administrador revisa cada solicitud a mano.

### Propuesta para producción
- **Ya hecho:** persistencia compartida en PostgreSQL (Neon), suficiente para una o varias instancias de Render.
- **Siguiente paso recomendado (cuando haya tráfico real):**
  - poner Cloudflare (plan gratis) delante del dominio, con una regla de *rate limiting* para `/api/auth/*`;
  - añadir Turnstile (CAPTCHA gratuito de Cloudflare) en «Solicitar acceso».
  Así se frena el abuso antes de llegar al servidor.
- **Si se escala a muchas instancias o mucho tráfico:**
  - mover los contadores a Redis (por ejemplo, Upstash gratis) con ventana deslizante (`INCR` + `EXPIRE`, o `ZSET`
    por marca de tiempo);
  - añadir un límite global de inicios de sesión fallidos por minuto para frenar el *password spraying*.
- **Para el administrador:** ~~activar un segundo factor (TOTP)~~ hecho: ver la sección 6.

## 5. Otras medidas

- Contraseñas con scrypt (n=2^14, r=8, p=1) y sal aleatoria. Comparación en tiempo constante. Mismo tiempo y mismo
  mensaje si el usuario no existe.
- Sesión en cookie `HttpOnly`, `SameSite=Lax` y `Secure` en HTTPS, con 14 días de vida. En la base solo se guarda
  el SHA-256 del token, que se rota en cada inicio de sesión.
- Cambiar o restablecer la contraseña, rechazar, desactivar o eliminar cierra todas las sesiones de esa cuenta.
- CSRF por sesión en cada POST autenticado. Mismo origen y JSON obligatorios. Cuerpo máximo de 64 KB.
- CSP estricta sin scripts en línea ni CDN, HSTS, COOP, `Permissions-Policy`, `nosniff` y `frame-ancestors 'none'`.

## 6. Verificación en dos pasos (TOTP)

- RFC 6238 (HMAC-SHA1, 30 s, 6 dígitos), compatible con Google Authenticator, Authy y 1Password. Implementación en
  `radar/totp.py` con la librería estándar; se prueba con los vectores oficiales del RFC.
- Se acepta el paso actual y uno a cada lado (±30 s). **Un código ya usado no vale otra vez**: se guarda el último paso
  aceptado con una actualización atómica (`totp_last_step`), así que dos peticiones simultáneas con el mismo código no
  pueden entrar las dos.
- Cada código incorrecto cuenta como fallo de inicio de sesión: 5 fallos bloquean la cuenta 15 minutos.
- **Administradores:** con `CRYPTO_RADAR_ADMIN_TOTP=required` (valor por defecto) un administrador sin TOTP solo puede
  entrar para activarlo. Todas las acciones de administración (`/api/admin/*`, escaneo manual, ajustes del sistema,
  concesión de planes, paper trading) responden 403 hasta que lo active. Un administrador no puede desactivarlo.
- Activar TOTP cierra todas las sesiones de esa cuenta: hay que volver a entrar con el siguiente código.
- Recuperación: `CRYPTO_RADAR_ADMIN_RESET=1` restablece la contraseña del entorno **y** borra el TOTP del administrador
  (hay que volver a activarlo). Restablecer la contraseña de un usuario desde el panel también borra su TOTP.
- El secreto TOTP se guarda en la base en claro (es necesario para calcular el código). Quien tenga la base o una copia
  de seguridad puede generar códigos: por eso las copias deben guardarse cifradas.

## 7. Pagos: modo off / sandbox / live

| `CRYPTO_RADAR_PAYMENTS` | Qué pasa |
| --- | --- |
| sin definir u `off` | Pagos desactivados aunque haya claves: checkout 503, webhooks 503 |
| `sandbox` | APIs de prueba (`sandbox.wompi.co`, `api-sandbox.nowpayments.io`). Una llave `pub_prod_` desactiva Wompi |
| `live` | APIs de producción y solo llaves `pub_prod_`. **No se activa en esta fase**; `preflight` lo marca como fallo |

Ya no existe la variable `WOMPI_API`: la URL del proveedor sale del modo y no se puede redirigir desde el entorno.
`python main.py payments-selftest` recorre el flujo completo por HTTP con un simulador local del proveedor (firma
válida, firma falsa, monto alterado, rechazo, repetición, modo off) y falla si alguna llamada sale hacia producción.

## 8. Copias de seguridad

`python main.py backup create|verify|compare|restore`, en `radar/backup.py`. Ver `docs/PRODUCCION_RENDER_NEON.md`.
Con `CRYPTO_RADAR_BACKUP_KEY` (32+ caracteres, guardada fuera de la copia) el manifiesto lleva un HMAC-SHA256 y
`verify`/`restore` rechazan copias sin firma o alteradas. **Sin esa clave los hashes solo detectan daños accidentales**:
quien pueda escribir en la copia también puede recalcularlos (auditoría del piloto, F-01).
La copia contiene datos personales, hashes de contraseñas y secretos TOTP: archivos con permisos 600, carpeta 700, y
debe guardarse cifrada y fuera del repositorio (`backups/` está en `.gitignore`). La restauración solo escribe en una
base vacía y nunca borra datos.

## 9. Auditoría final del piloto (resumen)

- Telegram: cada chat puede intentar 10 códigos de vinculación por hora (antes, sin límite).
- NOWPayments: la firma se comprueba sobre el JSON tal como lo serializa JavaScript (antes se rechazaban IPN
  legítimas con tildes o números en notación exponencial).
- Servidor con hilos fijos (`CRYPTO_RADAR_WORKERS`, 16) y cola de escucha de 128: sin conexiones rechazadas en ráfagas
  y como máximo una conexión a PostgreSQL por hilo. Reconexión automática si PostgreSQL/Neon corta la conexión.
- Detalle y evidencia: `docs/AUDITORIA_FINAL_PILOTO.md`.

