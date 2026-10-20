"""Run: python3 browser/test_monitor.py."""
import json
import time
from monitor import Monitor, normalize

# Exact-second fixtures keep the 10-second expiry boundary independent of float rounding.
now = float(int(time.monotonic()))
payload = {'cpu': {'percent_total': 42, 'percent_per_core': [25, 59]},
           'memory': {'ram': {'percent': 63, 'used': 8 * 2**30, 'total': 16 * 2**30}},
           'gpus': [{'usage_percent': 37, 'temperature_celsius': 62}],
           'temperatures': {'coretemp': [{'current': 55}]},
           'network_io': {'total': {'rate': {'rx_bytes_per_s': 1000, 'tx_bytes_per_s': 500}}},
           'disk_io': {'sda': {'rate': {'read_bytes_per_s': 2000, 'write_bytes_per_s': 750}}}}

def publish(state, host, timestamp):
    return state.receive(f'sys/agents/{host}/metrics', json.dumps(dict(payload, host=host)), now=timestamp)

state = Monitor()
for i in range(7):
    assert publish(state, f'host-{i}', now)
assert state.snapshot()['count'] == 7
assert len(state.snapshot()['hosts']) == 3
state.action('next', now)
assert state.selected == 'host-3' and state.paused
state.action('down', now)
state.action('detail', now)
assert state.detail == 'host-4'
state.action('down', now)
assert state.scroll == 0 and state.detail == 'host-4'
state.action('back', now)
assert state.detail is None and state.paused
state.action('next', now)
assert state.selected == 'host-6' and len(state.snapshot()['hosts']) == 1
# Fresh messages do not resume a manual pause, even beyond the auto interval.
for i in range(7):
    publish(state, f'host-{i}', now + 8)
state.tick(now + 16)
assert state.selected == 'host-6' and state.paused
state.action('toggle', now + 16)
for i in range(7):
    publish(state, f'host-{i}', now + 16)
for i in range(7):
    publish(state, f'host-{i}', now + 24)
for i in range(7):
    publish(state, f'host-{i}', now + 30)
state.tick(now + 31)
assert state.selected == 'host-0' and not state.paused
state.action('detail', now + 31)
publish(state, 'host-1', now + 39)
state.tick(now + 40)
assert state.detail is None and state.selected == 'host-1' and state.paused
state.tick(now + 49)
assert not state.hosts and state.selected is None
assert not state.receive('topic', b'[]', now=now)
assert not state.receive('topic', b'{bad', now=now)
assert not state.receive('topic', b'{"host":null}', now=now)
assert not state.receive('topic', json.dumps(dict(payload, host='stale', ts=time.time()-60)), retained=True)
assert normalize(payload)['cpu_temp'] == 55
assert normalize(payload)['gpu'] == 37
assert normalize(payload)['read'] == 2000
assert normalize({'gpu': None, 'cpu': []})['cpu'] is None
# Raw host names remain data; the web page escapes text before inserting HTML.
assert publish(state, '<script>bad</script>', now)
json.dumps(state.snapshot(), allow_nan=False)
print('PASS: 7-host pagination, pause/resume, auto rotation, detail/offline, payload validation')

# Three-level navigation, direct clicks, card switching, and offline fallback.
state = Monitor()
publish(state, 'drilldown', time.monotonic())
state.action('detail')
assert state.snapshot()['panel'] == 'cpu' and state.focus is None
state.action('detail')
assert state.focus == 'cpu'
state.action('right')
assert state.focus == 'gpu'
state.action('back')
assert state.detail == 'drilldown' and state.focus is None
state.action('right')
assert state.snapshot()['panel'] == 'memory' and state.scroll == 0
state.action('detail')
assert state.focus == 'memory'
state.action('back')
state.action('focus:network')
assert state.focus == 'network'
state.tick(time.monotonic() + 10)
assert state.detail is None and state.focus is None
print('PASS: overview/device/metric navigation, click actions, metric switching, offline fallback')

# Both analog sticks: center noise, dominant axis, all directions and held repeat.
from monitor import StickNavigation
stick = StickNavigation({axis: (-1800, 1800) for axis in (0, 1, 3, 4)})
stick.update(0, 20)
assert stick.poll(0) is None
stick.update(0, 1500)
assert stick.poll(1) == 'right'
assert stick.poll(1.2) is None
assert stick.poll(1.41) == 'right'
stick.update(0, 0)
assert stick.poll(1.5) is None
for axis, value, expected in [(0,-1500,'left'),(1,-1500,'up'),(1,1500,'down'),(3,1500,'right'),(4,-1500,'up')]:
    stick.update(axis,value)
    assert stick.poll(2) == expected
    stick.update(axis,0)
    assert stick.poll(2.1) is None
stick.update(0,1000);stick.update(1,-1500)
assert stick.poll(3) == 'up'
state = Monitor();publish(state,'navigation',time.monotonic());state.action('detail')
for direction, panel in [('right','gpu'),('right','memory'),('down','disks'),('left','network'),('down','temperatures'),('right','history'),('up','disks'),('up','memory')]:
    state.action(direction)
    assert state.snapshot()['panel'] == panel
print('PASS: both sticks, dead zone, dominant direction, repeat, spatial card navigation')

