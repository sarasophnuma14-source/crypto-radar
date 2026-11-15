# Plan de copia inicial y recuperación (R-10) · Crypto Radar 2.1.0

Fecha: 2026-11-15. Este plan complementa `RECUPERACION_DESASTRES.md`: el procedimiento ante un incidente sigue en su §3.
Aquí están la copia inicial, la verificación, la restauración probada y los objetivos de tiempo y de pérdida de datos.

**No se tocó ninguna base real.** Todo lo medido se hizo sobre bases PostgreSQL 16 temporales en local, creadas y
borradas por los propios scripts.

## 1. Procedimiento de la copia inicial (día del despliegue)

Se ejecuta desde una máquina de confianza, por ejemplo el ordenador del responsable. **No** se ejecuta en Render. La
máquina necesita la `DATABASE_URL` real con el endpoint **directo** de Neon, y la clave de copias.

```bash
export DATABASE_URL='postgresql://…@ep-….neon.tech/…?sslmode=require'   # endpoint directo, sin -pooler
export CRYPTO_RADAR_BACKUP_KEY='…'                                       # 32+ caracteres, distinta de la TOTP
python main.py preflight --db                     # 0 fallos antes de copiar
python main.py backup create --out backups        # solo lee la base; firma con HMAC
python main.py backup verify backups/crypto-radar-backup-AAAAMMDD-HHMMSS
```

1. `create` solo lee la base. Al terminar, compara la copia con el origen y debe decir «idéntica». Si dice
   «hubo escrituras durante la copia», repítela en un momento tranquilo.
2. `verify` comprueba la firma HMAC y el SHA-256 de cada tabla, y hace una restauración de prueba en una base SQLite
   temporal.
3. Prueba de restauración real: crea en Neon una **rama vacía o una base nueva**. Ejecuta
   `python main.py backup restore DIR --target '<URL de la base nueva>'` y después
   `python main.py backup compare DIR` con `DATABASE_URL` apuntando a esa base nueva. Borra la base de prueba al
   terminar.
4. Cifra la carpeta con `age` o `gpg` y guárdala fuera del repositorio y del servidor. La clave de copias y la clave
   TOTP se guardan **en otro sitio**.

Qué se copia y qué no:

| Se copia | No se copia |
| --- | --- |
| `users`, con las semillas TOTP **cifradas** | `sessions`: tras restaurar, todo el mundo vuelve a iniciar sesión |
| `activity`, `positions`, `payments`, `telegram_links`, `kv` (informes y ajustes) | `rate_limits`: se reconstruyen solos |
| `admin_enroll_tokens`, solo hashes, para que un código usado siga sin valer tras restaurar | Las claves (`*_KEY`): nunca viajan en la copia |

Una copia hecha con una versión anterior a esta rama no tiene la tabla `admin_enroll_tokens`, y esta versión no la
acepta. No es un problema práctico: todavía no existe ninguna copia real (R-10).

## 2. Integridad: qué se rechaza (probado)

| Caso | Resultado |
| --- | --- |
| Crear o verificar sin `CRYPTO_RADAR_BACKUP_KEY` | Error. No se crea nada |
| Verificar con otra clave | «Firma HMAC inválida» |
| Filas o manifiesto alterados, aunque se recalculen los hashes | Rechazada (`ataque_backup.py`) |
| Restaurar sobre la base de `DATABASE_URL` | Se niega |
| Restaurar sobre una base con datos | Se niega. La herramienta nunca borra |
| Restaurada con otra `CRYPTO_RADAR_TOTP_KEY` | El TOTP no se puede leer (503). La clave TOTP debe guardarse aparte |

## 3. Restauración en una base PostgreSQL vacía: resultados

Script: `tests/piloto/backup_inicial.py`. Usa las órdenes reales (`main.py backup …`, `main.py serve`,
`main.py preflight --db`) sobre bases temporales.

