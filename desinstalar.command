#!/bin/bash
# Detiene Crypto Radar y lo quita del arranque. Tus datos quedan en ~/CryptoRadar/data.
LABEL="com.cryptoradar.agent"; PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Crypto Radar detenido y quitado del arranque. Para borrarlo del todo elimina la carpeta ~/CryptoRadar."
read -p "Pulsa Enter para cerrar…"
