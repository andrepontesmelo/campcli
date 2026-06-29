#!/usr/bin/env bash
# Deploy campcli on the server: reinstall the CLI and restart the daemon.
#
# Run this on the server, from the repo root, after the new code is present
# (e.g. `git pull`). The systemd unit launches the *installed* binary at
# ~/.local/bin/campcli, so a bare `systemctl restart` would relaunch the old
# code — we reinstall first.
#
#   ./deploy.sh
#
set -euo pipefail

cd "$(dirname "$0")"

SERVICE=campcli-daemon

echo "==> Reinstalling campcli (uv tool install --force) ..."
uv tool install --force .

echo "==> Restarting ${SERVICE} ..."
if systemctl --user is-enabled --quiet "${SERVICE}" 2>/dev/null; then
  systemctl --user restart "${SERVICE}"
  systemctl --user --no-pager status "${SERVICE}" | head -n 5
else
  echo "    (${SERVICE} not enabled for this user — skipping restart)"
fi

echo "==> Done. Installed: $(command -v campcli) ($(campcli --version 2>/dev/null || echo 'no --version'))"
echo "    Logs: journalctl --user -u ${SERVICE} -f"
