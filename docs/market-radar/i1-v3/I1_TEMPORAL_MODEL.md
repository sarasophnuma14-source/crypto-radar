# I-1 v3 · Modelo temporal de todas las entidades

Fecha: 18-nov-2026. Resuelve V3-05, V3-20, V3-22. Términos (tiempo válido, versión de publicación, marca de agua (W, H), revisión, sustitución) definidos en `I1_LEDGER_REDESIGN.md` §4.

## 1. Principio

Toda consulta histórica responde «¿qué sabía el sistema en (W, H) sobre T?». Para eso, **cada dato que cambia el significado de una vela debe poder leerse tal como era en W**. Pero no todo necesita dos ejes de tiempo: se elige el mínimo que permite responder la pregunta.

## 2. Categorías

| Categoría | Qué significa | Columnas |
|---|---|---|
| **Inmutable** | Una vez publicada no cambia nunca; un error se corrige creando otra entidad | `write_seq` |
| **Versionada (registro)** | Puede corregirse; no tiene vigencia en el mundo: «la clase del activo es X» | `write_seq`, `superseded_seq` |
| **Bitemporal** | Tiene vigencia en el mundo y además puede corregirse: «del 1-ene al 1-jun el ticker fue X» | `valid_from`, `valid_to`, `write_seq`, `superseded_seq` |
| **Solo vigencia** | Tiene vigencia en el mundo pero nunca se corrige en el pasado | No se usa: toda vigencia puede tener errores de carga, así que se trata como bitemporal |
| **Referenciada por instantánea** | Un objeto que se guarda con la versión exacta usada (p. ej. un escaneo guarda su (W, H)) | Referencia a la marca |

Todas las tablas versionadas pasan por el mismo mecanismo de publicación (`I1_LEDGER_REDESIGN.md` §3).

## 3. Matriz entidad × temporalidad

| Entidad | Categoría | Clave de negocio | Por qué |
|---|---|---|---|
| `markets` | Versionada | `market_id` | Nombre, clase, calendario por defecto se corrigen; un mercado no «vence» |
| `exchanges` | Versionada | `exchange_id` | Ídem |
| `assets` | Versionada | `asset_id` | La clasificación puede corregirse (escenario 3); el activo no tiene vigencia propia |
| `instruments` (atributos **definitorios**: activo, bolsa, tipo, moneda de cotización, unidad, tamaño de contrato, vencimiento, dominio de precio) | **Inmutable** | `instrument_id` | Cambiar cualquiera cambia el significado de todas las velas. Un cambio real crea otro instrumento (escenarios 1 y 4) |
| `instrument_attributes` (no definitorios: `tick_size`, `tradable`, `calendar_id`, `price_scale`, `volume_scale`, `status`) | Bitemporal | (`instrument_id`, atributo) | Cambian en fechas concretas y pueden cargarse mal |
| `instrument_successions` | Inmutable | (`from_id`, `to_id`) | Enlaza un instrumento con su sucesor y la fecha del cambio |
| `asset_identifiers` | Bitemporal | (`scheme`, `value`, `provider_id`) | Escenario 2 |
| `instrument_sources` | Bitemporal | (`instrument_id`, `provider_id`) | Escenario 8 |
| `providers` | Versionada | `provider_id` | Descriptor y versión del adaptador |
| `provider_licenses` + `license_markets` | Bitemporal | `license_id` | Escenario 7 |
| `provider_quarantine` | Bitemporal | (`provider_id`, intervalo) | Escenario 9 |
| `market_calendars` | Versionada | `calendar_id` | Zona horaria y reglas; la definición se corrige |
| `market_sessions` | Bitemporal | (`calendar_id`, `trading_date`) | Escenarios 5 y 6 |
| `raw_payloads` | Inmutable (la purga es una publicación que vacía `body` y deja la huella) | `payload_id` | Lo recibido no cambia |
| `candles` | Bitemporal (tiempo válido = `[bar_start, bar_end)`) | (`instrument_id`, `provider_id`, `timeframe`, `bar_start`, `price_basis`) | Correcciones del proveedor |
| `ops_events` | Inmutable, fuera del ledger | `event_id` | Bitácora operativa; no forma parte de la historia de datos |

## 4. Escenarios

