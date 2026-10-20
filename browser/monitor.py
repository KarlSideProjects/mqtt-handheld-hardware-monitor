#!/usr/bin/env python3
"""MQTT receiver and local dashboard for the existing hwmonitor-mqtt senders."""
import fcntl
import json
import math
import os
import select
import signal
import struct
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SECTIONS = ('cpu', 'gpu', 'memory', 'network', 'disks', 'temperatures', 'history')
BUTTONS = {708: 'screen', 305: 'detail', 304: 'back', 705: 'toggle', 310: 'previous',
           311: 'next', 544: 'up', 545: 'down', 546: 'left', 547: 'right'}


def number(value):
    if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value):
        return value
    return None


def block(value):
    return value if isinstance(value, dict) else {}


def normalize(data):
    cpu, memory = block(data.get('cpu')), block(data.get('memory'))
    temps = block(data.get('temperatures'))
    cpu_temps = [number(item.get('current')) for key in ('cpu', 'coretemp', 'k10temp', 'cpu_thermal')
                 for item in (temps.get(key) if isinstance(temps.get(key), list) else [])
                 if isinstance(item, dict)]
    gpu = data.get('gpus') or data.get('gpu') or []
    if isinstance(gpu, dict):
        gpu = [gpu]
    gpu = [block(g) for g in gpu] if isinstance(gpu, list) else []
    ram, swap = block(memory.get('ram')), block(memory.get('swap'))
    net = block(data.get('network_io'))
    disks = block(data.get('disk_io'))
    def maximum(values):
        return max((v for v in values if v is not None), default=None)
    rates = block(block(net.get('total')).get('rate'))
    disk_rates = [block(block(d).get('rate')) for d in disks.values()]
    return {'cpu': number(cpu.get('percent_total')), 'ram': number(ram.get('percent')),
            'cpu_temp': maximum(cpu_temps),
            'gpu': maximum(number(g.get('usage_percent')) for g in gpu),
            'gpu_temp': maximum(number(g.get('temperature_celsius')) for g in gpu),
            'cores': [number(v) for v in cpu.get('percent_per_core', [])] if isinstance(cpu.get('percent_per_core'), list) else [],
            'ram_used': number(ram.get('used')), 'ram_total': number(ram.get('total')),
            'swap': number(swap.get('percent')),
            'gpus': gpu, 'network': net, 'disks': disks, 'temperatures': temps,
            'rx': number(rates.get('rx_bytes_per_s')), 'tx': number(rates.get('tx_bytes_per_s')),
            'read': sum(number(r.get('read_bytes_per_s')) or 0 for r in disk_rates) if disks else None,
            'write': sum(number(r.get('write_bytes_per_s')) or 0 for r in disk_rates) if disks else None}


class LocalStatus:
    """Read the handheld, independently of the MQTT hosts, at most once per 2 seconds."""
    def __init__(self, proc=Path('/proc'), supplies=Path('/sys/class/power_supply'), thermal=Path('/sys/class/thermal'),
                 thermal_types=('soc-thermal',)):
        self.proc, self.supplies, self.thermal = proc, supplies, thermal
        self.thermal_types = thermal_types
        self.previous = None
        self.updated = -math.inf
        self.data = {}

    @staticmethod
    def read(path):
        try:
            return path.read_text().strip()
        except OSError:
            return ''

    def sample(self, now=None):
        now = time.monotonic() if now is None else now
        if now - self.updated < 2:
            return self.data
        data = {'cpu': None, 'memory': None, 'temperature': None, 'battery': None,
                'charging': False, 'plugged': False, 'battery_status': 'Unknown'}
        try:
            ticks = [int(v) for v in self.read(self.proc / 'stat').splitlines()[0].split()[1:9]]
            total, idle = sum(ticks), ticks[3] + ticks[4]
            if self.previous and total > self.previous[0]:
                data['cpu'] = min(100, max(0, 100 * (1 - (idle - self.previous[1]) / (total - self.previous[0]))))
            self.previous = total, idle
        except (ValueError, IndexError):
            pass
        try:
            mem = {k: int(v.split()[0]) for k, v in (line.split(':', 1) for line in self.read(self.proc / 'meminfo').splitlines())}
            data['memory'] = min(100, max(0, (1 - mem['MemAvailable'] / mem['MemTotal']) * 100))
        except (ValueError, KeyError, IndexError, ZeroDivisionError):
            pass
        for zone in sorted(self.thermal.glob('thermal_zone*')):
            if self.read(zone / 'type') in self.thermal_types:
                try:
                    data['temperature'] = int(self.read(zone / 'temp')) / 1000
                except ValueError:
                    pass
                break
        for supply in self.supplies.glob('*'):
            if self.read(supply / 'type') == 'Battery':
                data['battery_status'] = self.read(supply / 'status') or 'Unknown'
                data['charging'] = data['battery_status'] == 'Charging'
                try:
                    capacity = int(self.read(supply / 'capacity'))
                    if 0 <= capacity <= 100:
                        data['battery'] = capacity
                except ValueError:
                    pass
            elif self.read(supply / 'online') == '1':
                data['plugged'] = True
        self.data, self.updated = data, now
        return data


