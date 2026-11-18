# Plan del primer incremento técnico (I-1) · Market Radar

Fecha: 18-nov-2026. Estado: **propuesta; no implementada.** No existe todavía ninguna línea de código de Market Radar.

> **Nombre.** El propietario lo llama "Fase 1". En `MULTI_ASSET_ROADMAP.md` la Fase 1 es el diseño y la Fase 2 el núcleo. Para evitar confusión, este incremento se llama **I-1** y es la primera entrega de la **Fase 2 (núcleo)** del roadmap (SPECIFICATION_GAP_ANALYSIS, CON-02).

## 1. Objetivo y límites

**Objetivo:** construir el núcleo universal de activos y contratos, probado y aislado, sobre el que se apoyarán los mercados.

| Incluye | No incluye |
|---|---|
| Registro de mercados, bolsas, activos, instrumentos e identificadores con vigencia | Ningún proveedor real (ni comercial ni gratuito) |
| Contrato de proveedores y un proveedor **sintético** determinista | Ninguna llamada de red |
| Modelo de licencias y guarda de licencias | Motores, indicadores, estados, score, señales |
| Calendarios: 24/7 real y calendario de tabla con datos ficticios de prueba | Calendarios reales de bolsas |
| Capa cruda y capa normalizada de velas, bitemporal | Acciones corporativas, futuros, rollovers, series |
| Validadores puros de calidad del grupo I-1 de `DATA_QUALITY_TEST_PLAN` | Auditoría diaria, comparación entre proveedores |
| Migraciones SQL versionadas con reversión | Conexión a Neon o a cualquier base remota |
| Eventos operativos (formato y escritura) | Worker, planificador, API, interfaz, Telegram, IA |

## 2. Reglas de control de cambios

1. Rama nueva `claude/market-radar-i1`, creada desde `release-2.1`, PR **en borrador**, sin fusionar.
2. Solo se **añaden** archivos en carpetas nuevas: `market_radar/`, `tests/market_radar/`, `docs/market-radar/foundation/`. Ningún archivo existente se modifica (comprobado en la PR con `git diff --stat` contra la base).
3. `radar/`, `web/`, `main.py`, `render.yaml`, `requirements.txt`, `ventas/` y `research/` quedan intactos.
4. Ninguna conexión a Neon ni a Render. Las pruebas usan PostgreSQL 16 local y SQLite no se usa (las restricciones de exclusión y los tipos de rango son de PostgreSQL).
5. Nada de producción importa `market_radar`: aunque la PR se fusionara, la 2.1 no cambiaría de comportamiento (prueba §6.8).
6. Fusionar exige: Fase 0 cerrada (CON-01) **y** autorización expresa del propietario.

## 3. Estructura de carpetas

```
market_radar/
  __init__.py                 versión del paquete
  __main__.py                 CLI: migrate up|down|status, selfcheck
  core/
    types.py                  enums: AssetClass, InstrumentKind, Timeframe, QualityStatus, SessionKind, DataUse
    timeutil.py               Clock (protocolo), SystemClock, FixedClock, utilidades UTC
    errors.py                 jerarquía de errores del dominio
  registry/
    models.py                 dataclasses inmutables: Market, Exchange, Asset, Instrument, Identifier, InstrumentSource
    repository.py             protocolo RegistryRepository
    memory.py                 implementación en memoria (pruebas)
    postgres.py               implementación sobre psycopg
  calendars/
    base.py                   protocolo MarketCalendar, dataclass Session
    continuous.py             Continuous24x7 (cripto, cierre diario 00:00 UTC)
    table.py                  TableCalendar (lee market_sessions)
  providers/
    contract.py               ProviderAdapter, ProviderDescriptor, Capabilities, Candle, CandleBatch, ProviderHealth, errores
    licensing.py              LicenseTerms, DataUse, LicenseGuard
    synthetic.py              SyntheticProvider determinista (semilla), sin red
  quality/
    rules.py                  reglas puras DQ-DUP-01/02, DQ-BAR-01…05, DQ-SES-01…04, DQ-STALE-04
    report.py                 resultado por lote: aceptado / rechazado / marcado, con motivo
  storage/
    migrate.py                runner de migraciones (checksum, up/down, bloqueo)
    candles.py                escritura cruda + normalizada, lectura vigente y "as of"
    ops.py                    escritura de eventos operativos
  boundaries.py               lista de dependencias permitidas entre subpaquetes (la usa la prueba de fronteras)
  migrations/
    0001_base.up.sql / .down.sql
    0002_registry.up.sql / .down.sql
    0003_providers_licenses.up.sql / .down.sql
    0004_calendars.up.sql / .down.sql
    0005_candles.up.sql / .down.sql
    0006_ops_events.up.sql / .down.sql
tests/market_radar/
  fixtures/synthetic.py       series y calendarios ficticios de DATA_QUALITY_TEST_PLAN §2
  contract/conformance.py     batería que todo ProviderAdapter debe pasar
  test_types.py  test_registry_memory.py  test_registry_pg.py  test_calendars.py
  test_provider_contract.py  test_licensing.py  test_quality_rules.py
  test_migrations.py  test_candles_bitemporal.py  test_ops_events.py
  test_boundaries.py  test_no_network.py  test_isolation_from_radar.py
docs/market-radar/foundation/
  DEVELOPER_GUIDE.md          cómo correr pruebas y migraciones en local
  CONTRACTS.md                contrato de proveedor y de calendario, con ejemplos
  DATA_MODEL_I1.md            tablas creadas por I-1 y sus restricciones
```

