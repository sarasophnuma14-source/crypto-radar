# Cierre de riesgos del piloto · Crypto Radar 2.1.0

Fecha: 2026-11-15. Rama `claude/cierre-riesgos`, PR #7 apilado sobre #6. Sin desplegar ni fusionar. No se ha tocado
producción ni ninguna base real. Los pagos siguen desactivados. La estrategia, el paper trading y el ledger no
cambian: `git diff origin/main -- research radar/quant radar/edge radar/paper_trading` sale vacío.

## 1. Veredicto

El código está listo para el piloto. Los riesgos de seguridad del administrador, del cifrado de secretos y de las
copias quedan **cerrados en código y con pruebas ejecutadas**. El apilado de PR se integra sin conflictos y con toda la
regresión verde en cada paso.

**El piloto todavía no puede abrirse.** Faltan:
- un bloqueante no técnico: el texto legal de privacidad (R-01);
- cuatro comprobaciones que solo se pueden hacer con acceso real: fusión y despliegue (R-17), configuración real
  (R-11), primera copia real (R-10) y alta del TOTP del administrador en producción.

## 2. Criterios de clasificación

| Clase | Significa |
| --- | --- |
| **CERRADO** | Corregido en código, con una prueba **ejecutada** que demuestra el comportamiento nuevo. Una recomendación escrita no basta |
| **MITIGADO** | Hay un control en código o en configuración, probado, que reduce el riesgo. Queda un riesgo residual descrito y aceptable para el piloto |
| **PENDIENTE DE VALIDACIÓN EXTERNA** | Preparado y probado en local; falta comprobarlo con acceso real (Render, Neon, GitHub, proveedores) o con una autorización del responsable |
| **BLOQUEANTE** | Impide abrir el piloto y no tiene solución técnica preparada |

## 3. Clasificación de cada riesgo

