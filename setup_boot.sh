#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo ">>> setup_boot.sh ist jetzt ein Kompatibilitäts-Wrapper."
echo ">>> Verwende künftig: bash \"$ROOT/install.sh\""
echo
bash "$ROOT/install.sh"
