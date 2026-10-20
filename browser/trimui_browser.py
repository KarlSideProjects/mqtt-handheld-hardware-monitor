"""Display the shared Chromium page through the handheld's native SDL renderer."""
import base64
import ctypes as C
import fcntl
from collections import deque
import json
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request


class CDP:
    def __init__(self, socket):
        self.socket = socket
        self.sequence = 0
        self.frames = deque()

    def send(self, method, **params):
        self.sequence += 1
        self.socket.send(json.dumps(dict(id=self.sequence, method=method, params=params)))
        return self.sequence

    def receive(self):
        message = self.socket.recv()
        if not message or len(message) > 8 * 1024 * 1024:
            raise RuntimeError('Invalid Chromium response')
        return json.loads(message)

    def call(self, method, **params):
        request = self.send(method, **params)
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            result = self.receive()
            if result.get('method') == 'Page.screencastFrame':
                self.frames.append(result['params'])
            if result.get('id') != request:
                continue
            if 'error' in result:
                raise RuntimeError(f'Chromium {method}: {result["error"]}')
            return result['result']
        raise TimeoutError(f'Chromium {method} timed out')

    def next_frame(self):
        if self.frames:
            return self.frames.popleft()
        while True:
            result = self.receive()
            if result.get('method') == 'Page.screencastFrame':
                return result['params']


