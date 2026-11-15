# Matriz de riesgos pendientes · Crypto Radar 2.1.0

Fecha: 2026-11-15.

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
| R-02 | Primer alta de TOTP del administrador: quien tenga su contraseña antes de que active TOTP puede inscribir su propio segundo factor | Media | Alto | **Sí** | Prueba `T25.test_admin_first_enrolment_is_trust_on_first_use` | Activar TOTP justo después del primer despliegue y comprobarlo con `preflight --db` |
| R-03 | Pagos nunca probados con los sandbox reales de Wompi y NOWPayments | Alta | Medio | No (pagos `off`) | Doc: no hay credenciales de sandbox | Hacer pagos de prueba en ambos sandbox antes de pasar a `live` |
| R-04 | Un reembolso o anulación posterior no quita el plan | Media | Medio | No | Prueba `T26.test_wompi_refund_after_approval_keeps_plan` | Revisión manual semanal de reembolsos; automatizarlo es una decisión de negocio |
| R-05 | Pagar un plan inferior con uno superior vigente reemplaza el plan y se pierde el tiempo pagado | Baja | Medio | No | Prueba `T26.test_buying_lower_plan_replaces_higher_one` | Ocultar la compra de planes inferiores o prorratear (decisión de negocio) |
| R-06 | Límite de 20 inicios de sesión por IP cada 15 min: usuarios detrás de CGNAT o de una oficina reciben 429 | Media | Medio | No | `carga_ip_compartida.json`: 30 de 50 recibieron 429 | Para el piloto basta; con más usuarios, límite por cuenta + Turnstile o Cloudflare |
| R-07 | Memoria: 345 MB con 100 usuarios y 422 MB sostenidos con 50, usando un informe sintético de 40 activos; el escaneo real (74 activos, pandas) corre en el mismo proceso. El plan gratis de Render tiene 512 MB | Media | Alto | No (piloto pequeño) | `PRUEBAS_RENDIMIENTO.md` | `MALLOC_ARENA_MAX=2` (ya en `render.yaml`), vigilar la memoria en Render y subir de plan antes de crecer |
| R-08 | Secreto TOTP en claro en la base y en las copias | Baja | Alto | No | Doc: `radar/auth.py` | Cifrarlo con una clave del entorno; mientras tanto, copias cifradas |
| R-09 | Copias sin firma si no se define `CRYPTO_RADAR_BACKUP_KEY`: se pueden alterar recalculando los hashes | Baja | Alto | No | `tests/piloto/ataque_backup.py` sin clave: «NO DETECTADO» | Definir siempre la clave en la máquina que hace las copias (`verify` lo avisa) |
| R-10 | No existe todavía ninguna copia de la base real, y la ventana de historial de Neon no se ha verificado | Alta | Alto | **Sí** | Doc | Primera copia firmada y verificada el día del despliegue |
| R-11 | La configuración real de Render y Neon no se inspeccionó (sin acceso; regla: no tocar producción) | — | Alto | **Sí** | Doc | Ejecutar `python main.py preflight --db` con las variables reales; debe dar 0 fallos |
| R-12 | Estrategia sin ventaja validada: el backtest fuera de muestra es negativo y ninguna de las 23 estrategias del holdout mostró ventaja | Alta | Alto | No, si se presenta como análisis | Doc: `research/edge/INFORME_VENTAJA.md`, `BACKTEST_REPORT.md` | No prometer rentabilidad; el aviso de riesgo ya lo dice; no publicar cifras de retorno |
| R-13 | Datos de financiación de Binance Futures no disponibles desde algunas regiones (451 o 403); CoinGecko respondió 429 | Media | Bajo | No | `escaneo_real.txt`: `binance_funding: N/D` | El escáner ya lo marca N/D; en Render (Frankfurt) comprobar `/healthz` → `sources` |
| R-14 | `X-Forwarded-For` se confía siempre: fuera de Render (sin proxy) un atacante evadiría los límites por IP | Baja | Medio | No | Doc: `Handler._client_ip` | Solo desplegar detrás del proxy de Render; revisar si se cambia de proveedor |
| R-15 | El evento de Wompi no se rechaza por antigüedad (reenvío de eventos viejos) | Baja | Bajo | No | Prueba `T26.test_wompi_retries_sequential_and_concurrent` (idempotente) | Aceptable: un pago verificado no se aplica dos veces |
| R-16 | Con la base caída, el registro se llena de trazas de error (sin secretos) | Media | Bajo | No | `entorno.json`: 4 trazas en la prueba | Aceptable para el piloto |
| R-17 | Producción sigue en 2.0.0 de un solo usuario; los PR #3, #4 y #5 están sin fusionar | — | — | **Sí**, para empezar | Doc | Fusionar en orden (#3 → #4 → #5) y desplegar cuando el responsable lo autorice |
| R-18 | Visibilidad del repositorio (público o privado) no verificada en esta auditoría | — | Medio | No | Doc | Hacerlo privado antes del piloto; no contiene secretos (búsqueda en todo el historial) |

## Riesgos cerrados en esta auditoría

| ID | Hallazgo | Cierre |
| --- | --- | --- |
| F-01 | Copias falsificables recalculando los hashes | HMAC con `CRYPTO_RADAR_BACKUP_KEY` (queda R-09 si no se define) |
| F-02 | Códigos de Telegram sin límite de intentos por chat | 10 intentos por hora por chat |
| F-03 | IPN legítimas de NOWPayments rechazadas (tildes o exponentes) | Firma comprobada sobre el JSON de JavaScript |
| F-04 | Conexiones rechazadas en ráfagas (23 % de los inicios de sesión con 100 usuarios) | Cola de escucha de 128 |
| F-05 | Una conexión a PostgreSQL por petición; 514 MB con 100 usuarios | 16 hilos fijos; 15 conexiones en total; 345 MB |
| F-06 | Tras un corte de conexiones fallaba una petición por hilo (16 de 40) | Reconexión cuando psycopg marca la conexión como rota |
