"""Query expansion with a small, generic ops/dev thesaurus (aliases and query rewriting
come before any embeddings). A query word or phrase in a group also matches the group's other members.

Project-specific vocabulary goes in memcrumbs.toml:  [search] synonyms = [["kiln", "furnace"], ...]
or in a page's `aliases:` frontmatter. Groups are symmetric; a word in two groups gets both. A project whose
domain keeps built-in synonyms apart removes them with `thesaurus_remove = ["kill"]`, or drops the built-in
groups with `thesaurus = false`."""

GROUPS = """
delete, remove, drop, purge, erase, wipe
row, record, entry
rotate, renew, replace, regenerate, swap
secret, credential
deploy, release, rollout, ship, publish, push
rollback, roll back, revert, undo, downgrade, switch back, go back
restart, reboot, bounce, recycle
stop, kill, halt, terminate, shut down, shutdown
install, set up, setup, provision, configure
server, host, machine, box
folder, directory, dir
website, site, web app, webapp
database, db, datastore
backup, back up, snapshot
restore, recover, recovery
error, failure, fault, crash, outage, exception
broke, broken
schedule, cron, scheduled task, timer
certificate, cert, tls, ssl
config, configuration, settings
email, mail, e-mail
alert, alarm, notification
disk, drive, storage, volume
temperature, temp
password, passphrase, passcode
price, pricing, cost, fee
nightly, each night, every night, overnight
daily, every day, each day
hourly, every hour
weekly, every week
previous, prior, last good, last known good
upgrade, update, bump
save, store, persist, record, write, insert
sample, reading, measurement, datapoint
reservation, booking, appointment
customer, client
invoice, bill, billing
payment, charge, transaction
refund, reimburse
health check, healthcheck, probe, monitor
log, logging
duplicate, double, twice
timezone, time zone, tz
export, extract
connect, connection
slow, latency, lag
cache, caching, memoize
lock, locked, locking
permission, access, privilege
approve, approval, sign off, sign-off, consent
production, prod, live
staging, stage
environment, env
decompress, decode, unpack, inflate
mask, obfuscate, redact
"""


def _parse(text):
    table = {}
    for line in text.strip().splitlines():
        members = [m.strip().lower() for m in line.split(",") if m.strip()]
        for m in members:
            table.setdefault(m, set()).update(x for x in members if x != m)
    return table


TABLE = _parse(GROUPS)


def build(extra_groups=(), remove=(), builtin=True):
    """The thesaurus a project searches with: the built-in groups (unless `builtin` is false) minus the `remove`d
    words, plus its own [search] synonyms (a list of lists)."""
    if builtin and not extra_groups and not remove:
        return TABLE
    table = {k: set(v) for k, v in TABLE.items()} if builtin else {}
    drop = {str(w).strip().lower() for w in remove}
    for w in drop:
        table.pop(w, None)
    for k in list(table):
        table[k] -= drop
        if not table[k]:
            del table[k]
    for group in extra_groups:
        members = [str(m).strip().lower() for m in group if str(m).strip()]
        for m in members:
            table.setdefault(m, set()).update(x for x in members if x != m)
    return table


def for_project(project):
    cfg = project.cfg.get("search", {})
    return build(cfg.get("synonyms", []), cfg.get("thesaurus_remove", []), cfg.get("thesaurus", True))


def max_words(table):
    return max((len(k.split()) for k in table), default=1)
