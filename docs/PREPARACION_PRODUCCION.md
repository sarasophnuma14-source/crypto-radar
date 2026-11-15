# Preparación para producción · Crypto Radar 2.1.0

Fecha: 2026-11-15 · Rama: `claude/auditoria-produccion` (PR #4, base `claude/project-thread-i8udp5`, PR #3).
No se desplegó, no se fusionó ningún PR, no se tocó producción, no se activaron pagos y no se cambiaron credenciales.
La estrategia cuantitativa, el paper trading y el ledger del holdout no cambian (comprobado con
`git diff --quiet HEAD -- research/edge/ledger/ledger.jsonl radar/paper_trading radar/edge radar/quant`).

## 1. Estado de Git y PR

| Rama | Commit de partida | PR | Estado |
| --- | --- | --- | --- |
| `main` | `9176b36` | #1 y #2 | fusionados antes de esta fase |
| `claude/project-thread-i8udp5` | `2d72a2b` | #3 → `main` | abierto, sin fusionar |
| `claude/auditoria-produccion` | `3beaf57` | #4 → rama del PR #3 | abierto, sin fusionar; este trabajo va encima |

Las 8 correcciones de la auditoría anterior (A-01 a A-08) siguen presentes y sus pruebas (`T20_AuditoriaProduccion`)
pasan.

## 2. Cambios

| # | Prioridad | Qué se hizo | Cómo se verifica |
| --- | --- | --- | --- |
| 4 | Copias de seguridad | `radar/backup.py` + `main.py backup create\|verify\|compare\|restore`. Hash SHA-256 por tabla y del manifiesto, lectura consistente (REPEATABLE READ), restauración solo en bases vacías y comprobación fila a fila al terminar | `T23_Backup` (6 pruebas, incluida ida y vuelta SQLite ↔ PostgreSQL real) |
| 5 | TOTP | `radar/totp.py` (RFC 6238). Login en dos pasos, alta con contraseña y código, activar cierra sesiones, códigos de un solo uso guardados de forma atómica, fallos cuentan para el bloqueo. Obligatorio para administradores: sin TOTP, 403 en toda acción de administración. `ADMIN_RESET` y el restablecimiento desde el panel lo borran | `T21` (10 pruebas, con vectores oficiales del RFC) + recorrido real en Chromium |
| 6 | Pagos sandbox | `CRYPTO_RADAR_PAYMENTS=off\|sandbox\|live`, por defecto `off`. Sandbox solo con APIs y llaves de prueba. Eliminada la variable `WOMPI_API`. `main.py payments-selftest` | `T22_ModoPagos` (6 pruebas) + autoprueba de extremo a extremo: 16 de 16 pasos OK |
| 7 | Render y Neon | `main.py preflight [--db]` y `docs/PRODUCCION_RENDER_NEON.md`. `render.yaml` fija `CRYPTO_RADAR_ADMIN_TOTP=required` y `CRYPTO_RADAR_PAYMENTS="off"` | `T24_Preflight` (5 pruebas, incluida que la salida no muestra secretos) |
| 8 | Secretos | Búsqueda en el árbol actual y en las 40 confirmaciones de todas las ramas | Sección 4 |
| 9 | Textos legales | `/privacidad` (borrador Ley 1581 de 2012) y `/aviso-de-riesgo`. La solicitud de acceso exige aceptarlos y guarda versión y fecha | `T21` (consentimiento y páginas públicas sin scripts, con CSP) |

## 3. Archivos

Nuevos: `radar/totp.py`, `radar/backup.py`, `radar/preflight.py`, `radar/payments_selftest.py`,
`web/privacidad.html`, `web/aviso-de-riesgo.html`, `docs/PRODUCCION_RENDER_NEON.md`, `docs/PREPARACION_PRODUCCION.md`.

Modificados: `radar/auth.py`, `radar/billing.py`, `radar/db.py` (5 columnas nuevas en `users`, solo se añaden si
faltan), `radar/server.py`, `radar/webapi.py`, `main.py`, `render.yaml`, `.gitignore`, `web/app.js`,
`web/entrar.html`, `web/entrar.js`, `web/index.html`, `web/landing.html`, `web/style.css`, `tests/test_suite.py`,
`docs/SEGURIDAD.md`, `docs/INSTALACION_Y_DESPLIEGUE.md`, `CHANGELOG.md`.

## 4. Pruebas ejecutadas

PostgreSQL 16 local en `127.0.0.1:55432` (base de pruebas, no la de producción).

```bash
export TEST_DATABASE_URL=postgresql://radar@127.0.0.1:55432/radar
python3.12 tests/test_suite.py -v      # Python 3.12.3: 231 pruebas, OK, 0 omitidas
python3.13 tests/test_suite.py -v      # Python 3.13.18: 231 pruebas, OK, 0 omitidas
python3.12 tests/test_edge.py          # 29 OK (y también con 3.13)
python3.12 tests/test_paper.py         # 39 OK (y también con 3.13)
python3.12 main.py payments-selftest   # 16/16 pasos OK, RESULTADO: TODO OK
node --check web/app.js web/entrar.js  # sin errores de sintaxis
```

Antes de esta fase la suite tenía 204 pruebas; se añadieron 27. Recorrido en el navegador (Chromium sin interfaz,
servidor local con base temporal): el administrador entra, ve el aviso obligatorio, `/api/admin/users` responde 403,
activa TOTP con su app, vuelve a `/entrar`, se le pide el código, entra y `/api/admin/users` responde 200. Sin
errores de JavaScript.

Búsqueda de secretos (patrones de tokens de Telegram, llaves `pub_prod_`/`prv_`, secretos de Wompi, URL de PostgreSQL
con contraseña, claves de AWS, GitHub, Slack y Neon, claves privadas y archivos `.env`, `.pem`, `.db`):
- historial completo: solo el ejemplo `postgresql://usuario:clave@host` de la documentación;
- árbol actual: solo valores ficticios de las pruebas y la autoprueba (`pub_test_selftest`, `SuperSecretaDB99`…);
- ningún archivo de datos ni `.env` se ha versionado nunca.

## 5. Vulnerabilidades encontradas y corregidas en esta fase

| ID | Gravedad | Hallazgo | Corrección |
| --- | --- | --- | --- |
| P-01 | Alta | Con solo la contraseña del administrador se controlaba todo: aprobar cuentas, dar planes, cambiar ajustes | TOTP obligatorio para administradores; 403 hasta activarlo |
| P-02 | Media | Bastaba con que existieran las claves de un proveedor para que los cobros quedaran activos, en producción por defecto | Modo explícito, `off` por defecto y fijado en `render.yaml` |
| P-03 | Media | `WOMPI_API` se podía apuntar a cualquier servidor, que «confirmaría» pagos falsos; y se podían mezclar llaves de prueba con la API de producción | URL fija según el modo; llaves comprobadas por prefijo |
| P-04 | Media | No había forma de hacer ni comprobar copias de la base de usuarios y pagos | Herramienta de copias con verificación por hash y restauración probada |
| P-05 | Baja | No se guardaba la autorización para tratar datos personales (Ley 1581 exige poder probarla) | Casilla obligatoria; se guardan versión y fecha |
| P-06 | Baja | Los enlaces «Privacidad» y «Aviso de riesgo» de la web de ventas llevaban a `#preguntas` | Páginas reales enlazadas desde la web de ventas y `/entrar` |

## 6. Riesgos pendientes

1. **Textos legales:** faltan los datos del responsable (6 marcas `COMPLETAR`) y la revisión de un abogado.
   `preflight` falla hasta que se completen.
2. **Pagos reales en sandbox sin probar:** no hay llaves de prueba de Wompi ni de NOWPayments en este entorno. El
   flujo se probó con un simulador; falta un pago en el sandbox real de cada proveedor.
3. **Secreto TOTP en claro en la base:** quien obtenga la base o una copia puede generar códigos. Mitigación: copias
   cifradas. Mejora futura: cifrarlo con una clave del entorno.
4. **Recuperación del administrador** depende del acceso a las variables de Render (`CRYPTO_RADAR_ADMIN_RESET`).
5. **Límites de intentos:** ventana fija, por IP, sin CAPTCHA (ver `docs/SEGURIDAD.md`, sección 4).
6. **Copias:** la rutina es manual; el historial de Neon depende del plan. Nadie ha hecho aún una copia de la base real.
7. **Render gratis:** se duerme sin visitas; el escáner corre en el proceso web, así que debe haber una sola instancia.
8. **Producción** sigue en la v2.0.0 de un solo usuario. Los PR #3 y #4 están sin fusionar.
9. Si el repositorio es público, el código y el correo del autor en los commits son visibles (no hay secretos).

## 7. Estado de preparación

**APTO CON RESTRICCIONES para un piloto cerrado** con usuarios aprobados a mano y pagos desactivados.
**No apto todavía para abrir al público ni para cobrar.** Antes hacen falta los puntos 1 y 2, activar el TOTP del
administrador en producción, una copia verificada de la base real y `python main.py preflight --db` sin fallos.
