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
