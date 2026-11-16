# Conexiones con Neon: endpoint directo, pooler y candado del líder

Auditoría correctiva, hallazgo H4 (2026-11-16). Este documento describe qué conexión usa cada parte de Crypto Radar
2.1, por qué el pooler de Neon no sirve para esta aplicación tal como está escrita, y qué queda pendiente del propietario.
**No se cambió DATABASE_URL en producción.** Nada de este documento se verificó contra el proyecto real de Neon: no hay
acceso a la consola ni a la API de Neon desde este entorno.

## 1. Qué hace Neon (documentación oficial consultada el 2026-11-16)

Fuente: https://neon.com/docs/connect/connection-pooling

| Concepto | Valor documentado |
|---|---|
| Pooler | PgBouncer, `pool_mode=transaction` |
| Cómo se elige | host con sufijo `-pooler` (p. ej. `ep-xxx-pooler.region.aws.neon.tech`); sin sufijo = endpoint directo |
| No soportado a través del pooler | `SET`/`RESET` de sesión, `LISTEN`/`NOTIFY`, **candados consultivos de sesión**, cursores `WITH HOLD`, `PREPARE` SQL, tablas temporales que duren más de una transacción |
| `max_client_conn` del pooler | 10 000 |
| `default_pool_size` | 0,9 × `max_connections` |
| `query_wait_timeout` | 120 s |
| `max_connections` directo | 0,25 CU: 112 (7 reservadas → 105 útiles) · 0,5 CU: 225 · 1 CU: 450 · 2 CU: 901 |

El plan y el tamaño de cómputo del proyecto real **no están verificados** (pendiente R-23 del propietario).

## 2. Qué usa cada parte de la aplicación

| Parte | Conexión | Estado de sesión que necesita | ¿Funciona con pooler? |
|---|---|---|---|
| `radar/db.py` (peticiones web, escáner, paper trading, Telegram) | `DATABASE_URL`, una conexión **autocommit por hilo** (`threading.local`) | `SET client_encoding` al conectar; en `init()`, `pg_advisory_lock` y `pg_advisory_unlock` **en sentencias separadas** | **No.** En modo transacción cada sentencia puede ir a otro servidor: el `SET` se pierde y el candado del arranque puede quedar tomado en una conexión del pooler que nadie libera |
| `radar/db.py` escrituras protegidas (`_fenced_upsert`) | la misma conexión del hilo, **en una transacción** | ninguno fuera de la transacción (`SET LOCAL`, `FOR SHARE`) | Sí, en sí misma (todo ocurre dentro de una transacción) |
| `radar/leader.py` (candado del líder) | **conexión dedicada**: `CRYPTO_RADAR_LEADER_DATABASE_URL` o, si no existe, `DATABASE_URL`; si el host lleva `-pooler.` se usa el mismo host sin él (`leader.leader_url`) | candado consultivo **de sesión** mantenido mientras la instancia es líder | **No**, por eso se fuerza el directo |
| `radar/backup.py` | `DATABASE_URL` | lecturas | Sí, pero el directo es lo esperado |

Conclusión: **la aplicación debe usar el endpoint directo.** Separar solo el líder no basta, porque el arranque y el
`SET` de cada conexión también son de sesión. Lo que se hizo en el código:

1. El candado del líder usa siempre el endpoint directo, aunque `DATABASE_URL` apunte al pooler (`leader.leader_url`, prueba
   `ConexionesNeon.test_el_lider_nunca_usa_el_pooler`). Se puede dar una URL propia con `CRYPTO_RADAR_LEADER_DATABASE_URL`
   (por ejemplo, otro rol con menos permisos); también se corrige al directo.
2. Al arrancar, **antes** de `db.init()`, si `DATABASE_URL` apunta al pooler se imprime un aviso sin mostrar la URL
   (`db.endpoint_warning`).
