# I-1 v3.1 · Plan de implementación

Fecha: 18-nov-2026. Sustituye como referencia a `I1_IMPLEMENTATION_PLAN_V3.md` (no modificado); todo lo no mencionado aquí sigue igual. **No autorizado. No existe código. M1 no ha empezado.**

## 1. Control de cambios (actualizado)

| Regla | v3 | v3.1 |
|---|---|---|
| Rama | Nueva desde `release-2.1`, PR en borrador | Igual |
| Rutas permitidas | `market_radar/`, `tests/market_radar/`, `docs/market-radar/foundation/` | Las mismas **+ una ruta exacta**, `.github/workflows/market-radar-i1.yml`, **solo si DP-03 = Sí** (DV3-15). Nada más en `.github/` |
| Archivos existentes | No se modifican | Igual (incluye `requirements.txt`, `render.yaml`, `main.py`, `web/`, `radar/`) |
| Fusión | Fase 0 cerrada + autorización expresa | Igual |
| DP-04 | Empezar antes de la Fase 0 sin fusionar | **Solo desarrollo aislado**: sin fusionar, desplegar, modificar archivos existentes ni interactuar con Neon, Render, Telegram, proveedores o pagos |
| Producción | Sin contacto | Igual; la conexión solo admite socket Unix |

## 2. Cambios de arquitectura

Solo en el ledger (`I1_LEDGER_REDESIGN_V3_1.md`):

- tabla `mr.batches` con ciclo `open → sealed → published`;
- `write_log.batch_id` `UNIQUE NOT NULL` con clave foránea a `batches`;
- funciones `mr.open_batch`, `mr.seal_batch`, `mr.publish`, `mr.batch_status` (`SECURITY DEFINER`, `search_path` fijo);
- disparador diferido que impide confirmar lotes abiertos;
- `publish` exige `READ COMMITTED`; orden de bloqueos lote → ledger; revalidación tras el bloqueo del ledger;
- en Python, `storage/ledger.py` calcula el digest canónico y el `batch_id` determinista (UUIDv5) y expone `publish_batch()` con reintento seguro basado en `batch_status`.

Las migraciones de v3 no cambian de número: `mr.batches` y las funciones nuevas pertenecen a `0003_ledger`; la clave foránea de las tablas de preparación hacia `batches`, a `0008_raw` y `0009_candles`. (Descripción documental: **no se crea ninguna migración**.)

## 3. Tareas, dependencias y estimación

Días = días de trabajo con revisión. SUPUESTO: sin velocidad histórica comparable.

| Tarea | Contenido | Depende de | v3 | v3.1 |
|---|---|---|---|---|
| T01 | Tipos, tiempo, `c2`, `config`, fronteras | — | 1,5 | 1,5 |
| T02 | Conexión solo Unix, entorno limpio, suite en red aislada; TS-NET | T01 | 1,5 | 1,5 |
| T03 | Runner con manifiesto; arranque de roles; TS-MIG | T02 | 2,5 | 2,5 |
| T04 | Roles y privilegios; TS-PRIV | T03 | 1,5 | 1,5 |
| T05 | Ledger + **ciclo de lotes, `publish` con doble validación, `batch_status`, disparador diferido** | T04 | 3,0 | **4,0** |
| T06 | TS-ADV (20), TS-CONC, TS-REC + **TS-IDEM con intercalados forzados y control negativo** | T05 | 2,5 | **4,0** |
| T15 | **Flujo `.github/workflows/market-radar-i1.yml` y TS-CI** (solo si DP-03 = Sí) | T02, T03 | — | **1,0** |
| **M1** | Evidencia de T01–T06 (+ T15) revisada por el propietario | T06 (+ T15) | 12,5 | **15,0** (16,0 con CI) |
| T07–T14 | Sin cambios respecto a v3 | M1 | 17,5 | 17,5 |
| **Total** | | | ≈ 30 | **≈ 32,5** (≈ 33,5 con CI); rango 28–40 |

**Ruta crítica:** T01 → T02 → T03 → T04 → T05 → T06 → M1 → T07 → T08 → T11 → T12 → T13 → T14. T15 va en paralelo a T04–T06 y no alarga la ruta salvo que falle la comprobación de `unshare` en el ejecutor.

**Trabajo adicional frente a v3:** ≈ 2,5 días (≈ 3,5 con CI).

## 4. Dependencias nuevas

| Dependencia | Estado |
|---|---|
| `unshare --net` (o `docker --network none`) en el ejecutor de GitHub | **SUP**; se comprueba en T15. Si no funciona, el flujo usa un contenedor sin red; si tampoco, TS-CI-07 se marca como no cumplido y se decide con el propietario |
| SHA de `actions/checkout`, `actions/setup-python`, `actions/upload-artifact` | **NO VERIFICADOS**; se registran al implementar |
| Hashes de `psycopg[binary]==3.3.9` | **NO VERIFICADOS**; se registran al implementar |
| Ajuste del repositorio «aprobación para flujos de colaboradores externos» | Solo lo puede hacer el propietario; recomendado, no requisito de M1 |

## 5. Reversión

Igual que v3, más: si DP-03 = Sí y el flujo causa cualquier problema, se elimina el único archivo `.github/workflows/market-radar-i1.yml` de la rama de I-1; no hay otros flujos en el repositorio a los que afecte.

## 6. Lo que este plan no autoriza

Ningún código, ninguna migración, el inicio de M1, fusionar, desplegar ni tocar la 2.1, Neon, Render, secretos, pagos, holdout o paper trading. Todo depende de DP-01…DP-04.
