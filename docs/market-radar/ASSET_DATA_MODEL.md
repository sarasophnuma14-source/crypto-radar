# Modelo de datos de activos · Market Radar

Versión 1.0 · 18-nov-2026 · Estado: **propuesta** (decisión D-008). PostgreSQL 16. Esquema `mr` separado del esquema `app` de la 2.1.

## 1. Idea central: activo ≠ instrumento ≠ serie

| Concepto | Ejemplo | Por qué se separa |
|---|---|---|
| **Activo** (`assets`) | Oro; S&P 500; Apple Inc.; Bitcoin; Petróleo WTI | Lo que el usuario piensa que sigue |
| **Instrumento** (`instruments`) | XAU/USD spot; GLD (ETF); GC dic-2026 (futuro); SPX (índice, no negociable); BTCUSDT en Binance | Lo que tiene precio, unidades, horario y vencimiento propios |
| **Serie** (`series`) | GC continuo, rollover por volumen, ajuste por diferencia, v1 | Lo que se analiza cuando un instrumento expira |

La especificación pide `assets` y `asset_identifiers`; este modelo añade `instruments`, `series` y `roll_rules` para cumplir "no mezclar instrumentos con unidades o vencimientos distintos" (§12 de la especificación). Es una propuesta que requiere aprobación (D-008).

## 2. Diagrama

```
markets ─┬─< exchanges
         └─< market_calendars ─< market_sessions
assets ─< instruments >─ exchanges
   │          ├─< asset_identifiers (proveedor, símbolo, vigencia)
   │          ├─< candles  (por proveedor y temporalidad)
   │          ├─< quotes
   │          ├─< corporate_actions
   │          └─< series_members >─ series >─ roll_rules
   ├─< fundamentals
   └─< news_item_assets >─ news_items
providers ─< provider_licenses
scan_runs ─< scan_observations ─< opportunity_scores
hypotheses ─< hypothesis_outcomes        experiment_registry
users ─< watchlists ─< watchlist_items
users ─< alerts ─< alert_deliveries
users ─< portfolios ─< portfolio_positions      risk_snapshots
model_versions        economic_events        indicators        audit_events
```

## 3. Columnas comunes de procedencia

Toda tabla de **datos de mercado u observación** lleva:

| Columna | Tipo | Significado |
|---|---|---|
| `provider_id` | text FK | proveedor de origen |
| `source_ts` | timestamptz | momento al que se refiere el dato según el proveedor |
| `received_ts` | timestamptz | momento en que lo recibimos |
| `timeframe` | text | `1m`,`5m`,`15m`,`1h`,`4h`,`1d`,`1w` o `tick` |
| `processing_version` | text | hash de código de normalización/motores + versión |
| `quality_status` | text | `ok`, `degraded`, `stale`, `suspect`, `missing` |
| `license_id` | FK | licencia bajo la que se guardó |

## 4. Tablas de referencia

### `markets`
`market_id` (pk, texto: `CRYPTO`, `US_EQUITY`, `US_ETF`, `FX`, `METALS`, `INDICES`, `ENERGY`, `AGRI`), `name`, `asset_class`, `default_currency`, `calendar_id`, `enabled` (bool, interruptor de reversión), `enabled_at`, `enabled_by`, `acceptance_checklist` (jsonb con los 14 criterios y evidencia).

### `exchanges`
`exchange_id` (MIC ISO 10383 cuando exista; `BINANCE`, `OTC_FX` si no), `name`, `country`, `timezone`, `market_id`.

### `assets`
`asset_id` (uuid), `asset_class` (`crypto`,`equity`,`etf`,`fx_pair`,`metal`,`index`,`energy`,`agri`), `name`, `sector`, `industry`, `country`, `status` (`active`,`delisted`,`merged`,`dead`), `listed_from`, `listed_to`, `created_at`.

### `instruments`
`instrument_id` (uuid), `asset_id`, `exchange_id`, `kind` (`spot`,`perp`,`future`,`etf`,`stock`,`index`,`otc_pair`), `base_ccy`, `quote_ccy`, `unit` (p. ej. `troy_oz`, `barrel`, `bushel`, `share`, `mmbtu`), `contract_size`, `tick_size`, `expiry` (null si no vence), `tradable` (false para índices), `calendar_id`, `status`, `first_seen`, `last_seen`.

