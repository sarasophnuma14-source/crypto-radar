# AUDIT_REPORT — Crypto Radar (versión original, commit 34f6898 de `main`)

Fecha: 2026-11-14 · Alcance: `radar/*.py`, `main.py`, `render.yaml`, `web/`, `research/`.
Respaldo: `main` queda intacta (34f6898) y la etiqueta local `backup-pre-2.0` apunta a ese commit. Todo el trabajo 2.0 va en la rama `claude/project-thread-i8udp5`.

Escala de severidad: **CRÍTICA** (resultados falsos, pérdida de datos o un agujero de seguridad explotable) · **ALTA** (sesgo que infla resultados o un fallo funcional importante) · **MEDIA** (calidad o robustez) · **BAJA** (detalle).

## Resumen

| Severidad | Hallazgos |
| --- | --- |
| CRÍTICA | 7 |
| ALTA | 13 |
| MEDIA | 14 |
| BAJA | 6 |

Conclusión: los motores de señal son razonables como heurística, pero **el backtest simple tiene sesgo de anticipación (entra al mismo cierre que genera la señal)**, el de cartera tiene **sesgo de supervivencia y exposición mal contabilizada**, y **la persistencia en Render se borra en cada reinicio**. Las cifras históricas publicadas antes de esta auditoría no deben usarse para vender el producto sin recalcularse con el motor corregido.

## Hallazgos

### Backtest y estadística

| # | Problema | Sev. | Archivo:línea | Evidencia | Solución |
| --- | --- | --- | --- | --- | --- |
| A1 | Entrada al mismo cierre que genera la señal (look-ahead) | CRÍTICA | radar/backtest.py:24-26 | `analyze()` usa la vela `i` completa y la entrada es `d1["c"][i]`: el sistema "compra" al precio que usó para decidir | Señal al cierre de `i`, orden ejecutable desde la apertura de `i+1` (motor nuevo `radar/quant/backtest_pro.py`) |
| A2 | Sesgo de supervivencia en el backtest de cartera | ALTA | radar/portfolio_backtest.py:97-98 | `DEFAULT_UNIVERSE` = 26 monedas que existen y son grandes HOY | Universo por fecha desde el panel histórico (incluye pausadas/retiradas, `research/fetch_panel.py`) y filtro de liquidez con datos de ESE día |
| A3 | Exposición a altcoins no se actualiza al colocar órdenes en el mismo día | ALTA | radar/portfolio_backtest.py:308-331 | `alt_exposure` se calcula una vez antes del bucle; las órdenes pendientes nuevas no la suman → se pueden abrir varias posiciones que juntas superan el límite del régimen | Exposición comprometida = posiciones + órdenes pendientes, recalculada tras cada orden |
| A4 | El día de la compra no se evalúa el stop | ALTA | radar/portfolio_backtest.py:250-270 | Si la vela que llena la orden límite también perfora el stop, la posición sobrevive hasta el día siguiente (optimista) | Tras el llenado, comprobar el stop en la misma vela (peor caso) |
| A5 | Ambigüedad intradía TP/stop tras TP1 | MEDIA | radar/portfolio_backtest.py:222-231 | Al tocar TP1 el stop sube a la entrada, pero no se comprueba si esa misma vela volvió a la entrada | Política conservadora explícita: si la vela toca TP y el nuevo stop, se asume que el stop ocurre después del TP (registrado como ambigua) |
| A6 | Valoración de posiciones sin vela ese día al precio de entrada | MEDIA | radar/portfolio_backtest.py:280 | `px = ... else p["entry"]` falsea la curva si un activo deja de cotizar | Usar el último cierre conocido; si se retira, liquidar al último precio con marca |
| A7 | Métricas incompletas: sin Sharpe, Sortino, expectancy, recuperación, exposición media, desglose por régimen/capitalización | MEDIA | radar/portfolio_backtest.py:354-370 | No existen en `summary` | Módulo de métricas calculado SOLO desde el libro de operaciones y la curva diaria |
| A8 | Régimen fijo "LATERAL" en el backtest simple | MEDIA | radar/backtest.py:23 | `analyze(..., "LATERAL")` | Régimen diario real |
| A9 | Sin separación entrenamiento/validación ni walk-forward en el motor de la app | ALTA | radar/portfolio_backtest.py (todo) | Solo `test_from`; los umbrales se fijaron mirando todo el periodo | Walk-forward con ventanas rodantes y prueba fuera de muestra única |
| A10 | Pesos de puntuación sin validación estadística | ALTA | radar/config.py:15-23 · radar/analysis.py:126-168 | Pesos y puntos fijados a mano; nunca se midió su poder predictivo | Pesos configurables + informe de validación (retorno a 10/20 días por quintil de score, fuera de muestra) |
| A11 | Estadística de memecoins publicada como constante | ALTA | radar/memes.py:30-31 | `BACKTEST = {...}` escrito a mano; el periodo "ciego" ya se había mirado antes del ajuste final (anotado en la memoria del proyecto) | Calcular desde el registro de operaciones del motor nuevo y etiquetar el periodo como "visto" |
| A12 | `profit_factor = 99.0` cuando no hay pérdidas | MEDIA | radar/memes.py:171 | Cifra inventada | Devolver `None` ("sin pérdidas aún") |
| A13 | Rendimiento de la cartera de memecoins sumado, no compuesto | BAJA | radar/memes.py:174 | `sum(pnl) * 10%` | Curva compuesta desde las operaciones |

