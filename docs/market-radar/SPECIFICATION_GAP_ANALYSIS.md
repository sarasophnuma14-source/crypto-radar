# Análisis de brechas de la especificación · Market Radar

Fecha: 18-nov-2026. Revisión crítica de los 14 documentos de `docs/market-radar/` (commit `e5a488f` de la rama `claude/project-thread-dclqgc`, primera entrega).
Revisor: el mismo equipo (Claude) que los escribió, actuando como comité independiente. Para compensar ese conflicto de interés, cada hallazgo cita el documento y la sección, y se contrastó con el código o con una fuente externa cuando fue posible.

## Clasificación

| Tipo | Código |
|---|---|
| Contradicción | CON |
| Requisito incompleto | INC |
| Decisión sin justificación | JUS |
| Dependencia omitida | DEP |
| Riesgo no identificado | RSK |
| Estimación sin fórmula | FOR |
| Criterio de aceptación ambiguo | AMB |
| Requisito no verificable objetivamente | VER |

Severidad: **B** = bloquea el primer incremento técnico (I-1) · **F** = debe resolverse antes de la fase que lo usa · **m** = menor.

## Resumen

| Tipo | Hallazgos | Bloqueantes para I-1 |
|---|---|---|
| CON | 9 | 3 |
| INC | 9 | 2 |
| JUS | 4 | 1 |
| DEP | 7 | 1 |
| RSK | 9 | 0 |
| FOR | 4 | 0 |
| AMB | 6 | 1 |
| VER | 5 | 0 |
| **Total** | **53** | **8** |

Los 8 bloqueantes tienen una corrección propuesta en este documento y se incorporan al plan de I-1 (`PHASE_1_IMPLEMENTATION_PLAN.md`). Ninguno exige tocar producción.

---

## 1. Contradicciones (CON)

| Id | Sev. | Dónde | Contradicción | Corrección propuesta |
|---|---|---|---|---|
| CON-01 | **B** | `MULTI_ASSET_ROADMAP` Fase 0 y Fase 2; `RISK_REGISTER` R-04; `AUDIT` §9 | La Fase 0 es requisito de entrada de la Fase 2, pero el propietario ahora pide un primer incremento técnico. Si se aplica literalmente, I-1 no puede empezar hasta cerrar P0 que dependen del propietario (TOTP, rotación, repo privado) | Separar dos compuertas: **Fase 0 bloquea fusionar, integrar y desplegar**; no bloquea código aislado en una rama sin acceso a producción. I-1 puede empezar con autorización; su PR no se fusiona hasta cerrar la Fase 0 |
| CON-02 | **B** | `MULTI_ASSET_ROADMAP` vs. solicitud actual | El roadmap llama "Fase 1" al diseño y "Fase 2" al núcleo; la solicitud pide `PHASE_1_IMPLEMENTATION_PLAN`. Dos significados de "Fase 1" | El plan se titula como pide el propietario, pero el incremento se llama **I-1** y pertenece a la Fase 2 (núcleo) del roadmap. Se dice explícitamente en el plan |
| CON-03 | **B** | `TARGET_ARCHITECTURE` §4 ("importar `radar/auth.py` tal cual; misma tabla `users`") vs. D-006 ("sin modificar `radar/`") y `ASSET_DATA_MODEL` §7 | Importar `radar/` acopla los despliegues de Market Radar a la 2.1 (la 2.1 degrada administradores y archiva usuarios en cada arranque, `docs/REGISTRO_USUARIOS_PILOTO.md`). Una FK de `mr` a `app.users` ata las migraciones de `mr` al ciclo de vida del esquema `app` | I-1 **no importa nada de `radar/`** (comprobado por prueba). Usuarios fuera de alcance de I-1. Cuando se necesiten: identificador opaco `user_ref` sin FK entre esquemas, y un único módulo `market_radar/compat/` autorizado a importar `radar/` |
| CON-04 | F | `PRODUCT_REQUIREMENTS` RS-01, RS-05, RS-06 | (a) Con "evidencia histórica" fija en 0 y pesos que suman 100, el máximo es < 100 sin regla de renormalización. (b) La calidad de datos es a la vez **compuerta** (RS-05) y **componente** (RS-01): se cuenta dos veces | Definir: score = Σ wᵢ·cᵢ / Σ wᵢ sobre componentes **activos**; la calidad es solo compuerta y factor de confianza separado, no componente |
| CON-05 | F | `SECURITY` S-11 ("claves solo en el worker; la web no las recibe") vs. D-005 ("worker separado solo si la medición lo justifica") | Mientras haya un solo servicio, S-11 es imposible | El worker separado se justifica también por **aislamiento de secretos**, no solo por carga. Se crea al activar el primer proveedor con clave, aunque la CPU no lo exija (ver `ARCHITECTURE_REVIEW` §9) |
| CON-06 | m | `ASSET_DATA_MODEL` §8 ("hash encadenado **opcional**") vs. `SECURITY` S-06 ("con hash encadenado") | Obligatorio en un documento, opcional en otro | Obligatorio para: licencias, mercados habilitados, versiones de modelo y accesos administrativos; opcional para el resto |
| CON-07 | m | `IMPLEMENTATION_BACKLOG` Q-3 ("300 series cripto") vs. `radar/config.py:55` (`universe_size: 150`) | El universo por defecto de la 2.1 es 150 | Usar "el universo del último escaneo de la 2.1 (por defecto 150)" |
| CON-08 | F | `QUANT_RESEARCH_PROTOCOL` §5 (tabla de costos propia) vs. `research/prospectivo/costes.py` (rama `claude/investigacion-prospectiva`) | El módulo existente modela comisión por exchange, semiespread por nivel (BTC/ETH 0,005 %, resto 0,25 %), deslizamiento 0,02 %, impacto k·σ·√participación y latencia de 1 barra; el protocolo propone otras cifras (p. ej. cripto pequeñas 0,30–1,00 %) sin impacto ni latencia | El protocolo debe **reutilizar `ModeloCostes`** para cripto y extender su estructura a otras clases, no redefinir cifras |
| CON-09 | m | `AUDIT` §6 | La tabla de PR no incluye la **PR #15** (respaldos independientes, borrador, rama `claude/respaldos-independientes`), que resuelve parte de P1-5/S0-6 | Añadirla a la Fase 0 |

