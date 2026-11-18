# I-1 v3.1 · Registro de cambios

Fecha: 18-nov-2026. Rama documental `claude/project-thread-dclqgc`. Revisión **solo documental**: no se escribió código, no se creó ninguna migración, no se ejecutó ninguna consulta (ni en un entorno desechable), no se inició M1, no se fusionó ni desplegó nada.

## 1. Archivos

| Archivo | Acción |
|---|---|
| `docs/market-radar/i1-v3/I1_DECISION_MATRIX_V3_1.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_LEDGER_REDESIGN_V3_1.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_TEST_STRATEGY_V3_1.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_ACCEPTANCE_V3_1.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_IMPLEMENTATION_PLAN_V3_1.md` | Nuevo |
| `docs/market-radar/i1-v3/I1_CHANGELOG_V3_1.md` | Nuevo (este) |
| Cualquier otro archivo | **Sin cambios.** Los documentos v3 (`I1_*.md` sin sufijo y `README.md` de esta carpeta) se conservan como historial; los v3.1 los complementan |

## 2. Peticiones del propietario y dónde se resuelven

| # | Petición | Resolución |
|---|---|---|
| 1 | DV3-13: idempotencia concurrente (restricción única de `batch_id`, revalidación tras el bloqueo de `ledger_head`, publicación única, retorno de la secuencia original) | DECISION_MATRIX_V3_1 §1; LEDGER_REDESIGN_V3_1 §2–§6 |
| 2 | Diseño del ledger y contrato de publicación | LEDGER_REDESIGN_V3_1 §4 (contrato formal de 10 pasos, orden de bloqueos, garantías con su fuente) |
| 3 | Pruebas adversariales y de concurrencia específicas | TEST_STRATEGY_V3_1 §2 (TS-IDEM-01…16) y §3 (TS-ADV-15…20) |
| 4 | Idempotencia obligatoria y verificable en la aceptación | ACCEPTANCE_V3_1 §3 (A10–A13) |
| 5 | Límites de seguridad de GitHub Actions | DECISION_MATRIX_V3_1 §3 (DV3-14); TEST_STRATEGY_V3_1 §4 (TS-CI) |
| 6 | Discrepancia de carpetas y `.github/` | DECISION_MATRIX_V3_1 §4 (DV3-15); IMPLEMENTATION_PLAN_V3_1 §1; ACCEPTANCE_V3_1 A14 |
| 7 | DP-04 limitado a desarrollo aislado | DECISION_MATRIX_V3_1 §2; IMPLEMENTATION_PLAN_V3_1 §1 |
| 8 | Conservar hallazgos, decisiones y restricciones; ninguna DP aprobada | §4 de este documento |

## 3. Hallazgos nuevos

| Id | Sev. | Documento/sección | Evidencia | Problema | Impacto | Corrección | Prueba | Estado |
|---|---|---|---|---|---|---|---|---|
| V3-26 | **P0** | `I1_LEDGER_REDESIGN.md` §3 (`publish_candles`) | Análisis del intercalado (LEDGER_V3_1 §1); no ejecutado | Comprobaciones de idempotencia antes de cualquier bloqueo y no repetidas después | Dos versiones para un lote, o un reintento que falla en vez de devolver la versión original | DV3-13 | TS-IDEM-02, 05, 06, 07 + control negativo | Corregido documentalmente |
| V3-27 | P1 | `I1_LEDGER_REDESIGN.md` §3 (aislamiento de `publish` no especificado) | DOC: en REPEATABLE READ, `FOR UPDATE` sobre una fila cambiada por otra transacción confirmada da error de serialización | Contrato no determinista: error en lugar de la versión original | Reintentos que fallan | `publish` exige READ COMMITTED y lo comprueba | TS-IDEM-11 | Corregido documentalmente |
| V3-28 | P2 | `I1_IMPLEMENTATION_PLAN_V3.md` §1 frente a DP-03 | Texto de ambos documentos | Tres carpetas permitidas, pero la CI necesita `.github/` | Criterio de rutas incumplible si se aprueba la CI | DV3-15: una ruta exacta, condicionada a DP-03 | TS-CI-01, A14 | Corregido documentalmente |
| V3-29 | P2 | `I1_LEDGER_REDESIGN.md` §6 (lotes huérfanos) | Texto | Un lote preparado sin dueño claro puede publicarse desde otra sesión con contenido parcial | Publicación de lotes incompletos | Ciclo `open → sealed` con digest declarado y disparador diferido | TS-IDEM-14, TS-ADV-15…17 | Corregido documentalmente |

## 4. Lo que se conserva

- Los 25 hallazgos de v3 (V3-01…V3-25) con su severidad y estado. Ninguno se cierra ni se rebaja.
- Las decisiones DV3-01…DV3-12, en estado Propuesta (matriz aceptada como base de revisión, sin aprobación individual).
- D-001…D-027 de `DECISION_LOG.md` sin cambios.
- DP-01…DP-04: **pendientes**. Ninguna figura como aprobada.
- Restricciones: no tocar `radar/`, la 2.1, `main.py`, `web/`, `render.yaml`, `requirements.txt`, precios, pagos, secretos, Neon, Render, holdout ni paper trading; no fusionar ni desplegar; nada irreversible.

## 5. Efecto en el plan

| | v3 | v3.1 |
|---|---|---|
| Pruebas | ≈ 179 | ≈ 209 (≈ 201 sin CI) |
| M1 | ≈ 12,5 días | ≈ 15 días (≈ 16 con CI) |
| I-1 completo | ≈ 30 días | ≈ 32,5 días (≈ 33,5 con CI) |
| Veredicto | NO READY | **NO READY** |
