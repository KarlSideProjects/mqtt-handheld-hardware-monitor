"""Run: python3 browser/test_install.py (no device or MQTT broker required)."""
import json
import os
from pathlib import Path
import socket
import struct
import tempfile
import threading
from unittest.mock import MagicMock, Mock, patch

import monitor
import mqtt_setup
import trimui_monitor
from trimui_monitor import Backlight, BUTTONS, TrimUIStatus, gamepad


def handshake(connack=0, suback=0, config=None):
    config = config or {'host': '127.0.0.1', 'username': 'default-user', 'password': 'default-secret'}
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        listener.listen()
        config = dict(config, port=listener.getsockname()[1])
        packets = []
        def broker():
            with listener.accept()[0] as stream:
                stream.settimeout(2)
                packets.append(mqtt_setup.receive(stream))
                mqtt_setup.send(stream, 0x20, bytes([0, connack]))
                if not connack:
                    packets.append(mqtt_setup.receive(stream))
                    mqtt_setup.send(stream, 0x90, bytes([0, 1, suback]))
                    if suback != 128:
                        packets.append(mqtt_setup.receive(stream))
        worker = threading.Thread(target=broker)
        worker.start()
        try:
            mqtt_setup.probe(config)
        finally:
            worker.join(timeout=3)
            assert not worker.is_alive()
        return packets


packets = handshake()
assert packets[0][0] == 0x10 and packets[0][1][7] == 0xc2
assert mqtt_setup.string('default-secret') in packets[0][1]
assert packets[1] == (0x82, b'\0\1' + mqtt_setup.string('sys/agents/+/metrics') + b'\0')
assert packets[2] == (0xe0, b'')
assert handshake(config={'host': '127.0.0.1'})[0][1][7] == 2
for options in ({'connack': 4}, {'connack': 5}, {'suback': 128}):
    try:
        handshake(**options)
    except mqtt_setup.Rejected:
        pass
    else:
        raise AssertionError('Rejected MQTT login/subscription accepted')
config = {'host': 'broker', 'username': 'default-user', 'password': 'default-secret'}
with patch('mqtt_setup.probe', side_effect=[mqtt_setup.Rejected('Rejected'), None]) as probe, \
        patch('builtins.input', return_value='manual-user'), \
        patch('mqtt_setup.getpass.getpass', return_value='manual-secret'):
    assert mqtt_setup.setup(config, True)['password'] == 'manual-secret'
    assert probe.call_count == 2
with patch('mqtt_setup.probe', side_effect=OSError('offline')), \
        patch('builtins.input', return_value='n'), patch('mqtt_setup.getpass.getpass') as password:
    try:
        mqtt_setup.setup(config, True)
    except ValueError:
        pass
    else:
        raise AssertionError('Offline broker accepted')
    password.assert_not_called()
with tempfile.TemporaryDirectory() as temp:
    output = Path(temp) / 'config.json'
    with patch('sys.argv', ['mqtt_setup.py', '--output', str(output)]), \
            patch('mqtt_setup.setup', return_value=config):
        mqtt_setup.main()
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())['username'] == 'manual-user'
print('PASS: MQTT CONNECT/SUBACK, default/anonymous login, hidden credential fallback, network failures, private config')

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    event = root / 'event9/device'
    event.mkdir(parents=True)
    (event / 'name').write_text('TRIMUI Player1\n')
    assert gamepad(root) == '/dev/input/event9'
    panel = root / 'panel'
    panel.mkdir()
    (panel / 'brightness').write_text('180')
    (panel / 'max_brightness').write_text('255')
    screen = Backlight(root, 16)
    with patch('monitor.subprocess.run') as power:
        screen.enter(); screen.toggle()
        assert screen.asleep and (panel / 'brightness').read_text() == '0'
        screen.toggle(); screen.restore()
        assert not screen.asleep and (panel / 'brightness').read_text() == '180'
        power.assert_not_called()
    thermal = root / 'thermal/thermal_zone0'
    thermal.mkdir(parents=True)
    (thermal / 'type').write_text('cpul_thermal_zone')
    (thermal / 'temp').write_text('44500')
    status = TrimUIStatus(proc=root/'proc', supplies=root/'supplies', thermal=thermal.parent)
    assert status.sample()['temperature'] == 44.5
    assert status.sample()['name'] == 'TrimUI'
    stream_path = root / 'input'
    events = [(3,16,-1), (3,16,0), (3,17,1), (1,305,1), (1,304,1),
              (1,308,1), (1,314,1), (1,315,1)]
    stream_path.write_bytes(b''.join(struct.pack('@llHHi',0,0,*e) for e in events))
    state, server = Mock(), Mock()
    def ioctl(fd, code, *args):
        if code != 0x40044590:
            raise OSError('No analog axes in fixture')
        return 0
    with patch('monitor.fcntl.ioctl', side_effect=ioctl), \
            patch('monitor.select.select', side_effect=lambda readers,*_: (readers,[],[])):
        monitor.controls(state, server, stream_path, BUTTONS, (314,315), (16,17))
    assert [call.args[0] for call in state.action.call_args_list] == ['left','down','detail','back','screen']
    server.shutdown.assert_called_once()
print('PASS: TrimUI sensor names, dynamic gamepad, hat navigation, buttons, exit combo, backlight restoration without X11')

