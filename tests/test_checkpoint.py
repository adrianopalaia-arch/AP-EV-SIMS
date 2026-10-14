import tempfile,unittest,json
from pathlib import Path
from ap_evsims.checkpoint import scan_bytes,safe_files
from ap_evsims.redteam import audit_inventory
from ap_evsims.diagnostics import readiness_gate

class CheckpointTests(unittest.TestCase):
    def test_secrets_env_database_and_large_file_rejected(self):
        cases=[('.env',b'x'),('data/x.json',b'{}'),('outputs/x.json',b'"private-value"'),('outputs/x.txt',b'x'*5_000_001)]
        for name,body in cases:
            with self.assertRaises(ValueError):scan_bytes(name,body,['private-value'])
        scan_bytes('.env.example',b'CFBD_API_KEY=\nTHE_ODDS_API_KEY=\n',[])
    def test_allowlist_omits_raw_data_and_runtime(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name in ('data/raw/x.json','.venv/x.py','src/a.py','TASK_STATE.json','.env','.env.example'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('{}')
            self.assertEqual(safe_files(root),['.env.example','TASK_STATE.json','src/a.py'])
    def test_real_audit_has_all_categories_and_blocks_readiness(self):
        rows=audit_inventory();self.assertEqual({r['id'] for r in rows},set(range(1,51)))
        result=readiness_gate(rows,empirical_n=0,prospective_n=0,beats_market=False,coverage_validated=False)
        self.assertEqual(result['status'],'RESEARCH_ONLY');self.assertIn('CRITICAL_RED_TEAM_UNRESOLVED',result['reasons'])
    def test_editable_install_metadata_is_never_staged(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for name in ('src/ap_evisims.egg-info/SOURCES.txt','src/build/leak.txt','src/a.py'):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('example')
            self.assertEqual(safe_files(root),['src/a.py'])
