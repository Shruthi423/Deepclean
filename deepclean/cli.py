"""Command line for Deep Clean."""

from __future__ import annotations

import argparse
import json
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path

from deepclean import __version__, session
from deepclean import codex_session
from deepclean.analysis import analyze_session
from deepclean.cleaner import CleanError, clean as clean_claude
from deepclean.integrations import install_claude_command, install_vscode_extension
from deepclean.model import normalize as normalize_claude
from deepclean.pins import list_pins, pin, protected_turn_numbers, unpin
from deepclean.turns import split_turns as split_claude_turns

BATCH_SIZE = 3
DEFAULT_PROTECT = 2
HISTORY_FILE = Path.home() / ".deepclean" / "history.jsonl"

FINDING_LABELS = {
    "lightweight_acknowledgement": "light exchange",
    "repeated_user_text": "repeated requirement",
    "near_duplicate_user_text": "possible re-explanation",
    "correction_marker": "possible correction loop",
    "possible_contradiction": "possible contradiction",
    "superseded_decision": "possible superseded decision",
    "stale_file_read": "stale file read",
    "source_of_truth_conflict": "pinned requirement conflict",
    "large_tool_output": "large tool output",
    "duplicate_tool_output": "duplicate tool output",
}


def _signals_by_turn(findings):
    signals = {}
    for finding in findings:
        label = FINDING_LABELS.get(finding.kind, finding.kind.replace("_", " "))
        for number in finding.turns:
            signals.setdefault(number, []).append(label)
    return signals


def show_findings(findings, protected_numbers):
    print("Context review")
    if not findings:
        print("  No review signals found.\n")
        return

    strong = [f for f in findings if f.review_level == "strong"]
    possible = [f for f in findings if f.review_level == "possible"]
    print(f"  {len(findings)} review signal(s) found. Nothing is selected automatically.")

    for label, group in (("Strong signals", strong), ("Possible signals", possible)):
        if not group:
            continue
        print(f"\n  {label}")
        for finding in group:
            joined = ", ".join(str(n) for n in finding.turns)
            noun = "Turn" if len(finding.turns) == 1 else "Turns"
            protected = "  [protected]" if all(n in protected_numbers for n in finding.turns) else ""
            print(f"  - {noun} {joined}: {finding.title}.{protected}")
            print(f"    {finding.detail}")
    print()


def ask_batch(batch, signals=None):
    signals = signals or {}
    allowed = {t.number for t in batch}
    for t in batch:
        labels = signals.get(t.number, [])
        suffix = f"  [{' / '.join(labels)}]" if labels else ""
        print(f"  {t.number:>3}. {t.preview}  ({t.message_count} messages){suffix}")
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


def record(original, cleaned_path, archived, provider):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "time": datetime.now(timezone.utc).isoformat(),
            "provider": provider,
            "original": str(original),
            "cleaned": str(cleaned_path),
            "archived_turns": archived,
        }) + "\n")


def file_size(entries):
    return sum(len(json.dumps(e, ensure_ascii=False)) + 1 for e in entries)


def resume_command(folder, session_id):
    """Claude Code resume command, kept public for compatibility/tests."""
    if not folder:
        return f"claude --resume {session_id}"
    if os.name == "nt":
        return f'cd /d "{folder}" && claude --resume {session_id}'
    return f"cd {shlex.quote(str(folder))} && claude --resume {session_id}"


def _provider_api(provider):
    if provider == "codex":
        return {
            "load": codex_session.load,
            "find_latest": codex_session.find_latest,
            "split_turns": codex_session.split_turns,
            "normalize": codex_session.normalize,
            "working_folder": codex_session.working_folder,
            "format_error": codex_session.CodexFormatError,
        }

    return {
        "load": session.load,
        "find_latest": session.find_latest,
        "split_turns": split_claude_turns,
        "normalize": normalize_claude,
        "working_folder": session.working_folder,
        "format_error": session.SessionFormatError,
    }


def _project_key(folder, path):
    return str(Path(folder).expanduser()) if folder else str(Path(path).parent)


