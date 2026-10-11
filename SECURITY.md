# Security

## What memcrumbs promises, and what it does not

memcrumbs keeps secrets **out** of its index, its output and the files it writes. It is not a secrets manager
and never holds a secret on purpose.

**Redaction is best effort.** The filter (`memcrumbs/redact.py`) recognises the shapes in the redaction corpus
(`tests/corpus/redaction.json`): key=value pairs whose key ends in a secret word, CLI flags, auth headers,
credentials in URLs, XML values, bot tokens, private keys and long random strings. It cannot recognise a
secret that looks like ordinary text (a word-list passphrase under an unusual key, a short password in prose).
For values you know, add them to the project's deny list with `memcrumbs secret-add`: it stores only
`sha256:<length>:<hash>`, never the value.

What is enforced:

- Every text that is indexed, printed (text and `--json`) or written passes the filter. If the filter itself
  fails, the file is not indexed and the line is not printed (fail closed).
- `[security] never_index` (defaults: `.env*`, `*.pem`, `*.key`, `*.p12`, `id_rsa*`, `credentials*`,
  `secrets.*`, `.netrc`, `.pgpass`, `.npmrc`, `.pypirc`, `.ssh/`, `.aws/`, `*.tfstate` …) keeps whole files out
  of the index, `page`, `outline` and `sym --body`.
- memcrumbs writes only inside its write set: the project's wiki, its index folder, its `secrets.deny`, and the
  files `wire` names (`CLAUDE.md`, `AGENTS.md`, `.claude/settings.json`, the skill). Any other path raises.
- `memcrumbs scan PATH` checks a folder, a file, an sdist or a wheel; CI runs it on the repo and the built
  artifacts. Lines containing `memcrumbs:allow` are intentional test fixtures and are skipped.
- `check` flags instruction-like text in wiki pages (possible prompt injection); search hits from such pages are
  marked and `page` prints a warning. Treat flagged text as data.
- The owner's review (`review --approve`, `quarantine --lift`, `suggest apply` outside the wiki) asks for a
  typed code at a terminal and refuses when it sees an agent's environment (`CLAUDECODE`, `MEMCRUMBS_AGENT`).
  This is a speed bump that keeps an agent from approving its own lines by habit. It is **not** a security
  boundary: an agent that can run any shell command can get around it, for example by editing the review
  state file or faking a terminal. The boundary is your agent's permission settings.

memcrumbs makes no network calls, runs no service and installs no per-tool-call hooks. Its only hook is a
SessionStart command (`memcrumbs -p NAME status --hook`), which never fails the session.

## Reporting a vulnerability

Please report security problems privately through GitHub's "Report a vulnerability" (Security tab of the
repository) rather than in a public issue. Include the memcrumbs version, the command, and — for a redaction
miss — the *shape* of the leaked value with the value itself replaced. We aim to acknowledge reports within a
week.

## Supported versions

Before 1.0 only the latest release gets fixes. From 1.0, the latest minor release of the current major does.
