# Configuración de Render para la 2.1.0 (servicio nuevo e independiente)

Fecha: 2026-11-16. **No se ha creado nada:** esta sesión no tiene acceso a Render (la API responde 401 y no hay
conector). Lo que solo se puede comprobar en Render va marcado **[VALIDAR EN REAL]**.

## 1. Reglas

- **Servicio nuevo.** No es el de la 2.0.0, no se clona y no comparte variables con él.
- **Créalo a mano**, como *New → Web Service*, **no desde el Blueprint**:
  - el `render.yaml` del repositorio define un servicio llamado `crypto-radar`, el mismo nombre que el de la 2.0.0;
  - sincronizar un Blueprint desde `main` podría tocar ese servicio (`ESTADO_LANZAMIENTO_2_1.md` §2.4).
- Antes de crearlo, la 2.0.0 debe estar fijada en la rama `production-2.0.0` (`ESTADO_LANZAMIENTO_2_1.md` §2).

## 2. Servicio

| Campo | Valor |
| --- | --- |
| Nombre | `crypto-radar-2-1` |
| Repositorio y rama | Este repositorio, rama `main` **después** de fusionar #3 a #8 |
| Región | **Frankfurt**. Binance bloquea IPs de EE. UU., y queda junto a Neon eu-central-1 |
| Plan | **Starter**: 0,5 CPU y 512 MB, US$7/mes más consumo. [VALIDAR EN REAL] el precio en la pantalla de alta |
| Runtime | Python |
| Build command | `pip install -r requirements.txt` |
| Start command | `python main.py serve` |
| Health check path | `/healthz` |
| Auto-Deploy | **Off**. Se despliega una vez y a mano |
| Instancias | 1 |
| Reinicio automático | Render reinicia el proceso si cae o si falla `/healthz`. No hay que configurar nada más |

**Tiempos:**
- el servidor cierra las conexiones ociosas a los 30 s (`radar/server.py`);
- la base corta las consultas a los 30 s (`statement_timeout` del rol, en `CONFIGURACION_NEON_2_1.md` §3);
- [VALIDAR EN REAL] el *health check timeout* de Render.

## 3. Variables (todas nuevas; ninguna copiada de la 2.0.0)

Los secretos se generan en el ordenador del responsable con
`python -c "import secrets;print(secrets.token_urlsafe(48))"`. Uno distinto para cada variable. Se pegan en Render
como *Secret* y se guardan en el gestor de contraseñas. **Nunca en el chat ni en el repositorio.**

| Variable | Valor |
| --- | --- |
| `PYTHON_VERSION` | `3.12.7` |
| `CRYPTO_RADAR_HOST` | `0.0.0.0` |
| `CRYPTO_RADAR_ACCOUNTS` | `1` |
| `DATABASE_URL` | La URL **directa** de Neon 2.1 con `radar_app` y `sslmode=require` (`CONFIGURACION_NEON_2_1.md` §4) |
| `CRYPTO_RADAR_ADMIN_USER` | Nombre nuevo del administrador |
| `CRYPTO_RADAR_ADMIN_PASSWORD` | Contraseña nueva de 12 o más caracteres, sin el nombre de usuario |
| `CRYPTO_RADAR_ADMIN_TOTP` | `required` |
| `CRYPTO_RADAR_TOTP_KEY` | Secreto nuevo de 32 o más caracteres |
| `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` | Secreto nuevo. **Solo** el día del alta del TOTP; se borra después (`BOOTSTRAP_ADMIN.md` §3) |
| `CRYPTO_RADAR_PAYMENTS` | `off` |
| `MALLOC_ARENA_MAX` | `2` |
| `KEEPALIVE` | `0`. Starter no se duerme |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Opcionales. Un bot **distinto** del de la 2.0.0, para no mezclar alertas |

**No se definen en Render:**
- `CRYPTO_RADAR_BACKUP_KEY`: solo en la máquina que hace las copias, y distinta de la clave TOTP;
- `CRYPTO_RADAR_PILOT`: sin definir, el piloto queda cerrado;
- `WOMPI_*`, `NOWPAYMENTS_*`;
- `CRYPTO_RADAR_ALLOW_SQLITE`, `CRYPTO_RADAR_ADMIN_RESET`, `CRYPTO_RADAR_ADMIN_TAKEOVER`,
  `CRYPTO_RADAR_PLATFORM_ADOPT`.

`CRYPTO_RADAR_BACKUP_KEY` debe ser **distinta** de `CRYPTO_RADAR_TOTP_KEY`. El arranque y el preflight comprueban:
- que las claves sean independientes y tengan longitud suficiente;
- que los pagos estén en `off`;
- que el TOTP sea obligatorio;
- que la conexión a la base vaya con TLS.

Los mensajes nunca muestran valores (`radar/pilot.py`, `radar/preflight.py`).

## 4. Acceso restringido (instancia interna)

Mientras G-16 siga pendiente:
- **no** se comparte la URL;
- **no** se invita a nadie externo;
- **no** se aprueban solicitudes de acceso ajenas al equipo.

El registro ya es solo por solicitud, con aprobación manual.

Las cuentas `prueba01` a `prueba10` de la prueba de 10 usuarios se desactivan al terminar.

## 5. Despliegue

Sigue `PROCEDIMIENTO_LANZAMIENTO_PILOTO.md` §3 a §8, sobre este servicio:
1. preflight;
2. despliegue único;
3. registro de arranque;
4. bootstrap del TOTP;
5. borrar el código de alta;
6. prueba de humo;
7. persistencia tras reiniciar;
8. primera copia;
9. prueba de 10 usuarios.

Si falla una condición crítica:
- **Suspend** del servicio 2.1 (`PROCEDIMIENTO_ROLLBACK.md` §1);
- la 2.0.0 no se toca.
