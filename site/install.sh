#!/usr/bin/env bash
# Public installer. Downloads one copy of the repository, then runs its install.sh.
set -euo pipefail
if [[ ${EUID:-$(id -u)} -eq 0 ]]; then
  echo "Run this as the desktop user, not root." >&2
  exit 1
fi
command -v python3 >/dev/null || { echo "Python 3 is required." >&2; exit 1; }
command -v systemctl >/dev/null || { echo "systemd is required." >&2; exit 1; }
command -v curl >/dev/null || { echo "curl is required." >&2; exit 1; }
repo="sauravsvt/pc-remote-ubuntu-mvp"
ref="${PC_REMOTE_REF:-main}"
if [[ "$ref" == v* ]]; then
  url="https://github.com/${repo}/archive/refs/tags/${ref}.tar.gz"
else
  url="https://github.com/${repo}/archive/refs/heads/${ref}.tar.gz"
fi
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl -fsSL "$url" | tar -xz -C "$tmp"
src="$(find "$tmp" -mindepth 1 -maxdepth 1 -type d)"
bash "$src/install.sh"
echo "Next, open https://pcremote.voxonlabs.com/#phone and connect Tailscale."
