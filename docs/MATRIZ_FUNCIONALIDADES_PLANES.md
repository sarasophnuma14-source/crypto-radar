# Matriz de funcionalidades por plan

> **Actualización del 16-nov-2026.** Decisión preliminar del propietario: lanzar solo Pro a US$15/149 y diferir Élite hasta tener 2 o más diferenciadores reales (`MODELO_NEGOCIO_VALIDADO.md` §4). Los números vigentes están en `UNIT_ECONOMICS.md`; los criterios para cobrar, en `DECISION_COMERCIAL_GO_NO_GO.md`.

Fecha: 16 de noviembre de 2026. Fuente: `radar/auth.py` (`PLANS`), `radar/webapi.py` y `web/app.js` en `release-2.1` (2f6df27).

Columnas "Hoy": lo que el código entrega de verdad. Columna "Propuesta": lo que se sugiere, marcado con "requiere desarrollo" cuando no existe.

| Función | Libre (hoy) | Pro (hoy) | Élite (hoy) | Propuesta Pro | Propuesta Élite |
|---|---|---|---|---|---|
| Ranking visible | top 3 | 20 | 20 | 20 | 20 |
| Tres motores (Early, Momentum, Exit) | parcial (top 3) | Sí | Sí | Sí | Sí |
| Entrada, invalidación, stop, TP1-TP3 | top 3 | Sí | Sí | Sí | Sí |
| Cartera (posiciones reales o simuladas) | No | Sí | Sí | Sí | Sí |
| Decisión de salida por posición | No | Sí | Sí | Sí | Sí |
| Lista de seguimiento | 50 | 50 | 50 | 50 | ilimitada o 200 (requiere desarrollo, S) |
| Vigilancia de precio cada 15 min | Sí (global) | Sí | Sí | Sí | Sí |
| Alertas por Telegram | No | Sí | Sí | Sí | Sí |
| Alertas configurables por activo y umbral | No existe | No existe | No existe | — | requiere desarrollo (M-L) |
| Memecoins (simulado) | No | Sí | Sí | Sí | Sí |
| Diario de señales evaluado | Sí | Sí | Sí | Sí | Sí |
| Exportación CSV (ranking, mercado, diario) | Sí | Sí | Sí | Sí | Sí |
| Resultados de backtest históricos (estáticos) | No | No | Sí | Sí (*) | Sí |
| Historial de señales con filtros y fechas | No existe | No existe | No existe | — | requiere desarrollo (M) |
| Frecuencia de escaneo | 4 h | 4 h | 4 h | 4 h | 1 h (requiere desarrollo y más costo de datos y cómputo, M) |
| Soporte | — | — | — | correo | correo prioritario (operativo, sin desarrollo) |
| Aviso "no validada" y datos de frescura | Sí (PR #12) | Sí | Sí | Sí | Sí |

(*) Recomendación: los resultados históricos, incluidos los negativos, son **información esencial de transparencia**. No deberían reservarse a un plan caro, porque el encargo pide no limitar información esencial.

**Cosas que no se limitan por plan:** el 2FA, el aviso de riesgo, la información de validación y la frescura de los datos.

## Costo estimado de los diferenciadores de Élite

Estimación de esfuerzo de ingeniería, no de dinero.

| Función | Esfuerzo | Costo operativo adicional |
|---|---|---|
| Alertas configurables por activo (precio o puntaje, con límite por plan) | L (2-3 días) | Bajo: lo hace el mismo vigilante de 15 min |
| Historial de señales con filtros | M (1 día) | Bajo: almacenamiento |
| Escaneo horario para Élite | M + costo | Unas 6 veces más llamadas a la API. Riesgo de límite de CoinGecko o Binance, requiere evaluar un plan de datos |
| Lista de seguimiento ampliada | S | Despreciable |