def _show_pins(project):
    items = list_pins(project)
    if not items:
        print("No pinned source-of-truth requirements for this project.")
        return
    print("Pinned source-of-truth requirements:")
    for index, item in enumerate(items, start=1):
        source = item.get("source_turn")
        suffix = f"  (turn {source})" if source else ""
        print(f"  {index}. {item.get('text', '')}{suffix}")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="deepclean",
        description="Human-reviewed context cleanup for Claude Code and Codex sessions.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("path", nargs="?", help="Path to a provider session .jsonl file")
    parser.add_argument("--provider", choices=("claude", "codex"), default="claude",
                        help="Session provider (default: claude)")
    parser.add_argument("--latest", action="store_true", help="Use the provider's most recent session")
    parser.add_argument("--protect", type=int, default=DEFAULT_PROTECT,
                        help=f"How many recent turns can never be archived (default {DEFAULT_PROTECT})")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen, write nothing")
    parser.add_argument("--analyze-only", action="store_true",
                        help="Show context review signals and exit")
    parser.add_argument("--no-analysis", action="store_true",
                        help="Skip advisory context analysis")
    parser.add_argument("--pin", type=int, metavar="TURN",
                        help="Pin a turn's user message as project source of truth")
    parser.add_argument("--pin-text", metavar="TEXT",
                        help="Pin explicit text as project source of truth")
    parser.add_argument("--list-pins", action="store_true",
                        help="List project source-of-truth pins and exit")
    parser.add_argument("--unpin", type=int, metavar="N",
                        help="Remove source-of-truth pin N and exit")
    parser.add_argument("--install-claude-command", action="store_true",
                        help="Install /deepclean for Claude Code")
    parser.add_argument("--install-vscode", action="store_true",
                        help="Install the Deep Clean VS Code extension locally")
    args = parser.parse_args(argv)

    if args.install_claude_command:
        target = install_claude_command()
        print(f"Installed Claude Code command: {target}")
        print("Restart Claude Code, then use /deepclean.")
        return 0

    if args.install_vscode:
        target = install_vscode_extension()
        print(f"Installed VS Code extension: {target}")
        print("Restart VS Code, then search 'Deep Clean' in the Command Palette.")
        return 0

    if args.analyze_only and args.no_analysis:
        parser.error("--analyze-only cannot be combined with --no-analysis")

    api = _provider_api(args.provider)

    if args.latest:
        path = api["find_latest"]()
        if path is None:
            print(f"No {args.provider} sessions found.")
            return 1
    elif args.path:
        path = Path(args.path).expanduser()
    else:
        parser.error("give a session file path, use --latest, or install an integration")

    try:
        entries = api["load"](path)
    except (OSError, api["format_error"]) as err:
        print(f"Could not read the session: {err}\nNothing was changed.")
        return 1

    turns = api["split_turns"](entries)
    normalized = api["normalize"](entries, turns)
    folder = api["working_folder"](entries)
    project = _project_key(folder, path)

    if args.list_pins:
        _show_pins(project)
        return 0

    if args.unpin:
        if unpin(project, args.unpin):
            print(f"Removed pin {args.unpin}.")
            return 0
        print(f"Pin {args.unpin} does not exist.")
        return 1

    if args.pin_text:
        created = pin(project, args.pin_text)
        print("Pinned." if created else "That source-of-truth requirement is already pinned.")
        return 0

    if args.pin is not None:
        try:
            turn = normalized.turn(args.pin)
        except KeyError:
            print(f"Turn {args.pin} does not exist.")
            return 1
        created = pin(project, turn.user_text, source_turn=turn.number)
        print("Pinned." if created else "That turn is already pinned.")
        return 0

    protect = max(1, args.protect)
    recent_protected = {t.number for t in turns[-protect:]}
    pinned_protected = protected_turn_numbers(normalized, project)
    protected_numbers = recent_protected | pinned_protected

    candidates = [t for t in turns if t.number not in protected_numbers]

    print(f"\nDeep Clean ({args.provider})  |  {Path(path).name}")
    print(
        f"{len(turns)} turns. {len(protected_numbers)} protected "
        f"({len(recent_protected)} recent, {len(pinned_protected)} pinned).\n"
    )

    pin_items = list_pins(project)
    pinned_texts = [item.get("text", "") for item in pin_items]

    findings = []
    if not args.no_analysis:
        findings = analyze_session(
            normalized,
            project_root=folder,
            pinned_texts=pinned_texts,
        )
        show_findings(findings, protected_numbers)

    if args.analyze_only:
        print("Analysis only: nothing was changed.")
        return 0

    if not candidates:
        print("Nothing to clean yet.")
        return 0

    signals = _signals_by_turn(findings)

    try:
        chosen = []
        for i in range(0, len(candidates), BATCH_SIZE):
            chosen += ask_batch(candidates[i:i + BATCH_SIZE], signals)
            print()

        if not chosen:
            print("Nothing archived. Nothing was changed.")
            return 0

        if any(number in protected_numbers for number in chosen):
            raise CleanError("A protected or pinned turn was selected.")

        if args.provider == "codex":
            cleaned, new_id = codex_session.clean(
                entries,
                turns,
                chosen,
                protect,
                protected_numbers=pinned_protected,
            )
        else:
            cleaned, new_id = clean_claude(entries, turns, chosen, protect)

        before, after = file_size(entries), file_size(cleaned)
        print(f"Archiving turns: {' '.join(map(str, chosen))}")
        change = 100 * (after - before) / before
        direction = "smaller" if change < 0 else "larger"
        print(f"Session size: {before:,} -> {after:,} characters ({abs(change):.1f}% {direction})")

        if args.dry_run:
            print("Dry run: nothing was written.")
            return 0

        if input("Write the cleaned copy? [y/N]: ").strip().lower() != "y":
            print("Cancelled. Nothing was changed.")
            return 0

    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. Nothing was changed.")
        return 1
    except (CleanError, codex_session.CodexFormatError) as err:
        print(f"Stopped: {err}\nNothing was changed.")
        return 1

    if args.provider == "codex":
        new_path = codex_session.write_new(cleaned, new_id)
        command = codex_session.resume_command(new_id)
    else:
        new_path = session.write_new(cleaned, Path(path).parent, new_id)
        command = resume_command(folder, new_id)

    record(path, new_path, chosen, args.provider)

    print("\nDone. Your original session is untouched.")
    print("Continue in the cleaned copy with:")
    print(f"  {command}")
    if args.provider == "claude" and not folder:
        print("  (run this from the project's folder)")
    print("To undo, simply resume the original session instead.")
    return 0