| # | Escenario | Tratamiento | Efecto en una reproducción con W anterior |
|---|---|---|---|
| 1 | Cambio de moneda de cotización | Nuevo instrumento + `instrument_successions` con fecha | Ve el instrumento antiguo con su moneda; las velas nunca cambian de moneda |
| 2 | Cambio de identificador de proveedor | Se cierra la vigencia del identificador antiguo (`valid_to`) y se publica el nuevo | Si W es anterior a la publicación, la resolución usa los identificadores conocidos entonces |
| 3 | Corrección de clasificación de activo | Revisión de `assets` | Ve la clasificación antigua; el informe puede marcar «corregida después» comparando con la marca actual |
| 4 | Cambio de bolsa | Nuevo instrumento + sucesión | Igual que 1 |
| 5 | Cambio de calendario de un instrumento | Nueva fila bitemporal de `instrument_attributes(calendar_id)` desde la fecha del cambio | Las velas anteriores se evalúan con el calendario vigente en su tiempo válido, tal como se sabía en W |
| 6 | Corrección de una sesión histórica | Revisión bitemporal de `market_sessions` para esa `trading_date` | Ve la sesión errónea (lo que se sabía); una reproducción con W posterior ve la corregida |
| 7 | Cambio de vigencia de una licencia | Revisión de `provider_licenses` | Ver `I1_LICENSE_ENFORCEMENT.md` §3: la reproducción para auditoría usa la licencia conocida en W; un **uso nuevo** (mostrar, exportar) siempre usa la licencia vigente hoy |
| 8 | Cambio de fuente primaria | Revisión bitemporal de `instrument_sources` | La selección de fuente se repite con las fuentes conocidas en W |
| 9 | Cuarentena retroactiva | Fila de `provider_quarantine` con vigencia en el pasado, publicada ahora | Con W anterior, la cuarentena no existía: el resultado es el de entonces. Con W posterior, las velas de ese intervalo y proveedor se excluyen de la selección de fuente y se marcan `quarantined` |

## 5. Política de consulta histórica

1. **Toda lectura recibe (W, H) obligatorio.** No hay valor por defecto: la lectura «actual» es pedir primero `mr.watermark()` y usarla.
2. Las lecturas se hacen solo con funciones `mr.<entidad>_asof(w, holes, …)` o vistas parametrizadas equivalentes. `mr_reader` no tiene `SELECT` sobre las tablas base versionadas.
3. Una consulta que une velas con metadatos usa **la misma (W, H)** para todos. La función de lectura de velas devuelve, junto a cada vela, los atributos del instrumento y la fuente resueltos en (W, H). No existe en el código un camino que una velas antiguas con metadatos actuales.
4. Para el eje válido, cada atributo se resuelve en el tiempo válido de la vela (`valid_from ≤ bar_start < valid_to`).
5. Un escaneo, informe o exportación guarda su (W, H). Repetirlo es llamar a las mismas funciones con esos valores.
6. Prueba de control (TS-REPRO-08): un análisis estático rechaza SQL del paquete que lea tablas base versionadas fuera de las funciones `_asof`.

```sql
-- Ilustrativo: lectura de velas con metadatos de la misma versión
CREATE FUNCTION mr.candles_asof(w bigint, holes bigint[], p_instrument uuid, p_provider text,
                                p_tf text, p_from timestamptz, p_to timestamptz)
RETURNS TABLE (bar_start timestamptz, bar_end timestamptz, open numeric, high numeric, low numeric, close numeric,
               volume numeric, volume_kind text, quote_ccy text, price_unit text, calendar_id text, write_seq bigint)
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
  SELECT c.bar_start, c.bar_end, c.open, c.high, c.low, c.close, c.volume, c.volume_kind,
         i.quote_ccy, i.price_unit, a.value AS calendar_id, c.write_seq
  FROM mr.candles c
  JOIN mr.instruments i ON i.instrument_id = c.instrument_id               -- inmutable
  JOIN mr.instrument_attributes a ON a.instrument_id = c.instrument_id AND a.attribute = 'calendar_id'
       AND a.valid_from <= c.bar_start AND (a.valid_to IS NULL OR c.bar_start < a.valid_to)
       AND mr.visible(a.write_seq, a.superseded_seq, w, holes)
  WHERE c.instrument_id = p_instrument AND c.provider_id = p_provider AND c.timeframe = p_tf
    AND c.bar_start >= p_from AND c.bar_start < p_to
    AND mr.visible(c.write_seq, c.superseded_seq, w, holes)
$$;
-- mr.visible(ws, ss, w, h) = ws <= w AND NOT ws = ANY(h) AND (ss IS NULL OR ss > w OR ss = ANY(h))
```

## 6. Complejidad que se evita

- No se versiona `ops_events` (no es historia de datos).
- No se usan dos ejes de tiempo donde uno basta (mercados, activos, bolsas, proveedores).
- No se versionan los atributos definitorios del instrumento: se crea otro. Esto evita la mayor fuente de errores sutiles (series en dos monedas).

## 7. Riesgo residual

Las funciones `_asof` concentran la lógica temporal: un error en ellas afecta a todo. Por eso se prueban contra una implementación de referencia en memoria con la misma batería (TS-REPRO-01…08) y con casos generados al azar.
