# 🧹 Deep Clean

**Human-controlled context cleanup for long Claude Code and Codex sessions.**

Deep Clean reviews a coding-agent session for context that may have lost value,
shows the evidence, and lets the user decide what stays in active context.
It never overwrites the original session.

> **Status: beta (v0.3.0).** Deep Clean writes cleaned copies only and fails
> closed when a session format is unfamiliar.

## What it detects

Deep Clean currently surfaces:

- repeated and highly similar requirements
- possible correction loops
- possible conflicting requirements
- possible superseded decisions
- stale file reads when a file changed after the agent read it
- large and duplicate tool output
- lightweight acknowledgement exchanges
- conflicts with user-pinned source-of-truth requirements

Higher-level findings are **review signals**, not automatic deletion decisions.

## Install

Requires Python 3.10+.

```bash
git clone https://github.com/Shruthi423/Deepclean.git
cd Deepclean
python -m pip install .
```

Verify:

```bash
deepclean --version
```

## Claude Code

Analyze the latest Claude Code session:

```bash
deepclean --provider claude --latest --analyze-only
```

Analyze and interactively clean:

```bash
deepclean --provider claude --latest
```

Install the Claude Code slash command:

```bash
deepclean --install-claude-command
```

Restart Claude Code, then use:

```text
/deepclean
```

The slash command analyzes the live session. Deep Clean does **not** rewrite a
session while Claude Code is actively using it. To clean, exit Claude Code,
run the CLI, then use the printed `claude --resume ...` command.

## Codex

Deep Clean supports current Codex rollout JSONL files under
`~/.codex/sessions/YYYY/MM/DD/` (or `$CODEX_HOME/sessions/`).

Analyze:

```bash
deepclean --provider codex --latest --analyze-only
```

Analyze and clean:

```bash
deepclean --provider codex --latest
```

After cleaning, Deep Clean prints:

```bash
codex resume <new-session-id>
```

The original rollout is never modified.

## VS Code

Install the lightweight local VS Code integration:

```bash
deepclean --install-vscode
```

Restart VS Code. In the Command Palette, search **Deep Clean**.

Available commands:

- Deep Clean: Analyze Latest Claude Session
- Deep Clean: Clean Latest Claude Session
- Deep Clean: Analyze Latest Codex Session
- Deep Clean: Clean Latest Codex Session

The extension runs Deep Clean in VS Code's integrated terminal, so cleanup
remains visible and interactive.

## Source-of-truth pins

Pin a session turn so it cannot be archived:

```bash
deepclean --provider claude --latest --pin 12
```

Or pin explicit project guidance:

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

Pinned requirements are treated as project source of truth and are protected
from cleanup. Deep Clean also flags later turns that appear to conflict with
them.

## Common options

| Command | What it does |
|---|---|
| `--provider claude` | Read Claude Code sessions |
| `--provider codex` | Read Codex rollout sessions |
| `--latest` | Use the provider's most recent session |
| `--analyze-only` | Show findings and change nothing |
| `--protect 5` | Protect the five most recent turns |
| `--dry-run` | Preview cleanup without writing a new session |
| `--no-analysis` | Use manual cleanup without review signals |
| `--pin TURN` | Pin that turn as project source of truth |
| `--pin-text TEXT` | Pin explicit project guidance |
| `--list-pins` | List project pins |
| `--unpin N` | Remove pin N |

## Safety rules

1. **The original session is never overwritten.**
2. **Only user-selected turns are archived.**
3. **Recent and pinned turns are protected.**
4. **Whole turns are removed so tool calls and results stay together.**
5. **Gap notes mark archived sections.**
6. **Cleaned copies get fresh session IDs.**
7. **Tool-call integrity is validated before a copy is written.**
8. **Unknown Claude/Codex session formats fail closed.**

## Architecture

```text
Claude JSONL / Codex rollout
            ↓
      provider adapter
            ↓
 normalized Deep Clean model
            ↓
       context graph
            ↓
 deterministic + advisory detectors
            ↓
 findings + source-of-truth pins
            ↓
         user review
            ↓
 provider-specific safe cleaner
            ↓
 verified NEW session
```

## Tests

```bash
python -m unittest discover -s tests -v
```

GitHub Actions runs the suite on Python 3.10, 3.11, and 3.12.

## Current limitations

- Claude Code's local session schema is not officially documented, so Deep
  Clean validates expected structure and stops on unfamiliar shapes.
- Codex support targets the current rollout record families
  (`session_meta`, `response_item`, `turn_context`, `event_msg`, etc.).
- Contradiction and supersession detection is intentionally conservative and
  advisory. Deep Clean does not decide which conflicting requirement is right.
- The VS Code integration is a lightweight Command Palette wrapper around the
  CLI, not a custom visual review panel yet.
- Deep Clean does not rewrite live sessions underneath Claude Code or Codex.