3. `python3 main.py preflight` pasa de *aviso* a **fallo** cuando el host lleva `-pooler.` (prueba
   `T24_Preflight.test_pooler_de_neon_es_fallo`).

No se cambió el comportamiento de `db.py` para «corregir» la URL de la aplicación por su cuenta: eso equivaldría a
cambiar la configuración de producción sin autorización. Si el propietario confirma que usa el directo, no hay nada
que cambiar.

## 3. Conexiones por instancia

Cuenta a partir del código (`radar/server.py`, `radar/leader.py`), no medida en Neon:

| Hilo | Conexiones |
|---|---|
| Servidor HTTP con hilos fijos (`CRYPTO_RADAR_WORKERS`, por defecto 16) | hasta 16 |
| Planificador (escaneo, memecoins, vigilancia de precios) | 1 |
| Paper trading (si `PAPER_TRADING=1`) | 1 |
| Telegram (solo en el líder) | 1 |
| Comprobación de salud | 1 |
| Candado del líder (dedicada) | 1 |
| Hilos puntuales (escaneo manual, memecoins a demanda) | hasta 2 mientras duran |
| **Total por instancia** | **≈ 23** |

Durante un despliegue Render arranca la instancia nueva antes de parar la antigua: **≈ 46** durante el solapamiento.
Con un tercer proceso (por ejemplo, `main.py backup` o `preflight --db` lanzados a mano) se suman 1–2.

Frente a los límites del endpoint directo: con 0,25 CU caben 105 conexiones útiles; 46 deja margen para dos instancias
y herramientas. Si se sube `CRYPTO_RADAR_WORKERS`, cada hilo HTTP suma una conexión por instancia (y dos durante un
despliegue). Regla práctica: `2 × (WORKERS + 7) + 5 ≤ conexiones útiles del plan`.

Neon puede suspender el cómputo por inactividad (*scale to zero*) según el plan: las conexiones se cortan, el candado
del líder se libera y la siguiente instancia que reconecte lo toma con una generación nueva (pruebas H3:
`FencingGeneracion.test_6_reinicio_de_postgresql`).

## 4. Despliegues solapados y el líder

- Ambas instancias intentan el candado; solo una lo obtiene. La nueva espera a que la antigua lo suelte (al terminar o al
  cortarse su sesión).
- Cada adquisición incrementa `leader_epoch.generation`. Toda escritura de resultados de fondo comprueba la generación
  en la misma transacción (`db._fenced_upsert`). Si la instancia antigua sigue a mitad de un escaneo cuando la nueva
  toma el relevo, sus escrituras posteriores se rechazan (`StaleLeader`) y no sobrescriben el resultado nuevo.
- Las alertas de Telegram se registran (escritura protegida) **antes** de enviarse (`radar/alerts.py`): una instancia
  antigua cuyo registro se rechaza no envía la alerta.

Límite conocido: el fencing protege las escrituras en `kv`. Un efecto externo hecho **después** de la última escritura
(p. ej. un envío) por una instancia que pierde el candado justo en ese instante puede ocurrir una vez; el registro
previo evita que se duplique.

## 5. Pendiente del propietario

| Acción | Por qué | Cómo comprobarlo sin compartir secretos |
|---|---|---|
| Confirmar que `DATABASE_URL` de 2.1 usa el endpoint **directo** | si usa `-pooler`, el arranque y el `SET` fallan de forma intermitente | Consola de Neon → Connection details: el host **no** termina en `-pooler`; o `main.py preflight` en el servicio (no imprime la URL) |
| Confirmar plan y tamaño de cómputo (R-23) | define `max_connections` y la suspensión por inactividad | Consola de Neon → Billing / Compute |
| Decidir si se crea un rol propio para el líder | mínimo privilegio: solo necesita `leader_epoch` y `pg_locks` | crear el rol en Neon y poner su URL en `CRYPTO_RADAR_LEADER_DATABASE_URL` |
