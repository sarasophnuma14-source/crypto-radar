# I-1 v3 · Matriz de decisiones

Fecha: 18-nov-2026. Ninguna decisión de este documento está aprobada. «Propietario» = decisión que corresponde a PATRON; «Técnica» = recomendación del comité. No se convierte ninguna propuesta en aprobada.

## 1. Decisiones recomendadas

| Id | Decisión | Sustituye o precisa | Recomendación | Justificación | Tipo | Estado |
|---|---|---|---|---|---|---|
| DV3-01 | Ledger por **preparar → publicar** con contador sin huecos en fila y marca (W, H) | D-021 (v2) | Adoptar | V3-01, V3-03: v2 falsificable y apoyado en un detalle interno; la alternativa usa garantías documentadas | Técnica | Propuesta |
| DV3-02 | Modelo de roles `mr_owner`/`mr_migrator`/`mr_writer`/`mr_reader`/`mr_test_fixtures`; tablas versionadas sin escritura para roles con LOGIN; funciones `SECURITY DEFINER` con `search_path` fijo | Nuevo (aplica S-60) | Adoptar | V3-02 | Técnica | Propuesta |
| DV3-03 | Cadena de hashes en `write_log` para detectar manipulación administrativa | Nuevo | Adoptar | V3-17; costo bajo | Técnica | Propuesta |
| DV3-04 | Matriz temporal de `I1_TEMPORAL_MODEL.md`; lecturas solo por `_asof(W, H)`; atributos definitorios del instrumento inmutables | Precisa D-008 | Adoptar | V3-05, V3-20 | Técnica | Propuesta |
| DV3-05 | Licencias: modelo completo de campos, «desconocido = restrictivo», comprobaciones por momento | Precisa D-010, D-023 | Adoptar | V3-12 | Técnica | Propuesta |
| DV3-06 | Sintéticos por `namespace` + rol + instancia inmutable; el nombre no da privilegios | D-023 (v2) | Adoptar | V3-11 | Técnica | Propuesta |
| DV3-07 | Crudos: persistir cuerpo decodificado + huella de transporte; JSON estricto; rechazos guardados | D-024 (v2) | Adoptar | V3-13 | Técnica | Propuesta |
| DV3-08 | Velas: `price_domain`, `price_kind`, `price_basis`, `volume` nulo + `volume_kind`, `numeric` sin modificador; hash `c2` | v2 §5.5, D-024 | Adoptar | V3-07, V3-08, V3-09, V3-14 | Técnica | Propuesta |
| DV3-09 | Calendario con `trading_date` e intervalos; `Timeframe` sin `align`; política de alineación por proveedor | v2 §4.1, §4.3 | Adoptar | V3-10 | Técnica | Propuesta |
| DV3-10 | Conexión solo por socket Unix en I-1; limpieza de `PG*`; suite en espacio de red aislado | D-026 (v2) | Adoptar | V3-06 | Técnica | Propuesta |
| DV3-11 | Migraciones transaccionales con manifiesto, sin `CASCADE`, `down` solo en instancia `test` | D-022 (parte de reversión) | Adoptar | V3-04, V3-15 | Técnica | Propuesta |
| DV3-12 | Hito M1 (integridad) con revisión del propietario antes de continuar | Nuevo | Adoptar | Evidencia ejecutada antes de construir encima | Técnica | Propuesta |

D-022 (instalación de `btree_gist` sin superusuario), D-025 (reglas de fuentes) y D-027 (fórmula cambiaria) se **mantienen** como propuestas; DV3-11 solo cambia la parte de reversión de D-022.

## 2. Decisiones del propietario

| Id | Pregunta | Opciones | Recomendación técnica |
|---|---|---|---|
| DP-01 | ¿Se autoriza escribir código? | (a) Solo el hito M1; (b) I-1 completo; (c) No por ahora | (a): produce evidencia en ≈ 12,5 días con el menor riesgo |
| DP-02 | ¿Se aprueban DV3-01…DV3-12? | Todas / algunas / ninguna | Todas; las que se rechacen deben sustituirse por otra solución al hallazgo correspondiente |
| DP-03 | ¿CI en GitHub Actions solo para Market Radar? | Sí / No | Sí si se quiere evidencia independiente del entorno local; implica un archivo nuevo en `.github/` |
| DP-04 | ¿El código empieza antes de cerrar la Fase 0 de la 2.1? | Sí, sin fusionar / No | Sí, sin fusionar: no comparte nada con la 2.1 |

## 3. Decisiones que siguen abiertas (no se pueden cerrar con documentos)

| Tema | Qué falta |
|---|---|
| Suficiencia legal de cualquier licencia | Contratos reales (F0-11 para cripto; ninguno para otros mercados) |
| Rendimiento del ledger con volúmenes reales | Medición en I-2 |
| Instancia `production` y su procedimiento | Diseño en I-2 |
| `btree_gist` en Neon | NO VERIFICADO; irrelevante para I-1 |
| Disponibilidad de `unshare` o contenedor sin red en el entorno de desarrollo | Comprobar al empezar T02 |

## 4. Decisiones que se mantienen sin cambios

Monolito modular (D-005), paquete aislado (D-006), esquema propio (D-007, con base separada según ARCHITECTURE_REVIEW §4), sin Redis/colas/microservicios, NO EDGE como referencia (D-002), restricciones de §19 (D-004).
