#!/usr/bin/env bash
set -euo pipefail

# ----- FONT GENERATION ------------------------------------------------------ #

FONT_DIR="$(cd "$(dirname "$0")" && pwd)"
MKFONT="$(command -v grub-mkfont || command -v grub2-mkfont)" || {
  echo "Error: grub-mkfont or grub2-mkfont is required." >&2
  exit 1
}
for size in 16 24 32; do
  "${MKFONT}" -o "${FONT_DIR}/unifont-${size}.pf2" -s "${size}" "${FONT_DIR}/unifont.otf"
done