## 4. Contratos de interfaces

Todas las estructuras son `dataclass(frozen=True, slots=True)`; todos los tiempos son `datetime` con zona UTC (una prueba rechaza tiempos sin zona).

### 4.1 Tipos base

```python
class AssetClass(StrEnum): CRYPTO, EQUITY, ETF, FX, METAL, INDEX, ENERGY, AGRI
class InstrumentKind(StrEnum): SPOT, PERP, FUTURE, ETF, STOCK, INDEX, OTC_PAIR
class Timeframe(StrEnum): M1, M5, M15, H1, H4, D1, W1     # con .duration y .align(ts)
class QualityStatus(StrEnum): OK, DEGRADED, SUSPECT, STALE, MISSING, REJECTED
class DataUse(StrEnum): STORE, DISPLAY, DERIVED_PUBLIC, ALERT, EXPORT, RESEARCH, STAGING

class Clock(Protocol):
    def now(self) -> datetime: ...          # siempre UTC
```

### 4.2 Registro

```python
@dataclass(frozen=True, slots=True)
class Instrument:
    instrument_id: UUID; asset_id: UUID; exchange_id: str; kind: InstrumentKind
    base_ccy: str; quote_ccy: str; unit: str; contract_size: Decimal | None
    tick_size: Decimal | None; expiry: datetime | None; tradable: bool; calendar_id: str

class RegistryRepository(Protocol):
    def add_asset(self, a: Asset) -> None: ...
    def add_instrument(self, i: Instrument) -> None: ...          # valida kind/expiry/tradable
    def add_identifier(self, ident: Identifier) -> None: ...       # falla si solapa vigencias
    def resolve(self, scheme: str, value: str, at: datetime,
                provider_id: str | None = None) -> Instrument: ... # fecha obligatoria
    def primary_source(self, instrument_id: UUID, at: datetime) -> str: ...
```

### 4.3 Calendarios

```python
@dataclass(frozen=True, slots=True)
class Session:
    calendar_id: str; session_date: date; kind: SessionKind; open_ts: datetime; close_ts: datetime

class MarketCalendar(Protocol):
    calendar_id: str
    def sessions(self, start: datetime, end: datetime) -> Iterator[Session]: ...
    def is_open(self, ts: datetime) -> bool: ...
    def session_for(self, ts: datetime) -> Session | None: ...
    def last_closed_session(self, now: datetime) -> Session | None: ...
    def expected_bars(self, tf: Timeframe, start: datetime, end: datetime) -> Iterator[datetime]: ...
```

### 4.4 Proveedores

