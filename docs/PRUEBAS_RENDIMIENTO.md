# Pruebas de rendimiento · Crypto Radar 2.1.0 (auditoría final del piloto)

Fecha: 2026-11-15. **Todo el tráfico fue local**: ninguna petición se envió a producción.

## Cómo se midió

Script reproducible: `tests/piloto/carga.py`.

```bash
PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/carga.py docs/evidencia_piloto/carga_despues.json
# variantes:  NIVELES=50,50,50,50 DURACION_S=60   ·   IP_COMPARTIDA=1   ·   MALLOC_ARENA_MAX=2
```

**Entorno**
- Contenedor con 4 CPU y 16 GB de RAM, Python 3.12.3 y PostgreSQL 16.15, ambos en la misma máquina.
- La base es temporal, se crea para la prueba y se borra al final.

**Servidor**
- El servidor es el real, `server.serve` sin planificador, arrancado en un proceso aparte.
- Todos los usuarios están en modo cuentas y aprobados, repartidos entre Libre, Pro y Élite.

**Datos**
- El informe de mercado sale de un escaneo con datos sintéticos (`tests/fake_market.py`), con 40 activos.
- Un escaneo real hecho en esta auditoría tuvo 74 activos con análisis completo, así que el informe real pesa más.

**Carga**
- Se probaron tres niveles: 10, 50 y 100 usuarios simultáneos.
- En cada nivel, primero todos los usuarios inician sesión a la vez (una ráfaga de scrypt).
- Después, durante 30 s, cada usuario repite estas peticiones con 1 s de pausa entre ellas: `/api/state` 40 %, `/api/me` 20 %, `/api/alerts` 15 %, `/api/positions` 15 % y `POST /api/me/settings` 10 %.
- Cada usuario llega con su propia IP en `X-Forwarded-For`, igual que detrás del proxy de Render.

**Mediciones**
- Latencia: p50, p95, p99 y máximo.
- Códigos HTTP de cada respuesta.
- Memoria (VmRSS) y CPU del proceso servidor.
- Conexiones a PostgreSQL abiertas, contadas con `pg_stat_database.sessions`.
- Esperas por bloqueos (`pg_locks` sin conceder), muestreadas cada 0,25 s.
- Consultas de más de 50 ms (`log_min_duration_statement`).

El 402 no cuenta como error: es la respuesta correcta cuando un usuario del plan Libre pide su cartera.

## Resultado antes de corregir (código de `8476715`)

Evidencia: `docs/evidencia_piloto/carga_antes.json`.

| Usuarios | Inicios de sesión OK | Peticiones del panel | p50 | p95 | p99 | Máx. | Errores | RSS máx. | CPU | Conexiones PostgreSQL abiertas |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | 10/10 | 298 | 14,8 ms | 38,1 ms | 53,5 ms | 1039 ms | 0 | 241 MB | 7,6 % | 308 en 308 peticiones |
| 50 | **32/50** (18 `ConnectionResetError`) | 938 | 14,8 ms | 59,0 ms | **1092 ms** | 1246 ms | 0 | 369 MB | 21,3 % | 970 en 988 |
| 100 | **77/100** (23 `ConnectionResetError`) | 2234 | 15,1 ms | 78,4 ms | **1355 ms** | 1896 ms | **4 resets** | **514 MB** | 47,1 % | 2307 en 2334 |

Hallazgos:
- **F-04:** la cola de escucha era de 5 conexiones. En ráfagas, el sistema operativo rechazaba conexiones: con 100 usuarios, 23 % de los inicios de sesión fallaron.
- **F-05:** se creaba un hilo por petición y cada hilo abría su propia conexión a PostgreSQL, es decir, una conexión por petición. En Neon cada una lleva negociación TLS.
- La memoria crecía con la concurrencia hasta 514 MB, que es más que los 512 MB del plan gratis de Render.

## Corrección

