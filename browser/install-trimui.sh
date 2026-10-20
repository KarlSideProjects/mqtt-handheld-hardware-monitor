#!/bin/bash
# Install a private ARM64 browser environment on Smart Pro S Buildroot.
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
for arg in "$@"; do
    if [[ $arg == --ssh ]]; then exec bash "$source_dir/install-remote.sh" trimui "$@"; fi
done
base=/mnt/UDISK/hwmonitor
menu=/mnt/SDCARD/Apps/HardwareMonitor
runtime=$base/runtime
config= check=0 deps_only=0 runtime_provided=0
fail() { echo "ERROR: $*" >&2; exit 1; }
while (($#)); do
    case "$1" in
        --config) config=${2:?--config requires FILE}; shift 2 ;;
        --runtime) runtime=${2:?--runtime requires DIR}; runtime_provided=1; shift 2 ;;
        --check) check=1; shift ;;
        --deps-only) deps_only=1; shift ;;
        --help) echo 'Usage: bash browser/install-trimui.sh [--ssh HOST [--user USER]] [--runtime DIR] [--config FILE] [--check | --deps-only]'; exit ;;
        *) fail "Unknown argument: $1" ;;
    esac
done
((check == 0 || deps_only == 0)) || fail 'Choose --check or --deps-only.'
[[ $(id -u) == 0 ]] || fail 'Run on TrimUI as root, or use --ssh HOST.'
[[ $(uname -m) == aarch64 ]] || fail 'Requires ARM64 TrimUI Smart Pro S.'
. /etc/os-release
[[ $ID == buildroot ]] || fail 'Requires the Smart Pro S Buildroot system.'
[[ -f /proc/device-tree/compatible ]] && grep -aq 'allwinner,a523' /proc/device-tree/compatible || fail 'Expected Smart Pro S A523 device tree.'
[[ -d /usr/trimui && -d /mnt/SDCARD/Apps && -d /mnt/UDISK && -e /dev/dri/card0 ]] || fail 'TrimUI display or mounted storage missing.'
[[ -w /sys/class/backlight/backlight0/brightness ]] || fail 'Backlight interface missing.'
command -v python3 >/dev/null || fail 'Python 3.10+ required.'
python3 -c 'import sys; assert sys.version_info >= (3,10)' || fail 'Python 3.10+ required.'
if ((check == 0)); then
    bash "$source_dir/trimui-awake.sh" --persist
    pgrep -f '^python3 trimui_monitor.py$' >/dev/null && fail 'Exit Hardware Monitor before updating.'
    if ((runtime_provided == 0)); then
        bash "$source_dir/install-trimui-deps.sh" "$runtime"
    fi
fi
missing=0
if [[ ! -x $runtime/bin/chromium ]]; then
    echo 'MISSING: Chromium/SDL runtime; run install-trimui.sh --deps-only to install all dependencies.' >&2
    missing=1
else
    LD_LIBRARY_PATH="$runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$runtime/bin/chromium" --version >/dev/null 2>&1 || { echo 'MISSING: Chromium executable or its ABI-compatible libraries.' >&2; missing=1; }
fi
PYTHONPATH="$runtime/python${PYTHONPATH:+:$PYTHONPATH}" python3 -c 'import paho.mqtt.client as m; assert hasattr(m,"CallbackAPIVersion")' 2>/dev/null || { echo 'MISSING: paho-mqtt 2.x (system or runtime/python/).' >&2; missing=1; }
PYTHONPATH="$runtime/python${PYTHONPATH:+:$PYTHONPATH}" python3 -c 'import websocket; assert hasattr(websocket,"create_connection")' 2>/dev/null || { echo 'MISSING: websocket-client (runtime/python/).' >&2; missing=1; }
((missing == 0)) || fail 'Prerequisites incomplete; no application files or device settings were changed.'
if ((deps_only)); then echo 'PASS: all TrimUI runtime dependencies installed; MQTT setup not requested.'; exit; fi
if ((check)); then
    bash "$source_dir/trimui-awake.sh" --check
    [[ -s $base/app/trimui_monitor.py && -s $base/app/pve.py && -s $base/app/pve.js && -x $menu/launch.sh && -s $menu/config.json ]] || fail 'Application not installed.'
    [[ -f $base/mqtt-config.json ]] || fail 'Private MQTT config missing.'
    PYTHONPATH="$base/app" python3 -c 'from trimui_monitor import gamepad; gamepad()'
    PYTHONPATH="$source_dir" python3 - "$base/mqtt-config.json" <<'PY'
