"""Terminal quarantine preparation cannot restart filesystem mutations."""
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parents[1] / "plugins/app-store-creative/skills/app-store-creative/runtime/scripts"))
import relocation_quarantine


class QuarantineResumeBoundaryTests(unittest.TestCase):
    def test_cancelled_or_committing_preparation_cannot_resume(self):
        for suffix in ('preparation-cancelled', 'commit-intent', 'purge-intent'):
            with self.subTest(marker=suffix), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                (root / suffix).write_text('{}')
                (root / 'preparation-resumed').write_text('{}')
                core = SimpleNamespace(transaction=nullcontext,
                                       _read=lambda *args: {'operation': 'relocation-quarantine'},
                                       _path=lambda category, identity, suffix: root/suffix)
                with patch.object(relocation_quarantine, '_attempt') as attempt:
                    with self.assertRaisesRegex(ValueError, 'resumable'):
                        relocation_quarantine.resume(core, 'operation', 'owner', 'retry')
                    attempt.assert_not_called()
