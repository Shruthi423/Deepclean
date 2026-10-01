import unittest
from unittest.mock import patch

from deepclean.cli import resume_command


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


if __name__ == "__main__":
    unittest.main()
