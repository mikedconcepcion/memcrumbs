"""SQLite FTS5 index: documents (wiki sections, docs, code symbols, legacy notes) + a symbol table.

The index is a disposable cache: it carries a schema version and is rebuilt on a mismatch; a broken file
raises IndexBroken so the caller can rebuild it or answer from the files. Writers take short, explicit
transactions; readers never wait for them (WAL)."""
import contextlib
import sqlite3
import time
from pathlib import Path

from memcrumbs import cites, rank
from memcrumbs.query import fts_query, split_filters, term_pairs, wants_code, wants_procedure  # fts_query is re-exported: store.fts_query
from memcrumbs.synonyms import TABLE

SCHEMA_VERSION = 7
ROWID_BITS = 20                       # up to ~1M docs per file
_TABLES = (
    "CREATE TABLE IF NOT EXISTS files(id INTEGER PRIMARY KEY, path TEXT UNIQUE, source TEXT, stamp TEXT)",
    "CREATE VIRTUAL TABLE IF NOT EXISTS docs USING fts5(kind UNINDEXED, path UNINDEXED, loc UNINDEXED, "
    "verified UNINDEXED, status UNINDEXED, flags UNINDEXED, title, section, body, tags, "
    "tokenize = \"porter unicode61 tokenchars '_'\")",
    "CREATE TABLE IF NOT EXISTS symbols(path TEXT, name TEXT, qual TEXT, kind TEXT, line INT, end INT, sig TEXT, doc TEXT)",
    "CREATE INDEX IF NOT EXISTS sym_name ON symbols(name COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS sym_path ON symbols(path)",
    "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)",
    "CREATE TABLE IF NOT EXISTS cites(target TEXT, token TEXT, path TEXT, loc INT, kind TEXT, status TEXT, title TEXT, "
    "section TEXT)",
    "CREATE INDEX IF NOT EXISTS cite_target ON cites(target)",
    "CREATE INDEX IF NOT EXISTS cite_path ON cites(path)",
    "CREATE TABLE IF NOT EXISTS pagefresh(path TEXT PRIMARY KEY, changed REAL, names TEXT)",
)
_BM25 = "bm25(docs, 0, 0, 0, 0, 0, 0, 6.0, 3.0, 1.0, 2.0)"      # title 6, section 3, body 1, tags 2
WIKI_KINDS = ("wiki", "runbook", "decision", "incident", "journal", "fact")
# ranking: hand-curated wiki first, raw legacy notes last; superseded crumbs below current ones
BOOST = {"fact": 1.8, "wiki": 1.8, "runbook": 1.8, "decision": 1.8, "incident": 1.8, "journal": 1.0, "doc": 1.15,
         "research": 1.15, "memory": 1.0, "code": 1.0, "bug": 0.9, "legacy": 0.75, "log": 0.5}
STATUS_BOOST = {"superseded": 0.35, "draft": 0.8}
COVERAGE_FLOOR = 0.5             # score x (floor + IDF-weighted share of query terms matched): 0.5 .. 1.5
CODE_INTENT_BOOST = 2.5          # code hits when the question asks for code ("which function …")
PROCEDURE_BOOST = 1.5            # runbook hits when the question asks for steps ("how do I …")
SAME_FILE_DECAY = 0.5            # each further hit from one file scores half the one before
CANDIDATES = 300


LISTING_SCAN = 2000               # filter-only listings look at this many matching docs


def _first_line(text):
    """The telling line of a listed part: a table group's first data row, else its first non-empty line."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) >= 3 and lines[0].startswith("|") and set(lines[1]) <= set("|-: "):
        return lines[2]
    return lines[0] if lines else ""


def peek(path, flag="unreviewed"):
    """For the session header: (docs, symbols, files flagged `flag`), read without migrating, writing or waiting
    more than 100 ms. 'version' when the index is of another schema (it rebuilds on the next lookup), None when it
    is missing, busy or broken. The header must never block a session on the index."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        db = sqlite3.connect(str(p), timeout=0.1, isolation_level=None)
    except sqlite3.Error:
        return None
    try:
        db.execute("PRAGMA busy_timeout = 100")
        if db.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
            return "version"
        docs = db.execute("SELECT count(*) FROM docs").fetchone()[0]
        syms = db.execute("SELECT count(*) FROM symbols").fetchone()[0]
        flagged = db.execute("SELECT count(DISTINCT path) FROM docs WHERE loc = 1 AND (' ' || flags || ' ') LIKE ?",
                             ("% " + flag + " %",)).fetchone()[0]
        return docs, syms, flagged
    except sqlite3.Error:
        return None
    finally:
        db.close()


