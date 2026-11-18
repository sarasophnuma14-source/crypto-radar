# Auditoría de la arquitectura actual · Crypto Radar 2.1 → Market Radar

Fecha: 18 de noviembre de 2026.
Rama inspeccionada: `release-2.1` en `2f6df27` (la que sirve `crypto-radar-2-1` en Render).
Alcance: código, esquema de datos, fuentes de datos, pruebas, ramas y PR abiertos, documentación de auditorías previas.
Esta auditoría **no** tocó Render, Neon, variables, secretos, el holdout ni el paper trading en curso. Solo lectura del repositorio y de GitHub.

> Regla de lectura. Cada hallazgo cita el archivo y la línea, o el documento previo que lo respalda. Lo que no se comprobó en esta sesión está marcado **NO VERIFICADO**. El estado en vivo (servicios de Render, base Neon) se toma de la auditoría de fase cero del 16-nov-2026 (`evolucion-saas/AUDITORIA_INTEGRAL_CRYPTO_RADAR.md`) y de la memoria del proyecto; **no se volvió a comprobar hoy** para no interferir con el hilo que mantiene la 2.1.

---

## 1. Resumen ejecutivo

1. Crypto Radar 2.1 es **un único proceso Python** (librería estándar + `psycopg`) que sirve web, programa escaneos, vigila precios, atiende Telegram y ejecuta paper trading. Es simple y funciona para un mercado; no está preparado para varios.
2. El sistema está **acoplado al modelo cripto** en tres puntos estructurales: la identidad del activo es el *ticker* de CoinGecko cruzado por texto con pares `XXXUSDT` de Binance; el calendario es 24/7 con cierre diario 00:00 UTC implícito; y las velas se guardan como documentos JSON enteros en una tabla clave-valor.
3. El **motor cuantitativo** (`radar/quant`) está bien separado (causal, con control de calidad de datos) y es reutilizable como base del *Trend/Momentum/Volume/Volatility Engine*, pero **no tiene ventaja demostrada**: Sharpe fuera de muestra −0,30 y holdout −0,15 (ronda v3, NO EDGE). Ninguna señal puede presentarse como validada.
4. Hay **tres implementaciones de indicadores** (`radar/indicators.py`, `radar/quant/features.py` sobre la primera, y `radar/edge/features.py` con numpy/pandas). Market Radar necesita una sola biblioteca con pruebas de valores de referencia.
5. La **seguridad de la 2.1** está trabajada (scrypt, sesiones con hash, CSRF, TOTP obligatorio para admin, rate limiting en base, copias con HMAC), pero quedan **bloqueos operativos P0** sin cerrar por el propietario (TOTP sin inscribir, credenciales expuestas sin rotar, health check vacío, repositorio público, 2.0 aún activa).
6. El código en producción **no está en `main`**: vive en una cadena de PR sin fusionar (#3→#8) más 4 PR de evolución (#11–#14). Market Radar no debe añadir otra cadena paralela; debe arrancar después de integrar.

**Conclusión:** Market Radar no debe construirse *dentro* de `radar/`. Debe construirse como un paquete nuevo, modular, que reutilice piezas probadas de la 2.1 mediante adaptadores, mientras la 2.1 sigue estable y sin cambios. Antes de cualquier código multiactivo hay que cerrar la **Fase 0** (§9).

---

## 2. Inventario del repositorio

| Área | Archivos | Líneas aprox. | Comentario |
|---|---|---|---|
| Servidor y API | `radar/server.py` (614), `radar/webapi.py` (270) | 884 | `http.server` con pool propio de 16 hilos; enrutado por `if p == ...` |
| Autenticación y cuentas | `radar/auth.py` (780), `radar/totp.py`, `radar/secretbox.py`, `radar/multiuser.py` | ~1.100 | Planes en `auth.py:45-50` |
| Datos de mercado | `radar/data.py` (352) | 352 | Binance, Bybit, OKX, CoinGecko, alternative.me, todo en un módulo |
| Escáner | `radar/scanner.py` (532) | 532 | Orquestación, universo, descarga, ranking, alertas, posiciones, diario |
| Motor cuantitativo | `radar/quant/*` (11 módulos) | ~2.000 | Calidad, features causales, régimen, early, exits, plan, cartera, backtest |
| Investigación | `radar/edge/*`, `research/*` | ~2.500 | Laboratorio, holdout bloqueado por ledger |
| Paper trading | `radar/paper_trading/*` | ~800 | D_volmom_L28, corre en producción con `PAPER_TRADING=1` |
| Pagos | `radar/billing.py` (263), `radar/payments_selftest.py` | ~430 | Apagados (`CRYPTO_RADAR_PAYMENTS=off`) |
| Persistencia | `radar/db.py` (365), `radar/storage.py` | ~400 | PostgreSQL o SQLite; documentos JSON en `kv` |
| Operación | `radar/backup.py`, `radar/preflight.py` | ~550 | Copias HMAC manuales, comprobación previa |
| Web | `web/*` (index, app.js, landing, legales) | — | Vanilla JS |
| Pruebas | `tests/test_suite.py` (3.426 líneas, 309 pruebas), `test_edge.py`, `test_paper.py`, `tests/piloto/*` | — | Sin CI en GitHub (B-4) |

Dependencias: `psycopg[binary]==3.3.9`, `numpy==2.5.3`, `pandas==3.0.5` (`requirements.txt`). `pip-audit` sin vulnerabilidades conocidas el 16-nov (fase cero §1.4).

---

## 3. Flujo actual de un escaneo

```
scheduler() (server.py:61) ── cada 4 h ──► scanner.run_scan()
   1. cg_global(), fear_greed()                         (CoinGecko, alternative.me)
   2. cg_markets() páginas de 250 → universo             (CoinGecko; caché 24 h si falla)
   3. binance_symbols(quote) → pares negociables         (Binance → Bybit → OKX)
   4. filtro: stables, envueltos, liquidez, capitalización, memecoins
   5. klines(SYM+"USDT","1d",400) en ThreadPool          (velas cerradas)
   6. quality → features → regime → engine.analyze       (radar/quant)
   7. order_book() de los 25 primeros
   8. build_report → storage.write("latest.json")        (documento entero en kv)
   9. fire_alerts → Telegram / escritorio
  10. update_positions, log_journal
   + price_watch cada 15 min (server.py:29), memecoins cada hora (server.py:30)
```

---

## 4. Hallazgos que condicionan el diseño multiactivo

### 4.1 Identidad del activo por texto (crítico para multiactivo)

- **Evidencia:** `scanner.py` construye el universo con `m["symbol"].upper()` de CoinGecko y lo cruza con pares de Binance por concatenación `sym + settings["quote"]` (`scanner.py`, función `fetch` dentro de `run_scan`). No existe un identificador interno estable.
- **Impacto:** varios tokens comparten ticker; en acciones, el mismo ticker cambia de empresa con el tiempo; en futuros cada vencimiento es un instrumento distinto; un índice no es negociable. Con el modelo actual es imposible distinguir *SPX* (índice), *SPY* (ETF) y *ES* (futuro).
- **Requisito derivado:** registro de activos con `asset_id` interno, tabla de identificadores por proveedor con vigencia temporal, y separación activo subyacente / instrumento cotizable (ver `ASSET_DATA_MODEL.md`).

### 4.2 Calendario implícito 24/7

- **Evidencia:** las velas se piden como `1d` cerradas (`data.drop_open_candle`, `data.py:281`); el escaneo cada 4 h y la vigilancia cada 15 min no consultan ningún calendario (`server.py:29-30`, `scheduler`).
- **Impacto:** en acciones, ETF, índices y futuros habría velas "vacías" en fines de semana y festivos, cierres mal fechados, gaps confundidos con señales y datos "viejos" que en realidad son mercado cerrado.
- **Requisito derivado:** servicio de calendarios y sesiones; frescura medida contra la sesión, no contra el reloj.

### 4.3 Persistencia como documentos JSON enteros

- **Evidencia:** `radar/storage.py` guarda cada documento en la tabla `kv` (`db.py`, `CREATE TABLE kv (name, value, updated_at)`). `scanner.py:257` escribe `latest.json` entero; `scanner.py:293` escribe `candles.json` entero; `history.json`, `journal.json`, `positions.json` igual.
- **Impacto:** sin consultas por activo ni por fecha, sin historial auditable por observación, sin versión de procesamiento por fila. La fase cero ya midió que leer `latest.json` cada 30 s impedía que Neon se suspendiera (corregido en PR #12, no desplegado).
- **Requisito derivado:** tablas normalizadas (`candles`, `scan_runs`, `scan_observations`, `opportunity_scores`) con procedencia y timestamps de origen y recepción.

### 4.4 Módulo de datos monolítico, sin contrato de proveedor

- **Evidencia:** `radar/data.py` mezcla HTTP genérico (`get_json`, `data.py:49`), CoinGecko (`data.py:105-118`), Binance (`data.py:20`, `121`), Bybit y OKX (`data.py:138-139`), futuros de Binance (`data.py:305-325`), sentimiento (`data.py:327`) y libro de órdenes (`data.py:336`). La procedencia se anota en un diccionario global `source_used`.
- **Impacto:** añadir un proveedor implica tocar el módulo central. No hay noción de licencia, límite de API declarado ni estado de servicio por proveedor.
- **Requisito derivado:** interfaz común de adaptadores (`DATA_PROVIDER_RESEARCH.md` §6, `TARGET_ARCHITECTURE.md` §5).

### 4.5 Licencias de datos sin resolver ya en la 2.1

- **Evidencia:** fase cero y `UNIT_ECONOMICS.md` §1: CoinGecko sin clave no permite uso comercial; el plan Basic con licencia comercial cuesta US$35/mes (PÚBLICO, consultado 16-nov-2026). Binance no publica una política oficial sobre uso comercial de su API pública (hilo del foro de desarrolladores sin respuesta oficial, consultado 18-nov-2026). Bybit y OKX: **NO VERIFICADO**.
- **Impacto:** la 2.1 ya no podría cobrar con las fuentes actuales sin resolver licencias. Multiactivo multiplica este problema (las bolsas cobran por usuario y por visualización).

### 4.6 Tres bibliotecas de indicadores

- **Evidencia:** `radar/indicators.py` (ema, sma, rsi, macd, atr, bollinger en Python puro); `radar/quant/features.py` importa la anterior y añade divergencias y pivotes; `radar/edge/features.py` recalcula con numpy/pandas.
- **Impacto:** dos cálculos de "RSI" pueden diferir; un resultado de investigación puede no ser reproducible en el producto.
- **Requisito derivado:** una biblioteca causal única con pruebas de valores de referencia (golden tests) y versión.

### 4.7 Puntaje 0–100 sin validación

- **Evidencia:** `docs/BACKTEST_REPORT.md` y memoria `crypto-radar-2-0`: IC del puntaje negativo dentro y fuera de muestra; ronda v3: NO EDGE en 8 familias.
- **Impacto:** el *Market Opportunity Score* no puede heredar pesos ni afirmaciones. Debe nacer como medida descriptiva, versionada y marcada "no validada".

### 4.8 Proceso único con responsabilidades mezcladas

- **Evidencia:** `server.py` arranca el servidor HTTP, `scheduler()`, `paper_scheduler()`, `keepalive()` y el bot de Telegram en el mismo proceso. Durante cada despliegue coexistieron dos instancias que escanearon a la vez (fase cero M-2). La PR #12 añade un candado de líder (sin desplegar).
- **Impacto:** con 8 universos, el escaneo dejará de caber en la ventana de un proceso web de 512 MB. La memoria en reposo medida fue 110–147 MB y 345 MB en la prueba de 100 usuarios.
- **Requisito derivado:** separar *worker* de escaneo y *web* cuando la medición lo justifique (no antes), con el candado de líder de la PR #12.

### 4.9 Escaneo omitido en producción (abierto)

- **Evidencia:** memoria del proyecto, 18-nov-2026: "Scanner skipped ~12h on 11-17/18 (open)". **NO VERIFICADO** en esta sesión.
- **Impacto:** un sistema multiactivo debe detectar y alertar huecos de escaneo; hoy no hay observabilidad que lo haga.

### 4.10 Lo que sí se puede reutilizar

| Pieza | Reutilización en Market Radar |
|---|---|
| `radar/quant/quality.py` | Base del control de calidad por serie (huecos, duplicados, OHLC incoherente, saltos, datos viejos), generalizado con calendario |
| `radar/quant/features.py` (causal) | Base de Trend, Momentum, Volume y Volatility Engines, tras unificar indicadores |
| `radar/quant/regime.py` | Punto de partida del Regime Detection Engine (hoy específico de BTC y amplitud cripto) |
| `radar/auth.py`, `totp.py`, `secretbox.py`, rate limiting en base | Se mantienen; Market Radar los usa sin reescribirlos |
| `radar/backup.py`, `preflight.py` | Se extienden a las tablas nuevas |
| `radar/edge/ledger.py`, `research/prospectivo` (rama sin PR) | Base del registro de experimentos y del candado de holdout |
| PR #12 (`leader.py`, `/livez` + `/healthz`) | Requisito previo del worker independiente |
| PR #14 (instrumentación del piloto) | Patrón de eventos idempotentes para métricas |

---

## 5. Seguridad: estado heredado

| Control | Estado en la 2.1 | Evidencia |
|---|---|---|
| Contraseñas scrypt, sesiones con hash, CSRF, cookies Secure | Implementado | `docs/ARQUITECTURA.md` §Seguridad |
| TOTP obligatorio para administrador | Implementado en código; **no inscrito** en producción | fase cero C-3 |
| Código de alta del administrador | **Vigente** en producción | fase cero C-3 |
| Credenciales que pasaron por el chat (`radar_app`, token Telegram) | **Sin rotar** | fase cero C-4 |
| Rate limiting compartido | Implementado (tabla `rate_limits`) | `db.py` |
| Copias de seguridad | Manuales con HMAC; **no automáticas** | fase cero A-3 |
| Health check en Render | **Vacío** | fase cero A-1 |
| Repositorio | **Público**, con identificadores de infraestructura en docs | fase cero A-4 |
| Política de privacidad | Borrador con marcadores COMPLETAR | fase cero A-5 |
| CI | No existe | fase cero B-4 |

---

## 6. Estado de ramas y PR (GitHub, consultado 18-nov-2026)

| PR | Rama → base | Estado |
|---|---|---|
| #3 → #8 | cadena 2.1 | abiertos, sin fusionar; `release-2.1` es su resultado |
| #9 | investigación edge v3 | borrador |
| #11 | landing honesta → `main` | abierto |
| #12 | fiabilidad 2.1 → `release-2.1` | abierto |
| #13 | docs plan maestro → `release-2.1` | abierto |
| #14 | instrumentación piloto → `release-2.1` | abierto |

`main` = `d1cf246` (2.0 + `ventas/`). `release-2.1` = `2f6df27`. `production-2.0.0` = `9176b36`.
Este trabajo (Market Radar) parte de `release-2.1` y **solo añade documentos** en `docs/market-radar/`.

---

## 7. Deuda técnica priorizada para Market Radar

| Id | Deuda | Bloquea | Prioridad |
|---|---|---|---|
| DT-1 | Identidad del activo por ticker | Cualquier mercado no cripto | Fase 2 |
| DT-2 | Sin calendario de mercado | Acciones, ETF, índices, futuros | Fase 2 |
| DT-3 | Velas y observaciones como JSON en `kv` | Trazabilidad, historial, auditoría | Fase 2 |
| DT-4 | `data.py` sin interfaz de proveedor ni licencias | Todo proveedor nuevo | Fase 2 |
| DT-5 | Tres bibliotecas de indicadores | Reproducibilidad | Fase 2 |
| DT-6 | Proceso único web + escáner + bot + paper | Escala, despliegues | Fase 2 (tras medir) |
| DT-7 | Sin CI | Calidad de todo lo demás | Fase 0 |
| DT-8 | Código de producción fuera de `main` | Cualquier integración | Fase 0 |
| DT-9 | Sin observabilidad de huecos de escaneo | Confianza en los datos | Fase 0/2 |

---

## 8. Riesgos de reutilizar mal la 2.1

- Copiar el ranking de la 2.1 a otros mercados trasladaría un puntaje con IC negativo a activos donde nunca se probó.
- Mezclar el paper trading de D_volmom_L28 (en curso, mínimo 183 días) con nuevas hipótesis invalidaría su registro.
- Reutilizar el holdout cripto de la ronda v3: ya se usó una vez y está bloqueado (`research/edge3/HOLDOUT_V3.lock`). No queda muestra histórica virgen en cripto.

---

## 9. Fase 0 obligatoria (pendientes de la 2.1)

Tomado de la auditoría de fase cero (16-nov) y actualizado con la memoria del 18-nov. **Ninguno lo ejecuta este hilo.**

| # | Pendiente | Responsable | Irreversible |
|---|---|---|---|
| P0-1 | Inscribir TOTP del admin y borrar `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` | PATRON | No |
| P0-2 | Rotar contraseña de `radar_app` y token de Telegram | PATRON | No |
| P0-3 | `/healthz` como health check en Render | PATRON | No |
| P0-4 | Retirar promesas y resultados de la landing (PR #11) | Fusionar con autorización | No |
| P0-5 | Suspender la 2.0 tras copia verificada | PATRON | **Sí** |
| P0-6 | Repositorio privado | PATRON | **Sí** |
| P1-1…P1-4 | Health/readiness, etiqueta "no validada", candado de líder, entregas de Telegram (PR #12, #14) | Revisión + fusión autorizada | No |
| P1-5 | Copias automáticas verificadas | Decisión de almacenamiento | No |
| P1-6 | Datos faltantes de la política de privacidad (G-16) | PATRON + abogado | No |
| P1-7 | Textos y móvil | Claude, PR | No |
| F0-8 | Investigar los ~12 h sin escaneo del 17/18-nov | Hilo de la 2.1 | No |
| F0-9 | Integrar la cadena #3→#8 en `main` según `docs/PLAN_INTEGRACION_GIT.md` | Autorización | No |
| F0-10 | CI con la suite en 3.12 y 3.13 | Claude, PR | No |
| F0-11 | Licencia comercial de CoinGecko o fuente alternativa decidida | PATRON | No (contrato) |

**Criterio de salida de Fase 0:** todos los P0 cerrados con evidencia, PR #11–#14 revisados (fusionados o descartados), CI verde, y una semana de escaneos sin huecos medida por la observabilidad mínima.
