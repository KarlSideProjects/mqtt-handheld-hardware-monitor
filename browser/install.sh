#!/bin/bash
# Run on the handheld as ark: bash browser/install.sh [--config /path/to/mqtt.json]
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for arg in "$@"; do
    if [[ $arg == --ssh ]]; then exec bash "$source_dir/install-remote.sh" r36 "$@"; fi
done
app=/home/ark/device-browser
config=
check=0
deps_only=0
fail() { echo "ERROR: $*" >&2; exit 1; }
while (($#)); do
    case "$1" in
        --config) [[ $# -ge 2 ]] || fail '--config requires a JSON file'; config=$2; shift 2 ;;
        --check) check=1; shift ;;
        --deps-only) deps_only=1; shift ;;
        --help) echo 'Usage: bash browser/install.sh [--ssh HOST [--user USER]] [--config FILE | --check | --deps-only]'; exit ;;
        *) fail "Unknown argument: $1" ;;
    esac
done
((check == 0 || deps_only == 0)) || fail 'Choose --check or --deps-only.'
[[ $(id -un) == ark ]] || fail 'Log in as ark; do not run this script with sudo.'
[[ $(uname -m) == aarch64 ]] || fail 'Requires ARM64 R36 MAX 2.'
. /etc/os-release
[[ $ID == debian && $VERSION_ID == 13 ]] || fail 'Requires Debian 13 dArkOS4Clone.'
[[ -d /roms/ports && -e /dev/dri/card0 && -e /dev/input/event2 ]] || fail 'Expected dArkOS display, controls or /roms/ports missing.'
[[ -w /sys/class/backlight/backlight/brightness ]] || fail 'ark needs write permission on the R36 backlight brightness control.'
validate_config() {
    python3 - "$1" <<'PY'
import json, sys
try:
    c = json.load(open(sys.argv[1]))
    assert isinstance(c, dict)
    assert isinstance(c.get('host'), str) and c['host'].strip()
    assert type(c.get('port', 1883)) is int and 1 <= c.get('port', 1883) <= 65535
    assert isinstance(c.get('topic', 'sys/agents/+/metrics'), str) and c.get('topic', 'sys/agents/+/metrics') and '\0' not in c.get('topic', '')
    assert isinstance(c.get('tls', False), bool)
    assert all(isinstance(c.get(key, ''), str) for key in ('username', 'password'))
except (OSError, ValueError, AssertionError):
    sys.exit('Invalid MQTT config: check host, port, topic and tls; credentials are not printed.')
PY
}
verify() {
    for command in chromium startx xset; do command -v "$command" >/dev/null || fail "Missing $command"; done
    python3 -c 'import paho.mqtt.client as m; assert hasattr(m, "CallbackAPIVersion")'
    [[ -s $app/lib/libgbm.so.1 && -s $app/monitor.html && -s /roms/ports/images/hardware-buddy.png ]] || fail 'Application files missing.'
    [[ -x '/roms/ports/Hardware Monitor.sh' && -r /dev/input/event2 ]] || fail 'Launcher or input permissions missing.'
    [[ $(loginctl show-user ark -p Linger --value) == yes ]] || fail 'Run sudo loginctl enable-linger ark.'
    grep -q '^/dev/zram' /proc/swaps || fail 'ZRAM is not active.'
    python3 - <<'PY'
import xml.etree.ElementTree as ET
root=ET.parse('/roms/ports/gamelist.xml').getroot()
assert sum(g.findtext('path')=='./Hardware Monitor.sh' for g in root.findall('game')) == 1
PY
    if [[ -e $app/mqtt-config.json ]]; then
        validate_config "$app/mqtt-config.json"
        [[ $(stat -c %a "$app/mqtt-config.json") == 600 ]] || fail 'MQTT config must have mode 600.'
        echo 'PASS: installed files, menu, dependencies, controls, linger, ZRAM and MQTT config.'
    else
        echo 'PASS: application installed. MQTT setup pending: rerun with --config FILE.'
    fi
}
if ((check)); then verify; exit; fi
[[ -z $config || -f $config ]] || fail 'MQTT config file not found.'
sudo -n true || { [[ -t 0 ]] && sudo -v; } || fail 'Run sudo -v first, then rerun the script.'
if ((deps_only == 0)); then
    pgrep -u ark -f '^python3 (monitor|device_info)\.py$' >/dev/null && fail 'Exit Hardware Monitor / Device Info with Select + B first.'