class IndexBroken(Exception):
    """The index file is unreadable (corrupt, not a database)."""


class Locked(Exception):
    """Another process holds the write lock longer than we are willing to wait."""


def expand_kinds(kinds):
    out = []
    for k in kinds or ():
        out += WIKI_KINDS if k == "wiki" else (k,)
    return out or None


class Store:
    def __init__(self, path, synonyms=TABLE):
        self.path = Path(path)
        self.synonyms = synonyms                                    # query expansion table (synonyms.build)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.db = sqlite3.connect(str(path), timeout=30, isolation_level=None)   # explicit transactions
            self.db.execute("PRAGMA busy_timeout = 30000")
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                self._migrate()
        except sqlite3.DatabaseError as e:
            with contextlib.suppress(Exception):
                self.db.close()                         # Windows cannot delete a file a connection holds
            if isinstance(e, sqlite3.OperationalError) and "locked" in str(e):
                raise Locked(str(e)) from None
            raise IndexBroken("%s: %s" % (type(e).__name__, e)) from None

    def _migrate(self):
        """Create the schema, or drop and recreate it when the version differs (the index is a cache)."""
        with contextlib.suppress(sqlite3.OperationalError):
            self.db.execute("PRAGMA journal_mode=WAL")
        with self.writer(wait=30):
            if self.db.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION:
                return                                          # another process migrated it meanwhile
            for (name,) in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE "
                                           "'docs_%' AND name NOT LIKE 'sqlite_%'").fetchall():
                self.db.execute('DROP TABLE IF EXISTS "%s"' % name)
            for sql in _TABLES:
                self.db.execute(sql)
            self.db.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)

    def close(self):
        self.db.close()

    # ---- writes
    @contextlib.contextmanager
    def writer(self, wait=0.25):
        """One write transaction. Waits at most `wait` seconds for the lock, then raises Locked."""
        self.db.execute("PRAGMA busy_timeout = %d" % int(wait * 1000))
        try:
            self.db.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as e:
            raise Locked(str(e)) from None
        finally:
            self.db.execute("PRAGMA busy_timeout = 30000")
        try:
            yield self
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        self.db.execute("COMMIT")

    def known(self, source):
        return dict(self.db.execute("SELECT path, stamp FROM files WHERE source=?", (source,)))

    def by_source(self):
        return dict(self.db.execute("SELECT source, count(*) FROM files GROUP BY source"))

    def replace(self, path, source, stamp, docs, syms):
        """Each file owns the doc rowids [id << ROWID_BITS, (id + 1) << ROWID_BITS): a file's docs are deleted by
        rowid range (an FTS5 `WHERE path=` would scan the whole table, making a full index quadratic)."""
        self.drop(path)
        fid = self.db.execute("INSERT INTO files(path, source, stamp) VALUES(?,?,?)", (path, source, str(stamp))).lastrowid
        base = fid << ROWID_BITS
        self.db.executemany("INSERT INTO docs(rowid, kind, path, loc, verified, status, flags, title, section, body, tags) "
                            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                            [(base + i, d.kind, d.path, d.loc, d.verified, d.status, d.flags, d.title, d.section, d.body,
                              d.tags) for i, d in enumerate(docs[:(1 << ROWID_BITS) - 1])])
        self.db.executemany("INSERT INTO symbols VALUES(?,?,?,?,?,?,?,?)",
                            [(path, s["name"], s["qual"], s["kind"], s["line"], s["end"], s["sig"], s["doc"]) for s in syms])
        self.db.executemany("INSERT INTO cites VALUES(?,?,?,?,?,?,?,?)", cites.rows(path, docs))

    def reset(self):
        """Empty every indexed table by dropping and recreating it (inside the caller's write transaction), for
        `index --full`. Deleting row by row costs an FTS5 table as much again as indexing: each deleted row is
        tokenized once more, which made a warm full rebuild on a Windows CI runner slower than the first build
        (40 s against 25 s)."""
        for name in ("docs", "symbols", "cites", "files", "pagefresh"):
            self.db.execute('DROP TABLE IF EXISTS "%s"' % name)
        for sql in _TABLES:
            self.db.execute(sql)

    def drop(self, path):
        r = self.db.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        if r:
            self.db.execute("DELETE FROM docs WHERE rowid >= ? AND rowid < ?", (r[0] << ROWID_BITS, (r[0] + 1) << ROWID_BITS))
        self.db.execute("DELETE FROM symbols WHERE path=?", (path,))
        self.db.execute("DELETE FROM cites WHERE path=?", (path,))
        self.db.execute("DELETE FROM files WHERE path=?", (path,))

    def set_fresh(self, rows):
        """Replace the stored source-change flags: [(page key, last source change, names)]."""
        self.db.execute("DELETE FROM pagefresh")
        self.db.executemany("INSERT OR REPLACE INTO pagefresh VALUES(?,?,?)", rows)

    def attach_fresh(self, hits):
        """Each hit whose page has sources changed since it was verified gets `src_changed` (a time)."""
        paths = sorted({h["path"] for h in hits})
        if not paths:
            return hits
        got = dict(self.db.execute("SELECT path, changed FROM pagefresh WHERE path IN (%s)" % ",".join("?" * len(paths)),
                                   paths))
        for h in hits:
            if h["path"] in got:
                h["src_changed"] = got[h["path"]]
        return hits

    def set_meta(self, k, v):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, str(v)))

    def get_meta(self, k, default=None):
        r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    # ---- reads
    @staticmethod
    def _where(kinds, filters):
        sql, args = "", []
        if kinds:
            sql += " AND kind IN (%s)" % ",".join("?" * len(kinds))
            args += list(kinds)
        if filters.get("status"):
            sql += " AND lower(status) IN (%s)" % ",".join("?" * len(filters["status"]))
            args += filters["status"]
        for part in filters.get("path", []):
            sql += " AND lower(path) LIKE ?"
            args.append("%" + part.replace("\\", "/") + "%")
        return sql, args

    def _match(self, match, kinds, n, cols, filters=None):
        where, extra = self._where(kinds, filters or {})
        try:
            return self.db.execute("SELECT %s FROM docs WHERE docs MATCH ?%s ORDER BY %s LIMIT ?" % (cols, where, _BM25),
                                   [match] + extra + [n]).fetchall()
        except sqlite3.OperationalError:
            return []

    def listing(self, kinds, filters, limit):
        """Filters alone (`kind:decision status:rejected`): one hit per matching page, by path. With a status
        filter, a page that only *contains* that verdict (table rows, a section) lists those parts instead, each
        with its path:line, after the pages whose own status matches."""
        where, args = self._where(kinds, filters)
        keys = ("kind", "path", "loc", "title", "section", "snippet", "verified", "status", "flags", "score")
        if not filters.get("status"):
            rows = self.db.execute("SELECT kind, path, loc, title, section, substr(body, 1, 160), verified, status, "
                                   "flags, 0 FROM docs WHERE rowid IN (SELECT min(rowid) FROM docs WHERE 1 = 1%s "
                                   "GROUP BY path) ORDER BY path LIMIT ?" % where, args + [limit]).fetchall()
            return self.attach_fresh([dict(zip(keys, r)) for r in rows])
        matched = [dict(zip(keys, r)) for r in self.db.execute(
            "SELECT kind, path, loc, title, section, substr(body, 1, 400), verified, status, flags, 0 FROM docs "
            "WHERE 1 = 1%s ORDER BY path, loc LIMIT ?" % where, args + [LISTING_SCAN])]
        names, totals = sorted({h["path"] for h in matched}), {}
        for i in range(0, len(names), 500):                # under SQLite's 999-variable limit on old builds
            chunk = names[i:i + 500]
            totals.update(self.db.execute("SELECT path, count(*) FROM docs WHERE path IN (%s) GROUP BY path"
                                          % ",".join("?" * len(chunk)), chunk))
        pages, parts = [], []
        for path in dict.fromkeys(h["path"] for h in matched):
            mine = [h for h in matched if h["path"] == path]
            if len(mine) >= totals.get(path, 0):           # every doc of the page carries it: the page's own status
                pages.append(mine[0])
            else:
                parts += mine
        for h in pages + parts:
            h["snippet"] = _first_line(h["snippet"])
        return self.attach_fresh((pages + parts)[:limit])

    def search(self, q, kinds=None, limit=8, per_path=2):
        """Ranked hits as dicts: kind, path, loc, title, section, snippet, verified, status, flags, score.
        Candidates match any query term (BM25 favours docs matching more, and rarer, terms); docs that match
        every term get a bonus."""
        from memcrumbs.query import clean
        q, filters = split_filters(clean(q))
        kinds = expand_kinds((kinds or []) + filters.get("kind", []))
        pairs = term_pairs(q, self.synonyms)                      # [(term with synonyms, term as typed)]
        if not pairs:
            return self.listing(kinds, filters, limit) if filters else []
        if rank.is_long(pairs):
            pairs = rank.effective_pairs(self.db, pairs)
        expanded, plain = " OR ".join(e for e, _ in pairs), " OR ".join(p for _, p in pairs)
        rows = self._match(expanded, kinds, CANDIDATES, "rowid, kind, path, loc, title, section, "
                           "snippet(docs, 8, '[', ']', '…', 14), verified, status, flags, " + _BM25, filters)
        keys = ("rowid", "kind", "path", "loc", "title", "section", "snippet", "verified", "status", "flags", "score")
        hits = [dict(zip(keys, r)) for r in rows]
        if expanded != plain and rank.is_long(pairs):
            rank.damp(dict(self._match(plain, kinds, CANDIDATES, "rowid, " + _BM25, filters)), hits)
        ids = [h["rowid"] for h in hits]
        cover, known = rank.coverage(self.db, pairs, ids, int(self.get_meta("ndocs", 0) or 0))
        code, proc = wants_code(q), wants_procedure(q)
        for h in hits:
            intent = (CODE_INTENT_BOOST if code and h["kind"] == "code" else
                      PROCEDURE_BOOST if proc and h["kind"] == "runbook" else 1.0)
            h["score"] = h["score"] * BOOST.get(h["kind"], 1.0) * STATUS_BOOST.get(h["status"], 1.0) * (
                COVERAGE_FLOOR + cover.get(h["rowid"], 1.0)) * intent
            h["answers"] = round(cover.get(h["rowid"], 1.0) * known, 3)     # how much of the question it holds
        hits.sort(key=lambda h: (h["score"], h["path"], h["loc"]))      # deterministic on ties
        seen = {}
        for h in hits:                         # a file's second hit counts half: distinct files come first
            n = seen[h["path"]] = seen.get(h["path"], 0) + 1
            h["score"] *= SAME_FILE_DECAY ** (n - 1)
        hits.sort(key=lambda h: (h["score"], h["path"], h["loc"]))
        rank.follow_links(self.db, hits, self._stems(),          # one hop: the page a top hit points at
                          [p.strip('"*').lower() for _, p in pairs])
        hits.sort(key=lambda h: (h["score"], h["path"], h["loc"]))
        shown = set()
        for h in hits:
            h.pop("rowid", None)
        out, seen = [], {}
        for h in hits:
            seen[h["path"]] = seen.get(h["path"], 0) + 1
            if seen[h["path"]] <= per_path:
                out.append(h)
                shown.add(h["path"])
            if len(out) >= limit:
                break
        for h in out:                          # a pointer is worth a line only if its page is not listed anyway
            see = h.pop("see", None)
            if see and see["path"] not in shown:
                h["see"] = dict(path=see["path"], loc=see["loc"], title=see["title"], section=see["section"])
        return self.attach_fresh(out)

    def _stems(self):
        """Markdown page slug → path, for following [[links]] (cached per store)."""
        if getattr(self, "_stem_map", None) is None:
            self._stem_map = {}
            for (p,) in self.db.execute("SELECT path FROM files WHERE path LIKE '%.md' ORDER BY length(path), path"):
                self._stem_map.setdefault(Path(p).stem.lower(), p)
        return self._stem_map

    def symbols(self, name, limit=10, path_like=None):
        res = []
        for pat, op in ((name, "="), (name + "%", "LIKE"), ("%" + name + "%", "LIKE")):
            sql = "SELECT path, name, qual, kind, line, end, sig, doc FROM symbols WHERE name %s ? COLLATE NOCASE" % op
            args = [pat]
            if path_like:
                sql += " AND path LIKE ?"
                args.append("%" + path_like + "%")
            for r in self.db.execute(sql + " ORDER BY kind='const', length(path), path, line LIMIT ?", args + [limit]):
                if r not in res:
                    res.append(r)
            if len(res) >= limit:
                break
        return res[:limit]

    def file_stamp(self, path):
        r = self.db.execute("SELECT stamp FROM files WHERE path=?", (path,)).fetchone()
        return r[0] if r else None

    def paths(self):
        return [p for (p,) in self.db.execute("SELECT path FROM files ORDER BY path")]

    def counts(self):
        kinds = dict(self.db.execute("SELECT kind, count(*) FROM docs GROUP BY kind"))
        nsym = self.db.execute("SELECT count(*) FROM symbols").fetchone()[0]
        nfiles = self.db.execute("SELECT count(*) FROM files").fetchone()[0]
        return kinds, nsym, nfiles

    def flagged(self, flag):
        """How many files carry a flag (e.g. 'unreviewed') on their page doc."""
        return self.db.execute("SELECT count(DISTINCT path) FROM docs WHERE loc = 1 AND (' ' || flags || ' ') LIKE ?",
                               ("% " + flag + " %",)).fetchone()[0]

    def age(self):
        t = float(self.get_meta("refreshed", 0) or 0)
        return time.time() - t if t else None
