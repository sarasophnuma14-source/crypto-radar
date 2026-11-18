# Plan del primer incremento técnico (I-1) · Market Radar · v2

Fecha: 18-nov-2026. Estado: **propuesta corregida; no implementada.** No existe ninguna línea de código de Market Radar. Lo que este documento llama «probado en sandbox» son consultas SQL desechables ejecutadas en un PostgreSQL 16 local temporal para comprobar el diseño; no forman parte del repositorio ni de I-1.

> **Nombre.** El propietario lo llama «Fase 1». En `MULTI_ASSET_ROADMAP.md` la Fase 1 es el diseño y la Fase 2 el núcleo. Este incremento se llama **I-1** y es la primera entrega de la **Fase 2 (núcleo)** (CON-02).

## 0. Cambios respecto a v1

| Id | Sección | Cambio |
|---|---|---|
| INC-10 / D-021 | §5.3, §6.10 | La marca de agua deja de ser `MAX(recorded_at)`. Secuencia de escritura asignada bajo un candado de transacción; lecturas «as of» por secuencia |
| DEP-08 / D-022 | §5.1, §6.7 | `btree_gist` se instala explícitamente en la migración 0001, dentro del esquema `mr`, sin superusuario; prueba desde base PostgreSQL 16 vacía |
| RSK-10 / D-023 | §4.5, §5.2, §6.5 | Desaparece la variable `MARKET_RADAR_ENV`. Las licencias sintéticas solo pueden cubrir mercados ficticios, por restricción de base de datos; el proveedor sintético vive solo en `tests/` |
| INC-11 / D-024 | §4.4, §5.4 | Se conservan los **bytes originales** recibidos (`raw_payloads`), separados de la representación canónica (`candles`). Se elimina `raw_candles` con JSON «normalizado» |
| INC-03 / D-025 | §4.2, §5.2 | Fuentes primarias: prioridad, vigencia, exclusión de empates, reglas de respaldo y de ausencia de fuente |
| INC-12 / D-026 | §6.9 | La prueba «sin red» bloqueaba también el PostgreSQL local. Ahora permite solo socket Unix y loopback |
| INC-13 / D-026 | §3, §6.8 | Guardia de conexión: el código rechaza cualquier DSN que no sea local |
| JUS-04 | §10 | Estimación revisada con desglose de tareas y dependencias |

## 1. Objetivo y límites

**Objetivo:** construir el núcleo universal de activos y contratos, probado y aislado, sobre el que se apoyarán los mercados.

| Incluye | No incluye |
|---|---|
| Registro de mercados, bolsas, activos, instrumentos e identificadores con vigencia | Ningún proveedor real (ni comercial ni gratuito) |
| Contrato de proveedores; proveedor **sintético** determinista solo en `tests/` | Ninguna llamada de red; ninguna base remota (Neon, Render) |
| Modelo de licencias aplicado en código **y** en restricciones de base | Motores, indicadores, estados, score, señales |
| Fuentes por instrumento con prioridad y vigencia | Validación cruzada entre proveedores (I-2) |
| Calendarios: 24/7 real y calendario de tabla con datos ficticios | Calendarios reales de bolsas |
| Capa de bytes originales y capa canónica bitemporal de velas | Acciones corporativas, futuros, rollovers, series |
| Validadores puros de calidad del grupo I-1 de `DATA_QUALITY_TEST_PLAN` | Auditoría diaria, purga por retención (solo el campo) |
| Migraciones SQL versionadas con reversión | Worker, planificador, API, interfaz, Telegram, IA |
| Eventos operativos (formato y escritura) | Cualquier cambio en `radar/`, la 2.1 o producción |

## 2. Reglas de control de cambios

1. Rama nueva `claude/market-radar-i1`, creada desde `release-2.1`, PR **en borrador**, sin fusionar.
2. Solo se **añaden** archivos en `market_radar/`, `tests/market_radar/` y `docs/market-radar/foundation/`. Ningún archivo existente se modifica (comprobado con `git diff --name-status release-2.1...HEAD`: solo líneas `A` dentro de esas carpetas).
3. `radar/`, `web/`, `main.py`, `render.yaml`, `requirements.txt`, `ventas/` y `research/` quedan intactos.
4. Ninguna conexión a Neon ni a Render; el código lo impide (§3, guardia de conexión).
5. Nada de producción importa `market_radar` (prueba §6.8).
6. Fusionar exige: Fase 0 cerrada (CON-01) **y** autorización expresa del propietario.
7. Sin claves, contraseñas, DSN remotos ni datos de proveedores reales en ningún archivo (búsqueda automática, §11).

## 3. Arquitectura definitiva de I-1