### Temporalidad y calidad de datos

| # | Problema | Sev. | Archivo:línea | Evidencia | Solución |
| --- | --- | --- | --- | --- | --- |
| T1 | El análisis en vivo usa la vela diaria aún abierta | ALTA | radar/data.py:278-288 · radar/analysis.py:22-24 | Binance/Bybit devuelven la vela del día en curso; `price=c[-1]`, `vol_ratio` y rupturas se calculan con un día a medias | Separar `closed` (decisión) de `live` (precio actual); las señales se calculan solo con velas cerradas |
| T2 | `vol_usd_24h` = volumen de la vela parcial | MEDIA | radar/analysis.py:47 | Volumen de unas horas tratado como 24 h | Volumen 24 h del ticker o de la última vela cerrada |
| T3 | Semanal construida desde el primer día disponible, no desde el lunes | BAJA | radar/scanner.py:20-27 | Bloques de 7 velas desde el índice 0 | Agrupar por semana ISO |
| T4 | Sin controles de calidad de datos | ALTA | radar/data.py (todo) | No se detectan huecos, velas duplicadas, precios ≤ 0, OHLC incoherente ni velas viejas | `radar/quant/quality.py`: puntuación de calidad 0-100 por activo y bloqueo si es insuficiente |
| T5 | OKX: la vela no confirmada no se marca | BAJA | radar/data.py:170-171 | Comentario dice que se descarta, el código no lo hace | Usar el campo `confirm` |
| T6 | Mezcla de fuentes sin registrar cuál se usó por activo | MEDIA | radar/data.py:142, 181-190 | `source_used` es global, se sobrescribe en cada llamada | Guardar la fuente por activo en el resultado |

### Señales

