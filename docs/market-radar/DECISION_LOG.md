# Registro de decisiones · Market Radar

Formato: cada decisión tiene estado **Aprobada** (por PATRON, con referencia), **Propuesta** (pendiente de PATRON), **Pendiente** (falta información) o **Sustituida**. Las decisiones no se borran; si cambian, se añade una nueva que sustituye a la anterior.

| Id | Fecha | Decisión | Estado | Fuente / responsable |
|---|---|---|---|---|
| D-001 | 18-nov-2026 | Market Radar es la dirección de producto de Crypto Radar (especificación v1.0) | **Aprobada** como dirección; implementación **no** aprobada | Especificación de PATRON, "Estado" |
| D-002 | 16-nov-2026 | Estado de investigación vigente: NO EDGE. Market Radar no hereda afirmaciones de ventaja | **Aprobada** | Especificación §13; ronda v3 |
| D-003 | 16-nov-2026 | Propuesta Pro US$15/mes o US$149/año como hipótesis de negocio; Élite aplazado; precios del backend sin cambiar; pagos apagados | **Aprobada** como hipótesis | Especificación §16 |
| D-004 | 18-nov-2026 | Restricciones: 2.1 estable, piloto cerrado, sin fusiones, despliegues, cambios de secretos, precios, holdout ni trading real; toda acción irreversible requiere al propietario | **Aprobada** | Especificación §19 |
| D-005 | 18-nov-2026 | **Monolito modular** en Python con dos procesos (web y worker) cuando la medición lo justifique; sin microservicios, colas ni Redis iniciales | **Propuesta** | TARGET_ARCHITECTURE §1, §9 |
| D-006 | 18-nov-2026 | Código nuevo en paquete `market_radar/` del mismo repositorio, sin modificar `radar/`; patrón *strangler* con ejecución en paralelo | **Propuesta** | TARGET_ARCHITECTURE §1, §3 |
| D-007 | 18-nov-2026 | Esquema PostgreSQL `mr` separado del esquema `app` de la 2.1; migraciones solo aditivas hasta Fase 8 | **Propuesta** | ASSET_DATA_MODEL |
| D-008 | 18-nov-2026 | Añadir entidades `instruments`, `series`, `roll_rules` (y `series_members`) a las de la especificación §11 para separar activo, instrumento y serie | **Propuesta** | ASSET_DATA_MODEL §1 |
| D-009 | 18-nov-2026 | Una sola biblioteca de indicadores causal para producto e investigación, con golden tests | **Propuesta** | AUDIT §4.6 |
| D-010 | 18-nov-2026 | `provider_licenses` como fuente de verdad aplicada en código; staging cuenta como visualización | **Propuesta** | DATA_LICENSE_MATRIX §4 |
| D-011 | 18-nov-2026 | Market Opportunity Score v1 descriptivo: componente "evidencia histórica" = 0 hasta que una hipótesis pase el protocolo | **Propuesta** | PRODUCT_REQUIREMENTS RS-06 |
| D-012 | 18-nov-2026 | Holdout nuevo por clase de activo (últimos 24 meses), bloqueado antes de descargar historial; cripto solo prospectivo | **Propuesta** | QUANT_RESEARCH_PROTOCOL §4 |
| D-013 | 18-nov-2026 | Índices y metales en fases tempranas vía ETF proxy etiquetado, hasta tener licencia del índice | **Propuesta** | DATA_PROVIDER_RESEARCH §7 |
| D-014 | 18-nov-2026 | No contratar proveedores de acciones/ETF hasta tener datos del piloto de la 2.1 y términos escritos | **Propuesta** | MULTI_ASSET_UNIT_ECONOMICS §6 |
| D-015 | 18-nov-2026 | Documentos de Market Radar en `docs/market-radar/`, rama `claude/project-thread-dclqgc` desde `release-2.1`, PR en borrador | **Aplicada** (sin efecto en producción) | Este hilo |
| D-016 | — | Proveedor de acciones/ETF (Twelve Data Venture vs Massive Business vs otro) | **Pendiente** | Requiere respuestas de proveedores |
| D-017 | — | Proveedor de velas cripto con uso comercial confirmado | **Pendiente** | F0-11 |
| D-018 | — | Proveedor de IA y presupuesto mensual | **Pendiente** | Fase 7 |
| D-019 | — | Marco legal de privacidad aplicable y datos del responsable | **Pendiente** | PATRON + abogado |
| D-020 | — | Uso público del nombre "Market Radar" | **Pendiente** | Búsqueda de marca |
| D-021 | 18-nov-2026 | Bitemporalidad por **secuencia de escritura** asignada bajo `pg_advisory_xact_lock`; marca de agua = `max(write_seq)`; `recorded_at` solo informativo. Sustituye la marca `MAX(recorded_at)` de ARCHITECTURE_REVIEW §8 | **Propuesta** | INC-10; ARCHITECTURE_REVIEW R2-1; plan I-1 v2 §5.3 |
| D-022 | 18-nov-2026 | `btree_gist` instalada por la migración 0001 en el esquema `mr` (o reutilizada si ya existe), sin superusuario; runner exige PostgreSQL 16 y rol no superusuario | **Propuesta** | DEP-08; R2-2; plan §5.1 |
| D-023 | 18-nov-2026 | Licencias sintéticas solo para mercados ficticios `zz-test-*`, impuesto por la base; sin variables de entorno en el `LicenseGuard`; proveedor sintético solo en `tests/`. Precisa D-010 | **Propuesta** | RSK-10; R2-3; plan §4.5, §5.2 |
| D-024 | 18-nov-2026 | Conservar los **bytes originales** de cada respuesta (`raw_payloads`) separados de la representación canónica (`candles`, codificación `c1`); retención por licencia | **Propuesta** | INC-11; R2-4; plan §4.4, §5.4 |
| D-025 | 18-nov-2026 | Fuentes por instrumento con prioridad 1–9, vigencia semiabierta, sin empates (exclusión en base), respaldo marcado `DEGRADED` y `NO_SOURCE` → `MISSING` | **Propuesta** | INC-03; R2-5; plan §4.2, §5.2 |
| D-026 | 18-nov-2026 | En pruebas, red bloqueada salvo socket Unix y loopback; en código, guardia que rechaza cualquier DSN no local durante I-1 | **Propuesta** | INC-12, INC-13; plan §3, §6.9, §6.13 |
| D-027 | 18-nov-2026 | La sensibilidad económica se calcula con la fórmula de ECONOMIC_REVIEW §7 (*f* = `COP_PER_USD` / TRM, diferencial bancario, moneda del soporte); cifras corregidas 70→69, 186→181, 773→751. No cambia precios | **Propuesta** | FOR-05, FOR-06; ECONOMIC_REVIEW §7 |