```
market_radar/
  __init__.py                 versión del paquete
  __main__.py                 CLI: migrate up|down|status, selfcheck
  config.py                   ÚNICO módulo que lee el entorno: solo MARKET_RADAR_DSN
  core/
    types.py                  enums: AssetClass, InstrumentKind, Timeframe, QualityStatus, SessionKind, DataUse
    timeutil.py               Clock (protocolo), SystemClock, FixedClock, utilidades UTC
    errors.py                 jerarquía de errores del dominio
    canonical.py              codificación canónica y hash de una vela (§4.4)
  registry/
    models.py                 Market, Exchange, Asset, Instrument, Identifier, InstrumentSource
    repository.py             protocolo RegistryRepository
    memory.py                 implementación en memoria (misma batería de pruebas)
    postgres.py               implementación sobre psycopg
    sources.py                selección de fuente (§4.2), pura
  calendars/
    base.py                   protocolo MarketCalendar, dataclass Session
    continuous.py             Continuous24x7 (cierre diario 00:00 UTC)
    table.py                  TableCalendar (lee market_sessions)
  providers/
    contract.py               ProviderAdapter, ProviderDescriptor, RawPayload, Candle, CandleBatch, errores
    licensing.py              LicenseTerms, LicenseGuard (sin lectura de entorno)
  quality/
    rules.py                  DQ-DUP-01/02, DQ-BAR-01…05, DQ-SES-01…04, DQ-STALE-04, DQ-SYM-01…03, DQ-EXP-01
    report.py                 resultado por lote: aceptado / rechazado / marcado, con motivo
  storage/
    connect.py                guardia de conexión: solo socket Unix, localhost, 127.0.0.1, ::1
    migrate.py                runner (checksum, up/down, candado de migración)
    ledger.py                 begin_write / watermark (§5.3)
    raw.py                    escritura de bytes originales
    candles.py                escritura canónica, lectura vigente y as-of
    ops.py                    eventos operativos
  boundaries.py               grafo de dependencias permitido (lo usa la prueba de fronteras)
  migrations/
    0001_base            0002_ledger          0003_registry
    0004_providers_licenses                   0005_sources
    0006_calendars       0007_raw_payloads    0008_candles
    0009_ops_events                           (cada una .up.sql / .down.sql)
tests/market_radar/
  fixtures/synthetic_provider.py   SyntheticProvider determinista (semilla) + licencias sintéticas
  fixtures/series.py               series y calendarios ficticios de DATA_QUALITY_TEST_PLAN §2
  fixtures/pg.py                   crea y destruye una base temporal por módulo de prueba
  contract/conformance.py          batería que todo ProviderAdapter debe pasar
  test_*.py                        ver §6
docs/market-radar/foundation/
  DEVELOPER_GUIDE.md  CONTRACTS.md  DATA_MODEL_I1.md
```

**Fronteras (comprobadas por la prueba 6.11):**

| Módulo | Puede importar |
|---|---|
| `core` | biblioteca estándar |
| `registry`, `calendars`, `providers` | `core` |
| `quality` | `core`, `providers.contract`, `calendars` |
| `storage` | todo lo anterior + `psycopg` |
| `__main__`, `config` | `storage`, `core` |
| Cualquiera | **nunca** `radar`, `web`, `research`, `ventas`, `main`, `tests` |

Terceros permitidos: solo `psycopg` (ya en `requirements.txt`). Lectura del entorno (`os.environ`, `os.getenv`): solo en `config.py`.

**Guardia de conexión (INC-13):** `storage/connect.py` analiza el DSN y rechaza cualquier host que no sea socket Unix, `localhost`, `127.0.0.1` o `::1`, antes de abrir la conexión. No hay opción para saltarla en I-1; abrirla a una base remota exigirá un cambio de código revisado en I-2.

## 4. Contratos de interfaces

Todas las estructuras son `dataclass(frozen=True, slots=True)`; todos los tiempos son `datetime` con zona UTC (se rechaza cualquier tiempo sin zona).

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

### 4.2 Registro y fuentes (INC-03)

```python
@dataclass(frozen=True, slots=True)
class InstrumentSource:
    instrument_id: UUID; provider_id: str; priority: int      # 1 = primaria
    valid_from: datetime; valid_to: datetime | None           # intervalo semiabierto [from, to)
    reason: str                                               # obligatorio

@dataclass(frozen=True, slots=True)
class SourceDecision:
    provider_id: str | None; priority: int | None
    status: Literal["PRIMARY", "FALLBACK", "NO_SOURCE"]; skipped: tuple[tuple[str, str], ...]  # (proveedor, motivo)

class RegistryRepository(Protocol):
    def add_asset(self, a: Asset) -> None: ...
    def add_instrument(self, i: Instrument) -> None: ...          # valida kind/expiry/tradable
    def add_identifier(self, ident: Identifier) -> None: ...       # falla si solapa vigencias
    def resolve(self, scheme: str, value: str, at: datetime, provider_id: str | None = None) -> Instrument: ...
    def sources(self, instrument_id: UUID, at: datetime, as_of: int | None = None) -> list[InstrumentSource]: ...

def select_source(candidates: list[InstrumentSource], eligible: Callable[[str], str | None]) -> SourceDecision: ...
    # eligible(provider_id) devuelve None si es elegible o el motivo de exclusión
```

**Reglas de selección de fuente** (función pura, determinista):

