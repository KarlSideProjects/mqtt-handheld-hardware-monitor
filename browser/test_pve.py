"""Run: python3 browser/test_pve.py."""
import json
import time
from pathlib import Path

from monitor import Monitor

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/virtualization-v1.fixture.json').read_text())
now = time.monotonic()
message = dict(FIXTURE, ts=time.time(), virtualization=dict(FIXTURE['virtualization'], observed_at=time.time()))
message['virtualization']['guests'] += [
    dict(message['virtualization']['guests'][0], id=f'lab:qemu:{vmid}', vmid=vmid, name=f'vm-{vmid}')
    for vmid in (102, 103, 104)]
state = Monitor()
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
snapshot = state.snapshot()
assert snapshot['count'] == 1 and snapshot['hosts'][0]['host'] == 'pve-node-a'
assert snapshot['hosts'][0]['virtualization']['guests'][0]['id'] == 'lab:qemu:100'
state.action('detail', now)
assert state.snapshot()['detail'] == 'pve-node-a'
state.action('detail', now)
assert state.snapshot()['focus'] == 'cpu'
state.action('back', now)
state.action('right', now)
state.action('detail', now)
assert state.snapshot()['focus'] == 'gpu'
state.action('back', now)
state.action('left', now)
for direction in ('right', 'right', 'down', 'down', 'right'):
    state.action(direction, now)
assert state.snapshot()['panel'] == 'pve'
state.action('detail', now)
assert state.snapshot()['pve_view'] == 'guests'
assert state.snapshot()['hosts'][0]['virtualization']['guest_count'] == 5
state.action('down', now)
assert state.snapshot()['pve_selected'] == 1
state.action('next', now)
assert state.snapshot()['pve_page'] == 1
state.action('previous', now)
assert state.snapshot()['pve_page'] == 0
state.action('back', now)
assert state.snapshot()['pve_view'] is None and state.snapshot()['detail'] == 'pve-node-a'

# Switching from the PVE host to an ordinary host clears the PVE-only card index.
mixed = Monitor()
assert mixed.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
assert mixed.receive('sys/agents/ordinary/metrics', json.dumps({'host': 'ordinary', 'ts': time.time()}), now=now)
mixed.action('detail', now)
for direction in ('right', 'right', 'down', 'down', 'right'):
    mixed.action(direction, now)
assert mixed.snapshot()['panel'] == 'pve'
mixed.action('next', now)
mixed_view = mixed.snapshot()
assert mixed_view['detail'] == 'ordinary' and mixed_view['panel'] == 'cpu'
assert mixed_view['focus'] is None and mixed_view['pve_view'] is None

# The transport's 256 KiB payload bound, rather than an arbitrary guest cap, limits inventories.
large = json.loads(json.dumps(message))
large['virtualization']['guests'] = [
    dict(large['virtualization']['guests'][0], id=f'lab:qemu:{vmid}', vmid=vmid, name=f'guest-{vmid}')
    for vmid in range(1000, 1513)]
large_payload = json.dumps(large)
assert len(large_payload) <= 262144
large_receiver = Monitor()
assert large_receiver.receive('sys/agents/pve-node-a/metrics', large_payload, now=now)
assert large_receiver.snapshot()['hosts'][0]['virtualization']['guest_count'] == 513

# Invalid complete inventories cannot erase a previously accepted list.
broken = json.loads(json.dumps(message))
broken['virtualization']['guests'][1]['id'] = 'wrong:id'
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(broken), now=now + 1)
assert len(state.snapshot()['hosts'][0]['virtualization']['guests']) == 5

# The first unconfigured envelope has no identity or inventory; null optional API values stay unknown.
unknown = json.loads(json.dumps(message))
unknown['virtualization']['guests'][0]['uptime'] = None
unknown['virtualization']['guests'][0]['vcpus'] = None
unknown['virtualization']['guests'][1].pop('uptime')
unknown['virtualization']['guests'][1].pop('vcpus')
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(unknown), now=now + 2)
assert state.snapshot()['hosts'][0]['virtualization']['guests'][0]['vcpus'] is None
unconfigured = dict(version=1, provider='pve', cluster_id=None, node=None, observed_at=None, status='unconfigured')
first_config = Monitor()
assert first_config.receive('sys/agents/unconfigured/metrics', json.dumps(dict(host='unconfigured', ts=time.time(), virtualization=unconfigured)), now=now)
assert first_config.snapshot()['hosts'][0]['virtualization']['guest_count'] is None
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(dict(message, virtualization=unconfigured)), now=now + 3)
assert state.snapshot()['hosts'][0]['virtualization']['status'] == 'unconfigured'
assert len(state.snapshot()['hosts'][0]['virtualization']['guests']) == 5
failed = dict(version=1, provider='pve', cluster_id='lab', node='pve-node-a', observed_at=None, status='error', error='api_unavailable')
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(dict(message, virtualization=failed)), now=now + 4)
assert state.snapshot()['hosts'][0]['virtualization']['status'] == 'error'
assert len(state.snapshot()['hosts'][0]['virtualization']['guests']) == 5

# Adversarial nested data is rejected without raising through Monitor.receive or clearing state.
malformed = json.loads(json.dumps(message))
malformed['virtualization']['guests'][0]['network_io']['total'] = []
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(malformed), now=now + 4)
assert len(state.snapshot()['hosts'][0]['virtualization']['guests']) == 5
huge_number = json.loads(json.dumps(message))
huge_number['virtualization']['guests'][0]['memory']['ram']['used'] = 10**1000
bad_before_huge = state.snapshot()['bad_messages']
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(huge_number), now=now + 4)
assert state.snapshot()['bad_messages'] == bad_before_huge + 1
assert len(state.snapshot()['hosts'][0]['virtualization']['guests']) == 5
wrong_version = json.loads(json.dumps(message))
wrong_version['virtualization']['version'] = True
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(wrong_version), now=now + 5)
assert len(state.snapshot()['hosts'][0]['virtualization']['guests']) == 5
old = json.loads(json.dumps(message))
old['virtualization']['observed_at'] = time.time() - 31
aged = Monitor()
assert aged.receive('sys/agents/pve-node-a/metrics', json.dumps(old), now=now)
assert not aged.snapshot()['hosts'][0]['virtualization']['fresh']

# Host-only payloads remain valid and missing initial inventory stays unknown.
legacy = Monitor()
assert legacy.receive('sys/agents/legacy/metrics', json.dumps({'host': 'legacy', 'ts': time.time()}), now=now)
assert legacy.snapshot()['hosts'][0].get('virtualization') is None
print('PASS: PVE receive, nested inventory, navigation, atomic invalid snapshot, legacy host')