```python
@dataclass(frozen=True, slots=True)
class Candle:
    instrument_id: UUID; timeframe: Timeframe; bar_start: datetime; bar_end: datetime
    open: Decimal; high: Decimal; low: Decimal; close: Decimal; volume: Decimal
    is_closed: bool; source_ts: datetime

@dataclass(frozen=True, slots=True)
class CandleBatch:
    provider_id: str; adapter_version: str; received_ts: datetime
    adjusted: bool; currency: str; candles: tuple[Candle, ...]; next_cursor: str | None
    def content_hash(self) -> str: ...      # SHA-256 canónico por vela

@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider_id: str; version: str; asset_classes: frozenset[AssetClass]
    timeframes: frozenset[Timeframe]; max_history_days: int | None
    declared_rate_limit_per_min: int | None; requires_key: bool

class ProviderAdapter(Protocol):
    descriptor: ProviderDescriptor
    def health(self) -> ProviderHealth: ...
    def list_instruments(self, market_id: str) -> Iterator[InstrumentMeta]: ...
    def candles(self, ref: ProviderSymbol, tf: Timeframe, start: datetime, end: datetime,
                cursor: str | None = None) -> CandleBatch: ...

# Errores: ProviderError > RateLimited(retry_after_s) | NotEntitled | NotFound
#          | ProviderUnavailable | InvalidResponse | ContractViolation
```

### 4.5 Licencias

```python
@dataclass(frozen=True, slots=True)
class LicenseTerms:
    license_id: UUID; provider_id: str; scope_markets: frozenset[str]
    allowed_uses: frozenset[DataUse]; max_storage_days: int | None
    display_delay_min: int | None; attribution: str | None
    valid_from: datetime; valid_until: datetime | None; contract_ref: str | None

class LicenseGuard:
    def __init__(self, terms_source: Callable[[str], list[LicenseTerms]], clock: Clock): ...
    def require(self, provider_id: str, market_id: str, use: DataUse) -> LicenseTerms: ...
        # lanza NotEntitled si no hay términos vigentes que lo permitan; sin excepciones por defecto
```

Regla: **sin licencia registrada no hay nada permitido**, ni siquiera `RESEARCH`. El proveedor sintético se registra con una licencia de prueba marcada `contract_ref = "SINTETICO-SOLO-PRUEBAS"` que el `LicenseGuard` rechaza fuera de pruebas (variable `MARKET_RADAR_ENV=test`).

### 4.6 Almacenamiento de velas

```python
class CandleStore:
    def write(self, batch: CandleBatch, guard: LicenseGuard, market_id: str) -> WriteResult: ...
        # 1) guard.require(..., STORE)  2) reglas de calidad  3) raw_candles (solo inserción)
        # 4) candles: inserta nueva revisión o ignora si el hash es igual; cierra la anterior
    def read_current(self, instrument_id, provider_id, tf, start, end) -> list[StoredCandle]: ...
    def read_as_of(self, watermark: datetime, instrument_id, provider_id, tf, start, end) -> list[StoredCandle]: ...
    def watermark(self) -> datetime: ...   # max(recorded_at)
```

## 5. Modelo de datos de I-1

Esquema `mr`. Solo las tablas necesarias para el núcleo; el resto de `ASSET_DATA_MODEL` llega en incrementos posteriores.

| Migración | Tablas | Restricciones clave |
|---|---|---|
| 0001 | `mr.schema_migrations` | versión PK, checksum SHA-256, aplicado_en |
| 0002 | `markets`, `exchanges`, `assets`, `instruments`, `asset_identifiers`, `instrument_sources` | `CHECK (kind <> 'index' OR NOT tradable)`, `CHECK (kind <> 'future' OR expiry IS NOT NULL)`, `EXCLUDE USING gist (scheme WITH =, value WITH =, coalesce(provider_id,'') WITH =, tstzrange(valid_from, valid_to) WITH &&)`; igual para `instrument_sources` por prioridad |
| 0003 | `providers`, `provider_licenses` | `allowed_uses text[]` con `CHECK` sobre valores válidos; `valid_until > valid_from` |
| 0004 | `market_calendars`, `market_sessions` | PK (`calendar_id`, `session_date`, `kind`); `close_ts > open_ts` |
| 0005 | `raw_candles`, `candles` | ver abajo |
| 0006 | `ops_events` | `at`, `kind`, `detail jsonb`; índice por `at` |