| # | Problema | Sev. | Archivo:línea | Evidencia | Solución |
| --- | --- | --- | --- | --- | --- |
| S1 | Indicadores duplicados en la puntuación | ALTA | radar/analysis.py:130-168, 222-262 | La ruptura con volumen suma en motor early (+10), momentum (+20), estructura (+0.1) y volumen (vol_ratio dos veces) | Un solo motor por familia de fenómeno (estructura, volumen, tendencia, momentum, fuerza relativa, liquidez, confirmación), cada indicador en UNA familia |
| S2 | "Acumulación" sin exigir volumen | ALTA | radar/analysis.py:112-115 | Basta rango bajo + squeeze o rango < 45 % + OBV ≥ −0.02: una lateralización muerta califica | Acumulación exige evidencia de demanda: OBV/volumen relativo en alza dentro del rango y mínimos crecientes |
| S3 | La fase depende del orden de los `if` y prioriza "SOBREEXTENDIDO" por un solo umbral | MEDIA | radar/analysis.py:102-123 | Un RSI de 76 basta | Clasificación por puntuación de cada fase con desempate documentado |
| S4 | Señal de salida por una sola condición débil | MEDIA | radar/portfolio_backtest.py:319-322 | Un cierre bajo EMA50 tras TP1 cierra todo | Motor de salida con 4 decisiones y confirmación de al menos 2 familias |
| S5 | Sin detector de manipulación ni de falsas rupturas con evidencia | ALTA | — | Solo existe `failed_breakout` (1 regla) | `radar/quant/manipulation.py` con evidencias verificables |
| S6 | Régimen sin estados "alta volatilidad" ni "capitulación" | MEDIA | radar/regime.py:4-37 | 5 estados en castellano; la volatilidad no se mide | Régimen nuevo BULLISH/NEUTRAL/BEARISH/HIGH VOLATILITY/CAPITULATION que ajusta exposición, umbral y tamaño |
| S7 | Divergencias con pivotes de 2 velas: muy ruidosas | BAJA | radar/indicators.py:141-157 | `pivots(..., 2, 2)` | Pivotes 3/3 y umbral de RSI relativo |

### Riesgo y cartera

| # | Problema | Sev. | Archivo:línea | Evidencia | Solución |
| --- | --- | --- | --- | --- | --- |
| R1 | Tamaño sin límite por categoría, correlación ni riesgo agregado | ALTA | radar/analysis.py:207-210 | Solo riesgo por operación y % máximo por activo | `radar/quant/portfolio.py`: límites por activo, categoría, nº de posiciones, correlación y riesgo abierto total; freno por drawdown |
| R2 | Posiciones manuales sin tamaño ni riesgo calculado | MEDIA | radar/server.py (POST /api/positions) | `qty` opcional, sin verificar el riesgo | Calcular tamaño sugerido desde el stop y avisar si excede límites |
| R3 | Diario de señales evalúa con 1000 velas de 1 h (≈ 41 días) pero cierra a los 45 | BAJA | radar/scanner.py:383, 406 | Los últimos días nunca se leen | Paginar o usar velas de 4 h tras 30 días |

### Persistencia y concurrencia

