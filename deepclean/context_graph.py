"""A small context graph for structural relationships inside a session.

The graph is deliberately conservative. It records relationships we can prove
from the session structure today and leaves semantic relationships, such as
"supersedes" or "contradicts", for future detectors to add only when justified.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from deepclean.model import NormalizedSession


@dataclass(frozen=True)
class ContextNode:
    id: str
    kind: str
    turn_number: int | None
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextEdge:
    source: str
    target: str
    kind: str


@dataclass
class ContextGraph:
    nodes: dict[str, ContextNode] = field(default_factory=dict)
    edges: list[ContextEdge] = field(default_factory=list)

    def add_node(self, node: ContextNode):
        self.nodes[node.id] = node

    def add_edge(self, source: str, target: str, kind: str):
        self.edges.append(ContextEdge(source=source, target=target, kind=kind))

    def edges_of_kind(self, kind: str):
        return [edge for edge in self.edges if edge.kind == kind]


def build_context_graph(session: NormalizedSession) -> ContextGraph:
    """Build structural relationships without making semantic guesses."""
    graph = ContextGraph()
    previous_turn_id = None
    tool_nodes = {}

    for turn in session.turns:
        turn_id = f"turn:{turn.number}"
        graph.add_node(
            ContextNode(
                id=turn_id,
                kind="turn",
                turn_number=turn.number,
                label=turn.preview,
                metadata={"char_count": turn.char_count},
            )
        )

        if previous_turn_id is not None:
            graph.add_edge(previous_turn_id, turn_id, "next")
        previous_turn_id = turn_id

        for index, tool in enumerate(turn.tool_uses, start=1):
            node_id = f"tool:{turn.number}:{index}:{tool.id}"
            tool_nodes[tool.id] = node_id
            graph.add_node(
                ContextNode(
                    id=node_id,
                    kind="tool_use",
                    turn_number=turn.number,
                    label=tool.name or "tool",
                    metadata={"tool_use_id": tool.id},
                )
            )
            graph.add_edge(turn_id, node_id, "contains")

        for index, result in enumerate(turn.tool_results, start=1):
            node_id = f"result:{turn.number}:{index}:{result.tool_use_id}"
            graph.add_node(
                ContextNode(
                    id=node_id,
                    kind="tool_result",
                    turn_number=turn.number,
                    label=f"{result.char_count} chars",
                    metadata={
                        "tool_use_id": result.tool_use_id,
                        "digest": result.digest,
                        "char_count": result.char_count,
                    },
                )
            )
            graph.add_edge(turn_id, node_id, "contains")
            call_node = tool_nodes.get(result.tool_use_id)
            if call_node:
                graph.add_edge(call_node, node_id, "resolved_by")

    return graph
