# I-1 v3 · Aplicación de licencias de datos

Fecha: 18-nov-2026. Resuelve V3-12; complementa V3-11 (sintéticas, ver `I1_SECURITY_THREAT_MODEL.md` §4).

> **Advertencia.** Este documento define **qué puede modelar y comprobar el software**. Si una licencia concreta es legalmente suficiente para un uso depende del contrato real de cada proveedor, que **hoy no existe** para ningún mercado nuevo (`DATA_LICENSE_MATRIX.md`; `ECONOMIC_REVIEW.md`: «COTIZACIÓN: hoy no existe ninguna»). Nada aquí declara una licencia suficiente.

## 1. Modelo de datos de licencia (I-1 crea las tablas y los campos)

| Campo | Tipo | Significado | Fuente |
|---|---|---|---|
| `license_id`, `provider_id`, `namespace` | | Identidad; `namespace` = `real` o `synthetic` | Modelo |
| `valid_from`, `valid_to` | tstzrange | Vigencia contractual | Contrato |
| `revoked_at` | timestamptz | Revocación anticipada (también bitemporal: se publica cuando se sabe) | Notificación del proveedor |
| `allowed_uses` | conjunto de `DataUse` | `store`, `display`, `derived_public`, `alert`, `export`, `research`, `staging` | Contrato |
| `audiences` | conjunto | `internal`, `non_professional`, `professional`, `commercial_redistribution` | Contrato |
| `territories` | conjunto ISO-3166 o `*` | Dónde pueden estar los usuarios que ven el dato | Contrato |
| `scope` | filas en `license_markets` (mercado, bolsa, opcionalmente instrumento) | Qué datos cubre | Contrato |
| `display_delay_min` | int | Retraso mínimo para mostrar (0 = tiempo real) | Contrato |
| `attribution_text` | texto exacto | Atribución obligatoria | Contrato |
| `max_storage_days` | int o nulo | Retención máxima durante la vigencia | Contrato |
| `post_termination` | `delete` / `retain_internal` / `retain_research` / `unknown` | Qué pasa con lo guardado al terminar | Contrato; `unknown` se trata como `delete` |
| `derived_retention` | `with_source` / `independent` / `unknown` | Si los derivados sobreviven al dato fuente | Contrato; `unknown` = `with_source` |
| `max_users` | int o nulo | Límite de usuarios | Contrato |
| `contract_ref`, `verified_by`, `verified_at` | | Trazabilidad; obligatorio en `namespace = real` | Proceso |

Todos los valores «desconocidos» se interpretan de la forma **más restrictiva**.

## 2. Matriz de autorización: uso × momento

`✔` = comprobación obligatoria; `—` = no aplica. «Licencia» = términos vigentes en el instante indicado, resueltos con la marca actual salvo que se diga otra cosa.

| Momento \ Uso | STORE | DISPLAY | DERIVED_PUBLIC | ALERT | EXPORT | RESEARCH | STAGING |
|---|---|---|---|---|---|---|---|
| **Recibir** (adaptador devuelve datos) | ✔ licencia vigente en `received_ts` que cubra el mercado; si no, se descarta y se registra | — | — | — | — | — | ✔ (preparación cuenta como almacenamiento temporal) |
| **Almacenar** (`publish`) | ✔ misma comprobación dentro de la base (no solo en Python); `retention_until` = `received_ts + max_storage_days` | — | — | — | — | — | ✔ |
| **Consultar** (lectura interna) | ✔ dato no purgado; si la licencia terminó y `post_termination = delete`, la lectura falla con `LicenseTerminated` | — | — | — | — | ✔ licencia con `research` vigente **o** `post_termination = retain_research` | — |
| **Mostrar** (UI, API) | — | ✔ licencia vigente **ahora** con `display`; audiencia y territorio del usuario; `now ≥ bar_end + display_delay_min`; atribución adjunta | — | — | — | — | — |
| **Alertar** (Telegram, correo) | — | ✔ todo lo de mostrar | — | ✔ `alert` vigente ahora; el mensaje es una visualización fuera de la plataforma | — | — | — |
| **Exportar** | — | — | — | — | ✔ `export` vigente ahora; audiencia; registro de quién, qué, cuándo | — | — |
| **Generar derivados** | — | — | ✔ si el derivado se publica: `derived_public` vigente; el derivado guarda las licencias de origen (linaje) | — | — | ✔ si es interno | — |
| **Purgar** | ✔ al vencer `retention_until`, al terminar con `post_termination = delete`, o por revocación; los derivados con `derived_retention = with_source` se purgan también | — | ✔ | — | — | — | ✔ |

