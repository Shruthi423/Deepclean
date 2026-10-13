# Deep Clean

**Human-controlled context cleanup for long Claude Code and Codex sessions.**

Deep Clean helps you review a long coding-agent session, see which parts may no longer be useful, and choose what to archive.

It is designed to be conservative:

- it reads session files locally
- it does not automatically delete context
- it protects recent, pinned, and structural context
- it writes a new cleaned session
- it leaves the original session untouched

> **Status: beta · v0.4.0**

---

## Quick start

### 1. Install from GitHub

Requirements:

- Python 3.10+
- Git
- Claude Code and/or Codex

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

### 2. Install the Claude Code command

```bash
deepclean --install-claude-command
```

Restart Claude Code.

Then, inside a Claude Code session:

```text
/deepclean
```

This analyzes the **exact active Claude session** and shows review signals.

It does not clean or rewrite the live session.

---

# What are you trying to do?

## Scenario 1: "I just want to see what Deep Clean finds"

Use analysis-only mode:

```bash
deepclean --provider claude --latest --analyze-only
```

Deep Clean may surface:

- repeated requirements
- near-duplicate re-explanations
- possible correction loops
- possible contradictions
- possible superseded decisions
- potentially stale file reads
- large tool outputs
- duplicate tool outputs
- lightweight acknowledgement exchanges
- conflicts with pinned source-of-truth requirements

These are **review signals**, not deletion decisions.

Nothing is changed.

---

## Scenario 2: "I want to preview a cleanup before writing anything"

Run:

```bash
deepclean --provider claude --latest --dry-run
```

Deep Clean will:

1. find the newest usable session in the current project
2. reconstruct the active conversation
3. protect recent, pinned, and structural context
4. show review signals
5. let you choose turns
6. show what the cleanup would look like

No new session is written.

This is the safest first cleanup workflow.

---

## Scenario 3: "I want to clean a Claude Code session"

Do not clean a Claude session while Claude Code is actively writing to it.

Exit the session, then run this from the same project folder:

```bash
deepclean --provider claude --latest
```

Deep Clean will:

1. load the current project's session
2. identify the active context
3. protect important context
4. show review signals
5. ask what you want to archive
6. validate tool-call/result integrity
7. create a **new cleaned session**
8. leave the original untouched
9. print a resume command

Example:

```text
claude --resume <new-session-id>
```

If you do not like the cleaned session, resume the original instead.

---

## Scenario 4: "My session is huge and I do not want to review three turns at a time"

You can select ranges directly:

```bash
deepclean --provider claude --latest --archive "2,4-12"
```

You can combine individual turns and ranges:

```text
2,4-12,18
```

Protected turns are still rejected even if they appear in your range.

You can also explicitly select every **flagged, unprotected** turn:

```bash
deepclean --provider claude --latest --archive-flagged
```

For a safer preview:

```bash
deepclean --provider claude --latest --archive-flagged --dry-run
```

Deep Clean never chooses this mode automatically. You must request it.

---

## Scenario 5: "I used /compact in Claude Code"

Deep Clean understands compaction boundaries.

After Claude compacts a long conversation, Deep Clean:

- ignores pre-compaction turns that are no longer part of the active context
- keeps the compact summary
- marks the compact summary as protected
- analyzes the context Claude is currently carrying

This prevents Deep Clean from claiming to "save context" by removing history Claude is no longer using anyway.

---

## Scenario 6: "I rewound or edited an earlier Claude message"

Claude sessions can contain multiple branches after rewinds or edits.

Deep Clean reconstructs the **active branch**.

For example, if a session contains:

```text
Old branch: Use MySQL
Current branch: Use Postgres
```

Deep Clean analyzes the active Postgres branch rather than mixing both histories together.

Abandoned branches remain in the original session file and are not treated as active context.

---

## Scenario 7: "There is a requirement Deep Clean must never archive"

Use a source-of-truth pin.

Pin a turn:

```bash
deepclean --provider claude --latest --pin 12
```

Or pin explicit guidance:

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

Pinned requirements:

- cannot be archived
- can be compared against later requirements
- can trigger a possible source-of-truth conflict warning

If the pins file is corrupt, Deep Clean stops safely instead of silently replacing it.

---

## Scenario 8: "I want to target one exact Claude session"

Use the session ID:

```bash
deepclean --provider claude --session-id <session-id> --analyze-only
```

Or provide the exact JSONL file:

```bash
deepclean /path/to/session.jsonl --provider claude --analyze-only
```

When you provide an exact session ID, Deep Clean never falls back to another session.

---

## Scenario 9: "I want to use /deepclean inside Claude Code"

Install once:

```bash
deepclean --install-claude-command
```

Restart Claude Code.

Then run:

```text
/deepclean
```

The command is designed to pass Claude Code's current `CLAUDE_SESSION_ID` to Deep Clean.

If Claude Code passes the literal text `${CLAUDE_SESSION_ID}` instead of expanding it, Deep Clean stops with a specific integration error.

It does **not** fall back to `--latest`.

The slash command analyzes the live session only. To create a cleaned session, exit Claude Code and run Deep Clean from the terminal.

---

## Scenario 10: "I use Codex instead of Claude Code"

