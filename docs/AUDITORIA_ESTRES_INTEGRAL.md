# Prueba de estrés integral · Crypto Radar 2.1.0

Fecha: 2026-11-15. Rama `claude/estres-integral`, sobre el PR #5 (`claude/auditoria-final-piloto`).

Reglas cumplidas:
- No se desplegó nada, no se fusionó ningún PR y no se tocó producción, Render ni Neon.
- Los pagos siguen desactivados.
- Estrategia, paper trading y ledger sin cambios: `git diff --quiet origin/main -- research radar/quant radar/edge radar/paper_trading` no devuelve diferencias.
- Todas las pruebas usaron bases PostgreSQL temporales, creadas y borradas por los scripts, y Telegram simulado: ningún mensaje salió a internet.

## 0. Resumen

| # | Pregunta | Resultado |
| --- | --- | --- |
| 1 | ¿Aguanta un escaneo con 10, 50 y 100 usuarios conectados? | **Sí: 0 errores.** El p95 del panel sube durante los 4–5 s del escaneo (de 17–50 ms a 150–470 ms) |
| 2 | ¿El escáner bloquea a los trabajadores HTTP? | Interfiere (GIL), no bloquea. Un proceso aparte lo elimina, pero **no se implementa**: con 512 MB no hay margen. Ver `ANALISIS_ESCANER_HTTP.md` |
| 3 | ¿Usuarios tras la misma IP? | **Corregido.** 50 de 50 entran (antes 30 de 50 recibían 429), sin debilitar el límite contra fuerza bruta. `X-Forwarded-For` solo desde proxies autorizados. Ver `RATE_LIMITING.md` |
| 4 | ¿PostgreSQL? | Reutiliza conexiones (19–20 en total), se recupera de cortes y no deja conexiones abandonadas. **Un reinicio real daba 15 errores 500: corregido**, ahora 0 |
| 5 | ¿Resistencia? | 50 usuarios × 10 min y 100 × 5 min, con escaneos repetidos y Telegram: **0 errores en 59.000 peticiones** y memoria estable |
| 6 | ¿Bastan 512 MB? | **La memoria sí** (pico de 339–341 MB con `MALLOC_ARENA_MAX=2`). **La CPU del plan gratis no**: con 0,1 CPU, 25 usuarios ya saturan el servidor. Ver la sección 6 |

Veredicto: **apto para el piloto cerrado** en las mismas condiciones del PR #5, con un cambio de recomendación:
- **plan Starter de Render (0,5 CPU, 512 MB) para hasta 50 usuarios activos;**
- el plan gratis solo para unas 10 personas y aceptando esperas de varios segundos.

## 1. Escaneo simultáneo con usuarios conectados

Script: `tests/piloto/estres.py`. Ejemplo:

```bash
PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar NIVELES=10,50,100 DURACION_S=90 REPETIR_ESCANEO=1 \
  python tests/piloto/estres.py docs/evidencia_piloto/estres/simultaneo_caliente.json
```

**Entorno**
- 4 CPU, Python 3.12.3 y PostgreSQL 16.15.
- Servidor real con 16 hilos.
- Datos de mercado sintéticos: 40 activos.

**Carga**
- Cada usuario repite peticiones del panel con 1 s de pausa: `/api/state`, `/api/me`, `/api/alerts`, `/api/positions` y `POST /api/me/settings`.
- El administrador lanza escaneos con `POST /api/scan`.
- Telegram: el sondeo real (`poll_forever`) contra un simulador local, con 2 comandos por segundo (`/estado`, `/top`, `/cartera`…) y una difusión de alerta cada 30 s a todos los chats.

Evidencia: `docs/evidencia_piloto/estres/simultaneo_caliente.json`, con 6 escaneos por tramo.

| Usuarios | Inicios de sesión | Panel p95 durante / fuera del escaneo | p99 durante / fuera | Máx. | Escaneo | CPU durante / fuera | RSS máx. | Errores |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | 10/10 | 149 / 17 ms | 186 / 30 ms | 223 ms | 3,8–3,9 s | 20 % / 7 % | 277 MB | **0** |
| 50 | 50/50 | 257 / 26 ms | 354 / 92 ms | 456 ms | 4,1–4,2 s | 40 % / 26 % | 362 MB | **0** |
| 100 | 100/100 | 306 / 50 ms | 415 / 126 ms | 467 ms | 4,2–4,5 s | 60 % / 49 % | 365 MB | **0** |