# Exercise the launcher call and cleanup on both successful and failed browser exits.
for code in (0, 1):
    state, client = Mock(), Mock()
    browser = Mock()
    browser.wait.return_value = code
    browser.poll.return_value = code
    http = MagicMock()
    with patch.dict(os.environ, {'TRIMUI_BROWSER': '/runtime/bin/chromium'}), \
            patch('trimui_monitor.signal.signal'), \
            patch('trimui_monitor.gamepad', return_value='/dev/input/event4'), \
            patch('trimui_monitor.monitor.Monitor', return_value=state), \
            patch('trimui_monitor.Backlight', return_value=Mock()) as screen, \
            patch('trimui_monitor.monitor.mqtt_start', return_value=client), \
            patch('trimui_monitor.ThreadingHTTPServer', return_value=http), \
            patch('trimui_monitor.threading.Thread'), \
            patch('trimui_monitor.subprocess.Popen', return_value=browser) as launch:
        try:
            trimui_monitor.main()
        except RuntimeError:
            assert code == 1
        else:
            assert code == 0
        launch.assert_called_once_with(['/runtime/bin/chromium', 'http://127.0.0.1:8766/'])
        screen.return_value.restore.assert_called_once()
        http.__enter__.return_value.shutdown.assert_called_once()
        client.disconnect.assert_called_once()
        client.loop_stop.assert_called_once()
print('PASS: Chromium launcher arguments and HTTP/MQTT/backlight cleanup on normal and failed exits')

# Drive the real Bash SSH wrapper with a fake ssh executable and a terminal.
import pty
import select
import subprocess
import sys
import time

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    fake = root / 'ssh'
    fake.write_text('''#!''' + sys.executable + '''
import os, subprocess, sys
args=sys.argv[1:]
secret=subprocess.check_output([os.environ['SSH_ASKPASS']],text=True).rstrip('\\n')
command=args[-1]
if command == 'true':
    expected='manual-test-password' if os.environ.get('REQUIRE_MANUAL') else os.environ['EXPECTED_FACTORY']
    if secret != expected:
        print('Permission denied (password).', file=sys.stderr)
        sys.exit(255)
elif 'mktemp -d' in command:
    print(os.environ['MOCK_STAGE'])
elif 'tar -xf' in command or 'cat >' in command:
    sys.stdin.buffer.read()
elif command.startswith('bash '):
    with open(os.environ['MOCK_COMMAND_LOG'],'a') as log:
        log.write(command+'\\n')
''')
    fake.chmod(0o755)
    for script, factory, stage in [('install.sh','ark','/home/ark/hwmonitor-install.test123'),
                                    ('install-trimui.sh','tina','/mnt/UDISK/hwmonitor-install.test123')]:
        env = dict(os.environ, PATH=str(root)+os.pathsep+os.environ['PATH'],
                   EXPECTED_FACTORY=factory, MOCK_STAGE=stage, MOCK_COMMAND_LOG=str(root/'commands'))
        env.pop('HWMONITOR_SSH_PASSWORD', None)
        command = ['bash',str(Path(__file__).parent/script),'--ssh','device.test','--check']
        completed = subprocess.run(command, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        assert completed.returncode == 0, completed.stderr
        assert '--check' in (root/'commands').read_text().splitlines()[-1]
        deps = subprocess.run(command[:-1]+['--deps-only'], env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)
        assert deps.returncode == 0, deps.stderr
        assert '--deps-only' in (root/'commands').read_text().splitlines()[-1]
        master, slave = pty.openpty()
        process = subprocess.Popen(command, env=dict(env,REQUIRE_MANUAL='1'), stdin=slave, stdout=slave, stderr=slave)
        os.close(slave)
        output = b''
        sent_user = sent_password = False
        deadline = time.monotonic()+10
        try:
            while process.poll() is None and time.monotonic() < deadline:
                if not select.select([master],[],[],.1)[0]:
                    continue
                try:
                    output += os.read(master,65536)
                except OSError:
                    break
                if b'SSH username [' in output and not sent_user:
                    os.write(master,b'operator\n');sent_user=True
                if b'SSH password: ' in output and not sent_password:
                    os.write(master,b'manual-test-password\n');sent_password=True
            assert process.wait(timeout=3) == 0, output.decode()
            assert sent_user and sent_password
            assert b'manual-test-password' not in output
        finally:
            if process.poll() is None:
                process.kill();process.wait()
            os.close(master)
print('PASS: both SH entry points try factory SSH login, prompt after rejection, hide password, and complete remote staging')

# A corrupt bootstrap must be rejected even when the transport itself succeeds.
import hashlib
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'base.tar.gz'
    source.write_bytes(b'fixture archive bytes')
    output = root / 'download.tar.gz'
    helper = str(Path(__file__).with_name('install-trimui-deps.sh').resolve())
    shell = 'source "$1"; base_url="file://$2"; base_sha=$3; fetch_base "$4"'
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    for expected, success in ((digest, True), ('0'*64, False)):
        result = subprocess.run(['bash','-c',shell,'bash',helper,str(source),expected,str(output)],capture_output=True,text=True)
        assert (result.returncode == 0) == success
print('PASS: dependency bootstrap accepts the pinned digest and rejects corrupted downloads')
