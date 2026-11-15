# CHANGELOG

## 2.1.0 — 2026-11-15 · Sitio unificado y acceso aprobado por el administrador

- Una sola web: ventas en `/`, inicio de sesión moderno en `/entrar` y la app en `/app` (se elimina `ventas/`).
- Se acabó la ventana de contraseña del navegador: cada persona elige usuario y contraseña al solicitar acceso, y solo
  entra cuando el administrador la aprueba. El administrador sale de `CRYPTO_RADAR_ADMIN_USER` / `_PASSWORD`.
- Panel de administración: aprobar, rechazar, desactivar, eliminar, asignar plan y días, crear usuarios y restablecer claves.
- Seguridad: contraseñas con scrypt, sesión HttpOnly/SameSite/Secure rotada al entrar, CSRF, bloqueo tras 5 fallos,
  límites por IP y global en solicitudes, mismo error para usuario inexistente y clave errónea, CSP sin scripts en línea
  ni CDN (librerías servidas desde `/static/vendor`), HSTS, COOP y Permissions-Policy.
- La sección de resultados y backtests de la web de ventas se sustituye por «Primero protege tu capital».

### Auditoría final de seguridad
- Arranque del administrador: nunca promueve una cuenta normal que tenga su nombre; el servidor no arranca o, con
  `CRYPTO_RADAR_ADMIN_TAKEOVER=1`, pone esa cuenta en cuarentena y crea un administrador nuevo con la clave del
  entorno. Nombres reservados. Eventos `admin_bootstrap_*` en la actividad.
- Permisos por plan revisados en todas las rutas: backtest solo Élite; paper trading solo admin; alertas, diario,
  escaneos, velas e historial filtrados por plan; cartera y Telegram exigen Pro también en las escrituras.
- Migraciones: solo se tolera «la columna ya existe»; el esquema completo se comprueba antes de arrancar.
- Límites de intentos guardados en la base (sobreviven a reinicios). En Render, el modo cuentas sin PostgreSQL no arranca.
- `docs/SEGURIDAD.md` con la matriz de permisos, las limitaciones y la propuesta para producción. 181 pruebas.
- `serve()` exige `CRYPTO_RADAR_ADMIN_USER` y `CRYPTO_RADAR_ADMIN_PASSWORD` en modo cuentas y se detiene si falta
  alguna o si no se confirma el administrador. 11 pruebas nuevas del arranque real en procesos aislados (192 en total).

### Preparación para producción
- Verificación en dos pasos (TOTP, RFC 6238) para todas las cuentas; **obligatoria para administradores**
  (`CRYPTO_RADAR_ADMIN_TOTP=required` por defecto): sin ella, toda acción de administración responde 403. Códigos de
  un solo uso, ventana ±30 s, fallos cuentan para el bloqueo, activar cierra las sesiones, `ADMIN_RESET` la borra.
- Pagos con modo explícito `CRYPTO_RADAR_PAYMENTS=off|sandbox|live` (por defecto `off`, también en `render.yaml`).
  Sandbox usa solo las APIs y llaves de prueba. Se elimina `WOMPI_API`. `python main.py payments-selftest`.
- Copias de seguridad verificables: `python main.py backup create|verify|compare|restore` (hashes SHA-256,
  restauración solo en bases vacías, prueba real de restauración al verificar).
- `python main.py preflight [--db]`: revisión de la configuración de Render y Neon sin mostrar secretos.
- Política de tratamiento de datos (`/privacidad`, borrador Ley 1581 de 2012 con datos por completar) y aviso de
  riesgo (`/aviso-de-riesgo`). La solicitud de acceso exige aceptarlos y guarda versión y fecha del consentimiento.
- `docs/PRODUCCION_RENDER_NEON.md` y `docs/PREPARACION_PRODUCCION.md`.

### Auditoría final antes del piloto cerrado
- Servidor con hilos fijos (`CRYPTO_RADAR_WORKERS`, 16) y cola de escucha de 128: con 100 usuarios simultáneos,
  0 errores (antes 23 % de inicios de sesión rechazados), 15 conexiones a PostgreSQL en total (antes una por
  petición) y 345 MB (antes 514 MB). Reconexión automática si PostgreSQL/Neon corta la conexión.
- Copias de seguridad firmadas con HMAC (`CRYPTO_RADAR_BACKUP_KEY`): ya no se pueden alterar recalculando hashes.
- NOWPayments: la firma se verifica sobre el JSON de JavaScript (antes se rechazaban IPN con tildes o exponentes).
- Telegram: 10 intentos de vinculación por chat y hora.
- `render.yaml`: `MALLOC_ARENA_MAX=2`.
- 27 pruebas nuevas (258) y scripts reproducibles en `tests/piloto/`: ataques, XSS en navegador, simulacro de
  desastre, carga y entorno. Informes `docs/AUDITORIA_FINAL_PILOTO.md`, `PRUEBAS_RENDIMIENTO.md`,
  `RECUPERACION_DESASTRES.md` y `MATRIZ_RIESGOS_PENDIENTES.md`. Veredicto: apto para piloto cerrado con condiciones.

## 2.0.0 — 2026-11-15 (rama `claude/project-thread-i8udp5`)

Respaldo de la versión anterior: rama `main` (commit 34f6898) y etiqueta local `backup-pre-2.0`.

