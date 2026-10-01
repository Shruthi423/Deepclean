import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from deepclean.analysis import analyze, analyze_session
from deepclean.model import NormalizedSession, NormalizedTurn, ToolUse
from deepclean.turns import split_turns


def make_turns(specs):
    entries = []
    parent = None
    for i, (user, assistant, blocks) in enumerate(specs, start=1):
        uid = f"u{i}"
        entries.append({"type": "user", "uuid": uid, "parentUuid": parent, "message": {"content": user}})
        parent = uid
        aid = f"a{i}"
        content = blocks if blocks is not None else [{"type": "text", "text": assistant}]
        entries.append({"type": "assistant", "uuid": aid, "parentUuid": parent, "message": {"content": content}})
        parent = aid
    return entries, split_turns(entries)


class AnalysisTests(unittest.TestCase):
    def test_short_thanks_exchange_is_flagged(self):
        entries, turns = make_turns([("Thanks", "You're welcome.", None)])
        kinds = [f.kind for f in analyze(entries, turns)]
        self.assertIn("lightweight_acknowledgement", kinds)

    def test_yes_and_no_are_never_acknowledgement_candidates(self):
        entries, turns = make_turns([("yes", "Okay.", None), ("no", "Okay.", None)])
        kinds = [f.kind for f in analyze(entries, turns)]
        self.assertNotIn("lightweight_acknowledgement", kinds)

    def test_acknowledgement_with_tool_work_is_not_flagged(self):
        blocks = [{"type": "tool_use", "id": "t1", "name": "Write", "input": {}}]
        entries, turns = make_turns([("Okay", "", blocks)])
        kinds = [f.kind for f in analyze(entries, turns)]
        self.assertNotIn("lightweight_acknowledgement", kinds)

    def test_repeated_substantive_prompt_is_flagged(self):
        prompt = "Keep the settings panel on the right side of the canvas."
        entries, turns = make_turns([(prompt, "Done", None), (prompt, "Still there", None)])
        finding = next(f for f in analyze(entries, turns) if f.kind == "repeated_user_text")
        self.assertEqual(finding.turns, (1, 2))

    def test_near_duplicate_rewording_is_flagged_as_possible(self):
        entries, turns = make_turns([
            ("Keep the settings panel fixed on the right side of the canvas.", "Done", None),
            ("Keep the settings panel fixed on the right side of this canvas.", "Done", None),
        ])
        finding = next(f for f in analyze(entries, turns) if f.kind == "near_duplicate_user_text")
        self.assertEqual(finding.review_level, "possible")

    def test_correction_marker_is_flagged_as_possible(self):
        entries, turns = make_turns([
            ("I already said keep the settings panel on the right.", "Got it.", None)
        ])
        finding = next(f for f in analyze(entries, turns) if f.kind == "correction_marker")
        self.assertEqual(finding.review_level, "possible")

    def test_possible_contradiction_is_flagged(self):
        entries, turns = make_turns([
            ("Keep the settings panel on the right side.", "Done", None),
            ("Do not keep the settings panel on the right side.", "Okay", None),
        ])
        kinds = [f.kind for f in analyze(entries, turns)]
        self.assertIn("possible_contradiction", kinds)

    def test_superseded_decision_is_flagged(self):
        entries, turns = make_turns([
            ("Use Postgres for the project database.", "Done", None),
            ("Now use SQLite instead of Postgres for the project database.", "Done", None),
        ])
        kinds = [f.kind for f in analyze(entries, turns)]
        self.assertIn("superseded_decision", kinds)

    def test_stale_file_read_is_flagged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.txt"
            path.write_text("new", encoding="utf-8")
            os.utime(path, (200, 200))
            session = NormalizedSession(turns=(
                NormalizedTurn(
                    1, 0, 1, "Read spec", 2, "Read the spec", "",
                    tool_uses=(ToolUse("t1", "Read", {"file_path": "spec.txt"}),),
                    timestamp="1970-01-01T00:01:00+00:00",
                ),
            ))
            kinds = [f.kind for f in analyze_session(session, project_root=folder)]
            self.assertIn("stale_file_read", kinds)

    def test_large_tool_result_is_flagged(self):
        payload = "x" * 5000
        entries = [
            {"type": "user", "uuid": "u1", "parentUuid": None, "message": {"content": "Run it"}},
            {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]}},
            {"type": "user", "uuid": "r1", "parentUuid": "a1", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": payload}]}},
            {"type": "assistant", "uuid": "a2", "parentUuid": "r1", "message": {"content": [{"type": "text", "text": "done"}]}},
        ]
        turns = split_turns(entries)
        kinds = [f.kind for f in analyze(entries, turns)]
        self.assertIn("large_tool_output", kinds)


if __name__ == "__main__":
    unittest.main()
