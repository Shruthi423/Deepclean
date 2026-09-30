import json
import tempfile
import unittest
from pathlib import Path

from deepclean import codex_session


def make_rollout():
    sid = "11111111-1111-1111-1111-111111111111"
    return [
        {
            "timestamp": "2026-09-29T12:00:00Z",
            "type": "session_meta",
            "payload": {"meta": {"id": sid, "session_id": sid, "cwd": "/tmp/deepclean-codex"}},
        },
        {
            "timestamp": "2026-09-29T12:00:01Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "Use Postgres for storage."}]},
        },
        {
            "timestamp": "2026-09-29T12:00:02Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "Okay."}]},
        },
        {
            "timestamp": "2026-09-29T12:01:01Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "Now use SQLite instead of Postgres."}]},
        },
        {
            "timestamp": "2026-09-29T12:01:02Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "Changed."}]},
        },
        {
            "timestamp": "2026-09-29T12:02:01Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "user",
                        "content": [{"type": "input_text", "text": "Continue."}]},
        },
        {
            "timestamp": "2026-09-29T12:02:02Z",
            "type": "response_item",
            "payload": {"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": "Done."}]},
        },
    ]


class CodexSessionTests(unittest.TestCase):
    def test_split_and_normalize(self):
        entries = make_rollout()
        codex_session.check_format(entries)
        turns = codex_session.split_turns(entries)
        self.assertEqual(len(turns), 3)
        normalized = codex_session.normalize(entries, turns)
        self.assertEqual(normalized.turns[1].user_text, "Now use SQLite instead of Postgres.")

    def test_clean_creates_new_id_and_gap_note(self):
        entries = make_rollout()
        turns = codex_session.split_turns(entries)
        cleaned, new_id = codex_session.clean(entries, turns, [1], protect_last=1)
        self.assertNotEqual(new_id, codex_session.session_id(entries))
        text = json.dumps(cleaned)
        self.assertNotIn("Use Postgres for storage.", text)
        self.assertIn("Deep Clean note", text)
        self.assertIn(new_id, text)

    def test_unknown_record_type_fails_closed(self):
        entries = make_rollout()
        entries.append({"type": "future_unknown_type", "payload": {}})
        with self.assertRaises(codex_session.CodexFormatError):
            codex_session.check_format(entries)

    def test_write_new_never_overwrites(self):
        with tempfile.TemporaryDirectory() as folder:
            entries = make_rollout()
            path = codex_session.write_new(entries, "abc", sessions_dir=folder)
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