```
PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar [USUARIOS=200 ACTIVIDAD=20000 LATENCIA_MS=10] \
  python tests/piloto/backup_inicial.py salida.json
```

| Medida | Piloto (201 usuarios, 20 567 filas de actividad) | Escala ×5 (1001 usuarios, 202 700 filas) |
| --- | --- | --- |
| Pasos OK | **16 de 16** | **16 de 16** |
| Tamaño de la base de origen / de la copia | 13,1 MB / 3,9 MB | 50,2 MB / 26,8 MB |
| `backup create` | 0,62 s | 3,50 s |
| `backup verify` | 0,44 s | 3,31 s |
| `backup restore` (local) | 0,88 s | 5,05 s |
| `backup restore` con 10 ms de latencia por sentido (proxy TCP) | 4,18 s | 19,56 s |
| `backup compare` | 0,41 s | 1,79 s |
| Arranque del servidor y entrada del administrador con TOTP | 0,26 s | 0,28 s |
| RTO técnico medido (verificar + restaurar + arrancar) | 1,55 s | 7,12 s |

Evidencias en `docs/evidencia_piloto/cierre/`: `backup_inicial_piloto.json` y `backup_inicial_escala.json`.

**Hallazgo corregido en este trabajo.** La restauración insertaba fila a fila. Con 10 ms de latencia de red, como entre
una máquina local y Neon, la base del piloto tardaba **444,6 s**
(`backup_restaurar_latencia_antes.json`). Ahora inserta en lotes de 1000 filas (`executemany`) y tarda **4,2 s**, más de
100 veces menos. Con la base ×5 local, el tiempo bajó de 20,6 s a 5,1 s.

## 4. Objetivos de recuperación (propuesta para aprobar)

| Objetivo | Propuesta para el piloto | En qué se basa |
| --- | --- | --- |
| **RTO** (tiempo hasta volver a dar servicio) | **≤ 30 min**, contando los pasos manuales | Lo técnico mide < 20 s con la base ×5 y latencia. El resto son pasos manuales: crear la base en Neon, cambiar `DATABASE_URL`, redesplegar (3–5 min en Render), comprobar. **Sin medir en Render ni en Neon** |
| **RPO** (datos que se aceptan perder) | **≤ 24 h** con copias propias diarias; **≤ minutos** si la ventana de historial de Neon cubre el incidente | Con copias lógicas, lo perdido es todo lo escrito desde la última copia (paso 16 del script). La ventana de Neon depende del plan y **no se ha verificado** |
| Pagos | Pérdida tolerable: 0 | Los pagos posteriores a la copia se reconcilian desde los paneles de Wompi y NOWPayments (`RECUPERACION_DESASTRES.md` §3.6). Hoy los pagos están desactivados |

Qué se pierde en concreto dentro del RPO:
- altas y cambios de plan;
- actividad;
- posiciones de la cartera simulada de cada usuario;
- vínculos de Telegram.

Los informes de escaneo (`kv`) se regeneran con el siguiente escaneo.

## 5. Rutina propuesta

- Una copia antes de cada despliegue y otra diaria, mientras dure el piloto. Hay que verificar cada una en el momento.
- Conservar 7 copias diarias y 4 semanales.
- Una vez al mes, restaurar en una rama de Neon y ejecutar `preflight --db` contra ella.
- Avisar si la última copia tiene más de 26 h. Hoy no está automatizado: alguien tiene que lanzar `backup create`.

## 6. Lo que requiere acceso real (validación externa)

1. Hacer la **primera copia real** y su verificación (§1). Hasta entonces, R-10 sigue abierto.
2. Comprobar en la consola de Neon la **ventana de historial** del plan y probar una vez la restauración por rama.
3. Medir el RTO completo en Render: cambiar `DATABASE_URL` a la base restaurada, redesplegar y comprobar `/healthz`.
4. Decidir dónde se guardan las copias cifradas y las dos claves.