| ID | Riesgo | Clase | ¿Bloquea el piloto? | Evidencia ejecutada | Qué falta |
| --- | --- | --- | --- | --- | --- |
| R-01 | Política de privacidad con 6 datos sin completar y sin revisión legal (Ley 1581 de 2012) | **BLOQUEANTE** | Sí | `preflight_entorno_tipo_render.txt`: único fallo de una configuración tipo Render | Datos del responsable y revisión legal. No es tarea de código |
| R-02 | Primer TOTP del administrador por confianza en el primer uso | **CERRADO** | No, si se sigue el §3 de `BOOTSTRAP_ADMIN.md` | `T29` (16 casos, incluida la concurrencia de 6 administradores con el mismo código) y `bootstrap_admin.py` **17/17** con el servidor real | Efectivo al desplegar. Inscribir el TOTP el primer día |
| R-03 | Pagos sin probar en los sandbox de Wompi y NOWPayments | PENDIENTE DE VALIDACIÓN EXTERNA | No (pagos `off`) | `preflight`: «Pagos: desactivados» | Credenciales de sandbox y pagos de prueba antes de `live` |
| R-04 | Un reembolso posterior no quita el plan | MITIGADO | No | `T26.test_wompi_refund_after_approval_keeps_plan`; pagos `off` | Residual: revisión manual si se activan los pagos |
| R-05 | Comprar un plan inferior reemplaza al superior | MITIGADO | No | `T26.test_buying_lower_plan_replaces_higher_one`; pagos `off` | Decisión de negocio antes de activar los pagos |
| R-06 | Usuarios tras la misma IP | MITIGADO | No | `estres/ip_compartida…` (F-08) | Residual: cupo de fallidos compartido |
| R-07 | Pico de memoria de 339–341 MB | MITIGADO | No | `AUDITORIA_ESTRES_INTEGRAL.md` §6; `preflight` avisa sin `MALLOC_ARENA_MAX=2` | Medir en Render |
| R-08 | Secreto TOTP en claro en la base y en las copias | **CERRADO** | No | `T29`; `bootstrap_admin.py` lee el valor directamente en PostgreSQL: `enc1:…`; `backup_inicial.py`: la copia no contiene el secreto en claro | Definir `CRYPTO_RADAR_TOTP_KEY` en Render. Sin ella el servidor no arranca |
| R-09 | Copias sin firma | **CERRADO** | No | `T29`; `ataque_backup.py` («SIN CLAVE»); `backup_inicial.py`: sin clave → se niega; con otra clave → rechazada | — |
| R-10 | No hay copia de la base real; ventana de Neon sin verificar | PENDIENTE DE VALIDACIÓN EXTERNA | **Sí** | `backup_inicial.py` **16/16** (piloto y ×5, con 10 ms de latencia); RTO técnico de 1,6 a 7,1 s | Primera copia real y comprobar el historial de Neon (`PLAN_BACKUP_RECUPERACION.md` §6) |
| R-11 | Configuración real de Render y Neon sin inspeccionar | PENDIENTE DE VALIDACIÓN EXTERNA | **Sí** | `migracion_desde_main.py` **6/6** (2.0.0 → 2.1.0, idempotente, 0,32 s); `preflight` en dos entornos | `preflight --db` con las variables reales: 0 fallos |
| R-12 | Estrategia sin ventaja validada | MITIGADO | No, si se presenta como análisis | `INFORME_VENTAJA.md`; la web ya no muestra resultados | Residual permanente: no prometer rentabilidad |
| R-13 | Financiación de Binance no disponible desde algunas regiones | MITIGADO | No | El escáner marca N/D (`escaneo_real.txt`) | Comprobar `/healthz` desde Render (Frankfurt) |
| R-14 | IP del usuario detrás del proxy de Render | PENDIENTE DE VALIDACIÓN EXTERNA | No | `T28.test_forwarded_for_*` | Ver en Render que el registro de actividad guarda la IP real |
| R-15 | Eventos de Wompi viejos reenviados | MITIGADO | No | `T26.test_wompi_retries_sequential_and_concurrent` (idempotente) | — |
| R-16 | Trazas de error con la base caída | MITIGADO | No | `entorno.json`; F-07 elimina los 500 durante el reinicio | Aceptado |
| R-17 | Producción en 2.0.0; PR #3 a #7 sin fusionar | PENDIENTE DE VALIDACIÓN EXTERNA | **Sí** | `integracion_local.sh`: 0 conflictos, árbol idéntico, 158 → 192 → 231 → 258 → 275 → **291** pruebas OK con 3.12 y 3.13; `test_edge` 29 y `test_paper` 39 OK en cada paso | Autorización para fusionar con *merge commit* y desplegar (`PLAN_INTEGRACION_GIT.md` §3) |
| R-18 | Visibilidad del repositorio | PENDIENTE DE VALIDACIÓN EXTERNA | No | API de GitHub, 2026-11-15: **público** | Hacerlo privado; lo decide el responsable |
| R-19 | CPU del plan gratis | PENDIENTE DE VALIDACIÓN EXTERNA | No, con Starter | `estres/render_free_0.1cpu.json` (cgroups) | Elegir el plan Starter y medirlo con la prueba de 10 usuarios |
| R-20 | El escaneo sube el p95 del panel | MITIGADO | No | `ANALISIS_ESCANER_HTTP.md` | Aceptado |
| R-21 | Neon real sin medir (TLS, suspensión, *pooler*) | PENDIENTE DE VALIDACIÓN EXTERNA | No | `prueba_render_10.py --simular`: APROBADA en local (10/10 entran, p95 de 10 ms). `preflight` marca el `-pooler` como aviso | Ejecutarla en Render + Neon tras desplegar, con autorización |
| R-22 | **Nuevo.** Los usuarios de la 2.0.0 quedan `active` al migrar, sin aprobación | PENDIENTE DE VALIDACIÓN EXTERNA | No | `migracion_desde_main.json`, paso 3 | Consulta de solo lectura en la base real antes de fusionar |

**Resumen:**
- 3 CERRADOS: R-02, R-08 y R-09.
- 9 MITIGADOS.
- 9 PENDIENTES DE VALIDACIÓN EXTERNA. Tres de ellos bloquean el piloto: R-10, R-11 y R-17.
- 1 BLOQUEANTE: R-01.

## 4. Lo que se hizo en este cierre

1. **Administrador (R-02)**, en `BOOTSTRAP_ADMIN.md`:
   - código de alta de un solo uso que solo tiene quien controla el servidor;
   - se guarda solo como hash;
   - caduca;
   - consumo atómico;
   - sin repetición, ni tras reiniciar ni tras restaurar;
   - límite de intentos sin bloquear la cuenta;
   - recuperación documentada y probada.
2. **Secretos (R-08 y R-09)**, en `PROTECCION_SECRETOS.md`:
   - semillas TOTP cifradas con una clave propia, independiente de la de copias;
   - rotación con `_OLD`;
   - una clave errónea da 503 sin bloquear a nadie;
   - copias con HMAC obligatorio en todas las operaciones.
