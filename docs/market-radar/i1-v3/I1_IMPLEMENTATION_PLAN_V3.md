# I-1 v3 · Plan de implementación

Fecha: 18-nov-2026. Sustituye a `PHASE_1_IMPLEMENTATION_PLAN.md` v2 (que no se edita y queda como historial). **No autorizado. No existe código.**

## 1. Lo que no cambia

Monolito modular en Python; paquete `market_radar/` aislado; ninguna dependencia de `radar/`; PostgreSQL 16 local; datos sintéticos; sin proveedores reales, red, IA, señales, motores, UI, Telegram, Neon ni despliegue. Sin Redis, colas ni microservicios. Sin dependencias nuevas (`psycopg` ya está en `requirements.txt`, que no se toca).

Control de cambios: rama nueva desde `release-2.1`, PR en borrador; solo altas en `market_radar/`, `tests/market_radar/`, `docs/market-radar/foundation/`; fusionar exige Fase 0 cerrada y autorización expresa.

## 2. Arquitectura de I-1 v3

```
market_radar/
  core/        tipos, Decimal, tiempo, codificación canónica c2, errores
  registry/    modelos; repositorio en memoria (referencia) y PostgreSQL (vía funciones _asof y publish)
  calendars/   Session con intervalos y trading_date; Continuous24x7; TableCalendar; bar_boundaries
  providers/   contrato, descriptor, RawPayload, reparse; licencias: modelo y funciones puras de decisión
  quality/     reglas DQ del grupo I-1 condicionadas a price_domain / volume_kind
  storage/     connect (solo socket Unix), migrate (manifiesto), ledger (publish, watermark), lecturas _asof
  config.py    única lectura de entorno: ruta del socket y nombre de base; limpia PG* del entorno
  boundaries.py
tests/market_radar/
  fixtures/    roles y base por módulo; proveedor y licencias sintéticas (solo aquí)
  reference/   implementación temporal en memoria para comparar
  ...          grupos de I1_TEST_STRATEGY_V3.md
docs/market-radar/foundation/  DEVELOPER_GUIDE, CONTRACTS, DATA_MODEL_I1, SECURITY_I1
```

El arranque del espacio de red aislado y de los roles se documenta en `DEVELOPER_GUIDE.md`; no se añade infraestructura nueva.

Python escribe **solo** en tablas de preparación y llama a `mr.publish_*`; lee **solo** con `mr.*_asof`. No hay SQL de escritura directa a tablas versionadas en el paquete (comprobado por análisis estático).

## 3. Arranque de roles (fuera de las migraciones)

Los roles son objetos del clúster y crearlos exige `CREATEROLE` o superusuario. Por eso no los crea el runner (que rechaza ejecutarse como superusuario). En I-1, el arnés de pruebas crea `mr_owner`, `mr_migrator`, `mr_writer`, `mr_reader`, `mr_test_fixtures` con un guion de arranque idempotente documentado en `DEVELOPER_GUIDE.md`; la migración 0001 **comprueba** que existen con los atributos esperados y aborta si no.

## 4. Migraciones

| # | Contenido | Notas |
|---|---|---|
| 0001_base | `mr` (dueño `mr_owner`), `mr.instance` (kind inmutable, `test` en I-1), `mr.schema_migrations` (checksum de up **y** down), `mr.migration_objects` (manifiesto), revocaciones a `PUBLIC`, privilegios por defecto | Comprueba roles y versión 16 |
| 0002_extensions | `btree_gist` en `mr` si no existe; si existe, se anota y no se toca | |
| 0003_ledger | `ledger_head`, `write_log` (con `xid`, cadena de hashes), `mr.visible()`, disparador genérico de defensa, `mr.watermark()` | |
| 0004_registry | `markets`, `exchanges`, `assets` (versionadas); `instruments` (inmutable); `instrument_attributes` (bitemporal); `instrument_successions`; `asset_identifiers` (bitemporal con exclusión) | |
| 0005_providers_licenses | `providers`, `provider_licenses`, `license_markets` con `namespace` y claves compuestas; funciones de registro real y sintético | |
| 0006_sources | `instrument_sources`, `provider_quarantine` (bitemporales, exclusiones) | |
| 0007_calendars | `market_calendars` (versionada), `market_sessions` (bitemporal, intervalos) | |
| 0008_raw | `stage_payloads`, `raw_payloads` | |
| 0009_candles | `stage_candles`, `candles` | |
| 0010_read_api | `*_asof` y `mr.publish_*` | Funciones `SECURITY DEFINER`, `search_path` fijo |
| 0011_ops_events | `ops_events` | |

### 4.1 Reversión segura (V3-04, V3-15)

