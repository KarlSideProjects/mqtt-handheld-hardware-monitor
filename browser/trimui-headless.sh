#!/bin/bash
set -euo pipefail
unset LD_LIBRARY_PATH
home=/var/lib/hwmonitor-browser
mkdir -p "$home" /run/hwmonitor/browser
chmod 700 "$home" /run/hwmonitor/browser
chown 65534:65534 "$home" /run/hwmonitor/browser
chmod 711 /run/hwmonitor
exec setpriv --reuid=65534 --regid=65534 --clear-groups \
    env HOME="$home" XDG_RUNTIME_DIR=/run/hwmonitor/browser FONTCONFIG_PATH=/etc/fonts \
    chromium --headless --disable-gpu --no-first-run --no-default-browser-check --disable-sync \
    --user-data-dir="$home/profile" --window-size=1280,720 --hide-scrollbars \
    --remote-debugging-address=127.0.0.1 --remote-debugging-port=0 "$@"
