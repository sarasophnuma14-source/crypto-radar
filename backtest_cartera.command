#!/bin/bash
# Ejecuta el backtest de cartera con datos reales de Binance y abre el informe.
cd "$HOME/CryptoRadar" 2>/dev/null || cd "$(dirname "$0")"
PY=$(command -v python3)
CRYPTO_RADAR_HOME="$(pwd)" "$PY" main.py cartera
open "data/backtest_cartera/informe.html"
read -p "Pulsa Enter para cerrar…"
