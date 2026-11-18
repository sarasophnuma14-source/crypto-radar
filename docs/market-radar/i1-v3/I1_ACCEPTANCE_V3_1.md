# I-1 v3.1 · Criterios de aceptación y veredicto

Fecha: 18-nov-2026. Sustituye como referencia a `I1_ACCEPTANCE_V3.md` (no modificado). Todos sus criterios A1–A9 y B1–B6 siguen vigentes; aquí se añaden y precisan.

## 1. Veredicto

**NO READY.**

| Nivel | Estado | Motivo |
|---|---|---|
| NO READY | **Sí** | No existe autorización expresa del propietario para escribir código (DP-01 pendiente). Los P0 de v3 (V3-01…V3-06) y el nuevo V3-26 están corregidos **solo documentalmente**; ninguno está implementado ni verificado |
| READY FOR FOUNDATION | No | Exige autorización (DP-01) y la evidencia ejecutada de M1 de §3 |
| READY FOR MARKET DATA | No | Núcleo inexistente; licencia cripto sin confirmar (F0-11); Fase 0 abierta |
| READY FOR FIRST MARKET | No | 0 de 14 criterios de §18 |
| READY FOR PRODUCTION | No | Nada implementado ni desplegado |

## 2. Condiciones previas para empezar M1 (decisiones del propietario)

| # | Condición | Estado |
|---|---|---|
| P1 | Autorización expresa de escribir código, con alcance (DP-01) | Pendiente |
| P2 | Aprobación individual (o sustitución) de DV3-01…DV3-15 (DP-02) | Pendiente; la matriz solo está aceptada como base de revisión |
| P3 | Decisión sobre CI (DP-03); si es Sí, rige DV3-14/15 | Pendiente |
| P4 | DP-04, limitado a desarrollo aislado: sin fusionar, desplegar, modificar archivos existentes ni tocar servicios de producción | Pendiente |

## 3. Criterios de M1 para READY FOR FOUNDATION (actualizados)

Todos con evidencia ejecutada adjunta a la PR. **Ninguno se cumple hoy.**

| # | Criterio | Evidencia exigida |
|---|---|---|
| A1–A9 | Los de `I1_ACCEPTANCE_V3.md` §3 (unidades, red, migraciones, privilegios, adversariales, concurrencia, aislamiento, revisión de funciones privilegiadas, secretos) | Igual que en v3 |
| A2' | TS-ADV ampliado: los 20 ataques fallan con el error concreto esperado | SQLSTATE por caso |
| **A10** | **Idempotencia concurrente obligatoria:** TS-IDEM-01…16 al 100 % en Python 3.12 y 3.13; las cuatro invariantes I1–I4 se cumplen en cada caso; TS-IDEM-02…05 y 08…09 con intercalado **forzado** y además 50 repeticiones aleatorias con semilla registrada | Salida, intercalados, semillas, invariantes |
| **A11** | **Control negativo de idempotencia:** la variante sin bloqueo del lote ni revalidación falla en TS-IDEM-02 y TS-IDEM-05 | Salida de la variante defectuosa |
| **A12** | **Reintento tras `COMMIT` desconocido:** TS-IDEM-08 y 09 demuestran que ningún reintento crea una versión nueva y que el estado se recupera con `batch_status` | Salida |
| **A13** | **Ausencia de interbloqueos y esperas acotadas:** TS-IDEM-12 sin `deadlock detected`; TS-IDEM-16 dentro del tiempo límite | Registro del servidor |
| **A14** | **Rutas:** solo altas en `market_radar/`, `tests/market_radar/`, `docs/market-radar/foundation/` y, solo si DP-03 = Sí, `.github/workflows/market-radar-i1.yml` | `git diff --name-status` |
| **A15** | **CI (solo si DP-03 = Sí):** TS-CI-01…08 al 100 %; ejecución verde del flujo en la PR en borrador, con la prueba de control de red fallando como se espera dentro del espacio aislado | Enlace a la ejecución y registro |

## 4. Criterios para cerrar I-1 completo

B1–B6 de v3, con B1 actualizado a **≈ 209 casos** (≈ 201 sin CI), 0 omitidos.

## 5. Lo que este veredicto no dice

- No dice que el diseño v3.1 sea correcto: dice que no hay P0 conocidos sin solución documentada.
- No autoriza nada. El estado sigue siendo **NO READY** hasta que exista autorización expresa del propietario y, después, la evidencia de M1.
