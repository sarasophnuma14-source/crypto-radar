# Arquitectura de Crypto Radar 2.0

Un solo proceso de Python (librería estándar) que sirve el panel, programa los escaneos y atiende el bot de Telegram.

```
main.py serve
 └─ radar/server.py        servidor HTTP, planificador (escaneo cada 4 h, vigilancia de precio cada 15 min, memecoins)
     ├─ radar/webapi.py     rutas del modo SaaS: cuentas, sesión, CSRF, planes, pagos, datos por usuario, admin
     ├─ radar/scanner.py    descarga de velas (4 hilos) → calidad → features → régimen → motor → ranking → alertas
     │   └─ radar/quant/    motor cuantitativo causal (el mismo en vivo y en backtest)
     ├─ radar/meme_radar.py radar de memecoins (antigüedad, liquidez, FDV, riesgo; on-chain N/D)
     ├─ radar/alerts.py     alertas deduplicadas → Mac/Windows/Linux, Telegram
     ├─ radar/notify.py     textos de Telegram y resúmenes diario y semanal
     ├─ radar/telegram_bot.py vinculación por usuario y comandos (/estado /top /regimen /cartera /alertas /baja /ayuda)
     ├─ radar/auth.py       usuarios (scrypt), sesiones (token con hash), bloqueo de intentos, planes
     ├─ radar/billing.py    Wompi y NOWPayments: checkout firmado, webhook verificado y reconsultado, concesión idempotente
     ├─ radar/multiuser.py  cartera aislada por usuario y salidas tras cada escaneo
     ├─ radar/db.py         PostgreSQL (DATABASE_URL) o SQLite local
     └─ radar/storage.py    documentos JSON en disco o en la tabla kv de la base
```

## Motor cuantitativo (`radar/quant`)

| Módulo | Función |
| --- | --- |
| `quality.py` | Puntuación de calidad de datos 0-100 (huecos, duplicados, OHLC incoherente, saltos, datos viejos). Con calidad insuficiente no hay señal |
| `features.py` | Indicadores calculados una vez por serie y de forma causal (el valor en t solo usa velas ≤ t; pivotes confirmados 3 velas después) |
| `early.py` | Detector de entrada temprana: 7 familias (estructura, volumen, tendencia, momentum, fuerza relativa, liquidez, ruptura), cada indicador en una sola familia, fases PRE-EXPLOSION / ACCUMULATION / BREAKOUT / MOMENTUM / OVEREXTENDED / DISTRIBUTION / REJECTED |
| `manipulation.py` | Riesgo de manipulación con evidencias verificables (picos sin volumen, mechas, falsas rupturas, libro de órdenes). Nunca afirma "prueba" |
| `exits.py` | Exit Intelligence: MANTENER, PROTEGER GANANCIAS, REDUCIR POSICIÓN o CERRAR POSICIÓN; exige al menos 2 familias para cerrar; el stop nunca baja |
| `regime.py` | Régimen BULLISH / NEUTRAL / BEARISH / HIGH VOLATILITY / CAPITULATION con política de exposición, umbral y tamaño |
| `plan.py` | Zona de entrada, disparo de ruptura, stop por ATR y estructura, TP1-TP3 en múltiplos de R, R:R |
| `portfolio.py` | Tamaño por riesgo y límites (activo, categoría, posiciones, correlación, riesgo abierto, liquidez, freno por drawdown) |
| `engine.py` | Une todo: `analyze()` devuelve fase, puntaje, plan, manipulación, salida y acción |
| `backtest_pro.py` | Backtest de cartera día a día con universo por fecha, órdenes reales, costes y métricas |
| `metrics.py` | Métricas solo desde el libro de operaciones y la curva diaria |

## Flujo de un escaneo

1. Universo: top por capitalización con par USDT, sin stablecoins ni tokens envueltos.
2. Velas diarias cerradas (Binance → Bybit → OKX si falla una fuente).
3. `quality.check` → `features.compute` → `regime.detect` (con amplitud del mercado) → `engine.analyze` por activo.
4. Libro de órdenes para los 25 primeros.
5. `build_report`: veredicto, régimen, ranking (fases tempranas primero, penaliza subidas previas y manipulación), rupturas, evitar.
6. Alertas solo cuando algo cambia (nueva PRE-EXPLOSION, ruptura confirmada, zona de entrada, riesgo, distribución, régimen).
7. Con cuentas: salidas de la cartera de cada usuario y envío por Telegram según su plan.

## Seguridad del modo SaaS

- Contraseñas con scrypt y sal. Sesión por cookie `HttpOnly; SameSite=Lax; Secure`; en la base solo se guarda el hash del token.
- CSRF: token por sesión en la cabecera `X-CSRF-Token`, POST solo JSON y del mismo origen.
- Bloqueo de la cuenta 15 min tras 5 fallos; límites por IP en inicio de sesión y registro; cuerpo máximo 64 KB.
- Cabeceras CSP, nosniff y frame-ancestors. Registro de actividad por usuario.
- Cada consulta de cartera, pagos y actividad filtra por `user_id`.
- Los ajustes del sistema, el escaneo manual y la concesión manual de planes son solo de administrador (con motivo registrado).
