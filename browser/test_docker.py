"""Docker and PVE coexist through the real receive/navigation boundary."""
import copy
import json
import time
from pathlib import Path
from monitor import Monitor

now = time.monotonic()
fixture = json.loads((Path(__file__).parent / 'fixtures/virtualization-v1.fixture.json').read_text())
fixture['virtualization']['observed_at'] = time.time() - 2
docker = json.loads((Path(__file__).parent / 'fixtures/docker-v1.fixture.json').read_text())['docker']
docker.update(node='pve-node-a', observed_at=time.time()-2)
sample = docker['guests'][0]
sample.update(node='pve-node-a', name='<img src=x onerror=alert(1)>')
fixture['docker'] = docker
state = Monitor()
assert state.receive('sys/agents/pve-node-a/metrics', json.dumps(fixture), now=now)
host = state.snapshot()['hosts'][0]
assert host['docker']['guest_count'] == 1
assert host['virtualization']['guest_count'] == 2
assert host['docker']['guests'][0]['cpu']['percent_total'] == 200
state.action('detail', now)
state.action('docker', now)
assert state.snapshot()['resource_provider'] == 'docker'
assert state.snapshot()['pve_view'] == 'guests'
state.action('detail', now)
assert state.snapshot()['pve_guest_id'] == 'docker:' + 'a'*64
state.action('back', now)
state.action('back', now)
state.action('pve', now)
assert state.snapshot()['resource_provider'] == 'pve'
assert state.snapshot()['pve_view'] == 'guests'
state.action('back', now)
state.action('docker', now)
state.action('detail', now)

# A cached heartbeat cannot manufacture history. Docker errors preserve only Docker's data.
assert state.receive('x', json.dumps(fixture), now=now+1)
assert len(state.snapshot()['hosts'][0]['docker']['guests'][0]['history']) == 1
error = copy.deepcopy(fixture)
error['docker'] = dict(version=1, provider='docker', node='pve-node-a', status='error', error='api_unavailable', observed_at=None)
assert state.receive('x', json.dumps(error), now=now+2)
host = state.snapshot()['hosts'][0]
assert host['docker']['guest_count'] == 1 and host['docker']['status'] == 'error'
assert host['virtualization']['status'] == 'ok'

# Removing selected container returns to Docker list, not PVE list.
removed = copy.deepcopy(fixture)
removed['docker']['observed_at'] += 1
removed['docker']['guests'] = []
assert state.receive('x', json.dumps(removed), now=now+3)
assert state.snapshot()['pve_view'] == 'guests'
assert state.snapshot()['resource_provider'] == 'docker'
assert state.snapshot()['hosts'][0]['docker']['guest_count'] == 0

# Invalid data keeps the old complete inventory and leaves ordinary host metrics usable.
for change in ({'container_id': '../bad'}, {'id': 'docker:wrong'}, {'memory_basis': 'pve'}, {'cpu': {'percent_total': -1}}):
    invalid = copy.deepcopy(fixture)
    invalid['docker']['guests'][0].update(change)
    bad = state.snapshot()['bad_messages']
    assert state.receive('x', json.dumps(invalid), now=now+4)
    assert state.snapshot()['bad_messages'] == bad + 1
    assert state.snapshot()['hosts'][0]['docker']['guest_count'] == 0

# Docker-only hosts reach the entry via physical directions and have no PVE entry.
solo = Monitor()
plain = {k:v for k,v in fixture.items() if k != 'virtualization'}
assert solo.receive('x', json.dumps(plain), now=now)
solo.action('detail', now)
for direction in ('right', 'right', 'down', 'down', 'right'):
    solo.action(direction, now)
assert solo.snapshot()['panel'] == 'docker'
solo.action('detail', now)
assert solo.snapshot()['resource_provider'] == 'docker' and solo.snapshot()['pve_view'] == 'guests'
print('PASS: Docker/PVE coexistence, full-ID navigation, history, error/removal, validation')

# Full-ID selection survives reordering; L/R remains inside the same Docker host.
paged = Monitor()
many = copy.deepcopy(plain)
many['docker']['guests'] = [dict(sample, container_id=f'{i:064x}', id=f'docker:{i:064x}', name='same-name') for i in range(5)]
assert paged.receive('x', json.dumps(many), now=now)
paged.action('detail', now)
paged.action('docker', now)
paged.action('right', now)
assert paged.snapshot()['pve_page'] == 1 and paged.snapshot()['pve_selected'] == 4
paged.action('detail', now)
paged.action('next', now)
assert paged.snapshot()['pve_guest_id'] == 'docker:' + '0'*64
reordered = copy.deepcopy(many)
reordered['docker']['observed_at'] += 1
reordered['docker']['guests'].reverse()
assert paged.receive('x', json.dumps(reordered), now=now+1)
assert paged.snapshot()['pve_selected'] == 4 and paged.snapshot()['pve_guest_id'] == 'docker:' + '0'*64
paged.action('previous', now+1)
assert paged.snapshot()['pve_guest_id'] == 'docker:' + f'{1:064x}'

# Stale data stays stale through host heartbeats; newer empty inventories cannot be undone.
aged = copy.deepcopy(plain)
aged['docker']['observed_at'] = time.time() - 40
stale = Monitor()
assert stale.receive('x', json.dumps(aged), now=now)
assert not stale.snapshot()['hosts'][0]['docker']['fresh']
assert stale.receive('x', json.dumps(plain), now=now+1)
assert stale.snapshot()['hosts'][0]['docker']['fresh']
assert stale.receive('x', json.dumps(removed), now=now+2)
assert stale.receive('x', json.dumps(plain), now=now+3)
assert stale.snapshot()['hosts'][0]['docker']['guest_count'] == 0

# Both entry cards can be reached with physical directions; B preserves the parent.
both = Monitor()
assert both.receive('x', json.dumps(fixture), now=now)
both.action('detail', now)
for direction in ('right', 'right', 'down', 'down', 'right', 'right'):
    both.action(direction, now)
assert both.snapshot()['panel'] == 'docker'
both.action('detail', now)
assert both.snapshot()['resource_provider'] == 'docker'
both.action('back', now)
assert both.snapshot()['detail'] == 'pve-node-a' and both.snapshot()['panel'] == 'docker'
both.action('left', now)
assert both.snapshot()['panel'] == 'pve'
both.action('detail', now)
assert both.snapshot()['resource_provider'] == 'pve'
both.action('back', now+11)
assert both.snapshot()['detail'] is None and both.snapshot()['pve_view'] is None
print('PASS: Docker pagination, stable-ID reorder, L/R, stale recovery, both physical entry cards')

# The browser's public HTTP control route accepts the Docker entry action.
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from monitor import handler
http_state = Monitor()
assert http_state.receive('x', json.dumps(plain))
http_state.action('detail')
with ThreadingHTTPServer(('127.0.0.1', 0), handler(http_state)) as server:
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/control',
                                         data=b'{"action":"docker"}', headers={'Host':'127.0.0.1:8766', 'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=3) as response:
            assert response.status == 200
        assert http_state.snapshot()['resource_provider'] == 'docker'
        assert http_state.snapshot()['pve_view'] == 'guests'
    finally:
        server.shutdown()
        thread.join()
print('PASS: public HTTP Docker control action')
