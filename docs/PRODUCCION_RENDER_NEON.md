# Producción en Render + Neon (2.1.0)

Guía y lista de revisión. Nada de esto se aplicó en producción: el servicio actual sigue en el modo de un solo
usuario (v2.0.0) hasta que el responsable despliegue esta rama.

## 1. Revisión automática: `python main.py preflight`

Solo lee variables de entorno y archivos; no cambia nada y no muestra contraseñas, claves ni la URL de la base.
Con `--db` además se conecta en **solo lectura** a `DATABASE_URL` y comprueba el esquema y que el administrador
tenga TOTP activo. Termina con código 1 si hay algún fallo.

| Comprobación | Fallo si… |
| --- | --- |
| Modo cuentas | `CRYPTO_RADAR_ACCOUNTS` no es `1` |
| Base de datos | `DATABASE_URL` no es PostgreSQL, o `CRYPTO_RADAR_ALLOW_SQLITE` está definida |
| TLS con la base | `sslmode` no es `require`, `verify-ca` ni `verify-full` |
| Conexión Neon | (aviso) el host no es el endpoint `-pooler` |
| Administrador | falta usuario o contraseña, o la contraseña tiene < 12 caracteres o contiene el usuario |
| Variables de recuperación | `CRYPTO_RADAR_ADMIN_RESET` o `CRYPTO_RADAR_ADMIN_TAKEOVER` siguen definidas |
| TOTP del administrador | `CRYPTO_RADAR_ADMIN_TOTP=optional` |
| Pagos | `CRYPTO_RADAR_PAYMENTS=live`, o `sandbox` con una llave de Wompi de producción |
| Textos legales | quedan marcas `COMPLETAR` o el aviso de borrador en `/privacidad` |
| render.yaml | alguna variable secreta tiene el valor escrito en el archivo (deben ser `sync: false`) |

Resultado hoy con una configuración correcta: **1 fallo**, los datos del responsable en la política de privacidad.

## 2. Render

Estado del `render.yaml` revisado:
- Región `frankfurt` (Binance bloquea IP de EE. UU.), `healthCheckPath: /healthz`, Python 3.12.7.
- Todas las variables secretas son `sync: false` (Render las pide; no están en el repositorio).
- Nuevas: `CRYPTO_RADAR_ADMIN_TOTP=required` y `CRYPTO_RADAR_PAYMENTS="off"` con valor fijo.

Recomendaciones antes de abrir a clientes:
1. **Plan:** el plan gratis se duerme tras un rato sin visitas y su disco se borra en cada despliegue. Con cuentas el
   disco ya no importa (todo va a PostgreSQL), pero el primer acceso tras dormir tarda. Para clientes que pagan conviene
   un plan de pago (sin suspensión). `KEEPALIVE=1` mitiga, no sustituye.
2. **Una sola instancia** mientras el escáner corra dentro del proceso web: con dos instancias habría dos escáneres.
3. **Dominio propio con HTTPS** (Render lo emite). La cookie de sesión es `Secure` en HTTPS.
4. **Variables:** quitar `CRYPTO_RADAR_PASSWORD` cuando se pase al modo cuentas; no definir `CRYPTO_RADAR_ALLOW_SQLITE`.
5. **Auto-deploy:** si el servicio despliega solo al cambiar `main`, fusionar el PR equivale a desplegar.

## 3. Neon

1. Usar la cadena de conexión **con pooler** (host con `-pooler`) y `?sslmode=require`. Si la librería lo admite,
   `sslmode=verify-full` es más estricto.
2. Región de Neon en Europa (cerca de Frankfurt) para reducir la latencia de cada consulta.
3. Un rol propio para la app, sin permisos sobre otras bases. No usar el rol propietario del proyecto en la app si se
   puede evitar.
4. **Restauración a un punto en el tiempo:** Neon permite crear una rama desde un instante pasado dentro de la
   ventana de historial de su plan. Revisa en el panel de Neon cuánto historial incluye tu plan; con el plan gratis es
   corto, por eso además hacen falta copias propias (sección 4).
5. La compute del plan gratis se suspende tras un rato sin uso: la primera consulta después tarda algo más. La app
   reconecta una vez si Neon cerró la conexión.

## 4. Copias de seguridad y restauración

Copia lógica verificable de las tablas de la app (usuarios, actividad, posiciones, pagos, vínculos de Telegram y
documentos `kv`). No copia sesiones ni límites de intentos (son temporales).

```bash
# 1. Crear (lee DATABASE_URL; en PostgreSQL usa una transacción REPEATABLE READ de solo lectura)
DATABASE_URL='postgresql://…?sslmode=require' python main.py backup create --out backups
# 2. Verificar: hashes + restauración real en una SQLite temporal
python main.py backup verify backups/crypto-radar-backup-AAAAMMDD-HHMMSS
# 3. Comparar con la base actual (debe decir «Idéntica» si nadie escribió desde la copia)
DATABASE_URL='…' python main.py backup compare backups/crypto-radar-backup-…
# 4. Restaurar SOLO en una base nueva y vacía (por ejemplo, una rama nueva de Neon)
python main.py backup restore backups/crypto-radar-backup-… --target 'postgresql://…/base_nueva?sslmode=require'
```

Garantías probadas (`tests/test_suite.py`, clase `T23_Backup`):
- cada tabla lleva su SHA-256 y el manifiesto tiene su propio hash: cualquier cambio en la copia se detecta;
- `restore` se niega si el destino tiene una sola fila (nunca borra ni sobrescribe) y se niega a usar la base de
  `DATABASE_URL` como destino;
- tras restaurar vuelve a exportar el destino y compara fila a fila con la copia;
- ida y vuelta SQLite → PostgreSQL → copia → SQLite con el contenido idéntico;
- archivos con permisos 600 y carpeta 700. `backups/` está en `.gitignore`.

Rutina propuesta: copia semanal y antes de cada despliegue, `verify` inmediatamente, guardar cifrada
(por ejemplo `age` o `gpg`) fuera del repositorio y del servidor, y una prueba de restauración en una rama de Neon
al mes. Alternativa nativa: `pg_dump --format=custom "$DATABASE_URL"` con un cliente de PostgreSQL de la misma versión
mayor que el servidor, y `pg_restore` en una base nueva.

## 5. Pagos en sandbox

1. `python main.py payments-selftest`: flujo completo por HTTP con un simulador local. No usa red ni claves reales.
2. Con cuentas de prueba de cada proveedor: `CRYPTO_RADAR_PAYMENTS=sandbox`, llaves `pub_test_…` de Wompi y la API
   key del sandbox de NOWPayments. Configurar los webhooks del sandbox hacia `/api/billing/wompi/webhook` y
   `/api/billing/nowpayments/ipn` y pagar con las tarjetas de prueba del proveedor.
3. `live` solo cuando el responsable del negocio lo decida, con los textos legales revisados y `preflight` sin fallos.

## 6. Lista para abrir al público

- [ ] Datos del responsable completados en `/privacidad` y revisión de un abogado de ambos textos legales.
- [ ] Neon con pooler y `sslmode=require`; copia creada y verificada; prueba de restauración hecha.
- [ ] Administrador con TOTP activo (`preflight --db` sin avisos).
- [ ] `CRYPTO_RADAR_ADMIN_RESET` y `_TAKEOVER` quitadas.
- [ ] Pagos probados en el sandbox real de cada proveedor.
- [ ] `python main.py preflight` con 0 fallos.
