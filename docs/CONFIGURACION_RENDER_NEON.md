# Configuración de producción: Render + Neon · Crypto Radar 2.1.0 (piloto cerrado)

Fecha: 2026-11-15. **Preparada sin conectarse a Render ni a Neon** (regla de esta fase). Todo lo que sigue sale del
código y de pruebas locales. Lo que solo se puede comprobar con acceso real está marcado **[VALIDAR EN REAL]**.

## 1. Cómo se valida

- **`python main.py preflight`** solo lee variables y archivos. Cada comprobación sale como **APROBADO**,
  **ADVERTENCIA** o **BLOQUEANTE**. Devuelve código 1 si hay algún bloqueante, y entonces termina con
  «NO listo para producción». Nunca muestra valores secretos ni la URL completa de la base (prueba
  `test_output_never_shows_secrets`).
- **`python main.py preflight --db`** añade comprobaciones de solo lectura sobre la base:
  - sesión con `default_transaction_read_only`;
  - esquema completo;
  - marca de plataforma 2.1;
  - un único administrador y su TOTP;
  - secretos TOTP cifrados y legibles;
  - códigos de alta sin usar.
- **El arranque** (`main.py serve`) aplica las mismas reglas de `radar/pilot.py` **antes de abrir la base**. Si hay un
  bloqueante, el servidor no arranca y dice qué variable falla, nunca su valor (pruebas
  `T30…insecure_config_blocks_startup_without_leaking` y `T30…serve_refuses_before_touching_the_database`).

Evidencia: `docs/evidencia_piloto/preparacion/preflight_*.txt`.

## 2. Variables

Leyenda de la columna «Si falta o es incorrecta»:
- **B**: bloquea el arranque y el preflight.
- **P**: el preflight lo marca BLOQUEANTE, pero el servidor arranca.
- **A**: ADVERTENCIA.

| Variable | Valor en Render | Dónde se define | Si falta o es incorrecta |
| --- | --- | --- | --- |
| `CRYPTO_RADAR_ACCOUNTS` | `1` | Render (*sync: false*) | P (sin modo cuentas no hay piloto) |
| `DATABASE_URL` | URL **directa** de Neon (sin `-pooler`) con `sslmode=require` | Render (*sync: false*) | B si no es PostgreSQL en Render o le falta `sslmode=require`; A si es `-pooler` |
| `CRYPTO_RADAR_ADMIN_USER` / `_PASSWORD` | Usuario y contraseña de 12+ caracteres que no contenga el usuario | Render (*sync: false*) | B |
| `CRYPTO_RADAR_ADMIN_TOTP` | `required` (en `render.yaml`) | `render.yaml` | B si es `optional` en Render |
| `CRYPTO_RADAR_TOTP_KEY` | 32+ caracteres aleatorios | Render (*sync: false*) y un gestor de contraseñas | B si falta en Render o es corta |
| `CRYPTO_RADAR_BACKUP_KEY` | **No va en Render.** Solo en la máquina que hace las copias | Gestor de contraseñas | B si coincide con la clave TOTP o es corta; A si falta donde corre el preflight |
| `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` | Solo el día del alta del TOTP del administrador; luego se borra | Render (*sync: false*), temporal | A mientras siga definida |
| `CRYPTO_RADAR_PAYMENTS` | `off` (en `render.yaml`) | `render.yaml` | B si es `live` durante el piloto, o cualquier valor distinto de `off` en Render |
| `CRYPTO_RADAR_PILOT` | Sin definir: el piloto queda **cerrado** por defecto | — | A si es `abierto` |
| `MALLOC_ARENA_MAX` | `2` (en `render.yaml`) | `render.yaml` | A si no es 2 (pico de 419 MB en vez de 339 MB) |
| `TELEGRAM_BOT_TOKEN` | Token del bot, si se quieren alertas | Render (*sync: false*) | A: sin avisos por Telegram; el panel funciona igual |
| `CRYPTO_RADAR_TRUSTED_PROXIES` | Sin definir: en Render se confía en el proxy de Render | — | [VALIDAR EN REAL] que la IP registrada sea la del usuario (R-14) |
| `CRYPTO_RADAR_ADMIN_RESET`, `_TAKEOVER`, `CRYPTO_RADAR_PLATFORM_ADOPT` | **Sin definir.** Solo se usan una vez para recuperación (`BOOTSTRAP_ADMIN.md` §4) | — | P si se quedan puestas |
| `CRYPTO_RADAR_ALLOW_SQLITE` | **Sin definir** | — | B en Render |
| `CRYPTO_RADAR_TOTP_KEY_OLD` | Solo durante una rotación | Render, temporal | A |
| `KEEPALIVE`, `PYTHON_VERSION`, `CRYPTO_RADAR_HOST`, `healthCheckPath` | Ya en `render.yaml` (`1`, `3.12.7`, `0.0.0.0`, `/healthz`) | `render.yaml` | — |
| `WOMPI_*`, `NOWPAYMENTS_*`, `COP_PER_USD` | **Vacías** durante el piloto | — | Sin efecto con los pagos en `off` |

`render.yaml` no se ha cambiado en esta fase. Dos decisiones quedan para el responsable:
1. **Plan de Render.** `render.yaml` dice `plan: free`. Con 0,1 CPU, el servidor se satura a partir de 25 usuarios
   activos (R-19). Para el piloto se recomienda **Starter** (0,5 CPU, 512 MB). El ensayo emulado está en
   `INFORME_FINAL_PREPARACION_PILOTO.md` §5. Cambiar el plan tiene coste, así que lo decide el responsable.
