import unittest

from deepclean.context_graph import build_context_graph
from deepclean.model import normalize
from deepclean.turns import split_turns


class ModelGraphTests(unittest.TestCase):
    def test_normalize_captures_tool_relationships(self):
        entries = [
            {"type": "user", "uuid": "u1", "parentUuid": None, "message": {"content": "Run tests"}},
            {"type": "assistant", "uuid": "a1", "parentUuid": "u1", "message": {"content": [
                {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"cmd": "pytest"}}
            ]}},
            {"type": "user", "uuid": "r1", "parentUuid": "a1", "message": {"content": [
                {"type": "tool_result", "tool_use_id": "t1", "content": "OK"}
            ]}},
            {"type": "assistant", "uuid": "a2", "parentUuid": "r1", "message": {"content": [
                {"type": "text", "text": "Tests passed."}
            ]}},
        ]

        turns = split_turns(entries)
        session = normalize(entries, turns)
        self.assertEqual(len(session.turns), 1)
        self.assertTrue(session.turns[0].has_tool_activity)
        self.assertEqual(session.turns[0].tool_uses[0].name, "Bash")
        self.assertEqual(session.turns[0].tool_results[0].tool_use_id, "t1")

        graph = build_context_graph(session)
        resolved = graph.edges_of_kind("resolved_by")
        self.assertEqual(len(resolved), 1)


if __name__ == "__main__":
    unittest.main()
