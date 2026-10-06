# Deep Clean

**Human-controlled context cleanup for long Claude Code and Codex sessions.**

Deep Clean reviews a coding-agent session for context that may have lost value,
shows the evidence, and lets the user decide what stays active.

It never overwrites the original session.

> **Status: beta (v0.3.1).** Deep Clean writes cleaned copies only and stops
> when it encounters a session format it does not understand.

## What Deep Clean does

Deep Clean can surface:

- repeated or highly similar requirements
- possible correction loops
- possible conflicting requirements
- possible superseded decisions
- stale file reads
- large or duplicate tool output
- lightweight acknowledgement exchanges
- conflicts with user-pinned source-of-truth requirements

These are **review signals**, not automatic deletion decisions.

The user always decides what gets archived.

---

# Install

## 1. Requirements

- Python 3.10 or newer
- Claude Code and/or Codex installed locally
- Git

Check Python:

```bash
python3 --version
```

## 2. Clone Deep Clean

```bash
git clone https://github.com/Shruthi423/Deepclean.git
cd Deepclean
```

## 3. Install

macOS / Linux:

```bash
python3 -m pip install .
```

Windows:

```powershell
py -m pip install .
```

## 4. Verify

```bash
deepclean --version
```

Expected:

```text
deepclean 0.3.1
```

If the `deepclean` command is not available, try:

```bash
python3 -m deepclean --version
```

---

# Use Deep Clean from the command line

You do **not** need the Claude slash command or VS Code extension to use Deep Clean.

## Analyze a Claude Code session

Analyze the most recently modified Claude session:

```bash
deepclean --provider claude --latest --analyze-only
```

This only reads and reports findings. Nothing is changed.

## Preview cleanup

```bash
deepclean --provider claude --latest --dry-run
```

Deep Clean shows eligible turns and lets you choose what you would archive,
but it writes nothing.

## Clean a Claude session

Do not clean a Claude session while Claude Code is actively writing to it.

Exit that Claude session, then run:

```bash
deepclean --provider claude --latest
```

Deep Clean will:

1. load one session
2. show review signals
3. protect recent and pinned turns
4. ask which turns you want to archive
5. ask for confirmation
6. write a **new cleaned session**
7. leave the original untouched
8. print the command to resume the cleaned copy

Example:

```text
claude --resume <new-session-id>
```

## Target one exact Claude session

By session ID:

```bash
deepclean --provider claude --session-id <session-id> --analyze-only
```

Or by exact JSONL path:

```bash
deepclean /path/to/session.jsonl --provider claude --analyze-only
```

Deep Clean does not fall back to another session if an explicit session ID
cannot be found.

---

# Optional: Claude Code `/deepclean`

Install the Claude Code command:

```bash
deepclean --install-claude-command
```

Restart Claude Code.

Inside Claude Code:

```text
/deepclean
```

The slash command uses Claude Code's current session ID, so it analyzes the
**exact active session** rather than guessing based on which file changed most
recently.

`/deepclean` only analyzes the live session. It does not rewrite live Claude
history.

To actually clean it, exit Claude Code and run Deep Clean from the terminal
against that session.

---

# Codex

Analyze the latest Codex rollout:

```bash
deepclean --provider codex --latest --analyze-only
```

Preview cleanup:

```bash
deepclean --provider codex --latest --dry-run
```

Clean:

```bash
deepclean --provider codex --latest
```

Deep Clean writes a new Codex rollout and prints:

```text
codex resume <new-session-id>
```

The original rollout is never modified.

Codex sessions are read from:

```text
~/.codex/sessions/YYYY/MM/DD/
```

or:

```text
$CODEX_HOME/sessions/
```

---

# Optional: VS Code commands

Install the local VS Code integration:

```bash
deepclean --install-vscode
```

Restart VS Code and open the Command Palette.

Available commands:

- **Deep Clean: Analyze Latest Claude Session**
- **Deep Clean: Clean Latest Claude Session**
- **Deep Clean: Analyze Latest Codex Session**
- **Deep Clean: Clean Latest Codex Session**

The VS Code integration is a lightweight wrapper around the CLI.

For the exact Claude session currently open, use Claude Code's `/deepclean`
command instead.

---

# Source-of-truth pins

Pins protect important requirements from cleanup.

Pin a turn:

```bash
deepclean --provider claude --latest --pin 12
```

Pin explicit guidance:

```bash
deepclean --provider claude --latest --pin-text "The settings panel stays on the right."
```

List pins:

```bash
deepclean --provider claude --latest --list-pins
```

Remove pin 2:

```bash
deepclean --provider claude --latest --unpin 2
```

Pinned requirements cannot be archived. Deep Clean can also flag later turns
that appear to conflict with them.

---

# CLI reference

| Option | What it does |
|---|---|
| `--provider claude` | Use Claude Code sessions |
| `--provider codex` | Use Codex rollout sessions |
| `--session-id ID` | Use one exact Claude Code session ID |
| `--latest` | Explicitly use the provider's most recently modified session |
| `--analyze-only` | Show findings and change nothing |
| `--dry-run` | Preview cleanup without writing a new session |
| `--protect 5` | Protect the five most recent turns |
| `--no-analysis` | Skip review signals and manually review turns |
| `--pin TURN` | Protect a turn as project source of truth |
| `--pin-text TEXT` | Pin explicit project guidance |
| `--list-pins` | List project pins |
| `--unpin N` | Remove a pin |
| `--install-claude-command` | Install Claude Code `/deepclean` |
| `--install-vscode` | Install the lightweight VS Code integration |

Show all options:

```bash
deepclean --help
```

---

# Safety model

1. **The original session is never overwritten.**
2. **Only user-selected turns are archived.**
3. **Recent and pinned turns are protected.**
4. **Whole turns are removed so tool calls and results stay together.**
5. **Gap notes mark archived sections.**
6. **Cleaned copies receive fresh session IDs.**
7. **Tool-call integrity is checked before a cleaned copy is written.**
8. **Unknown Claude/Codex formats fail closed.**
9. **`/deepclean` targets the exact active Claude session.**
10. **Other sessions are read only when the user explicitly selects them or uses `--latest`.**

Deep Clean is not an OS-level sandbox. The CLI runs with the filesystem
permissions of the user who launches it.

---

# Architecture

```text
Claude JSONL / Codex rollout
            |
            v
      provider adapter
            |
            v
 normalized Deep Clean model
            |
            v
       context graph
            |
            v
 deterministic + advisory detectors
            |
            v
 findings + source-of-truth pins
            |
            v
         user review
            |
            v
 provider-specific safe cleaner
            |
            v
 verified NEW session
```

---

# Development

Install the repository in editable mode:

```bash
python3 -m pip install -e .
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions runs the test suite on Python 3.10, 3.11, and 3.12.

---

# Current limitations

- Claude Code's local session schema is not officially documented. Deep Clean
  validates expected structure and stops on unfamiliar shapes.
- Codex support targets current rollout record families.
- Contradiction and supersession detection is conservative and advisory.
- The VS Code integration is a Command Palette wrapper, not a graphical review
  panel.
- Deep Clean does not rewrite live sessions underneath Claude Code or Codex.
- Deep Clean does not currently provide an OS-level filesystem sandbox.
