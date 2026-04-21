#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOOT_DIR="$HOME/.termux/boot"
BOOT_SCRIPT="$BOOT_DIR/start-shopkasse.sh"

echo ">>> Setup Termux:Boot für Shopkasse"
echo ">>> Projekt: $ROOT"

mkdir -p "$BOOT_DIR"

cat >"$BOOT_SCRIPT" <<EOF
#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
cd "$ROOT"
bash "$ROOT/run.sh"
EOF

chmod 700 "$BOOT_SCRIPT"
chmod +x "$ROOT/run.sh" "$ROOT/stop.sh" "$ROOT/setup_boot.sh" || true

echo
echo "Fertig. Termux:Boot-Script wurde erstellt:"
echo "  $BOOT_SCRIPT"
echo
echo "Wichtig für Android-Autostart:"
echo "1) App 'Termux:Boot' installieren und einmal öffnen."
echo "2) Akku-Optimierung für Termux + Termux:Boot deaktivieren."
echo "3) Gerät neu starten und server.log prüfen."
