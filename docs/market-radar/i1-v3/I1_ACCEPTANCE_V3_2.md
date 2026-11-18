# I-1 v3.2 · Criterios de aceptación y veredicto

Fecha: 18-nov-2026. **Amplía** `I1_ACCEPTANCE_V3.md` y `I1_ACCEPTANCE_V3_1.md`, que no se modifican. Siguen vigentes todos sus criterios:

- A1–A9 (v3);
- A2' y A10–A15 (v3.1);
- B1–B6 (v3, con B1 actualizado aquí).

Diseño: `I1_LEDGER_REDESIGN_V3_2.md`. Pruebas: `I1_TEST_STRATEGY_V3_2.md`. Hallazgos y plan: `I1_CHANGELOG_V3_2.md`.

## 1. Veredicto

**NO READY.**

| Nivel | Estado | Motivo |
|---|---|---|
| **NO READY** | **Sí** | No existe código de Market Radar ni autorización expresa para escribirlo (DP-01 pendiente). Ninguna decisión DP está aprobada. Los P0 conocidos están corregidos **solo documentalmente**: V3-01…V3-06 (v3), V3-26 (v3.1) y el nuevo V3-30 (v3.2). Ninguno está implementado ni verificado |
| READY FOR DOCUMENT REVIEW | **No se declara** | La documentación v3.2 queda **presentada** para la revisión del propietario, pero eso es una entrega, no un nivel de preparación. Por la regla del propietario para esta tarea, el estado sigue en NO READY mientras no existan evidencia nueva ni autorización expresa, y esta tarea no puede producir ninguna de las dos |
| READY FOR FOUNDATION | No | Exige autorización (DP-01) y la evidencia **ejecutada** de M1 (§3). Su significado no cambia: sigue sin poder basarse en documentos ni en consultas desechables |
| READY FOR MARKET DATA | No | El núcleo no existe; la licencia cripto no está confirmada (F0-11); la Fase 0 de la 2.1 está abierta |
| READY FOR FIRST MARKET | No | 0 de 14 criterios de §18 |
| READY FOR PRODUCTION | No | Nada implementado ni desplegado |

No se declara ninguna ventaja estadística: el estado de investigación sigue siendo **NO EDGE** (D-002).

## 2. Condiciones previas para empezar M1 (todas pendientes)

| # | Condición | Estado |
|---|---|---|
| P1 | Autorización expresa para escribir código, con su alcance (DP-01) | Pendiente |
| P2 | Aprobación individual (o sustitución) de DV3-01…DV3-15 y de las nuevas DV3-16…DV3-21 (DP-02) | Pendiente. Ninguna está aprobada |
| P3 | Decisión sobre CI (DP-03). Si es Sí, rigen DV3-14, DV3-15 y DV3-21 | Pendiente |
| P4 | DP-04, solo desarrollo aislado: sin fusionar, desplegar, modificar archivos existentes ni tocar servicios de producción | Pendiente |
| P5 | Solo si DP-03 = Sí: el propietario aplica la configuración R-01…R-08 del repositorio (`I1_LEDGER_REDESIGN_V3_2.md` §6.3) **antes** de activar el flujo (DP-05) | Pendiente |

## 3. Criterios de M1 para READY FOR FOUNDATION (v3.2)

Todos se acreditan con **evidencia ejecutada** adjunta a la PR. **Ninguno se cumple hoy**: solo están especificados.

