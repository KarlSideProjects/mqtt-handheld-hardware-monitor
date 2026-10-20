#!/bin/bash
# Supply temporary private device mounts, then run a command in the application rootfs.
set -euo pipefail
root=${1:?Rootfs required}; shift
[[ $root == /* && -x $root/usr/bin/env && $# -gt 0 ]] || { echo 'Invalid rootfs/command.' >&2; exit 1; }
mkdir "$root/.mount-lock" 2>/dev/null || { echo 'Runtime is already mounted; exit the monitor before updating.' >&2; exit 1; }
mounted=() child=
cleanup() {
    status=$?
    mount_failed=0
    trap - EXIT
    trap '' TERM INT
    if [[ -n $child ]]; then
        kill -TERM -- "-$child" 2>/dev/null || true
        # Avoid recursively waiting in the trap that interrupted the foreground wait.
        for ((attempt=0; attempt<50; attempt++)); do
            kill -0 "$child" 2>/dev/null || break
            sleep .1
        done
        kill -KILL -- "-$child" 2>/dev/null || true
    fi
    for ((i=${#mounted[@]}-1; i>=0; i--)); do
        # Browser workers can outlive the launcher briefly while their IPC connections close.
        for ((attempt=0; attempt<30; attempt++)); do
            if umount "${mounted[i]}" 2>/dev/null; then break; fi
            sleep .1
        done
        if ((attempt == 30)); then echo "Failed to unmount ${mounted[i]}" >&2; status=1; mount_failed=1; fi
    done
    if ((mount_failed == 0)); then rmdir "$root/.mount-lock" || status=1; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
bind() {
    mount --bind "$1" "$2"
    mounted+=("$2")
}
mkdir -p "$root/dev" "$root/proc" "$root/sys" "$root/run/udev" "$root/run/hwmonitor"
chmod 700 "$root/run/hwmonitor"
mount -t tmpfs -o mode=755,size=2m hwmonitor-dev "$root/dev"
mounted+=("$root/dev")
python3 - "$root/dev" <<'PY'
import os, stat, sys
for name, minor in (('null',3), ('zero',5), ('full',7), ('random',8), ('urandom',9)):
    path = os.path.join(sys.argv[1], name)
    os.mknod(path, stat.S_IFCHR | 0o666, os.makedev(1, minor))
    os.chmod(path, 0o666)
PY
for name in tty tty0 tty1 fb0 mali0 ion; do
    if [[ -e /dev/$name ]]; then touch "$root/dev/$name"; bind "/dev/$name" "$root/dev/$name"; fi
done
for name in dri input dma_heap; do
    if [[ -d /dev/$name ]]; then mkdir -p "$root/dev/$name"; bind "/dev/$name" "$root/dev/$name"; fi
done
mkdir -p "$root/dev/shm" "$root/dev/pts"
mount -t tmpfs -o mode=1777,size=128m hwmonitor-shm "$root/dev/shm"
mounted+=("$root/dev/shm")
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$root/dev/pts"
mounted+=("$root/dev/pts")
ln -s pts/ptmx "$root/dev/ptmx"
ln -s /proc/self/fd "$root/dev/fd"
bind /proc "$root/proc"
bind /sys "$root/sys"
[[ ! -d /run/udev ]] || bind /run/udev "$root/run/udev"
chroot "$root" /usr/bin/setsid /usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 DEBIAN_FRONTEND=noninteractive XDG_RUNTIME_DIR=/run/hwmonitor \
    "$@" &
child=$!
wait "$child"
child=