**Duración del escaneo**
- Sin usuarios dura 3,75 s; con 100 usuarios, 4,5 s.
- El primer escaneo de cada día dura unos 25 s por las pausas de cortesía con CoinGecko.

**PostgreSQL**
- 0 esperas por bloqueo en 1076 muestras.
- 0 consultas de más de 50 ms.
- 0 trazas de error en el registro.

**Telegram**

| Usuarios | Respuesta a un comando, p95 fuera / durante el escaneo | Máx. |
| --- | --- | --- |
| 10 | 52 / 119 ms | 163 ms |
| 50 | 54 / 255 ms | 299 ms |
| 100 | 68 / 230 ms | 371 ms |

- Todas las respuestas llegaron.
- Una difusión a 106 chats tarda 8,6–9,3 s, porque el bot espera 0,05 s entre mensajes para respetar el límite de Telegram. Es el comportamiento diseñado.

**Escaneo con datos reales**

Evidencia: `escaneo_real_50.json`. 74 activos, 50 usuarios y `MALLOC_ARENA_MAX=2`.

| | Durante el escaneo (43 s) | Fuera |
| --- | --- | --- |
| p95 del panel | 52 ms | 30 ms |
| p99 del panel | 182 ms | 52 ms |
| Respuesta de Telegram, p95 | 57 ms | 62 ms |

Resultado: 0 errores y un pico de memoria de 340 MB.

## 2. Aislamiento del escáner

Detalle en `docs/ANALISIS_ESCANER_HTTP.md`.
- El escáner compite por el GIL con los hilos HTTP.
- Con el prototipo de proceso aparte, el p95 durante el escaneo baja de 466 a 46 ms con 100 usuarios.
- Un escaneo real en su propio proceso llega a 151 MB, que se sumarían a los unos 340 MB del servidor.
- **Decisión: no implementarlo en un plan de 512 MB.** El documento fija los criterios para hacerlo.

## 3. Límites de inicio de sesión

Detalle en `docs/RATE_LIMITING.md`. **Cambio realizado** en `radar/auth.py` y `radar/server.py`.

**Diseño**
- Tope de 300 intentos por IP.
- **20 intentos fallidos por IP**: los aciertos ya no cuentan.
- Modo estricto con 5 fallidos por IP si en el sitio hay más de 200 fallos en 15 min.
- Se mantiene el bloqueo por cuenta (5 fallos, 15 min).

**`X-Forwarded-For`**
- Solo se acepta si la conexión viene de `CRYPTO_RADAR_TRUSTED_PROXIES`.
- En Render se acepta por defecto, como hasta ahora.
- Fuera de Render se ignora.

| Prueba | Antes | Después |
| --- | --- | --- |
| 50 inicios de sesión correctos simultáneos desde una IP, por HTTP (`carga.py` con `IP_COMPARTIDA=1`) | 20 OK, **30 con 429** (`carga_ip_compartida.json`) | **50 OK**, 0 con 429 (`estres/ip_compartida_despues.json`) |
| 20 contraseñas falsas desde una IP y luego la buena | 429 | 429 |
| 60 contraseñas falsas a la vez | — | como mucho 20 comprobadas |
| IP inventada en `X-Forwarded-For` sin proxy autorizado | eludía el límite | no lo elude |

16 pruebas nuevas en `T28_RateLimitingCombinado`.

## 4. PostgreSQL

**Reutilización**
- En todas las corridas hubo 19–20 conexiones de la app: 16 hilos HTTP, el sondeo de Telegram, la difusión y el hilo del escaneo.
- En la prueba de 10 minutos, con 18 escaneos, el número no creció.
- Cada escaneo abre una conexión nueva en su hilo y se cierra al terminar el hilo: 33 conexiones abiertas en total en 10 minutos.

**Conexiones abandonadas**
- Al terminar cada tramo, todas estaban en estado `idle`.
- 0 en `idle in transaction` en todas las muestras.
- No quedó ninguna conexión colgada.

**Corte y reinicio durante la carga**

Evidencia: `caos_postgres.json` antes y `caos_postgres_reintento.json` después. 50 usuarios, escaneos repetidos y Telegram.

