import json
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
import cog_core

class VerificationContractTests(unittest.TestCase):
    def test_invalid_input_never_executes(self):
        for bundle in ({}, {'materialized': None}, {'command': 'anything'}):
            with self.subTest(bundle=bundle), patch.object(cog_core.task_logic, 'run') as run:
                result = cog_core.invoke(bundle)
                self.assertFalse(result['ok'])
                run.assert_not_called()

    def test_unknown_or_duplicate_evidence_criteria_refused(self):
        for ids in (['invented'], ['length', 'length']):
            bundle = {'author_request': {'contract': {'acceptance_criteria': [{'id': 'length'}]}}, 'test_criterion_ids': ids}
            self.assertEqual(cog_core.task_logic.check_input(bundle)[0]['check'], 'evidence-criteria')

    def test_real_failing_test_diagnostics_reach_bounded_marked_review_evidence(self):
        from task_logic import Suite, digest, package_digest, verify
        bundle=json.loads((ROOT/'examples/sample-bundle.json').read_text())
        files=bundle['author_envelope']['payload']['files']
        tests=next(row for row in files if row['path']=='tests/test_cog.py')
        tests['content'] += '\nprint("p" * 5000)\nprint("Distinctive stdout repair diagnostic")\nclass NeedsRepair(unittest.TestCase):\n    def test_needs_repair(self):\n        self.fail("Distinctive stderr repair diagnostic")\n'
        with tempfile.TemporaryDirectory(prefix='.verification-review-',dir=ROOT.parent) as folder:
            root=Path(folder);suite=Suite(ROOT.parent,root/'state',journal=lambda _:None)
            packaged=suite.package(bundle['author_request'],bundle['author_envelope'],root/bundle['author_request']['identity']['name'])
            snapshot=suite.source_snapshot(bundle['author_request'],bundle['author_envelope'])
            bundle['materialized']={'path':packaged['path'],'package_sha256':package_digest(root/bundle['author_request']['identity']['name']),'source_sha256':digest({'contract':snapshot['contract'],'files':sorted(snapshot['files'],key=lambda row:row['path'])})}
            report=verify(bundle,suite)
            self.assertNotEqual(report['tests']['exit_code'],0)
            evidence=next(row for row in report['review_request']['evidence'] if row['id']=='declared-tests:length')
            text=json.loads(evidence['text'])
            self.assertEqual(evidence['status'],'failed')
            self.assertIn('Distinctive stdout repair diagnostic',text['stdout_excerpt'])
            self.assertIn('Distinctive stderr repair diagnostic',text['stderr_excerpt'])
            self.assertLessEqual(len(text['stdout_excerpt']),4096);self.assertLessEqual(len(text['stderr_excerpt']),4096)
            self.assertTrue(text['stdout_excerpt_truncated']);self.assertFalse(text['stderr_excerpt_truncated'])
            self.assertEqual(text['stdout_retained_characters'],len(report['tests']['stdout']))
            self.assertEqual(text['stderr_retained_characters'],len(report['tests']['stderr']))
