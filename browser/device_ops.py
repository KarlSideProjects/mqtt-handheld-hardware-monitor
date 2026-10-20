"""Bounded, credential-free operations for an already running handheld dashboard."""
import base64
import contextlib
import ctypes as C
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import threading
import time
import urllib.request
import secrets
import signal
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UI_FILES = ('monitor.html', 'pve.js', 'assets/hardware-buddy.svg')
BACKEND_FILES = {'r36': ('monitor.py', 'pve.py'),
                 'trimui': ('monitor.py', 'pve.py', 'trimui_monitor.py')}
ROOTS = {'r36': Path('/home/ark/device-browser'),
         'trimui': Path('/mnt/UDISK/hwmonitor/app')}
MARKER = '__HWMONITOR_REVISION__'
ACK_MARKER = '__HWMONITOR_ACK_URL__'
TITLE = re.compile(r'^Hardware Monitor \[([a-f0-9]{64})\]')


class OpsError(Exception):
    def __init__(self, code, recovery=None):
        super().__init__(code)
        self.code, self.recovery = code, recovery


def digest(data):
    return hashlib.sha256(data).hexdigest()


def release_digest(files, backend):
    h = hashlib.sha256()
    for name, data in sorted(files.items()):
        h.update(name.encode() + b'\0' + data + b'\0')
    h.update(json.dumps(backend, sort_keys=True).encode())
    return h.hexdigest()


def make_release(root, device):
    root = Path(root)
    files = {name: (root / name).read_bytes() for name in UI_FILES}
    if files['monitor.html'].count(MARKER.encode()) != 1 or files['monitor.html'].count(ACK_MARKER.encode()) != 1:
        raise OpsError('source_revision_marker_missing')
    backend = {name: digest((root / name).read_bytes()) for name in BACKEND_FILES[device]}
    return {'device': device, 'revision': release_digest(files, backend), 'backend': backend,
            'files': {name: base64.b64encode(data).decode() for name, data in files.items()}}


def validate_release(root, release):
    device = release.get('device')
    if device not in ROOTS or set(release.get('files', {})) != set(UI_FILES):
        raise OpsError('invalid_release')
    backend = release.get('backend', {})
    if set(backend) != set(BACKEND_FILES[device]):
        raise OpsError('invalid_release')
    try:
        files = {name: base64.b64decode(data, validate=True) for name, data in release['files'].items()}
    except (ValueError, TypeError):
        raise OpsError('invalid_release') from None
    if sum(map(len, files.values())) > 2 * 1024 * 1024:
        raise OpsError('invalid_release')
    revision = release.get('revision')
    if (revision != release_digest(files, backend) or files['monitor.html'].count(MARKER.encode()) != 1
            or files['monitor.html'].count(ACK_MARKER.encode()) != 1):
        raise OpsError('invalid_release')
    for name, expected in backend.items():
        if not (root / name).is_file() or digest((root / name).read_bytes()) != expected:
            raise OpsError('backend_requires_install')
    files['monitor.html'] = files['monitor.html'].replace(MARKER.encode(), revision.encode())
    for name in UI_FILES:
        p = root / name
        if p.is_symlink() or p.parent.is_symlink() or not p.is_file():
            raise OpsError('unsafe_application_path')
    return files


def read_status():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8766/status', timeout=3) as response:
            data = response.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            raise ValueError()
        state = json.loads(data)
        if not isinstance(state, dict) or not isinstance(state.get('hosts'), list):
            raise ValueError()
        return state
    except (OSError, ValueError):
        raise OpsError('monitor_unavailable') from None


def summarize_status(state, device):
    hosts = []
    for host in state.get('hosts', []):
        v = host.get('virtualization') or {}
        hosts.append({'host': host.get('host'), 'pve_status': v.get('status'),
                      'guest_count': v.get('guest_count'), 'fresh': v.get('fresh'),
                      'age_seconds': v.get('age_seconds')})
        docker = host.get('docker')
        if isinstance(docker, dict):
            hosts[-1]['docker'] = {k: docker.get(k) for k in ('status', 'guest_count', 'fresh', 'age_seconds')}
            if docker.get('error') is not None:
                allowed = {'api_unavailable', 'permission_denied', 'api_error', 'invalid_response',
                           'invalid_inventory', 'invalid_stats', 'response_too_large', 'capacity_error',
                           'container_restarted', 'poll_timeout', 'not_observed'}
                hosts[-1]['docker']['error'] = docker['error'] if docker['error'] in allowed else 'unknown_error'
    return {'device': device, 'connection': state.get('connection'), 'online_hosts': state.get('count'),
            'bad_messages': state.get('bad_messages'), 'screen_off': state.get('screen_off', False),
            'view': {k: state.get(k) for k in ('selected', 'detail', 'focus', 'pve_view', 'pve_guest_id', 'resource_provider')},
            'hosts': hosts}


