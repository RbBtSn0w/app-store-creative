"""Missing commits require explicit decisions, without concealing committed records."""
import unittest
from unittest.mock import patch
import test_artifact_lifecycle as fixtures


class CommitAbandonmentTests(unittest.TestCase):
    setUp = fixtures.ArtifactLifecycleTests.setUp

    def missing(self):
        original=self.store._write_path
        def fail(path,data):
            if path.parent.name=='runs': raise OSError('simulated failed publication')
            return original(path,data)
        with patch.object(self.store,'_write_path',side_effect=fail):
            with self.assertRaises(OSError): self.store.start_run({})
        return self.store.verify_history()['events'][0]['event_id']

    def test_explicit_abandonment_preserves_intent_and_never_claims_commit(self):
        event=self.missing(); before=self.store._path('events',event).read_bytes()
        self.store.abandon_commit(event,'owner','Cancelled failed run creation')
        audit=self.store.verify_history()
        self.assertEqual(audit['status'],'PASS',audit)
        row=next(row for row in audit['events'] if row['event_id']==event)
        self.assertEqual(row['status'],'ABANDONED')
        self.assertEqual(self.store._path('events',event).read_bytes(),before)
        self.assertEqual(list((self.store.paths.workspace/'records/runs').glob('*.json')),[])

    def test_committed_record_cannot_be_abandoned(self):
        self.store.start_run({});event=self.store.verify_history()['events'][0]['event_id']
        with self.assertRaisesRegex(ValueError,'missing'):
            self.store.abandon_commit(event,'owner','Cancel')

    def test_blank_decision_is_rejected(self):
        event=self.missing()
        with self.assertRaises(ValueError): self.store.abandon_commit(event,'owner','')

    def test_referenced_missing_target_cannot_be_abandoned(self):
        event=self.missing()
        identity=self.store._read('events',event)['record']['id']
        with self.store.transaction():
            self.store._record('incidents',{'id':'a'*32,'references':{'id':identity}})
        with self.assertRaisesRegex(ValueError,'referenced'):
            self.store.abandon_commit(event,'owner','Cancel failed run')

    def test_public_cli_requires_confirmation_and_records_decision(self):
        import json,subprocess,sys
        from pathlib import Path
        event=self.missing();self.store.config_path.write_text(json.dumps(self.cfg))
        cli=Path(__file__).parents[1]/'plugins/app-store-creative/scripts/app_store_creative.py'
        args=[sys.executable,str(cli),'history','abandon','--repo',str(self.root),
              '--event-id',event,'--actor','owner','--reason','Cancel failed run']
        missing=subprocess.run(args,capture_output=True,text=True)
        self.assertNotEqual(missing.returncode,0)
        saved=subprocess.run(args+['--confirm','ABANDON'],check=True,capture_output=True,text=True)
        self.assertEqual(json.loads(saved.stdout)['status'],'ABANDONED')
        self.assertEqual(self.store.verify_history()['status'],'PASS')

    def test_abandoned_target_cannot_be_recreated_under_the_same_identity(self):
        event=self.missing()
        target=self.store._read('events',event)['record']
        self.store.abandon_commit(event,'owner','Cancel failed run')
        with self.assertRaisesRegex(ValueError,'abandoned'):
            with self.store.transaction():
                self.store._record(target['category'],{'id':target['id'],'target':{}},target['suffix'])
        self.assertEqual(self.store.verify_history()['status'],'PASS')
