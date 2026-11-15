# Recuperación ante desastres · Crypto Radar 2.1.0

Fecha: 2026-11-15.
- Todo se ejecutó en **bases PostgreSQL temporales** creadas y borradas por los scripts.
- No se usó ninguna base real ni se tocó Neon.

## 1. Simulacro ejecutado

Script: `tests/piloto/simulacro_recuperacion.py`. Evidencia: `docs/evidencia_piloto/simulacro_recuperacion.json`.

```bash
PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/simulacro_recuperacion.py docs/evidencia_piloto/simulacro_recuperacion.json
```

Resultado: **18 de 18 pasos OK** (PostgreSQL 16.15, Python 3.12.3).

| # | Paso | Resultado |
| --- | --- | --- |
| 1 | Base de origen poblada con la propia app | 41 usuarios, 40 sesiones, 52 posiciones, 10 pagos verificados por webhook, 193 actividades, 5 códigos de Telegram, 1 documento |
| 2 | Copia creada, firmada con HMAC y verificada con una restauración de prueba en SQLite | OK |
| 3 | Copia idéntica al origen (`compare`) | OK |
| 4 | Monto de un pago cambiado en la copia | Detectado: SHA-256 distinto |
| 5 | Un usuario borrado de la copia | Detectado: filas y SHA-256 |
| 6 | Usuario elevado a administrador **con los hashes recalculados** | Detectado: firma HMAC inválida |
| 7 | Firma eliminada | Detectado: copia sin firma con la clave definida |
| 8 | Tabla sustituida por otra | Detectado |
| 9 | Restaurada en una base vacía | OK |
| 10 | Comparación campo por campo de usuarios, pagos, posiciones, actividad, Telegram y kv | Idénticos |
| 11 | Sesiones | No se restauran, por diseño (40 → 0): todos vuelven a entrar |
| 12 | Segunda restauración sobre una base con datos | Rechazada; no se toca nada |
| 13 | **Desastre:** base de origen eliminada (`DROP DATABASE`) | — |
| 14 | La app arranca sobre la base recuperada (migraciones y verificación de esquema) | OK; administrador «verificado» |
| 15 | Inicio de sesión con la contraseña original | OK |
| 16 | Plan y posiciones de un cliente | Intactos (Pro, 2 posiciones) |
| 17 | Reintento del webhook de un pago ya aplicado | 200 y el plan **no** se extiende dos veces |
| 18 | Datos escritos después de la copia | **Perdidos**: el usuario creado tras la copia no existe (RPO = tiempo desde la última copia) |

Tiempos medidos con datos de piloto (unas 300 filas):
- copia: 0,03 s;
- restauración: 0,14 s;
- de la caída al primer inicio de sesión: 0,6 s.

Con datos reales los tiempos crecen. Además, en producción hay que sumar los pasos manuales (sección 3). **El RTO real no se midió en Render ni en Neon.**

## 2. Corte de conexiones y caída de la base

Script: `tests/piloto/entorno.py`. Evidencia: `docs/evidencia_piloto/entorno.json`.

El servidor real corre sobre PostgreSQL con 16 hilos fijos.

| Escenario | Antes de corregir | Después |
| --- | --- | --- |
| PostgreSQL corta las 17 conexiones de la app, como Neon al suspender la base por inactividad | **16 de 40 peticiones fallaron**: una por hilo (F-06) | 0 de 40 |
| La base deja de aceptar conexiones | `/healthz` responde 500: Render lo detecta | igual |
| La base vuelve | — | 0 de 40 fallidas; se recupera sin reiniciar |

Sobre F-06:
- Lo introdujo la corrección de rendimiento F-05, porque con hilos fijos las conexiones viven más tiempo.
- La prueba lo detectó antes del commit.
- La causa estaba en `db.execute`: solo reintentaba si el error decía «closed», y el primer error de PostgreSQL dice «terminating connection due to administrator command».
- En `8476715` la primera consulta tras un corte también fallaba (`AdminShutdown`, contraprueba en `T27`), pero quedaba oculto porque se abría una conexión nueva en cada petición.
- Ahora se reconecta cuando psycopg marca la conexión como rota. Es seguro repetir la sentencia porque no llegó a ejecutarse.

## 3. Procedimiento de recuperación en producción

Tiempo objetivo con datos de piloto: menos de 30 minutos, contando los pasos manuales.

1. **Detectar.**
   - `/healthz` devuelve 500, o Render reinicia el servicio en bucle.
   - El registro muestra errores de PostgreSQL.
2. **Elegir el punto de restauración.**
   - Si el problema es de datos (borrado o corrupción): crear en Neon una **rama desde un instante anterior** al incidente, dentro de la ventana de historial del plan.
   - Si no alcanza el historial: usar la última copia propia.
3. **Restaurar desde una copia propia.** Desde la máquina de confianza que guarda las copias y la clave:
   ```bash
   export CRYPTO_RADAR_BACKUP_KEY=…           # la misma con la que se firmó
   python main.py backup verify backups/crypto-radar-backup-AAAAMMDD-HHMMSS
   python main.py backup restore backups/crypto-radar-backup-… --target 'postgresql://…/base_nueva?sslmode=require'
   ```
   `restore` se niega si el destino tiene datos o si es la base de `DATABASE_URL`.
4. **Apuntar Render a la base nueva.** Cambiar `DATABASE_URL` y desplegar. En el registro debe aparecer `esquema verificado` y `Administrador: … · verificado`.
5. **Comprobar.**
   - `python main.py preflight --db`.
   - Inicio de sesión de prueba.
   - Revisar en el panel los pagos de las últimas 48 h.
6. **Reconciliar pagos.** Los pagos confirmados por Wompi o NOWPayments después de la copia no están en la base restaurada.
   - Buscarlos en los paneles de los proveedores.
   - Concederlos con «Conceder plan» y como motivo la referencia del pago.
   - Volver a entregar un webhook es seguro: no concede dos veces.
7. **Avisar.** Todos los usuarios deben volver a iniciar sesión, porque las sesiones no se restauran. Los administradores conservan su TOTP, que viaja en la copia.

## 4. Copias: rutina recomendada

- Copia firmada (`CRYPTO_RADAR_BACKUP_KEY`) antes de cada despliegue y al menos una vez por semana.
- Verificar la copia en el momento (`verify`).
- Guardarla cifrada (por ejemplo con `age` o `gpg`), fuera del repositorio y del servidor.
- La clave de firma se guarda **separada** de las copias.
- Una vez al mes, restaurar en una rama de Neon y ejecutar `preflight --db` contra ella.

## 5. Lo que no se pudo verificar

- La ventana de historial ni la restauración por rama de Neon: no hay acceso a la cuenta.
- El RTO real en Render: no se desplegó, por regla.
- Una copia de la base real de producción: no existe todavía.