1. **Candidatas:** filas de `instrument_sources` cuya vigencia contiene el instante de la vela (`valid_from ≤ bar_start < valid_to`) y que son visibles en la marca de agua de lectura (`as_of`, §5.3).
2. **Elegibilidad:** una candidata es elegible si (a) el `LicenseGuard` concede `STORE` (y `DISPLAY` cuando la lectura es para mostrar) para el mercado del instrumento en el instante de evaluación, y (b) el proveedor no está en cuarentena en ese instante (`mr.provider_quarantine`, misma semántica bitemporal). Motivos de exclusión: `no_license`, `license_expired`, `use_not_allowed`, `quarantined`.
3. **Orden:** prioridad ascendente. **No hay desempates en tiempo de ejecución**: la base impide dos filas vigentes con la misma prioridad o el mismo proveedor solapadas para un instrumento (restricciones de exclusión, §5.2).
4. **Resultado:** la primera elegible. Si es la de prioridad mínima entre las candidatas → `PRIMARY`. Si no → `FALLBACK`: la vela se marca `DEGRADED` con motivo `source_fallback` y se escribe un evento operativo.
5. **Sin fuente válida:** si no hay candidatas o ninguna es elegible → `NO_SOURCE`. La vela esperada se marca `MISSING`; no se muestra nada; no se toma dato de un proveedor que no esté en `instrument_sources`.
6. **Sin mezcla silenciosa:** las velas se guardan por proveedor. Toda lectura de serie devuelve el proveedor de cada vela; un cambio de proveedor dentro de la ventana pedida se marca `source_switch` para que los motores futuros no calculen a través de él sin saberlo.
7. **Cambios de prioridad:** nunca se editan filas; se cierra la vigente (`superseded_seq`) y se inserta otra. La configuración de fuentes también es reproducible en una marca de agua.

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

### 4.4 Proveedores y datos crudos (INC-11)

```python
@dataclass(frozen=True, slots=True)
class RawPayload:
    body: bytes                    # exactamente los bytes entregados al adaptador, tras decodificar el transporte (gzip/chunked)
    content_type: str; transport_encoding: str | None    # p. ej. "gzip": cómo llegó, para auditoría
    request_fingerprint: str       # método + endpoint + parámetros ordenados, solo los declarados no secretos
    requested_at: datetime; received_ts: datetime; status: int | None

@dataclass(frozen=True, slots=True)
class Candle:
    instrument_id: UUID; timeframe: Timeframe; bar_start: datetime; bar_end: datetime
    open: Decimal; high: Decimal; low: Decimal; close: Decimal; volume: Decimal
    is_closed: bool; source_ts: datetime
    payload_index: int; locator: str   # qué RawPayload y dónde dentro de él (p. ej. puntero JSON "/values/17")

@dataclass(frozen=True, slots=True)
class CandleBatch:
    provider_id: str; adapter_version: str
    adjusted: bool; currency: str
    payloads: tuple[RawPayload, ...]; candles: tuple[Candle, ...]; next_cursor: str | None

@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    provider_id: str; version: str; asset_classes: frozenset[AssetClass]
    timeframes: frozenset[Timeframe]; max_history_days: int | None
    declared_rate_limit_per_min: int | None; requires_key: bool
    secret_params: frozenset[str]      # nombres de parámetros que nunca entran en request_fingerprint

class ProviderAdapter(Protocol):
    descriptor: ProviderDescriptor
    def health(self) -> ProviderHealth: ...
    def list_instruments(self, market_id: str) -> Iterator[InstrumentMeta]: ...
    def candles(self, ref: ProviderSymbol, tf: Timeframe, start: datetime, end: datetime,
                cursor: str | None = None) -> CandleBatch: ...
    def reparse(self, payload: RawPayload) -> tuple[Candle, ...]: ...   # mismo resultado que candles() para esos bytes

# Errores: ProviderError > RateLimited(retry_after_s) | NotEntitled | NotFound
#          | ProviderUnavailable | InvalidResponse | ContractViolation
```

**Original frente a canónico:**

| | Original (`mr.raw_payloads`) | Canónico (`mr.candles`) |
|---|---|---|
| Qué es | Los bytes recibidos, sin reinterpretar (ni `jsonb`, que reordena claves y elimina duplicados) | Una vela por fila con tipos fijos: UUID, `timestamptz` UTC, `numeric` |
| Identidad | `body_sha256` = SHA-256 de los bytes | `canonical_sha256` = SHA-256 de la codificación canónica |
| Cambia si | Cambia cualquier byte (espacios, orden de claves) | Cambia un valor de negocio |
| Uso | Auditoría, re-proceso con otra versión de adaptador, disputa con el proveedor | Lecturas, calidad, motores futuros |
| Retención | `retention_until` según `max_storage_days` de la licencia; la purga (I-2) borra `body` y deja la huella | Igual, por licencia |

**Codificación canónica** (`core/canonical.py`, versión `c1`): texto UTF-8 con los campos `instrument_id|timeframe|bar_start|bar_end|adjusted|open|high|low|close|volume|is_closed`; tiempos ISO-8601 UTC con microsegundos y sufijo `Z`; decimales sin exponente, sin ceros finales, `-0` → `0`; booleanos `t`/`f`. La versión de codificación se guarda en cada fila.

**Garantía de re-proceso:** `adapter.reparse(payload)` sobre los bytes guardados produce exactamente las mismas velas canónicas (mismo `canonical_sha256`) que la ingesta original con la misma `adapter_version`. Es parte de la batería de conformidad.

### 4.5 Licencias (RSK-10)

```python
@dataclass(frozen=True, slots=True)
class LicenseTerms:
    license_id: UUID; provider_id: str; is_synthetic: bool; scope_markets: frozenset[str]
    allowed_uses: frozenset[DataUse]; max_storage_days: int | None
    display_delay_min: int | None; attribution: str | None
    valid_from: datetime; valid_until: datetime | None; contract_ref: str | None

class LicenseGuard:
    def __init__(self, terms_source: Callable[[str], list[LicenseTerms]], clock: Clock): ...
    def require(self, provider_id: str, market_id: str, use: DataUse) -> LicenseTerms: ...
```

Reglas, sin interruptores:

1. **Sin licencia registrada no hay nada permitido**, ni siquiera `RESEARCH`.
2. **No existe variable de entorno, bandera ni parámetro** que cambie el comportamiento del `LicenseGuard`. Se elimina `MARKET_RADAR_ENV` de v1.
3. Una licencia sintética (`is_synthetic`) **solo puede cubrir mercados ficticios** (`market_id` con prefijo `zz-test-`), y un mercado ficticio solo puede estar cubierto por licencias sintéticas. Se aplica tres veces: en el `LicenseGuard`, en restricciones `CHECK` y claves foráneas compuestas de la base (§5.2), y en la prueba 6.5.
4. El proveedor sintético y sus licencias viven **solo en `tests/market_radar/fixtures/`**. El paquete `market_radar` no los contiene ni puede importarlos (prueba de fronteras).

Consecuencia: aunque una licencia sintética llegara a una base de producción futura, no autorizaría ningún mercado real, porque la base rechaza la combinación. Probado en sandbox (18-nov): las cinco combinaciones prohibidas fueron rechazadas por PostgreSQL 16.

### 4.6 Almacenamiento de velas

```python
class CandleStore:
    def write(self, batch: CandleBatch, guard: LicenseGuard, market_id: str) -> WriteResult: ...
        # en una transacción: 1) guard.require(STORE)  2) reglas de calidad  3) seq = begin_write('candles')
        # 4) raw_payloads (solo inserción)  5) candles: inserta revisión nueva o nada si canonical_sha256 es igual;
        #    cierra la revisión anterior con superseded_seq = seq   6) commit
    def watermark(self) -> int: ...                                   # §5.3; un entero, no una hora
    def read_current(self, instrument_id, provider_id, tf, start, end) -> list[StoredCandle]: ...
    def read_as_of(self, watermark: int, instrument_id, provider_id, tf, start, end) -> list[StoredCandle]: ...
```

## 5. Modelo de datos y migraciones

Esquema `mr`. Cada migración tiene `.up.sql` y `.down.sql`; `down` deja la base exactamente como antes de `up`.

| Migración | Objetos | Restricciones clave |
|---|---|---|
| 0001_base | esquema `mr`; extensión `btree_gist`; `mr.schema_migrations` | ver §5.1 |
| 0002_ledger | secuencia `mr.write_seq`, `mr.write_log`, función `mr.begin_write(kind)`, función de disparador `mr.require_current_write()` | ver §5.3 |
| 0003_registry | `markets`, `exchanges`, `assets`, `instruments`, `asset_identifiers` | `markets.is_fictional = (market_id LIKE 'zz-test-%')`; `CHECK (kind <> 'index' OR NOT tradable)`; `CHECK (kind <> 'future' OR expiry IS NOT NULL)`; identificadores con `EXCLUDE USING gist (scheme WITH =, value WITH =, (coalesce(provider_id,'')) WITH =, tstzrange(valid_from, valid_to) WITH &&)` |
| 0004_providers_licenses | `providers`, `provider_licenses`, `license_markets`, `provider_quarantine` | ver §5.2 |
| 0005_sources | `instrument_sources` | ver §5.2 |
| 0006_calendars | `market_calendars`, `market_sessions` | PK (`calendar_id`, `session_date`, `kind`); `close_ts > open_ts` |
| 0007_raw_payloads | `raw_payloads` | ver §5.4 |
| 0008_candles | `candles` | ver §5.5 |
| 0009_ops_events | `ops_events` | `at`, `kind`, `detail jsonb`; índice por `at` |

Orden de `down`: 0009 → 0001. El libro de escrituras (0002) va antes de cualquier tabla versionada; cada migración posterior crea en sus tablas el disparador que exige `begin_write`.

### 5.1 Base y `btree_gist` (DEP-08)

```sql
-- 0001_base.up.sql (extracto)
CREATE SCHEMA mr;
CREATE TABLE mr.schema_migrations (
  version int PRIMARY KEY, name text NOT NULL, checksum bytea NOT NULL CHECK (octet_length(checksum) = 32),
  applied_at timestamptz NOT NULL DEFAULT clock_timestamp(), applied_by text NOT NULL DEFAULT current_user,
  notes jsonb NOT NULL DEFAULT '{}'
);
-- btree_gist: necesaria para las restricciones de exclusión con columnas escalares (INC-01, INC-03).
-- Si ya existe en otro esquema se usa la existente y se anota; si no, se instala dentro de mr.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'btree_gist') THEN
    PERFORM set_config('mr.btree_gist_preexisting', 'true', true);
  ELSE
    CREATE EXTENSION btree_gist WITH SCHEMA mr;
    PERFORM set_config('mr.btree_gist_preexisting', 'false', true);
  END IF;
END $$;
```

| Hecho | Evidencia |
|---|---|
| `btree_gist` es extensión **confiable** en PostgreSQL 16: la instala el dueño de la base sin superusuario | Archivo de control del paquete Ubuntu 16.15 (`trusted = true`); probado en sandbox con un rol no superusuario dueño de la base: `CREATE EXTENSION` correcto, versión 1.7 |
| Instalada en el esquema `mr`, las restricciones de exclusión funcionan aunque `mr` no esté en `search_path` | Probado en sandbox con `search_path = pg_catalog` |
| `DROP SCHEMA mr CASCADE` elimina la extensión instalada en `mr` | Probado en sandbox: `pg_extension` vuelve a 0 filas |
| Disponibilidad en Neon | **NO VERIFICADO** (I-1 no usa Neon) |