```sql
-- 0005 (extracto)
CREATE TABLE mr.raw_candles (
  raw_id        bigserial PRIMARY KEY,
  provider_id   text NOT NULL REFERENCES mr.providers,
  instrument_id uuid NOT NULL REFERENCES mr.instruments,
  timeframe     text NOT NULL,
  bar_start     timestamptz NOT NULL,
  payload       jsonb NOT NULL,                 -- lo recibido, normalizado a JSON canónico
  content_hash  text NOT NULL,
  received_ts   timestamptz NOT NULL,
  adapter_version text NOT NULL,
  license_id    uuid NOT NULL REFERENCES mr.provider_licenses
);
CREATE TABLE mr.candles (
  instrument_id uuid NOT NULL REFERENCES mr.instruments,
  provider_id   text NOT NULL REFERENCES mr.providers,
  timeframe     text NOT NULL,
  bar_start     timestamptz NOT NULL,
  bar_end       timestamptz NOT NULL,
  adjusted      boolean NOT NULL DEFAULT false,
  open numeric(28,10) NOT NULL, high numeric(28,10) NOT NULL,
  low  numeric(28,10) NOT NULL, close numeric(28,10) NOT NULL,
  volume numeric(38,10) NOT NULL,
  is_closed     boolean NOT NULL,
  source_ts     timestamptz NOT NULL,
  received_ts   timestamptz NOT NULL,
  recorded_at   timestamptz NOT NULL DEFAULT clock_timestamp(),
  superseded_at timestamptz,
  content_hash  text NOT NULL,
  raw_id        bigint NOT NULL REFERENCES mr.raw_candles,
  quality_status text NOT NULL,
  processing_version text NOT NULL,
  CHECK (low <= LEAST(open, close) AND GREATEST(open, close) <= high),
  CHECK (low > 0 AND volume >= 0 AND bar_end > bar_start),
  CHECK (superseded_at IS NULL OR superseded_at >= recorded_at)
);
-- una sola revisión vigente por vela
CREATE UNIQUE INDEX candles_current ON mr.candles
  (instrument_id, provider_id, timeframe, bar_start, adjusted) WHERE superseded_at IS NULL;
CREATE INDEX candles_asof ON mr.candles
  (instrument_id, provider_id, timeframe, bar_start, recorded_at);
```

`numeric(38,10)` para volumen (cambio respecto a `ASSET_DATA_MODEL`: tokens con suministros de 10¹⁵ unidades y precios bajos pueden superar 28 dígitos en volumen).

## 6. Pruebas

Marco: `unittest` (el mismo de la suite actual, `tests/test_suite.py`). Python 3.12 (producción) y 3.13. PostgreSQL 16 local vía `MARKET_RADAR_TEST_DSN`; las pruebas de PostgreSQL **fallan** (no se omiten) si la variable falta en CI.

| # | Grupo | Qué demuestra | Casos aprox. |
|---|---|---|---|
| 6.1 | Tipos y tiempo | Rechazo de tiempos sin zona; alineación de temporalidades | 10 |
| 6.2 | Registro (memoria y PG, misma batería) | Altas, validaciones, resolución con fecha, vigencias sin solape (DQ-SYM-01…03), fuente primaria | 20 |
| 6.3 | Calendarios | 24/7; calendario ficticio con festivo, media sesión y cambios de hora de EE. UU. y Europa; `expected_bars` (DQ-SES-01…04, DQ-STALE-04) | 15 |
| 6.4 | Contrato de proveedores | El proveedor sintético pasa la batería de conformidad; un proveedor defectuoso a propósito la falla en cada punto | 15 |
| 6.5 | Licencias | Sin términos → `NotEntitled`; términos vencidos; uso no incluido; licencia sintética fuera de pruebas | 10 |
| 6.6 | Reglas de calidad | Cada regla I-1 con caso positivo y negativo (DATA_QUALITY_TEST_PLAN §3) | 25 |
| 6.7 | Migraciones | `up` desde vacío, `down` hasta vacío, `up` de nuevo; idempotencia; checksum alterado → error; ejecución concurrente bloqueada | 8 |
| 6.8 | Aislamiento | Nada en `market_radar/` importa `radar/`; nada en `radar/`, `main.py` ni `web/` importa `market_radar`; `render.yaml` y `requirements.txt` sin cambios respecto a la base | 4 |
| 6.9 | Sin red | Toda la suite corre con `socket.socket` bloqueado | 1 (global) |
| 6.10 | Bitemporal | Corrección de una vela crea revisión; `read_as_of(watermark previo)` devuelve exactamente lo anterior; reescribir el mismo lote no cambia nada | 10 |
| 6.11 | Fronteras | `boundaries.py` respetado por todos los módulos | 1 |
| 6.12 | Eventos operativos | Formato y escritura | 3 |

Total estimado: **~120 casos**. Criterio: 100 % en verde en 3.12 y 3.13; la suite existente de la 2.1 sigue pasando sin cambios (313 pruebas según la auditoría correctiva).