1. Cada migración se ejecuta en **una transacción** con `pg_advisory_xact_lock`, `lock_timeout` y `statement_timeout`; si falla, no queda nada aplicado (DOC: DDL transaccional en PostgreSQL, incluida `CREATE EXTENSION`).
2. Tras cada `up`, el runner registra en `mr.migration_objects` la identidad de cada objeto creado (`pg_identify_object` sobre `pg_depend`/`pg_class`/`pg_proc`/`pg_type`).
3. `down` está prohibido salvo `mr.instance.kind = 'test'`. En cualquier otra instancia, las correcciones son migraciones hacia delante.
4. Antes de `down`, el runner: (a) compara los objetos actuales de `mr` con el manifiesto y aborta si hay alguno no inventariado; (b) busca en `pg_depend` dependencias desde objetos **fuera** del manifiesto hacia objetos del manifiesto y aborta si existen, listándolas.
5. Los scripts `down` eliminan objeto por objeto, en orden inverso, **sin `CASCADE`** (RESTRICT por defecto). Si algo depende, el `DROP` falla y la transacción se deshace.
6. `btree_gist` solo se elimina si 0002 la creó (`DROP EXTENSION btree_gist RESTRICT`).
7. El checksum de `down` se registra al aplicar `up`; si el archivo cambió, `down` se niega.

## 5. Tareas, dependencias y estimación

Días = días de trabajo con revisión. SUPUESTO: sin velocidad histórica comparable.

| Tarea | Contenido | Depende de | Días |
|---|---|---|---|
| T01 | Tipos, `Decimal`, tiempo, codificación `c2`, `config`, fronteras; TS-UNIT parcial | — | 1,5 |
| T02 | Conexión solo socket Unix, limpieza de entorno, verificación tras conectar; ejecución de la suite en espacio de red aislado; TS-NET | T01 | 1,5 |
| T03 | Runner con manifiesto, checksums up/down, instancia, `down` restringido; arranque de roles; TS-MIG | T02 | 2,5 |
| T04 | Roles y privilegios, inventario contra lista blanca; TS-PRIV | T03 | 1,5 |
| T05 | Ledger: cabecera, `write_log`, cadena de hashes, disparadores, `watermark()`, `visible()`, publicación genérica | T04 | 3,0 |
| T06 | TS-ADV, TS-CONC (con control negativo), TS-REC sobre el ledger | T05 | 2,5 |
| **M1** | **Hito de integridad: evidencia de T01–T06 revisada por el propietario** | T06 | — |
| T07 | Registro: versionadas, inmutables, atributos bitemporales, sucesiones, identificadores | M1 | 3,0 |
| T08 | Licencias con `namespace`, sintéticos por rol e instancia, funciones puras de uso; TS-LIC, TS-LIC-SYN | T07 | 2,5 |
| T09 | Fuentes, cuarentena, selección; TS-SRC | T08 | 1,5 |
| T10 | Calendarios con intervalos, `trading_date`, alineación; TS-CAL | T07 | 2,5 |
| T11 | Contrato de proveedor, sintético en `tests/`, conformidad, `reparse`; TS-RAW parcial | T08 | 2,0 |
| T12 | Crudos y velas: preparación, `publish_candles`, reglas DQ; TS-DATA, TS-RAW | T09, T10, T11 | 3,0 |
| T13 | Lecturas `_asof` completas, referencia en memoria; TS-REPRO | T12 | 2,0 |
| T14 | TS-ISO, documentación de `foundation/`, evidencia en la PR | T13 | 1,0 |
| **Total** | | | **≈ 30 días ≈ 6 semanas** (rango 25–36) |

**Ruta crítica:** T01 → T02 → T03 → T04 → T05 → T06 → M1 → T07 → T08 → T11 → T12 → T13 → T14.

**Trabajo adicional frente a v2:** ≈ 13 días (v2: ≈ 17). Origen: modelo de permisos y ledger con publicación (≈ 4), manifiesto y reversión segura (≈ 1,5), temporalidad del registro (≈ 2,5), aislamiento de red real (≈ 1), contratos universales y calendarios con intervalos (≈ 2), pruebas adversariales y de recuperación (≈ 2).

## 6. Hito M1 y por qué existe

El propietario estableció que READY FOR FOUNDATION no puede basarse solo en documentos ni en consultas desechables. M1 produce la primera **evidencia ejecutada** sobre lo que más riesgo tiene (permisos, ledger, reproducibilidad, migraciones, red), en ≈ 12,5 días y sin tocar nada fuera de las carpetas nuevas. Si M1 falla o revela un problema de diseño, se detiene antes de construir el resto encima.

## 7. Reversión

| Situación | Acción |
|---|---|
| Durante el desarrollo | Cerrar la PR y borrar la rama |
| Base local | `down` (solo instancia `test`) o borrar la base y el clúster local |
| Si se fusionara algún día | Revertir el commit de fusión: solo carpetas nuevas, nada de la 2.1 las importa |
| Base remota | No existe en I-1; la conexión solo admite socket Unix |

## 8. Dependencias

| Dependencia | Estado |
|---|---|
| Python 3.12/3.13, biblioteca estándar | Disponibles |
| `psycopg[binary]==3.3.9` | Ya en `requirements.txt` |
| PostgreSQL 16 con `btree_gist` | EXP: 16.15 disponible localmente |
| Espacio de red aislado (`unshare` o contenedor) | SUP: disponible en el entorno de desarrollo; si no, la evidencia TS-NET se genera en un contenedor `--network none` |
| Autorización del propietario | **Pendiente** |
| Aprobación de las decisiones de `I1_DECISION_MATRIX.md` | **Pendiente** |