| Evento | Antes | Después |
| --- | --- | --- |
| `pg_terminate_backend` de las 19 conexiones de la app (lo que hace Neon al suspender por inactividad) | 0 errores | 0 errores |
| Reinicio real de PostgreSQL (`pg_ctl restart -m fast`) | **15 respuestas 500** en 0,1 s y 16 trazas («the database system is starting up») | **0 errores, 0 trazas** |
| Recuperación | sin reiniciar la app | sin reiniciar la app |

**Corrección** en `radar/db.py`:
- Al **conectar**, si PostgreSQL responde con un error de conexión, se reintenta con esperas de 0,25, 0,5, 1 y 2 s.
- Nunca se repite una sentencia: la petición espera unos instantes en vez de fallar.
- Además, `connect_timeout=10` para que una conexión no quede colgada para siempre, salvo que la URL ya lo traiga.
- Con la base caída del todo, `/healthz` sigue devolviendo 500, ahora tras unos 4 s.
- Prueba: `T27.test_pg_connect_retries_while_database_starts`.

**Neon: qué no se pudo comprobar** (no hay acceso)
- La latencia TLS hasta Neon.
- El tiempo de arranque tras la suspensión.
- El comportamiento real del *pooler*.

Recomendaciones:
- Usar la URL **directa** de Neon (sin `-pooler`): 20 conexiones caben de sobra, y psycopg usa sentencias preparadas.
- Con la URL del *pooler*, comprobarlo antes en una rama de Neon.

## 5. Resistencia

Configuración de las dos pruebas:
- `MALLOC_ARENA_MAX=2`, como en `render.yaml`.
- Un escaneo cada ~35 s, regenerando los datos sintéticos en cada uno.
- Telegram con 2 comandos por segundo y una difusión cada 30 s.

| Prueba | Peticiones del panel | Errores | p95 / p99 total | p95 / p99 durante el escaneo | Escaneos | Telegram | RSS máx. / final | Conexiones PG |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 50 usuarios × 10 min (`resistencia_50x10min.json`) | 29.621 | **0** | 32 / 184 ms | 217 / 306 ms | 18, de 4,1–4,4 s | 1284 comandos, 19 difusiones | 338 / 233 MB | 20 máx., todas `idle` al final |
| 100 usuarios × 5 min (`resistencia_100x5min.json`) | 29.373 | **0** | 57 / 379 ms | 413 / 507 ms | 9, de 4,5–4,9 s | 649 comandos, 9 difusiones | 339 / 179 MB | 20 máx., todas `idle` al final |

- La memoria no crece con el tiempo: el pico es el mismo en 5 y en 10 minutos, y al terminar baja.
- 0 consultas lentas y 0 esperas por bloqueo.

## 6. Memoria y CPU: ¿bastan 512 MB?

### 6.1 Memoria

100 usuarios, 2 min y 8 escaneos. Evidencia: `memoria_sin_arena.json` y `memoria_arena2.json`.

| | Pico (VmHWM) | Al terminar | p95 del panel |
| --- | --- | --- | --- |
| Sin `MALLOC_ARENA_MAX` | 419 MB | 419 MB (no devuelve) | 200 ms |
| `MALLOC_ARENA_MAX=2` (lo que usa `render.yaml`) | **339 MB** | **176 MB** | 234 ms |

En todas las corridas con `MALLOC_ARENA_MAX=2` el pico quedó entre 338 y 341 MB:
- resistencia;
- escaneo real con 74 activos;
- plan Starter emulado.

Eso deja unos 170 MB de margen sobre 512 MB.

Sobre la cifra de 345 MB del encargo: era el pico **sin** `MALLOC_ARENA_MAX`, con un único escaneo previo. Con
`MALLOC_ARENA_MAX=2` la medición anterior dio un pico de 337 MB y 162 MB en reposo. Esta prueba lo confirma con
escaneos simultáneos.

La memoria la dominan las peticiones concurrentes, no el escaneo:
- un escaneo real en un proceso propio llega solo a 151 MB;
- el servidor en reposo, sin usuarios, ocupa unos 100 MB.

**Conclusión sobre memoria:** 512 MB bastan para el piloto, con `MALLOC_ARENA_MAX=2` siempre definido.

### 6.2 CPU: lo que de verdad limita

