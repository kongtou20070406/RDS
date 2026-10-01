"""The retired bare-note API must never silently grant pruning authority."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from rds_research_note import load_research_note, review_research_note

class ResearchNoteRetirementTests(unittest.TestCase):
    def test_old_entry_points_require_the_transaction_ledger(self):
        for function, value in ((load_research_note, "missing/RESEARCH.md"),
                                (review_research_note, {"verified": True, "rejected": ["route"]})):
            with self.subTest(function=function):
                with self.assertRaisesRegex(ValueError, "checkpoint save --decision"):
                    function(value)

if __name__ == "__main__":
    unittest.main()
