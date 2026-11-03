"""Foundation imports and wire bytes stay independent of business composition."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


RUNTIME = Path(__file__).resolve().parents[1] / 'plugins/app-store-creative/skills/app-store-creative/runtime/scripts'


class FoundationBoundaryTests(unittest.TestCase):
    def test_legacy_record_exports_reexport_foundation_functions(self):
        import artifact_lifecycle
        import record_primitives
        for name in ('canonical', 'digest', 'safe_id', 'identifier', 'now', 'dependency_closure'):
            with self.subTest(name=name):
                self.assertIs(getattr(artifact_lifecycle, name), getattr(record_primitives, name))

    def test_legacy_storage_exports_reexport_foundation_types(self):
        import artifact_lifecycle
        import storage_paths
        for name in ('StoragePaths', 'STORAGE_DEFAULTS', 'overlaps'):
            with self.subTest(name=name):
                self.assertIs(getattr(artifact_lifecycle, name), getattr(storage_paths, name))

    def test_configuration_import_does_not_load_business_composition(self):
        result = subprocess.run([sys.executable, '-c',
            'import configuration_layers, sys, json; '
            'print(json.dumps([name for name in sys.modules if name in '
            '("artifact_lifecycle", "delivery_lifecycle", "publication_lifecycle", '
            '"relocation_lifecycle")]))'],
            env={**os.environ, 'PYTHONPATH': str(RUNTIME), 'PYTHONDONTWRITEBYTECODE': '1'},
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [])

    def test_canonical_bytes_and_identity_rejections_remain_exact(self):
        from artifact_lifecycle import canonical, safe_id
        self.assertEqual(canonical({'z': [True, None], 'a': 'value'}),
                         b'{"a":"value","z":[true,null]}')
        self.assertEqual(canonical({'text': '\u5b57'}), '{"text":"\u5b57"}'.encode())
        with self.assertRaises(ValueError):
            canonical({'invalid': float('nan')})
        for value in ('../other', '', True, None, 'x' * 129):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Invalid record identity'):
                safe_id(value)
        self.assertEqual(safe_id('Valid_record-1'), 'Valid_record-1')

    def test_digest_and_dependency_traversal_remain_compatible(self):
        from artifact_lifecycle import dependency_closure, digest
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source'
            path.write_bytes(b'unchanged bytes')
            self.assertEqual(digest(path), hashlib.sha256(b'unchanged bytes').hexdigest())
        records = {'a': {'inputs': ['b', 'c']}, 'b': {'inputs': ['c']}, 'c': {'inputs': []}}
        self.assertEqual(dependency_closure(['a'], records.__getitem__), records)
        records['c']['inputs'] = ['a']
        with self.assertRaisesRegex(ValueError, 'Artifact dependency cycle'):
            dependency_closure(['a'], records.__getitem__)

    def test_storage_resolution_retains_default_and_overlap_rules(self):
        from artifact_lifecycle import StoragePaths
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            paths = StoragePaths.resolve(root, {})
            self.assertEqual(paths.workspace, root / '.creative')
            self.assertEqual(paths.objects, root / '.creative/objects')
            self.assertEqual(paths.layer_paths()['cache'], root / '.creative/.cache')
            with self.assertRaisesRegex(ValueError, 'overlap'):
                StoragePaths.resolve(root, {'storage': {'releaseRoot': '.creative/releases'}})
            with self.assertRaisesRegex(ValueError, 'relative escape'):
                StoragePaths.resolve(root, {'storage': {'workspaceRoot': '../external'}})
