#!/usr/bin/env bash
set -euo pipefail

source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
destination="$HOME/.config/omarchy/plugins/nurfaizfoat.agent-monitor"

command -v python3 >/dev/null || { echo 'Python 3 is required.' >&2; exit 1; }
command -v omarchy >/dev/null || { echo 'Omarchy shell is required.' >&2; exit 1; }
omarchy plugin validate "$source_dir"
if [[ -e "$destination" || -L "$destination" ]]; then
  echo "Already installed at $destination; refusing to overwrite it." >&2
  exit 1
fi
mkdir -p -- "$(dirname -- "$destination")"
mkdir -- "$destination"
for file in manifest.json Panel.qml OpenAIIcon.qml WhaleIcon.qml whale.svg balance.py openai.py setup.py README.md; do
  cp -- "$source_dir/$file" "$destination/$file"
done
omarchy plugin enable nurfaizfoat.agent-monitor
echo 'Installed. Hover over Agent Monitor to configure missing credentials.'
