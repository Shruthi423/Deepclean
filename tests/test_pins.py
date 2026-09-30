import tempfile
import unittest
from pathlib import Path

from deepclean.model import NormalizedSession, NormalizedTurn
from deepclean.pins import list_pins, pin, protected_turn_numbers, unpin


class PinTests(unittest.TestCase):
    def test_pin_list_protect_unpin(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "pins.json"
            project = "/tmp/project"
            self.assertTrue(pin(project, "Keep the panel on the right.", source_turn=2, path=path))
            self.assertFalse(pin(project, "Keep the panel on the right.", source_turn=2, path=path))
            self.assertEqual(len(list_pins(project, path=path)), 1)

            session = NormalizedSession(turns=(
                NormalizedTurn(1, 0, 1, "x", 1, "Something else", ""),
                NormalizedTurn(2, 1, 2, "x", 1, "Keep the panel on the right.", ""),
            ))
            self.assertEqual(protected_turn_numbers(session, project, path=path), {2})
            self.assertTrue(unpin(project, 1, path=path))
            self.assertEqual(list_pins(project, path=path), [])


if __name__ == "__main__":
    unittest.main()
