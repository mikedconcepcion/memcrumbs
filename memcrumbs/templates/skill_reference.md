---
name: dev-reference
description: The user's own development reference (their principles, philosophy and how they work), set up with memcrumbs. Use when planning work, choosing between approaches, reviewing or finishing a change, or when the user asks how they want things done.
---
# The user's development reference

The user keeps their development reference in `{folder}`: {files}. It is theirs, so follow it, and never rewrite
it on your own. Propose a change in one line and let the user decide.

- **Before planning or choosing an approach,** read it (start with `{main}`) and let it shape the plan.
- **When finishing a change,** check the work against it in one or two lines, and say where the work drifts from it.
- **When the user asks for a reflection,** run `memcrumbs reflect`. It prints counts only (commits, open items,
  tokens) across their projects; read them next to this reference and say where the numbers and the stated
  principles disagree, and what to do about it. It costs tokens to read, so run it only on the user's word.

In a project with a memcrumbs wiki, leave a one-line note when the reference changed what you did:
`memcrumbs log "<what it changed, one line>" --skill dev-reference`.
