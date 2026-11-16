# Informe final de preparación del piloto cerrado · Crypto Radar 2.1.0

Fecha: 2026-11-15. Rama `claude/preparacion-piloto` (PR #8, apilado sobre #7).

Reglas de esta fase, cumplidas:
- **no** se desplegó, **no** se fusionó ningún PR y **no** se tocó producción;
- **no** se conectó a Neon real ni se usaron credenciales reales;
- **no** se activaron pagos;
- **no** se modificaron `research/`, `radar/quant/`, `radar/edge/`, `radar/paper_trading/` ni el ledger.

Todo lo ejecutado corrió sobre:
- bases temporales: SQLite en directorios temporales y un PostgreSQL 16.15 local desechable;
- una rama de integración local que se borró al terminar.

## 1. Veredicto

| | |
| --- | --- |
| **Estado técnico** | **PREPARADO PARA PILOTO.** No queda ningún bloqueante técnico |
| **Recomendación** | **NO-GO** hasta cerrar G-16 (texto legal de privacidad sin completar ni revisar) y las decisiones D-1 a D-5 |
| **Detalle** | `GO_NO_GO_PILOTO.md` (26 requisitos con evidencia) |

Lo local **no** valida Render ni Neon. Siguen pendientes de autorización expresa, y nada de ello se ha hecho:
- el preflight real;
- la primera copia real;
- el TOTP del administrador en producción;
- la prueba de 10 usuarios en Render;
- el historial de Neon;
- la IP real del usuario.

## 2. Estado inicial (verificado en el repositorio)

- **Producción:** `main` = `9176b36`, la 2.0.0, en modo de un solo usuario.
- **PR #3 a #7:** abiertos, apilados linealmente y sin CI en GitHub. #7 = `27f23e3` con 291 / 29 / 39 pruebas en verde.
- **Repositorio:** **público** según la API de GitHub.
- **Hallazgo principal de partida (N-01, ya era R-22):** al migrar una base de la 2.0.0, sus usuarios seguían
  **activos** en la 2.1 con su contraseña antigua. Eso contradice la decisión del responsable de no migrar usuarios.
- `render.yaml` dice `plan: free` (región Frankfurt). No se cambió: el plan lo decide el responsable (D-1).

## 3. Cambios

| Fase | Cambio | Archivos |
| --- | --- | --- |
| A | **Plataforma nueva.** En el primer arranque de la 2.1, en una sola transacción con bloqueo:<br>• archiva en `legacy_archive` todo lo de la 2.0.0 (usuarios, sesiones, vínculos de Telegram, posiciones, pagos y actividad), **sin** hashes de contraseña, semillas TOTP, *tokens* de sesión, CSRF ni códigos;<br>• borra esas filas y limpia los límites de intentos;<br>• marca la base como `2.1`.<br>Es idempotente: una base 2.1 sin marca no se toca salvo con `CRYPTO_RADAR_PLATFORM_ADOPT=1` | `radar/db.py` |
| A | **Un único administrador.** En cada arranque, cualquier otro `is_admin` pierde el rol, queda rechazado y desactivado y se le cierran las sesiones. Si no queda exactamente uno, el servidor no arranca | `radar/auth.py` |
| A | Bloqueo consultivo de PostgreSQL alrededor del esquema, la migración y la inicialización: corrige F-10 | `radar/db.py` |
| B / D | **Arranque seguro.** Antes de abrir la base, `pilot.startup_errors()` bloquea:<br>• pagos `live` en el piloto, y `sandbox` en Render;<br>• claves cortas o iguales entre sí;<br>• en Render: falta de `CRYPTO_RADAR_TOTP_KEY`, `ADMIN_TOTP=optional`, `DATABASE_URL` sin `sslmode=require` o `ALLOW_SQLITE=1`.<br>Los mensajes nombran la variable, nunca su valor | `radar/pilot.py` (nuevo), `radar/server.py` |
| D | **Preflight** con etiquetas APROBADO / ADVERTENCIA / BLOQUEANTE, alineado con el arranque. Comprobaciones nuevas: clave de copias, claves independientes, piloto, Telegram y variables de un solo uso. Con `--db`, también la marca de plataforma y el número de administradores | `radar/preflight.py` |
| C | Las copias incluyen `platform_meta` y `legacy_archive`. Se rechaza una copia sin ellas | `radar/backup.py` |
| F | Aviso «Piloto cerrado» en `/entrar`, en precios y en la app. «Solicitar acceso al piloto». Ninguna promesa de rentabilidad | `web/entrar.html`, `web/landing.html`, `web/app.js` |
| G | Pagos imposibles en el piloto: `live` → `off`, y `status()` informa del piloto | `radar/billing.py` |
| H | Política de privacidad: campos `COMPLETAR` para representante legal, teléfono y plazos de conservación; además, piloto, Telegram, archivo de la 2.0.0, prórrogas de plazos y requisito de procedibilidad ante la SIC. **No** se inventó ningún dato del responsable | `web/privacidad.html`, `docs/POLITICA_PRIVACIDAD_BORRADOR.md` |
| E | La prueba de 10 usuarios exige 0 respuestas 5xx, 0 respuestas 429 y 0 peticiones > 2 s. Añade inicio de sesión escalonado (`--escalonar`) | `tests/piloto/prueba_render_10.py` |
| Pruebas | Nuevas: `T30_PlataformaNueva` (7), `T31_CopiasExtremos` (6) y `T32_PagosPiloto` (5). Script `tests/piloto/plataforma_nueva.py` (41 pasos). Se actualizaron las pruebas que codificaban el comportamiento antiguo de «conservar usuarios» | `tests/test_suite.py`, `tests/piloto/*` |
| Docs | `GO_NO_GO_PILOTO.md`, `PROCEDIMIENTO_LANZAMIENTO_PILOTO.md`, `PROCEDIMIENTO_ROLLBACK.md`, `POLITICA_PRIVACIDAD_BORRADOR.md`, `CONFIGURACION_RENDER_NEON.md`, `REGISTRO_USUARIOS_PILOTO.md`, este informe; `MATRIZ_RIESGOS_PENDIENTES.md` y `PLAN_INTEGRACION_GIT.md` actualizados | `docs/` |

## 4. Pruebas ejecutadas y resultados exactos

| Prueba | Resultado | Evidencia |
| --- | --- | --- |
| Integración #3 → #8 con *merge commits*, regresión completa en cada paso con Python 3.12 y 3.13, sobre PostgreSQL 16 | **0 conflictos** en los 6 pasos; el árbol resultante es idéntico a la rama en cada paso; todo en verde. La contraprueba con *squash* de #3 da conflictos en 14 archivos | `evidencia_piloto/preparacion/integracion_local_preparacion.txt` |
| `test_suite` en #8 | **309 OK** con 3.12 y con 3.13 (antes, 291 en #7) | ídem |
| `test_edge` / `test_paper` en cada paso | 29 OK / 39 OK | ídem |
| Código protegido (`research`, `radar/quant`, `radar/edge`, `radar/paper_trading`) | **Sin cambios** frente a `origin/main` | ídem |
| Plataforma nueva de extremo a extremo: esquema 2.0.0 exacto con datos, servidor real, SQLite y PostgreSQL, 4 arranques simultáneos | **41/41 OK** | `plataforma_nueva.json` |
| Migración desde `main`, bootstrap del administrador, copia inicial | **6/6**, **17/17** y **15/15** OK sobre PostgreSQL | `migracion_desde_main.txt`, `bootstrap_admin.txt`, `backup_inicial.txt` |
| Preflight con entorno inseguro tipo Render | **8 bloqueantes**, 2 advertencias, ningún secreto impreso | `preflight_tipo_render_inseguro.txt` |
| Preflight con entorno correcto tipo Render | Solo el bloqueante del texto legal (G-16) | `preflight_tipo_render_correcto.txt` |
| Carga local de 1 a 50 usuarios, y emulación de 0,5 CPU | 0 respuestas 5xx en todos los niveles (detalle en §5) | `carga_1_50_*.json` |
| Ensayo de 10 usuarios a 0,5 CPU, inicio de sesión escalonado | **APROBADA**. Inicio de sesión p95 110,9 ms; panel p95 9,3 ms | `prueba_10_ensayo_local.json` |
| Ensayo de 10 usuarios a 0,5 CPU, inicio de sesión en ráfaga | **APROBADA**. Inicio de sesión p95 1194 ms (máximo 1201 ms); panel p95 11,5 ms; 0 respuestas 5xx o 429 | `prueba_10_ensayo_local_rafaga.json` |

Casos de copias probados (`T31` y `backup_inicial.py`), todos rechazados o recuperados como se esperaba:
- sin clave;
- con otra clave;
- copia manipulada;
- copia incompleta;
- restauración interrumpida (excepción, y SIGKILL real en PostgreSQL): la base queda vacía y se puede repetir;
- restauración repetida;
- marca de plataforma conservada.

**RPO y RTO realistas:** RPO ≤ 24 h con la copia diaria propia, o de minutos si el incidente cae dentro de la ventana
de historial de Neon (sin verificar: G-23). RTO ≤ 30 min, contando los pasos manuales. La parte técnica mide < 20 s
en local; **no se midió en Render** (`PLAN_BACKUP_RECUPERACION.md`).

## 5. Rendimiento (local, NO es Render ni Neon)

Cada nivel duró 60 s, con un escaneo, Telegram y un corte de conexiones de PostgreSQL a los 30 s.

**Máquina local (4 CPU):**

| Usuarios | Panel p95 | Panel p99 | Inicio de sesión en ráfaga, p95 | Respuestas 5xx | RSS máx. |
| --- | --- | --- | --- | --- | --- |
| 1 | 16,5 ms | 70 ms | 52 ms | 0 | 99 MB |
| 5 | 15,1 ms | 121 ms | 98 ms | 0 | — |
| 10 | 20,5 ms | 142,5 ms | 183 ms | 0 | 139 MB |
| 20 | 26,1 ms | 144 ms | 324 ms | 0 | 346 MB |
| 50 | 35,7 ms | 265,5 ms | 772 ms | 0 | 348 MB |

En todos los niveles:
- 0 errores tras el corte;
- como máximo 19 conexiones de PostgreSQL;
- escaneos de 3,7 a 4,0 s.

**Emulación de Starter (0,5 CPU con cgroup):**

| Usuarios | Panel p95 | Panel máx. | Inicio de sesión en ráfaga, p95 | Respuestas 5xx |
| --- | --- | --- | --- | --- |
| 1 | 14,3 ms | — | — | 0 |
| 10 | 17,7 ms | 418 ms | 1130 ms | 0 |
| 20 | 25,1 ms | 621 ms | 2220 ms | 0 |
| 50 | 51,6 ms | 851 ms | 5621 ms | 0 |

**Hallazgo:** con 0,5 CPU, el límite es el **inicio de sesión simultáneo**, porque scrypt usa CPU a propósito. El panel
va sobrado. Con 20 o más usuarios entrando en el mismo segundo, el inicio de sesión pasa de 2 s. En un piloto real los
usuarios no entran todos a la vez, y con 10 en ráfaga sigue por debajo de 1,3 s. Para la fase 4 (50 usuarios) hay que
repetir la prueba en el plan real (`PROCEDIMIENTO_LANZAMIENTO_PILOTO.md` §10).

## 6. Hallazgos nuevos

| ID | Hallazgo | Estado |
| --- | --- | --- |
| N-01 / R-22 | La migración desde la 2.0.0 heredaba usuarios activos con su contraseña | **CERRADO**: plataforma nueva (fase A) |
| F-10 | Dos instancias que arrancan a la vez sobre PostgreSQL: una caía por un choque en el catálogo | **CERRADO**: bloqueo consultivo; 4 procesos sin errores |
| F-11 | Cambiar `CRYPTO_RADAR_ADMIN_USER` dejaba dos administradores | **CERRADO**: siempre queda uno |
| N-02 | Inicio de sesión en ráfaga lento con 0,5 CPU a partir de unos 20 usuarios simultáneos | MITIGADO (§5) |
| N-03 | Volver a la 2.0.0 con `CRYPTO_RADAR_ACCOUNTS=1` abriría el registro libre, y quien se registre con `CRYPTO_RADAR_ADMIN_EMAIL` sería administrador | Documentado: el rollback **restaura las variables de la 2.0.0** (`PROCEDIMIENTO_ROLLBACK.md` §2.1) |
| N-04 | Si la 2.1 arranca sobre la base de la 2.0.0, archiva sus cuentas y la 2.0.0 ya no puede usarlas | Por diseño. Por eso se recomienda una base nueva (D-2) o una rama de Neon previa |

## 7. Riesgos residuales

- **Inherente al modelo:** quien controle las variables de Render controla el administrador.
- **Copias:** van firmadas, no cifradas. Guardarlas cifradas es un procedimiento, no un control del código.
- **Proveedores de pago:** nunca se probaron en el sandbox real (R-03). Solo hace falta al salir del piloto.
- **Derechos de los titulares:** se atienden a mano (G-19). Hay que automatizarlos antes de la fase 3.
- **Registro:** al pedir acceso se revela si un nombre ya existe. Está limitado a 3 solicitudes por IP y hora.
- **Estrategia:** no tiene ventaja demostrada (R-12). Se presenta como herramienta de análisis, sin cifras de
  rentabilidad.
- **Sin CI en GitHub:** hay que repetir la regresión sobre el `main` final.

## 8. Validaciones que requieren acceso real (pendientes)

| ID | Validación | Procedimiento |
| --- | --- | --- |
| G-17 | Fusionar #3 a #8 con *merge commit* y desplegar una vez | Lanzamiento §1 y §5 |
| G-18 | `preflight --db` con las variables reales: 0 bloqueantes | Lanzamiento §3 |
| G-20 | Copia previa de la 2.0.0 y primera copia real de la 2.1 verificadas | `PLAN_BACKUP_RECUPERACION.md` §1 |
| G-22 | TOTP del administrador activo y código de alta borrado | `BOOTSTRAP_ADMIN.md` §3 |
| G-21 | Prueba de 10 usuarios en Render + Neon | Lanzamiento §8 |
| G-23 | Ventana de historial de Neon y restauración por rama | `PLAN_BACKUP_RECUPERACION.md` §6 |
| G-25 | IP real del usuario en el registro (R-14) y fuentes de datos desde Frankfurt (R-13) | Lanzamiento §7, H-9 |

## 9. Bloqueantes

**G-16:** la política de privacidad tiene 11 marcas `COMPLETAR`:
- razón social, NIT, domicilio, representante legal, correo, teléfono y plazos de conservación;
- además, falta la revisión de un abogado (Ley 1581 de 2012 y Decreto 1377 de 2013).

No se ha inventado ningún dato. **No** se declara cumplimiento legal.

## 10. Decisiones y autorizaciones humanas que faltan

1. **G-16:** los datos del responsable del tratamiento y la revisión jurídica escrita.
2. **D-1:** el plan de Render. Se recomienda Starter; hoy `render.yaml` dice `free`.
3. **D-2:** una base **nueva** en Neon para la 2.1, en una región cercana a Frankfurt.
4. **D-3:** quién hace la revisión legal y cuándo.
5. **D-4:** pasar el repositorio a **privado**.
6. **D-5:** fecha y hora del despliegue: un día laborable por la mañana (Bogotá), con 2 h libres.
7. El inventario de las variables actuales de la 2.0.0 en Render, guardado en el gestor de contraseñas.
8. Autorización expresa para:
   - desactivar el despliegue automático;
   - fusionar #3 → #8 con *merge commit*;
   - desplegar una vez;
   - hacer el bootstrap del TOTP;
   - hacer la primera copia real;
   - ejecutar la prueba de 10 usuarios.