La auditoría anterior no pudo medir «Render con su CPU real». Ahora se emuló con cgroups:
- CPU limitada con `cpu.cfs_quota_us`;
- memoria limitada con `memory.limit_in_bytes`;
- planes de Render según https://render.com/docs/compute-plans: Free 0,1 CPU y 512 MB; Starter 0,5 CPU y 512 MB; Standard 1 CPU y 2 GB.

Evidencia: `render_free_0.1cpu.json`, `render_starter_0.5cpu.json` y `render_standard_1cpu.json`.

| Plan emulado | Usuarios | Ráfaga de inicios de sesión | Panel p95 fuera / durante el escaneo | Máx. | Ritmo atendido | Escaneo | Telegram p95 fuera / durante | Errores |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Free (0,1 CPU) | 10 | **6,4 s** | 196 ms / **1,9 s** | 3,1 s | 9,1 de 10/s | 12,5 s | 0,2 / **3,0 s** | 0 |
| Free (0,1 CPU) | 25 | **15,6 s** | 1,3 s / **3,3 s** | 5,2 s | **14,1 de 25/s (saturado)** | 19,6 s | 3,3 / 10,2 s | 0 |
| Starter (0,5 CPU) | 10 | 1,2 s | 15 ms / 571 ms | 719 ms | 9,9/s | 5,2 s | 53 / 509 ms | 0 |
| Starter (0,5 CPU) | 50 | 5,9 s | 22 ms / 654 ms | 982 ms | 49,4/s | 5,6 s | 55 / 549 ms | 0 |
| Starter (0,5 CPU) | 100 | 12,4 s | 356 ms / 1,0 s | 1,3 s | **87 de 100/s (al límite)** | 6,9 s | 381 / 420 ms | 0 |
| Standard (1 CPU) | 50 | 2,9 s | 24 ms / 293 ms | 395 ms | 49,6/s | 4,2 s | 55 / 37 ms | 0 |
| Standard (1 CPU) | 100 | 5,5 s | 36 ms / 417 ms | 496 ms | 98,8/s | 4,1 s | 69 / 150 ms | 0 |

Lectura:
- Con 0,1 CPU, cada inicio de sesión (scrypt) tarda unos 0,5 s de CPU, frente a 38 ms sin límite. 25 usuarios entrando
  a la vez esperan hasta 15 s.
- Con 25 usuarios activos, el servidor ya no da abasto: atiende 14 peticiones por segundo de las 25 que se le piden.
- El escaneo real hace más cálculo que el sintético, así que en el plan gratis también tardará más.

Advertencias sobre la medición:
- La CPU de Render puede ser más lenta o más rápida, núcleo a núcleo, que la de esta máquina: la emulación da el orden de magnitud, no la cifra exacta.
- El cgroup de memoria solo cuenta lo reservado después de mover el proceso, tras la preparación. Por eso su
  «uso máximo» (81–276 MB) es menor que el RSS. La cifra válida es la del RSS y VmHWM del proceso.

**Conclusión sobre el plan:**

| Plan | Para qué |
| --- | --- |
| Free (0,1 CPU) | Demostraciones y hasta unas 10 personas que entren de forma escalonada. Las esperas de 2–3 s durante el escaneo y de hasta 6 s al entrar en grupo son visibles. Además se suspende por inactividad (arranque en frío) |
| **Starter (0,5 CPU, 512 MB)** | **Recomendado para el piloto cerrado, hasta 50 usuarios activos a la vez.** p95 de 22 ms fuera del escaneo y 0 errores |
| Standard (1 CPU, 2 GB) | Más de 50 usuarios activos, o si se quiere aislar el escáner en un proceso aparte (sección 2) |

La memoria no obliga a subir de plan. **La CPU sí, en cuanto haya más de unas 10 personas.** Subir de plan es una
decisión con coste, así que queda en manos del responsable.

## 7. Cambios realizados

