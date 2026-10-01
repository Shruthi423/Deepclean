---
description: Review the current Claude Code session with Deep Clean
allowed-tools: Bash(deepclean:*)
---

Run `deepclean --provider claude --latest --analyze-only`.

Show the user the Deep Clean findings without changing the active session.

If the user wants to actually clean the session, explain that Deep Clean will
not rewrite a live Claude Code history. Tell them to exit Claude Code, run
`deepclean --provider claude --latest`, choose what to archive, and then run
the resume command Deep Clean prints.

Never archive or delete context without the user's explicit selection.