### Fase A · Auditoría
- `AUDIT_REPORT.md`: 40 hallazgos (7 críticos, 13 altos, 14 medios, 6 bajos) con archivo, línea, evidencia y solución.

### Fase B · Correcciones críticas
- Backtest simple: entra a la apertura siguiente (antes compraba al mismo cierre de la señal).
- Backtest de cartera: exposición con órdenes pendientes, stop el día del llenado, valoración al último cierre.
- Señales solo con velas cerradas. Escrituras atómicas y alertas sin duplicados entre hilos.
- Seguridad: CSRF, límite de intentos, cuerpo máximo de 64 KB, cabeceras CSP/nosniff/frame, números finitos.

### Fases C a F · Motor cuantitativo nuevo (`radar/quant`)
- Calidad de datos, indicadores causales, Early Entry Detector por 7 familias sin indicadores repetidos.
- Detector de manipulación con evidencias, Exit Intelligence de 4 decisiones, régimen de 5 estados y plan de operación.

### Fase G · Backtest profesional
- `radar/quant/backtest_pro.py`: universo por fecha (sin elegir las ganadoras de hoy), órdenes límite y stop-buy reales,
  costes, stops pesimistas, parciales, freno por drawdown con pausa, monedas retiradas.
- `research/backtest_pro_run.py`: diseño y fuera de muestra, calibración, walk-forward anual, sensibilidad y validación del puntaje.
- Resultado honesto en `BACKTEST_REPORT.md`: **no supera la validación fuera de muestra**.

### Fase H · Memecoins
- `radar/meme_radar.py`: antigüedad, liquidez, volumen relativo, FDV, perfil de riesgo; on-chain N/D.

### Fase I · Smart Portfolio
- `radar/quant/portfolio.py`: tamaño por riesgo y límites por activo, categoría, correlación, riesgo abierto y drawdown.

### Fases J y K · Escáner y Telegram
- Escáner con el motor nuevo, descargas en paralelo y libro de órdenes. Ranking que prioriza fases tempranas.
- Alertas por transición (PRE-EXPLOSION, ruptura, zona de entrada, riesgo, distribución, salida, régimen) y resúmenes diario y semanal.

### Fase L · SaaS
- Cuentas, sesiones, CSRF, bloqueo de intentos, registro de actividad, planes Libre / Pro / Élite.
- Pagos con Wompi y NOWPayments: el plan solo se concede tras verificar la firma y reconsultar la transacción en la API.
- PostgreSQL en producción, SQLite en local. Bot de Telegram por usuario.

### Fase M · Interfaz
- Panel de 11 secciones: Dashboard, Oportunidades tempranas, Mercado, Rupturas, Memecoins, Salidas, Cartera,
  Backtesting, Rendimiento, Alertas, Configuración. Inicio de sesión, planes y administración. Solo datos del backend.

### Fase N · Pruebas
- `tests/test_suite.py`: 158 pruebas ejecutadas y aprobadas (`TEST_REPORT.md`). Encontraron y se corrigieron 3 fallos reales: IP falsificable en los límites por IP,
  texto como bytes en PostgreSQL SQL_ASCII y datos desactualizados marcados como válidos.

### Fase O · Documentación
- `docs/INSTALACION_Y_DESPLIEGUE.md`, `docs/ARQUITECTURA.md`, `PENDIENTES.md`, este archivo.
- `render.yaml` con las variables del modo SaaS y `requirements.txt` (psycopg).
- Web de ventas: la tarjeta del motor principal muestra el resultado fuera de muestra de la 2.0.

## Comparativa: versión original frente a 2.0

| Aspecto | Original (34f6898) | 2.0 |
| --- | --- | --- |
| Backtest | Compraba al cierre que generaba la señal; 26 monedas elegidas hoy | Orden desde la apertura siguiente; universo de 150 por fecha entre 661 pares; costes y stops pesimistas |
| Validación | Ninguna separación | Diseño / fuera de muestra, walk-forward, sensibilidad, validación del puntaje |
| Resultado medido | No comparable (sesgado) | +25,8 % en 6,3 años; −18,6 % fuera de muestra. Ventaja no demostrada |
| Velas | Usaba la vela del día aún abierta | Solo velas cerradas y control de calidad de datos |
| Puntaje | Indicadores contados varias veces | Cada indicador en una sola familia, con evidencias |
| Manipulación | Una regla de falsa ruptura | Detector con evidencias y libro de órdenes |
| Salidas | Una condición débil cerraba todo | 4 decisiones, al menos 2 familias para cerrar |
| Régimen | 5 estados, sin volatilidad | 5 estados con alta volatilidad y capitulación; ajusta tamaño, umbral y fases |
| Cartera | Riesgo por operación y % por activo | Límites por categoría, correlación, riesgo abierto, liquidez y drawdown |
| Usuarios | Una contraseña compartida | Cuentas individuales, sesiones seguras, planes, datos aislados |
| Pagos | Página de ventas sin cobro | Wompi y NOWPayments verificados con firma y API |
| Persistencia en Render | Se borraba en cada reinicio | PostgreSQL |
| Telegram | Un chat fijo | Cada usuario vincula su chat; comandos y resúmenes |
| Panel | Vistas originales | 11 secciones con datos reales |
| Pruebas | Scripts de humo | 158 pruebas automáticas |