def preflight(device, root, state):
    if root != ROOTS[device] or root.is_symlink() or os.uname().machine != 'aarch64':
        raise OpsError('wrong_device')
    if device == 'trimui':
        if state.get('device', {}).get('name') != 'TrimUI':
            raise OpsError('wrong_device')
    else:
        release = Path('/etc/os-release').read_text()
        if not re.search(r'^ID=[\"\']?debian[\"\']?$', release, re.M) or not re.search(r'^VERSION_ID=[\"\']?13[\"\']?$', release, re.M):
            raise OpsError('wrong_device')
        if state.get('device', {}).get('name') == 'TrimUI' or not Path('/dev/input/event2').exists():
            raise OpsError('wrong_device')
    if state.get('screen_off'):
        raise OpsError('wake_monitor_before_update')


def wait_revision(browser, expected, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 8
    while clock() < deadline:
        if browser.loaded_revision() == expected:
            return
        sleep(.2)
    raise OpsError('loaded_revision_timeout')


class RevisionReceipt:
    """A temporary loopback endpoint receives one nonce-bound render receipt."""
    def __init__(self, revision):
        self.revision, self.received = revision, threading.Event()
        path = '/loaded/' + secrets.token_urlsafe(24) + '/' + revision
        receipt = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != path:
                    self.send_error(404)
                    return
                receipt.received.set()
                self.send_response(204)
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_address[1]}' + path

    def loaded_revision(self):
        return self.revision if self.received.is_set() else None

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def last_verification(root):
    try:
        record = json.loads((root / '.ui-verification.json').read_text())
        if all(digest((root / name).read_bytes()) == record['ui_sha256'][name] for name in UI_FILES):
            return {'revision': record['revision'], 'verified_at': record['verified_at']}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def verify_live(reader, clock=time.monotonic, sleep=time.sleep):
    # Monitor expires senders after 10 seconds; a longer observation proves new input.
    deadline = clock() + 11
    while True:
        state = reader()
        if state.get('connection') != 'Connected' or type(state.get('count')) is not int or state['count'] < 1:
            raise OpsError('mqtt_not_live')
        if clock() >= deadline:
            return state
        sleep(.5)


