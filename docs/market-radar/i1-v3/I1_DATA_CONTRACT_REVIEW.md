# I-1 v3 · Contratos de datos corregidos

Fecha: 18-nov-2026. Resuelve V3-07, V3-08, V3-09, V3-10, V3-13, V3-14, V3-20. Ilustrativo: no es código.

## 1. Criterio

Un contrato universal no puede excluir en silencio un mercado aprobado (cripto, acciones, ETF, forex, oro y plata, índices, petróleo y gas, agrícolas). Las restricciones de la base solo expresan lo que es cierto **para todos**; lo específico de cada mercado va en atributos del instrumento y en reglas de calidad condicionadas.

## 2. Instrument

| Campo | Tipo | Justificación |
|---|---|---|
| `instrument_id` | uuid | Identidad estable |
| `namespace` | `real`/`synthetic` | Frontera de datos sintéticos (`I1_SECURITY_THREAT_MODEL.md` §4) |
| `asset_id` | uuid | Varios instrumentos por activo (spot, perpetuo, futuro, ETF) |
| `exchange_id` | texto | Lugar de negociación o `OTC` |
| `kind` | `SPOT`, `PERP`, `FUTURE`, `STOCK`, `ETF`, `INDEX`, `FX_SPOT`, `OTC_SPOT` | `FX_SPOT` separa divisas de metales OTC (`OTC_SPOT`: XAU/USD) |
| `quote_ccy` | ISO-4217 o código de token | Moneda del precio |
| `price_unit` | texto (`per_share`, `per_barrel`, `per_troy_oz`, `per_mmbtu`, `per_bushel`, `index_points`, `per_unit`) | Un precio sin unidad no se puede comparar |
| `contract_multiplier` | numeric, nulo si no aplica | Futuros: valor de un punto |
| `price_domain` | `positive` / `any` | Petróleo y gas en futuros: `any` (V3-07) |
| `expiry` | timestamptz, obligatorio si `FUTURE` | |
| `underlying_root`, `contract_month` | texto, si `FUTURE` | Base para series continuas (I-2+) |
| `tradable` | bool (falso en `INDEX`) | Un índice no se compra |
| `settlement` | `cash` / `physical` / `none` | Riesgo de entrega en futuros |

Todos estos son **definitorios e inmutables** (`I1_TEMPORAL_MODEL.md`); `tick_size`, `calendar_id`, `price_scale`, `volume_scale`, `status` van en `instrument_attributes` (bitemporal).

Restricciones: `kind = 'INDEX' ⇒ NOT tradable`; `kind = 'FUTURE' ⇒ expiry, underlying_root, contract_month NOT NULL`; `kind <> 'FUTURE' ⇒ expiry IS NULL`.

## 3. Candle

| Campo | Tipo | Justificación |
|---|---|---|
| `instrument_id`, `provider_id`, `timeframe` | | Clave con `bar_start` y `price_basis` |
| `bar_start`, `bar_end` | timestamptz, `[start, end)` | La duración real depende del calendario (media sesión, D1 de sesión), por eso no se impone `end − start = duración` en la base |
| `price_kind` | `trade`, `bid`, `ask`, `mid`, `settlement`, `index_level`, `nav` | Forex suele dar `mid` o `bid`; índices dan nivel; ETF puede dar NAV |
| `price_basis` | `raw` / `split_adjusted` / `total_return_adjusted` + `adjustment_version` | Sustituye el booleano `adjusted` |
| `open`, `high`, `low`, `close` | `numeric` sin modificador | Precisión arbitraria; la escala máxima se valida contra `price_scale` del instrumento (V3-14) |
| `volume` | `numeric`, **nulo permitido** | Forex OTC e índices no tienen volumen negociado (V3-08) |
| `volume_kind` | `base_units`, `quote_notional`, `contracts`, `shares`, `tick_count`, `none` | Magnitudes incomparables no se mezclan |
| `trade_count` | int, nulo | Opcional |
| `session_kind` | `regular`, `extended`, `continuous` | Acciones con preapertura |
| `is_closed` | bool | Velas parciales explícitas |
| `source_ts` | timestamptz | Hora del proveedor |
| `payload_id`, `locator` | | Procedencia |
| `canonical_version`, `canonical_sha256` | | §5 |
| `adapter_version`, `license_id`, `quality_status` | | |
| `write_seq`, `superseded_seq` | | Ledger |

**Restricciones de base (ciertas para todos):**

```sql
CHECK (bar_end > bar_start),
CHECK (low <= LEAST(open, close) AND GREATEST(open, close) <= high),
CHECK ((volume IS NULL) = (volume_kind = 'none')),
CHECK (volume IS NULL OR volume >= 0),
CHECK (open  NOT IN ('NaN','Infinity','-Infinity') AND high  NOT IN ('NaN','Infinity','-Infinity')
   AND low   NOT IN ('NaN','Infinity','-Infinity') AND close NOT IN ('NaN','Infinity','-Infinity'))
-- Ojo: en PostgreSQL NaN = NaN es verdadero para numeric (DOC), así que «open = open» no sirve
-- Sin low > 0: la positividad es regla de calidad DQ-BAR-02 solo si price_domain = 'positive'
```

`numeric` de PostgreSQL admite `NaN` y, desde la versión 14, `Infinity` (DOC). Se rechazan ambos con restricciones explícitas.

## 4. Datos recibidos: cuatro niveles

