import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import research_protocol as protocol

class ResearchProtocolTests(unittest.TestCase):
    def test_freeze_detects_changed_prompt_or_data(self):
        with patch.object(protocol,'hashes',return_value={'tampered':'hash'}):
            with self.assertRaises(ValueError): protocol.verify_freeze()

    def test_failures_kept_and_blind_form_has_no_method_or_state_labels(self):
        async def failed(*args): raise ValueError('deliberate synthetic failure')
        with tempfile.TemporaryDirectory() as tmp, patch.object(protocol,'execute',failed), patch.object(protocol,'verify_freeze'):
            out=Path(tmp)/'result';asyncio.run(protocol.run(out))
            rows=json.loads((out/'rows.json').read_text())
            self.assertEqual(len(rows),27)
            self.assertTrue(all(r['status']=='mock_failed' for r in rows))
            header=(out/'blind-template.csv').read_text().splitlines()[0]
            self.assertNotIn('condition',header)
            self.assertNotIn('strategy_label',header)
            self.assertIn('final_output',header)
            self.assertIn('unscorable_reason',header)
