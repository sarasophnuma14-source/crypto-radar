# Matriz de riesgos pendientes · Crypto Radar 2.1.0

Fecha: 2026-11-15 (actualizada tras el cierre de riesgos; clasificación final en `CIERRE_RIESGOS_PILOTO.md`).

Escalas:
- **Probabilidad:** baja, media o alta.
- **Impacto:** bajo, medio o alto.
- **Bloquea piloto:** si es «Sí», ese riesgo debe resolverse antes de invitar al primer usuario.

Evidencia:
- «Prueba»: una prueba automática que reproduce el comportamiento actual.
- «Doc»: algo comprobado en el código o el entorno, pero sin prueba.

| ID | Riesgo | Prob. | Impacto | Bloquea piloto | Evidencia | Mitigación propuesta |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | Política de privacidad con 6 datos sin completar y sin revisión legal (Ley 1581 de 2012 aplica también a un piloto) | Alta | Alto | **Sí** | `preflight` falla en «Texto legal privacidad.html» | Completar los datos del responsable y pasar la revisión de un abogado |
| R-02 | ~~Primer alta de TOTP por confianza en el primer uso~~ → **CERRADO en código**: código de alta de un solo uso (CLI o entorno), consumo atómico, sin repetición | Baja | Alto | No | `T29` (16 casos) y `tests/piloto/bootstrap_admin.py` 17/17 | `BOOTSTRAP_ADMIN.md`: inscribir el TOTP el día del despliegue y borrar la variable |
| R-03 | Pagos nunca probados con los sandbox reales de Wompi y NOWPayments | Alta | Medio | No (pagos `off`) | Doc: no hay credenciales de sandbox | Hacer pagos de prueba en ambos sandbox antes de pasar a `live` |
| R-04 | Un reembolso o anulación posterior no quita el plan | Media | Medio | No | Prueba `T26.test_wompi_refund_after_approval_keeps_plan` | Revisión manual semanal de reembolsos; automatizarlo es una decisión de negocio |
| R-05 | Pagar un plan inferior con uno superior vigente reemplaza el plan y se pierde el tiempo pagado | Baja | Medio | No | Prueba `T26.test_buying_lower_plan_replaces_higher_one` | Ocultar la compra de planes inferiores o prorratear (decisión de negocio) |
| R-06 | Usuarios tras la misma IP: ~~20 inicios de sesión por IP~~ → ahora 20 **fallidos** por IP (estrés integral). Quedan: cupo de fallidos compartido, solicitud de acceso 3/IP/h y bloqueo dirigido de cuenta | Baja | Bajo | No | `estres/ip_compartida_despues.json`: 50 de 50 OK; `T28` | Con más usuarios, Turnstile en lugar de 429 |
| R-07 | Memoria: pico de 339–341 MB con `MALLOC_ARENA_MAX=2` con 100 usuarios, escaneos simultáneos y escaneo real (74 activos); sin la variable, 419 MB | Baja | Alto | No | `AUDITORIA_ESTRES_INTEGRAL.md` §6 | Mantener `MALLOC_ARENA_MAX=2` (en `render.yaml`) y vigilar la memoria en Render |
| R-08 | ~~Secreto TOTP en claro~~ → **CERRADO en código**: cifrado con `CRYPTO_RADAR_TOTP_KEY` (encrypt-then-MAC, ligado al usuario); en Render no arranca sin clave | Baja | Alto | No | `T29`, `bootstrap_admin.py` (lectura directa en PostgreSQL) | `PROTECCION_SECRETOS.md` §4: rotación |
| R-09 | ~~Copias sin firma sin clave~~ → **CERRADO**: `CRYPTO_RADAR_BACKUP_KEY` obligatoria para crear, verificar, comparar y restaurar | Baja | Alto | No | `T29`, `ataque_backup.py` («SIN CLAVE»), `backup_inicial.py` | `PROTECCION_SECRETOS.md` §5 |
| R-10 | Procedimiento probado (16/16, también ×5 y con latencia), pero **no existe ninguna copia de la base real** y la ventana de historial de Neon no se ha verificado | Alta | Alto | **Sí** | `backup_inicial_piloto.json`, `backup_inicial_escala.json` | `PLAN_BACKUP_RECUPERACION.md` §1 el día del despliegue |
| R-11 | Migración desde 2.0.0 probada (6/6) y preflight revisado, pero la configuración **real** de Render y Neon no se inspeccionó | — | Alto | **Sí** | `migracion_desde_main.json`, `preflight_entorno_*.txt` | `python main.py preflight --db` con las variables reales: 0 fallos |
| R-12 | Estrategia sin ventaja validada: el backtest fuera de muestra es negativo y ninguna de las 23 estrategias del holdout mostró ventaja | Alta | Alto | No, si se presenta como análisis | Doc: `research/edge/INFORME_VENTAJA.md`, `BACKTEST_REPORT.md` | No prometer rentabilidad; el aviso de riesgo ya lo dice; no publicar cifras de retorno |
| R-13 | Datos de financiación de Binance Futures no disponibles desde algunas regiones (451 o 403); CoinGecko respondió 429 | Media | Bajo | No | `escaneo_real.txt`: `binance_funding: N/D` | El escáner ya lo marca N/D; en Render (Frankfurt) comprobar `/healthz` → `sources` |
| R-14 | ~~`X-Forwarded-For` se confía siempre~~ → solo desde `CRYPTO_RADAR_TRUSTED_PROXIES` (en Render, `*` por defecto) | Baja | Bajo | No | `T28.test_forwarded_for_*` | Comprobar en Render que la IP del registro de actividad es la del usuario |
| R-15 | El evento de Wompi no se rechaza por antigüedad (reenvío de eventos viejos) | Baja | Bajo | No | Prueba `T26.test_wompi_retries_sequential_and_concurrent` (idempotente) | Aceptable: un pago verificado no se aplica dos veces |
| R-16 | Con la base caída, el registro se llena de trazas de error (sin secretos) | Media | Bajo | No | `entorno.json`: 4 trazas en la prueba | Aceptable para el piloto |
| R-17 | Producción sigue en 2.0.0; PR #3 → #4 → #5 → #6 → #7 apilados sin fusionar. Integración local sin conflictos y regresión completa verde tras cada paso | — | — | **Sí**, para empezar | `PLAN_INTEGRACION_GIT.md`, `evidencia_piloto/cierre/integracion_local.txt` | Fusionar en orden con «merge commit» (no *squash*) cuando el responsable lo autorice |
| R-18 | Repositorio **público** (verificado el 2026-11-15 en la API de GitHub). No contiene secretos, pero expone el código y los documentos de seguridad | — | Medio | No | API de GitHub: `visibility: public` | Hacerlo privado antes del piloto (decisión del responsable) |
| R-19 | CPU del plan gratis (0,1 CPU): con 25 usuarios activos el servidor se satura (entrar tarda hasta 15 s, p95 2,1 s) | Alta | Medio | No, si se usa Starter | `estres/render_free_0.1cpu.json` (cgroups) | Plan Starter (0,5 CPU) para hasta 50 usuarios activos; decisión del responsable |
| R-20 | El escaneo (GIL) sube el p95 del panel a 0,3–0,5 s durante sus 4–7 s (0,65–1 s en Starter emulado) | Alta | Bajo | No | `ANALISIS_ESCANER_HTTP.md` | Aceptado; proceso aparte con 2 GB o si el p99 en Render supera 1 s |
| R-21 | Neon real sin medir: TLS, arranque tras suspensión, *pooler*. Prueba de 10 usuarios **preparada y ensayada en local**, no ejecutada en Render | — | Medio | No | `tests/piloto/prueba_render_10.py`, `prueba_10_ensayo_local.json` | Ejecutarla tras desplegar, con autorización |
| R-22 | Usuarios de la 2.0.0 quedan como `active` al migrar (no pasan por la aprobación del administrador). Se desconoce si la base real tiene alguno | Baja | Medio | No | `migracion_desde_main.json`, paso 3 | Antes de desplegar, en solo lectura: `SELECT id, email, status FROM users` |

