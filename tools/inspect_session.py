#!/usr/bin/env python3
"""
Deep Clean - Phase 1 experiment: inspect a Claude Code session file.

READ-ONLY. This script never changes, moves, or deletes anything.
It prints the structure of one session file so we can learn its format
before writing the cleaner.

Usage:
    python3 inspect_session.py --latest          # newest session on this Mac
    python3 inspect_session.py path/to/file.jsonl

Only run it on a throwaway TEST session. The output shows short previews
of message text.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
PREVIEW_CHARS = 70


def short(value, n=8):
    """First n characters of an id, or '-' if missing."""
    return str(value)[:n] if value else "-"


def one_line(text, n=PREVIEW_CHARS):
    """Collapse whitespace and cut to n characters."""
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 3] + "..."


def describe_content(content):
    """Summarize message content, which may be a string or a list of blocks."""
    if content is None:
        return "(no content)"
    if isinstance(content, str):
        return one_line(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                parts.append(one_line(block, 30))
                continue
            kind = block.get("type", "?")
            if kind == "text":
                parts.append(f"text:{one_line(block.get('text', ''), 40)}")
            elif kind == "tool_use":
                parts.append(f"tool_use:{block.get('name', '?')}#{short(block.get('id'))}")
            elif kind == "tool_result":
                parts.append(f"tool_result#{short(block.get('tool_use_id'))}")
            else:
                parts.append(kind)
        return " | ".join(parts)
    return one_line(content)


def find_latest():
    """Return the most recently modified session file, or None."""
    if not PROJECTS_DIR.exists():
        return None
    files = [p for p in PROJECTS_DIR.glob("*/*.jsonl") if p.is_file()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def inspect(path):
    print(f"File: {path}")
    print(f"Size: {path.stat().st_size:,} bytes\n")

    key_counts = Counter()
    type_counts = Counter()
    session_ids = set()
    rows = []
    bad_lines = 0

    with path.open(encoding="utf-8") as f:
        for number, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                bad_lines += 1
                continue
            if not isinstance(entry, dict):
                bad_lines += 1
                continue

            key_counts.update(entry.keys())
            type_counts[entry.get("type", "?")] += 1
            if entry.get("sessionId"):
                session_ids.add(entry["sessionId"])

            message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
            rows.append({
                "line": number,
                "type": entry.get("type", "?"),
                "uuid": entry.get("uuid"),
                "parent": entry.get("parentUuid"),
                "side": entry.get("isSidechain"),
                "role": message.get("role", "-"),
                "content": describe_content(message.get("content"))
                if message else one_line(entry.get("summary", "")),
            })

    # 1. Every top-level field and how often it appears
    print("== Fields found (field: number of lines) ==")
    for key, count in sorted(key_counts.items()):
        print(f"  {key}: {count}")

    # 2. Line types
    print("\n== Line types ==")
    for kind, count in type_counts.most_common():
        print(f"  {kind}: {count}")

    # 3. One row per line
    print("\n== Lines ==")
    print(f"{'#':>4}  {'type':<12} {'uuid':<8} {'parent':<8} {'side':<5} {'role':<9} content")
    for r in rows:
        print(f"{r['line']:>4}  {r['type']:<12} {short(r['uuid']):<8} {short(r['parent']):<8} "
              f"{str(r['side'])[:5]:<5} {r['role']:<9} {r['content']}")

    # 4. Is it a simple chain? (each line's parent = the previous line's id)
    breaks = 0
    previous = None
    for r in rows:
        if r["uuid"] and previous and r["parent"] != previous:
            breaks += 1
        if r["uuid"]:
            previous = r["uuid"]

    print("\n== Summary ==")
    print(f"  Lines read: {len(rows)}")
    print(f"  Unreadable lines: {bad_lines}")
    print(f"  Session ids in file: {len(session_ids)} {[short(s) for s in session_ids]}")
    print(f"  Filename stem matches a session id: {path.stem in session_ids}")
    print(f"  Places where the parent is not the previous line: {breaks}")


def main():
    parser = argparse.ArgumentParser(description="Inspect a Claude Code session file (read-only).")
    parser.add_argument("path", nargs="?", help="Path to a .jsonl session file")
    parser.add_argument("--latest", action="store_true", help="Use the newest session file")
    args = parser.parse_args()

    if args.latest:
        path = find_latest()
        if path is None:
            sys.exit(f"No session files found under {PROJECTS_DIR}")
    elif args.path:
        path = Path(args.path).expanduser()
    else:
        parser.error("give a file path or use --latest")

    if not path.is_file():
        sys.exit(f"Not a file: {path}")
    inspect(path)


if __name__ == "__main__":
    main()
