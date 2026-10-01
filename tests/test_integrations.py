import tempfile
import unittest
from pathlib import Path

from deepclean.integrations import install_claude_command, install_vscode_extension


class IntegrationTests(unittest.TestCase):
    def test_install_claude_command(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "deepclean.md"
            result = install_claude_command(target)
            self.assertEqual(result, target)
            self.assertIn("deepclean --provider claude", target.read_text())

    def test_install_vscode_extension(self):
        with tempfile.TemporaryDirectory() as folder:
            target = install_vscode_extension(folder)
            self.assertTrue((target / "package.json").exists())
            self.assertTrue((target / "extension.js").exists())


if __name__ == "__main__":
    unittest.main()
