# Despliegue real de Crypto Radar 2.1 (2026-11-16)

Estado: **2.1 funcionando en Render con su propia base Neon, en piloto cerrado** (registro solo por solicitud y
aprobación, pagos desactivados). **No apta para abrir al público**: G-16 (texto legal de privacidad) sigue pendiente.

## Qué se desplegó

| Elemento | Valor |
| --- | --- |
| Commit desplegado | `2f6df27` en la rama exclusiva `release-2.1` (igual a `claude/preparacion-piloto`, PR #8) |
| PR integrados en main | **Ninguno**. 2.1 se despliega desde su rama; `main` y `production-2.0.0` siguen en `9176b36` |
| Servicio Render 2.1 | `crypto-radar-2-1` (`srv-dbt67erbc2fs73d7s74g`), Frankfurt, Starter, Python 3.12.7, Auto-Deploy **off**, `python main.py serve` |
| URL | https://crypto-radar-2-1.onrender.com |
| Base Neon | Proyecto `MyCryptoRadar` (`mute-sky-79699743`), rama `production`, base `radar`, endpoint directo `ep-polished-lake-b9lfqq5g`, PG 16 |
| Migraciones | Desde cero en el primer arranque (02:22Z): 11 tablas en `app`, 0 en `public`; `platform_meta` 2.1 / nueva; 1 administrador (`patron`) |
| Variables (sin valores) | `PYTHON_VERSION`, `CRYPTO_RADAR_HOST`, `CRYPTO_RADAR_ACCOUNTS=1`, `DATABASE_URL` (radar_app, `sslmode=require&channel_binding=require`), `CRYPTO_RADAR_ADMIN_USER`, `CRYPTO_RADAR_ADMIN_PASSWORD`, `CRYPTO_RADAR_ADMIN_TOTP=required`, `CRYPTO_RADAR_TOTP_KEY`, `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN`, `CRYPTO_RADAR_PAYMENTS=off`, `MALLOC_ARENA_MAX=2`, `KEEPALIVE=0` |
| 2.0.0 | Servicio `crypto-radar` (`srv-dbs9mkbrjlhs73djcs8g`) **sin cambios** (última actualización 2026-11-16T00:24Z, antes de esta sesión); `/healthz` 200 |

## Pruebas realizadas EN RENDER Y NEON REALES

| # | Prueba | Resultado |
| --- | --- | --- |
| 1 | Arranque y migraciones desde cero | OK: "esquema verificado · Plataforma 2.1 · nueva · piloto cerrado · Administrador: patron · creado" |
| 2 | `/healthz`, `/`, `/entrar` | 200; `/app` 302 sin sesión; API sin sesión 401 |
| 3 | Inicio de sesión del administrador | OK con la contraseña correcta; cookie `Secure; HttpOnly; SameSite=Lax`; la cuenta exige activar TOTP (`totp_setup_required: true`) |
| 4 | Contraseña incorrecta | 401 "Usuario o contraseña incorrectos" |
| 5 | Registro | Rechazado sin aceptar la política y el aviso de riesgo (400); el acceso es por solicitud con aprobación |
| 6 | Webhook de pagos desde origen no permitido | 403; pagos `off` |
| 7 | Escáner y fuentes de datos (desde Frankfurt) | OK: CoinGecko, Fear & Greed, Binance spot (518 pares), funding, klines (71 activos), libros (25); primer escaneo 02:25:54Z |
| 8 | Persistencia tras reiniciar (redespliegue 02:24Z) | OK: "Administrador: patron · verificado", 1 usuario, `platform_meta` intacta |
| 9 | Copia con `radar_backup` (solo lectura) | OK: idéntica al origen, firmada HMAC, verificada |
| 10 | Restauración | OK en una base temporal `restauracion_prueba` del mismo proyecto (users 1, platform_meta 3), borrada después |
| 11 | Carga controlada | 120 peticiones, 10 concurrentes: 120 × 200, p50 0,19 s, p95 0,49 s, máx 0,77 s |
| 12 | Registros | Sin errores tras el arranque; ninguna contraseña, clave TOTP, código de alta ni URL de la base en los registros |
| 13 | Base con TLS | `sslmode=require` y `channel_binding=require` en la URL; el arranque en Render se niega sin TLS. `pg_stat_ssl` muestra `ssl=f` porque Neon termina TLS en su proxy |
| 14 | Privilegios mínimos | `radar_app` no crea bases ni tablas en `public`; `radar_backup` no escribe |

Pruebas en rama temporal de Neon (antes del despliegue): 20/20, ver `CONFIGURACION_NEON_2_1.md` §8.

Incidencias resueltas durante el despliegue:
- primer arranque sin claves: el servidor se negó a arrancar (comportamiento esperado);
- contraseña de `radar_app` no coincidía tras el reinicio de contraseña en la consola: se alineó con SQL.

## No hecho o pendiente

| Pendiente | Quién | Detalle |
| --- | --- | --- |
| Activar TOTP del administrador | PATRON | Entrar en `/entrar`, activar TOTP con el código de alta (`CRYPTO_RADAR_ADMIN_ENROLL_TOKEN`, vale 24 h) y **después borrar esa variable** en Render |
| Health Check Path `/healthz` en 2.1 | PATRON | El conector de Render no permite cambiarlo; Settings del servicio |
| Proteger 2.0 antes de cualquier merge a main | PATRON | `crypto-radar` y `crypto-radar-ventas` despliegan desde `main` con Auto-Deploy on: pasar a `production-2.0.0` y Auto-Deploy off. Hasta entonces **no se fusiona nada en main** |
| Rotar la contraseña de `radar_app` | PATRON | Pasó por el chat. Reset en Neon y sustituirla en `DATABASE_URL` de Render |
| Telegram | PATRON | Falta un bot nuevo (@BotFather) para 2.1: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID`. No probado |
| Paper trading D_volmom | Decisión | El almacenamiento del paper trading es de archivos locales y el disco de Render se borra en cada despliegue: no persistiría. No iniciado |
| Copias periódicas | PATRON | Requieren una máquina de confianza con `CRYPTO_RADAR_BACKUP_KEY` propia; la copia de prueba se hizo en la sesión de trabajo (efímera) |
| Repositorio privado | PATRON | Sigue público |
| G-16 privacidad | Abogado | 11 marcas COMPLETAR: impide abrir al público |