class Display:
    def __init__(self):
        self.sdl = C.CDLL('libSDL2.so')
        self.img = C.CDLL('libSDL2_image.so')
        self.window = self.renderer = None
        self.sdl.SDL_GetError.restype = C.c_char_p
        self.sdl.SDL_CreateWindow.argtypes = [C.c_char_p, C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint32]
        self.sdl.SDL_CreateWindow.restype = C.c_void_p
        self.sdl.SDL_CreateRenderer.argtypes = [C.c_void_p, C.c_int, C.c_uint32]
        self.sdl.SDL_CreateRenderer.restype = C.c_void_p
        self.sdl.SDL_SetHint.argtypes = [C.c_char_p, C.c_char_p]
        self.sdl.SDL_RWFromConstMem.argtypes = [C.c_void_p, C.c_int]
        self.sdl.SDL_RWFromConstMem.restype = C.c_void_p
        self.img.IMG_LoadTexture_RW.argtypes = [C.c_void_p, C.c_void_p, C.c_int]
        self.img.IMG_LoadTexture_RW.restype = C.c_void_p
        self.sdl.SDL_RenderClear.argtypes = [C.c_void_p]
        self.sdl.SDL_RenderCopy.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
        self.sdl.SDL_RenderPresent.argtypes = [C.c_void_p]
        for name in ('SDL_DestroyTexture', 'SDL_DestroyRenderer', 'SDL_DestroyWindow'):
            getattr(self.sdl, name).argtypes = [C.c_void_p]
        try:
            # Match the working stock MainUI: SHOWN window and accelerated/vsync renderer.
            self.check(self.sdl.SDL_Init(0x221) == 0)
            self.sdl.SDL_SetHint(b'SDL_RENDER_SCALE_QUALITY', b'1')
            self.window = self.sdl.SDL_CreateWindow(b'Hardware Monitor', 0x1fff0000, 0x1fff0000, 1280, 720, 4)
            self.check(self.window)
            self.renderer = self.sdl.SDL_CreateRenderer(self.window, -1, 6)
            self.check(self.renderer)
            self.check(self.img.IMG_Init(1) & 1)
        except BaseException:
            self.close()
            raise

    def check(self, success):
        if not success:
            raise RuntimeError(self.sdl.SDL_GetError().decode(errors='replace'))

    def present(self, jpeg):
        with open('/tmp/hwmonitor-display.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if Path('/sys/class/drm/card0-DSI-1/dpms').read_text().strip() == 'Off':
                return False
            self._present(jpeg)
            return True

    def _present(self, jpeg):
        # RWFromConstMem borrows this buffer until IMG_LoadTexture_RW finishes.
        buffer = C.create_string_buffer(jpeg)
        rw = self.sdl.SDL_RWFromConstMem(buffer, len(jpeg))
        self.check(rw)
        texture = self.img.IMG_LoadTexture_RW(self.renderer, rw, 1)
        self.check(texture)
        try:
            self.check(self.sdl.SDL_RenderClear(self.renderer) == 0)
            self.check(self.sdl.SDL_RenderCopy(self.renderer, texture, None, None) == 0)
            self.sdl.SDL_RenderPresent(self.renderer)
        finally:
            self.sdl.SDL_DestroyTexture(texture)
        event = C.create_string_buffer(64)
        while self.sdl.SDL_PollEvent(event):
            pass

    def close(self):
        if self.renderer:
            self.sdl.SDL_DestroyRenderer(self.renderer)
            self.renderer = None
        if self.window:
            self.sdl.SDL_DestroyWindow(self.window)
            self.window = None
        self.img.IMG_Quit()
        self.sdl.SDL_Quit()


def main():
    import websocket
    url = sys.argv[1]
    if url != 'http://127.0.0.1:8766/':
        raise ValueError('Only the local dashboard is supported')
    runtime = Path(__file__).resolve().parent
    root = runtime / 'rootfs'
    port_file = root / 'var/lib/hwmonitor-browser/profile/DevToolsActivePort'
    port_file.unlink(missing_ok=True)
    def stop(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    display = Display()
    browser = socket = receiver = None
    stopping = threading.Event()
    try:
        browser = subprocess.Popen([str(runtime / 'run-rootfs.sh'), str(root),
                                    '/bin/bash', '/opt/hwmonitor-headless.sh', url])
        deadline = time.monotonic() + 30
        while True:
            if browser.poll() is not None:
                raise RuntimeError('Headless Chromium exited before becoming ready')
            try:
                port = int(port_file.read_text().splitlines()[0])
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=1) as response:
                    pages = json.load(response)
                page = next(p for p in pages if p['type'] == 'page')
                # recv() still decodes UTF-8 in C; avoid the duplicate Python validator on large JPEG messages.
                socket = websocket.create_connection(page['webSocketDebuggerUrl'], timeout=3,
                                                      suppress_origin=True, skip_utf8_validation=True)
                break
            except (OSError, ValueError, StopIteration, IndexError):
                if time.monotonic() >= deadline:
                    raise TimeoutError('Headless Chromium did not become ready')
                time.sleep(.1)
        cdp = CDP(socket)
        cdp.call('Emulation.setDeviceMetricsOverride', width=1280, height=720, deviceScaleFactor=1, mobile=False)
        cdp.call('Emulation.setEmulatedMedia', features=[dict(name='prefers-reduced-motion', value='reduce')])
        cdp.call('Page.enable')
        params = dict(format='jpeg', quality=75, maxWidth=1280, maxHeight=720, everyNthFrame=1)
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/protocol', timeout=3) as response:
            protocol = json.load(response)
        command = next(c for d in protocol['domains'] if d['domain'] == 'Page'
                       for c in d['commands'] if c['name'] == 'startScreencast')
        parameters = {p['name'] for p in command.get('parameters', [])}
        if {'maxFramesInFlight', 'sendLastFrame'} <= parameters:
            params.update(maxFramesInFlight=1, sendLastFrame=True)
        cdp.call('Page.startScreencast', **params)
        socket.settimeout(.5)
        condition = threading.Condition()
        latest = [None]
        errors = []
        def receive_frames():
            try:
                while not stopping.is_set():
                    try:
                        frame = cdp.next_frame()
                    except websocket.WebSocketTimeoutException:
                        continue
                    # Ack every event; retain only the newest image so input never queues behind old frames.
                    cdp.send('Page.screencastFrameAck', sessionId=frame['sessionId'])
                    with condition:
                        latest[0] = frame
                        condition.notify()
            except Exception as error:
                if not stopping.is_set():
                    with condition:
                        errors.append(error)
                        condition.notify()
        receiver = threading.Thread(target=receive_frames, daemon=True)
        receiver.start()
        frames = 0
        first_frame_deadline = time.monotonic() + 10
        while browser.poll() is None:
            with condition:
                condition.wait_for(lambda: latest[0] is not None or errors, timeout=.5)
                if errors:
                    raise errors[0]
                frame, latest[0] = latest[0], None
            if frames == 0 and Path('/sys/class/drm/card0-DSI-1/dpms').read_text().strip() == 'Off':
                first_frame_deadline = time.monotonic() + 10
            if frame is None:
                if frames == 0 and time.monotonic() >= first_frame_deadline:
                    raise TimeoutError('Chromium did not produce a display frame within 10 seconds')
                continue
            if not display.present(base64.b64decode(frame['data'], validate=True)):
                continue
            frames += 1
            if frames == 1:
                print('SDL dashboard: first Chromium frame presented', flush=True)
        raise RuntimeError('Headless Chromium exited unexpectedly')
    finally:
        stopping.set()
        if socket:
            socket.close()
        if receiver:
            receiver.join(timeout=1)
        if browser is not None and browser.poll() is None:
            browser.terminate()
            try:
                browser.wait(timeout=8)
            except subprocess.TimeoutExpired:
                browser.kill()
                browser.wait()
        display.close()


if __name__ == '__main__':
    main()