## 2. Requisitos incompletos (INC)

| Id | Sev. | Dónde | Falta | Corrección |
|---|---|---|---|---|
| INC-01 | **B** | `ASSET_DATA_MODEL` §4 `asset_identifiers` | La clave única (`scheme`,`value`,`provider_id`,`valid_from`) permite **rangos de vigencia solapados**: el mismo ticker podría resolver a dos instrumentos a la vez | Restricción de exclusión con `tstzrange(valid_from, valid_to)` y `btree_gist`; prueba de colisión |
| INC-02 | **B** | `ASSET_DATA_MODEL` §5 `candles` + `PRODUCT_REQUIREMENTS` NF-04 | NF-04 exige reproducir un `scan_run` con los mismos datos, pero `candles` se actualiza en sitio: una corrección del proveedor borra la versión anterior | Persistencia **bitemporal**: `recorded_at` y `superseded_at` por fila; cada `scan_run` guarda una marca de agua de datos (`data_watermark`). Ver `ARCHITECTURE_REVIEW` §8 |
| INC-03 | F | `ASSET_DATA_MODEL` §5 | No hay regla de **fuente primaria** por instrumento cuando dos proveedores entregan la misma vela | Tabla `instrument_sources` (instrumento, proveedor, prioridad, vigencia); los motores leen solo la primaria; las demás sirven para validación cruzada |
| INC-04 | F | `PRODUCT_REQUIREMENTS` RA-05 | Los nueve estados están nombrados pero **no definidos**: no hay reglas de entrada ni de salida, ni histéresis | Especificación de la máquina de estados antes de la Fase 3, con tabla de transiciones y casos de prueba |
| INC-05 | F | `PRODUCT_REQUIREMENTS` RB-03 | "Soportes y resistencias estimados" sin algoritmo | Definir el método (pivotes confirmados, como `radar/quant/features.py`) y su versión |
| INC-06 | F | `ASSET_DATA_MODEL` §5 `corporate_actions` | Los tipos no cubren eventos cripto: migración de token, redenominación, cambio de ticker por *rebrand*, *airdrop* de nuevo token, deslistado por exchange | Añadir `token_migration`, `redenomination`, `rebrand` |
| INC-07 | F | `PRODUCT_REQUIREMENTS` §1 | No hay requisito de **conversión de moneda**: comparar DAX (EUR) con S&P (USD) exige tipos de cambio con licencia | Nuevo RD-13: toda comparación entre monedas declara fuente FX y hora de fijación; dependencia de la Fase 4 adelantada si hay acciones no USD |
| INC-08 | m | `ASSET_DATA_MODEL` §4 | `instruments.calendar_id` y `markets.calendar_id`: no se dice cuál prevalece | El del instrumento; el del mercado es el valor por defecto |
| INC-09 | m | `PRODUCT_REQUIREMENTS` RT-03 | "Límite de frecuencia" sin número | Proponer: máx. 10 alertas/usuario/hora y 1 por (activo, tipo) cada 4 h, configurable |

