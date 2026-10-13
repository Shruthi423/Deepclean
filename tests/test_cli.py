import unittest
from unittest.mock import patch

from deepclean.cli import main, parse_turn_selection, resume_command


class CliTests(unittest.TestCase):
    def test_unix_resume_command_quotes_folder(self):
        with patch("deepclean.cli.os.name", "posix"):
            command = resume_command("/tmp/My Project", "session-1")
        self.assertIn("claude --resume session-1", command)
        self.assertIn("My Project", command)

    def test_windows_resume_command_uses_cd_d(self):
        with patch("deepclean.cli.os.name", "nt"):
            command = resume_command(r"C:\\Users\\Shruthi\\My Project", "session-1")
        self.assertTrue(command.startswith('cd /d "'))
        self.assertIn("claude --resume session-1", command)

    def test_resume_without_folder(self):
        self.assertEqual(resume_command(None, "session-1"), "claude --resume session-1")

    def test_parse_turn_selection_supports_ranges(self):
        self.assertEqual(
            parse_turn_selection("2,4-6 9", set(range(1, 11))),
            [2, 4, 5, 6, 9],
        )

    def test_parse_turn_selection_rejects_missing_turns(self):
        with self.assertRaises(ValueError):
            parse_turn_selection("2-12", set(range(1, 6)))

    def test_parse_turn_selection_rejects_reverse_range(self):
        with self.assertRaises(ValueError):
            parse_turn_selection("8-3", set(range(1, 10)))

    def test_literal_claude_session_variable_fails_safely(self):
        self.assertEqual(main(["--session-id", "${CLAUDE_SESSION_ID}"]), 1)


if __name__ == "__main__":
    unittest.main()
