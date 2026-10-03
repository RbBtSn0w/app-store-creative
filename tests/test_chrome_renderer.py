"""Transport checks for the owned renderer: bounded frames, events, and masking."""
import json
from pathlib import Path
import struct
import sys
import time
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'plugins/app-store-creative/scripts'))
from chrome_renderer import DevToolsSocket, MAX_FRAME_BYTES


class FakeSocket:
    def __init__(self):
        self.sent = []

    def settimeout(self, timeout):
        pass

    def sendall(self, data):
        self.sent.append(data)


def frame(data, opcode=1, final=True):
    payload = data if isinstance(data, bytes) else json.dumps(data).encode()
    return bytes([opcode | (128 if final else 0), len(payload)]) + payload


def client(buffer=b''):
    transport = DevToolsSocket.__new__(DevToolsSocket)
    transport.buffer, transport.sock = buffer, FakeSocket()
    transport.deadline, transport.sequence = time.monotonic() + 1, 0
    return transport


class ChromeTransportTests(unittest.TestCase):
    def test_remote_debugging_endpoints_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'loopback'):
            DevToolsSocket('ws://remote.example:1234/devtools/page/id', time.monotonic() + 1)

    def test_client_frames_are_masked_without_changing_payload(self):
        transport = client()
        payload = b'{"id":1}'
        transport.send(payload)
        encoded = transport.sock.sent[0]
        self.assertEqual(encoded[0], 129)
        self.assertTrue(encoded[1] & 128)
        mask, content = encoded[2:6], encoded[6:]
        self.assertEqual(bytes(byte ^ mask[index % 4] for index, byte in enumerate(content)), payload)

    def test_fragmented_text_survives_interleaved_ping(self):
        text = json.dumps({'message': 'Chinese copy'}, ensure_ascii=False).encode()
        transport = client(frame(text[:12], final=False) + frame(b'ping', opcode=9) + frame(text[12:], opcode=0))
        self.assertEqual(transport.receive(), {'message': 'Chinese copy'})
        self.assertEqual(transport.sock.sent[0][0], 138)

    def test_events_are_not_mistaken_for_command_results(self):
        transport = client(frame({'method': 'Page.loadEventFired'}) + frame({'id': 1, 'result': {'ready': True}}))
        self.assertEqual(transport.call('Page.enable'), {'ready': True})

    def test_oversized_responses_fail_before_reading_payload(self):
        transport = client(b'\x81\x7f' + struct.pack('>Q', MAX_FRAME_BYTES + 1))
        with self.assertRaisesRegex(ValueError, 'Oversized'):
            transport.receive()


if __name__ == '__main__':
    unittest.main()
