import json,tempfile,unittest,socket
from pathlib import Path
from unittest.mock import patch
from hashlib import sha256
from ap_evsims.handoff import publish_handoff
from ap_evsims.cycle import research_cycle
from ap_evsims.publication import atomic_json
from ap_evsims.research_store import ResearchStore
from ap_evsims.warehouse import Warehouse
from ap_evsims.offline import offline_mode
from ap_evsims.integrity import digest
from ap_evsims.__main__ import main
from test_warehouse import archive

def setup_repo(root):
    repo=Path(root);store=ResearchStore(repo/'data');warehouse=Warehouse(store.root)
    state=dict(branch='test',categories={k:{} for k in ('CFB','NHL','NFL','MLB','NBA')},
        current_task='test',next_task='test',tests=dict(passed=0,failed=0))
    atomic_json(repo/'TASK_STATE.json',state)
    return repo,store,warehouse

class HandoffCycleTests(unittest.TestCase):
    def test_feed_is_pass_only_and_manifest_verifiable(self):
        with tempfile.TemporaryDirectory() as t,offline_mode():
            repo,s,w=setup_repo(t);w.record_odds(s,archive(s))
            result=publish_handoff(repo,s,w,now='2026-10-14T10:05:00Z')
            self.assertEqual(result['passes'],2);self.assertEqual(result['edges'],0)
            passes=json.loads((repo/'outputs/latest_passes.json').read_text())
            self.assertIn('STALE_PRICE',passes[0]['pass_reason'])
            self.assertIsNone(passes[0]['model_probability'])
            self.assertAlmostEqual(sum(p['market_no_vig_probability'] for p in passes),1)
            last=json.loads((repo/'outputs/last_update.json').read_text())
            for name,fingerprint in last['feed_hashes'].items():
                self.assertEqual(fingerprint,digest(json.loads((repo/'outputs'/name).read_text())))
    def test_atomic_failure_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as t:
            target=Path(t)/'value.json';atomic_json(target,{'old':True})
            with patch('ap_evsims.publication.os.replace',side_effect=OSError('fixture failure')):
                with self.assertRaises(OSError):atomic_json(target,{'new':True})
            self.assertEqual(json.loads(target.read_text()),{'old':True})
            self.assertEqual(len(list(Path(t).iterdir())),1)
    def test_offline_cycle_never_fetches_and_keeps_empty_sample(self):
        with tempfile.TemporaryDirectory() as t:
            repo,s,w=setup_repo(t)
            with patch('ap_evsims.cycle.collect_odds',side_effect=AssertionError('network forbidden')):
                result=research_cycle(repo,s,w,offline=True)
            self.assertEqual(result['real_model_sample'],0)
            self.assertEqual(result['action'],'KEEP_CHAMPION')
            self.assertIn('MISSING_LOCAL_DATA',result['blockers'][0])
    def test_offline_flag_cannot_silently_allow_download(self):
        with self.assertRaises(SystemExit):main(['collect_odds','--offline'])
        with self.assertRaises(SystemExit):main(['sync_data','--offline','--cfbd-year','2025'])
    def test_publication_rejects_secret_and_nonfinite_values(self):
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'CFBD_API_KEY':'private-test-value'}):
            with self.assertRaisesRegex(ValueError,'SECRET_IN_PUBLICATION'):atomic_json(Path(t)/'secret.json',{'value':'private-test-value'})
            with self.assertRaises(ValueError):atomic_json(Path(t)/'nan.json',{'value':float('nan')})