## 3. Decisiones sin justificación (JUS)

| Id | Sev. | Decisión | Qué falta | Corrección |
|---|---|---|---|---|
| JUS-01 | **B** | D-007 esquema `mr` en la **misma base** que la 2.1 | No se analiza que comparten cómputo de Neon, almacenamiento, copias y roles con producción: una carga de ingesta mal hecha degrada la 2.1 | Hasta la Fase 3: base separada (proyecto o rama de Neon distinta) para `mr`; en I-1, **solo PostgreSQL local**. Ver `ARCHITECTURE_REVIEW` §4 |
| JUS-02 | F | D-013 ETF proxy "sin costo adicional" | Mostrar un ETF también requiere licencia de visualización del proveedor de acciones y, potencialmente, tarifas de bolsa | Reescribir: "sin costo adicional **una vez licenciadas las acciones/ETF**" |
| JUS-03 | m | D-012 holdout de 24 meses | No se justifica la longitud ni la potencia estadística | Ver `QUANT_VALIDATION_REVIEW` §4 |
| JUS-04 | m | Tamaños S/M/L del backlog | Sin base de estimación | Se mantienen como relativos; I-1 se estima en el plan con desglose |

## 4. Dependencias omitidas (DEP)

| Id | Sev. | Dependencia | Afecta | Corrección |
|---|---|---|---|---|
| DEP-01 | **B** | Herramienta de migraciones: la 2.1 usa `CREATE TABLE IF NOT EXISTS` + lista de columnas (`radar/db.py`), sin historial ni reversión | I-1 | Migraciones SQL numeradas con tabla `mr.schema_migrations` (versión, checksum, aplicado_en) y scripts `down`, sin dependencias nuevas |
| DEP-02 | F | Fuente de festivos y sesiones (no hay biblioteca ni datos elegidos) | Calendarios | Evaluar `exchange_calendars` (código abierto; licencia y exactitud **NO VERIFICADAS**) o tablas propias; en I-1 solo 24/7 y un calendario de prueba |
| DEP-03 | F | Observabilidad mínima para medir la salida de la Fase 0 ("7 días sin huecos no alertados") | Fase 0 | Es circular: la 2.1 no tiene detector de huecos. Opción barata: comprobar desde fuera el campo de último escaneo de `/healthz` (ya existe) con un monitor externo gratuito |
| DEP-04 | F | Monitor externo de disponibilidad para NF-01 (99 %) | NF-01 | Render no publica disponibilidad por servicio; hace falta un sondeo externo |
| DEP-05 | F | Historial de composición de índices (p. ej. miembros del S&P 500 por fecha) para universos sin sesgo de supervivencia y "amplitud" | Fase 3–6, investigación | Es dato licenciado del proveedor del índice; añadir a la matriz de licencias |
| DEP-06 | F | `coverage.py` (o similar) para NF-08 "cobertura ≥ 90 %" | CI | Dependencia de desarrollo; no entra en producción |
| DEP-07 | m | `btree_gist` (extensión de PostgreSQL) para INC-01 | I-1 | Disponible en PostgreSQL 16 y en Neon (**NO VERIFICADO en Neon**; en I-1 solo se usa local) |