**Qué implementa I-1:** recibir, almacenar, consultar y el cálculo de `retention_until`; el modelo completo de campos; y las funciones puras de decisión para mostrar, alertar, exportar, derivar y purgar, con sus pruebas. **No** implementa UI, alertas, exportación ni el proceso de purga (I-2 o posterior).

## 3. Casos

| # | Caso | Regla |
|---|---|---|
| 1 | Licencia vencida después de almacenar | El dato guardado sigue en la base hasta que la purga lo trate según `post_termination`. No se muestra ni exporta (las comprobaciones de uso miran la licencia **actual**) |
| 2 | Licencia revocada | `revoked_at` publicado → igual que vencida desde esa fecha. Una reproducción histórica para auditoría (W anterior) sí puede leer lo que se sabía entonces, solo con `RESEARCH`/auditoría interna y solo si `post_termination` lo permite |
| 3 | Cambio del permiso de visualización | Nueva revisión de la licencia; mostrar usa siempre la vigente ahora |
| 4 | Datos históricos con autorización vencida | Igual que 1; la reproducción de un escaneo antiguo devuelve los datos solo a roles internos y marca `license_terminated` |
| 5 | Exportación | Requiere `export` + audiencia; registro inmutable en `ops_events` |
| 6 | Alertas | Son visualización fuera de la plataforma: `display` + `alert` + retraso + atribución |
| 7 | Derivados | Linaje obligatorio (`derived_from_licenses`); publicar exige `derived_public` en **todas** las licencias de origen |
| 8 | Caché | Toda caché (memoria, disco, CDN) es almacenamiento: misma retención; la caché de visualización respeta el retraso |
| 9 | Retención de crudos | `raw_payloads.retention_until` desde la licencia; la purga vacía `body` y conserva hash, tamaño y huella |
| 10 | Retención de canónicos | Misma licencia que el crudo de origen; se purga la fila canónica (publicación de purga que deja la huella del hash) |
| 11 | Atribución | Texto exacto adjunto a cada respuesta que muestra el dato; prueba que compara literal |
| 12 | Retraso de visualización | `now ≥ bar_end + display_delay_min`; si no, se muestra la última vela que lo cumple |
| 13 | Usuario gratuito, profesional, comercial | El usuario tiene una `audience`; mostrar exige que esté en `audiences`. Clasificar a un usuario como no profesional es una **obligación contractual de las bolsas** (p. ej. formularios de Nasdaq) que el software solo registra |
| 14 | Restricciones por bolsa o territorio | `license_markets` por bolsa; `territories` contra el país declarado del usuario. La verificación del país real **no** la puede garantizar el software |

## 4. Lo técnico frente a lo contractual

| Se puede modelar y probar | Depende del contrato real |
|---|---|
| Que nada se guarda sin una fila de licencia que lo cubra | Si esa licencia permite realmente guardar |
| Retención, retraso, atribución, audiencia, territorio declarados | Los valores correctos de esos campos |
| Linaje de derivados y purga en cascada | Qué cuenta como «derivado» para cada proveedor |
| Registro de exportaciones y visualizaciones | Si el proveedor exige informes de uso y en qué formato |
| Clasificación declarada de usuarios | La validez legal de esa clasificación |

## 5. Pruebas (I-1)

TS-LIC-01…20 en `I1_TEST_STRATEGY_V3.md`: sin licencia → rechazo en recepción y en `publish` (dos capas); licencia vencida, revocada, de otro mercado, sin `store`; cálculo de `retention_until`; lectura tras terminación con cada valor de `post_termination`; funciones puras de mostrar/alertar/exportar/derivar con cada campo; desconocido → restrictivo; reproducción histórica con licencia luego revocada.