class Screen:
    """Manual backlight toggle; retain the user's game-menu brightness on exit."""
    def __init__(self, directory=Path('/sys/class/backlight'), brightness=16):
        self.path = next(iter(sorted(Path(directory).glob('*/brightness'))), None)
        if self.path is None:
            raise OSError('No backlight brightness control found')
        self.original = int(self.path.read_text())
        maximum = int(self.path.with_name('max_brightness').read_text())
        # ponytail: visibility differs per panel; tune R36_MONITOR_BRIGHTNESS if 16 is too dim.
        self.dim = max(1, min(maximum, int(brightness)))
        self.asleep = False
        self.dpms_off = False

    @staticmethod
    def power(mode):
        try:
            subprocess.run(['xset', 'dpms', 'force', mode], check=True, timeout=3,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as error:
            raise OSError('DPMS display power command failed') from error

    def enter(self):
        self.path.write_text(str(self.dim))

    def toggle(self):
        if self.asleep:
            if self.dpms_off:
                self.power('on')
            self.path.write_text(str(self.dim))
            self.dpms_off = self.asleep = False
        else:
            self.path.write_text('0')
            try:
                self.power('off')
                self.dpms_off = True
            except OSError:
                print('DPMS unavailable; screen uses backlight-only sleep.', flush=True)
            self.asleep = True

    def restore(self):
        try:
            if self.dpms_off:
                self.power('on')
        finally:
            self.path.write_text(str(self.original))


class Monitor:
    def __init__(self):
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.version = 0
        self.hosts = {}
        self.selected = None
        self.detail = None
        self.focus = None
        self.panel = 0
        self.scroll = 0
        self.item_page = 0
        self.paused = False
        self.last_page = time.monotonic()
        self.connection = 'Not configured'
        self.bad_messages = 0
        self.device = LocalStatus()
        self.screen = None

    def receive(self, topic, payload, retained=False, now=None):
        now = time.monotonic() if now is None else now
        try:
            if len(payload) > 262144:
                raise ValueError('Oversized payload')
            data = json.loads(payload, parse_constant=lambda _: None)
            if not isinstance(data, dict):
                raise ValueError('Object required')
            host = data.get('host')
            if not isinstance(host, str) or not host.strip() or len(host) > 128:
                raise ValueError('Invalid host')
            # Retained snapshots must not revive machines that stopped publishing.
            stamp = number(data.get('ts'))
            if retained and (stamp is None or time.time() - stamp >= 10):
                return False
            metrics = normalize(data)
            with self.lock:
                self.tick(now)
                if host not in self.hosts and len(self.hosts) >= 128:
                    return False
                entry = self.hosts.setdefault(host, {'history': deque(maxlen=60)})
                entry.update(host=host, seen=now, metrics=metrics)
                entry['history'].append({key: metrics[key] for key in
                                         ('cpu', 'gpu', 'ram', 'rx', 'tx', 'read', 'write', 'cpu_temp', 'gpu_temp', 'swap')})
                entry['history'][-1]['gpus'] = [
                    {'load': number(g.get('usage_percent')), 'temperature': number(g.get('temperature_celsius')),
                     'vram': number(g.get('memory_percent')) if g.get('memory_total_mb') != 0 else None}
                    for g in metrics['gpus']]
                if self.selected is None:
                    self.selected = host
                self.version += 1
                self.changed.notify_all()
            return True
        except (ValueError, TypeError, UnicodeError, OverflowError):
            with self.lock:
                self.bad_messages += 1
            return False

    def tick(self, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            for host in list(self.hosts):
                if now - self.hosts[host]['seen'] >= 10:
                    del self.hosts[host]
            order = list(self.hosts)
            if self.detail not in self.hosts:
                self.detail = None
                self.focus = None
                self.panel = 0
            if self.selected not in self.hosts:
                self.selected = order[0] if order else None
            if not self.paused and order and now - self.last_page >= 15:
                page = order.index(self.selected) // 3
                pages = (len(order) + 2) // 3
                self.selected = order[((page + 1) % pages) * 3]
                self.last_page = now

    def action(self, action, now=None):
        now = time.monotonic() if now is None else now
        with self.lock:
            if action == 'screen':
                if self.screen is not None:
                    try:
                        self.screen.toggle()
                    except OSError as error:
                        print(str(error), flush=True)
                        return  # Keep FN available to retry a failed wake command.
                    self.version += 1
                    self.changed.notify_all()
                return
            if self.screen is not None and self.screen.asleep:
                return
            self.tick(now)
            order = list(self.hosts)
            if action in ('left', 'right') and (self.detail is None or self.focus is not None):
                action = 'previous' if action == 'left' else 'next'
                if self.focus is not None:
                    action = 'metric_' + action
            if action == 'toggle' and self.detail is None:
                self.paused = not self.paused
                self.last_page = now
            elif action == 'back':
                if self.focus is not None:
                    self.focus = None
                else:
                    self.detail = None
                self.scroll = 0
                self.paused = True
            elif order:
                index = order.index(self.selected)
                if action.startswith('focus:') and self.detail is not None and action[6:] in SECTIONS:
                    self.focus = action[6:]
                    self.panel = SECTIONS.index(self.focus)
                    self.item_page = 0
                elif action in ('metric_previous', 'metric_next') and self.focus is not None:
                    self.panel = (self.panel + (1 if action == 'metric_next' else -1)) % len(SECTIONS)
                    self.focus = SECTIONS[self.panel]
                    self.item_page = 0
                elif action in ('previous', 'next') and self.detail is not None:
                    self.selected = order[(index + (1 if action == 'next' else -1)) % len(order)]
                    self.detail = self.selected
                    self.item_page = self.scroll = 0
                elif action in ('previous', 'next'):
                    pages = (len(order) + 2) // 3
                    page = (index // 3 + (1 if action == 'next' else -1)) % pages
                    self.selected = order[page * 3]
                    self.detail = None
                    self.scroll = 0
                elif action in ('up', 'down', 'left', 'right') and self.detail is not None:
                    if self.focus is None:
                        neighbors = {'up': {3: 0, 4: 2, 5: 3, 6: 4},
                                     'down': {0: 3, 1: 3, 2: 4, 3: 5, 4: 6},
                                     'left': {1: 0, 2: 1, 4: 3, 6: 5},
                                     'right': {0: 1, 1: 2, 3: 4, 5: 6}}
                        self.panel = neighbors[action].get(self.panel, self.panel)
                    elif self.focus in ('gpu', 'network', 'disks', 'temperatures'):
                        self.item_page += 1 if action == 'down' else -1
                    else:
                        return
                elif action in ('up', 'down') and self.detail is None:
                    start = index // 3 * 3
                    count = min(3, len(order) - start)
                    self.selected = order[start + (index - start + (1 if action == 'down' else -1)) % count]
                elif action == 'detail':
                    if self.detail is None:
                        self.detail = self.selected
                        self.panel = 0
                    elif self.focus is None:
                        self.focus = SECTIONS[self.panel]
                    self.scroll = 0
                    self.item_page = 0
                else:
                    return
                self.paused = True
            self.version += 1
            self.changed.notify_all()

    def snapshot(self):
        with self.lock:
            self.tick()
            order = list(self.hosts)
            page = order.index(self.selected) // 3 if order else 0
            visible = [self.detail] if self.detail else order[page * 3:page * 3 + 3]
            return {'device': self.device.sample(), 'connection': self.connection, 'paused': self.paused, 'detail': self.detail,
                    'screen_off': bool(self.screen and self.screen.asleep),
                    'focus': self.focus, 'panel': SECTIONS[self.panel], 'item_page': self.item_page,
                    'selected': self.selected, 'page': page + 1, 'pages': max(1, (len(order) + 2) // 3),
                    'count': len(order), 'bad_messages': self.bad_messages,
                    'scroll': self.scroll,
                    'hosts': [{k: (list(v) if self.detail else [{'cpu': sample['cpu'], 'ram': sample['ram']} for sample in v]) if k == 'history' else v for k, v in self.hosts[h].items() if k != 'seen'}
                              for h in visible]}


def mqtt_start(state):
    import paho.mqtt.client as mqtt
    config_path = Path(os.environ.get('MQTT_CONFIG', ROOT / 'mqtt-config.json'))
    if not config_path.exists():
        return None
    config = json.loads(config_path.read_text())
    host, port = config.get('host'), config.get('port', 1883)
    topic = config.get('topic', 'sys/agents/+/metrics')
    if not isinstance(host, str) or not host or not isinstance(port, int) or not 1 <= port <= 65535:
        state.connection = 'Broker address required'
        return None
    if not isinstance(topic, str) or not topic or '\0' in topic:
        raise ValueError('Invalid MQTT topic')
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if config.get('username'):
        client.username_pw_set(config['username'], config.get('password', ''))
    if config.get('tls'):
        client.tls_set()
    def on_connect(client, userdata, flags, reason, properties):
        state.connection = 'Connected' if not reason.is_failure else 'Connection rejected'
        if reason.is_failure:
            client.disconnect()
        if not reason.is_failure:
            result, _ = client.subscribe(topic)
            if result != mqtt.MQTT_ERR_SUCCESS:
                state.connection = 'Subscription failed'
    def on_subscribe(client, userdata, mid, reasons, properties):
        if any(reason.is_failure for reason in reasons):
            state.connection = 'Subscription rejected'
            client.disconnect()
    def on_disconnect(client, userdata, flags, reason, properties):
        if state.connection not in ('Connection rejected', 'Subscription rejected'):
            state.connection = 'Reconnecting'
    client.on_connect, client.on_disconnect, client.on_subscribe = on_connect, on_disconnect, on_subscribe
    client.on_message = lambda client, userdata, msg: state.receive(msg.topic, msg.payload, msg.retain)
    client.on_connect_fail = lambda client, userdata: setattr(state, 'connection', 'Broker unavailable; retrying')
    client.reconnect_delay_set(1, 30)
    state.connection = 'Connecting'
    client.connect_async(host, port, keepalive=30)
    client.loop_start()
    return client


class StickNavigation:
    """Dominant-axis navigation for both sticks, with a dead zone and hold repeat."""
    def __init__(self, limits):
        self.limits = limits
        self.values = {axis: 0.0 for axis in limits}
        self.direction = None
        self.next_repeat = 0.0

    def update(self, axis, value):
        if axis in self.limits:
            low, high = self.limits[axis]
            center = (low + high) / 2
            self.values[axis] = (value - center) / max(1, (high - low) / 2)

    def poll(self, now):
        axis = max(self.values, key=lambda a: abs(self.values[a]), default=None)
        value = self.values.get(axis, 0)
        threshold = .25 if self.direction else .45
        if abs(value) < threshold:
            self.direction = None
            return None
        direction = ('left' if value < 0 else 'right') if axis in (0, 3) else ('up' if value < 0 else 'down')
        if direction != self.direction:
            self.direction = direction
            self.next_repeat = now + .4
            return direction
        if now >= self.next_repeat:
            self.next_repeat = now + .18
            return direction
        return None


def controls(state, server, path='/dev/input/by-path/platform-odroidgo3-joypad-event-joystick',
             buttons=BUTTONS, exit_buttons=(704, 304), hat_axes=()):
    event = struct.Struct('@llHHi')
    pressed = set()
    try:
        with open(path, 'rb', buffering=0) as stream:
            limits, initial = {}, {}
            for axis in (0, 1, 3, 4):
                try:
                    info = bytearray(24)
                    fcntl.ioctl(stream.fileno(), 0x80184540 + axis, info, True)
                    value, low, high, *_ = struct.unpack('6i', info)
                    if high > low:
                        limits[axis], initial[axis] = (low, high), value
                except OSError:
                    pass
            # Own the gamepad while monitoring so FN combinations cannot change global brightness.
            fcntl.ioctl(stream.fileno(), 0x40044590, 1)  # EVIOCGRAB; released when the stream closes.
            stick = StickNavigation(limits)
            for axis, value in initial.items():
                stick.update(axis, value)
            while True:
                ready, _, _ = select.select([stream], [], [], .05)
                if not ready:
                    action = stick.poll(time.monotonic())
                    if action:
                        state.action(action)
                    continue
                raw = stream.read(event.size)
                if len(raw) != event.size:
                    return
                _, _, kind, code, value = event.unpack(raw)
                if kind == 3:
                    if code in hat_axes:
                        if value:
                            state.action(('left' if value < 0 else 'right') if code == 16
                                         else ('up' if value < 0 else 'down'))
                        continue
                    stick.update(code, value)
                    continue
                if kind == 0 and code == 0:
                    action = stick.poll(time.monotonic())
                    if action:
                        state.action(action)
                    continue
                if kind != 1:
                    continue
                if value:
                    pressed.add(code)
                else:
                    pressed.discard(code)
                if set(exit_buttons) <= pressed:
                    server.shutdown()
                    return
                if value == 1 and code in buttons:
                    state.action(buttons[code])
    except OSError as error:
        print(f'Gamepad unavailable: {error}', flush=True)


def handler(state):
    class Handler(BaseHTTPRequestHandler):
        def respond(self, content, content_type):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            try:
                self.wfile.write(content)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_GET(self):
            if self.path == '/':
                self.respond((ROOT / 'monitor.html').read_bytes(), 'text/html; charset=utf-8')
            elif self.path == '/assets/hardware-buddy.svg':
                self.respond((ROOT / 'assets/hardware-buddy.svg').read_bytes(), 'image/svg+xml')
            elif self.path == '/events':
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                try:
                    while True:
                        with state.changed:
                            version = state.version
                            content = json.dumps(state.snapshot(), allow_nan=False)
                        self.wfile.write(('data: ' + content + '\n\n').encode())
                        self.wfile.flush()
                        with state.changed:
                            state.changed.wait_for(lambda: state.version != version, timeout=1)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            elif self.path == '/status':
                self.respond(json.dumps(state.snapshot(), allow_nan=False).encode(), 'application/json')
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != '/control':
                self.send_error(404)
                return
            if self.headers.get('Host') not in ('127.0.0.1:8766', 'localhost:8766') or self.headers.get('Origin', 'http://127.0.0.1:8766') not in ('http://127.0.0.1:8766', 'http://localhost:8766'):
                self.send_error(403)
                return
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 128:
                    raise ValueError('Invalid body size')
                self.connection.settimeout(3)
                action = json.loads(self.rfile.read(size)).get('action')
                if action not in set(BUTTONS.values()) | {'focus:' + key for key in SECTIONS}:
                    raise ValueError('Invalid action')
                state.action(action)
                self.respond(b'{}', 'application/json')
            except (ValueError, TypeError, AttributeError, OSError):
                self.send_error(400)

        def log_message(self, *_):
            pass
    return Handler


if __name__ == '__main__':
    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    state = Monitor()
    state.screen = Screen(brightness=os.environ.get('R36_MONITOR_BRIGHTNESS', '16'))
    client = None
    try:
        state.screen.enter()
        client = mqtt_start(state)
        with ThreadingHTTPServer(('127.0.0.1', 8766), handler(state)) as server:
            threading.Thread(target=controls, args=(state, server), daemon=True).start()
            server.serve_forever()
    finally:
        state.screen.restore()
        if client:
            client.disconnect()
            client.loop_stop()