El runner lee `mr.btree_gist_preexisting` en la misma transacción y lo guarda en `schema_migrations.notes`.

`0001_base.down.sql`: si `notes.btree_gist_preexisting = false`, `DROP SCHEMA mr CASCADE` (elimina también la extensión); si era preexistente, `DROP SCHEMA mr` sin `CASCADE` sobre la extensión, que queda intacta. El runner se niega a ejecutar `down` de 0001 si quedan objetos fuera de los creados por las migraciones (comparación con el catálogo).

Requisitos que el runner comprueba antes de migrar: `server_version_num` entre 160000 y 169999 (si no, error); el rol actual **no** es superusuario (si lo es, error: obliga a probar con privilegios realistas); candado `pg_advisory_lock` de migración para que dos procesos no migren a la vez.

### 5.2 Licencias, mercados ficticios y fuentes (RSK-10, INC-03)

```sql
-- 0003: markets.is_fictional  CHECK (is_fictional = (market_id LIKE 'zz-test-%')), UNIQUE (market_id, is_fictional)
-- 0004
CREATE TABLE mr.provider_licenses (
  license_id uuid PRIMARY KEY, provider_id text NOT NULL REFERENCES mr.providers,
  is_synthetic boolean NOT NULL,
  allowed_uses text[] NOT NULL CHECK (allowed_uses <@ ARRAY['store','display','derived_public','alert','export','research','staging']),
  max_storage_days int CHECK (max_storage_days > 0), display_delay_min int, attribution text,
  valid_from timestamptz NOT NULL, valid_until timestamptz CHECK (valid_until > valid_from),
  contract_ref text,
  CHECK (is_synthetic = (provider_id LIKE 'synthetic.%')),
  CHECK (is_synthetic OR contract_ref IS NOT NULL),        -- una licencia real exige referencia de contrato
  UNIQUE (license_id, is_synthetic)
);
CREATE TABLE mr.license_markets (
  license_id uuid NOT NULL, is_synthetic boolean NOT NULL,
  market_id text NOT NULL, market_is_fictional boolean NOT NULL,
  PRIMARY KEY (license_id, market_id),
  FOREIGN KEY (license_id, is_synthetic) REFERENCES mr.provider_licenses (license_id, is_synthetic),
  FOREIGN KEY (market_id, market_is_fictional) REFERENCES mr.markets (market_id, is_fictional),
  CHECK (is_synthetic = market_is_fictional)               -- sintética ⇔ mercado ficticio
);
-- 0005
CREATE TABLE mr.instrument_sources (
  instrument_id uuid NOT NULL REFERENCES mr.instruments, provider_id text NOT NULL REFERENCES mr.providers,
  priority smallint NOT NULL CHECK (priority BETWEEN 1 AND 9),
  valid_from timestamptz NOT NULL, valid_to timestamptz CHECK (valid_to > valid_from),
  reason text NOT NULL CHECK (length(reason) > 0),
  write_seq bigint NOT NULL REFERENCES mr.write_log, superseded_seq bigint REFERENCES mr.write_log,
  CHECK (superseded_seq IS NULL OR superseded_seq > write_seq),
  EXCLUDE USING gist (instrument_id WITH =, priority WITH =, tstzrange(valid_from, valid_to) WITH &&)
    WHERE (superseded_seq IS NULL),                         -- sin empates de prioridad
  EXCLUDE USING gist (instrument_id WITH =, provider_id WITH =, tstzrange(valid_from, valid_to) WITH &&)
    WHERE (superseded_seq IS NULL)                          -- un proveedor una sola vez por intervalo
);
```

Además, un disparador `BEFORE INSERT` en `raw_payloads` y `candles` comprueba que la licencia de la fila cubre el mercado del instrumento (`license_markets`). Es la misma regla del `LicenseGuard`, aplicada por la base para que un error de código no pueda saltársela.

### 5.3 Bitemporalidad bajo escrituras concurrentes (INC-10)

**Problema demostrado.** Con `recorded_at = clock_timestamp()` y marca de agua `MAX(recorded_at)`, una transacción que empezó antes pero confirma después inserta filas con hora **anterior** a una marca de agua ya leída. Releer «as of» esa marca devuelve otra cosa. Sandbox 18-nov, PostgreSQL 16.15, 8 escritores concurrentes con 25 lotes cada uno y 60 lecturas: **11 de 60** marcas de agua devolvieron un resultado distinto al releerlas. Un caso mínimo (una escritura lenta y una rápida) lo reproduce siempre.

**Diseño.**

```sql
-- 0002_ledger (extracto)
CREATE SEQUENCE mr.write_seq;
CREATE TABLE mr.write_log (
  write_seq bigint PRIMARY KEY, kind text NOT NULL, started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  committed_by text NOT NULL DEFAULT current_user, batch_ref text
);
CREATE FUNCTION mr.begin_write(p_kind text) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE s bigint;
BEGIN
  IF current_setting('mr.write_seq', true) IS NOT NULL AND current_setting('mr.write_seq', true) <> '' THEN
    RAISE EXCEPTION 'begin_write ya llamado en esta transacción';
  END IF;
  PERFORM pg_advisory_xact_lock(hashtext('mr.write'));    -- un escritor a la vez, hasta commit o rollback
  s := nextval('mr.write_seq');                             -- se asigna DESPUÉS de tener el candado
  INSERT INTO mr.write_log (write_seq, kind) VALUES (s, p_kind);
  PERFORM set_config('mr.write_seq', s::text, true);        -- local a la transacción
  RETURN s;
END $$;
-- Disparador en candles, instrument_sources y raw_payloads: NEW.write_seq (y superseded_seq si cambia)
-- debe ser igual a current_setting('mr.write_seq'); si no, error. Nadie escribe sin pasar por begin_write.
```

