"""Run: python3 browser/test_monitor_events.py; real SSE transport must wake on input."""
import http.client
import json
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
    conn.close()
    conn = http.client.HTTPConnection(*server.server_address, timeout=2)
    conn.request('GET', '/pve.js')
    response = conn.getresponse()
    assert response.status == 200 and response.getheader('Content-Type').startswith('application/javascript')
    assert b'PVEView' in response.read()
    conn.close()
    server.shutdown()
print('PASS: SSE initial state and immediate input notification')
