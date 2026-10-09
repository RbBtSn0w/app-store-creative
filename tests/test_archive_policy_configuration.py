"""Declared archive choice is shared across configuration and execution."""
import tempfile
from pathlib import Path
import unittest
from artifact_lifecycle import Lifecycle
from configuration_layers import compose
from studio_contract import check_config


class ArchivePolicyConfigurationTests(unittest.TestCase):
    def test_invalid_declarations_rejected_consistently_before_writes(self):
        invalid = [None, {}, {'schema_version': True, 'mediaMode': 'git'},
            {'schema_version': 2, 'mediaMode': 'git'},
            {'schema_version': 1, 'mediaMode': 'unknown'},
            {'schema_version': 1, 'mediaMode': []},
            {'schema_version': 1, 'mediaMode': 'external'},
            {'schema_version': 1, 'mediaMode': 'git', 'backend': 'team'},
            {'schema_version': 1, 'mediaMode': 'external', 'backend': '/private/store'},
            {'schema_version': 1, 'mediaMode': 'lfs', 'credentials': 'forbidden'}]
        for policy in invalid:
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                config = {'project': {'id': 'fixture'}, 'cards': [], 'archivePolicy': policy}
                for operation in (lambda: Lifecycle(root, config),
                        lambda: compose(root, config), lambda: check_config(config)):
                    with self.assertRaisesRegex(ValueError, 'archive policy'):
                        operation()
                self.assertEqual(list(root.iterdir()), [])

    def test_declared_mode_and_backend_are_preserved_in_run_snapshot(self):
        for mode in ('git', 'lfs', 'external'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                policy = {'schema_version': 1, 'mediaMode': mode}
                if mode == 'external': policy['backend'] = 'team-media'
                config = {'project': {'id': 'fixture'}, 'cards': [], 'archivePolicy': policy}
                effective, _, _ = compose(Path(directory), config)
                self.assertEqual(effective['archivePolicy'], policy)
                self.assertEqual(check_config(config)['archivePolicy'], policy)
                run = Lifecycle(Path(directory), config).start_run({})
                self.assertEqual(run['config']['archivePolicy'], policy)

    def test_undeclared_policy_allows_exploration_without_inventing_choice(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'project': {'id': 'fixture'}, 'cards': []}
            run = Lifecycle(Path(directory), config).start_run({})
            self.assertNotIn('archivePolicy', run['config'])

class ArchivePolicyRetrievalTests(unittest.TestCase):
    def test_retrieval_must_match_declared_mode_and_backend(self):
        from archive_policy import require_retrieval
        for mode in ('git', 'lfs', 'external'):
            policy = {'schema_version': 1, 'mediaMode': mode}
            if mode == 'external': policy['backend'] = 'team'
            config = {'archivePolicy': policy}
            proof = {'media_mode': mode}
            if mode == 'external': proof['backend'] = 'team'
            self.assertEqual(require_retrieval(config, proof), policy)
            for other in ('git', 'lfs', 'external'):
                if other != mode:
                    with self.assertRaisesRegex(ValueError, 'archive policy'):
                        require_retrieval(config, {**proof, 'media_mode': other})
        with self.assertRaisesRegex(ValueError, 'archive policy'):
            require_retrieval({'archivePolicy': {'schema_version': 1, 'mediaMode': 'external', 'backend': 'team'}},
                              {'media_mode': 'external', 'backend': 'other'})
