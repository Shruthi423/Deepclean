import unittest

from deepclean.cleaner import CleanError, check_tool_pairs


class ToolEndSafetyTests(unittest.TestCase):
    def test_unanswered_call_at_end_is_caught(self):
        entries = [
            {"type": "assistant", "uuid": "a", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "x", "input": {}}
            ]}},
        ]
        with self.assertRaises(CleanError):
            check_tool_pairs(entries)


if __name__ == "__main__":
    unittest.main()
