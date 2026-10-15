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


class BrowserIdentityTests(unittest.TestCase):
    def test_owned_version_evidence_excludes_private_response_fields(self):
        from chrome_renderer import browser_identity
        result = browser_identity({'product': 'Chrome/141.0.7390.0', 'protocolVersion': '1.3',
            'jsVersion': '14.1.146.2', 'userAgent': '/private/profile', 'revision': 'internal'})
        self.assertEqual(result['source'], 'owned-live-devtools')
        self.assertEqual(result['product'], 'Chrome/141.0.7390.0')
        self.assertNotIn('userAgent', result)
        self.assertNotIn('revision', result)

    def test_missing_or_private_version_fields_do_not_become_identity(self):
        from chrome_renderer import browser_identity
        for product in (None, '/Users/private/browser', 'Chrome/unknown'):
            with self.assertRaises(ValueError):
                browser_identity({'product': product, 'protocolVersion': '1.3', 'jsVersion': '14.1'})


class TargetScalingTests(unittest.TestCase):
    def test_mac_16_10_scaling_is_exact_integer_retina(self):
        from export_engine import get_target_scaling
        base_w, base_h, scale, phys_w, phys_h = get_target_scaling('mac_16_10')
        self.assertEqual(base_w, 720)
        self.assertEqual(base_h, 450)
        self.assertEqual(scale, 4.0)
        self.assertEqual(phys_w, 2880)
        self.assertEqual(phys_h, 1800)

    def test_iphone_scaling_matches_proportional_physical_dimensions(self):
        from export_engine import get_target_scaling
        base_w, base_h, scale, phys_w, phys_h = get_target_scaling('iphone_6_9')
        self.assertEqual(base_w, 400)
        self.assertEqual(base_h, 869)
        self.assertAlmostEqual(scale, 3.3, places=2)
        self.assertEqual(phys_w, 1320)
        self.assertEqual(phys_h, 2868)


class LaunchFlagsTests(unittest.TestCase):
    def test_launch_flags_preserve_scale_factor_and_window_size(self):
        cmd = [
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
            '--headless=new',
            '--screenshot=/tmp/out.png',
            '--window-size=720,450',
            '--default-background-color=ffffffff',
            '--dump-dom',
            '--no-first-run',
            '--disable-background-networking',
            '--hide-scrollbars',
            '--force-device-scale-factor=4.0',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--run-all-compositor-stages-before-draw',
            '--virtual-time-budget=10000',
            'http://127.0.0.1:3100/?export=true',
        ]
        excluded = ('--screenshot=', '--virtual-time-budget=')
        flags = [value for value in cmd[1:-1] if not value.startswith(excluded)
                 and value not in ('--dump-dom', '--run-all-compositor-stages-before-draw', '--default-background-color=ffffffff', '--disable-gpu', '--disable-dev-shm-usage')]
        self.assertIn('--force-device-scale-factor=4.0', flags)
        self.assertIn('--window-size=720,450', flags)
        self.assertNotIn('--disable-gpu', flags)
        self.assertNotIn('--screenshot=/tmp/out.png', flags)

