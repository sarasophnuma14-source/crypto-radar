# Configuración de Neon para la 2.1.0 (base nueva e independiente)

Fecha: 2026-11-16. **No se ha creado nada:** esta sesión no tiene acceso a Neon (la API responde 401 y no hay
conector). No se inventa ningún identificador ni ninguna `DATABASE_URL`. Lo que solo se puede comprobar en Neon va
marcado **[VALIDAR EN REAL]**.

## 1. Antes de crear

1. En Neon → *Projects*, comprueba que **no** exista ya un proyecto para la 2.1, para no duplicarlo.
2. Identifica el proyecto de la 2.0.0, si existe, y **no lo toques**. Anota solo su nombre, para el inventario.
3. Plan y coste:
   - El plan gratuito de Neon suele bastar para el piloto interno.
   - [VALIDAR EN REAL] Revisa en *Billing* los límites del plan elegido: horas de cómputo, almacenamiento, ventana de
     historial (*restore window*) y número de ramas. Sus importes cambian y no se pudieron comprobar desde aquí.

## 2. Crear

| Campo | Valor |
| --- | --- |
| Nombre del proyecto | `crypto-radar-2-1` |
| Región | **AWS Europe Central 1 (Frankfurt)**, junto a Render Frankfurt. [VALIDAR EN REAL] que esté disponible en la cuenta |
| PostgreSQL | **16**. Las pruebas corrieron sobre 16.15; la aplicación usa SQL estándar |
| Base de datos | `radar` |
| Rama | `main` (la de por defecto) |

## 3. Roles: privilegios mínimos

El rol que Neon crea con el proyecto es del propietario. No lo uses en Render.

Abre el *SQL Editor* de Neon, conectado como propietario a la base `radar`, y crea un rol de aplicación **por SQL**.
[VALIDAR EN REAL] Los roles creados desde la consola entran en `neon_superuser`; los creados por SQL no.

La contraseña se genera en el ordenador del responsable, con `python -c "import secrets;print(secrets.token_urlsafe(32))"`,
y se pega directamente en el editor. **Nunca en el chat.**

```sql
CREATE ROLE radar_app LOGIN PASSWORD '<generada en tu ordenador>' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
REVOKE ALL ON DATABASE radar FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE radar TO radar_app;
CREATE SCHEMA app AUTHORIZATION radar_app;          -- la aplicación crea y migra sus tablas aquí
ALTER ROLE radar_app SET search_path = app;
ALTER ROLE radar_app SET statement_timeout = '30s';
ALTER ROLE radar_app SET idle_in_transaction_session_timeout = '60s';
```

- El arranque crea las tablas y aplica las migraciones (`db.init`), así que `radar_app` debe ser **dueño de su
  esquema**. No tiene permisos sobre nada más.
- **Copias:** usa un segundo rol, `radar_backup`, solo con lectura. `backup create` y `backup verify` solo leen:

  ```sql
  CREATE ROLE radar_backup LOGIN PASSWORD '<otra, generada aparte>' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  GRANT CONNECT ON DATABASE radar TO radar_backup;
  GRANT USAGE ON SCHEMA app TO radar_backup;
  ALTER DEFAULT PRIVILEGES FOR ROLE radar_app IN SCHEMA app GRANT SELECT ON TABLES TO radar_backup;
  ALTER ROLE radar_backup SET search_path = app;   -- sin esto la copia no encuentra las tablas (hallado en Neon real)
  ```

  Después del primer arranque, cuando ya existen las tablas, ejecuta también
  `GRANT SELECT ON ALL TABLES IN SCHEMA app TO radar_backup;`.
- `backup restore` se hace sobre una base **vacía y nueva**, con el rol propietario. Nunca sobre la de `DATABASE_URL`:
  el propio comando se niega.
- Ensayado en local con este mismo SQL (`docs/evidencia_piloto/lanzamiento/neon_privilegios_minimos_local.txt`): el arranque crea las 11 tablas en `app`, `radar_backup` hace y verifica la copia y no puede escribir, y `radar_app` no puede crear bases.
- **Crea la 2.1 en un proyecto de Neon distinto del de la 2.0.0**, nunca como otra base del mismo proyecto: en el mismo servidor, un rol puede conectarse a otras bases que no revoquen `CONNECT` a `PUBLIC`.
- [VALIDAR EN REAL] El primer arranque con `search_path = app` debe crear las tablas en `app`. Compruébalo en el
  paso 5. Si `verify_schema` no las encuentra, el servidor **no arranca**: es seguro, no corrompe nada.

## 4. Conexión

- **Endpoint directo**, sin `-pooler`. El arranque usa un bloqueo consultivo de sesión (`pg_advisory_lock`, F-10),
  que no funciona con el *pooler* en modo transacción.
  - Cada instancia abre como mucho unas 20 conexiones: 19 medidas en local con 50 usuarios.
  - [VALIDAR EN REAL] El límite de conexiones del cómputo elegido.