| Nivel | Qué es | ¿Se persiste en I-1? |
|---|---|---|
| 1. Bytes de transporte | Lo que llegó por el cable (posiblemente gzip, chunked) | **No** el contenido; **sí** su huella: `transport_encoding`, `transport_size`, `transport_sha256` cuando el cliente HTTP lo exponga (si no, nulo y se dice) |
| 2. Cuerpo decodificado | Bytes tras quitar la codificación de transporte, antes de interpretar | **Sí**: `raw_payloads.body`, `body_sha256` |
| 3. Interpretación del adaptador | Registros en la forma del proveedor (sus nombres de campo, sus tipos) | **No**: se reconstruye con `reparse(body, adapter_version)`; el contrato exige que sea determinista |
| 4. Canónico | `Candle` de §3 | **Sí**: `candles` |

Casos límite:

| Caso | Regla |
|---|---|
| JSON con claves duplicadas | Interpretación estricta: la respuesta se rechaza (`InvalidResponse`); el cuerpo se guarda con `parse_status = 'rejected'` y el motivo |
| Juego de caracteres distinto de UTF-8 | JSON debe ser UTF-8 (RFC 8259); otros formatos declaran su codificación en el descriptor; si no coincide, rechazo |
| Números no finitos, exponentes, precisión | Se leen como `Decimal` desde el texto, nunca como `float` |
| Tamaño | Tope 8 MiB por cuerpo (configurable por proveedor en I-2); mayor → rechazo sin guardar el cuerpo, solo la huella |
| Purga | `body = NULL`, se conservan hash, tamaño y huella de la petición |
| Orden de operaciones | Guardar cuerpo (preparación) → interpretar → validar → publicar todo junto. Un fallo de interpretación no impide guardar el cuerpo para auditoría (si la licencia permite almacenarlo) |

## 5. Identidad canónica de una vela (`c2`)

`canonical_sha256 = SHA-256` de la concatenación UTF-8, separada por `|`, de:

`c2 | namespace | provider_id | instrument_id | timeframe | bar_start | bar_end | price_kind | price_basis | adjustment_version | quote_ccy | price_unit | open | high | low | close | volume | volume_kind | session_kind | is_closed`

Tiempos ISO-8601 UTC con microsegundos y `Z`; decimales normalizados (sin exponente, sin ceros finales, `-0` → `0`); nulos como cadena vacía. `quote_ccy` y `price_unit` se copian del instrumento para que el hash sea autosuficiente.

**Correcciones retroactivas del proveedor:** una respuesta posterior con otro valor para la misma clave produce otro `canonical_sha256` → revisión nueva en la siguiente publicación; la anterior queda sustituida pero visible en (W, H) antiguas. Si el valor es igual, no hay revisión.

**Re-proceso con otra versión de adaptador:** se interpreta el cuerpo guardado con la versión nueva. Si el canónico no cambia, nada; si cambia, revisión nueva con `adapter_version` nuevo y registro del motivo. Nunca se edita una fila publicada.

## 6. Timeframe y calendario

**Timeframe** deja de saber alinearse (V3-10):

| Valor | Clase | Duración nominal |
|---|---|---|
| `M1`, `M5`, `M15`, `H1`, `H4` | Intradía de duración fija | 1, 5, 15, 60, 240 min |
| `D1` | **Sesión** de negociación | Variable (una sesión, no 24 h) |
| `W1` | Semana de sesiones | Variable |

Las fronteras de cada vela las da `calendar.bar_boundaries(tf, start, end, alignment)` con una **política de alineación** registrada por (instrumento, proveedor, temporalidad): `utc_clock` (cripto habitual) o `session_open` (acciones). Una vela intradía que cae en un borde de sesión puede ser **parcial**: se marca y no se rechaza.

**Session** pasa a:

```
Session(calendar_id, trading_date, kind, intervals: tuple[(open_ts, close_ts), ...])
```

- `trading_date` es la fecha comercial, que puede no coincidir con la fecha civil de apertura (futuros CME y forex abren el domingo por la tarde, hora de EE. UU., para la sesión del lunes).
- `intervals` admite pausas intradía (p. ej. pausa diaria de futuros) y sesiones que cruzan medianoche.
- Las horas se definen en la zona del mercado y se convierten a UTC con `zoneinfo`; horas locales inexistentes o ambiguas por cambio de horario se resuelven con una regla escrita (`fold` documentado) y prueba.
- Cierres extraordinarios y medias sesiones son revisiones bitemporales de `market_sessions`.
- `Continuous24x7`: «cierre diario 00:00 UTC» es una **convención por proveedor**, no un hecho del mercado; se declara en la política de alineación.

## 7. Contrato de proveedor (cambios respecto a v2)

- `ProviderDescriptor` añade `namespace`, `price_kinds`, `volume_kinds`, `alignment` por temporalidad, `max_body_bytes`.
- `CandleBatch` deja de llevar `adjusted: bool` y lleva `price_basis` + `adjustment_version`.
- `reparse(body, adapter_version)` es obligatorio y determinista.
- La batería de conformidad incluye: claves duplicadas, UTF-8 inválido, `NaN`, cuerpo sobredimensionado, precios negativos con `price_domain = any`, volumen ausente con `volume_kind = none`.

## 8. Qué no cambia

Bitemporalidad por publicación, separación crudo/canónico, procedencia por vela, `Decimal` en Python y restricciones de exclusión para vigencias.
