# Arquitectura objetivo · Market Radar

Versión 1.0 · 18-nov-2026 · Estado: **propuesta**, pendiente de aprobación (decisiones D-005 a D-012 en `DECISION_LOG.md`).

## 1. Decisión central: monolito modular, dos procesos

Market Radar se construye como **un monolito modular en Python** con paquetes de límites claros, desplegado como **dos procesos** cuando la medición lo justifique:

- **web**: API versionada + frontend estático + autenticación.
- **worker**: ingesta, normalización, escaneo, motores, alertas, tareas programadas.

Ambos comparten código y la misma base PostgreSQL. No hay microservicios, colas ni Redis en la arquitectura inicial. Cada uno de esos componentes tiene un criterio de entrada medible (§9).

**Por qué no microservicios:** un equipo de una persona más asistentes, costos fijos que ya superan el ingreso probable (ver `MULTI_ASSET_UNIT_ECONOMICS.md`) y ningún componente con requisitos de escala independientes demostrados.

**Por qué no dentro de `radar/`:** `radar/` sirve producción y tiene pendientes de Fase 0. Construir al lado (patrón *strangler*) permite comparar resultados en paralelo y no tocar la 2.1.

## 2. Vista de componentes

```
                    ┌──────────────────────── web ─────────────────────────┐
  Navegador ───────►│ A Frontend (estático)    B API /api/v1 (contratos)    │
  Telegram  ◄───┐   │ O Administración         auth/sesiones (de radar/)    │
                │   └──────────────┬───────────────────────────────────────┘
                │                  │ lee
                │   ┌──────────────▼─────────────── PostgreSQL ─────────────┐
                │   │ registry · market data · observaciones · usuarios ·    │
                │   │ alertas · auditoría · experimentos                     │
                │   └──────────────▲───────────────────────────────────────┘
                │                  │ escribe
                │   ┌──────────────┴──────────── worker ────────────────────┐
                └───┤ L Alert Service   G Scanner Orchestrator (líder único) │
                    │ D Ingestion → E Normalization → calidad              │
                    │ C Asset Registry  F Calendars                         │
                    │ H Engines (trend, momentum, volume, volatility,       │
                    │   liquidity, regime, correlation, catalyst)           │
                    │ J Risk  M Portfolio  K AI Services (fase 7)           │
                    │ N Audit  P Observability                              │
                    └──────────────┬───────────────────────────────────────┘
                                   │ HTTPS (adaptadores con licencia)
                       Proveedores: cripto · acciones/ETF · FX · futuros · macro · noticias
                    I Quantitative Research: fuera de línea, misma biblioteca de motores,
                      lee copias de datos; nunca escribe en tablas de producción
```

## 3. Paquetes

Directorio nuevo `market_radar/` en el mismo repositorio (decisión D-006):

| Paquete | Componente | Responsabilidad | Depende de |
|---|---|---|---|
| `market_radar/registry` | C | activos, instrumentos, identificadores, mercados, bolsas | `db` |
| `market_radar/calendars` | F | sesiones, festivos, horarios parciales, estado abierto/cerrado | registry |
| `market_radar/providers` | D | adaptadores por proveedor con interfaz común, licencias, límites | registry |
| `market_radar/ingest` | D | tareas de descarga, reintentos, cuotas, idempotencia | providers, calendars |
| `market_radar/normalize` | E | unidades, monedas, ajustes corporativos, rollover, calidad | registry, calendars |
| `market_radar/quality` | E | puntuación de calidad por serie (generaliza `radar/quant/quality.py`) | calendars |
| `market_radar/features` | H | biblioteca causal única de indicadores | — (puro) |
| `market_radar/engines/*` | H | un subpaquete por motor; funciones puras sobre `features` | features |
| `market_radar/scoring` | — | Market Opportunity Score versionado | engines |
| `market_radar/scanner` | G | orquestación por mercado, estados, observaciones | todos los anteriores |
| `market_radar/risk` | J | riesgo por activo y cartera | engines |
| `market_radar/portfolio` | M | carteras de usuario (lectura; sin órdenes) | risk |
| `market_radar/alerts` | L | reglas, deduplicación, entregas, Telegram | scanner |
| `market_radar/ai` | K | cuatro servicios, guardas, registro | API de solo lectura interna |
| `market_radar/audit` | N | `audit_events`, hash encadenado opcional | db |
| `market_radar/obs` | P | métricas, registros JSON, health/readiness | — |
| `market_radar/api` | B | `/api/v1/...` con esquemas | todos (solo lectura salvo preferencias) |
| `research/` | I | experimentos, registro, holdout | features, engines |

