"""Recorder compilation pins SDK/target and preserves the Swift driver entrypoint."""
import hashlib
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_managed_recording
from recording_adapters import validate_execution_identity
from record_app_window import compile_recorder, main


class RecorderExecutionIdentityTests(unittest.TestCase):
    def test_compilation_keeps_driver_alias_and_explicit_sdk_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); sdk = root / 'sdk'; sdk.mkdir()
            driver = root / 'swift-frontend'
            driver.write_text('#!/bin/sh\nif [ "$1" = "--version" ]; then echo "Apple Swift version 6.2-test"; exit 0; fi\nfor argument in "$@"; do output="$argument"; done\nprintf "fixture-binary" > "$output"\n')
            driver.chmod(0o700)
            compiler = root / 'swiftc'; compiler.symlink_to(driver)
            source = root / 'source.swift'; source.write_text('fixture source')
            binary = root / 'recorder'
            original = subprocess.run
            def run(command, **options):
                if command[0] == 'fixture-xcrun':
                    output = str(compiler) if '--find' in command else str(sdk) if '--show-sdk-path' in command else '0.0'
                    return subprocess.CompletedProcess(command, 0, output, '')
                return original(command, **options)
            with patch('record_app_window.shutil.which', return_value='fixture-xcrun'), \
                 patch('record_app_window.subprocess.run', side_effect=run), \
                 patch('record_app_window.platform.machine', return_value='arm64'):
                command, identity, source_sha = compile_recorder(source, binary)
            self.assertEqual(command[0], str(compiler))
            self.assertEqual(command[1:5], ['-sdk', str(sdk), '-target', 'arm64-apple-macosx15.0'])
            self.assertEqual(identity['version'], '6.2-test')
            self.assertEqual(identity['sdk_version'], '0.0')
            self.assertEqual(binary.read_bytes(), b'fixture-binary')
            self.assertRegex(source_sha, r'^[0-9a-f]{64}$')

    def test_missing_identity_or_private_machine_fields_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'identity'):
            validate_execution_identity(None)
        identity = test_managed_recording.fixture_execution_identity()
        validate_execution_identity(identity)
        identity['environment']['architecture'] = '/private/machine'
        with self.assertRaisesRegex(ValueError, 'environment'):
            validate_execution_identity(identity)


class RecorderReceiptOwnershipTests(unittest.TestCase):
    def test_receipt_created_during_recording_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'recording.mov'
            receipt = root / 'recording.receipt.json'
            class FixtureTools:
                evidence = []
                @staticmethod
                def digest(path):
                    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
            def compile_fixture(source, binary):
                binary.write_bytes(b'fixture-recorder')
                return ['fixture-compiler'], {}, FixtureTools.digest(source)
            def normalize_fixture(plan, native, destination, tools):
                native.write_bytes(b'native')
                destination.write_bytes(b'normalized')
                receipt.write_bytes(b'owner receipt')
                return {'probe': {}, 'output_sha256': FixtureTools.digest(destination),
                        'native_sha256': FixtureTools.digest(native)}
            with patch('record_app_window.platform.system', return_value='Darwin'), \
                 patch('record_app_window.platform.mac_ver', return_value=('15.0', (), '')), \
                 patch('record_app_window.shutil.which', return_value='fixture-tool'), \
                 patch('record_app_window.compile_recorder', side_effect=compile_fixture), \
                 patch('record_app_window.subprocess.run', return_value=subprocess.CompletedProcess([], 0)), \
                 patch('media_tool_identity.MediaTools', FixtureTools), \
                 patch('recording_normalization.normalize', side_effect=normalize_fixture):
                result = main(['--bundle-id', 'fixture.dev', '--window-id', '42',
                               '--output', str(output), '--receipt', str(receipt), '--execute'])
            self.assertEqual(result, 2)
            self.assertEqual(receipt.read_bytes(), b'owner receipt')
