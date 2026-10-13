import json
import unittest

from deepclean import codex_session
from deepclean.cleaner import CleanError, check_tool_pairs, clean
from deepclean.turns import split_turns


def claude_entry(kind, uid, parent, text=None, blocks=None, **extra):
    content = text if text is not None else (blocks or [])
    return {
        "type": kind,
        "uuid": uid,
        "parentUuid": parent,
        "sessionId": "s1",
        "message": {"content": content},
        **extra,
    }


class ClaudeP0Tests(unittest.TestCase):
    def test_active_branch_ignores_abandoned_sibling(self):
        entries = [
            claude_entry("user", "u1", None, "Start"),
            claude_entry("assistant", "a1", "u1", "Okay"),
            claude_entry("user", "dead-u", "a1", "Use MySQL"),
            claude_entry("assistant", "dead-a", "dead-u", "Done"),
            claude_entry("user", "live-u", "a1", "Use Postgres"),
            claude_entry("assistant", "live-a", "live-u", "Done"),
        ]
        turns = split_turns(entries)
        self.assertEqual([t.preview for t in turns], ["Start", "Use Postgres"])
        self.assertNotIn(2, turns[1].indices)
        self.assertNotIn(3, turns[1].indices)

    def test_compaction_hides_old_history_and_protects_summary(self):
        summary = (
            "This session is being continued from a previous conversation that ran out of context. "
            "The conversation is summarized below: important state."
        )
        entries = [
            claude_entry("user", "u1", None, "Old request"),
            claude_entry("assistant", "a1", "u1", "Old answer"),
            claude_entry("user", "sum", "a1", summary),
            claude_entry("assistant", "a2", "sum", "Ready"),
            claude_entry("user", "u2", "a2", "Continue now"),
            claude_entry("assistant", "a3", "u2", "Done"),
        ]
        turns = split_turns(entries)
        self.assertEqual(len(turns), 2)
        self.assertTrue(turns[0].preview.startswith("This session is being continued"))
        self.assertFalse(turns[0].archivable)
        self.assertEqual(turns[0].protected_reason, "compact summary")
        self.assertEqual(turns[1].preview, "Continue now")
        with self.assertRaisesRegex(CleanError, "compact summary"):
            clean(entries, turns, [1], protect_last=1)

    def test_slash_command_is_not_a_turn(self):
        entries = [
            claude_entry("user", "u1", None, "First"),
            claude_entry("assistant", "a1", "u1", "Okay"),
            claude_entry("user", "cmd", "a1", "<command-name>/clear</command-name>"),
            claude_entry("user", "u2", "cmd", "Second"),
            claude_entry("assistant", "a2", "u2", "Okay"),
        ]
        turns = split_turns(entries)
        self.assertEqual([t.preview for t in turns], ["First", "Second"])

    def test_orphan_tool_call_error_names_turn_and_call(self):
        entries = [
            claude_entry("user", "u1", None, "Run it"),
            claude_entry(
                "assistant",
                "a1",
                "u1",
                blocks=[{"type": "tool_use", "id": "call-7", "name": "Bash"}],
            ),
            claude_entry("user", "u2", "a1", "Next"),
            claude_entry("assistant", "a2", "u2", "Okay"),
        ]
        with self.assertRaisesRegex(CleanError, "call-7.*turn 1"):
            check_tool_pairs(entries)


class CodexP0Tests(unittest.TestCase):
    def _msg(self, role, text):
        return {
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": role,
                "content": [{
                    "type": "input_text" if role == "user" else "output_text",
                    "text": text,
                }],
            },
        }

    def test_injected_instructions_are_not_turns_and_survive_clean(self):
        sid = "11111111-1111-1111-1111-111111111111"
        entries = [
            {"type": "session_meta", "payload": {"meta": {"id": sid, "cwd": "/tmp/project"}}},
            self._msg("user", "<user_instructions>Use AGENTS.md</user_instructions>"),
            self._msg("user", "<environment_context>cwd=/tmp/project</environment_context>"),
            self._msg("user", "First human prompt"),
            self._msg("assistant", "First answer"),
            self._msg("user", "Second human prompt"),
            self._msg("assistant", "Second answer"),
        ]
        codex_session.check_format(entries)
        turns = codex_session.split_turns(entries)
        self.assertEqual([t.preview for t in turns], ["First human prompt", "Second human prompt"])
        cleaned, _ = codex_session.clean(
            entries, turns, [1], protect_last=1, new_session_id="new-id"
        )
        raw = json.dumps(cleaned)
        self.assertIn("<user_instructions>", raw)
        self.assertIn("<environment_context>", raw)
        self.assertNotIn("First human prompt", raw)

    def test_codex_compaction_hides_pre_compaction_turns(self):
        sid = "11111111-1111-1111-1111-111111111111"
        entries = [
            {"type": "session_meta", "payload": {"meta": {"id": sid}}},
            self._msg("user", "Old prompt"),
            self._msg("assistant", "Old answer"),
            {"type": "compacted", "payload": {"summary": "old work"}},
            self._msg("user", "Current prompt"),
            self._msg("assistant", "Current answer"),
        ]
        turns = codex_session.split_turns(entries)
        self.assertEqual([t.preview for t in turns], ["Current prompt"])


if __name__ == "__main__":
    unittest.main()
