# Deep Clean

Long Claude Code sessions fill up with tangents and finished work, and answer
quality drops. Deep Clean lets you choose which parts of a session to archive,
then continues in a cleaned copy. Nothing is deleted: your original session is
never changed, so every clean can be undone.

**Status: Tier 1 (experiment).** It works on Claude Code's session files,
whose format is not officially documented. Try it on test sessions first.

## Requirements

- macOS or Linux, Python 3.10+
- Claude Code

No packages to install. No API key. Claude Code keeps using your normal plan.

## Use

1. In Claude Code, type `/exit` to end the session you want to clean.
2. From this folder, run:

   ```bash
   python3 -m deepclean --latest
   ```

3. Deep Clean shows your turns 3 at a time. Type the numbers you want to
   archive, or press Enter to keep them all.
4. Confirm, then run the `claude --resume ...` command it prints.

Options:

| Option | What it does |
|---|---|
| `--latest` | Use the most recent session |
| `path/to/session.jsonl` | Use a specific session |
| `--protect N` | Protect the last N turns (default 2) |
| `--dry-run` | Show what would happen, write nothing |

**Undo:** resume the original session. It is untouched. Every clean is logged
in `~/.deepclean/history.jsonl`.

## Rules

1. Only the turns you choose are archived.
2. The last turns are protected and can never be archived.
3. Whole turns are archived, so a tool call never loses its result.
4. A short note replaces archived turns so Claude knows something was there.
5. The cleaned copy is a new session. The original is never modified.
6. The copy is checked before it is written. If a check fails, nothing is written.
7. If the session file looks unfamiliar, Deep Clean stops and changes nothing.

## Development

```bash
python3 -m unittest discover tests        # run the tests
python3 tools/inspect_session.py --latest # look inside a session file (read-only)
```

## Project layout

```
deepclean/
  session.py   read, check, and safely write session files
  turns.py     split a session into turns
  cleaner.py   build the cleaned copy and enforce the rules
  cli.py       the interactive command
tests/         tests for every rule
tools/         helper scripts
```
