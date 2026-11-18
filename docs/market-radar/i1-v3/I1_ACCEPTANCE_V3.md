# I-1 v3 · Criterios de aceptación y veredicto

Fecha: 18-nov-2026.

## 1. Veredicto

**NO READY.**

| Nivel | Estado | Motivo |
|---|---|---|
| NO READY | **Sí** | El diseño v2 tiene 6 hallazgos P0 (V3-01…V3-06). v3 los corrige **documentalmente**; ninguno está implementado ni verificado. Por la regla del propietario, READY FOR FOUNDATION no puede basarse solo en documentos ni en consultas desechables |
| READY FOR FOUNDATION | No | Falta la evidencia ejecutada de §3 (hito M1) |
| READY FOR MARKET DATA | No | El núcleo no existe; sin licencia cripto confirmada (F0-11); Fase 0 de la 2.1 abierta |
| READY FOR FIRST MARKET | No | 0 de 14 criterios de §18 |
| READY FOR PRODUCTION | No | Nada implementado ni desplegado |

Lo que sí cambia frente a v2: el diseño v3 no tiene P0 **conocidos sin solución documentada**. Que las soluciones funcionen es lo que M1 debe demostrar.

## 2. Qué hace falta para autorizar la implementación (decisión del propietario)

1. Aprobar (o rechazar con alternativa) DV3-01…DV3-12 (`I1_DECISION_MATRIX.md`).
2. Autorizar expresamente **escribir código**, con el alcance que elija (DP-01). Recomendación: solo el hito M1.
3. Decidir CI (DP-03) y si el código empieza antes de cerrar la Fase 0 sin fusionar (DP-04).

## 3. Criterios objetivos para pasar a READY FOR FOUNDATION (al terminar M1)

Todos deben cumplirse con **evidencia ejecutada** adjunta a la PR. Ninguno se cumple hoy.

| # | Criterio | Evidencia exigida | Estado hoy |
|---|---|---|---|
| A1 | TS-UNIT (parte de T01), TS-NET, TS-MIG, TS-PRIV, TS-ADV, TS-CONC, TS-REC: 100 % en Python 3.12 y 3.13, PostgreSQL 16, 0 omitidas | Salida completa, versión de servidor, semillas | No existe |
| A2 | Los 14 ataques de TS-ADV fallan con el error concreto esperado; la verificación de la cadena detecta la alteración como superusuario | SQLSTATE por caso | Solo EXP preliminar (13 de 14 sobre un prototipo SQL desechable) |
| A3 | TS-CONC: 100 % de relecturas idénticas en 3 ejecuciones con semillas distintas, 8 y 32 escritores, con rollbacks y conexiones terminadas; versiones confirmadas sin huecos; **control negativo** detecta al menos 1 diferencia | Registros (W, H, hash) | Solo EXP preliminar (1 ejecución, 8 escritores) |
| A4 | TS-MIG: `up`→`down`→`up` con catálogo idéntico; `down` aborta ante objeto ajeno dependiente sin borrar nada; `down` rechazado fuera de instancia `test` | Volcados de catálogo | No existe |
| A5 | TS-PRIV: inventario de privilegios igual a la lista blanca | Inventario generado | No existe |
| A6 | TS-NET: rechazo de todos los DSN peligrosos; control de red dentro del espacio aislado falla como se espera | Salida + configuración | No existe |
| A7 | TS-ISO: solo altas en las carpetas permitidas; suite de la 2.1 idéntica | Salida de `git` y de la suite | No existe |
| A8 | Revisión línea a línea de cada función `SECURITY DEFINER` registrada en la PR | Comentarios de revisión | No existe |
| A9 | Búsqueda de secretos limpia (patrones de clave, `postgres://` con host, `neon.tech`, `render.com`) | Salida | No existe |

## 4. Criterios para cerrar I-1 completo (después de M1)

| # | Criterio |
|---|---|
| B1 | Las ≈ 179 pruebas de `I1_TEST_STRATEGY_V3.md` al 100 %, 0 omitidas, en 3.12 y 3.13 |
| B2 | TS-REPRO: igualdad exacta con la implementación de referencia en 1.000 historias aleatorias; análisis estático sin lecturas de tablas base fuera de `_asof` |
| B3 | TS-LIC y TS-LIC-SYN al 100 % |
| B4 | TS-DATA y TS-CAL: precio negativo, volumen ausente, sesión que cruza medianoche, pausa intradía y cambio de hora cubiertos |
| B5 | Documentación de `foundation/` presente |
| B6 | Ningún archivo existente modificado; `requirements.txt` sin cambios |

## 5. Lo que este veredicto no dice

- No dice que el diseño v3 sea correcto: dice que no tiene problemas P0 conocidos sin solución documentada.
- No dice nada sobre la viabilidad comercial ni sobre la existencia de ventaja estadística (NO EDGE sigue vigente).
- No autoriza nada por sí mismo.