| # | Problema | Sev. | Archivo:línea | Evidencia | Solución |
| --- | --- | --- | --- | --- | --- |
| P1 | En Render gratis todos los datos se pierden en cada reinicio o despliegue | CRÍTICA | render.yaml:3-4 · radar/storage.py | Archivos JSON en disco efímero (lo dice el propio comentario) | Base de datos PostgreSQL (`DATABASE_URL`) con respaldo SQLite en local |
| P2 | Condición de carrera en `append_list`: se pierden escrituras | ALTA | radar/storage.py:33-37 | Lee bajo el candado y escribe fuera; escáner, vigilancia de precio y memecoins escriben `alerts.json` en hilos distintos | Operaciones atómicas en la base de datos (una fila por alerta) |
| P3 | Alertas duplicadas entre hilos | ALTA | radar/alerts.py:98-109 | Comprobación de duplicado y escritura no son atómicas; la clave es solo tipo+símbolo | Clave única (tipo, símbolo, ventana, huella del contenido) con restricción `UNIQUE` |
| P4 | Escrituras de posiciones sin candado (lectura-modificación-escritura) | MEDIA | radar/server.py (POST /api/positions/*) · radar/scanner.py:324-358 | Un cierre manual puede pisarse con la actualización de la vigilancia de precio | Transacciones por fila |

### Seguridad

| # | Problema | Sev. | Archivo:línea | Evidencia | Solución |
| --- | --- | --- | --- | --- | --- |
| X1 | Una sola contraseña compartida para todo el panel | CRÍTICA | radar/server.py:114-130 | Basic Auth con `CRYPTO_RADAR_PASSWORD`; no hay usuarios | Cuentas individuales, hash scrypt, sesiones con cookie `HttpOnly; Secure; SameSite=Lax` |
| X2 | Sin protección CSRF | CRÍTICA | radar/server.py:99-107, do_POST | El navegador reenvía Basic Auth; `_body()` acepta JSON en cualquier `Content-Type`, así que un formulario externo `text/plain` puede cambiar ajustes (incluido el token de Telegram) | Token CSRF por sesión + exigir `application/json` + comprobar `Origin` |
| X3 | Sin límite de intentos de contraseña | CRÍTICA | radar/server.py:114-130 | Fuerza bruta ilimitada | Rate limiting por IP y por cuenta |
| X4 | Sin límite de tamaño del cuerpo | ALTA | radar/server.py:100-101 | `Content-Length` arbitrario se lee entero en memoria | Máximo 64 KB, 413 si se supera |
| X5 | Cualquiera con acceso puede redirigir las alertas a otro bot | ALTA | radar/server.py (POST /api/settings) | El token de Telegram es editable sin re-autenticación | Ajustes de sistema solo para administrador; Telegram por usuario con enlace firmado |
| X6 | Validación de entradas débil (acepta `nan`, `inf`, negativos) | MEDIA | radar/server.py:72-76 | `float("nan")` pasa | Validadores con rangos |
| X7 | El repositorio es público con la estrategia completa | CRÍTICA | GitHub | Reglas de memecoins y pesos visibles | Pasar a privado (decisión del dueño) |
| X8 | Inyección en la notificación de Windows | BAJA | radar/alerts.py:75-79 | Título/mensaje interpolados en PowerShell | Escapar comillas o desactivar en servidor |
| X9 | Sin cabeceras de seguridad (CSP, nosniff, frame-ancestors) | MEDIA | radar/server.py:85-92 | `_send` solo pone tipo y longitud | Cabeceras por defecto |
| X10 | Sin registro de actividad ni de errores estructurado | MEDIA | — | `print` y `traceback.print_exc()` | Registro JSON + tabla de auditoría |

### Rendimiento y operación

| # | Problema | Sev. | Archivo:línea | Evidencia | Solución |
| --- | --- | --- | --- | --- | --- |
| O1 | Escaneo secuencial: ~2 peticiones por activo + `sleep` | MEDIA | radar/scanner.py:142-154 | 150 activos ≈ 300 peticiones en serie | Descarga concurrente acotada (4-6 hilos por host) con caché de velas cerradas |
| O2 | `technicals()` se calcula dos veces por activo (amplitud y análisis) | BAJA | radar/scanner.py:156-157, 175 | Se repite el cálculo completo | Reutilizar el resultado |
| O3 | VWAP rodante O(n·p) y pivotes O(n·k) recalculados en cada día del backtest | MEDIA | radar/indicators.py:101-110 · radar/portfolio_backtest.py:298 | Backtest de cartera de años tarda horas | Indicadores incrementales/precalculados por serie en el backtest |
| O4 | El planificador duerme 20 min dentro del hilo tras un fallo | BAJA | radar/server.py:64-66 | Bloquea también la vigilancia de precio | Reintento con marca de tiempo, sin dormir el hilo |
| O5 | Backtest en vivo eliminado del panel en PR #1, pero el usuario lo pide | MEDIA | — | Binance bloquea las IP de Render y el cálculo excede el tiempo de la petición | Backtests precalculados en lote con resultados guardados y servidos desde la base de datos |

## Lo que se mantiene

- Respaldo de fuentes (Binance → Bybit → OKX), manejo de 418/429 con `Retry-After` y caché de universo y pares (hilo de la app, commits 388cc39 y 34f6898).
- Política de "nunca inventar datos" (N/D cuando no hay fuente).
- Laboratorio `research/` con diseño/prueba ciega: se reutiliza su panel histórico para el backtest sin sesgo de supervivencia.