2. **Disco efímero.** Con `DATABASE_URL` todo lo persistente va a Neon: cuentas, sesiones, límites de intentos,
   informes, diario y alertas, guardados como documentos `kv`. El disco de Render solo guarda cachés.

## 3. Neon

| Aspecto | Configuración | Evidencia | Pendiente |
| --- | --- | --- | --- |
| **Base** | Una base **nueva y vacía** para la 2.1.0. Es la opción recomendada: la 2.0.0 queda intacta donde está y no hay nada que archivar. Si se reutilizara la base de la 2.0.0, el primer arranque archivaría sus cuentas (`REGISTRO_USUARIOS_PILOTO.md` §1) | `plataforma_nueva.json` 41/41 | Decisión del responsable |
| **Endpoint** | **Directo**, no `-pooler`. Cada instancia abre como mucho unas 20 conexiones: 16 hilos más escáner, Telegram y arranque | Carga local: máximo 19 conexiones con 50 usuarios | [VALIDAR EN REAL] límite de conexiones del plan de Neon |
| **TLS** | `sslmode=require` es obligatorio. `verify-full` necesita el certificado raíz en Render | El arranque y el preflight lo comprueban | [VALIDAR EN REAL] negociación TLS |
| **Tiempo de espera** | `connect_timeout=10` por defecto (`radar/db.py`). Reintento corto de conexión, unos 3,75 s, para el «starting up» de Neon tras suspenderse | F-07 (estrés integral) | [VALIDAR EN REAL] tiempo de arranque en frío |
| **Conexiones caídas** | Si Neon cierra conexiones inactivas, se reconecta una vez; la sentencia no se repite si ya llegó a ejecutarse | `pg_terminate_backend` a los 30 s en cada tramo: 0 errores tras el corte | — |
| **Arranque simultáneo** | Un bloqueo consultivo (`pg_advisory_lock`) serializa esquema, migración y marca de plataforma | 4 procesos a la vez: una sola inicialización, 0 errores | — |
| **Historial** | Ventana de restauración por instante (*point in time*) según el plan | — | [VALIDAR EN REAL] (R-10) |

## 4. Salud, reinicios y persistencia

- **`/healthz`** responde sin sesión y sin datos privados: estado del escáner, último escaneo, último error recortado
  a 300 caracteres y fuentes. Render lo usa como *health check*.
- **Reinicio.** Al arrancar se verifican el esquema, la plataforma y el administrador, y se cifran los secretos TOTP
  que estuvieran en claro. Reiniciar no reactiva cuentas antiguas ni crea administradores duplicados
  (`plataforma_nueva.py`, pasos de reinicio).
- **Despliegue sin corte de Render.** Durante unos segundos conviven la instancia vieja y la nueva. Las dos usan la
  misma base y el bloqueo consultivo evita choques. Los límites de intentos están en la base y se comparten.
- **Persistencia.** Va en Neon:
  - cuentas, sesiones (hash), actividad, pagos, vínculos de Telegram, límites de intentos y códigos de alta;
  - marca de plataforma y archivo de la 2.0.0;
  - documentos del escáner (`kv`).

  No va en Neon: las cachés de mercado, que se regeneran.

## 5. Secretos

- Nunca aparecen en el registro, en `/healthz`, en el preflight ni en los mensajes de error del arranque. La URL de la
  base se muestra enmascarada. Pruebas: `test_no_secrets_in_responses_or_logs`, `test_output_never_shows_secrets` y
  `T30…without_leaking`.
- `render.yaml` no contiene valores secretos: todas las variables sensibles son *sync: false*, y el preflight lo
  comprueba.
- Rotación y recuperación de claves: `PROTECCION_SECRETOS.md` §4–5.

## 6. Pagos durante el piloto

- `CRYPTO_RADAR_PAYMENTS=off` en Render.
- **`live` está prohibido mientras el piloto esté cerrado.** El arranque se niega, y aunque alguien se saltara el
  arranque, `billing.payments_mode()` devuelve `off`.
- El **sandbox tampoco se permite en Render**: con tarjetas de prueba alguien obtendría un plan sin pagar.

Para probar los proveedores más adelante, en local o en un servicio de *staging* separado y nunca con la base del
piloto:
1. Credenciales de sandbox: Wompi `pub_test_…`, `prv_test_…` y los secretos de eventos e integridad; NOWPayments,
   la clave de la API de sandbox y el secreto IPN.
2. Ensayo sin red: `python main.py payments-selftest`. Recorre el flujo completo en un sandbox simulado sobre una
   base temporal. Después, el mismo flujo con las credenciales de sandbox reales en un servicio de pruebas.
3. Comprobar, con la consulta de verificación a la API del proveedor:
   - un pago aprobado concede el plan una sola vez;
   - un evento repetido no concede dos veces;
   - una firma alterada se rechaza;
   - un importe distinto se rechaza.

   Pruebas existentes: T14, T22 y T26.
4. Para `live` hacen falta:
   - el final del piloto (`CRYPTO_RADAR_PILOT=abierto`);
   - claves de producción;
   - la aprobación expresa del responsable;
   - una revisión de R-03, R-04 y R-05.
