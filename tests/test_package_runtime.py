"""Packaging smoke probes must not introduce interpreter-specific payloads."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile


class PackageRuntimeTests(unittest.TestCase):
    def test_complete_package_contains_no_generated_python_bytecode(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as scratch:
            output = Path(scratch) / 'plugin.zip'
            environment = dict(os.environ)
            environment.pop('PYTHONDONTWRITEBYTECODE', None)
            result = subprocess.run([sys.executable, str(root / '.github/package_plugin.py'),
                                     '--output', str(output)], cwd=scratch,
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertFalse([name for name in names if '__pycache__' in Path(name).parts
                                  or name.endswith('.pyc')])
                self.assertIn('app-store-creative/skills/app-store-creative/runtime/scripts/app_store_creative.py', names)
