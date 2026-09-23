"""
Command line for Deep Clean (Tier 1).

Run after exiting Claude Code:
    python3 -m deepclean --latest
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from deepclean import session
from deepclean.cleaner import CleanError, clean
from deepclean.turns import split_turns

BATCH_SIZE = 3
DEFAULT_PROTECT = 2
HISTORY_FILE = Path.home() / ".deepclean" / "history.jsonl"


def ask_batch(batch):
    """Show up to 3 turns and return the numbers the user wants archived."""
    allowed = {t.number for t in batch}
    for t in batch:
        print(f"  {t.number:>3}. {t.preview}  ({t.message_count} messages)")
    while True:
        answer = input("  Archive which? Type numbers (e.g. 2 3), or press Enter to keep all: ").strip()
        if not answer:
            return []
        try:
            picked = {int(x) for x in answer.replace(",", " ").split()}
        except ValueError:
            print("  Please type numbers only.")
            continue
        if not picked <= allowed:
            print(f"  Please pick from: {' '.join(str(n) for n in sorted(allowed))}")
            continue
        return sorted(picked)


def record(original, cleaned_path, archived):
    """Keep a local log of every clean, so you can always find the original."""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "time": datetime.now(timezone.utc).isoformat(),
            "original": str(original),
            "cleaned": str(cleaned_path),
            "archived_turns": archived,
        }) + "\n")


def file_size(entries):
    return sum(len(json.dumps(e, ensure_ascii=False)) + 1 for e in entries)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="deepclean",
        description="Archive parts of a Claude Code session into a cleaned copy. The original is never changed.",
    )
    parser.add_argument("path", nargs="?", help="Path to a session .jsonl file")
    parser.add_argument("--latest", action="store_true", help="Use the most recent session")
    parser.add_argument("--protect", type=int, default=DEFAULT_PROTECT,
                        help=f"How many recent turns can never be archived (default {DEFAULT_PROTECT})")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen, write nothing")
    args = parser.parse_args(argv)

    if args.latest:
        path = session.find_latest()
        if path is None:
            print(f"No sessions found under {session.PROJECTS_DIR}")
            return 1
    elif args.path:
        path = Path(args.path).expanduser()
    else:
        parser.error("give a session file path, or use --latest")

    try:
        entries = session.load(path)
    except (OSError, session.SessionFormatError) as err:
        print(f"Could not read the session: {err}\nNothing was changed.")
        return 1

    turns = split_turns(entries)
    protect = max(1, args.protect)
    candidates = turns[:-protect] if len(turns) > protect else []

    print(f"\nDeep Clean  |  {path.name}")
    print(f"{len(turns)} turns. The last {min(protect, len(turns))} are protected.\n")
    if not candidates:
        print("Nothing to clean yet.")
        return 0

    try:
        chosen = []
        for i in range(0, len(candidates), BATCH_SIZE):
            chosen += ask_batch(candidates[i:i + BATCH_SIZE])
            print()

        if not chosen:
            print("Nothing archived. Nothing was changed.")
            return 0

        cleaned, new_id = clean(entries, turns, chosen, protect)
        before, after = file_size(entries), file_size(cleaned)
        print(f"Archiving turns: {' '.join(map(str, chosen))}")
        change = 100 * (after - before) / before
        direction = "smaller" if change < 0 else "larger"
        print(f"Session size: {before:,} -> {after:,} characters ({abs(change):.1f}% {direction})")
        if change >= 0:
            print("Note: the archived turns were shorter than the note that replaces them.")

        if args.dry_run:
            print("Dry run: nothing was written.")
            return 0

        if input("Write the cleaned copy? [y/N]: ").strip().lower() != "y":
            print("Cancelled. Nothing was changed.")
            return 0
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing was changed.")
        return 1
    except CleanError as err:
        print(f"Stopped: {err}\nNothing was changed.")
        return 1

    new_path = session.write_new(cleaned, path.parent, new_id)
    record(path, new_path, chosen)

    folder = session.working_folder(entries)
    print(f"\nDone. Your original session is untouched.")
    print("Continue in the cleaned copy with:")
    if folder:
        print(f'  cd "{folder}" && claude --resume {new_id}')
    else:
        print(f"  claude --resume {new_id}   (run this from the project's folder)")
    print("To undo, simply resume the original session instead.")
    return 0
