---
name: memcrumbs-review
description: Take the owner through what memcrumbs holds for their decision (new rules and gotchas, agent-written pages, suggestions, quarantined pages, the refresh budget) and record each approval in this session. Use when the owner types /memcrumbs-review or asks to review, and when the session header says something waits for the owner's review.
---
# Owner review, in this session

The owner decides; you never decide for them. Every approving command below is one that Claude Code asks the owner
about before it runs (memcrumbs wired that prompt), so their answer to the prompt is the approval. Run each one
exactly as written, with `memcrumbs` first and nothing before the subcommand: inside Claude Code memcrumbs refuses
any other form, because another form would run without the prompt.

**1. Rules, gotchas and agent-written pages** (`memcrumbs review` lists them):
- Show the owner every item in full in your reply: the id, the file and the whole line; for a page its title,
  summary and sources. Never shorten them: the owner approves what they read.
- Ask which to approve: all, some ids, or none. If they want a line reworded, edit it, then list again (its id
  changes with its text).
- Approve: `memcrumbs review --approve <id,id>` or `memcrumbs review --approve all`.
- If it says header lines were kept at an upgrade: `memcrumbs review --kept`, show them, then
  `memcrumbs review --approve kept`.
- What is not approved stays out of the header. Remove a line only when the owner says so.

**2. Suggestions**, when the owner wants to see them (listing costs tokens): `memcrumbs suggest`. Skill offers come
from work that repeated: a task flow or a pipeline (the same steps in many tasks), a command sequence, a status
check, a runbook read again and again.
- `memcrumbs suggest show <ID>` and show the owner the evidence and the change.
- A skill offer gets a readable name on apply: `--name <name>`. After the scaffold, write its steps from the
  evidence and the wiki, and keep facts in the wiki.
- On a yes: `memcrumbs suggest apply <ID>` (add `--outside-wiki` when it writes outside the wiki). On a no:
  `memcrumbs suggest dismiss <ID> --for 14d`, or `--never`. `memcrumbs suggest undo <ID>` reverses one.

**3. Quarantined pages** (listed by `memcrumbs review`): show the page (`memcrumbs page <name> --full`). On the
owner's yes: `memcrumbs quarantine --lift <name>`.

**4. The refresh budget**, when the owner wants pages refreshed: `memcrumbs plan` lists candidates with token
estimates. The owner picks: `memcrumbs plan --approve <page,page> --budget <tokens>`.

**Nothing waits and the wiki is new** (the header says rules and gotchas are empty): offer the first-run draft. On
the owner's yes, draft the lines as the memcrumbs skill's First run says (only what CLAUDE.md, the README and the
code support), then go back to step 1 with them.

In a worktree or a copy of the repo, add `-p NAME` right after `memcrumbs` (the name is in the memcrumbs block of
CLAUDE.md). If memcrumbs answers that the approval needs the owner, say why it gave: the ask rule is missing (the
owner runs `memcrumbs init` in the repo to add it), or the owner runs the command in their own terminal.
