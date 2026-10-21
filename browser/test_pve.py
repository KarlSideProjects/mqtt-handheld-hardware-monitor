"""Run: python3 browser/test_pve.py."""
import json
import time
from pathlib import Path

from monitor import Monitor

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/virtualization-v1.fixture.json').read_text())
# Exact-second fixtures keep the 10-second expiry boundary independent of float rounding.
now = float(int(time.monotonic()))
message = dict(FIXTURE, ts=time.time(), virtualization=dict(FIXTURE['virtualization'], observed_at=time.time()))
message['virtualization']['guests'] += [
    dict(message['virtualization']['guests'][0], id=f'lab:qemu:{vmid}', vmid=vmid, name=f'vm-{vmid}')
    for vmid in (102, 103, 104)]
state = Monitor()
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
snapshot = state.snapshot()
assert snapshot['count'] == 1 and snapshot['hosts'][0]['host'] == 'pve-node-a'
assert snapshot['hosts'][0]['virtualization']['guests'][0]['id'] == 'lab:qemu:100'
assert snapshot['hosts'][0]['virtualization']['guests'][1]['status'] == 'stopped'
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
state.action('rotate_right', now)
assert state.snapshot()['rotation'] == 90 and state.pve_view == 'guests'
assert state.snapshot()['hosts'][0]['virtualization']['guest_count'] == 5
state.action('down', now)
assert state.snapshot()['pve_selected'] == 1
state.action('detail', now)
assert state.snapshot()['pve_view'] == 'guest'
state.action('rotate_left', now)
assert state.snapshot()['rotation'] == 0 and state.pve_view == 'guest'
assert state.snapshot()['pve_guest_id'] == 'lab:lxc:101'
state.action('next', now)
assert state.snapshot()['pve_guest_id'] == 'lab:qemu:102'
state.action('back', now)
assert state.snapshot()['pve_view'] == 'guests' and state.snapshot()['pve_selected'] == 2
state.action('next', now)
assert state.snapshot()['pve_page'] == 1
state.action('previous', now)
assert state.snapshot()['pve_page'] == 0
state.action('right', now)
assert state.snapshot()['pve_page'] == 1
state.action('left', now)
assert state.snapshot()['pve_page'] == 0
assert state.snapshot()['pve_selected'] == 0
state.action('back', now)
assert state.snapshot()['pve_view'] is None and state.snapshot()['detail'] == 'pve-node-a'

# Public A/B navigation and lifecycle recovery keep the selected guest in its parent context.
life = Monitor()
assert life.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
life.action('detail', now)  # overview -> host detail
for direction in ('right', 'right', 'down', 'down', 'right'):
    life.action(direction, now)
life.action('detail', now)  # host detail -> guest list
life.action('detail', now)  # selected guest -> guest detail
assert life.snapshot()['pve_view'] == 'guest' and life.snapshot()['pve_guest_id'] == 'lab:qemu:100'
deleted = json.loads(json.dumps(message))
deleted['virtualization']['observed_at'] += 1
deleted['virtualization']['guests'] = [g for g in deleted['virtualization']['guests'] if g['id'] != 'lab:qemu:100']
assert life.receive('sys/agents/pve-node-a/metrics', json.dumps(deleted), now=now + 1)
assert life.snapshot()['pve_view'] == 'guests'
assert life.snapshot()['pve_guest_id'] in {g['id'] for g in life.snapshot()['hosts'][0]['virtualization']['guests']}
life.action('detail', now + 1)
assert life.snapshot()['pve_view'] == 'guest'
life.action('back', now + 11)
assert life.snapshot()['detail'] is None and life.snapshot()['pve_view'] is None

