#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$(dirname "$0")" && pwd)"
target_dir="$HOME/.local/share/pc-remote"
unit_dir="$HOME/.config/systemd/user"
# Every file the service loads at runtime; test_agent.py parses this line.
files=(agent.py actions.py windows_actions.py index.html)
for file in "${files[@]}"; do
  [[ -f "$source_dir/$file" ]] || { echo "Missing $source_dir/$file" >&2; exit 1; }
done
mkdir -p "$target_dir" "$unit_dir"
for file in "${files[@]}"; do
  install -m 600 "$source_dir/$file" "$target_dir/$file"
done
cat > "$unit_dir/pc-remote.service" <<EOF
[Unit]
Description=Private PC Remote control agent
After=graphical-session.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 $target_dir/agent.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable pc-remote.service
systemctl --user restart pc-remote.service
echo "PC Remote installed at http://127.0.0.1:8765"
echo "Your private token is in ~/.config/pc-remote/token"
echo "Read README.md before enabling remote access."
