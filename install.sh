#!/usr/bin/env bash
set -euo pipefail
source_dir="$(cd "$(dirname "$0")" && pwd)"
target_dir="$HOME/.local/share/pc-remote"
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$target_dir" "$unit_dir"
install -m 600 "$source_dir/agent.py" "$target_dir/agent.py"
install -m 600 "$source_dir/index.html" "$target_dir/index.html"
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
systemctl --user enable --now pc-remote.service
echo "PC Remote installed at http://127.0.0.1:8765"
echo "Your private token is in ~/.config/pc-remote/token"
echo "Read README.md before enabling remote access."