Analyze:

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

Deep Clean writes a new Codex rollout and prints:

```text
codex resume <new-session-id>
```

Codex-specific protections include:

- injected `<user_instructions>`
- injected `<environment_context>`
- pre-compaction context
- project-scoped pins when a stable project `cwd` is available

If Deep Clean cannot determine a stable Codex project path, it refuses project-scoped pin operations rather than guessing.

> Codex rollout formats can change. Resume behavior should be smoke-tested against the Codex version installed on your machine.

---

## Scenario 11: "I already installed Deep Clean and want to update it"

From your cloned repository:

```bash
cd Deepclean
git checkout main
git pull origin main
python3 -m pip install .
```

Then verify:

```bash
deepclean --version
```

For development installs:

```bash
python3 -m pip install -e .
```

---

# Does Deep Clean consume LLM tokens?

## Reading the session

**No model/API tokens are required for Deep Clean itself to read the session file.**

Deep Clean is a local Python program. It parses the Claude Code or Codex JSONL files directly on your machine.

A longer session means:

- more local file data to read
- more turns to inspect
- potentially more findings

It does **not** mean Deep Clean sends the entire session through another LLM.

For example:

```text
20,000-token session
Deep Clean reads the local JSONL file
LLM/API tokens used by Deep Clean for that read: 0
```

The same is true for a much larger session.

## What about /deepclean inside Claude Code?

When you run:

```text
/deepclean
```

Claude Code sees the command instructions and the findings Deep Clean prints.

That can use some Claude context/tokens.

The important distinction is that **Deep Clean does not send the whole session back through Claude just to analyze it**.

Token usage from the slash-command workflow depends more on the amount of output/findings than on the raw size of the session file.

---

# How Deep Clean decides what is active

Deep Clean does not treat a session file as one flat transcript.

For Claude Code it accounts for:

- active conversation branches
- rewinds and edited branches
- compaction boundaries
- compact summaries
- slash-command/system pseudo-user records
- tool calls and tool results

For Codex it accounts for:

- compaction
- injected project/environment instructions
- tool activity
- project context when available

This matters because:

> **session file history is not always the same thing as active model context.**

---

# What Deep Clean protects

By default, Deep Clean protects:

- the most recent turns
- pinned source-of-truth turns
- compact summaries
- structural context
- Codex project/environment instructions

You can change how many recent turns are protected:

```bash
deepclean --provider claude --latest --protect 5
```

---

# Selecting turns interactively

Deep Clean presents eligible turns in small batches.

You can enter individual numbers:

```text
2 3
```

Ranges:

```text
2-3
```

Or:

```text
all
```

Press Enter to keep the entire batch.

Nothing is archived until you explicitly select it.

---

# Understanding the cleanup output

Example:

```text
Archiving turns: 4 5 6
Active turns: 27 -> 24 (3 archived)
Protected turns preserved: 4 (2 recent, 1 pinned, 1 structural)
Compact summary: protected
Session file size: 184,201 -> 157,992 characters (14.2% smaller; this is file size, not token savings)
```

The last line is about the serialized JSON session file.

It is **not** a claim about:

- tokens saved
- percentage of the context window saved
- model cost reduction

Deep Clean currently does not claim exact active-token savings because provider context accounting can differ from raw session-file size.

---

# Safety model

Deep Clean is intentionally conservative.

1. The original session is never overwritten.
2. Only explicitly selected turns are archived.
3. Recent turns are protected.
4. Pinned turns are protected.
5. Compact summaries and structural context are protected.
6. Abandoned Claude branches are not mixed into active-context analysis.
7. Codex project/environment instructions are protected.
8. Whole turns are removed so tool calls and results stay paired.
9. Tool-call/result integrity is checked before writing.
10. Cleaned copies receive fresh session IDs.
11. Unknown provider formats fail closed.
12. Corrupt pin storage fails closed.
13. `--latest` stays inside the current project.
14. `/deepclean` never guesses another session if the session ID integration fails.

Deep Clean runs with the filesystem permissions of the user who launches it. It is not an OS-level sandbox.

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

The VS Code extension is a lightweight wrapper around the CLI.

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
context graph + detectors
        |
        v
findings + protected context
        |
        v
explicit user review
        |
        v
provider-specific safe cleaner
        |
        v
verified new session
```

---

# Development

Install in editable mode:

```bash
python3 -m pip install -e .
```

Run tests:

```bash
python3 -m unittest discover -s tests -v
```

GitHub Actions currently tests:

- Ubuntu 24.04
- Python 3.10
- Python 3.11
- Python 3.12

---

# Current limitations

- Claude Code's local session schema is not officially documented.
- Codex rollout formats can change between releases.
- contradiction and supersession detection are conservative heuristics
- shell-based file-read detection intentionally handles only simple, recognizable reads
- file-size reduction is not a token/context estimate
- the VS Code integration is a command wrapper, not a graphical review panel
- Deep Clean does not rewrite live Claude Code or Codex sessions in place
- exact `CLAUDE_SESSION_ID` expansion depends on the installed Claude Code environment
- newly written Codex rollouts should be smoke-tested against the installed Codex version before production use
