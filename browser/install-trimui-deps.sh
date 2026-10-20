#!/bin/bash
# Bootstrap an official, checksum-pinned Debian ARM64 rootfs without changing Buildroot.
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
base_url=https://raw.githubusercontent.com/debuerreotype/docker-debian-artifacts/cf1f4a45447842b45e9952e0f018ae734a7341c7/bookworm/slim/oci/blobs/rootfs.tar.gz
base_sha=c75f989a229d12b2d2613a5997de9ff3546f664c22da9248720033a2410220f6

fetch_base() {
    # This fixed archive's pinned hash authenticates the CA bootstrap; nothing is extracted before verification.
    curl --fail --location --retry 3 --connect-timeout 15 --insecure "$base_url" -o "$1"
    printf '%s  %s\n' "$base_sha" "$1" | sha256sum -c -
}

main() {
    runtime=${1:?Runtime directory required}
    [[ $(id -u) == 0 && $(uname -m) == aarch64 ]] || { echo 'Requires root on ARM64 TrimUI.' >&2; exit 1; }
    bash "$source_dir/trimui-awake.sh" --persist
    for command in curl sha256sum tar mount umount chroot python3; do command -v "$command" >/dev/null; done
    [[ ! -d $runtime/rootfs/.mount-lock ]] || { echo 'Exit the monitor before updating runtime.' >&2; exit 1; }
    umask 077
    mkdir -p "$runtime"
    root=$runtime/rootfs
    if [[ ! -x $root/usr/bin/apt-get ]]; then
        available=$(df -Pk "$runtime" | awk 'END {print $4}')
        ((available >= 1500000)) || { echo 'At least 1.5 GB free internal storage is required.' >&2; exit 1; }
        stage=$(mktemp -d "$runtime/.bootstrap.XXXXXXXX")
        trap 'rm -rf -- "$stage"' EXIT
        fetch_base "$stage/base.tar.gz"
        mkdir "$stage/rootfs"
        # BusyBox tar applies the caller's umask; Debian's _apt user needs the archived public modes.
        umask 000
        gzip -dc "$stage/base.tar.gz" | tar -xf - -C "$stage/rootfs"
        umask 077
        [[ -x $stage/rootfs/usr/bin/apt-get && -f $stage/rootfs/usr/share/keyrings/debian-archive-keyring.gpg ]] || { echo 'Invalid Debian base archive.' >&2; exit 1; }
        [[ ! -e $root ]] || { echo 'Incomplete rootfs exists; preserve it for diagnosis before retrying.' >&2; exit 1; }
        mv "$stage/rootfs" "$root"
        rm -rf -- "$stage"
        trap - EXIT
    fi
    # Resolve DNS normally; the Debian image already contains the signed archive keyring.
    rm -f "$root/etc/resolv.conf"
    cp /etc/resolv.conf "$root/etc/resolv.conf"
    chmod 755 "$root"
    chmod 644 "$root/etc/resolv.conf"
    cat > "$root/etc/apt/apt.conf.d/80hwmonitor-network" <<'APT'
Acquire::Retries "3";
Acquire::ForceIPv4 "true";
Acquire::http::Timeout "20";
APT
    mkdir -p "$root/opt" "$runtime/bin" "$root/usr/sbin"
    printf '#!/bin/sh\nexit 101\n' > "$root/usr/sbin/policy-rc.d"
    chmod 755 "$root/usr/sbin/policy-rc.d"
    # Headless Chromium uses Debian libraries; the native SDL presenter keeps the vendor GPU ABI.
    python3 -c 'import ctypes; ctypes.CDLL("libSDL2.so"); ctypes.CDLL("libSDL2_image.so")'
    install -m 755 "$source_dir/trimui-rootfs.sh" "$runtime/run-rootfs.sh"
    "$runtime/run-rootfs.sh" "$root" /usr/bin/env -u LD_LIBRARY_PATH /bin/sh -ec '
        dpkg --configure -a || true
        apt-get update -o APT::Update::Error-Mode=any
        apt-get -f install -y --no-install-recommends
        apt-get install -y --no-install-recommends chromium chromium-sandbox libgl1-mesa-dri libgbm1 ca-certificates fonts-dejavu-core python3-pip util-linux
        printf "paho-mqtt==2.1.0 --hash=sha256:6db9ba9b34ed5bc6b6e3812718c7e06e2fd7444540df2455d2c51bd58808feee\n" > /tmp/hwmonitor-requirements.txt
        printf "websocket-client==1.8.0 --hash=sha256:17b44cc997f5c498e809b22cdf2d9c7a9e71c02c8cc2b6c56e7c2d1239bfa526\n" >> /tmp/hwmonitor-requirements.txt
        python3 -m pip install --no-cache-dir --disable-pip-version-check --upgrade --target /opt/hwmonitor-python --require-hashes -r /tmp/hwmonitor-requirements.txt
        apt-get clean
        chromium --version
    '
    [[ ! -e $runtime/python || -L $runtime/python ]] || { echo 'Existing runtime/python directory conflicts with automatic runtime.' >&2; exit 1; }
    ln -sfn rootfs/opt/hwmonitor-python "$runtime/python"
    install -m 755 "$source_dir/trimui-headless.sh" "$root/opt/hwmonitor-headless.sh"
    install -m 644 "$source_dir/trimui_browser.py" "$runtime/trimui_browser.py"
    cat > "$runtime/bin/chromium" <<'CHROMIUM'
#!/bin/bash
set -euo pipefail
runtime=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} == --version ]]; then
    if grep -Fq " $runtime/rootfs/proc " /proc/mounts; then
        exec chroot "$runtime/rootfs" /usr/bin/env -i PATH=/usr/bin:/bin HOME=/root LANG=C.UTF-8 /usr/bin/chromium --version
    fi
    exec "$runtime/run-rootfs.sh" "$runtime/rootfs" /usr/bin/env -u LD_LIBRARY_PATH /usr/bin/chromium --version
fi
export PYTHONPATH="$runtime/python${PYTHONPATH:+:$PYTHONPATH}"
exec python3 "$runtime/trimui_browser.py" "$@"
CHROMIUM
    chmod 755 "$runtime/bin/chromium"
    PYTHONPATH="$runtime/python" python3 -c 'import paho.mqtt.client as m; assert hasattr(m,"CallbackAPIVersion")'
    "$runtime/bin/chromium" --version
    PYTHONPATH="$runtime/python" python3 -c 'import websocket; assert websocket.__version__ == "1.8.0"'
    touch "$runtime/.deps-ready"
    echo 'PASS: headless Chromium, native SDL presenter, sandbox, CA, fonts, paho-mqtt and websocket-client installed.'
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
