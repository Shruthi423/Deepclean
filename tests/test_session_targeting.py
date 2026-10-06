import tempfile
import unittest
from pathlib import Path

from deepclean import session


class SessionTargetingTests(unittest.TestCase):
    def test_find_by_id_returns_exact_matching_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "project-a").mkdir()
            (root / "project-b").mkdir()
            wanted = root / "project-a" / "abc-123.jsonl"
            other = root / "project-b" / "xyz-999.jsonl"
            wanted.write_text("{}\n", encoding="utf-8")
            other.write_text("{}\n", encoding="utf-8")

            self.assertEqual(session.find_by_id("abc-123", root), wanted)

    def test_find_by_id_does_not_fallback_to_latest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "project-a").mkdir()
            latest = root / "project-a" / "latest-session.jsonl"
            latest.write_text("{}\n", encoding="utf-8")

            self.assertIsNone(session.find_by_id("missing-session", root))

    def test_duplicate_session_ids_fail_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("project-a", "project-b"):
                project = root / name
                project.mkdir()
                (project / "same-id.jsonl").write_text("{}\n", encoding="utf-8")

            with self.assertRaises(session.SessionFormatError):
                session.find_by_id("same-id", root)

    def test_invalid_session_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(session.SessionFormatError):
                session.find_by_id("../other-session", folder)


if __name__ == "__main__":
    unittest.main()
