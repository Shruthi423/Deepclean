import unittest

from deepclean.analysis import analyze
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

    def test_correction_marker_is_flagged_as_possible(self):
        entries, turns = make_turns([
            ("I already said keep the settings panel on the right.", "Got it.", None)
        ])
        finding = next(f for f in analyze(entries, turns) if f.kind == "correction_marker")
        self.assertEqual(finding.review_level, "possible")

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
