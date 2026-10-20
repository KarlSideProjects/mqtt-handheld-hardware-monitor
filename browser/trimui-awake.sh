#!/bin/bash
# Disable stock keymon's automatic dim/off/suspend before installing or displaying the monitor.
set -euo pipefail
mode=${1:-}
base=/mnt/UDISK/hwmonitor
hook=/mnt/SDCARD/System/starts/90-hwmonitor-awake.sh
[[ -x /usr/trimui/bin/systemval ]] || { echo 'TrimUI systemval is required for sleep configuration.' >&2; exit 1; }
case "$mode" in
    --check)
        [[ $(/usr/trimui/bin/systemval dimtime) == 0 && -e /tmp/stay_awake && -e /tmp/stay_alive && -s $hook ]] || { echo 'Automatic-sleep guard missing; rerun the installer.' >&2; exit 1; }
        echo 'PASS: dimtime=0, awake/alive guards and startup hook.'
        exit ;;
    --persist)
        umask 077
        mkdir -p "$base"
        if [[ ! -f $base/original-dimtime ]]; then
            original=$(/usr/trimui/bin/systemval dimtime)
            [[ $original =~ ^-?[0-9]+$ ]] || { echo 'Cannot read original dimtime.' >&2; exit 1; }
            printf '%s\n' "$original" > "$base/original-dimtime"
        fi ;;
    '') ;;
    *) echo 'Usage: trimui-awake.sh [--persist | --check]' >&2; exit 1 ;;
esac
# These flags also protect the current keymon/MainUI session, whose settings may be cached.
touch /tmp/stay_awake /tmp/stay_alive
/usr/trimui/bin/systemval dimtime 0 >/dev/null
[[ $(/usr/trimui/bin/systemval dimtime) == 0 ]] || { echo 'Failed to disable automatic sleep.' >&2; exit 1; }
if [[ $mode == --persist ]]; then
    mkdir -p "$(dirname "$hook")"
    temporary=$(mktemp "$(dirname "$hook")/.hwmonitor-awake.XXXXXXXX")
    trap 'rm -f -- "$temporary"' EXIT
    cat > "$temporary" <<'BOOT'
#!/bin/sh
# Hardware Monitor: keep the stock menu and network awake after reboot.
touch /tmp/stay_awake /tmp/stay_alive
/usr/trimui/bin/systemval dimtime 0 >/dev/null
BOOT
    chmod 755 "$temporary"
    mv "$temporary" "$hook"
fi
echo 'Automatic dim, display-off and idle suspend disabled.'
