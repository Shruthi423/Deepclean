import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from deepclean import codex_session, session
from deepclean.analysis import (
    detect_correction_markers,
    detect_possible_contradictions,
    detect_stale_file_reads,
    detect_superseded_decisions,
)
from deepclean.cli import main
from deepclean.model import NormalizedSession, NormalizedTurn, ToolUse
from deepclean.pins import PinsError, list_pins


def normalized(*texts):
    return NormalizedSession(
        turns=tuple(
            NormalizedTurn(
                number=i,
                start=i - 1,
                end=i,
                preview=text[:60],
                message_count=2,
                user_text=text,
                assistant_text="Okay.",
            )
            for i, text in enumerate(texts, start=1)
        )
    )


def claude_entries(cwd, first="First prompt", second="Second prompt"):
    return [
        {
            "type": "user",
            "uuid": "u1",
            "parentUuid": None,
            "cwd": str(cwd),
            "message": {"content": first},
        },
        {
            "type": "assistant",
            "uuid": "a1",
            "parentUuid": "u1",
            "message": {"content": "Okay"},
        },
        {
            "type": "user",
            "uuid": "u2",
            "parentUuid": "a1",
            "message": {"content": second},
        },
        {
            "type": "assistant",
            "uuid": "a2",
            "parentUuid": "u2",
            "message": {"content": "Done"},
        },
    ]


def write_jsonl(path, entries):
    path.write_text(
        "".join(json.dumps(entry) + "\n" for entry in entries),
        encoding="utf-8",
    )


class DetectorAccuracyTests(unittest.TestCase):
    def test_curly_apostrophe_and_punctuation_are_detected(self):
        findings = detect_possible_contradictions(
            normalized(
                "Keep the animation enabled for the loading state.",
                "Don’t keep the animation enabled. Never.",
            )
        )
        self.assertTrue(findings)

    def test_again_alone_is_not_a_correction_marker(self):
        findings = detect_correction_markers(
            normalized("Run the tests again after installing the package.")
        )
        self.assertEqual(findings, [])

    def test_generic_change_is_not_a_supersession_marker(self):
        findings = detect_superseded_decisions(
            normalized(
                "The settings panel is on the right side.",
                "Change the spacing around the settings panel.",
            )
        )
        self.assertEqual(findings, [])

    def test_explicit_instead_of_is_still_supersession(self):
        findings = detect_superseded_decisions(
            normalized(
                "Use Postgres for the project database.",
                "Use SQLite instead of Postgres for the project database.",
            )
        )
        self.assertTrue(findings)

    def test_same_turn_write_prevents_stale_read_false_positive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.txt"
            path.write_text("new", encoding="utf-8")
            os.utime(path, (200, 200))
            s = NormalizedSession(
                turns=(
                    NormalizedTurn(
                        1, 0, 1, "Read then write", 2, "Read then update spec", "",
                        tool_uses=(
                            ToolUse("r1", "Read", {"file_path": "spec.txt"}),
                            ToolUse("w1", "Write", {"file_path": "spec.txt", "content": "new"}),
                        ),
                        timestamp="1970-01-01T00:01:00+00:00",
                    ),
                )
            )
            self.assertEqual(detect_stale_file_reads(s, project_root=folder), [])

    def test_simple_codex_shell_cat_can_be_recognized_as_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "spec.txt"
            path.write_text("new", encoding="utf-8")
            os.utime(path, (200, 200))
            s = NormalizedSession(
                turns=(
                    NormalizedTurn(
                        1, 0, 1, "Read", 2, "Read spec", "",
                        tool_uses=(ToolUse("r1", "shell_command", {"command": "cat spec.txt"}),),
                        timestamp="1970-01-01T00:01:00+00:00",
                    ),
                )
            )
            findings = detect_stale_file_reads(s, project_root=folder)
            self.assertEqual(len(findings), 1)
            self.assertLess(findings[0].confidence, 0.95)


class PinsSafetyTests(unittest.TestCase):
    def test_corrupt_pins_fail_closed_and_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pins.json"
            original = "{ definitely not json"
            path.write_text(original, encoding="utf-8")
            with self.assertRaises(PinsError):
                list_pins("/tmp/project", path=path)
            self.assertEqual(path.read_text(encoding="utf-8"), original)


class LatestSelectionTests(unittest.TestCase):
    def test_claude_latest_stays_in_current_project(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            current = root / "current"
            other = root / "other"
            current.mkdir()
            other.mkdir()
            project_a = root / "workspace-a"
            project_b = root / "workspace-b"
            project_a.mkdir()
            project_b.mkdir()

            wanted = current / "wanted.jsonl"
            newer_other = other / "newer.jsonl"
            write_jsonl(wanted, claude_entries(project_a))
            write_jsonl(newer_other, claude_entries(project_b))
            os.utime(wanted, (100, 100))
            os.utime(newer_other, (200, 200))

            selected = session.find_latest(root, cwd=project_a)
            self.assertEqual(selected, wanted)

    def test_claude_latest_ignores_agent_transcript(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = root / "encoded-project"
            project.mkdir()
            workspace = root / "workspace"
            workspace.mkdir()

            wanted = project / "session.jsonl"
            agent = project / "agent-abc.jsonl"
            write_jsonl(wanted, claude_entries(workspace))
            write_jsonl(agent, claude_entries(workspace, "Agent prompt", "Agent next"))
            os.utime(wanted, (100, 100))
            os.utime(agent, (200, 200))

            self.assertEqual(session.find_latest(root, cwd=workspace), wanted)


class CodexProjectScopeTests(unittest.TestCase):
    def test_environment_context_recovers_project_cwd(self):
        entries = [
            {
                "type": "session_meta",
                "payload": {"meta": {"id": "11111111-1111-1111-1111-111111111111"}},
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{
                        "type": "input_text",
                        "text": "<environment_context><cwd>/tmp/my-project</cwd></environment_context>",
                    }],
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "Human prompt"}],
                },
            },
        ]
        self.assertEqual(codex_session.working_folder(entries), "/tmp/my-project")


class CliRegressionTests(unittest.TestCase):
    def test_unpin_zero_is_handled_as_unpin_not_clean(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "session.jsonl"
            write_jsonl(path, claude_entries(folder))
            with patch("deepclean.cli.unpin", return_value=False) as unpin_mock:
                result = main([str(path), "--unpin", "0"])
            self.assertEqual(result, 1)
            unpin_mock.assert_called_once()
            self.assertEqual(unpin_mock.call_args.args[1], 0)


if __name__ == "__main__":
    unittest.main()