3. **Recuperación (R-10)**, en `PLAN_BACKUP_RECUPERACION.md`:
   - procedimiento de la copia inicial;
   - restauración probada en PostgreSQL vacío;
   - RTO propuesto ≤ 30 min y RPO ≤ 24 h.
   - Hallazgo corregido: la restauración por red pasó de 444,6 s a 4,2 s con inserción por lotes.
4. **Infraestructura (R-11 y R-21):**
   - migración real desde la 2.0.0;
   - preflight con comprobaciones nuevas: clave TOTP, claves independientes, secretos en la base, endpoint directo
     de Neon y `MALLOC_ARENA_MAX`;
   - prueba de 10 usuarios preparada y limitada a 10 por diseño: solo hace lecturas y se detiene sola si los errores
     pasan del 5 %.
5. **Git (R-17)**, en `PLAN_INTEGRACION_GIT.md`:
   - integración simulada con regresión completa en cada paso;
   - contraprueba con *squash*: 14 archivos en conflicto, por eso se exige *merge commit*.

## 5. Comprobaciones que requieren acceso real

Ninguna se ejecutó: las reglas prohíben desplegar y tocar producción. Van en este orden.

| # | Comprobación | Quién | Cómo | Criterio |
| --- | --- | --- | --- | --- |
| 1 | Usuarios existentes en la base de la 2.0.0 (R-22) | Responsable | `SELECT id, email, status FROM users`, en solo lectura | Conocer cuántos quedan `active` |
| 2 | Primera copia de la base actual | Responsable | `PLAN_BACKUP_RECUPERACION.md` §1 | `verify` OK |
| 3 | Variables reales y Neon directo (R-11) | Responsable | `python main.py preflight --db` con la `DATABASE_URL` directa | 0 fallos (exige R-01 resuelto) |
| 4 | Fusión de #3 a #7 y despliegue (R-17) | Responsable | `PLAN_INTEGRACION_GIT.md` §3 | `main` = `claude/cierre-riesgos` y regresión OK |
| 5 | TOTP del administrador (R-02) | Responsable | `BOOTSTRAP_ADMIN.md` §3 | `preflight --db`: «activo» y variable borrada |
| 6 | Historial de Neon y restauración por rama (R-10) | Responsable | Consola de Neon | Ventana conocida y documentada |
| 7 | Prueba de 10 usuarios (R-21 y R-19) | Responsable, con autorización | `tests/piloto/prueba_render_10.py` | APROBADA: p95 < 1 s, sin 5xx, nada > 2 s |
| 8 | IP real en la actividad (R-14) y `/healthz` desde Frankfurt (R-13) | Responsable | Panel de administración | La IP es la del usuario |
| 9 | Repositorio privado (R-18) | Responsable | GitHub → Settings | `private` |

## 6. Cómo reproducir

Todo se ejecuta sobre un PostgreSQL local de prueba, `PG=postgresql://radar@127.0.0.1:55432/radar`.

| Script | Escribe en `docs/evidencia_piloto/cierre/` | Resultado |
| --- | --- | --- |
| `TEST_DATABASE_URL=$PG python tests/test_suite.py` | — | 291 OK, con 3.12 y 3.13 |
| `python tests/test_edge.py`, `python tests/test_paper.py` | — | 29 OK y 39 OK |
| `PG_ADMIN_URL=$PG python tests/piloto/bootstrap_admin.py salida.json` | `bootstrap_admin.json` | 17/17 |
| `PG_ADMIN_URL=$PG python tests/piloto/backup_inicial.py salida.json` | `backup_inicial_piloto.json` | 16/16 |
| `USUARIOS=1000 ACTIVIDAD=200000 LATENCIA_MS=10 PG_ADMIN_URL=$PG python tests/piloto/backup_inicial.py salida.json` | `backup_inicial_escala.json` | 16/16 |
| `PG_ADMIN_URL=$PG python tests/piloto/migracion_desde_main.py salida.json` | `migracion_desde_main.json` | 6/6 |
| `python tests/piloto/prueba_render_10.py --simular salida.json` | `prueba_10_ensayo_local.json` | APROBADA |
| `TEST_DATABASE_URL=$PG PY312=python3.12 tests/piloto/integracion_local.sh` | `integracion_local.txt` | 0 conflictos; todo OK |
| `python main.py preflight`, sin variables y con variables tipo Render ficticias | `preflight_entorno_vacio.txt`, `preflight_entorno_tipo_render.txt` | 5 fallos y 1 fallo (R-01) |

Los scripts crean bases temporales con nombre aleatorio y las borran al terminar. Nunca leen `DATABASE_URL` real.
Las evidencias no contienen claves ni contraseñas reales: todas las de prueba se generan en cada ejecución.
