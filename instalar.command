#!/bin/bash
# CRYPTO RADAR AI — instalador para macOS.
# Copia la app a ~/CryptoRadar y la registra para que arranque sola al encender el Mac
# y siga funcionando en segundo plano (escaneo cada 4 h, vigilancia de precio cada 15 min).
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/CryptoRadar"
LABEL="com.cryptoradar.agent"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
echo "== Crypto Radar: instalación =="

PY=""
for c in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/Current/bin/python3 /usr/bin/python3; do
  if [ -x "$c" ] && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Necesitas Python 3. Se abrirá la instalación de las herramientas de Apple; acepta, espera a que termine y vuelve a abrir este instalador."
  xcode-select --install 2>/dev/null || true
  open "https://www.python.org/downloads/macos/"
  read -p "Pulsa Enter para cerrar…"; exit 1
fi
echo "Python: $PY ($("$PY" --version))"

mkdir -p "$DEST/data" "$HOME/Library/LaunchAgents"
rsync -a --exclude data --exclude tests --exclude '__pycache__' "$SRC/" "$DEST/"
chmod +x "$DEST"/*.command 2>/dev/null || true

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null || true
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$PY</string><string>$DEST/main.py</string><string>serve</string></array>
  <key>WorkingDirectory</key><string>$DEST</string>
  <key>EnvironmentVariables</key><dict><key>CRYPTO_RADAR_HOME</key><string>$DEST</string><key>PYTHONUNBUFFERED</key><string>1</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$DEST/data/radar.log</string>
  <key>StandardErrorPath</key><string>$DEST/data/radar.log</string>
</dict></plist>
PL
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load "$PLIST"
sleep 3
if curl -s -o /dev/null http://localhost:8777/api/state; then
  echo "✅ Crypto Radar está funcionando en segundo plano."
  echo "   Panel: http://localhost:8777  (el primer escaneo empieza solo y tarda unos minutos)"
  open "http://localhost:8777"
else
  echo "⚠️  El servicio no respondió todavía. Revisa $DEST/data/radar.log"
fi
read -p "Pulsa Enter para cerrar…"
