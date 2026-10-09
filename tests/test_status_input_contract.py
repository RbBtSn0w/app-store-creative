"""Status entry points reject malformed identities without record writes."""
import json,tempfile,unittest
from pathlib import Path
from artifact_lifecycle import Lifecycle

class StatusInputContractTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();config={'project':{'id':'status-input'}}
        (self.root/'creative.config.json').write_text(json.dumps(config))
        self.store=Lifecycle.from_configuration(self.root);self.store.start_run({})
    def check(self,name):
        before={str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for identity in ('../outside','',True,None,'a'*129,'with space'):
            with self.subTest(identity=identity),self.assertRaisesRegex(ValueError,'Invalid record identity'):
                getattr(self.store,name)(identity)
        self.assertEqual(before,{str(p):p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_delivery(self):self.check('delivery_status')
    def test_publication(self):self.check('publication_status')
    def test_preparation(self):self.check('external_preparation_status')