## Riesgos cerrados en esta auditoría

| ID | Hallazgo | Cierre |
| --- | --- | --- |
| F-01 | Copias falsificables recalculando los hashes | HMAC con `CRYPTO_RADAR_BACKUP_KEY` (queda R-09 si no se define) |
| F-02 | Códigos de Telegram sin límite de intentos por chat | 10 intentos por hora por chat |
| F-03 | IPN legítimas de NOWPayments rechazadas (tildes o exponentes) | Firma comprobada sobre el JSON de JavaScript |
| F-04 | Conexiones rechazadas en ráfagas (23 % de los inicios de sesión con 100 usuarios) | Cola de escucha de 128 |
| F-05 | Una conexión a PostgreSQL por petición; 514 MB con 100 usuarios | 16 hilos fijos; 15 conexiones en total; 345 MB |
| F-06 | Tras un corte de conexiones fallaba una petición por hilo (16 de 40) | Reconexión cuando psycopg marca la conexión como rota |
| F-07 | Reinicio de PostgreSQL: 15 respuestas 500 mientras la base arrancaba (estrés integral) | Reintento corto al conectar (`radar/db.py`): 0 errores |
| F-08 | 30 de 50 usuarios legítimos tras una misma IP recibían 429 (estrés integral) | Límite por intentos fallidos (`radar/auth.py`) |
| F-09 | Restaurar la copia del piloto a través de la red tardaba 444,6 s (fila a fila con 10 ms de latencia) | Inserción por lotes de 1000 filas: 4,2 s (`PLAN_BACKUP_RECUPERACION.md` §3) |
