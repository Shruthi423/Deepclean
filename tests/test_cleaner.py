"""
Tests for Deep Clean's rules. Run with:
    python3 -m unittest discover tests
"""

import json
import tempfile
import unittest
from pathlib import Path

from deepclean import session
from deepclean.cleaner import CleanError, check_tool_pairs, clean
from deepclean.turns import split_turns

SID = "11111111-1111-1111-1111-111111111111"


def make_session():
    """A small fake session shaped like the test chat in the README."""
    lines = []
    parent = None

    def add(kind, content, **extra):
        nonlocal parent
        line_id = f"id-{len(lines) + 1}"
        entry = {
            "type": kind, "uuid": line_id, "parentUuid": parent, "sessionId": SID,
            "cwd": "/tmp/deepclean-test",
            "message": {"role": kind, "content": content},
        }
        entry.update(extra)
        lines.append(entry)
        parent = line_id

    # Turn 1: the rule
    add("user", "Every answer must end with PINEAPPLE.")
    add("assistant", [{"type": "text", "text": "Understood. PINEAPPLE"}])
    # Turn 2: tool use
    add("user", "Create notes.txt")
    add("assistant", [{"type": "tool_use", "id": "toolu_1", "name": "Write", "input": {}}])
    add("user", [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}])
    add("assistant", [{"type": "text", "text": "Created. PINEAPPLE"}])
    # Turns 3 and 4: the tangent
    add("user", "Unrelated: good serif font?")
    add("assistant", [{"type": "text", "text": "Try a serif. PINEAPPLE"}])
    add("user", [{"type": "text", "text": "And a sans-serif?"}])
    add("assistant", [{"type": "text", "text": "Try a sans. PINEAPPLE"}])
    # Turn 5: back to work, with tool use
    add("user", "Add a second line")
    add("assistant", [{"type": "tool_use", "id": "toolu_2", "name": "Edit", "input": {}}])
    add("user", [{"type": "tool_result", "tool_use_id": "toolu_2", "content": "ok"}])
    add("assistant", [{"type": "text", "text": "Done. PINEAPPLE"}])
    # Turn 6: the check
    add("user", "What rule did I give you?")
    add("assistant", [{"type": "text", "text": "End with PINEAPPLE. PINEAPPLE"}])
    return lines


class TurnTests(unittest.TestCase):
    def test_turns_are_what_the_user_typed(self):
        turns = split_turns(make_session())
        self.assertEqual(len(turns), 6)
        self.assertTrue(turns[2].preview.startswith("Unrelated"))

    def test_tool_results_do_not_start_a_turn(self):
        turns = split_turns(make_session())
        self.assertEqual(turns[1].message_count, 4)  # prompt, call, result, reply


class CleanTests(unittest.TestCase):
    def setUp(self):
        self.entries = make_session()
        self.turns = split_turns(self.entries)

    def test_archived_turns_are_removed(self):
        cleaned, _ = clean(self.entries, self.turns, [3, 4], protect_last=2)
        text = json.dumps(cleaned)
        self.assertNotIn("Try a serif", text)
        self.assertNotIn("Try a sans", text)
        self.assertIn("Create notes.txt", text)

    def test_stub_is_added_to_the_next_kept_turn(self):
        cleaned, _ = clean(self.entries, self.turns, [3, 4], protect_last=2)
        next_prompt = next(e for e in cleaned if "Add a second line" in json.dumps(e))
        first_block = next_prompt["message"]["content"]
        self.assertIn("Deep Clean note", json.dumps(first_block))
        self.assertIn("2 earlier exchanges", json.dumps(first_block))

    def test_chain_stays_connected(self):
        cleaned, _ = clean(self.entries, self.turns, [3, 4], protect_last=2)
        ids = {e["uuid"] for e in cleaned}
        for e in cleaned[1:]:
            self.assertIn(e["parentUuid"], ids)

    def test_copy_gets_new_session_id_and_line_ids(self):
        cleaned, new_id = clean(self.entries, self.turns, [3], protect_last=2)
        self.assertNotEqual(new_id, SID)
        self.assertTrue(all(e["sessionId"] == new_id for e in cleaned))
        old_ids = {e["uuid"] for e in self.entries}
        self.assertFalse(old_ids & {e["uuid"] for e in cleaned})

    def test_original_is_not_modified(self):
        before = json.dumps(self.entries)
        clean(self.entries, self.turns, [3, 4], protect_last=2)
        self.assertEqual(before, json.dumps(self.entries))

    def test_protected_turns_cannot_be_archived(self):
        with self.assertRaises(CleanError):
            clean(self.entries, self.turns, [5], protect_last=2)

    def test_unknown_turn_is_rejected(self):
        with self.assertRaises(CleanError):
            clean(self.entries, self.turns, [99], protect_last=2)

    def test_last_turn_is_always_protected(self):
        with self.assertRaises(CleanError):
            clean(self.entries, self.turns, [1], protect_last=0)

    def test_tool_call_and_result_leave_together(self):
        cleaned, _ = clean(self.entries, self.turns, [2], protect_last=2)
        text = json.dumps(cleaned)
        self.assertNotIn("toolu_1", text)
        self.assertIn("toolu_2", text)

    def test_separate_runs_get_separate_stubs(self):
        cleaned, _ = clean(self.entries, self.turns, [1, 3], protect_last=2)
        self.assertEqual(json.dumps(cleaned).count("Deep Clean note"), 2)


class ToolPairTests(unittest.TestCase):
    def test_orphan_result_is_caught(self):
        entries = [
            {"type": "user", "uuid": "a", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "missing", "content": "x"}]}},
        ]
        with self.assertRaises(CleanError):
            check_tool_pairs(entries)

    def test_unanswered_call_before_next_prompt_is_caught(self):
        entries = [
            {"type": "assistant", "uuid": "a", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "x", "input": {}}]}},
            {"type": "user", "uuid": "b", "message": {"content": "next question"}},
        ]
        with self.assertRaises(CleanError):
            check_tool_pairs(entries)


class FileTests(unittest.TestCase):
    def test_write_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            session.write_new([{"a": 1}], folder, "same")
            with self.assertRaises(FileExistsError):
                session.write_new([{"a": 2}], folder, "same")

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = session.write_new(make_session(), folder, "abc")
            self.assertEqual(len(session.load(path)), len(make_session()))

    def test_unexpected_format_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.jsonl"
            path.write_text(json.dumps({"type": "user", "text": "no uuid"}) + "\n")
            with self.assertRaises(session.SessionFormatError):
                session.load(path)


if __name__ == "__main__":
    unittest.main()
