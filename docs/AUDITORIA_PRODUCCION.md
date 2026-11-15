# Auditoría integral previa a producción — Crypto Radar 2.1.0

- **Fecha:** 2026-11-15.
- **Base auditada:** `2d72a2b2e207ae74ba49057252a9098d49e9f52d` (PR #3).
- **Rama de la auditoría:** `claude/auditoria-produccion`.
- **Alcance:** revisión manual del código real de `radar/` (server, webapi, auth, db, billing, telegram_bot, multiuser, storage, config, paper_trading), `web/`, `render.yaml`, `requirements.txt` y del historial de git. Cada vulnerabilidad se reprodujo en local, con datos de prueba, en bases temporales: SQLite en directorios temporales y un PostgreSQL 16.15 local de pruebas. **No se tocó ninguna base real, Render ni producción.**

## A. Resumen ejecutivo

| Aspecto | Estado |
| --- | --- |
| Estado general | Base sólida: hashes scrypt, sesiones con hash, CSRF, permisos en el backend, pagos verificados con firma y API, sin código de órdenes reales |
| Hallazgos comprobados | 8 (0 críticos, 0 altos, 4 medios, 4 bajos), **todos corregidos** con una prueba que los reproduce |
| Riesgos pendientes | Pagos sin probar en sandbox real, plan gratis de Render, copias de seguridad sin verificar, sin segundo factor para el administrador, repositorio público |
| Evaluación | **APTO CON RESTRICCIONES** (ver F) |

No se encontró ninguna vía para:
- hacerse administrador;
- activar un plan sin pago verificado;
- leer datos de otro usuario;
- saltarse la autenticación;
- enviar órdenes reales.

## B. Hallazgos comprobados

Las líneas se refieren a `2d72a2b`, antes de la corrección. Cada prueba está en `tests/test_suite.py`, clase `T20_AuditoriaProduccion`. Ejecutadas contra el código anterior, las 8 pruebas de hallazgos fallan (6 fallos y 2 errores); con la corrección pasan.

| ID | Vulnerabilidad | Gravedad | Archivo | Líneas | Evidencia | Impacto | Corrección |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A-01 | `Content-Length` negativo o no numérico salta el límite de 64 KB | MEDIO | radar/server.py | 152, 160-174 | `Content-Length: -1` con 200 KB devolvió **401** (cuerpo procesado); el mismo cuerpo con longitud real devolvió 413. `rfile.read(-1)` lee hasta que el cliente cierra | Sin sesión, un atacante puede agotar la memoria de la instancia (512 MB en el plan gratis). El proxy de Render probablemente rechaza longitudes negativas; no se pudo comprobar | `_content_length()` solo acepta dígitos. Si no es válida, responde 413 sin leer el cuerpo |
| A-02 | Conexiones ociosas abiertas para siempre (sin `timeout`) | MEDIO | radar/server.py | 115 | Un socket abierto sin enviar nada seguía conectado a los 12 s | Agotamiento de hilos del servidor (tipo slowloris) | `Handler.timeout = 30` |
| A-03 | El bot de Telegram entrega datos sin cuenta aprobada y a cuentas desactivadas | MEDIO | radar/telegram_bot.py, radar/multiuser.py | tg 52-54, 70, 92; mu 87 | Un chat no vinculado recibió con `/top` el ranking con zonas, stop y TP1. Una cuenta Pro **desactivada** siguió viendo su cartera (`/cartera`) y el top | Salta el acceso «solo con aprobación» y la desactivación del administrador | Solo se atiende a cuentas activas (no pendientes, rechazadas ni desactivadas). Los comandos con datos exigen chat vinculado. `/start` rechaza códigos de cuentas no activas. Las alertas de salida comprueban lo mismo |
| A-04 | Doble concesión de plan ante entregas simultáneas del mismo webhook | MEDIO | radar/billing.py | 88-100 | Dos llamadas a `_grant` con el mismo pago leído antes de escribir: ambas devolvieron `True` y el plan quedó en **60 días en vez de 30** | Días de plan sin pagar si Wompi o NOWPayments reintentan a la vez. No lo puede forzar un usuario (las firmas son válidas) | Solo se extiende el plan si el `UPDATE … AND verified = 0` afectó a 1 fila (`rowcount`). Probado en SQLite y en PostgreSQL |
| A-05 | El nombre del informe de paper trading se usa como ruta sin validar | BAJO | radar/server.py | 398-404 | `paper_report("../../etc")` construía `data/paper/../../etc` | Lectura de `spec.json`, `state.json` o `*.jsonl` fuera de la carpeta, solo para el administrador o con la contraseña del modo de un usuario | Nombre restringido a `^[A-Za-z0-9_-]{1,40}$` |
| A-06 | El mensaje de bloqueo revela qué usuarios existen | BAJO | radar/auth.py | 321-330 | Tras 6 intentos: usuario real → `429 Cuenta bloqueada…`; inexistente → `401 Usuario o contraseña incorrectos` | Enumeración de cuentas, que facilita ataques dirigidos | Los usuarios inexistentes también «se bloquean» tras 5 fallos (contador en `rate_limits`), con la misma respuesta |
| A-07 | `admin_grant` con días no numéricos da error 500 | BAJO | radar/billing.py | 187 | `int("muchos")` lanzaba `ValueError` | Error interno en una ruta de administración | Responde 400 |
| A-08 | Usuario duplicado en carrera da error 500 | BAJO | radar/auth.py | 144-150 | Dos `INSERT` con el mismo usuario: el segundo lanzaba la excepción de `UNIQUE` | Error 500 y ruido en los registros; la base impedía el duplicado | Si la fila ya existe, responde 409 |

### Observaciones y riesgos sin vulnerabilidad demostrada (no corregidos)

| ID | Observación | Gravedad | Detalle |
| --- | --- | --- | --- |
| R-01 | Pagos nunca probados con un comercio real ni en sandbox | ALTO (riesgo) | El código verifica la firma, vuelve a consultar la API y compara referencia, monto y moneda. Las pruebas usan respuestas simuladas, así que **no hay evidencia con Wompi ni NOWPayments reales** |
| R-02 | Plan gratis de Render | MEDIO | Una sola instancia, que se duerme sin KEEPALIVE. Sin réplicas ni alertas de caída. El disco es efímero (mitigado: en modo cuentas no arranca sin PostgreSQL) |
| R-03 | Copias de seguridad de PostgreSQL | MEDIO | No hay ninguna en el código. Depende de la retención de Neon, que no se verificó |
| R-04 | Administrador sin segundo factor (TOTP) | MEDIO | Una contraseña filtrada da control total del panel. Mitigación actual: 12 caracteres o más, bloqueo tras 5 fallos y límites por IP |
| R-05 | Repositorio público | MEDIO | No contiene secretos (revisado en el código y en todo el historial), pero expone el código, la investigación y los resultados |
| R-06 | Sesiones de 14 días sin caducidad por inactividad; las filas vencidas no se borran | BAJO | La sesión caduca a los 14 días y se invalida al cambiar o restablecer la contraseña, desactivar o rechazar |
| R-07 | La CSP permite estilos en línea (`style-src 'unsafe-inline'`) | BAJO | Los scripts sí son estrictos (`script-src 'self'`) |
| R-08 | `/healthz` es público y muestra `last_error` (300 caracteres) y las fuentes de datos | BAJO | No se vio ningún secreto en esos mensajes. Conviene limitarlo si se añaden integraciones con claves en la URL |
| R-09 | El webhook de Wompi no comprueba la antigüedad del evento | BAJO | Reenviar un evento no tiene efecto: el pago es idempotente y se vuelve a consultar en la API |
| R-10 | La firma de NOWPayments se calcula sobre el JSON ya interpretado | INFORMATIVO | Si NOWPayments serializa los decimales distinto, un pago legítimo podría rechazarse (falso negativo); nunca se aceptaría uno falso |
| R-11 | Enumeración por «Solicitar acceso» (409 «no disponible») | INFORMATIVO | Es inherente a que cada persona elija su usuario. Limitada a 3 por hora por IP y 60 por hora en total |
| R-12 | Datos personales (IP, navegador, contacto) en `activity` y `sessions` | INFORMATIVO | Antes de abrir al público: política de privacidad y autorización de tratamiento de datos (Ley 1581 de 2012 en Colombia) |
| R-13 | Al eliminar un usuario quedan sus posiciones, pagos y actividad | INFORMATIVO | No se cambió, porque la restricción era no eliminar información |
| R-14 | `HEAD` responde 501 | INFORMATIVO | El health check de Render usa GET; algunos monitores externos usan HEAD |
| R-15 | El producto no tiene ventaja estadística demostrada | INFORMATIVO (financiero) | Ver `research/edge/INFORME_VENTAJA.md` y `AUDITORIA_D_VOLMOM.md`. No se debe vender con cifras de rentabilidad ni presentar señales como recomendación |

## Matriz de rutas (modo cuentas)

- **Sesión:** sesión obligatoria (sin ella, 401).
- **CSRF:** cabecera `X-CSRF-Token` con el token de la sesión, más mismo origen y JSON.
- **Resultado:** el comportamiento que dan las pruebas automáticas (`test_entitlements_matrix`, `test_every_api_route_requires_session_unless_public`, `T13`, `T18`, `T19`, `T20`).

| Endpoint | Método | Autenticación | Permiso requerido | Riesgo | Resultado |
| --- | --- | --- | --- | --- | --- |
| `/`, `/entrar`, `/static/*` | GET | Pública | — | Bajo | OK (sin JS en línea, ruta limitada a `web/`) |
| `/app` | GET | Sesión (si no, 302 a `/entrar`) | Cuenta activa | Bajo | OK |
| `/healthz` | GET | Pública | — | Bajo (R-08) | OK |
| `/api/public/status`, `/api/billing/status` | GET | Pública | — | Bajo | OK (sin datos de usuarios) |
| `/api/me`, `/api/state`, `/api/activity`, `/api/billing/payments` | GET | Sesión | Cuenta activa; `state` filtrado por plan; actividad y pagos solo los propios | Medio | OK |
| `/api/alerts`, `/api/journal`, `/api/scans`, `/api/candles`, `/api/history` | GET | Sesión | Libre: solo su top | Medio | OK |
| `/api/positions` | GET/POST | Sesión (+CSRF en POST) | Pro | Medio (IDOR) | OK: consulta con `user_id`; otro usuario → 404 |
| `/api/positions/<id>/<acción>` | POST | Sesión + CSRF | Pro, y propietario | Medio (IDOR) | OK |
| `/api/memes`, `/api/memes/radar` | GET | Sesión | Pro | Bajo | OK |
| `/api/backtest/results` | GET | Sesión | Élite | Bajo | OK (402 si no) |
| `/api/paper/report` | GET | Sesión | Admin | Bajo (A-05 corregido) | OK |
| `/api/settings` | GET | Sesión | Admin ve los del sistema (token enmascarado); el resto, los suyos | Medio | OK |
| `/api/settings`, `/api/scan`, `/api/telegram/test`, `/api/memes/check` | POST | Sesión + CSRF | Admin | Medio | OK (403) |
| `/api/me/settings` | POST | Sesión + CSRF | Propio; lista blanca de campos | Medio | OK: ignora `is_admin`, `plan` y `plan_until` |
| `/api/telegram/link` | POST | Sesión + CSRF | Pro | Medio (A-03) | OK |
| `/api/auth/request`, `/api/auth/register` | POST | Pública (mismo origen y JSON) | — | Medio | OK: queda pendiente, sin sesión; ignora `is_admin`, `status` y `plan` |
| `/api/auth/login` | POST | Pública (mismo origen y JSON) | — | Alto | OK: scrypt, bloqueo, límites persistentes, mismo mensaje (A-06) |
| `/api/auth/logout`, `/api/auth/logout_all`, `/api/auth/password` | POST | Sesión + CSRF | Propio | Medio | OK: invalida sesiones |
| `/api/billing/checkout` | POST | Sesión + CSRF | Propio | Alto | OK: el precio sale del servidor y el plan no cambia aquí |
| `/api/billing/wompi/webhook` | POST | Firma de Wompi | — | Alto | OK: firma, más consulta a la API, más referencia, monto y moneda; idempotente (A-04) |
| `/api/billing/nowpayments/ipn` | POST | HMAC-SHA512 | — | Alto | OK: igual que Wompi |
| `/api/admin/users` | GET | Sesión | Admin | Alto | OK |
| `/api/admin/user`, `/api/admin/user/create`, `/api/admin/user/password`, `/api/admin/grant` | POST | Sesión + CSRF | Admin; nunca sobre otro admin ni sobre sí mismo | Alto | OK |

## C. Correcciones realizadas

| Archivo | Cambio |
| --- | --- |
| `radar/server.py` | `Handler.timeout = 30` (A-02); `_content_length()` estricto, usado en `_body` y `_same_origin` (A-01); validación del nombre en `paper_report` (A-05) |
| `radar/telegram_bot.py` | `active()`; `_user_by_chat` solo devuelve cuentas activas; comandos con datos solo para chats vinculados; `/start` y `fanout` comprueban que la cuenta esté activa (A-03) |
| `radar/multiuser.py` | Las alertas de salida por Telegram exigen cuenta activa (A-03) |
| `radar/billing.py` | `_grant` comprueba `rowcount` (A-04); `admin_grant` valida los días (A-07) |
| `radar/auth.py` | Bloqueo aparente para usuarios inexistentes (A-06); `_create` responde 409 ante duplicado en carrera (A-08) |
| `tests/test_suite.py` | Nueva clase `T20_AuditoriaProduccion` con 12 pruebas: 8 reproducen los hallazgos y 4 son verificaciones generales (rutas sin sesión, tokens y contraseñas sin texto plano, campos de privilegio ignorados, ausencia de código de órdenes reales). `T17_Postgres` ahora también prueba A-04 y A-08 en PostgreSQL. `test_link_flow` ahora aprueba la cuenta antes de vincular y comprueba que una cuenta pendiente **no** puede vincular, que es el comportamiento nuevo correcto |
| `docs/AUDITORIA_PRODUCCION.md` | Este informe |

**Sin cambios:**
- estrategia (`radar/quant`, `radar/edge`);
- paper trading (`radar/paper_trading`);
- registro del holdout (`research/edge/ledger/ledger.jsonl`);
- resultados históricos;
- `render.yaml`;
- secretos.

## D. Pruebas

**Entorno:**
- Linux en un contenedor efímero.
- Python 3.13.18; Render usa 3.12.7 y no se probó con esa versión exacta.
- SQLite 3.53.1.
- PostgreSQL 16.15 local de pruebas en `127.0.0.1:55432`. No es Neon ni producción.

| Comando | Resultado | Pruebas | Fallos | Omitidas |
| --- | --- | --- | --- | --- |
| `TEST_DATABASE_URL=postgresql://radar@127.0.0.1:55432/radar python3 tests/test_suite.py -v` | OK | 204 | 0 | 0 |
| `python3 tests/test_suite.py` (sin PostgreSQL) | OK | 204 | 0 | 2 (las dos de PostgreSQL) |
| `python3 tests/test_edge.py` | OK | 29 | 0 | 0 |
| `python3 tests/test_paper.py` | OK | 39 | 0 | 0 |
| `python3 tests/test_suite.py T20_AuditoriaProduccion` con los archivos de `2d72a2b` (contraprueba) | FAILED | 12 | 8 (6 fallos, 2 errores), una por cada hallazgo A-01…A-08 | 0 |

Durante el trabajo hubo dos fallos intermedios que **no** eran vulnerabilidades:
- `test_link_flow` vinculaba una cuenta pendiente. La prueba se ajustó para reflejar la regla nueva.
- En `test_a01`, el cliente de prueba no toleraba que el servidor cerrara la conexión tras responder 413.

Las cuatro suites se volvieron a ejecutar completas tras esos ajustes, con los resultados de la tabla.

**Regresión cubierta por las suites:**
- solicitud, aprobación y rechazo de cuentas;
- inicio y cierre de sesión;
- restablecimiento y cambio de contraseña;
- permisos por plan y panel de administración;
- migraciones desde el esquema antiguo;
- límites de intentos tras reinicio;
- alertas, diario, historial, escaneos con datos sintéticos y paper trading;
- PostgreSQL.

**No ejecutado:**
- escaneos con datos reales de mercado, porque la red del contenedor no llega a las APIs;
- navegador en producción;
- pagos reales o en sandbox.

## E. Riesgos pendientes y aspectos no verificados

1. Pagos con Wompi y NOWPayments reales o en sandbox (R-01). **Mantener los pagos desactivados** (sin claves) hasta probarlos.
2. Si el proxy de Render deja pasar `Content-Length` negativo. Ya no importa tras A-01, pero no se observó.
3. Retención y restauración de copias de Neon (R-03).
4. Comportamiento con varias instancias. El código es compatible, porque límites y sesiones están en la base, pero no se probó.
5. Python 3.12.7 (versión de Render) frente al 3.13.18 usado en las pruebas.
6. Producción actual: Render sigue con la 2.0.0 en modo de contraseña única. Esta auditoría no lo modificó.

## F. Evaluación final: **APTO CON RESTRICCIONES**

**Justificación:**
- No quedan vulnerabilidades comprobadas sin corregir.
- Los controles críticos están en el backend y probados, también contra PostgreSQL real:
  - administrador obligatorio e imposible de suplantar;
  - permisos por plan;
  - aislamiento entre usuarios;
  - CSRF;
  - sesiones con hash e invalidación;
  - límites persistentes;
  - pagos idempotentes.
- Aun así, no es «apto para producción» sin condiciones, porque faltan comprobaciones que el código no puede dar.

**Restricciones para operar:**
1. Beta cerrada con usuarios aprobados a mano y **pagos desactivados** hasta probar Wompi y NOWPayments en sandbox (R-01).
2. `CRYPTO_RADAR_ACCOUNTS=1` con `DATABASE_URL` de Neon y copia de seguridad verificada (R-03).
3. Contraseña de administrador larga y exclusiva; añadir TOTP antes de cobrar (R-04).
4. Repositorio privado antes de abrir al público (R-05).
5. Política de privacidad y aviso de riesgo visibles. No presentar señales como recomendación ni prometer rentabilidad (R-12, R-15).
6. Plan de pago de Render, o aceptar explícitamente las caídas del gratuito, antes de tener clientes que pagan (R-02).

## G. GitHub

- Rama: `claude/auditoria-produccion`, creada desde `2d72a2b`. No se tocaron `main` ni la rama del PR #3.
- El PR de esta auditoría apunta a `claude/project-thread-i8udp5` (la rama del PR #3) y **no se fusiona**.
- No hubo despliegues ni cambios en Render, en secretos ni en bases reales.