def atomic_write(path, data, mode):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
            os.fchmod(output.fileno(), mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply_update(root, release, browser, reader, clock=time.monotonic, sleep=time.sleep):
    root = Path(root)
    files = validate_release(root, release)
    old_revision = browser.loaded_revision()
    modes = {name: stat.S_IMODE((root / name).stat().st_mode) for name in UI_FILES}
    backup = Path(tempfile.mkdtemp(prefix='hwmonitor-ui-backup.', dir=root.parent))
    for name in UI_FILES:
        (backup / name).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(root / name, backup / name)
        (backup / name).chmod(0o600)
    (backup / 'revision.json').write_text(json.dumps({'old': old_revision, 'new': release['revision']}))
    (backup / 'revision.json').chmod(0o600)
    try:
        with contextlib.closing(RevisionReceipt(release['revision'])) as receipt:
            files['monitor.html'] = files['monitor.html'].replace(ACK_MARKER.encode(), receipt.url.encode())
            for name, data in files.items():
                atomic_write(root / name, data, modes[name])
            browser.reload()
            wait_revision(receipt, release['revision'], clock, sleep)
            state = verify_live(reader, clock, sleep)
        record = {'revision': release['revision'], 'verified_at': int(time.time()),
                  'ui_sha256': {name: digest((root / name).read_bytes()) for name in UI_FILES}}
        atomic_write(root / '.ui-verification.json', json.dumps(record).encode(), 0o600)
        return {'revision': release['revision'], 'loaded': True, 'backup': str(backup),
                'mqtt_observation_seconds': 11, 'status': summarize_status(state, release['device'])}
    except Exception as error:
        recovery = {'backup': str(backup), 'files_restored': False, 'page_revision_restored': False}
        try:
            for name in UI_FILES:
                atomic_write(root / name, (backup / name).read_bytes(), modes[name])
            recovery['files_restored'] = True
            browser.reload()
            if old_revision:
                wait_revision(browser, old_revision, clock, sleep)
                recovery['page_revision_restored'] = True
        except Exception:
            pass
        raise OpsError(error.code if isinstance(error, OpsError) else 'update_failed', recovery) from None


STOCK_QUEUE = Path('/tmp/cmd_to_run.sh')
TRIMUI_COMMAND = b'#!/bin/sh\nexec /mnt/SDCARD/Apps/HardwareMonitor/launch.sh\n'


def processes(proc=Path('/proc')):
    result = []
    for path in proc.glob('[0-9]*/cmdline'):
        try:
            fields = (path.parent / 'stat').read_text().rsplit(')', 1)[1].split()
            args = [x.decode(errors='replace') for x in path.read_bytes().split(b'\0') if x]
            result.append({'pid': int(path.parent.name), 'ppid': int(fields[1]), 'started': fields[19],
                           'name': (path.parent / 'comm').read_text().strip(), 'args': args,
                           'exe': str((path.parent / 'exe').resolve(strict=True)),
                           'cwd': str((path.parent / 'cwd').resolve(strict=True))})
        except (OSError, ValueError, IndexError):
            continue
    return result


def signal_process(expected, sig):
    current = next((p for p in processes() if p['pid'] == expected['pid']), None)
    if current is None:
        return
    if current != expected:
        raise OpsError('process_changed')
    # A pidfd binds the signal to this process even if its numeric PID is reused.
    try:
        fd = os.pidfd_open(expected['pid'])
        try:
            current = next((p for p in processes() if p['pid'] == expected['pid']), None)
            if current != expected:
                raise OpsError('process_changed')
            signal.pidfd_send_signal(fd, sig)
        finally:
            os.close(fd)
    except ProcessLookupError:
        pass


def monitor_processes(device, rows):
    root = ROOTS[device]
    filename = 'trimui_monitor.py' if device == 'trimui' else 'monitor.py'
    return [p for p in rows if len(p['args']) >= 2 and Path(p['args'][0]).name == 'python3'
            and (p['args'][1] == str(root / filename) or p['args'][1] == filename and p['cwd'] == str(root))]


def display_health(device):
    rows = processes()
    monitors = monitor_processes(device, rows)
    if device == 'trimui':
        renderers = [p for p in rows if len(p['args']) >= 2 and p['args'][1] == '/mnt/UDISK/hwmonitor/runtime/trimui_browser.py']
        loops = [p for p in rows if len(p['args']) >= 2 and p['args'][1] == '/usr/trimui/bin/runtrimui.sh']
        menus = [p for p in rows if p['name'] == 'MainUI']
        stock_parent = len(monitors) == 1 and monitors[0]['ppid'] in {p['pid'] for p in loops}
    else:
        renderers = [p for p in rows if len(p['args']) >= 2 and Path(p['args'][0]).name in ('sh', 'bash')
                     and p['args'][1] == str(ROOTS[device] / 'client.sh')]
        menus, stock_parent = [], None
    return {'monitor_count': len(monitors), 'renderer_count': len(renderers),
            'mainui_count': len(menus), 'stock_parent': stock_parent}


def display_log(device, root):
    return root.parent / 'launch.log' if device == 'trimui' else root / 'page.log'


def launch_preflight(device, root):
    if device not in ROOTS or root != ROOTS[device] or root.is_symlink() or os.uname().machine != 'aarch64':
        raise OpsError('wrong_device')
    release = Path('/etc/os-release').read_text()
    if device == 'trimui':
        if not re.search(r'^ID=[\"\']?buildroot[\"\']?$', release, re.M) or b'allwinner,a523' not in Path('/proc/device-tree/compatible').read_bytes():
            raise OpsError('wrong_device')
        launcher = Path('/mnt/SDCARD/Apps/HardwareMonitor/launch.sh')
    else:
        if not re.search(r'^ID=[\"\']?debian[\"\']?$', release, re.M) or not re.search(r'^VERSION_ID=[\"\']?13[\"\']?$', release, re.M):
            raise OpsError('wrong_device')
        launcher = Path('/roms/ports/Hardware Monitor.sh')
    if launcher.is_symlink() or not launcher.is_file() or not root.is_dir():
        raise OpsError('launcher_unavailable')
    return launcher


def restart_monitor(device, root, reader=read_status, clock=time.monotonic, sleep=time.sleep):
    root = Path(root)
    launcher = launch_preflight(device, root)
    def wait_for(predicate, seconds, code):
        deadline = clock() + seconds
        while not predicate():
            if clock() >= deadline:
                raise OpsError(code)
            sleep(.25)
    rows = processes()
    old = monitor_processes(device, rows)
    if len(old) > 1:
        raise OpsError('multiple_monitors')
    if device == 'trimui':
        if STOCK_QUEUE.is_symlink() or STOCK_QUEUE.exists() and (not old or STOCK_QUEUE.stat().st_size != len(TRIMUI_COMMAND) or STOCK_QUEUE.read_bytes() != TRIMUI_COMMAND):
            raise OpsError('launch_queue_busy')
        # Validate the stock owner before stopping a healthy existing monitor.
        loops = [p for p in rows if len(p['args']) >= 2 and p['args'][1] == '/usr/trimui/bin/runtrimui.sh']
        menus = [p for p in rows if p['name'] == 'MainUI']
        if len(loops) != 1 or len(menus) > 1 or any(p['ppid'] != loops[0]['pid'] or p['exe'] not in ('/usr/trimui/bin/MainUI', '/mnt/UDISK/trimui/bin/MainUI') for p in menus):
            raise OpsError('unsafe_stock_launcher')
        if STOCK_QUEUE.exists() and old[0]['ppid'] != loops[0]['pid']:
            raise OpsError('launch_queue_busy')
        if not old and len(menus) != 1:
            raise OpsError('unsafe_stock_launcher')
    for process in old:
        signal_process(process, signal.SIGTERM)
    wait_for(lambda: not monitor_processes(device, processes()) and display_health(device)['renderer_count'] == 0,
             15, 'monitor_stop_timeout')
    log = display_log(device, root)
    before = log.stat() if log.exists() else None
    offset = before.st_size if before else 0
    queued = False
    try:
        if device == 'trimui':
            def menu_ready():
                return not STOCK_QUEUE.exists() and len([p for p in processes() if p['name'] == 'MainUI']) == 1
            wait_for(menu_ready, 15, 'stock_menu_unavailable')
            menu = next(p for p in processes() if p['name'] == 'MainUI')
            if menu['ppid'] != loops[0]['pid'] or menu['exe'] not in ('/usr/trimui/bin/MainUI', '/mnt/UDISK/trimui/bin/MainUI'):
                raise OpsError('unsafe_stock_launcher')
            fd = os.open(STOCK_QUEUE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o700)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(TRIMUI_COMMAND)
                handle.flush()
                os.fsync(handle.fileno())
            queued = True
            signal_process(menu, signal.SIGTERM)
            deadline = clock() + 2
            while clock() < deadline and any(p == menu for p in processes()):
                sleep(.25)
            if any(p == menu for p in processes()):
                signal_process(menu, signal.SIGKILL)
        else:
            result = subprocess.run(['sudo', '-n', 'systemctl', 'stop', 'emulationstation'], capture_output=True, timeout=10)
            if result.returncode:
                raise OpsError('menu_stop_failed')
            with (root / 'deploy-launch.log').open('ab') as output:
                subprocess.Popen(['bash', str(launcher)], stdin=subprocess.DEVNULL, stdout=output,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        def running():
            health = display_health(device)
            return health['monitor_count'] == 1 and health['renderer_count'] == 1 and health['mainui_count'] == 0 and (device != 'trimui' or health['stock_parent'])
        wait_for(running, 30, 'display_start_timeout')
        def mqtt_ready():
            try:
                state = reader()
                return state.get('connection') == 'Connected' and type(state.get('count')) is int and state['count'] > 0
            except OpsError:
                return False
        wait_for(mqtt_ready, 30, 'mqtt_not_live')
        deadline = clock() + 12
        while True:
            if not running():
                raise OpsError('display_process_conflict')
            state = reader()
            if state.get('connection') != 'Connected' or type(state.get('count')) is not int or state['count'] < 1:
                raise OpsError('mqtt_not_live')
            if device == 'trimui':
                if not log.is_file():
                    raise OpsError('display_log_unavailable')
                current = log.stat()
                if before and (current.st_ino != before.st_ino or current.st_size < offset):
                    raise OpsError('display_log_changed')
                with log.open('rb') as handle:
                    handle.seek(offset)
                    new = handle.read(262145)
                if len(new) > 262144:
                    raise OpsError('display_log_overflow')
                if b'Could not queue pageflip' in new:
                    raise OpsError('display_pageflip_error')
            if clock() >= deadline:
                return {'status': summarize_status(state, device), 'display': display_health(device),
                        'mqtt_observation_seconds': 12, 'new_pageflip_errors': 0 if device == 'trimui' else None}
            sleep(.5)
    except Exception:
        for process in monitor_processes(device, processes()):
            signal_process(process, signal.SIGTERM)
        wait_for(lambda: not monitor_processes(device, processes()) and display_health(device)['renderer_count'] == 0,
                 15, 'recovery_stop_timeout')
        if device == 'trimui' and queued and STOCK_QUEUE.exists() and not STOCK_QUEUE.is_symlink() and STOCK_QUEUE.read_bytes() == TRIMUI_COMMAND:
            # Remove only our own queue when the stock loop has not consumed it.
            if any(p['name'] == 'MainUI' for p in processes()):
                STOCK_QUEUE.unlink()
        if device == 'r36':
            subprocess.run(['sudo', '-n', 'systemctl', 'start', 'emulationstation'], capture_output=True, timeout=10)
        raise



class R36Browser:
    def __init__(self):
        self.x = C.CDLL('libX11.so.6')
        self.x.XOpenDisplay.argtypes, self.x.XOpenDisplay.restype = [C.c_char_p], C.c_void_p
        self.x.XDefaultRootWindow.argtypes, self.x.XDefaultRootWindow.restype = [C.c_void_p], C.c_ulong
        self.x.XQueryTree.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong),
                                     C.POINTER(C.POINTER(C.c_ulong)), C.POINTER(C.c_uint)]
        self.x.XFetchName.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_void_p)]
        self.x.XFree.argtypes = [C.c_void_p]
        self.x.XCloseDisplay.argtypes = [C.c_void_p]
        self.display = self.x.XOpenDisplay(b':0')
        if not self.display:
            raise OpsError('browser_unavailable')

    def close(self):
        self.x.XCloseDisplay(self.display)

    def window(self):
        self.x.XInternAtom.argtypes, self.x.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
        self.x.XGetWindowProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong, C.c_long, C.c_long,
            C.c_int, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_int), C.POINTER(C.c_ulong),
            C.POINTER(C.c_ulong), C.POINTER(C.c_void_p)]
        atom = self.x.XInternAtom(self.display, b'_NET_WM_NAME', 1)
        pending = [(self.x.XDefaultRootWindow(self.display), 0)]
        for _ in range(200):
            if not pending:
                break
            window, depth = pending.pop(0)
            actual_type, count, remaining = C.c_ulong(), C.c_ulong(), C.c_ulong()
            format_ = C.c_int()
            value = C.c_void_p()
            if atom and self.x.XGetWindowProperty(self.display, window, atom, 0, 1024, 0, 0,
                    C.byref(actual_type), C.byref(format_), C.byref(count), C.byref(remaining), C.byref(value)) == 0 and value.value:
                try:
                    if format_.value == 8:
                        name = C.string_at(value.value, min(count.value, 4096)).decode(errors='replace')
                        if name.startswith('Hardware Monitor'):
                            return window, name
                finally:
                    self.x.XFree(value)
            if depth < 3:
                root, parent, child_count = C.c_ulong(), C.c_ulong(), C.c_uint()
                children = C.POINTER(C.c_ulong)()
                if self.x.XQueryTree(self.display, window, C.byref(root), C.byref(parent), C.byref(children), C.byref(child_count)):
                    try:
                        pending.extend((children[i], depth + 1) for i in range(min(child_count.value, 200)))
                    finally:
                        if children:
                            self.x.XFree(children)
        raise OpsError('browser_unavailable')

    def loaded_revision(self):
        match = TITLE.match(self.window()[1])
        return match[1] if match else None

    def reload(self):
        window, _ = self.window()
        self.x.XSetInputFocus.argtypes = [C.c_void_p, C.c_ulong, C.c_int, C.c_ulong]
        self.x.XStringToKeysym.argtypes, self.x.XStringToKeysym.restype = [C.c_char_p], C.c_ulong
        self.x.XKeysymToKeycode.argtypes, self.x.XKeysymToKeycode.restype = [C.c_void_p, C.c_ulong], C.c_ubyte
        self.x.XFlush.argtypes = [C.c_void_p]
        test = C.CDLL('libXtst.so.6')
        test.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        key = self.x.XKeysymToKeycode(self.display, self.x.XStringToKeysym(b'F5'))
        self.x.XSetInputFocus(self.display, window, 1, 0)
        if not key or not test.XTestFakeKeyEvent(self.display, key, 1, 0) or not test.XTestFakeKeyEvent(self.display, key, 0, 0):
            raise OpsError('browser_reload_failed')
        self.x.XFlush(self.display)