Integración continua: la PR puede incluir un workflow de GitHub Actions **limitado a `market_radar/` y `tests/market_radar/`** (Python 3.12 y 3.13 + servicio PostgreSQL 16). Añadir un workflow es un archivo nuevo en `.github/`, pero cambia lo que corre en el repositorio, así que **se incluye solo si el propietario lo aprueba**; si no, la evidencia es la salida local adjunta a la PR.

## 7. Documentación

| Documento | Contenido |
|---|---|
| `docs/market-radar/foundation/DEVELOPER_GUIDE.md` | PostgreSQL local, variables, comandos de prueba y migración |
| `docs/market-radar/foundation/CONTRACTS.md` | Contratos de §4 con ejemplos y la batería de conformidad |
| `docs/market-radar/foundation/DATA_MODEL_I1.md` | Tablas, restricciones y decisiones (bitemporal, exclusión, volumen 38 dígitos) |
| `DECISION_LOG.md` | Nuevas entradas D-021… para las decisiones modificadas por `ARCHITECTURE_REVIEW` que el propietario apruebe |

## 8. Dependencias

| Dependencia | Tipo | Estado |
|---|---|---|
| Python 3.12 / 3.13, biblioteca estándar (`dataclasses`, `zoneinfo`, `decimal`, `uuid`, `hashlib`) | Ejecución | Ya disponibles |
| `psycopg[binary]==3.3.9` | Ejecución | **Ya está** en `requirements.txt`; no se toca |
| PostgreSQL 16 con extensión `btree_gist` | Pruebas | Local; en Neon **NO VERIFICADO** (no se usa en I-1) |
| `tzdata` | Solo si el sistema no tiene base de zonas | No se añade a `requirements.txt` en I-1 |
| Nuevas dependencias de terceros | — | **Ninguna** |

Dependencias de proceso: aprobación de las decisiones modificadas (ARCHITECTURE_REVIEW), autorización del propietario para empezar I-1, y cierre de la Fase 0 solo para **fusionar**.

## 9. Plan de reversión

| Situación | Reversión |
|---|---|
| Durante el desarrollo | Cerrar la PR y borrar la rama; nada más existe fuera de ella |
| Base de datos local | `python -m market_radar migrate down --to 0` (probado en 6.7); o borrar la base local |
| Si algún día se fusionara | Revertir el commit de fusión: solo contiene carpetas nuevas y ningún código de producción las importa (6.8), así que la 2.1 no cambia |
| Base remota | No aplica: I-1 nunca se conecta a Neon |

## 10. Estimación

| Bloque | Tamaño | Notas |
|---|---|---|
| Tipos, tiempo, errores, fronteras | S | |
| Registro (memoria + PG) y migración 0002 | M | Restricción de exclusión |
| Calendarios y migración 0004 | M | Cambios de hora |
| Contrato, proveedor sintético, conformidad | M | |
| Licencias y migración 0003 | S | |
| Velas bitemporales y migración 0005 | M | Lo más delicado |
| Reglas de calidad | S | Puras |
| Runner de migraciones | S | |
| Documentación | S | |
| **Total** | ≈ 2 semanas de trabajo con revisión | Varias PR pequeñas o una PR en borrador con commits por bloque |

## 11. Criterios de aceptación de I-1 (verificables)

1. Las ~120 pruebas pasan en Python 3.12 y 3.13 con PostgreSQL 16 local, y la suite de la 2.1 pasa sin cambios.
2. `git diff --stat release-2.1...` muestra solo archivos nuevos en las tres carpetas de §2.2 (y `.github/` si se aprobó).
3. La prueba de aislamiento (6.8) y la de red bloqueada (6.9) están en verde.
4. `migrate up`, `down` y `up` funcionan sobre una base vacía sin errores ni restos.
5. La prueba bitemporal reproduce exactamente una lectura anterior a una corrección.
6. Ningún archivo contiene claves, contraseñas, URLs de bases remotas ni datos de proveedores reales (búsqueda automática en la PR).
7. Documentación de §7 presente.

## 12. Lo que viene después (no autorizado)

I-2: auditoría de calidad por lotes, primer adaptador cripto **solo** tras resolver la licencia (F0-11), base de Neon separada, worker con `mr.jobs`. Cada uno con su propia solicitud de autorización.
