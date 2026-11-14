#!/bin/bash
# Para Linux (o WSL): ejecuta el radar en segundo plano. En Windows usa:  py main.py serve
cd "$(dirname "$0")" && CRYPTO_RADAR_HOME="$(pwd)" nohup python3 main.py serve >> data/radar.log 2>&1 &
echo "Panel en http://localhost:8777"