Restricción: `kind='index' ⇒ tradable=false`. `kind='future' ⇒ expiry NOT NULL`.

### `asset_identifiers`
`instrument_id`, `scheme` (`ticker`,`isin`,`cusip`,`figi`,`provider_symbol`,`coingecko_id`), `value`, `provider_id` (null si es universal), `valid_from`, `valid_to`.
Único: (`scheme`, `value`, `provider_id`, `valid_from`). Resolver un ticker exige fecha.

### `providers` y `provider_licenses`
`providers`: `provider_id`, `name`, `kind` (`market_data`,`news`,`macro`,`fundamentals`), `base_url`, `adapter_version`, `status`.
`provider_licenses`: `license_id`, `provider_id`, `plan`, `scope_markets` (text[]), `allows_storage` (bool), `max_storage_days`, `allows_display` (bool), `display_delay_min` (0 = tiempo real), `allows_derived_public` (bool), `allows_export` (bool), `allows_redistribution` (bool), `max_users`, `requires_attribution` (texto exacto), `professional_users_allowed` (bool), `contract_ref`, `verified_by`, `verified_at`, `valid_until`, `notes`.
**Regla:** sin fila vigente con `allows_display=true`, la API devuelve `license_display:false` y la interfaz oculta el valor.

### `market_calendars` y `market_sessions`
`market_calendars`: `calendar_id`, `timezone`, `regular_open`, `regular_close`, `source`.
`market_sessions`: `calendar_id`, `session_date`, `kind` (`regular`,`pre`,`post`,`half_day`,`closed`), `open_ts`, `close_ts`. Generadas con anticipación de 12 meses; cripto = sesión continua con cierre diario 00:00 UTC.

## 5. Datos de mercado

### `candles`
PK (`instrument_id`, `provider_id`, `timeframe`, `bar_start`, `adjusted`).
`bar_start`, `bar_end` (timestamptz; convención: inicio inclusivo, fin exclusivo), `open`, `high`, `low`, `close` (numeric(28,10)), `volume` (numeric), `quote_volume`, `trades`, `session_kind`, `is_closed` (bool), + procedencia.
Particionado por `asset_class` y año. Las velas abiertas no se guardan como cerradas.

### `quotes`
`instrument_id`, `provider_id`, `ts`, `bid`, `ask`, `last`, `mid`, `spread_bps`, + procedencia. Retención corta (configurable por licencia).

### `corporate_actions`
`instrument_id`, `kind` (`split`,`reverse_split`,`cash_dividend`,`stock_dividend`,`spinoff`,`symbol_change`,`delisting`), `ex_date`, `ratio`, `amount`, `currency`, + procedencia. Las series ajustadas se recalculan desde aquí con `processing_version` nueva.

### `series`, `series_members`, `roll_rules`
`roll_rules`: `rule_id`, `method` (`calendar_days_before_expiry`,`volume_crossover`,`open_interest_crossover`), `params` jsonb, `adjustment` (`none`,`difference`,`ratio`), `version`.
`series`: `series_id`, `asset_id`, `rule_id`, `kind` (`continuous`,`spot_proxy`,`etf_proxy`).
`series_members`: `series_id`, `instrument_id`, `active_from`, `active_to`.

### `fundamentals`
`asset_id`, `period_end`, `period_type` (`Q`,`FY`,`TTM`), `metric`, `value`, `currency`, `reported_ts`, + procedencia. Se usa `reported_ts` (no `period_end`) en investigación para evitar look-ahead.

### `economic_events`
`event_id`, `country`, `name`, `scheduled_ts`, `actual`, `forecast`, `previous`, `unit`, `importance`, `source_url`, + procedencia.

### `news_items` y `news_item_assets`
`news_id`, `provider_id`, `published_ts`, `received_ts`, `title`, `url`, `summary_allowed` (bool según licencia), `language`, `raw_hash`. Relación con activos con `confidence` y `method` (`provider_tag`,`ner`,`manual`). El texto completo no se guarda salvo licencia.

### `indicators`
Caché opcional de valores calculados: `instrument_id`, `timeframe`, `bar_start`, `name`, `params_hash`, `value`, `processing_version`. Recalculable; no es fuente de verdad.

## 6. Escaneo, puntuación e hipótesis

