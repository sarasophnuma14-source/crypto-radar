# Instalación, variables de entorno y despliegue

## 1. Uso local (un solo usuario, como siempre)

Nada cambió para el uso en el Mac: `instalar.command` sigue funcionando y el panel abre en `http://localhost:8777`.

```
python3 main.py serve          # panel + escaneos automáticos
python3 main.py scan           # un escaneo ahora
python3 tests/test_suite.py -v # batería de pruebas (166 con SQLite)
```

Requisitos: Python 3.10 o superior. El radar solo usa la librería estándar. `psycopg` solo hace falta con PostgreSQL.

## 2. Modo SaaS en local (para probar cuentas y planes)

```
CRYPTO_RADAR_ACCOUNTS=1 CRYPTO_RADAR_ADMIN_USER=admin CRYPTO_RADAR_ADMIN_PASSWORD='una clave larga de admin' python3 main.py serve
```

Sin `DATABASE_URL` usa SQLite en `data/app.db`. Al arrancar se crea (o confirma) la cuenta de administrador con esos datos.

Rutas del sitio unificado:

| Ruta | Qué muestra |
| --- | --- |
| `/` | Web de ventas (pública) |
| `/entrar` | Inicio de sesión y pestaña «Solicitar acceso» (`/entrar#solicitar`) |
| `/app` | La aplicación. Sin sesión redirige a `/entrar` |

Flujo de acceso: el visitante elige su usuario y contraseña en «Solicitar acceso». La cuenta queda **pendiente** y no
puede entrar hasta que el administrador la apruebe en **Configuración → Usuarios y solicitudes de acceso**, donde
también puede rechazar, desactivar, eliminar, asignar plan y días, crear usuarios ya aprobados y restablecer contraseñas.
Nadie puede convertirse en administrador desde la web.

## 3. Variables de entorno

| Variable | Obligatoria | Para qué |
| --- | --- | --- |
| `CRYPTO_RADAR_ACCOUNTS` | No | `1` activa cuentas, planes y pagos. Vacía: modo de un solo usuario |
| `DATABASE_URL` | Sí con cuentas en Render | PostgreSQL (`postgresql://usuario:clave@host/db?sslmode=require`). Guarda usuarios, sesiones, pagos y también los informes del escáner |
| `CRYPTO_RADAR_ADMIN_USER` | Sí con cuentas | Usuario del administrador. Se crea al arrancar (plan Élite, aprueba solicitudes, botón de escaneo, ajustes) |
| `CRYPTO_RADAR_ADMIN_PASSWORD` | Sí con cuentas | Contraseña del administrador, mínimo 12 caracteres. Solo se usa al crearlo |
| `CRYPTO_RADAR_ADMIN_RESET` | No | `1` vuelve a poner la contraseña de `CRYPTO_RADAR_ADMIN_PASSWORD` al arrancar (si la olvidaste). Quítala después |
| `CRYPTO_RADAR_PASSWORD` | Sí sin cuentas fuera de localhost | Contraseña única del panel en el modo antiguo |
| `CRYPTO_RADAR_HOST` | No | `0.0.0.0` en servidores |
| `PORT` | No | Puerto (Render lo pone solo) |
| `KEEPALIVE` | No | `1` para que Render gratis no duerma el servicio |
| `TELEGRAM_BOT_TOKEN` | No | Bot de Telegram. Con cuentas, cada usuario lo vincula desde Configuración |
| `TELEGRAM_CHAT_ID` | No | Solo en el modo de un solo usuario |
| `WOMPI_PUBLIC_KEY` | Para cobrar con Wompi | Llave pública del comercio |
| `WOMPI_INTEGRITY_SECRET` | Para cobrar con Wompi | Secreto de integridad (firma del checkout) |
| `WOMPI_EVENTS_SECRET` | Para cobrar con Wompi | Secreto de eventos (firma del webhook) |
| `WOMPI_API` | No | `https://sandbox.wompi.co/v1` para pruebas; por defecto producción |
| `COP_PER_USD` | Para cobrar con Wompi | Tasa para cobrar en pesos el precio en dólares (p. ej. 4100). Sin ella Wompi queda desactivado |
| `NOWPAYMENTS_API_KEY` | Para cobrar en cripto | Clave de API de NOWPayments |
| `NOWPAYMENTS_IPN_SECRET` | Para cobrar en cripto | Secreto IPN (firma HMAC-SHA512) |
| `CRYPTO_RADAR_STORAGE` | No | `db` guarda los informes en la base aunque no haya `DATABASE_URL` |

Si faltan las claves de un proveedor, ese método de pago aparece desactivado. **Nunca se concede un plan sin la
confirmación del proveedor**: el webhook se verifica con su firma y además se vuelve a consultar la transacción en la API
(estado, referencia, monto y moneda).

## 4. Desplegar en Render con cuentas

1. Crea una base PostgreSQL gratis en [Neon](https://neon.tech) y copia la cadena de conexión.
2. En Render, el servicio `crypto-radar` ya existe. En **Environment** añade `CRYPTO_RADAR_ACCOUNTS=1`, `DATABASE_URL`,
   `CRYPTO_RADAR_ADMIN_USER`, `CRYPTO_RADAR_ADMIN_PASSWORD` y, si vas a cobrar, las claves de Wompi y NOWPayments. `render.yaml` ya las lista.
3. Despliega. El comando de compilación instala `requirements.txt` (psycopg). En el registro debe aparecer
   `Modo cuentas activo · base de datos postgresql`. Si dice `sqlite`, falta `DATABASE_URL` y las cuentas se perderían.
4. Entra en `https://TU-APP.onrender.com/entrar` con el usuario y la contraseña de administrador. Las solicitudes nuevas
   aparecen en Configuración → Usuarios y solicitudes de acceso, con un contador de pendientes.
   El antiguo servicio estático `crypto-radar-ventas` ya no hace falta: la web de ventas vive en `/`. Puedes borrarlo en Render.
5. Webhooks:
   - Wompi (panel de comercio → Desarrolladores → URL de eventos): `https://TU-APP.onrender.com/api/billing/wompi/webhook`
   - NOWPayments (Store settings → IPN callback): `https://TU-APP.onrender.com/api/billing/nowpayments/ipn`
6. Haz un pago de prueba en el sandbox de cada proveedor (`WOMPI_API=https://sandbox.wompi.co/v1` y llaves de prueba)
   y comprueba en Configuración → Pagos que aparece como verificado y que el plan cambió.

Para volver al modo anterior basta con quitar `CRYPTO_RADAR_ACCOUNTS`.

## 5. Recalcular el backtest

```
CRYPTO_RADAR_HOME=$(pwd) python3 research/fetch_panel.py      # descarga el panel (una vez, ~16 MB, necesita acceso a Binance)
python3 research/backtest_pro_run.py                           # ~8 minutos
cp data/research/backtest_pro_results.json docs/backtest_results.json
```

Binance bloquea IP de EE. UU.; ejecútalo desde una conexión de otro país.