| Archivo | Cambio | Demostrado por |
| --- | --- | --- |
| `radar/auth.py` | Límite de inicio de sesión combinado (fallidos por IP con descuento al acertar, tope por IP, modo estricto global, bloqueo por cuenta intacto); `rate_bump` y `rate_peek` | `carga_ip_compartida.json` (30/50 con 429) → `ip_compartida_despues.json` (50/50); `T28` |
| `radar/server.py` | `client_ip()` y `trusted_proxies()`: `X-Forwarded-For` solo desde proxies autorizados; aviso si hay más hilos que fallidos permitidos | `T28` y `T13` (prueba actualizada) |
| `radar/db.py` | Reintento corto al conectar y `connect_timeout=10` | `caos_postgres.json` (15 × 500) → `caos_postgres_reintento.json` (0); `T27` |
| `tests/piloto/estres.py` | Arnés nuevo: usuarios, escaneos, Telegram simulado, sonda de GIL, caos de PostgreSQL, prototipo de proceso aparte y emulación de planes de Render | — |
| `tests/piloto/memoria_escaner.py` | Memoria de un escaneo en su propio proceso | — |
| `tests/piloto/carga.py` | Autoriza 127.0.0.1 como proxy para seguir dando una IP propia a cada usuario | — |

No se cambió: la estrategia, los parámetros de trading, el paper trading, el ledger, los pagos ni la producción.

## 8. Regresión

| Suite | Python 3.12.3 | Python 3.13.18 |
| --- | --- | --- |
| `tests/test_suite.py` con `TEST_DATABASE_URL` (PostgreSQL 16.15) | **275 OK, 0 omitidas** | **275 OK, 0 omitidas** |
| `tests/test_edge.py` | OK | OK |
| `tests/test_paper.py` | OK | OK |

Hay 17 pruebas nuevas: 16 en T28 y 1 en T27.

Durante el desarrollo, una versión de `T28` lanzaba 24 inicios de sesión simultáneos desde una IP y fallaba de forma
intermitente (1–4 respuestas 429). Es un límite real del diseño:
- cada intento cuenta como fallido mientras se comprueba, así que con más de 20 comprobaciones a la vez desde una IP las que sobran reciben 429;
- con el servidor real no ocurre, porque como mucho hay 16 en curso (los hilos);
- la prueba se ajustó a 16, se documentó el límite y el servidor avisa si se configuran más hilos que fallidos permitidos.

## 9. Riesgos pendientes

Actualizado en `docs/MATRIZ_RIESGOS_PENDIENTES.md`.

| ID | Riesgo | Estado |
| --- | --- | --- |
| R-06 | Usuarios tras la misma IP reciben 429 | **Mitigado.** Quedan: el cupo de 20 fallidos se comparte entre quienes usan esa IP; la solicitud de acceso sigue en 3 por IP y hora; y el bloqueo dirigido de una cuenta con 5 fallos (ya existía) |
| R-07 | Memoria en 512 MB | **Reducido:** pico de 339–341 MB con escaneos simultáneos, `MALLOC_ARENA_MAX=2` obligatorio |
| R-14 | `X-Forwarded-For` falsificable fuera de Render | **Cerrado** en el código. Falta comprobar en Render que la IP registrada sea la del usuario |
| R-19 (nuevo) | CPU del plan gratis: con 25 usuarios activos se satura (15 s para entrar, p95 de 2,1 s) | Abierto: **usar Starter** para el piloto (decisión del responsable) |
| R-20 (nuevo) | El escaneo sube el p95 del panel a 0,3–0,5 s (en Starter, 0,65–1 s) durante sus segundos | Aceptado para el piloto; criterio para el proceso aparte en `ANALISIS_ESCANER_HTTP.md` |
| R-21 (nuevo) | Neon real no medido: TLS, arranque en frío y *pooler* | Abierto: prueba corta de 10 usuarios en Render y Neon antes de invitar a más |

Los demás riesgos de la matriz no cambian. Siguen bloqueando el piloto R-01, R-02, R-10, R-11 y R-17.

## 10. Lo que no se ejecutó

- Nada en Render ni en Neon reales. La CPU se emuló, no se midió en Render.
- Telegram real: el simulador responde en 30 ms. No se probó contra la API real ni sus límites.
- La memoria del proceso hijo junto al servidor en el prototipo: se sumó, no se midió a la vez.
- Escaneo real con 100 usuarios: solo se hizo con 50, por el tiempo y los límites de las API públicas.
- Orden de las corridas: `simultaneo_caliente.json` se ejecutó con el código del PR #5, antes de los cambios. Las
  corridas siguientes ya tenían el nuevo límite de inicio de sesión, y desde `caos_postgres_reintento.json`
  también el reintento al conectar. Ninguno de los dos cambios toca el escaneo ni el panel, así que las cifras de
  latencia son comparables. La comparación antes/después de cada cambio está en sus propias evidencias.
