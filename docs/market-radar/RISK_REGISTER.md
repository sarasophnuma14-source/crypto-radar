# Registro de riesgos · Market Radar

Fecha: 18-nov-2026. Escala: Probabilidad (P) y Impacto (I) de 1 (bajo) a 5 (alto). Nivel = P × I. Responsable: P = PATRON, C = Claude, A = asesor externo.
Los riesgos de la 2.1 ya registrados en `docs/MATRIZ_RIESGOS_PENDIENTES.md` y en la auditoría de fase cero siguen vigentes; aquí se resumen los que bloquean Market Radar.

## 1. Riesgos críticos (nivel ≥ 15)

| Id | Riesgo | P | I | Nivel | Mitigación | Resp. | Disparador |
|---|---|---|---|---|---|---|---|
| R-01 | Mostrar datos sin licencia de visualización (acciones, índices, futuros) y recibir reclamación o corte del proveedor | 4 | 5 | 20 | `provider_licenses` en código; ningún mercado habilitado sin contrato escrito; staging tratado como visualización | P, C | Cualquier PR que añada un proveedor |
| R-02 | Que usuarios interpreten estados o score como recomendación de inversión o probabilidad de ganancia | 4 | 5 | 20 | Textos fijos (RA-10, RS-04), "no validada" en cada señal, sin veredicto público, revisión legal | P, A, C | Cada cambio de interfaz |
| R-03 | Costos de datos muy superiores al ingreso (equilibrio de 52 a 410 usuarios) | 5 | 4 | 20 | Orden de mercados por costo, datos de cierre/retraso, ETF proxy, no contratar antes del piloto | P | Antes de Fase 3 |
| R-04 | Construir multiactivo sobre una 2.1 con P0 abiertos (TOTP, credenciales expuestas, repo público) | 4 | 5 | 20 | Fase 0 como requisito de entrada | P | Inicio de Fase 2 |
| R-05 | Sobreajuste y falsos descubrimientos al probar muchas ideas en 8 mercados | 4 | 4 | 16 | Protocolo cuantitativo, deflated Sharpe, contador de pruebas, holdout por clase | C | Cada experimento |
| R-06 | Mezclar instrumentos (índice vs ETF vs futuro; vencimientos; unidades) y producir análisis falsos | 3 | 5 | 15 | Modelo activo/instrumento/serie, `roll_rules`, validaciones en `normalize` | C | Fases 4–5 |

## 2. Riesgos altos (nivel 9–14)

| Id | Riesgo | P | I | Nivel | Mitigación | Resp. |
|---|---|---|---|---|---|---|
| R-07 | Tarifas de bolsa por usuario no previstas convierten costos fijos en variables altos | 3 | 4 | 12 | Preguntar por escrito (DATA_PROVIDER_RESEARCH §11) | P |
| R-08 | Ambigüedad de tickers (cripto y acciones) asigna datos al activo equivocado | 3 | 4 | 12 | Identificadores con vigencia; `coingecko_id`, FIGI/ISIN | C |
| R-09 | Calendarios erróneos: velas en festivos, cierres mal fechados, gaps como señales | 3 | 4 | 12 | Servicio de calendarios con pruebas por mercado y año | C |
| R-10 | Sesgo de supervivencia en investigación de acciones | 3 | 4 | 12 | Universo histórico con deslistados; proveedor que los incluya | C, P |
| R-11 | Inyección de instrucciones vía noticias en servicios de IA | 3 | 4 | 12 | S-40…S-42; pruebas con contenido malicioso | C |
| R-12 | La IA inventa cifras o noticias | 3 | 4 | 12 | Solo datos verificados, validación de salida, descarte | C |
| R-13 | Interferir con la 2.1 en producción o con el paper trading de D_volmom_L28 | 2 | 5 | 10 | Esquema `mr` separado, paquete nuevo, sin despliegue, sin tocar `radar/` | C |
| R-14 | Neon: almacenamiento/transferencia superan el plan | 3 | 3 | 9 | Medir; retención por licencia; Parquet fuera de producción | P, C |
| R-15 | Capacidad de Render (512 MB) insuficiente para varios mercados | 3 | 3 | 9 | Worker separado según criterio medible | C |
| R-16 | Datos personales y carteras sin política completa (Ley 1581) | 3 | 4 | 12 | Política con responsable real y abogado antes de usuarios externos | P, A |
| R-17 | Dependencia de un solo proveedor por mercado | 3 | 3 | 9 | Interfaz común; segundo proveedor evaluado por mercado | C |

## 3. Riesgos medios

| Id | Riesgo | P | I | Mitigación |
|---|---|---|---|---|
| R-18 | Alcance excesivo: 14 secciones de interfaz y 9 motores para una persona | 4 | 2 | Entregas pequeñas, habilitación por mercado |
| R-19 | Divergencia de indicadores entre producto e investigación | 3 | 3 | Biblioteca única con golden tests |
| R-20 | Proveedores cambian precios o términos | 3 | 3 | `valid_until` en licencias, revisión trimestral |
| R-21 | Telegram: entregas perdidas o duplicadas, límites de la API | 3 | 2 | `alert_deliveries`, dedupe, reintentos |
| R-22 | Nombre "Market Radar" en conflicto con marcas existentes | 2 | 3 | Búsqueda de marca antes de usar públicamente (PENDIENTE) |
| R-23 | El código de producción sigue fuera de `main` y la integración se complica | 3 | 3 | F0-9 antes de Fase 2 |
| R-24 | Huecos de escaneo no detectados (como el del 17/18-nov) | 3 | 3 | `scan_runs` + alerta operativa |

## 4. Riesgos aceptados explícitamente

| Id | Riesgo | Por qué se acepta |
|---|---|---|
| RA-1 | No hay ventaja demostrada; puede no haberla nunca | El producto se define como inteligencia descriptiva, no como señales |
| RA-2 | Validación prospectiva de cripto tarda ≥ 90 días por hipótesis | No hay muestra histórica virgen |

## 5. Revisión

Se revisa al cerrar cada fase y ante cualquier contrato de datos. Cada riesgo cerrado conserva su fila con fecha y evidencia de cierre.
