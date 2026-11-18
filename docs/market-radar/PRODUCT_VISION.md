# Visión de producto · Market Radar

Versión 1.0 · 18 de noviembre de 2026 · Estado: dirección aprobada por el propietario; implementación **no** aprobada.
Producto de origen: Crypto Radar 2.1.

## 1. Qué es

Market Radar es una plataforma de **inteligencia de mercado multiactivo** para investigar y seguir mercados. Vigila ocho universos (cripto, acciones, ETF, forex, metales preciosos, índices, energía y agrícolas), describe en qué estado está cada activo, muestra la evidencia que sostiene cada observación y dice qué la invalidaría.

No es una plataforma de señales de compra y venta, no ejecuta órdenes y no promete rentabilidad.

## 2. Las cinco preguntas

| Pregunta | Dónde se responde |
|---|---|
| ¿Qué está pasando en los mercados? | Dashboard y Global Radar (régimen, fortaleza relativa, volatilidad, correlaciones) |
| ¿Qué activos presentan configuraciones interesantes? | Scanner (Motor A) y ranking por mercado |
| ¿En qué etapa está cada uno? | Estado observado (compresión, señal temprana, confirmación, tendencia, expansión, agotamiento, invalidado, sin datos) |
| ¿Qué evidencia lo respalda? | Ficha de activo (Motor B): datos, indicadores, procedencia, frescura y versión de cálculo |
| ¿Qué riesgos e invalidaciones hay? | Risk Engine y escenarios con condiciones explícitas de invalidación |

## 3. Para quién

| Perfil | Necesidad | Qué no le damos |
|---|---|---|
| Inversor minorista autodidacta (hispanohablante, hoy el público de Crypto Radar) | Un lugar para vigilar varios mercados con explicaciones en su idioma | Recomendaciones personalizadas ni promesas |
| Analista o creador de contenido independiente | Comparar mercados, exportar observaciones con fuente y fecha | Datos redistribuibles sin licencia |
| Usuario de cartera propia | Ver exposición, concentración y correlaciones de lo que ya tiene | Órdenes ni conexión a brókeres |

Fuera de alcance: profesionales regulados que requieren datos de nivel institucional (cambiarían la clasificación de licencias, ver `DATA_LICENSE_MATRIX.md`), gestores de terceros y trading algorítmico.

## 4. Propuesta de valor

1. **Una sola vista coherente** de mercados distintos, con las mismas reglas de calidad, estado y riesgo aplicadas a cada uno, respetando sus diferencias (sesiones, vencimientos, unidades).
2. **Evidencia antes que opinión:** cada estado muestra qué datos lo produjeron, cuándo, de qué proveedor y con qué versión del cálculo.
3. **Honestidad sobre lo que no se sabe:** si un dato es viejo, falta o no tiene licencia, el sistema lo dice y no clasifica.
4. **Historial auditable:** cada observación queda registrada con su resultado posterior, también cuando sale mal.
5. **IA que explica, no que inventa:** los resúmenes se construyen solo con resultados verificados y citan fuente y fecha.

## 5. Principios (orden de prioridad)

1. Calidad de datos antes que cantidad de activos.
2. Evidencia antes que predicciones.
3. Gestión de riesgo antes que señales.
4. Trazabilidad antes que automatización.
5. Modularidad antes que acoplamiento.
6. Validación estadística antes que afirmaciones de ventaja.
7. Transparencia sobre limitaciones.
8. Seguridad y privacidad desde el diseño.

Cuando dos principios chocan, gana el de número menor. Ejemplo: si añadir 2.000 acciones obliga a usar una fuente de calidad dudosa, se añaden menos acciones.

## 6. Punto de partida honesto

- La investigación vigente es **NO EDGE**: 35 configuraciones pre-registradas en la ronda v3, holdout usado una vez, ninguna familia con ventaja. El motor de la 2.1 tiene Sharpe fuera de muestra −0,30.
- Market Radar **no hereda ninguna afirmación de ventaja**. Los estados y el score describen configuraciones; no predicen.
- La 2.1 tiene pendientes de seguridad y operación (Fase 0) que van antes que cualquier funcionalidad nueva.
- Los datos multiactivo con derechos de visualización comercial cuestan órdenes de magnitud más que los datos cripto (ver `MULTI_ASSET_UNIT_ECONOMICS.md`). Esto condiciona el orden de los mercados.

## 7. Qué significa éxito

| Horizonte | Señal de éxito | Señal de fracaso |
|---|---|---|
| Fase 2 | Cripto migrado al núcleo nuevo con los mismos resultados que la 2.1 en un escaneo paralelo, cero huecos sin alerta | Divergencias inexplicadas entre núcleo y 2.1 |
| Fase 3 | Acciones/ETF con licencia confirmada y calidad medida ≥ umbral durante 30 días | Activar un mercado sin licencia o con calidad no medida |
| Fase 8 | Historial de observaciones con resultados posteriores publicado, incluidos los negativos | Mostrar solo aciertos |
| Negocio | Usuarios del piloto que vuelven cada semana y dicen que la vista multiactivo les sirve | Uso dependiente de "señales" que el sistema no puede respaldar |

## 8. Qué no haremos

- Ejecución real de operaciones ni conexión a brókeres.
- Probabilidades de ganancia sin evento, horizonte y calibración validados fuera de muestra.
- Apalancamiento, recomendaciones personalizadas o lenguaje de garantía.
- Mostrar datos de un proveedor sin derecho contractual de visualización.
- Mezclar spot, futuros, ETF e índices como si fueran el mismo instrumento.
- Activar pagos, cambiar precios o lanzar oferta pública en esta etapa.

## 9. Nombre y relación con Crypto Radar

Crypto Radar 2.1 sigue siendo el producto en piloto y no cambia. Market Radar es su evolución: el universo cripto será el primero en migrar al núcleo nuevo, y solo cuando dé los mismos resultados que la 2.1 se podrá plantear sustituirla. Marca, dominio y registro del nombre "Market Radar" están **pendientes** de comprobación (posibles conflictos de marca NO VERIFICADOS).
