# CRYPTO RADAR AI

Escáner cuantitativo de criptomonedas con panel operativo. Corre solo en tu Mac, en segundo plano:
escanea el mercado cada 4 horas, vigila precios cada 15 minutos y te avisa (notificación en el Mac y, si quieres, Telegram).

**Solo análisis. No es asesoría financiera. Solo spot, sin apalancamiento.**

## Versión 2.0
- Motor cuantitativo nuevo (`radar/quant`), backtest profesional, radar de memecoins, cartera con límites de riesgo,
  Telegram por usuario y modo SaaS con cuentas, planes y pagos verificados (Wompi y NOWPayments).
- Documentos: [CHANGELOG](CHANGELOG.md) (incluye la comparativa con la versión original) ·
  [Auditoría](AUDIT_REPORT.md) · [Pruebas](TEST_REPORT.md) · [Backtest](BACKTEST_REPORT.md) ·
  [Instalación, variables y despliegue](docs/INSTALACION_Y_DESPLIEGUE.md) · [Arquitectura](docs/ARQUITECTURA.md) ·
  [Pendientes](PENDIENTES.md).
- Importante: el backtest 2.0 **no supera la validación fuera de muestra** (ver BACKTEST_REPORT.md). Úsalo como
  herramienta de análisis y riesgo, no como promesa de rentabilidad.

## Instalar (Mac)
1. Descomprime la carpeta `crypto-radar`.
2. Haz clic derecho en **instalar.command** → **Abrir** → **Abrir** (la primera vez macOS pide confirmarlo).
3. Se abre el panel en `http://localhost:8777`. El primer escaneo empieza solo y tarda unos minutos.

Desde entonces arranca solo cada vez que enciendes el Mac. Para volver al panel: abre `http://localhost:8777`
o haz doble clic en `~/CryptoRadar/abrir.command`. Para detenerlo: `desinstalar.command`.

> Si el Mac está dormido o apagado, el radar se pausa. Al despertar, si pasó la hora del escaneo, lo hace en seguida.

## Qué hace
- **Universo**: top 150 por capitalización (configurable) con par USDT en Binance, filtrando stablecoins,
  tokens envueltos, poca liquidez y poca capitalización. Etiqueta Large/Mid/Small cap, IA, DePIN, RWA, DeFi, Gaming, Infraestructura y Memecoins.
- **Análisis multitemporal** 1D / 4H / 1W: RSI, MACD, EMA 20/50/200, Bollinger (squeeze), ATR, OBV, VWAP, divergencias,
  rupturas, retests, volumen anormal, Fibonacci, soportes/resistencias por pivotes; funding y open interest de Binance como sentimiento.
- **Fases**: Acumulación, Ruptura inicial, Momentum, Retroceso, Lateral, Sobreextendido, Distribución, Bajista.
- **Tres motores**: Early Entry, Explosive Momentum y Exit Intelligence (cada uno 0-100 con sus señales).
- **Puntuación 0-100** con los 7 bloques y pesos de tu especificación. Si un bloque no tiene datos verificables gratuitos
  (actividad on-chain, ballenas; catalizadores si no los registras) se muestra **N/D** y su peso se reparte entre los demás. Nunca se inventa.
- **Plan de entrada**: entrada ideal/zona, agresiva y de confirmación, stop técnico, TP1, TP2, TP3, salida final, R:R, retorno,
  riesgo y **tamaño de posición** según tu capital y % de riesgo.
- **Régimen de mercado** (BTC, dominancia, amplitud de altcoins, Fear & Greed, capitalización total): sube el puntaje mínimo
  de compra y baja la exposición máxima a altcoins cuando el mercado se deteriora. Si nada califica: **MANTENER LIQUIDEZ**.
- **Alertas**: nueva entrada temprana, ruptura confirmada, precio en zona de entrada, cerca del stop / stop tocado,
  TP alcanzado, distribución, giro bajista y cambio de régimen.

## Mejoras añadidas sobre la especificación
1. **Telegram**: alertas en el celular (Ajustes → pasos para crear el bot).
2. **Vigilancia de precio cada 15 min** entre escaneos, para que las alertas de zona de entrada, stop y TP lleguen a tiempo.
3. **Mis posiciones**: registra compras reales o simuladas; el radar sigue TP/stop y las señales de salida de cada una.
4. **Rendimiento real**: cada señal "COMPRAR EN ZONA" se guarda y se evalúa sola con velas de 1h (acierto, R medio). Así sabes si el sistema funciona antes de arriesgar dinero.
5. **Backtest** de las reglas sobre hasta 1000 días de historia para cualquier token, y **backtest de cartera** con órdenes exactas, comisiones y slippage (doble clic en `backtest_cartera.command`).
6. **Catalizadores verificables**: los registras tú (con fuente) y suman al bloque de catalizadores.
7. **Watchlist y exclusiones** personalizadas.
8. **Gráfico por activo** con EMA y niveles del plan, y historial de puntuación.

## Datos
CoinGecko (mercado, supply, categorías, dominancia), Binance (velas, funding, open interest), alternative.me (Fear & Greed).
Todo es público y gratuito, sin claves. Todos tus datos quedan en `~/CryptoRadar/data` en tu Mac.

## Comandos (opcional)
```
python3 main.py serve          # panel + escaneos automáticos
python3 main.py scan           # un escaneo ahora en la terminal
python3 main.py backtest SOL   # backtest rápido
```

## Desplegar en Render gratis (24/7 sin tu Mac)

Para el modo con cuentas y pagos sigue [docs/INSTALACION_Y_DESPLIEGUE.md](docs/INSTALACION_Y_DESPLIEGUE.md). El modo de un solo usuario:

1. En Render: **New → Blueprint** y elige este repositorio. Render lee `render.yaml`.
2. Escribe la contraseña del panel en `CRYPTO_RADAR_PASSWORD` (usuario: cualquiera). Opcional: `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` para alertas al celular.
3. Confirma. Queda en Frankfurt (Binance bloquea EE. UU.).

Plan gratis: el servicio se visita a sí mismo cada 10 min para no dormirse (usa ~720 de las 750 horas gratis al mes;
no despliegues otro servicio gratis en la misma cuenta). El disco se borra al reiniciar o redesplegar: se pierden el
historial, las posiciones y el diario de señales; el siguiente escaneo se hace solo. Las alertas importantes llegan por Telegram.
