"""The public entrypoint rejects interpreters missing required runtime APIs."""
from pathlib import Path
import subprocess
import sys
import unittest


class PythonRequirementTests(unittest.TestCase):
    def invoke(self, version):
        entry = Path(__file__).resolve().parents[1] / 'plugins/app-store-creative/scripts/app_store_creative.py'
        code = ('import runpy, sys; '
                f'sys.version_info = {version!r}; '
                f'sys.argv = [{str(entry)!r}, "--help"]; '
                f'runpy.run_path({str(entry)!r}, run_name="__main__")')
        return subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)

    def test_python_310_is_rejected_before_runtime_imports(self):
        result = self.invoke((3, 10, 16))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('requires Python 3.11 or newer', result.stderr)

    def test_python_311_can_open_public_help(self):
        result = self.invoke((3, 11, 0))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('usage:', result.stdout)
