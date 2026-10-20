"""Run on the development computer: python3 browser/test_trimui_browser.py."""
import json

from trimui_browser import CDP


class Socket:
    def __init__(self, messages):
        self.messages = iter(json.dumps(message) for message in messages)
        self.sent = []

    def recv(self):
        return next(self.messages)

    def send(self, message):
        self.sent.append(json.loads(message))


# A frame may arrive before the command response; identical session IDs still require separate acknowledgments.
socket = Socket([
    dict(method='Page.screencastFrame', params=dict(sessionId=7, data='first')),
    dict(id=1, result={}),
    dict(id=2, result={}),
    dict(method='Page.screencastFrame', params=dict(sessionId=7, data='second')),
])
cdp = CDP(socket)
assert cdp.call('Page.startScreencast', format='jpeg') == {}
first = cdp.next_frame()
assert first['data'] == 'first'
cdp.send('Page.screencastFrameAck', sessionId=first['sessionId'])
second = cdp.next_frame()
assert second['data'] == 'second'
cdp.send('Page.screencastFrameAck', sessionId=second['sessionId'])
assert [message['params'] for message in socket.sent[1:]] == [{'sessionId': 7}, {'sessionId': 7}]
assert [message['id'] for message in socket.sent] == [1, 2, 3]
try:
    CDP(Socket([dict(id=1, error=dict(message='capture failed'))])).call('Page.startScreencast')
except RuntimeError as error:
    assert 'capture failed' in str(error)
else:
    raise AssertionError('Chromium protocol error was ignored')
print('PASS: CDP interleaved events, retained first frame, per-frame ACK with shared session ID, error propagation')

# Do not submit pageflips while native DRM is powered off.
from unittest.mock import Mock, patch
from trimui_browser import Display
presenter = Display.__new__(Display)
presenter._present = Mock()
with patch('trimui_browser.Path.read_text', return_value='Off\n'):
    assert presenter.present(b'jpeg') is False
    presenter._present.assert_not_called()
with patch('trimui_browser.Path.read_text', return_value='On\n'):
    assert presenter.present(b'jpeg') is True
    presenter._present.assert_called_once_with(b'jpeg')
print('PASS: powered-off display skips native pageflips and resumes when on')
