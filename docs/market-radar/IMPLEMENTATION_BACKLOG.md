# Backlog de implementación · Market Radar

Fecha: 18-nov-2026. Tamaño: S (≤ 1 día), M (2–4 días), L (1–2 semanas), XL (dividir antes de empezar).
Cada ítem enlaza requisitos de `PRODUCT_REQUIREMENTS.md`. Ningún ítem se empieza sin la aprobación de la fase. Las PR van a ramas propias, en borrador, sin fusionar ni desplegar.

## Épica F0 · Estabilización 2.1 (Fase 0)

| Id | Historia | Resp. | Tam. | Aceptación |
|---|---|---|---|---|
| F0-1 | Inscribir TOTP del admin y borrar el código de alta | PATRON | S | Registro de arranque sin "vigente"; acceso admin pide TOTP |
| F0-2 | Rotar `radar_app` y token de Telegram | PATRON | S | Fecha de rotación registrada; app y bot funcionan |
| F0-3 | Health check `/healthz` en Render | PATRON | S | Servicio muestra el path configurado |
| F0-4 | Revisar y decidir PR #11, #12, #14, #13 | PATRON / C | M | Cada PR fusionada o cerrada con motivo |
| F0-5 | Copia verificada y suspensión de la 2.0 | PATRON | S | Copia con `verify` OK; servicio suspendido (irreversible) |
| F0-6 | Repositorio privado | PATRON | S | `private: true`; despliegue manual de prueba OK |
| F0-7 | Copias automáticas cifradas externas | C tras decisión | M | Copia diaria + restauración mensual probada |
| F0-8 | Diagnóstico de huecos de escaneo 17/18-nov | Hilo 2.1 | S | Causa documentada |
| F0-9 | Integrar #3→#8 en `main` | C con autorización | M | `main` = producción; suite verde |
| F0-10 | CI GitHub Actions: 3.12 + 3.13, SQLite + PostgreSQL, pip-audit, gitleaks | C | M | Workflow verde en una PR de prueba |
| F0-11 | Decidir licencia cripto (CoinGecko Basic y exchange) | PATRON | S | Fila en `provider_licenses` (cuando exista) o documento |

## Épica F1 · Diseño (Fase 1)

| Id | Historia | Tam. | Aceptación |
|---|---|---|---|
| F1-1 | 14 documentos de la §20 | L | **Esta PR** |
| F1-2 | Aprobar/sustituir decisiones D-005…D-012 | S | `DECISION_LOG.md` actualizado por PATRON |
| F1-3 | Prototipo de interfaz (HTML estático navegable, móvil y escritorio) con datos ficticios marcados | L | Revisado por PATRON; capturas en carpeta del proyecto |
| F1-4 | Contratos de adaptador en código (`Protocol`, tipos, errores) con pruebas grabadas | M | Pruebas sin red pasan |
| F1-5 | Migraciones iniciales del esquema `mr` (sin aplicar en producción) | M | Aplican y revierten en PG 16 local |
| F1-6 | Correos de consulta de licencias (borradores) | S | PATRON los envía o descarta |
| F1-7 | Pregunta de encuesta "otros mercados" en el piloto | S | Incluida en la instrumentación apagada de #14 |

## Épica R · Registro y calendarios (Fase 2)

| Id | Historia | Req. | Tam. |
|---|---|---|---|
| R-1 | Tablas `markets`, `exchanges`, `assets`, `instruments`, `asset_identifiers` | RD-01, RD-02 | M |
| R-2 | Resolución de identificador por fecha con pruebas de colisión de tickers | RD-01 | M |
| R-3 | Carga cripto desde CoinGecko con `coingecko_id` | RD-01 | S |
| R-4 | `market_calendars`, `market_sessions`; cripto 24/7 | RD-05 | M |
| R-5 | Calendario NYSE/Nasdaq (festivos, medias sesiones) con pruebas por año | RD-05 | M |
| R-6 | `providers`, `provider_licenses`, guarda de licencia en `ingest` | RD-10 | M |

## Épica D · Datos e ingesta (Fase 2)

| Id | Historia | Req. | Tam. |
|---|---|---|---|
| D-1 | `ProviderAdapter` base: HTTP con reintentos, cuotas, errores tipados | §5 arq. | M |
| D-2 | Adaptadores Binance, OKX, Bybit, CoinGecko reescritos | — | L |
| D-3 | Tabla `candles` particionada; inserción idempotente | RD-03 | M |
| D-4 | Calidad generalizada con calendario (huecos reales vs mercado cerrado) | RD-06, RD-11 | M |
| D-5 | Tarea de retención por licencia con auditoría | RD-10 | S |