Regla de dependencias (comprobada por prueba): `features` y `engines` no importan nada de red ni de base de datos; `api` no importa `providers`; `research` no escribe en producción.

## 4. Reutilización de la 2.1

| De la 2.1 | Uso | Cómo |
|---|---|---|
| `radar/auth.py`, `totp.py`, `secretbox.py`, `rate_limits` | Autenticación de Market Radar | Importar tal cual; misma tabla `users` |
| `radar/db.py` | Conexión | Extraer a `market_radar/db` cuando se integre; mientras, envoltorio |
| `radar/quant/quality.py`, `features.py` | Base de `quality` y `features` | Portar con pruebas de equivalencia (mismos valores en 300 series cripto) |
| `radar/data.py` (Binance/Bybit/OKX/CoinGecko) | Adaptadores cripto | Reescritos con la interfaz común; mismos endpoints |
| `leader.py` (PR #12) | Líder único del worker | Requisito previo |
| `radar/edge/ledger.py`, `research/prospectivo` | Registro de experimentos | Base de `experiment_registry` |

## 5. Contrato de adaptador de proveedor

```python
class ProviderAdapter(Protocol):
    provider_id: str                      # "binance_spot", "twelvedata", ...
    version: str

    def capabilities(self) -> Capabilities        # clases, temporalidades, historial, intradía, bid/ask
    def license(self) -> LicenseTerms              # leído de provider_licenses, no del código
    def limits(self) -> RateLimits                 # peticiones/min, por día, peso
    def health(self) -> ProviderHealth             # último éxito, error, latencia p95
    def resolve(self, ident: Identifier) -> list[InstrumentRef]
    def list_instruments(self, market: str) -> Iterable[InstrumentMeta]
    def candles(self, inst: InstrumentRef, tf: Timeframe,
                start: datetime, end: datetime) -> CandleBatch
    def quote(self, inst: InstrumentRef) -> Quote | None
```

- `CandleBatch` lleva siempre `source_ts`, `received_ts`, `provider_id`, `adapter_version`, `adjusted: bool`, `currency`, `unit`.
- Errores tipados: `RateLimited(wait)`, `NotEntitled`, `NotFound`, `ProviderDown`, `BadData`.
- Antes de cada llamada, `ingest` comprueba en `provider_licenses` que el uso está permitido; si no, lanza `NotEntitled` sin llamar.
- Cada adaptador tiene pruebas con respuestas grabadas (sin red) y una prueba de humo opcional con red.

## 6. Flujo de un escaneo por mercado

```
calendars.next_due(market) ─► scanner.run(market, tf)
  1. registry.universe(market, as_of)          universo por fecha, con exclusiones y motivos
  2. ingest.ensure(candles hasta el último cierre)   solo lo que falta; idempotente
  3. normalize + quality                       calidad < umbral ⇒ "Sin datos suficientes"
  4. engines.*(features)                       funciones puras, versionadas
  5. scoring.score(version)                    componentes + total
  6. state_machine.transition(prev, evidencia) histéresis para evitar parpadeo
  7. persist: scan_runs, scan_observations, opportunity_scores
  8. alerts.evaluate(cambios)                  dedupe, límites, entregas
  9. obs.emit(duración, huecos, errores)
```

Cada paso escribe con `processing_version` = hash del código de motores + versión del score. Un `scan_run` se puede reejecutar en investigación con los mismos datos.

## 7. Almacenamiento

| Dato | Dónde | Motivo |
|---|---|---|
| Registro, usuarios, observaciones, alertas, auditoría | PostgreSQL (Neon) | relacional, transaccional |
| Velas diarias | PostgreSQL, tabla `candles` particionada por clase de activo y año | volumen manejable (§8) |
| Velas intradía | PostgreSQL con retención limitada (p. ej. 90 días de 1h) | **solo si la licencia permite almacenar** |
| Historial largo para investigación | Archivos Parquet fuera de producción | no carga Neon; reproducible |
| Caché de última cotización | memoria del worker | Redis solo si hay >1 worker (§9) |

## 8. Estimación de volumen (SUPUESTO, a medir)

| Escenario | Instrumentos | Velas diarias × 10 años | Tamaño aprox. (≈120 B/fila con índice) |
|---|---|---|---|
| Cripto (Fase 2) | 300 | ~1,1 M | ~0,13 GB |
| + acciones/ETF EE. UU. (Fase 3) | 3.000 | ~7,6 M | ~0,9 GB |
| + macro, energía, agro (Fases 4–5) | +300 | ~0,8 M | ~0,1 GB |
| + 1h, 90 días (cripto 24 h; resto ~7 h por sesión) | 3.600 | ~2,1 M en ventana móvil | ~0,25 GB |

Cabe en PostgreSQL gestionado de gama baja; el límite real será la **licencia de almacenamiento** y la transferencia de Neon, no el disco.

## 9. Criterios para añadir infraestructura

| Componente | Se añade solo si |
|---|---|
| Proceso worker separado | El escaneo de todos los mercados habilitados supera 50 % de CPU media del servicio web o la memoria pico > 400 MB de 512 MB |
| Segundo worker | Un ciclo de escaneo no termina antes del siguiente con 1 worker |
| Redis | Hay ≥ 2 procesos que necesitan caché o límites compartidos y la tabla `rate_limits` en Postgres mide > 20 ms p95 |
| Cola de mensajes | Las alertas pierden entregas con la tabla `alert_deliveries` como cola |
| Almacén columnar / TimescaleDB | Consultas de velas p95 > 300 ms con particiones e índices |
| CDN | Tráfico estático > 50 % del ancho de banda de Render |

## 10. API

- Prefijo `/api/v1`. Esquemas JSON publicados en `docs/api/v1/*.json`. Cambios incompatibles ⇒ `/api/v2`.
- Toda respuesta con datos de mercado incluye `as_of`, `provider`, `processing_version`, `quality`, `license_display: true|false`.
- Lectura pública mínima (`/api/v1/public/status`): sin veredicto ni señales (corrige fase cero A-7).

## 11. Observabilidad

- Registros JSON una línea por evento, sin datos personales.
- Métricas: por proveedor (llamadas, errores, latencia, cuota restante), por escaneo (duración, activos, excluidos por motivo, huecos), por endpoint (p50/p95, códigos).
- `/livez` (proceso vivo), `/readyz` (base accesible, último escaneo dentro de la ventana esperada por mercado abierto).
- Alerta operativa al administrador por Telegram si un mercado habilitado no completa escaneo en 2 ventanas.

## 12. Despliegue y entornos

| Entorno | Uso | Datos |
|---|---|---|
| local | desarrollo | proveedores en modo grabado |
| staging (rama de Neon) | pruebas de integración | proveedores con claves de prueba; **solo el propietario la ve** (licencias de "display" aplican incluso a testers en algunos proveedores, p. ej. Massive) |
| producción | piloto | solo mercados habilitados según §18 |

Render sigue siendo la referencia inicial, sujeto a prueba de capacidad. Ningún despliegue en esta etapa.

## 13. Reversión

- Cada mercado tiene un interruptor `market_enabled` en base; apagarlo oculta el mercado sin borrar datos.
- Migraciones de esquema solo aditivas hasta la Fase 8; las destructivas requieren copia verificada y autorización.
- La 2.1 sigue sirviendo en paralelo hasta que Market Radar cripto pase la comparación (Fase 2, criterio de salida).