| # | Criterio | Evidencia exigida | Estado |
|---|---|---|---|
| A1–A15 | Los de v3 y v3.1, con los resultados esperados precisados en `I1_TEST_STRATEGY_V3_2.md` §2 | Igual que en v3 y v3.1 | No cumplido |
| **A16** | **Conflictos de identidad rechazados correctamente.** TS-BATCH-ID-01…10 al 100 % en Python 3.12 y 3.13. En particular: un conflicto nunca modifica ni reutiliza el lote existente (comparación columna a columna antes y después); el evento de conflicto sobrevive al `COMMIT`; A → B → A deja A como estado vigente; el control negativo (identidad por contenido de v3.1) **falla** en TS-BATCH-ID-04 | Salida, filas antes y después, salida del control negativo | No cumplido |
| **A17** | **Digest canónico determinista.** TS-BATCH-DIGEST-01…18 al 100 %; Python y PostgreSQL dan bytes idénticos en todos los vectores y en los 10 000 lotes aleatorios (semilla registrada, 0 diferencias); los vectores hexadecimales quedan congelados en el repositorio; el control negativo (`c2`) **falla** en 11 y 16 | Hex de los vectores por implementación, semilla, recuento de diferencias | No cumplido |
| **A18** | **Publicación y limpieza sin pérdida ni duplicación.** TS-CLEANUP-01…13 al 100 %, con intercalados forzados y 50 repeticiones aleatorias con semilla; invariantes C1–C4 e I1–I4 en todos los casos; un evento por expiración; el control negativo (limpieza por antigüedad sin bloqueo) **falla** en TS-CLEANUP-05 | Intercalados, semillas, invariantes, eventos | No cumplido |
| **A19** | **Identidad auditada correctamente.** TS-IDENTITY-01…10 al 100 %; cada entrada de `write_log` y cada lote con OID y nombre de rol, productor y PID; ninguna decisión de autorización usa un valor enviado por el cliente (revisión línea a línea, A8); la verificación de la cadena detecta la alteración de la auditoría; el control negativo **falla** en TS-IDENTITY-01 | Salida, consultas de auditoría, comentarios de revisión | No cumplido |
| **A20** | **Seguridad de CI comprobada (solo si DP-03 = Sí).** TS-CI-SEC-01…14 al 100 %; ejecución en verde del flujo en la PR en borrador, con la prueba de control de red fallando como se espera dentro del espacio aislado y las pruebas sin root; un ensayo forzado sin aislamiento que termina en **rojo**; el control negativo (flujo inseguro de ejemplo) detectado. Sustituye a A15 de v3.1 | Enlace a las ejecuciones, registros, salida del análisis | No cumplido |
| **A20b** | **Configuración del repositorio (solo si DP-03 = Sí).** El propietario confirma por escrito en la PR que aplicó R-01…R-08, o indica cuáles no y por qué. Es una **declaración del propietario**, no una prueba: ningún código del repositorio puede comprobarla | Comentario del propietario | No cumplido |
| **A21** | **Ninguna ruta fuera del alcance.** `git diff --name-status release-2.1...HEAD` muestra **solo** altas (`A`) en `market_radar/`, `tests/market_radar/` y `docs/market-radar/foundation/`, más, solo si DP-03 = Sí, `.github/workflows/market-radar-i1.yml`. El bloqueo de dependencias de CI está en `tests/market_radar/ci/`. Ninguna `M`, `D` ni `R`. Amplía A14 | Salida de `git` | No cumplido |
| **A22** | **Ninguna modificación de Crypto Radar 2.1.** `radar/`, `main.py`, `web/`, `requirements.txt`, `render.yaml` y cualquier otro archivo existente son idénticos byte a byte a `release-2.1`. La suite de la 2.1 tiene el mismo número de pruebas y el mismo resultado que en la base. No hay importaciones cruzadas en ningún sentido. Ninguna conexión a Neon, Render, Telegram ni proveedores. Refuerza A7 y B6 | Sumas SHA-256 de esos archivos en la base y en la rama, salida de la suite 2.1, análisis de importaciones | No cumplido |
| **A23** | **Cierre de los hallazgos de v3.2.** Cada hallazgo P0 y P1 de `I1_CHANGELOG_V3_2.md` §3 y §6 tiene al menos una prueba ejecutada que lo cubre, y su estado pasa a «Verificado» solo con esa salida | Tabla de trazabilidad con enlaces a la salida | No cumplido |

## 4. Criterios para cerrar I-1 completo

B1–B6 de v3 siguen vigentes, con B1 actualizado: **≈ 266 casos** (≈ 252 si DP-03 = No), 0 omitidos, en Python 3.12 y 3.13.

## 5. Verificabilidad de cada criterio

Para no aceptar criterios imposibles de verificar:

| Criterio | Quién lo verifica | Cómo | Límite |
|---|---|---|---|
| A16–A19, A21–A23 | Pruebas automáticas + revisión del propietario | Salida ejecutada | No prueban ausencia de colisiones ni de errores (§6) |
| A17 (vectores) | Dos implementaciones independientes | Igualdad de bytes | Si ambas comparten un error de especificación, coincidirán: por eso los vectores 01–16 tienen además el resultado relacional esperado (= / ≠) escrito a mano |
| A20 | Ejecución real en GitHub | Registro del trabajo | No protege frente a una PR maliciosa (V3-35) |
| A20b | Propietario | Declaración escrita | No es comprobable por código |
| RR-01 (claves del productor) | — | Solo productor sintético | No verificable para productores reales en I-1 |

## 6. Lo que este veredicto no dice

- No dice que el diseño v3.2 sea correcto. Dice que no hay P0 conocidos sin una solución documentada, y que los P0 conocidos solo están corregidos en papel.
- No dice que una prueba haya pasado: ninguna existe.
- No dice nada sobre viabilidad comercial ni ventaja estadística (NO EDGE).
- No autoriza M1, código, migraciones, fusiones ni despliegues. Todo sigue pendiente de DP-01…DP-05.
