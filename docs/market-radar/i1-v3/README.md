# I-1 v3 · Informe ejecutivo de la auditoría crítica

Fecha: 18-nov-2026. Rama documental `claude/project-thread-dclqgc` (PR #16 en borrador). Esta revisión **solo añade** esta carpeta: ningún archivo existente se modificó, no hay código, no se fusionó ni desplegó nada. Market Radar sigue teniendo **0 líneas de código**.

**Evidencia:** las comprobaciones citadas como «EXP» son consultas SQL desechables ejecutadas el 18-nov en un PostgreSQL 16.15 local temporal, borrado al terminar. No son implementación ni pruebas de integración.

## Documentos

| # | Documento | Contenido |
|---|---|---|
| 1 | [I1_CRITICAL_REVIEW.md](I1_CRITICAL_REVIEW.md) | 25 hallazgos (6 P0, 9 P1, 7 P2, 3 P3) con evidencia, corrección, prueba y estado |
| 2 | [I1_LEDGER_REDESIGN.md](I1_LEDGER_REDESIGN.md) | Permisos, publicación, marca (W, H), alternativas, recuperación, ataques |
| 3 | [I1_TEMPORAL_MODEL.md](I1_TEMPORAL_MODEL.md) | Matriz entidad × temporalidad, 9 escenarios, política de consulta histórica |
| 4 | [I1_LICENSE_ENFORCEMENT.md](I1_LICENSE_ENFORCEMENT.md) | Matriz uso × momento, 14 casos, técnico frente a contractual |
| 5 | [I1_SECURITY_THREAT_MODEL.md](I1_SECURITY_THREAT_MODEL.md) | 7 actores, 15 casos adversariales, sintéticos, red |
| 6 | [I1_DATA_CONTRACT_REVIEW.md](I1_DATA_CONTRACT_REVIEW.md) | Instrument, Candle, Timeframe, Session, crudos, hash `c2` |
| 7 | [I1_TEST_STRATEGY_V3.md](I1_TEST_STRATEGY_V3.md) | 15 grupos, ≈ 179 casos, controles negativos |
| 8 | [I1_IMPLEMENTATION_PLAN_V3.md](I1_IMPLEMENTATION_PLAN_V3.md) | Arquitectura, 11 migraciones, reversión segura, 14 tareas, hito M1, ≈ 30 días |
| 9 | [I1_DECISION_MATRIX.md](I1_DECISION_MATRIX.md) | DV3-01…12 (técnicas, propuestas) y DP-01…04 (del propietario) |
| 10 | [I1_ACCEPTANCE_V3.md](I1_ACCEPTANCE_V3.md) | Veredicto y criterios objetivos |

## Respuestas

**1. ¿Qué tan sólido es I-1 v2?** La dirección es buena, el mecanismo no. v2 acierta en aislamiento, bitemporalidad, separación crudo/canónico y licencias en base, pero tiene **6 problemas P0**: el ledger se puede falsificar con los permisos que el propio plan da a la aplicación, la garantía de orden se apoya en un detalle interno no documentado, la reversión puede borrar objetos ajenos, la historia solo cubre velas y fuentes, y la guardia de red se puede saltar. No debe implementarse tal como está.

**2. Los tres riesgos más importantes.**
1. Historia reescribible (V3-01, V3-02). EXP: en una réplica de v2, la lectura de la versión 1 pasó de `{1}` a `{99}` con `set_config` + `INSERT`, `UPDATE` directo y desactivación del disparador, sin ningún error.
2. Reproducciones que mezclan velas antiguas con metadatos actuales (V3-05).
3. Conexiones fuera de lo local pese a la guardia (V3-06). EXP: `host=localhost hostaddr=192.0.2.1` y `PGHOSTADDR` llevaron libpq a 192.0.2.1.

**3. Decisiones que deben cambiar.** Ledger (preparar → publicar, contador sin huecos, (W, H)); modelo de roles y funciones `SECURITY DEFINER`; temporalidad de todo el registro; sintéticos por espacio de nombres, rol e instancia; contrato de velas (precios negativos, volumen ausente, tipo de precio, base de ajuste, `numeric` sin límite); calendarios con sesiones de varios intervalos; conexión solo por socket Unix con prueba de red a nivel de sistema; migraciones con manifiesto y sin `CASCADE`.

**4. Decisiones que pueden mantenerse.** Monolito modular en Python, paquete aislado sin `radar/`, PostgreSQL 16 local, sin proveedores, red, IA, señales, UI ni despliegue; exclusiones con `btree_gist` sin superusuario; reglas de selección de fuente; ningún interruptor de entorno para licencias; NO EDGE como referencia.

**5. Qué falta para iniciar la implementación.** Que el propietario apruebe (o sustituya) DV3-01…12 y autorice expresamente escribir código. Para el veredicto READY FOR FOUNDATION falta además la evidencia ejecutada del hito M1 (`I1_ACCEPTANCE_V3.md` §3).

**6. Trabajo adicional.** ≈ 13 días sobre v2: I-1 pasa de ≈ 17 a **≈ 30 días** (rango 25–36). El hito M1 (integridad) son ≈ 12,5 días.

**7. Pruebas imprescindibles.** TS-ADV (ataques al ledger), TS-CONC con control negativo, TS-PRIV (inventario de privilegios), TS-MIG (ida y vuelta con objetos ajenos), TS-NET dentro de un espacio de red aislado y TS-REPRO contra una implementación de referencia.

**8. Riesgos que quedan abiertos.** Administradores de base (solo detección por cadena de hashes); errores en funciones privilegiadas; rendimiento real del ledger; suficiencia legal de cualquier licencia; `btree_gist` en Neon (NO VERIFICADO); disponibilidad de un espacio de red aislado en el entorno de desarrollo.

**9. Veredicto final.** **NO READY.** Los P0 están corregidos solo en documentos. Según tu regla, READY FOR FOUNDATION exige evidencia ejecutada que todavía no existe.

**10. Siguiente paso recomendado.** Autorizar solo el **hito M1** (≈ 12,5 días: conexión, migraciones, roles, ledger y sus pruebas adversariales y de concurrencia) en una rama nueva, sin fusionar, y revisar su evidencia antes de autorizar el resto.

## Tabla de decisiones

| Decisión | Recomendación | Estado |
|---|---|---|
| Arquitectura modular | **Mantener** | Propuesta vigente (D-005, D-006) |
| Ledger | **Rediseñar** (DV3-01, DV3-02, DV3-03) | Propuesta; requiere aprobación |
| Bitemporalidad | **Rediseñar** (DV3-04) | Propuesta; requiere aprobación |
| Modelo de licencias | **Modificar** (DV3-05, DV3-06) | Propuesta; requiere aprobación |
| Modelo de activos | **Modificar** (atributos definitorios inmutables, sucesiones) | Propuesta; requiere aprobación |
| Modelo de velas | **Modificar** (DV3-08) | Propuesta; requiere aprobación |
| Calendarios | **Modificar** (DV3-09) | Propuesta; requiere aprobación |
| Seguridad de conexión | **Modificar** (DV3-10) | Propuesta; requiere aprobación |
| Migraciones | **Modificar** (DV3-11) | Propuesta; requiere aprobación |
| Inicio de I-1 | **No autorizar I-1 completo; autorizar solo el hito M1** | Pendiente de decisión del propietario |
