#!/bin/bash
# Shared SSH transport for install.sh and install-trimui.sh.
set -euo pipefail
model=${1:?Missing device model}; shift
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case "$model" in
    r36) installer=install.sh; login=ark; factory_password=ark; staging=/home/ark/hwmonitor-install ;;
    trimui) installer=install-trimui.sh; login=root; factory_password=tina; staging=/mnt/UDISK/hwmonitor-install ;;
    *) echo 'Unknown device model.' >&2; exit 1 ;;
esac
host= config= runtime= check=0 deps_only=0
while (($#)); do
    case "$1" in
        --ssh) host=${2:?--ssh requires HOST}; shift 2 ;;
        --user) login=${2:?--user requires USER}; shift 2 ;;
        --config) config=${2:?--config requires FILE}; shift 2 ;;
        --runtime) runtime=${2:?--runtime requires DIR}; shift 2 ;;
        --check) check=1; shift ;;
        --deps-only) deps_only=1; shift ;;
        *) echo "Unknown remote option: $1" >&2; exit 1 ;;
    esac
done
[[ $host =~ ^[a-zA-Z0-9.:-]+$ && $login =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid SSH host/user.' >&2; exit 1; }
[[ -z $config || -f $config ]] || { echo 'MQTT config file not found.' >&2; exit 1; }
[[ -z $runtime || $model == trimui && -d $runtime ]] || { echo '--runtime requires a TrimUI bundle directory.' >&2; exit 1; }
for tool in ssh tar mktemp; do command -v "$tool" >/dev/null; done
umask 077
work=$(mktemp -d)
remote_dir=
opts=(-o ConnectTimeout=8 -o NumberOfPasswordPrompts=1 -o StrictHostKeyChecking=accept-new)
cleanup() {
    if [[ -n $remote_dir ]]; then
        ssh "${opts[@]}" "$login@$host" "rm -rf -- '$remote_dir'" </dev/null >/dev/null 2>&1 || true
    fi
    rm -rf -- "$work"
}
trap cleanup EXIT
cat > "$work/askpass" <<'ASKPASS'
#!/bin/sh
printf '%s\n' "$HWMONITOR_SSH_PASSWORD"
ASKPASS
chmod 700 "$work/askpass"
export SSH_ASKPASS="$work/askpass" SSH_ASKPASS_REQUIRE=force
export DISPLAY=${DISPLAY:-hwmonitor:0}
export HWMONITOR_SSH_PASSWORD=${HWMONITOR_SSH_PASSWORD-$factory_password}
unset factory_password
while ! ssh "${opts[@]}" "$login@$host" true </dev/null 2>"$work/ssh-error"; do
    if ! grep -Eqi 'permission denied|authentication failed' "$work/ssh-error"; then
        cat "$work/ssh-error" >&2
        exit 1
    fi
    [[ -t 0 ]] || { echo 'SSH login rejected. Run in a terminal, or set HWMONITOR_SSH_PASSWORD and --user.' >&2; exit 1; }
    echo 'Default/provided SSH login failed. Enter the device login.' >&2
    read -r -p "SSH username [$login]: " answer
    login=${answer:-$login}
    [[ $login =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Invalid SSH username.' >&2; exit 1; }
    read -r -s -p 'SSH password: ' HWMONITOR_SSH_PASSWORD
    printf '\n' >&2
    export HWMONITOR_SSH_PASSWORD
done
remote_dir=$(ssh "${opts[@]}" "$login@$host" "umask 077; mktemp -d '$staging.XXXXXXXX'" </dev/null)
[[ $remote_dir == "$staging."* && ${remote_dir#"$staging."} =~ ^[a-zA-Z0-9]+$ ]] || { echo 'Unexpected remote staging path.' >&2; exit 1; }
tar -C "$source_dir/.." --exclude='__pycache__' --exclude='*.pyc' --exclude='mqtt-config.json' -cf - browser | ssh "${opts[@]}" "$login@$host" "tar -xf - -C '$remote_dir'"
args=()
if [[ -n $config ]]; then
    ssh "${opts[@]}" "$login@$host" "umask 077; cat > '$remote_dir/mqtt-config.json'" < "$config"
    args+=(--config "$remote_dir/mqtt-config.json")
fi
if [[ -n $runtime ]]; then
    ssh "${opts[@]}" "$login@$host" "mkdir '$remote_dir/runtime'" </dev/null
    tar -C "$runtime" -cf - . | ssh "${opts[@]}" "$login@$host" "tar -xf - -C '$remote_dir/runtime'"
    args+=(--runtime "$remote_dir/runtime")
fi
((check == 0)) || args+=(--check)
((deps_only == 0)) || args+=(--deps-only)
printf -v command 'bash %q' "$remote_dir/browser/$installer"
for arg in "${args[@]}"; do printf -v command '%s %q' "$command" "$arg"; done
# A terminal allows sudo and the MQTT credential fallback to prompt on the handheld.
if [[ -t 0 ]]; then
    ssh -tt "${opts[@]}" "$login@$host" "$command"
else
    ssh "${opts[@]}" "$login@$host" "$command" </dev/null
fi