- **Escritura:** toda transacción que escribe datos versionados llama primero a `mr.begin_write`, que toma un candado de transacción y luego asigna la secuencia. El candado se libera al confirmar o deshacer.
- **Por qué funciona:** la secuencia se asigna con el candado tomado y el candado dura hasta el final de la transacción, así que el orden de secuencia es el orden de confirmación. Cuando un lector ve confirmada la secuencia *W*, todas las menores ya están confirmadas o deshechas (los números deshechos dejan huecos, que no afectan porque no tienen filas). PostgreSQL libera los candados de transacción después de que el commit es visible; esto se apoya en el orden interno de `CommitTransaction` (**no documentado como garantía en el manual**), por eso la prueba 6.10 lo comprueba con concurrencia real en cada ejecución.
- **Marca de agua:** `SELECT max(write_seq) FROM mr.write_log`, leída en la misma transacción `REPEATABLE READ` que los datos. Es un entero, no una hora. `recorded_at` se conserva solo como dato informativo.
- **Lectura as-of(W):** `write_seq ≤ W AND (superseded_seq IS NULL OR superseded_seq > W)`.
- **Corrección de una vela:** en la misma transacción se inserta la revisión nueva con `write_seq = s` y se pone `superseded_seq = s` en la anterior. Es atómico.
- **Evidencia en sandbox:** el mismo ensayo de 8 escritores y 60 lecturas con este diseño dio **0 de 60** relecturas distintas.
- **Costo:** las escrituras versionadas se serializan. Con lotes de cientos o miles de velas cada escritura dura milisegundos; suficiente para I-1 e I-2. Revisión si la espera del candado supera 50 ms p95 (se mide en `ops_events`). Alternativa entonces: escribir sin candado en tablas de preparación y publicar con una transacción corta bajo el candado.

### 5.4 Bytes originales (INC-11)

```sql
-- 0007_raw_payloads (extracto)
CREATE TABLE mr.raw_payloads (
  payload_id bigserial PRIMARY KEY,
  provider_id text NOT NULL REFERENCES mr.providers,
  license_id uuid NOT NULL REFERENCES mr.provider_licenses,
  adapter_version text NOT NULL,
  request_fingerprint text NOT NULL,         -- sin parámetros secretos (descriptor.secret_params)
  requested_at timestamptz NOT NULL, received_ts timestamptz NOT NULL,
  http_status int, content_type text NOT NULL, transport_encoding text,
  body bytea,                                 -- bytes exactos; NULL solo tras purga
  body_sha256 bytea NOT NULL CHECK (octet_length(body_sha256) = 32),
  body_size int NOT NULL CHECK (body_size BETWEEN 0 AND 8388608),   -- 8 MiB; más grande → ContractViolation
  retention_until timestamptz,                -- received_ts + max_storage_days de la licencia
  purged_at timestamptz,
  write_seq bigint NOT NULL REFERENCES mr.write_log,
  CHECK ((body IS NULL) = (purged_at IS NOT NULL)),
  CHECK (body IS NULL OR octet_length(body) = body_size)
);
```

La aplicación calcula `body_sha256` y la base comprueba el tamaño. Una prueba compara byte a byte lo guardado con lo recibido, incluidos espacios, orden de claves, claves duplicadas y números como `1.10` o `1e-7`, que `jsonb` alteraría.

### 5.5 Velas canónicas

```sql
-- 0008_candles (extracto)
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
  payload_id    bigint NOT NULL REFERENCES mr.raw_payloads,
  locator       text NOT NULL,
  canonical_version text NOT NULL,            -- 'c1'
  canonical_sha256  bytea NOT NULL CHECK (octet_length(canonical_sha256) = 32),
  adapter_version   text NOT NULL,
  license_id    uuid NOT NULL REFERENCES mr.provider_licenses,
  quality_status text NOT NULL,
  write_seq     bigint NOT NULL REFERENCES mr.write_log,
  superseded_seq bigint REFERENCES mr.write_log,
  recorded_at   timestamptz NOT NULL DEFAULT clock_timestamp(),   -- informativo; no se usa para reproducir
  CHECK (low <= LEAST(open, close) AND GREATEST(open, close) <= high),
  CHECK (low > 0 AND volume >= 0 AND bar_end > bar_start),
  CHECK (superseded_seq IS NULL OR superseded_seq > write_seq)
);
CREATE UNIQUE INDEX candles_current ON mr.candles
  (instrument_id, provider_id, timeframe, bar_start, adjusted) WHERE superseded_seq IS NULL;
CREATE INDEX candles_asof ON mr.candles
  (instrument_id, provider_id, timeframe, bar_start, write_seq);
```

`numeric(38,10)` para volumen (tokens con suministros de 10¹⁵ unidades pueden superar 28 dígitos).

## 6. Pruebas

