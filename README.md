# Deep Clean

**Human-controlled context cleanup for long Claude Code and Codex sessions.**

Deep Clean reviews an agent session, surfaces context that may be worth removing,
and lets the user decide what stays active.

It never overwrites the original session.

> **Status: beta (v0.4.0).** Deep Clean writes cleaned copies only and fails
> closed when it encounters session structure it does not understand.

## Why Deep Clean exists

Long coding-agent sessions accumulate stale decisions, repeated requirements,
tool output, abandoned branches, and context that is no longer useful.

Deep Clean does **not** decide what to delete for you.

It:

1. identifies review signals
2. protects structural and user-designated context
3. lets you explicitly choose turns to archive
4. writes a new cleaned session
5. leaves the original untouched

---

# What v0.4.0 adds

Deep Clean is now **session-structure aware**, not just a top-to-bottom JSONL cleaner.

### Claude Code

- follows the active conversation branch after rewinds or edits
- ignores abandoned branches during analysis and cleanup
- detects compaction boundaries
- protects compact summaries
- ignores slash-command/system pseudo-user lines as normal turns
- validates tool-call/result integrity on the active branch
- reports the exact turn and tool-call ID when a call is incomplete

### Codex

- protects injected project/environment instructions such as
  `<user_instructions>` and `<environment_context>`
- ignores pre-compaction turns
- recovers project `cwd` from stable session context when available
- refuses project-scoped pin operations when no stable project path exists

### Safer targeting

- `--latest` is scoped to the **current working project**
- Deep Clean does not silently jump to another project's newest session
- Claude `agent-*` / subagent-style transcripts are skipped
- invalid and empty session files are skipped

### Better detector behavior

- curly apostrophes such as `Don’t` are normalized
- punctuation such as `never.` no longer breaks contradiction checks
- ordinary uses of `again` no longer trigger correction-loop warnings
- generic `change` no longer implies a superseded decision
- stale-file signals are advisory rather than near-certain
- same-turn read/write activity avoids false stale-read warnings
- simple Codex shell reads such as `cat file` are recognized conservatively

### Better cleanup UX

- select ranges such as `2,4-12`
- explicitly archive all currently flagged, unprotected turns with
  `--archive-flagged`
- interactive batches accept ranges and `all`
- cleanup output separates:
  - active turns
  - protected turns
  - compact-summary protection
  - JSON file-size change

Deep Clean does **not** claim that JSON file-size reduction equals token or
model-context savings.

---

# Install

## Requirements

- Python 3.10 or newer
- Claude Code and/or Codex installed locally
- Git

Clone and install:

```bash
git clone https://github.com/Shruthi423/Deepclean.git
cd Deepclean
python3 -m pip install .
```

Windows:

```powershell
py -m pip install .
```

Verify:

```bash
deepclean --version
```

Expected:

```text
deepclean 0.4.0
```

For development:

```bash
python3 -m pip install -e .
```

---

# Claude Code

## Analyze the latest session in the current project

Run this from the same project directory:

```bash
deepclean --provider claude --latest --analyze-only
```

`--latest` means the newest **usable session for the current project**.
It no longer searches across unrelated projects and picks whichever file
changed most recently.

## Preview cleanup

```bash
deepclean --provider claude --latest --dry-run
```

## Clean

Do not clean a Claude session while Claude Code is actively writing to it.

Exit the session, then run:

```bash
deepclean --provider claude --latest
```

Deep Clean will:

1. load the current project's selected session
2. reconstruct active context
3. protect recent, pinned, and structural turns
4. show review signals
5. ask what you want to archive
6. validate the cleaned result
7. write a **new** session file with a new session ID
8. print the resume command

Example:

```text
claude --resume <new-session-id>
```

## Target an exact Claude session

By session ID:

```bash
deepclean --provider claude --session-id <session-id> --analyze-only
```

Or by exact path:

```bash
deepclean /path/to/session.jsonl --provider claude --analyze-only
```

Deep Clean never falls back to another session when an explicit ID cannot be
found.

---

# Claude Code `/deepclean`

Install the command:

```bash
deepclean --install-claude-command
```

Restart Claude Code, then run:

```text
/deepclean
```

The command is designed to pass Claude Code's current `CLAUDE_SESSION_ID` to
Deep Clean and analyze that exact session.

If Claude Code passes the literal text `${CLAUDE_SESSION_ID}` instead of
expanding it, Deep Clean stops safely and prints an integration-specific error.
It does not fall back to `--latest`.

`/deepclean` analyzes the live session only. To actually clean it, exit the
session and run the terminal command against the same session ID.

---

# Codex

Analyze the latest usable Codex rollout for the current project:

```bash
deepclean --provider codex --latest --analyze-only
```

Preview:

```bash
deepclean --provider codex --latest --dry-run
```

Clean:

```bash
deepclean --provider codex --latest
```

Deep Clean writes a new rollout and prints:

```text
codex resume <new-session-id>
```

The original rollout is never modified.

Codex session files are discovered under:

```text
~/.codex/sessions/YYYY/MM/DD/
```

or:

```text
$CODEX_HOME/sessions/
```

Deep Clean does not rely on a separate session-index entry to discover files.
Whether a particular Codex release can resume every newly written rollout ID is
still something to verify against that installed Codex version.