- **TLS obligatorio:** `sslmode=require` como mínimo, o `verify-full` si Render tiene el certificado raíz. Sin él, el
  servidor no arranca en Render (`radar/pilot.py`).
- Formato, sin valores: `postgresql://radar_app:<clave>@<endpoint directo>.eu-central-1.aws.neon.tech/radar?sslmode=require`.
  - Va **solo** en la variable `DATABASE_URL` del servicio **nuevo** de Render, como secreto.
  - Ni en el repositorio ni en el chat.
- **No reutilices** ninguna variable, URL ni contraseña de la 2.0.0.

## 5. Comprobaciones después del primer arranque

Ejecuta en la máquina de confianza con las variables reales, o como lectura en el *SQL Editor*:

| Comprobación | Esperado |
| --- | --- |
| `python main.py preflight --db` | 0 bloqueantes; «Plataforma 2.1 · nueva»; «Administradores: 1» |
| `SELECT k, v FROM app.platform_meta` | Contiene `platform = 2.1` e `initialized = nueva` |
| `SELECT count(*) FROM app.users WHERE is_admin = 1` | `1` |
| `SELECT count(*) FROM app.users` | `1`, solo el administrador, antes de crear cuentas de prueba |
| `SELECT count(*) FROM app.legacy_archive` | `0`: la base es nueva y no hay nada de la 2.0.0 |
| `SELECT current_user, inet_server_addr() IS NOT NULL` | `radar_app` |
| `SHOW ssl` en la sesión de la app (o `pg_stat_ssl`) | `on` |

La base nueva **no** recibe usuarios, sesiones ni contraseñas de la 2.0.0. No se ejecuta nada sobre la base de la
2.0.0.

## 6. Recuperación

- Historial de Neon: anota la ventana de restauración del plan. Haz un ensayo de restauración por rama: crear una rama
  a una hora anterior, comprobar que tiene los datos y borrar la rama (`PLAN_BACKUP_RECUPERACION.md` §6).
- Copia propia diaria, firmada con HMAC (`CRYPTO_RADAR_BACKUP_KEY`) y guardada **cifrada**, por ejemplo con
  `age` o `gpg`, en un almacenamiento con acceso restringido (`PLAN_BACKUP_RECUPERACION.md` §1).


## 8. Estado REAL en Neon (2026-11-16, 01:45–01:56 UTC)

Hecho con la CLI de Neon (`neon init`/`neon deploy`, sesión OAuth de la cuenta del propietario) y SQL por HTTPS:

| Elemento | Valor |
| --- | --- |
| Proyecto | `MyCryptoRadar` (`mute-sky-79699743`), organización `org-empty-fog-45336387`; proyecto nuevo, distinto del de la 2.0.0 |
| Región / versión | AWS eu-central-1 (Frankfurt) / PostgreSQL 16.16 |
| Rama / base | `production` (`br-dry-tree-b95aum41`) / `radar` (propietario `radar_owner`) |
| Endpoint directo | `ep-polished-lake-b9lfqq5g` (la app usa el directo, sin `-pooler`) |
| Roles | `radar_app` (sin superusuario, sin crear bases ni roles; dueño del esquema `app`; `search_path=app`, `statement_timeout=30s`, `idle_in_transaction_session_timeout=60s`) y `radar_backup` (solo lectura, `search_path=app`) |
| Esquemas | `app` vacío, a la espera del primer arranque en Render; `public` sin permiso de creación para nadie más |
| Contraseñas | Generadas en la sesión de trabajo, nunca mostradas ni en el repositorio. Se cargarán en Render como secreto; si se pierden, se rotan con `ALTER ROLE … PASSWORD` desde la consola de Neon |

Pruebas reales (20/20) en una rama temporal `verificacion-2-1` copiada de `production` y **borrada al terminar**, para que el
administrador de prueba no quede en la base real. Evidencia: `docs/evidencia_piloto/lanzamiento/neon_real_verificacion.json`.
Migraciones desde cero (11 tablas en `app`, 0 en `public`, 17 índices, 11 PK, 2 únicas), `platform_meta` 2.1/nueva, 1 administrador,
reconexión tras cortar las 4 conexiones de la app (0/10 peticiones fallidas), persistencia tras reiniciar, copia con `radar_backup`
idéntica al origen y firmada, verificación, restauración en una base aparte, y denegaciones (`radar_backup` no escribe; `radar_app`
no crea bases ni tablas en `public`). Registros sin secretos.

Limitación de la prueba: este entorno no puede abrir el puerto 5432, así que el protocolo de PostgreSQL viajó por el WebSocket
seguro de Neon (puerto 443, `tests/piloto/puente_ws_neon.py`) con `sslmode=disable` en el tramo local. En Render la conexión es
directa con `sslmode=require` y debe comprobarse en el primer arranque (§5).