class TrimuiBrowser:
    def __init__(self):
        runtime = Path('/mnt/UDISK/hwmonitor/runtime')
        sys.path.insert(0, str(runtime / 'python'))
        sys.path.insert(0, str(runtime))
        import websocket
        from trimui_browser import CDP
        port = int((runtime / 'rootfs/var/lib/hwmonitor-browser/profile/DevToolsActivePort').read_text().splitlines()[0])
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=3) as response:
            page = next(p for p in json.load(response) if p['type'] == 'page' and p['url'] == 'http://127.0.0.1:8766/')
        self.socket = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=3, suppress_origin=True)
        self.cdp = CDP(self.socket)

    def close(self):
        self.socket.close()

    def loaded_revision(self):
        result = self.cdp.call('Runtime.evaluate', expression='document.title', returnByValue=True)
        match = TITLE.match(result['result'].get('value', ''))
        return match[1] if match else None

    def reload(self):
        self.cdp.call('Page.reload', ignoreCache=True)


def remote_main():
    try:
        data = sys.stdin.buffer.read(3 * 1024 * 1024 + 1)
        if len(data) > 3 * 1024 * 1024:
            raise OpsError('invalid_request')
        request = json.loads(data)
        device, action = request.get('device'), request.get('action')
        if device not in ROOTS or action not in ('diagnose', 'update', 'restart'):
            raise OpsError('invalid_request')
        root = ROOTS[device]
        if action == 'restart':
            launch_preflight(device, root)
        else:
            state = read_status()
            preflight(device, root, state)
        with contextlib.ExitStack() as stack:
            if action != 'diagnose':
                fd = os.open(root.parent / '.hwmonitor-ui-update.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
                handle = stack.enter_context(os.fdopen(fd, 'r+'))
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise OpsError('update_in_progress') from None
            if action == 'restart':
                result = restart_monitor(device, root)
            browser = stack.enter_context(contextlib.closing(R36Browser() if device == 'r36' else TrimuiBrowser()))
            if action == 'diagnose':
                result = {'status': summarize_status(state, device), 'loaded_revision': browser.loaded_revision(),
                          'last_verified_update': last_verification(root), 'display': display_health(device),
                          'ui_sha256': {name: digest((root / name).read_bytes()) for name in UI_FILES}}
            elif action == 'restart':
                result['loaded_revision'] = browser.loaded_revision()
            else:
                if request.get('release', {}).get('device') != device:
                    raise OpsError('invalid_release')
                result = apply_update(root, request['release'], browser, read_status)
        print(json.dumps({'ok': True, **result}))
    except OpsError as error:
        print(json.dumps({'ok': False, 'error': error.code, 'recovery': error.recovery}))
        raise SystemExit(1)
    except Exception as error:
        print(json.dumps({'ok': False, 'error': 'operation_failed', 'exception_type': type(error).__name__}))
        raise SystemExit(1)