`radar/server.py`, `PooledHTTPServer`:
- Usa un número fijo de hilos (`CRYPTO_RADAR_WORKERS`, 16 por defecto) y una cola de escucha de 128.
- Cada hilo reutiliza su conexión a PostgreSQL.
- `radar/db.py` reconecta si PostgreSQL o Neon cortan la conexión (F-06, ver `docs/RECUPERACION_DESASTRES.md`).
- Pruebas: `T27_ServidorHilosFijos`.

## Resultado después (código de esta auditoría)

Evidencia: `docs/evidencia_piloto/carga_despues.json`.

| Usuarios | Inicios de sesión OK | Login p95 | Peticiones del panel | Ritmo | p50 | p95 | p99 | Máx. | Errores | RSS máx. | CPU | Conexiones PostgreSQL |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | 10/10 | 217 ms | 300 | 10,0/s | 8,7 ms | 24,7 ms | 42,7 ms | 49 ms | **0** | 248 MB | 6,5 % | 15 abiertas en total, máx. 17 a la vez |
| 50 | 50/50 | 606 ms | 1500 | 50,0/s | 9,2 ms | 60,3 ms | 139,7 ms | 198 ms | **0** | 344 MB | 29,2 % | 0 nuevas |
| 100 | 100/100 | 1159 ms | 2981 | 99,4/s | 10,7 ms | 65,6 ms | 380,5 ms | 503 ms | **0** | 345 MB | 58,6 % | 0 nuevas |

En las tres corridas, a todos los niveles:
- **Bloqueos de PostgreSQL:** ninguna espera en 364 muestras.
- **Consultas lentas (más de 50 ms):** ninguna.

### Resistencia: 4 × 60 s con 50 usuarios

Evidencia: `carga_resistencia.json`.

| Tramo | p95 | p99 | Errores | RSS |
| --- | --- | --- | --- | --- |
| 1 | 34,9 ms | 91,8 ms | 0 | 417,7 MB |
| 2 | 36,5 ms | 115,1 ms | 0 | 422,3 MB |
| 3 | 32,5 ms | 109,6 ms | 0 | 422,5 MB |
| 4 | 37,4 ms | 77,6 ms | 0 | 422,6 MB |

La memoria se estabiliza en unos 422 MB: no hay fuga que crezca con el tiempo. Pero el nivel es alto para los 512 MB del plan gratis (riesgo R-07).

### Memoria con `MALLOC_ARENA_MAX=2`

Evidencia: `carga_malloc_arena2.json`.
- Mismo pico (337 MB) y misma latencia (p99 de 344 ms con 100 usuarios).
- En reposo, la memoria vuelve a 162 MB en lugar de quedarse en 345 MB.
- Se añadió a `render.yaml`.

### Usuarios detrás de la misma IP

Evidencia: `carga_ip_compartida.json`.

Se lanzaron 50 inicios de sesión simultáneos desde una sola IP, como en una oficina o con el CGNAT de un operador móvil:
- **30 recibieron 429**, porque el límite es de 20 inicios de sesión por IP cada 15 minutos.
- Es el comportamiento diseñado contra fuerza bruta, pero afecta a usuarios legítimos que comparten IP (riesgo R-06).

## Conclusiones

- Con las correcciones, 100 usuarios simultáneos activos se atienden sin errores, a unas 99 peticiones por segundo, con p95 de 66 ms y p99 de 381 ms en el panel.
- El cuello de botella es el inicio de sesión: scrypt consume CPU a propósito. Una ráfaga de 100 inicios de sesión tarda 1,5 s en completarse (p95 de 1,2 s).
- **Lo que no se midió:**
  - Render con su CPU real (el plan gratis tiene una fracción de CPU, así que la latencia será mayor).
  - La latencia de red hasta Neon.
  - Un escaneo real ejecutándose a la vez que la carga (el escaneo real tardó 165 s y usa pandas en el mismo proceso).
  - Antes de invitar a muchos usuarios hay que repetir una prueba corta en el entorno real, sin pasar de 10 usuarios.