Marco: `unittest` (el de la suite actual). Python 3.12 (producción) y 3.13. PostgreSQL 16 local vía `MARKET_RADAR_TEST_DSN` (solo local, la guardia lo comprueba); las pruebas de PostgreSQL **fallan**, no se omiten, si falta la variable. Cada módulo de prueba crea una base nueva desde `template0` con un rol **no superusuario** con `CREATEDB` y la borra al terminar.

| # | Grupo | Qué demuestra | Casos aprox. |
|---|---|---|---|
| 6.1 | Tipos, tiempo, canónico | Tiempos sin zona rechazados; alineación; codificación canónica estable (mismos valores con distinta escala decimal → mismo hash) | 14 |
| 6.2 | Registro (memoria y PG, misma batería) | Altas, validaciones, resolución con fecha, vigencias sin solape (DQ-SYM-01…03) | 20 |
| 6.3 | Fuentes primarias | Primaria; respaldo por licencia vencida, uso no permitido y cuarentena; `NO_SOURCE`; empate de prioridad rechazado por la base; mismo proveedor solapado rechazado; límites semiabiertos; cambio de prioridad reproducible as-of; `source_switch` | 16 |
| 6.4 | Calendarios | 24/7; calendario ficticio con festivo, media sesión y cambios de hora de EE. UU. y Europa; `expected_bars` (DQ-SES-01…04, DQ-STALE-04) | 15 |
| 6.5 | Licencias | Sin términos → `NotEntitled`; vencidas; uso no incluido; sintética sobre mercado real rechazada por el `LicenseGuard` **y** por la base (5 combinaciones); real sobre mercado ficticio rechazada; real sin `contract_ref` rechazada; análisis estático: ningún `os.environ`/`getenv` fuera de `config.py` y ninguna lectura de entorno en `licensing.py` | 14 |
| 6.6 | Contrato de proveedores | El sintético pasa la batería; uno defectuoso a propósito la falla en cada punto; `reparse` reproduce el `canonical_sha256` | 16 |
| 6.7 | Migraciones en PostgreSQL 16 vacío | `up` desde base recién creada sin superusuario; `btree_gist` instalada en `mr`; catálogo esperado (tablas, restricciones por nombre); `down` hasta vacío sin restos (esquema y extensión ausentes); `up` otra vez; variante con `btree_gist` preexistente (queda tras `down`); checksum alterado → error; dos procesos migrando a la vez → uno espera; versión de servidor distinta de 16 → error; rol superusuario → error | 12 |
| 6.8 | Aislamiento de la 2.1 | Nada en `market_radar/` importa `radar/`, `web/`, `research/`, `main`; nada de eso importa `market_radar`; `git diff --name-status` contra la base solo con archivos nuevos en las carpetas permitidas | 4 |
| 6.9 | Sin red | La suite corre con un bloqueo de sockets que solo permite socket Unix y direcciones de loopback; `getaddrinfo` de nombres no locales falla; prueba de control: conectar a `192.0.2.1:443` (dirección de documentación) lanza error | 3 |
| 6.10 | Bitemporal y concurrencia | Corrección crea revisión; `read_as_of(W)` reproduce exactamente lo anterior; reescribir el mismo lote no cambia nada; escritura sin `begin_write` rechazada por disparador; `begin_write` dos veces en la misma transacción rechazada; **ensayo concurrente**: 8 escritores × 25 lotes con pausas aleatorias dentro de la transacción y un lector que guarda (W, hash del resultado) 60 veces; al final, releer cada W da el mismo hash en 60/60; **control negativo**: el mismo ensayo con `MAX(recorded_at)` debe mostrar al menos una diferencia (demuestra que la prueba detecta el fallo) | 12 |
| 6.11 | Fronteras | Grafo de importaciones dentro del permitido; terceros solo `psycopg`; `market_radar` no importa `tests` | 3 |
| 6.12 | Datos crudos | Bytes guardados idénticos a los recibidos (espacios, orden de claves, duplicados, `1.10`, `1e-7`); `request_fingerprint` sin parámetros secretos; tamaño > 8 MiB rechazado; `body` nulo solo con `purged_at` | 8 |
| 6.13 | Guardia de conexión | DSN con host remoto, con IP pública o con nombre de Neon rechazados antes de conectar; socket Unix y loopback aceptados | 5 |
| 6.14 | Eventos operativos | Formato y escritura | 3 |

Total estimado: **~145 casos**. La suite existente de la 2.1 sigue pasando sin cambios (313 pruebas según la auditoría correctiva).

Integración continua: un workflow de GitHub Actions limitado a `market_radar/` y `tests/market_radar/` (Python 3.12 y 3.13 + servicio PostgreSQL 16) **solo si el propietario lo aprueba**; si no, la evidencia es la salida local adjunta a la PR.

## 7. Documentación

| Documento | Contenido |
|---|---|
| `docs/market-radar/foundation/DEVELOPER_GUIDE.md` | PostgreSQL 16 local con rol no superusuario, variables, comandos de prueba y migración |
| `docs/market-radar/foundation/CONTRACTS.md` | Contratos de §4 con ejemplos, batería de conformidad, codificación canónica `c1` |
| `docs/market-radar/foundation/DATA_MODEL_I1.md` | Tablas y restricciones; bitemporalidad por secuencia; licencias sintéticas; fuentes |
| `DECISION_LOG.md` | Pasar D-021…D-026 de «Propuesta» a «Aprobada» si el propietario las aprueba |

## 8. Dependencias

