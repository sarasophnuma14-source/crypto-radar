# ¿El escáner bloquea a los trabajadores HTTP? · Crypto Radar 2.1.0

Fecha: 2026-11-15. Todo se midió en local (4 CPU, Python 3.12.3, PostgreSQL 16.15). Ninguna petición fue a producción.

## 1. Respuesta corta

- **Sí hay interferencia, pero no bloqueo.** Mientras corre un escaneo, el p95 del panel sube de 17–50 ms a
  150–470 ms. No hubo ni un error ni una petición de más de 0,7 s en ninguna corrida.
- **Un proceso aparte para el escáner la elimina:** con el prototipo, el p95 durante el escaneo queda en 19–46 ms.
- **No se implementó en la app** porque, con 512 MB, el proceso del escáner más el servidor quedarían cerca del
  límite (sección 5). Hoy la interferencia no justifica ese riesgo. La sección 6 fija cuándo hacerlo.

## 2. Por qué ocurre

El servidor y el escáner comparten un único proceso de Python.

- Python ejecuta código de un solo hilo a la vez (el GIL). El escáner calcula indicadores con pandas y Python puro,
  y mientras lo hace compite por el GIL con los 16 hilos HTTP.
- Cada petición del panel suelta y vuelve a pedir el GIL varias veces (una por consulta a PostgreSQL, y al leer y
  convertir el informe JSON). Con el escáner ocupando CPU, cada vez espera un turno de hasta 5 ms
  (`sys.getswitchinterval()`). Esas esperas se suman.
- Lo confirma la sonda de la prueba: un hilo que duerme 5 ms en bucle dentro del servidor tarda en despertar, en el
  p99, 12–29 ms durante el escaneo frente a 2–9 ms fuera.
- No es un bloqueo de PostgreSQL: 0 esperas por bloqueo en todas las muestras de todas las corridas.

## 3. Cómo se midió

Script: `tests/piloto/estres.py`. Ver el comando y las variables en su cabecera.

- Servidor real (`server.serve`) en otro proceso, con 16 hilos y base PostgreSQL temporal.
- Usuarios simultáneos que repiten peticiones del panel con 1 s de pausa.
- El administrador lanza el escaneo con `POST /api/scan`, el mismo camino que el botón del panel.
- Las peticiones se separan según empezaran **durante** o **fuera** de un escaneo. Las ventanas de escaneo las
  registra el propio servidor.
- Telegram simulado: 2 comandos por segundo y una difusión cada 30 s a todos los chats vinculados. Nada sale a internet.

## 4. Resultados

### 4.1 Escáner en hilo (la app actual), datos sintéticos

Evidencia: `docs/evidencia_piloto/estres/simultaneo_caliente.json` (6 escaneos por tramo, 90 s) y
`simultaneo_frio.json` (1 escaneo por tramo, 60 s).

| Usuarios | p95 durante | p95 fuera | p99 durante | p99 fuera | Máx. | Sonda p99 durante / fuera | Escaneo | Errores |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | 149 ms | 17 ms | 186 ms | 30 ms | 223 ms | 11,7 / 2,5 ms | 3,8–3,9 s (3,75 s en reposo) | 0 |
| 50 | 257 ms | 26 ms | 354 ms | 92 ms | 456 ms | 20,1 / 5,7 ms | 4,1–4,2 s | 0 |
| 100 | 306 ms | 50 ms | 415 ms | 126 ms | 467 ms | 23,5 / 7,6 ms | 4,2–4,5 s | 0 |
| 100 (frío) | 466 ms | 52 ms | 512 ms | 187 ms | 549 ms | 28,9 / 8,1 ms | 4,95 s | 0 |

- El escaneo apenas se alarga con los usuarios: de 3,75 s en reposo a 4,5 s con 100 usuarios.
- Quien más sufre es el panel, y solo durante esos segundos.
- «Frío» regenera las series sintéticas en cada escaneo. Esperaba que fuera mucho más lento, pero apenas cambió
  (+0,6 s): el escaneo inicial de 25 s se debe a las pausas de cortesía con CoinGecko (`category_map`, 3 s por
  categoría, una vez al día), no al cálculo.

### 4.2 Escáner en hilo, datos reales (74 activos)

Evidencia: `escaneo_real_50.json`. 50 usuarios, `MALLOC_ARENA_MAX=2`.

| | Durante el escaneo (43 s) | Fuera |
| --- | --- | --- |
| p50 | 10,9 ms | 8,8 ms |
| p95 | 52 ms | 30 ms |
| p99 | 182 ms | 52 ms |
| Máx. | 295 ms | 342 ms |
| Sonda, retraso máximo | 150 ms | 58 ms |

Con datos reales el escaneo pasa la mayor parte del tiempo esperando a la red, que suelta el GIL. La interferencia es
menor que con datos sintéticos, aunque dura más.