## 5. Riesgos no identificados (RSK)

| Id | Riesgo | Por qué importa | Mitigación propuesta |
|---|---|---|---|
| RSK-01 | **Moneda**: ingresos en COP vía Wompi, costos de datos en USD | Una devaluación del COP sube el equilibrio sin que cambie nada más | Escenario de sensibilidad (ECONOMIC_REVIEW §6) |
| RSK-02 | **Regulatorio**: que un producto de estados y scores se considere asesoría de inversión en Colombia u otros países | Puede exigir licencia o cambiar la oferta | Consulta legal antes de cualquier oferta pública (**NO VERIFICADO**) |
| RSK-03 | **Persona clave**: un propietario y asistentes de IA; nadie más conoce el sistema | Continuidad | Runbooks y documentación operacional en la tercera entrega |
| RSK-04 | **Cláusulas de destrucción**: algunos términos obligan a destruir copias al terminar (FRED lo exige para su API) | Reproducibilidad de la investigación tras cancelar un proveedor | Registrar en `provider_licenses` si los datos sobreviven a la cancelación |
| RSK-05 | **Contaminación del holdout por conocimiento general**: el propietario y el modelo conocen la historia reciente del mercado (2024–2026) | "Virgen" no significa "no visto" | Declarar y limitar; ver QUANT_VALIDATION_REVIEW §4 |
| RSK-06 | **Datos personales hacia el proveedor de IA** (carteras) | Privacidad y retención del proveedor | Ya hay S-43; añadir revisión de retención del proveedor antes de Fase 7 |
| RSK-07 | **Base compartida con producción** (ver JUS-01) | Degradación de la 2.1 | Base separada |
| RSK-08 | **Conflictos de ramas**: varias ramas parten de `release-2.1` y otros hilos la tocan | Integración | I-1 en paquete y carpeta nuevos, sin tocar archivos existentes |
| RSK-09 | **Repositorio público** expone diseño y plan comercial completos | Competencia, reconocimiento | Ya en Fase 0 (P0-6); se recuerda que estos documentos también quedan públicos |

## 6. Estimaciones sin fórmula (FOR)

| Id | Dónde | Estimación | Fórmula que faltaba |
|---|---|---|---|
| FOR-01 | `TARGET_ARCHITECTURE` §8 | "≈120 B/fila con índice" | Fila ≈ cabecera de tupla 24 B + claves (uuid 16, texto proveedor ~12, temporalidad ~4, 2 × timestamptz 16) + 6 numéricos (~8–12 B c/u) + procedencia (~40 B) ≈ **170–200 B**; índice PK ≈ 60–80 B. Total ≈ **250 B/fila**. La estimación anterior subestimaba ~2×. Ver ECONOMIC_REVIEW §5 |
| FOR-02 | `MULTI_ASSET_UNIT_ECONOMICS` §2 | Neon Launch US$19,70 | Neon Launch no tiene mínimo mensual (PÚBLICO, neon.com/pricing, consultado 18-nov-2026): costo = CU-h × 0,106 + GB-mes × 0,35 + transferencia > 500 GB × 0,10. US$19,70 ≈ 186 CU-h ≈ 0,25 CU encendido todo el mes |
| FOR-03 | `MULTI_ASSET_UNIT_ECONOMICS` §3 | Costo de IA "PENDIENTE" | Costo = Σ (tokens de entrada × precio de entrada + tokens de salida × precio de salida). Ver ECONOMIC_REVIEW §4 |
| FOR-04 | `TARGET_ARCHITECTURE` §9 | Umbrales para crear worker (50 % CPU, 400 MB) | Sin derivación; razonables como punto de partida pero deben ligarse a la medición de Render del 16-nov (110–147 MB en reposo, 345 MB con 100 usuarios locales) |

## 7. Criterios ambiguos (AMB)

