"""Prueba de humo de los adaptadores contra las fuentes públicas reales (necesita red). Uso: python research/prospectivo/humo_datos.py
No evalúa ninguna estrategia: solo comprueba que cada fuente responde y se convierte al esquema común."""
import sys, json; sys.path.insert(0, "research")
import pandas as pd
from prospectivo import datos as D
out = {}
def t(nombre, f):
    try:
        df = f(); out[nombre] = {"filas": len(df), "primera": str(df.index.min()), "ultima": str(df.index.max())}
    except Exception as e:
        out[nombre] = {"error": str(e)[:150]}
t("binance_spot_1h", lambda: D.parse_klines_binance(D.descargar(D.url_binance("klines","BTCUSDT","2026-11-14","1h")),"BTCUSDT","1h"))
t("binance_um_1h", lambda: D.parse_klines_binance(D.descargar(D.url_binance("klines","BTCUSDT","2026-11-14","1h","um")),"BTCUSDT","1h","um"))
t("binance_aggtrades_ofi", lambda: D.desequilibrio_flujo(D.parse_aggtrades_binance(D.descargar(D.url_binance("aggTrades","ETHUSDT","2026-11-14"))),"1h"))
t("binance_bookdepth", lambda: D.parse_bookdepth_binance(D.descargar(D.url_binance("bookDepth","BTCUSDT","2026-11-14",mercado="um"))))
t("binance_metrics", lambda: D.parse_metrics_binance(D.descargar(D.url_binance("metrics","BTCUSDT","2026-11-14",mercado="um"))))
t("binance_funding_mensual", lambda: D.parse_funding_binance(D.descargar(D.url_binance("fundingRate","BTCUSDT","2026-10",mercado="um",periodo="monthly")),"BTCUSDT"))
t("coinbase_1h", lambda: D.parse_coinbase(D.descargar(D.url_coinbase("BTC-USD",3600,"2026-11-15T00:00:00Z","2026-11-15T23:00:00Z")).decode(),"BTC-USD",3600))
t("kraken_1h", lambda: D.parse_kraken(D.descargar(D.url_kraken("XBTUSD",60)).decode(),"XBTUSD",60))
t("okx_1h", lambda: D.parse_okx(D.descargar(D.url_okx("BTC-USDT","1H")).decode(),"BTC-USDT",3600))
t("fred_dtb3", lambda: D.parse_fred(D.descargar("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3").decode()))
print(json.dumps(out, indent=1))