## Épica Q · Motores (Fase 2–3)

| Id | Historia | Req. | Tam. |
|---|---|---|---|
| Q-1 | Biblioteca única `features` (causal) portada de `radar/quant/features.py` | RQ-01…04 | L |
| Q-2 | Golden tests: valores de referencia de RSI, MACD, ATR, Bollinger, EMA contra cálculos independientes | NF-08 | M |
| Q-3 | Prueba de equivalencia: 300 series cripto, nueva vs `radar/quant` (diferencia 0 o explicada) | — | M |
| Q-4 | Trend, Momentum, Volume, Volatility engines con salida tipada y versión | RQ-01…04 | L |
| Q-5 | Liquidity y Risk engines | RQ-05, RQ-06 | M |
| Q-6 | Regime por mercado | RQ-08 | M |
| Q-7 | Máquina de estados con histéresis + pruebas de transición | RA-05 | M |
| Q-8 | Market Opportunity Score v1 con pesos por clase en `model_versions`; "evidencia histórica" = 0 | RS-01…06 | M |

## Épica S · Scanner (Fase 2–3)

| Id | Historia | Req. | Tam. |
|---|---|---|---|
| S-1 | Orquestador por mercado alineado a calendario, con líder único (PR #12) | RA-01 | M |
| S-2 | `scan_runs`, `scan_observations` inmutables, `opportunity_scores` | RA-06, RA-09 | M |
| S-3 | Ejecución en paralelo con la 2.1 y informe de diferencias | Fase 2 salida | M |
| S-4 | Filtros y ranking por mercado | RA-03, RA-07 | M |
| S-5 | Seguimiento de resultados a 5/20/60 sesiones (`hypothesis_outcomes`) | RB-07 | M |

## Épica O · Observabilidad (Fase 2)

| Id | Historia | Tam. |
|---|---|---|
| O-1 | Registros JSON y métricas por proveedor/escaneo/endpoint | M |
| O-2 | `/livez`, `/readyz` por mercado | S |
| O-3 | Alerta operativa por huecos | S |

## Épica U · Interfaz y API (Fase 3)

| Id | Historia | Req. | Tam. |
|---|---|---|---|
| U-1 | `/api/v1` con esquemas y procedencia en cada respuesta | §10 arq. | L |
| U-2 | Dashboard, Scanner, Mercados, Explorador | RU-02 | XL → dividir |
| U-3 | Ficha de activo (A–D, F, G) | RB-01…08 | L |
| U-4 | Watchlists y preferencias persistentes por usuario | RU-03 | M |
| U-5 | Historial de observaciones | RB-07 | M |
| U-6 | Ocultación por licencia en interfaz y exportación | RU-05 | S |

## Épica T · Alertas (Fase 3)

| Id | Historia | Req. | Tam. |
|---|---|---|---|
| T-1 | `alerts`, `alert_deliveries`, dedupe, límites, reintentos | RT-03 | M |
| T-2 | Plantillas Telegram con todos los campos de RT-02 | RT-02 | S |
| T-3 | Preferencias y horario silencioso | RT-04 | S |

## Épica M · Acciones/ETF (Fase 3, tras licencia)

| Id | Historia | Tam. |
|---|---|---|
| M-1 | Adaptador del proveedor elegido | M |
| M-2 | Acciones corporativas y series ajustadas/no ajustadas | L |
| M-3 | Universo histórico con deslistados | M |
| M-4 | Lista §18 completa con evidencia | M |

## Épicas posteriores (resumen)

| Épica | Fase | Contenido |
|---|---|---|
| FX | 4 | Adaptador, sesiones, fortaleza de monedas |
| IDX | 4 | Índice de referencia vs ETF/futuro; proxy etiquetado |
| MET | 4 | Spot, futuros, ETF separados; ratio oro/plata |
| FUT | 4–5 | `series`, `roll_rules`, curva, contango/backwardation |
| MAC | 4–6 | FRED, EIA, CFTC, USDA con atribución |
| GLB | 6 | Correlación, régimen global, Global Radar, Risk Center, Cartera |
| AI | 7 | Cuatro servicios con guardas, registro y tope de costo |
| VAL | 8 | Protocolo cuantitativo, holdouts por clase, paper trading separado |

## Orden recomendado de las primeras PR de la segunda entrega

1. F0-10 CI (desbloquea todo lo demás; no toca producción).
2. F1-4 contratos de adaptador + F1-5 migraciones `mr` (aisladas, sin aplicar).
3. Q-1 + Q-2 + Q-3 biblioteca única de features con equivalencia.
4. F1-3 prototipo de interfaz.