import json,sys,stat
from pathlib import Path
from mqtt_setup import validate
assert stat.S_IMODE(Path(sys.argv[1]).stat().st_mode) == 0o600, 'MQTT config must have mode 600'
validate(json.load(open(sys.argv[1])))
PY
    echo 'PASS: files, platform, runtime, gamepad and config. Display/MQTT operation still needs launch verification.'
    exit
fi
for file in monitor.py pve.py pve.js monitor.html trimui_monitor.py trimui-launch.sh trimui-awake.sh mqtt_setup.py assets/hardware-buddy.svg assets/hardware-buddy.png; do
    [[ -f $source_dir/$file ]] || fail "Missing source: $file"
done
umask 077
work=$(mktemp -d /mnt/UDISK/hwmonitor-stage.XXXXXXXX)
trap 'rm -rf -- "$work"' EXIT
[[ -n $config || ! -f $base/mqtt-config.json ]] || config=$base/mqtt-config.json
args=(--output "$work/mqtt-config.json")
[[ -z $config ]] || args+=(--config "$config")
python3 "$source_dir/mqtt_setup.py" "${args[@]}"
mkdir -p "$base"
backup=$(mktemp -d "$base/backup.XXXXXXXX")
paths=()
for path in mnt/UDISK/hwmonitor/app mnt/UDISK/hwmonitor/mqtt-config.json mnt/SDCARD/Apps/HardwareMonitor; do
    [[ ! -e /$path ]] || paths+=("$path")
done
if ((${#paths[@]})); then
    tar -C / -cf - "${paths[@]}" | gzip > "$backup/files.tar.gz"
else
    # BusyBox tar refuses to create an empty archive; two zero blocks are a valid empty tar.
    python3 -c 'import gzip,sys; gzip.open(sys.argv[1],"wb").write(bytes(1024))' "$backup/files.tar.gz"
fi
printf 'Private backup (contains credentials): %s\n' "$backup"
mkdir -p "$work/app/assets"
for file in monitor.py pve.py pve.js monitor.html trimui_monitor.py trimui-awake.sh mqtt_setup.py; do cp "$source_dir/$file" "$work/app/$file"; done
cp "$source_dir/assets/hardware-buddy.svg" "$work/app/assets/"
# Replace whole directories so removed files do not survive an update.
if [[ $(cd -- "$runtime" && pwd) != "$base/runtime" ]]; then
    cp -a "$runtime" "$work/runtime"
    rm -rf -- "$base/runtime"
    mv "$work/runtime" "$base/runtime"
fi
rm -rf -- "$base/app"
mv "$work/app" "$base/app"
cp "$work/mqtt-config.json" "$base/mqtt-config.json"
chmod 600 "$base/mqtt-config.json"
mkdir -p "$menu"
cp "$source_dir/trimui-launch.sh" "$menu/launch.sh"
chmod 755 "$menu/launch.sh"
cp "$source_dir/assets/hardware-buddy.png" "$menu/icon.png"
cat > "$menu/config.json" <<'JSON'
{"label":"Hardware Monitor","icontop":"icon.png","launch":"launch.sh","description":"MQTT hardware dashboard (experimental)"}
JSON
echo 'INSTALLED (experimental): Apps > Hardware Monitor. Select + Start exits; Y blanks backlight only.'
echo 'Chromium/SDL display, physical button labels and screen idle behavior require actual launch testing; see launch.log.'
