"""Owned, loopback-only Chrome rendering with real-time readiness and no extra dependencies."""
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import urllib.parse
import urllib.request

MAX_FRAME_BYTES = 32 * 1024 * 1024


class DevToolsSocket:
    def __init__(self, url, deadline):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != 'ws' or parsed.hostname not in ('127.0.0.1', 'localhost'):
            raise ValueError('Chrome DevTools must use an owned loopback endpoint')
        self.deadline = deadline
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=self.remaining())
        self.buffer = b''
        self.sequence = 0
        key = base64.b64encode(os.urandom(16)).decode()
        path = parsed.path + ('?' + parsed.query if parsed.query else '')
        request = (f'GET {path} HTTP/1.1\r\nHost: {parsed.hostname}:{parsed.port}\r\n'
                   f'Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n'
                   'Sec-WebSocket-Version: 13\r\n\r\n')
        self.sock.sendall(request.encode())
        header = b''
        while b'\r\n\r\n' not in header:
            data = self.sock.recv(4096)
            if not data:
                raise RuntimeError('Chrome closed its DevTools connection')
            header += data
            if len(header) > 16384:
                raise ValueError('Oversized DevTools handshake')
            if not header:
                raise RuntimeError('Chrome closed its DevTools connection')
        header, self.buffer = header.split(b'\r\n\r\n', 1)
        expected = base64.b64encode(hashlib.sha1((key + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest()).decode()
        lines = header.decode().split('\r\n')
        fields = {key.lower(): value.strip() for key, value in (line.split(':', 1) for line in lines[1:] if ':' in line)}
        if ' 101 ' not in lines[0] or fields.get('sec-websocket-accept', '') != expected:
            raise RuntimeError('Chrome rejected its DevTools handshake')

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Chrome render deadline exceeded')
        return remaining

    def read(self, size):
        while len(self.buffer) < size:
            self.sock.settimeout(self.remaining())
            data = self.sock.recv(min(65536, size - len(self.buffer)))
            if not data:
                raise RuntimeError('Chrome closed its DevTools connection')
            self.buffer += data
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def send(self, payload, opcode=1):
        mask = os.urandom(4)
        size = len(payload)
        if size > MAX_FRAME_BYTES:
            raise ValueError('Oversized DevTools request')
        length = bytes([size | 128]) if size < 126 else (
            bytes([126 | 128]) + struct.pack('>H', size) if size <= 65535 else bytes([127 | 128]) + struct.pack('>Q', size))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        self.sock.settimeout(self.remaining())
        self.sock.sendall(bytes([128 | opcode]) + length + mask + masked)

    def receive(self):
        fragments = bytearray()
        while True:
            first, second = self.read(2)
            opcode, final = first & 15, bool(first & 128)
            length = second & 127
            if length == 126:
                length = struct.unpack('>H', self.read(2))[0]
            elif length == 127:
                length = struct.unpack('>Q', self.read(8))[0]
            if length > MAX_FRAME_BYTES or len(fragments) + length > MAX_FRAME_BYTES:
                raise ValueError('Oversized DevTools response')
            mask = self.read(4) if second & 128 else None
            data = self.read(length)
            if mask:
                data = bytes(byte ^ mask[index % 4] for index, byte in enumerate(data))
            if opcode == 8:
                raise RuntimeError('Chrome closed its DevTools connection')
            if opcode == 9:
                self.send(data, 10)
                continue
            if opcode == 10:
                continue
            if opcode not in (0, 1):
                raise ValueError('Unsupported DevTools message')
            fragments.extend(data)
            if final:
                return json.loads(fragments.decode())

    def call(self, method, params=None):
        self.sequence += 1
        self.send(json.dumps({'id': self.sequence, 'method': method, 'params': params or {}}).encode())
        while True:
            response = self.receive()
            if response.get('id') == self.sequence:
                if 'error' in response:
                    raise RuntimeError(f"Chrome {method}: {response['error'].get('message', 'request failed')}")
                return response.get('result', {})

    def close(self):
        self.sock.close()


def render_native(cmd, profile: Path, output: Path, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    app = next(parent for parent in Path(cmd[0]).parents if parent.suffix == '.app')
    size = next(value.split('=', 1)[1] for value in cmd if value.startswith('--window-size='))
    width, height = map(int, size.split(','))
    # DevTools owns the screenshot action; virtual time must not expire image decoding.
    excluded = ('--screenshot=', '--virtual-time-budget=', '--window-size=')
    flags = [value for value in cmd[1:-1] if not value.startswith(excluded)
             and value not in ('--dump-dom', '--run-all-compositor-stages-before-draw', '--force-device-scale-factor=1', '--default-background-color=ffffffff')]
    launch = ['/usr/bin/open', '-n', '-g', '--stdout', str(profile / 'browser.stdout'),
              '--stderr', str(profile / 'browser.stderr'), '-a', str(app), '--args', *flags,
              '--remote-debugging-address=127.0.0.1', '--remote-debugging-port=0', 'about:blank']
    result = subprocess.run(launch, capture_output=True, text=True, timeout=timeout_seconds)
    if result.returncode:
        return result
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    client = None
    while time.monotonic() < deadline:
        port_file = profile / 'DevToolsActivePort'
        try:
            port = int(port_file.read_text().splitlines()[0])
            with opener.open(f'http://127.0.0.1:{port}/json/list', timeout=min(1, deadline - time.monotonic())) as response:
                targets = json.loads(response.read())
            page = next(target for target in targets if target.get('type') == 'page' and target.get('url') == 'about:blank')
            client = DevToolsSocket(page['webSocketDebuggerUrl'], deadline)
            break
        except (OSError, ValueError, IndexError, StopIteration):
            time.sleep(0.05)
    if client is None:
        raise TimeoutError('Chrome did not expose the owned render page')
    try:
        client.call('Page.enable')
        client.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': height, 'deviceScaleFactor': 1, 'mobile': False})
        client.call('Emulation.setDefaultBackgroundColorOverride', {'color': {'r': 255, 'g': 255, 'b': 255, 'a': 1}})
        client.call('Page.navigate', {'url': cmd[-1]})
        while time.monotonic() < deadline:
            state = client.call('Runtime.evaluate', {'expression': "(() => { const root = document.querySelector('[data-export-ready]'); return { ready: root?.getAttribute('data-export-ready') === 'true', error: root?.getAttribute('data-export-error') }; })()", 'returnByValue': True})
            value = state.get('result', {}).get('value', {})
            if value.get('ready') or value.get('error'):
                dom = client.call('Runtime.evaluate', {'expression': 'document.documentElement.outerHTML', 'returnByValue': True})['result']['value']
                geometry = None
                if value.get('ready'):
                    measured = client.call('Runtime.evaluate', {'expression': "(() => { const card = document.querySelector('[data-card-id]'); const bounds = card.getBoundingClientRect(); const region = node => { const r = node.getBoundingClientRect(); return {left:(r.left-bounds.left)/bounds.width,top:(r.top-bounds.top)/bounds.width,width:r.width/bounds.width,height:r.height/bounds.width}; }; return {height:bounds.height/bounds.width, texts:Array.from(card.querySelectorAll('h2,p')).map(node=>({text:node.textContent,...region(node),lines:Math.round(node.getBoundingClientRect().height/(parseFloat(getComputedStyle(node).lineHeight)*(bounds.width/card.clientWidth)))})), device:card.querySelector('[data-device-frame]')?region(card.querySelector('[data-device-frame]')):null, background:region(card.querySelector('[data-background-track]'))}; })()", 'returnByValue': True})
                    geometry = measured['result']['value']
                    screenshot = client.call('Page.captureScreenshot', {'format': 'png', 'fromSurface': True,
                        'captureBeyondViewport': False, 'clip': {'x': 0, 'y': 0, 'width': width, 'height': height, 'scale': 1}})
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(base64.b64decode(screenshot['data'], validate=True))
                result = subprocess.CompletedProcess(cmd, 0, dom, '')
                result.geometry = geometry
                return result
            time.sleep(0.05)
        raise TimeoutError('Chrome page did not become ready before the render deadline')
    except RuntimeError as error:
        log = profile / 'browser.stderr'
        detail = log.read_text(errors='replace')[-1000:] if log.is_file() else ''
        if detail:
            import sys
            print(f'Chrome diagnostic: {detail}', file=sys.stderr)
        raise RuntimeError(f'{error}; retry the affected card in a supported local Chrome environment') from error
    finally:
        client.close()