### `scan_runs`
`run_id`, `market_id`, `timeframe`, `started_at`, `finished_at`, `status` (`ok`,`partial`,`failed`), `universe_size`, `excluded` jsonb (motivo → n), `providers_used` jsonb, `errors` jsonb, `processing_version`, `leader_instance`.

### `scan_observations`
`obs_id`, `run_id`, `instrument_id`, `timeframe`, `as_of` (cierre de la última vela usada), `state`, `prev_state`, `engine_outputs` jsonb (trend, momentum, volume, volatility, liquidity, regime con valores y reglas), `evidence` jsonb (lista corta legible), `invalidation` jsonb, `risks` jsonb, `data_quality`, + procedencia. **Inmutable.**

### `opportunity_scores`
`obs_id`, `model_version_id`, `total` (0–100 o null), `components` jsonb, `weights_ref`, `validated` (bool, siempre false hasta aprobación).

### `hypotheses` y `hypothesis_outcomes`
`hypotheses`: `hypothesis_id`, `experiment_id`, `instrument_id`, `created_obs_id`, `direction`, `event_definition`, `horizon`, `invalidation_rule`, `benchmark`, `created_at`.
`hypothesis_outcomes`: `hypothesis_id`, `horizon`, `measured_at`, `return`, `benchmark_return`, `max_adverse`, `max_favorable`, `invalidated_at`, `outcome` (`hit`,`miss`,`invalidated`,`no_data`).

### `model_versions` y `experiment_registry`
`model_versions`: `model_version_id`, `component` (`score`,`engine:trend`,…,`ai:analyst`), `version`, `code_hash`, `params` jsonb, `created_at`, `status` (`draft`,`active`,`retired`), `approved_by`.
`experiment_registry`: `experiment_id`, `title`, `preregistration` (texto/hash), `registered_at`, `data_cutoff`, `holdout_spec`, `holdout_lock_hash`, `status`, `result_summary`, `tests_count_before` (para corrección por pruebas múltiples).

## 7. Usuarios y personalización

Se reutiliza `app.users` de la 2.1. Tablas nuevas en `mr`:
`watchlists` (`watchlist_id`, `user_id`, `name`), `watchlist_items` (`watchlist_id`, `instrument_id`, `added_at`, `note`), `alerts` (`alert_id`, `user_id`, `kind`, `filter` jsonb, `channel`, `quiet_hours`, `rate_limit`), `alert_deliveries` (`delivery_id`, `alert_id`, `obs_id`, `dedupe_key` único, `status`, `attempts`, `last_error`, `sent_at`), `portfolios`, `portfolio_positions` (`instrument_id`, `quantity`, `cost`, `opened_at`; **sin órdenes**), `risk_snapshots` (`portfolio_id`, `as_of`, métricas jsonb, `processing_version`).

## 8. Auditoría

`audit_events`: `event_id`, `at`, `actor` (`user:<id>`,`system:worker`,`admin:<id>`), `action`, `target`, `detail` jsonb (sin secretos ni datos personales innecesarios), `ip_hash`, `prev_hash`, `hash` (cadena opcional para cambios de licencias, mercados habilitados y versiones de modelo).

## 9. Reglas de integridad y retención

| Regla | Implementación |
|---|---|
| No guardar más allá de la licencia | Tarea diaria borra filas con `received_ts` anterior a `max_storage_days` de su licencia; registra en `audit_events` |
| No mezclar unidades | `CHECK` y validación en `normalize`: comparaciones entre instrumentos exigen misma `unit` o conversión declarada |
| No mezclar vencimientos | Las consultas de análisis usan `series`, nunca varios `instruments` futuros sueltos |
| Universo histórico | `assets.status` y `instruments.last_seen` nunca se borran (sesgo de supervivencia) |
| Datos personales | Solo en `app.users` y tablas de usuario; borrado en cascada según política de retención |

## 10. Migración desde la 2.1

1. Crear esquema `mr` (aditivo; la 2.1 no lo lee).
2. Poblar `assets`/`instruments` cripto desde CoinGecko + listas de pares, con `coingecko_id` como identificador (resuelve la ambigüedad de tickers).
3. Ejecutar el escáner nuevo en paralelo con la 2.1 durante ≥ 14 días y comparar estados y métricas por activo.
4. Ninguna tabla de la 2.1 se modifica ni se borra.