## Detalle de decisiones propuestas

### D-005 · Monolito modular
- **Contexto:** una persona, costos fijos altos de datos, ningún componente con necesidad de escala independiente medida.
- **Alternativas:** microservicios por motor (rechazada: costo operativo); seguir en `radar/` (rechazada: riesgo para producción).
- **Consecuencias:** despliegue simple; límites entre paquetes comprobados por prueba de importaciones; criterios numéricos para separar procesos.

### D-008 · Activo / instrumento / serie
- **Contexto:** la especificación exige distinguir índice, ETF y futuros, y no comparar vencimientos sin normalización.
- **Alternativas:** solo `assets` con un campo `kind` (rechazada: un activo tendría varios precios incompatibles en la misma tabla).
- **Consecuencias:** consultas de análisis más explícitas; rollover versionado y auditable.

### D-011 · Score sin evidencia histórica
- **Contexto:** IC del puntaje de la 2.1 negativo dentro y fuera de muestra; NO EDGE.
- **Consecuencias:** el score es una descripción ordenable, no una predicción; la interfaz lo dice.

### D-012 · Holdout por clase
- **Contexto:** el holdout cripto se usó una vez (v3) y quedan 58 pruebas acumuladas.
- **Consecuencias:** cualquier mirada al tramo holdout de una clase antes del pre-registro lo invalida y debe declararse.

### D-021 · Secuencia de escritura como marca de agua
- **Contexto:** reproducir un escaneo (NF-04) exige que «lo que se sabía en W» no cambie después. Con horas de inserción y transacciones concurrentes cambia (sandbox: 11/60 relecturas distintas).
- **Alternativas:** instantánea de transacción (`pg_current_snapshot`), correcta pero difícil de guardar y comparar; hora lógica híbrida, innecesaria con un nodo; tablas de preparación con publicación corta, plan B si la espera del candado supera 50 ms p95.
- **Consecuencias:** escrituras versionadas serializadas; marca de agua entera; prueba concurrente con control negativo en cada ejecución (sandbox con el diseño: 0/60).

### D-023 · Licencias sintéticas sin interruptor
- **Contexto:** una variable de entorno que habilita licencias de prueba es un riesgo de configuración en producción.
- **Alternativas:** marcar la base como «test/prod» al crearla (sigue siendo configuración); quitar la licencia sintética y probar sin licencias (no prueba el camino real).
- **Consecuencias:** la regla la impone el esquema; una licencia sintética no puede autorizar un mercado real en ninguna base, aunque se cuele.

### D-024 · Bytes originales y representación canónica
- **Contexto:** auditar o disputar un dato con el proveedor, o re-procesar con otra versión de adaptador, exige lo recibido exactamente.
- **Consecuencias:** más almacenamiento (acotado por la retención de la licencia); el adaptador debe poder re-procesar sus propios bytes con el mismo resultado.
