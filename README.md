# 🧹 Deep Clean

**Remove the clutter from a long Claude Code session, without losing anything.**

When a Claude Code session runs for a long time, it fills up with side
conversations, old drafts, and finished tasks. Claude has to reread all of it
with every message, and answers can get less focused.

Deep Clean first reviews the session for conservative context signals, then lets you decide which parts to set aside. It can flag repeated requirements, lightweight exchanges, large or duplicate tool output, and explicit correction-loop language. You then continue in a cleaned copy of the session. Your original session is never changed, so you can always go back.

> **Status: beta.** It works and is covered by automated tests, but it relies on
> Claude Code's session files, whose format is not officially documented.
> Your original sessions are never modified, so trying it is safe.

---

## How it works, in one minute

1. You end a Claude Code session as usual.
2. You run Deep Clean. It analyzes the session and surfaces **review signals**. Strong signals are mechanical, such as duplicate tool output. Possible signals are weaker clues, such as correction-loop language.
3. Deep Clean then shows the session as numbered **turns**. A turn is one message you sent, plus everything Claude did in response.
4. You choose which turns, if any, to set aside. Deep Clean never selects them for you.
5. Deep Clean makes a **cleaned copy** without those turns. In their place it leaves a short note, so Claude knows something was there.
6. You continue working in the cleaned copy.

🔒 Nothing is deleted. Your original session stays exactly as it was.

---

## Before you start

You need:

- macOS, Linux, or Windows
- **Claude Code**, installed and working
- **Python 3.10 or newer.** To check, open Terminal and run `python3 --version`

You do **not** need an API key, an account, or any extra software.
Claude Code keeps using your normal Claude plan.

---

## Install

Open a terminal and run:

```bash
git clone https://github.com/Shruthi423/Deepclean.git
cd Deepclean
python -m pip install .
```

After that, you can run Deep Clean with the `deepclean` command.

---

## Use it

### Step 1: Find your session ID

When you leave Claude Code with `/exit`, it prints a line like this:

```
Resume this session with:
claude --resume d1c4ccea-1993-4415-b48e-26201e0e6df4
```

The long code at the end is your **session ID**. Copy it.

### Step 2: Run Deep Clean on that session

The simplest option is to analyze the most recent Claude Code session:

```bash
deepclean --latest
```

For a specific session, pass its JSONL file path:

```bash
deepclean PATH_TO_SESSION.jsonl
```

To inspect findings without cleaning anything:

```bash
deepclean PATH_TO_SESSION.jsonl --analyze-only
```

### Step 3: Choose what to set aside

Deep Clean shows your turns three at a time:

```
Deep Clean  |  d1c4ccea-1993-4415-b48e-26201e0e6df4.jsonl
7 turns. The last 2 are protected.

    1. Remember this rule for this session: every answer must en...  (2 messages)
    2. Create a file called notes.txt with the line "hello deep ...  (4 messages)
    3. what's a good serif font for a portfolio?  (2 messages)
  Archive which? Type numbers (e.g. 2 3), or press Enter to keep all:
```

- Type the numbers of turns you don't need, then press **Enter**.
- To keep everything in a group, just press **Enter**.
- Your most recent turns are **protected** and are never shown here.

When you're done, Deep Clean asks you to confirm. Type `y` and press **Enter**.

### Step 4: Continue in the cleaned copy

Deep Clean prints a command like this:

```
cd "/Users/you/my-project" && claude --resume a0876963-770f-4ea5-bccb-d9e1f046c148
```

Copy and run it. Claude Code opens the cleaned session, and you carry on
working.

### Changed your mind?

Resume your **original** session instead, using the session ID from Step 1.
It is untouched. Deep Clean also keeps a record of every clean in
`~/.deepclean/history.jsonl`, so you can always find the original.

---

## Options

| Command | What it does |
|---|---|
| `deepclean PATH` | Analyze and clean the session file at PATH |
| `deepclean --latest` | Analyze and clean the most recently used session. ⚠️ **Careful:** this may pick a different session than you expect |
| `--protect 5` | Protect the last 5 turns instead of the default 2 |
| `--dry-run` | Show what would happen without writing anything |
| `--analyze-only` | Show context review signals and exit without asking what to archive |
| `--no-analysis` | Skip the advisory context analysis and use the original manual flow |
| `--version` | Print the installed Deep Clean version |

---

## 🛡️ Safety rules

Deep Clean follows these rules every time:

1. **Only what you choose is set aside.** Nothing is removed automatically.
2. **Your most recent turns are protected** and can never be set aside.
3. **Whole turns only.** If Claude used a tool, the request and its result
   always stay together, so the session never breaks.
4. **A note marks every gap,** so Claude knows earlier conversation existed.
5. **Your original session is never changed.** The cleaned version is always
   a new copy.
6. **Every copy is checked before it's saved.** If something looks wrong,
   nothing is written.
7. **If a session file looks unfamiliar,** Deep Clean stops and changes
   nothing.

---

## ⚠️ Known limitations

- **Claude Code only.** It does not work with claude.ai or other chat apps.
- **You run it after exiting** Claude Code, not from inside a session (yet).
- **The note appears inside your next message** in the session history, so
  you may see text you didn't type.
- **The size shown is the file size,** which includes Claude Code's own
  records. The real saving in what Claude reads is usually larger.
- **Claude Code updates** could change the session format. If Deep Clean
  suddenly stops working after an update, that is the likely reason.

---

## What's inside the code

Deep Clean is plain Python with no outside packages. Each file has one job:

| File | What it does |
|---|---|
| `deepclean/session.py` | Reads session files, checks they look right, and saves the cleaned copy safely (never overwriting anything) |
| `deepclean/turns.py` | Splits a session into turns: each message you sent plus Claude's response |
| `deepclean/model.py` | Converts Claude session data into Deep Clean's internal, vendor-neutral session model |
| `deepclean/context_graph.py` | Builds structural relationships between turns, tool calls, and tool results |
| `deepclean/findings.py` | Defines review findings and confidence levels |
| `deepclean/analysis.py` | Runs conservative, non-destructive context detectors |
| `deepclean/cleaner.py` | Builds the cleaned copy: removes only user-approved turns, adds notes, and enforces safety rules |
| `deepclean/cli.py` | Shows review signals, asks for user decisions, and prints the resume command |
| `tests/test_cleaner.py` | Automated tests, one or more for each safety rule |
| `tools/inspect_session.py` | A read-only helper that shows what's inside a session file, for debugging |

### Run the tests

```bash
python -m unittest discover -s tests -v
```

You should see `OK` at the end.

---

## Current analysis

Deep Clean currently uses deterministic, conservative detectors. It does **not** use an LLM to decide what should be removed.

It can currently flag:

- exact repeated substantive user requirements
- highly similar reworded requirements as a possible re-explanation signal
- lightweight acknowledgement exchanges with no tool activity
- large tool-result payloads
- duplicate non-trivial tool results
- explicit correction-loop phrases such as `I already said`

These are review signals only. The user remains the authority on what gets archived.

## Coming next

- richer semantic re-explanation detection beyond textual similarity
- superseded and conflicting decisions
- source-of-truth pinning and a project-state manifest
- stale-file and file-version detection
- semantic context-graph relationships such as `supersedes`, `contradicts`, and `resolves`
- Codex session adapter
- run `/deepclean` from inside Claude Code
- restore set-aside turns from inside a session
- measure what the model actually reads, not just file size
