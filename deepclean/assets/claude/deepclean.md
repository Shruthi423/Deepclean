---
description: Review the current Claude Code session with Deep Clean
allowed-tools: Bash(deepclean:*)
---

Run `deepclean --provider claude --session-id "${CLAUDE_SESSION_ID}" --analyze-only`.

This command must target the exact active Claude Code session ID. Do not replace
it with `--latest` and do not inspect unrelated session files.

Show the user the Deep Clean findings without changing the active session.

If the user wants to actually clean the session, explain that Deep Clean will
not rewrite a live Claude Code history. Tell them to exit Claude Code, then run:

`deepclean --provider claude --session-id "${CLAUDE_SESSION_ID}"`

Choose what to archive, then run the resume command Deep Clean prints.

Never archive or delete context without the user's explicit selection.