# Local device readings do not depend on any monitored MQTT host.
from pathlib import Path
from tempfile import TemporaryDirectory
from monitor import LocalStatus
with TemporaryDirectory() as directory:
    root = Path(directory)
    proc, supplies, thermal = root/'proc', root/'power', root/'thermal'
    for path in (proc, supplies/'battery', supplies/'ac', thermal/'thermal_zone0'):
        path.mkdir(parents=True)
    (proc/'stat').write_text('cpu 100 0 0 200 0 0 0 0 0 0\n')
    (proc/'meminfo').write_text('MemTotal: 1000 kB\nMemAvailable: 750 kB\n')
    (thermal/'thermal_zone0'/'type').write_text('soc-thermal')
    (thermal/'thermal_zone0'/'temp').write_text('55000')
    (supplies/'battery'/'type').write_text('Battery')
    (supplies/'battery'/'capacity').write_text('42')
    (supplies/'battery'/'status').write_text('Charging')
    (supplies/'ac'/'type').write_text('Mains')
    (supplies/'ac'/'online').write_text('1')
    device = LocalStatus(proc, supplies, thermal)
    first=device.sample(0)
    assert first['cpu'] is None and first['memory']==25 and first['temperature']==55
    assert first['battery']==42 and first['charging'] and first['plugged']
    (proc/'stat').write_text('cpu 150 0 0 250 0 0 0 0 0 0\n')
    assert device.sample(1) is first
    assert device.sample(2)['cpu']==50
    (supplies/'battery'/'capacity').write_text('100')
    (supplies/'battery'/'status').write_text('Full')
    full=device.sample(4)
    assert full['battery']==100 and not full['charging'] and full['plugged']
    (supplies/'ac'/'online').write_text('0')
    (supplies/'battery'/'status').write_text('Discharging')
    assert not device.sample(6)['plugged']
    unknown=LocalStatus(root/'missing',root/'missing',root/'missing').sample(0)
    assert all(unknown[key] is None for key in ('cpu','memory','temperature','battery'))
print('PASS: handheld CPU delta, cached reads, memory, temperature, battery/charging/full/unplugged/unknown')

state.action('focus:gpu')
state.action('down')
assert state.snapshot()['item_page'] == 1
state.action('up');state.action('up')
assert state.snapshot()['item_page'] == -1 and state.scroll == 0
state.action('right')
assert state.snapshot()['item_page'] == 0 and state.focus == 'memory'
state.action('down')
assert state.snapshot()['item_page'] == 0
print('PASS: metric item paging, reverse paging, reset when changing metric, no scrolling')

# The display goes completely dark only on request, then restores the dim level.
from monitor import Screen, BUTTONS
from unittest.mock import patch
with TemporaryDirectory() as directory, patch('monitor.subprocess.run') as dpms:
    panel=Path(directory)/'panel';panel.mkdir()
    (panel/'brightness').write_text('200');(panel/'max_brightness').write_text('255')
    screen=Screen(directory,16);screen.enter()
    assert (panel/'brightness').read_text()=='16'
    state=Monitor();state.screen=screen
    assert BUTTONS[708]=='screen' and 307 not in BUTTONS
    state.action('screen')
    assert state.snapshot()['screen_off'] and (panel/'brightness').read_text()=='0'
    version=state.version;state.action('down');assert state.version==version
    state.action('screen')
    assert not state.snapshot()['screen_off'] and (panel/'brightness').read_text()=='16'
    assert [call.args[0][-1] for call in dpms.call_args_list]==['off','on']
    state.action('screen');dpms.side_effect=OSError('display unavailable')
    state.action('screen');assert screen.asleep  # A failed wake stays retryable.
    dpms.side_effect=None;state.action('screen');assert not screen.asleep
    dpms.side_effect=OSError('DPMS unsupported');state.action('screen')
    assert screen.asleep and not screen.dpms_off
    state.action('screen');assert not screen.asleep
    dpms.side_effect=None
    state.action('screen');screen.restore()
    assert dpms.call_args.args[0][-1]=='on' and (panel/'brightness').read_text()=='200'
    (panel/'brightness').write_text('0');dpms.side_effect=OSError('X already closed')
    try:screen.restore()
    except OSError:pass
    else:raise AssertionError('Expected DPMS error')
    assert (panel/'brightness').read_text()=='200'
    dpms.side_effect=None
    assert Screen(directory,0).dim==1 and Screen(directory,999).dim==255
print('PASS: FN sleep/wake, nonzero dim brightness, sleeping input ignored, exit brightness restored')

# Shoulder buttons cycle devices without leaving either detail level.
state=Monitor()
for i in range(7):publish(state,f'device-{i}',time.monotonic())
state.action('detail')
for i in range(1,8):
    state.action('next')
    assert state.detail==state.selected==f'device-{i%7}' and state.focus is None and state.paused
state.action('previous');assert state.detail=='device-6'
state.action('focus:gpu');state.action('down');state.action('next')
assert state.detail=='device-0' and state.focus=='gpu' and state.item_page==0
state.action('right');assert state.focus=='memory' and state.detail=='device-0'
state.action('previous');assert state.detail=='device-6' and state.focus=='memory'
state.hosts.pop('device-0');state.action('next');assert state.detail=='device-1'
state.action('back');assert state.detail=='device-1' and state.focus is None
state.action('back');assert state.detail is None
single=Monitor();publish(single,'only',time.monotonic());single.action('detail')
for button in ('next','previous'):
    single.action(button);assert single.detail=='only'
print('PASS: L1/R1 detail device cycling, wrap, metric retained, item reset, removed host, B back, single host')