| Dependencia | Tipo | Estado |
|---|---|---|
| Python 3.12 / 3.13, biblioteca estándar | Ejecución | Ya disponibles |
| `psycopg[binary]==3.3.9` | Ejecución | **Ya está** en `requirements.txt`; no se toca |
| PostgreSQL 16 local con `btree_gist` (paquete `postgresql-contrib` o equivalente) | Pruebas | Verificado en sandbox con 16.15 |
| `tzdata` | Solo si el sistema no tiene base de zonas | No se añade a `requirements.txt` |
| Nuevas dependencias de terceros | — | **Ninguna** |

## 9. Estrategia de reversión

| Situación | Reversión |
|---|---|
| Durante el desarrollo | Cerrar la PR y borrar la rama; nada existe fuera de ella |
| Base de datos local | `python -m market_radar migrate down --to 0` (probado en 6.7), o borrar la base local |
| Una migración concreta | `down` de esa versión; el runner no permite saltar versiones |
| Si algún día se fusionara | Revertir el commit de fusión: solo carpetas nuevas que ningún código de producción importa (6.8); la 2.1 no cambia |
| Base remota | No aplica: la guardia de conexión impide conectarse a una |

## 10. Desglose de tareas, dependencias y estimación

Días = días de trabajo con revisión, para una persona con asistencia de IA. SUPUESTO: no hay base histórica de velocidad para este tipo de código en el proyecto.

| Tarea | Contenido | Depende de | Días |
|---|---|---|---|
| T01 | Tipos, tiempo, errores, canónico, `config`, `boundaries`, pruebas 6.1, 6.11 | — | 1,0 |
| T02 | Guardia de conexión y fixture de PostgreSQL por módulo; 6.13 | T01 | 0,5 |
| T03 | Bloqueo de red en la suite; 6.9 | T01 | 0,5 |
| T04 | Runner de migraciones y 0001 con `btree_gist`; 6.7 parcial | T02 | 1,5 |
| T05 | Libro de escrituras 0002 (`begin_write`, función de disparador) | T04 | 1,0 |
| T06 | Registro en memoria y PG, 0003; 6.2 | T05 | 2,0 |
| T07 | Licencias 0004 y `LicenseGuard`; 6.5 | T06 | 1,5 |
| T08 | Fuentes 0005 y `select_source`; 6.3 | T05, T07 | 1,5 |
| T09 | Calendarios 0006; 6.4 | T06 | 1,5 |
| T10 | Contrato, `RawPayload`, proveedor sintético en `tests/`, batería de conformidad; 6.6 | T01, T07 | 1,5 |
| T11 | Reglas de calidad; DQ del grupo I-1 | T09, T10 | 1,0 |
| T12 | Bytes originales 0007 y velas 0008, `CandleStore`; 6.10, 6.12 | T05, T08, T10, T11 | 2,5 |
| T13 | Eventos operativos 0009; 6.14; 6.7 completa (up/down de todo) | T12 | 0,5 |
| T14 | Aislamiento 6.8, documentación de §7, evidencia en la PR | T13 | 1,0 |
| **Total** | | | **≈ 17 días ≈ 3,5 semanas** (rango 14–21) |

Ruta crítica: T01 → T02 → T04 → T05/T06 → T07 → T08 → T12 → T13 → T14. v1 estimaba ≈ 2 semanas; el aumento viene del libro de escrituras, los bytes originales, las restricciones de licencias y las fuentes.

## 11. Criterios objetivos de aceptación

| # | Criterio | Cómo se comprueba |
|---|---|---|
| 1 | Las ~145 pruebas pasan en Python 3.12 y 3.13 con PostgreSQL 16 local; 0 omitidas | Salida de `python -m unittest discover tests/market_radar -v` en ambas versiones |
| 2 | La suite de la 2.1 pasa sin cambios | Misma cifra de pruebas que en `release-2.1` |
| 3 | Solo archivos nuevos en las carpetas permitidas | `git diff --name-status release-2.1...HEAD` solo con `A` en `market_radar/`, `tests/market_radar/`, `docs/market-radar/foundation/` (y `.github/` si se aprobó) |
| 4 | `up` → `down` → `up` desde una base PostgreSQL 16 vacía, con rol no superusuario, sin restos | Prueba 6.7 y comparación de catálogo antes/después |
| 5 | Reproducción bitemporal bajo concurrencia | Prueba 6.10: 60/60 relecturas idénticas y control negativo con al menos 1 diferencia |
| 6 | Ninguna licencia sintética cubre un mercado real | Prueba 6.5: 5 combinaciones rechazadas por la base y por el `LicenseGuard` |
| 7 | Ningún interruptor de entorno | Prueba 6.5 (análisis estático): una sola lectura de entorno, en `config.py`, de `MARKET_RADAR_DSN` |
| 8 | Bytes originales idénticos y re-proceso exacto | Pruebas 6.6 y 6.12 |
| 9 | Selección de fuente determinista sin empates | Prueba 6.3 |
| 10 | Sin red y sin bases remotas | Pruebas 6.9 y 6.13 |
| 11 | Sin secretos | Búsqueda en la PR de patrones de clave, `postgres://` con host no local, `neon.tech`, `render.com` |
| 12 | Documentación de §7 presente | Revisión de la PR |

## 12. Lo que viene después (no autorizado)

I-2: auditoría de calidad por lotes, purga por retención, primer adaptador cripto **solo** tras resolver la licencia (F0-11), base de Neon separada, worker con `mr.jobs`. Cada uno con su propia solicitud de autorización.