### 4.3 Prototipo: escáner en un proceso aparte

Evidencia: `simultaneo_frio_proceso.json`. Activado con `CRYPTO_RADAR_SCANNER=proceso`, **solo en el script de
prueba**.

El servidor lanza `python -c …` con `scanner.run_scan()`. El proceso hijo escribe en la misma base (tabla `kv`),
igual que el hilo. El servidor solo refleja `scanning` en `/healthz` y `/api/state`. No cambia la estrategia ni el
formato de los datos.

| Usuarios | p95 durante (hilo → proceso) | p99 durante (hilo → proceso) | Sonda p99 durante (hilo → proceso) | Errores |
| --- | --- | --- | --- | --- |
| 10 | 195 → **19 ms** | 226 → **27 ms** | 12,4 → 2,4 ms | 0 |
| 50 | 365 → **26 ms** | 417 → **41 ms** | 20,6 → 6,5 ms | 0 |
| 100 | 466 → **46 ms** | 512 → **69 ms** | 28,9 → 8,8 ms | 0 |

**Advertencia sobre la duración:** en el prototipo los escaneos duraron 37–75 s, en lugar de 4–5 s.

- La causa es la prueba, no la arquitectura. Cada proceso nuevo genera series sintéticas distintas, porque el hash
  de Python cambia entre procesos.
- Con datos distintos saltan alertas nuevas, y la difusión por Telegram espera 0,05 s por usuario (160 usuarios).
- Esa duración no sirve para comparar. La latencia sí, porque el hijo no comparte el GIL con el servidor.

## 5. Memoria de cada opción

Evidencia: `memoria_escaner_proceso_arena2.json` y `memoria_escaner_proceso.json` (`tests/piloto/memoria_escaner.py`).
Mide un escaneo en un proceso propio, sin servidor.

| Escaneo en proceso propio | Tras importar | Pico (VmHWM) |
| --- | --- | --- |
| Sintético, 40 activos | 36 MB | 63 MB |
| Real, 74 activos (`MALLOC_ARENA_MAX=2`) | 36 MB | **151 MB** |

El servidor, con 100 usuarios y escaneos, llega a 339 MB con `MALLOC_ARENA_MAX=2` (ver
`docs/AUDITORIA_ESTRES_INTEGRAL.md`). En un plan de 512 MB:

- **escáner en hilo**: un pico de unos 340 MB, con un margen de 170 MB;
- **escáner en proceso aparte**: hasta 340 + 151 ≈ 490 MB si coinciden el pico del servidor y el del escaneo real.
  Margen de unos 20 MB: un universo mayor o más usuarios provocarían que Render matara el proceso.

El servidor podría bajar algo, porque ya no haría el escaneo. Pero su memoria la dominan las peticiones
concurrentes, no el escaneo (sección 4 de `AUDITORIA_ESTRES_INTEGRAL.md`), así que no se puede contar con ese ahorro
sin medirlo.

El prototipo no midió la memoria del proceso hijo junto al servidor: este kernel no expone
`/proc/<pid>/task/<pid>/children`. Por eso la cifra de 490 MB es una suma, no una medición.

## 6. Decisión y criterio

**No se implementa el proceso aparte para el piloto cerrado.**

- Con el escáner en hilo no hubo errores, y el peor p99 fue de 0,5 s, solo durante unos segundos cada 4 horas.
- Con datos reales, el p99 durante el escaneo fue de 182 ms.
- El proceso aparte resolvería un problema pequeño a cambio de un riesgo real de quedarse sin memoria en 512 MB.

Hacerlo, con el prototipo de `tests/piloto/estres.py` como base, cuando se cumpla **cualquiera** de estas condiciones:

1. Se pasa a un plan de 2 GB o más (Standard de Render), donde la memoria deja de ser un problema.
2. En producción, el p99 del panel durante el escaneo supera 1 s (medirlo en Render, ver la sección 5 de la auditoría).
3. El universo crece claramente por encima de 74 activos, o el escaneo pasa a ser más frecuente.

Antes de implementarlo hay que resolver lo que el prototipo no cubre:
- cancelar el hijo si el servidor se reinicia;
- pasar `progress` y `last_error` del hijo al servidor;
- ejecutar el planificador y `price_watch` igual que el escaneo manual;
- volver a medir memoria y latencia juntas en el plan de destino.

Una mejora más barata, que reduciría tanto la interferencia como la memoria: hoy cada `/api/state` lee el informe
completo de la base y lo convierte de JSON en cada petición. Guardarlo ya convertido en el proceso hasta que cambie
reduciría la CPU por petición. Tampoco se implementó, porque no estaba pedido y cambia el camino de datos del panel.
Queda como recomendación medible con el mismo script.