---

# Selecting turns

## Interactive review

Deep Clean shows eligible turns in small batches.

You can enter:

```text
2 3
```

or:

```text
2-3
```

or:

```text
all
```

Press Enter to keep the entire batch.

## Select ranges directly

For long sessions, skip dozens of prompts:

```bash
deepclean --provider claude --latest --archive "2,4-12"
```

Protected turns are still rejected even when included in an explicit range.

## Archive all flagged turns

If you explicitly want every **flagged, unprotected** turn selected:

```bash
deepclean --provider claude --latest --archive-flagged
```

This is opt-in. Deep Clean never invokes this behavior automatically.

Use `--dry-run` first if you want to preview the result:

```bash
deepclean --provider claude --latest --archive-flagged --dry-run
```

---

# Source-of-truth pins

Pins protect requirements that should remain authoritative for a project.

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

If `pins.json` is corrupt, Deep Clean now stops instead of silently replacing
it and losing pins.

---

# What Deep Clean can flag

Review signals include:

- repeated substantive requirements
- near-duplicate re-explanations
- possible correction loops
- possible conflicting requirements
- possible superseded decisions
- potentially stale file reads
- large tool outputs
- duplicate tool outputs
- lightweight acknowledgement exchanges
- conflicts with pinned source-of-truth requirements

These are **review signals**, not deletion decisions.

---

# Safety model

Deep Clean is intentionally conservative.

1. The original session is never overwritten.
2. Only explicitly selected turns are archived.
3. Recent turns are protected.
4. Pinned turns are protected.
5. Compact summaries and other structural context are protected.
6. Claude abandoned branches are ignored rather than flattened into active history.
7. Codex injected project/environment instructions are protected.
8. Whole turns are removed so tool calls and results stay together.
9. Tool-call/result integrity is checked before writing.
10. Cleaned copies receive fresh session IDs.
11. Unknown provider formats fail closed.
12. Corrupt pins storage fails closed.
13. `--latest` stays inside the current project.
14. `/deepclean` never falls back to guessing another session.

Deep Clean runs with the filesystem permissions of the user who launches it.
It is not an OS-level sandbox.

---

# Understanding the output

Example:

```text
Archiving turns: 4 5 6
Active turns: 27 -> 24 (3 archived)
Protected turns preserved: 4 (2 recent, 1 pinned, 1 structural)
Compact summary: protected
Session file size: 184,201 -> 157,992 characters (14.2% smaller; this is file size, not token savings)
```

The file-size line describes serialized session-file size only.

It should **not** be interpreted as:

- tokens saved
- context-window percentage saved
- model cost reduction

Those require provider/model-specific context accounting that Deep Clean does
not currently claim to provide.

---

# VS Code

Install:

```bash
deepclean --install-vscode
```

Restart VS Code and open the Command Palette.

Available commands:

- **Deep Clean: Analyze Current Project Claude Session**
- **Deep Clean: Clean Current Project Claude Session**
- **Deep Clean: Analyze Current Project Codex Session**
- **Deep Clean: Clean Current Project Codex Session**

The extension is a lightweight command wrapper around the CLI.

For the exact Claude Code session currently open, prefer `/deepclean`.

---

# CLI reference

| Option | What it does |
|---|---|
| `--provider claude` | Use Claude Code sessions |
| `--provider codex` | Use Codex rollout sessions |
| `--session-id ID` | Target one exact Claude Code session |
| `--latest` | Use the newest usable session in the current project |
| `--analyze-only` | Show findings and change nothing |
| `--dry-run` | Preview cleanup without writing |
| `--protect N` | Protect the N most recent turns |
| `--archive "2,4-12"` | Explicitly select turns/ranges |
| `--archive-flagged` | Explicitly select every flagged, unprotected turn |
| `--no-analysis` | Skip advisory analysis |
| `--pin TURN` | Protect a turn as project source of truth |
| `--pin-text TEXT` | Pin explicit project guidance |
| `--list-pins` | List project pins |
| `--unpin N` | Remove a pin |
| `--install-claude-command` | Install Claude Code `/deepclean` |
| `--install-vscode` | Install the VS Code command wrapper |

Show all options:

```bash
deepclean --help
```

---

# Architecture

```text
Claude JSONL / Codex rollout
            |
            v
     provider adapter
            |
            v
 active session structure
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
       explicit user review
            |
            v
 provider-specific safe cleaner
            |
            v
 verified NEW session
```

---

# Development

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions runs on:

- Ubuntu 24.04
- Python 3.10
- Python 3.11
- Python 3.12

---

# Current limitations

- Claude Code's local session schema is not officially documented.
- Codex rollout formats can change between releases.
- Contradiction and supersession detection remain conservative heuristics.
- Shell-based file-read detection intentionally handles only simple, recognizable reads.
- File-size reduction is not a token/context estimate.
- The VS Code integration is a command wrapper, not a graphical review panel.
- Deep Clean does not rewrite live Claude Code or Codex sessions in place.
- Exact `CLAUDE_SESSION_ID` expansion depends on the installed Claude Code integration environment; Deep Clean fails safely if it receives the literal variable instead.
- Resuming a newly written rollout should be smoke-tested against the installed Codex version before relying on that workflow in production.
