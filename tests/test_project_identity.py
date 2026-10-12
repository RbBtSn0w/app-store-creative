"""Configuration review and execution share stable project identity validation."""
from pathlib import Path
import tempfile
import unittest
from artifact_lifecycle import Lifecycle
from configuration_layers import compose
from studio_contract import check_config


class ProjectIdentityTests(unittest.TestCase):
    def test_invalid_identity_is_refused_consistently_before_writes(self):
        for project in (None, {}, {'id': ''}, {'id': '  '}, {'id': True}, {'id': 'bad\nidentity'}):
            with self.subTest(project=project), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = {'project': project, 'cards': []}
                errors = []
                for operation in (lambda: Lifecycle(root, config),
                                  lambda: compose(root, config), lambda: check_config(config)):
                    with self.assertRaises(ValueError) as error:
                        operation()
                    errors.append(str(error.exception))
                self.assertEqual(len(set(errors)), 1)
                self.assertEqual(list(root.iterdir()), [])

    def test_explicit_identity_is_preserved_without_directory_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'project': {'id': 'explicit-product-Ω'}, 'cards': []}
            self.assertEqual(check_config(config)['project']['id'], 'explicit-product-Ω')
            effective, _, _ = compose(root, config)
            self.assertEqual(effective['project']['id'], 'explicit-product-Ω')
            core = Lifecycle(root, config)
            self.assertEqual(core.start_run({})['config']['project']['id'], 'explicit-product-Ω')
