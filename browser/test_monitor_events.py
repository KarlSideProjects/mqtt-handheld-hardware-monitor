"""Run: python3 browser/test_monitor_events.py; real SSE transport must wake on input."""
import http.client
import json
from pathlib import Path
import threading
import time
from http.server import ThreadingHTTPServer
from monitor import Monitor, handler

state = Monitor()
for host in ('one', 'two', 'three'):
    state.receive('metrics', json.dumps({'host': host}))
with ThreadingHTTPServer(('127.0.0.1', 0), handler(state)) as server:
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    conn = http.client.HTTPConnection(*server.server_address, timeout=2)
    conn.request('GET', '/events')
    response = conn.getresponse()
    assert response.getheader('Content-Type') == 'text/event-stream'
    assert json.loads(response.readline().decode()[6:])['selected'] == 'one'
    response.readline()
    started = time.monotonic()
    state.action('down')
    assert json.loads(response.readline().decode()[6:])['selected'] == 'two'
    assert time.monotonic() - started < .2, 'Input waited for polling heartbeat'
    response.readline()
    control = http.client.HTTPConnection(*server.server_address, timeout=2)
    control.request('POST', '/control', json.dumps({'action': 'rotate_right'}),
                    {'Host': '127.0.0.1:8766', 'Content-Type': 'application/json'})
    assert control.getresponse().status == 200
    assert json.loads(response.readline().decode()[6:])['rotation'] == 90
    control.close()
    conn.close()
    conn = http.client.HTTPConnection(*server.server_address, timeout=2)
    conn.request('GET', '/pve.js')
    response = conn.getresponse()
    assert response.status == 200 and response.getheader('Content-Type').startswith('application/javascript')
    assert b'PVEView' in response.read()
    conn.close()
    # Browser actions must pass the real HTTP allowlist and change the real state.
    both = json.loads((Path(__file__).parent / 'fixtures/virtualization-v1.fixture.json').read_text())
    both['virtualization']['observed_at'] = time.time()
    both['docker'] = json.loads((Path(__file__).parent / 'fixtures/docker-v1.fixture.json').read_text())['docker']
    both['docker']['observed_at'] = time.time()
    state.receive('metrics', json.dumps(both))
    while state.snapshot()['selected'] != both['host']:
        state.action('next')
    def control(action, host='127.0.0.1:8766', origin='http://127.0.0.1:8766'):
        client = http.client.HTTPConnection(*server.server_address, timeout=2)
        client.request('POST', '/control', json.dumps({'action': action}),
                       {'Host': host, 'Origin': origin, 'Content-Type': 'application/json'})
        response = client.getresponse()
        code = response.status
        response.read()
        client.close()
        return code
    assert control('detail') == 200 and state.snapshot()['detail'] == both['host']
    assert control('focus:cpu') == 200 and state.snapshot()['focus'] == 'cpu'
    assert control('back') == 200 and state.snapshot()['focus'] is None
    for provider in ('pve', 'docker'):
        assert control(provider) == 200
        assert state.snapshot()['resource_provider'] == provider
        assert state.snapshot()['pve_view'] == 'guests'
        assert control('detail') == 200 and state.snapshot()['pve_view'] == 'guest'
        identity = state.snapshot()['pve_guest_id']
        assert control('next') == 200 and control('previous') == 200
        assert state.snapshot()['pve_guest_id'] == identity
        assert control('back') == 200 and state.snapshot()['pve_view'] == 'guests'
        assert control('back') == 200 and state.snapshot()['pve_view'] is None
    before = state.snapshot()['detail']
    assert control('back', origin='https://untrusted.example') == 403
    assert control('back', host='untrusted.example') == 403
    assert control('execute:rm') == 400
    assert control(['docker']) == 400
    assert state.snapshot()['detail'] == before
    assert control('back') == 200 and state.snapshot()['detail'] is None
    server.shutdown()
print('PASS: SSE, real HTTP host/metric/PVE/Docker navigation and invalid-origin/action rejection')