| Id | Sev. | Criterio | Ambigüedad | Versión verificable propuesta |
|---|---|---|---|---|
| AMB-01 | **B** | Fase 2: "diferencias de estado por activo explicadas al 100 %" | "Explicada" no es medible | (a) Indicadores portados: diferencia absoluta ≤ 1e-9 en 100 % de los puntos; (b) estados: solo se comparan cuando el motor es la misma versión; (c) cada diferencia restante se clasifica en una categoría cerrada (dato distinto, calendario, versión) y queda en un informe |
| AMB-02 | F | §18 punto 5 y Fase 3: "calidad de datos medida (≥ 30 días)" | No dice qué métrica ni qué umbral | Umbrales de `DATA_QUALITY_TEST_PLAN` §4 (completitud, frescura, coherencia, discrepancia entre proveedores) cumplidos 30 días seguidos |
| AMB-03 | F | RD-06 frescura "umbral" | Sin número | Por temporalidad: diaria → degradado a 1 sesión de retraso, sin clasificar a 2; intradía → degradado a 2 barras, sin clasificar a 4 (propuesta) |
| AMB-04 | F | RD-07 "umbral de liquidez de su clase" | Sin número | Tabla por clase en `DATA_QUALITY_TEST_PLAN` §4 (p. ej. cripto ≥ US$2 M/día de volumen medio de 30 días, igual que `radar/edge/features.universe`) |
| AMB-05 | m | Fase 0: "7 días de escaneos sin huecos no alertados" | ¿Qué es un hueco? | Intervalo entre escaneos completados > 2 × 4 h |
| AMB-06 | m | NF-03 "p95 < 1,5 s con datos en caché" | ¿Qué es "en caché"? | Medido con la base precargada y sin llamadas a proveedores |

## 8. Requisitos no verificables (VER)

| Id | Requisito | Problema | Reformulación |
|---|---|---|---|
| VER-01 | QUANT_PROTOCOL §4: holdout "virgen (nadie del proyecto lo ha mirado)" | No hay forma de comprobar que nadie miró | Holdout "**bloqueado**": candado creado antes de descargar el tramo; el registro prueba que ningún experimento lo leyó, no que nadie lo vio |
| VER-02 | RI-06 "toda cifra debe coincidir con un dato de la entrada" | Porcentajes o diferencias calculados por la IA no aparecen en la entrada | La IA no calcula: solo cita cifras recibidas; los derivados se calculan antes y se pasan como entrada |
| VER-03 | PRODUCT_VISION §7 "usuarios que vuelven y dicen que les sirve" | Sin métrica | Usar las métricas del piloto (PR #14): activación, retención 30 días, encuesta |
| VER-04 | RU-06 "Accesibilidad AA" | Verificable solo con herramienta | Prueba automática de contraste y navegación por teclado en CI (Fase 3) |
| VER-05 | PRODUCT_VISION §7 Fase 8 "historial publicado" | Puede chocar con licencias que prohíben publicar datos derivados | Condicionarlo a `allows_derived_public` |

---

## 9. Bloqueantes para I-1 y su resolución

| Id | Resolución dentro de I-1 |
|---|---|
| CON-01 | Compuerta separada: I-1 es código aislado; su PR no se fusiona antes del cierre de Fase 0 |
| CON-02 | Nombre I-1, perteneciente a la Fase 2 |
| CON-03 | Prueba que impide importar `radar/` desde `market_radar/` |
| INC-01 | Restricción de exclusión de vigencias en la migración inicial |
| INC-02 | Modelo bitemporal desde la primera migración de `candles` |
| JUS-01 | I-1 solo usa PostgreSQL local; ninguna conexión a Neon |
| DEP-01 | Migraciones SQL versionadas con checksum y `down` |
| AMB-01 | Criterio de equivalencia numérica (se aplica en I-2, no en I-1, pero se fija ya) |

## 10. Qué no se cambió

Los 14 documentos originales **no se editaron**: este análisis funciona como fe de erratas. Si el propietario aprueba las correcciones, se aplicarán en un commit aparte con referencia a cada Id.