# Only a newly observed successful inventory adds guest trend samples.
sample_state = Monitor()
assert sample_state.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
initial_guest = sample_state.snapshot()['hosts'][0]['virtualization']['guests'][0]
assert len(initial_guest['history']) == 1
assert sample_state.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now + 1)
assert len(sample_state.snapshot()['hosts'][0]['virtualization']['guests'][0]['history']) == 1
newer = json.loads(json.dumps(message))
newer['virtualization']['observed_at'] += 1
newer['virtualization']['guests'][0]['cpu']['percent_total'] = 40
assert sample_state.receive('sys/agents/pve-node-a/metrics', json.dumps(newer), now=now + 2)
trend = sample_state.snapshot()['hosts'][0]['virtualization']['guests'][0]['history']
assert len(trend) == 2 and trend[-1]['cpu'] == 40

for initial_status in ('unconfigured', 'error'):
    pending = Monitor()
    pending_envelope = dict(version=1, provider='pve', cluster_id=None if initial_status == 'unconfigured' else 'lab',
                            node=None if initial_status == 'unconfigured' else 'pve-node-a',
                            observed_at=None, status=initial_status)
    assert pending.receive('sys/agents/pve-node-a/metrics', json.dumps(dict(host='pve-node-a', ts=time.time(),
                                                                          virtualization=pending_envelope)), now=now)
    assert pending.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now + 1)
    assert len(pending.snapshot()['hosts'][0]['virtualization']['guests'][0]['history']) == 1

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
unknown['virtualization']['guests'][1]['status'] = 'unknown'
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(unknown), now=now + 2)
assert state.snapshot()['hosts'][0]['virtualization']['guests'][0]['vcpus'] is None
assert state.snapshot()['hosts'][0]['virtualization']['guests'][1]['status'] == 'unknown'
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

# API errors and host heartbeats cannot turn an old observation into fresh inventory.
cached = Monitor()
old_observation = json.loads(json.dumps(message))
old_observation['virtualization']['observed_at'] = time.time() - 31
assert cached.receive('sys/agents/pve-node-a/metrics', json.dumps(old_observation), now=now)
assert cached.receive('sys/agents/pve-node-a/metrics', json.dumps(dict(old_observation, ts=time.time())), now=now + 1)
cached_view = cached.snapshot()['hosts'][0]['virtualization']
assert not cached_view['fresh'] and cached_view['status'] == 'ok'
assert cached.receive('sys/agents/pve-node-a/metrics', json.dumps(dict(old_observation, virtualization=failed)), now=now + 2)
cached_view = cached.snapshot()['hosts'][0]['virtualization']
assert not cached_view['fresh'] and cached_view['status'] == 'error'
recovered = json.loads(json.dumps(message))
recovered['virtualization']['observed_at'] = time.time()
recovered['virtualization']['guests'] = recovered['virtualization']['guests'][:1]
assert cached.receive('sys/agents/pve-node-a/metrics', json.dumps(recovered), now=now + 3)
cached_view = cached.snapshot()['hosts'][0]['virtualization']
assert cached_view['fresh'] and cached_view['status'] == 'ok' and cached_view['guest_count'] == 1

# A delayed complete inventory cannot restore a guest removed by a newer observation.
ordered = Monitor()
newer = json.loads(json.dumps(message))
newer['virtualization']['observed_at'] = time.time()
newer['virtualization']['guests'] = newer['virtualization']['guests'][:1]
older = json.loads(json.dumps(message))
older['virtualization']['observed_at'] = newer['virtualization']['observed_at'] - 10
assert ordered.receive('sys/agents/pve-node-a/metrics', json.dumps(newer), now=now)
assert ordered.receive('sys/agents/pve-node-a/metrics', json.dumps(older), now=now + 1)
ordered_view = ordered.snapshot()['hosts'][0]['virtualization']
assert ordered_view['guest_count'] == 1 and ordered_view['observed_at'] == newer['virtualization']['observed_at']

# Losing the parent host closes the PVE route and returns to the overview.
offline = Monitor()
assert offline.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
offline.action('detail', now)
for direction in ('right', 'right', 'down', 'down', 'right'):
    offline.action(direction, now)