fi
[[ -f /etc/zram.conf ]] || fail 'This image has no built-in /etc/zram.conf.'
systemctl cat zram-swap.service >/dev/null || fail 'This image has no built-in zram-swap.service.'
# Private backup includes MQTT secrets; never upload it to Git.
umask 077
backup=$(mktemp -d /home/ark/hwmonitor-backup.XXXXXXXX)
paths=(home/ark/device-browser 'roms/ports/Hardware Monitor.sh' 'roms/ports/Device Info.sh' roms/ports/gamelist.xml roms/ports/images/hardware-buddy.png etc/zram.conf)
existing=()
for entry in "${paths[@]}"; do [[ ! -e /$entry ]] || existing+=("$entry"); done
sudo tar -C / -czf "$backup/files.tar.gz" "${existing[@]}"
sudo chown ark:ark "$backup/files.tar.gz"
loginctl show-user ark -p Linger --value > "$backup/linger"
systemctl is-enabled zram-swap.service > "$backup/zram-enabled" || true
systemctl is-active zram-swap.service > "$backup/zram-active" || true
printf 'Backup: %s\n' "$backup"
menu_active=0
systemctl is-active --quiet emulationstation && menu_active=1
work=$(mktemp -d)
cleanup() {
    rm -rf -- "$work"
    if ((menu_active)); then sudo systemctl start emulationstation; fi
}
trap cleanup EXIT
# Skip package installation when the required packages are already configured.
packages=(chromium chromium-sandbox xserver-xorg-core xinit xauth x11-xserver-utils python3 python3-paho-mqtt ca-certificates fonts-dejavu-core procps util-linux)
missing=()
for package in "${packages[@]}"; do
    [[ $(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true) == 'install ok installed' ]] || missing+=("$package")
done
if ((${#missing[@]})); then
    sudo apt-get update
    sudo apt-get install -y --no-install-recommends "${missing[@]}"
fi
# Extract Debian GBM privately; keep the gaming system's Mali libraries intact.
mkdir -p "$app/assets" "$app/lib"
if [[ ! -s $app/lib/libgbm.so.1 ]]; then
    (cd "$work"
     apt-get download libgbm1:arm64 || { sudo apt-get update; apt-get download libgbm1:arm64; }
     dpkg-deb -x ./libgbm1_*_arm64.deb extracted)
    install -m 644 "$work/extracted/usr/lib/aarch64-linux-gnu/libgbm.so.1" "$app/lib/libgbm.so.1"
fi
if ((deps_only)); then
    python3 -c 'import paho.mqtt.client as m; assert hasattr(m,"CallbackAPIVersion")'
    echo 'PASS: Chromium/Xorg, sandbox, Python/MQTT, CA certificates, fonts and private GBM installed.'
    exit
fi
[[ -n $config || ! -e $app/mqtt-config.json ]] || config=$app/mqtt-config.json
setup_args=(--output "$work/mqtt-config.json")
[[ -z $config ]] || setup_args+=(--config "$config")
python3 "$source_dir/mqtt_setup.py" "${setup_args[@]}"
for file in monitor.py device_info.py install-menu.py monitor.html xorg.conf; do
    install -m 644 "$source_dir/$file" "$app/$file"
done
for file in client.sh xserver.sh 'Hardware Monitor.sh' 'Device Info.sh'; do
    install -m 755 "$source_dir/$file" "$app/$file"
done
install -m 644 "$source_dir/assets/hardware-buddy.svg" "$app/assets/"
install -m 600 "$work/mqtt-config.json" "$app/mqtt-config.json"
[[ ! -e $app/mqtt-config.json ]] || chmod 600 "$app/mqtt-config.json"
sudo loginctl enable-linger ark
sudo sed -i 's/^ENABLED=.*/ENABLED=1/' /etc/zram.conf
sudo systemctl enable --now zram-swap.service
if ((menu_active)); then sudo systemctl stop emulationstation; fi
mkdir -p /roms/ports/images
install -m 755 "$app/Hardware Monitor.sh" "$app/Device Info.sh" /roms/ports/
install -m 644 "$source_dir/assets/hardware-buddy.png" /roms/ports/images/
python3 "$app/install-menu.py"
verify
echo 'Open Ports > Hardware Monitor. Select + B exits back to the game menu.'