offline.action('detail', now)
assert offline.snapshot()['pve_view'] == 'guests'
offline.action('up', now + 11)
offline_view = offline.snapshot()
assert offline_view['count'] == 0 and offline_view['detail'] is None and offline_view['pve_view'] is None

# Removing the selected list entry keeps the current selection on a surviving guest.
list_removal = Monitor()
assert list_removal.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
list_removal.action('detail', now)
for direction in ('right', 'right', 'down', 'down', 'right'):
    list_removal.action(direction, now)
list_removal.action('detail', now)
list_removal.action('down', now)
assert list_removal.snapshot()['pve_selected'] == 1
reduced = json.loads(json.dumps(message))
reduced['virtualization']['observed_at'] = time.time()
reduced['virtualization']['guests'] = [guest for guest in reduced['virtualization']['guests'] if guest['id'] != 'lab:lxc:101']
assert list_removal.receive('sys/agents/pve-node-a/metrics', json.dumps(reduced), now=now + 1)
list_view = list_removal.snapshot()
assert list_view['pve_view'] == 'guests' and list_view['pve_selected'] == 1
assert list_view['hosts'][0]['virtualization']['guest_count'] == 4

# List selection follows the current index on refresh, then follows guest ID across reorder.
selection = Monitor()
assert selection.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
selection.action('detail', now)
for direction in ('right', 'right', 'down', 'down', 'right'):
    selection.action(direction, now)
selection.action('detail', now)
assert selection.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now + 1)
selection.action('down', now + 1)
assert selection.snapshot()['pve_selected'] == 1
assert selection.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now + 2)
selection_view = selection.snapshot()
assert selection_view['pve_selected'] == 1
selected_id = selection_view['hosts'][0]['virtualization']['guests'][selection_view['pve_selected']]['id']
reordered = json.loads(json.dumps(message))
reordered['virtualization']['observed_at'] = time.time()
reordered['virtualization']['guests'].reverse()
assert selection.receive('sys/agents/pve-node-a/metrics', json.dumps(reordered), now=now + 3)
selection_view = selection.snapshot()
assert selection_view['hosts'][0]['virtualization']['guests'][selection_view['pve_selected']]['id'] == selected_id

# A migrated guest keeps its cluster/type/VMID identity and appears under its new node only after both observations complete.
migration = Monitor()
assert migration.receive('sys/agents/pve-node-a/metrics', json.dumps(message), now=now)
removed_from_node_a = json.loads(json.dumps(message))
removed_from_node_a['virtualization']['observed_at'] = time.time()
removed_from_node_a['virtualization']['guests'] = []
assert migration.receive('sys/agents/pve-node-a/metrics', json.dumps(removed_from_node_a), now=now + 1)
node_b = json.loads(json.dumps(message))
node_b['host'] = 'pve-node-b'
node_b['virtualization']['node'] = 'pve-node-b'
node_b['virtualization']['observed_at'] = time.time()
node_b['virtualization']['guests'] = [dict(node_b['virtualization']['guests'][0], node='pve-node-b')]
assert migration.receive('sys/agents/pve-node-b/metrics', json.dumps(node_b), now=now + 2)
migrated = migration.snapshot()
assert migrated['count'] == 2
assert migrated['hosts'][0]['virtualization']['guest_count'] == 0
assert migrated['hosts'][1]['virtualization']['guests'][0]['id'] == 'lab:qemu:100'
assert migrated['hosts'][1]['virtualization']['guests'][0]['node'] == 'pve-node-b'

# Host-only payloads remain valid and missing initial inventory stays unknown.
legacy = Monitor()
assert legacy.receive('sys/agents/legacy/metrics', json.dumps({'host': 'legacy', 'ts': time.time()}), now=now)
assert legacy.snapshot()['hosts'][0].get('virtualization') is None
print('PASS: PVE receive, nested inventory, navigation, atomic invalid snapshot, legacy host')
