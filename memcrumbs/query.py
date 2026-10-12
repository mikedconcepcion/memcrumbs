"""Query rewriting for FTS5: quote every term (so `app_cfg.json` or `a-b` never break the syntax), drop the
words of a natural-language question that carry no topic ("how do I …", "where is the …"), expand words and
phrases through the thesaurus (synonyms.py), and notice when the question asks for code ("which function …",
"where is X implemented") so code hits rank first."""
import re

from memcrumbs.synonyms import TABLE, max_words

STOPWORDS = frozenset("""
a about above after again all am an and any are as at be been before being below between both but by can
could did do does doing done down during each ever few for from further get gets got had has have having he her
here hers him his how i if in into is it its itself just know let me more most my myself need no nor not now
of off on once only or other our ours out over own same she should so some such than that the their theirs them
then there these they this those through to too under until up us very was were what when where which while
who whom why will with would you your yours we
""".split())
# words that ask for code rather than name a topic: dropped from the match, used to rank code hits first
CODE_INTENT = frozenset("""
code function functions method methods class classes script scripts module modules implemented implementation
implements defined definition defines source routine handler cmdlet logic
""".split())


def _tokens(q):
    out = []
    for t in re.findall(r'"[^"]+"|\S+', q):
        prefix = t.endswith("*") and len(t) > 1
        phrase = t.startswith('"')
        t = t.strip('"').rstrip("*").replace('"', "")
        if not phrase:
            t = t.strip("?!.,;:()[]{}'`")
            if t.lower().endswith("'s"):
                t = t[:-2]
        if re.search(r"\w", t):
            out.append((t, prefix, phrase))
    return out


def terms(q, table=TABLE):
    """[(alternatives, prefix, keep)]: each query term with its synonyms. Thesaurus phrases ("roll back",
    "each night") are found before stopwords are dropped; stopwords and code-intent words are dropped unless
    nothing else is left."""
    toks, out, i = _tokens(q), [], 0
    longest = max_words(table)
    while i < len(toks):
        t, prefix, phrase = toks[i]
        for k in range(min(longest, len(toks) - i), 1, -1):
            if any(p or ph for _, p, ph in toks[i:i + k]):
                continue
            key = " ".join(x[0].lower() for x in toks[i:i + k])
            if key in table:
                out.append(([key] + sorted(table[key]), False, True))
                i += k
                break
        else:
            alts = [t] if phrase or prefix else [t] + sorted(table.get(t.lower(), ()))
            out.append((alts, prefix, phrase or prefix))
            i += 1
    keep = [x for x in out if x[2] or x[0][0].lower() not in STOPWORDS | CODE_INTENT]
    return keep or [x for x in out if x[0][0].lower() not in STOPWORDS] or out


FILTERS = ("kind", "status", "path")
_FILTER = re.compile(r"(?<!\S)(kind|status|path|in):(\S+)", re.I)


def split_filters(q):
    """Inline filters, in the spirit of a Boolean search DSL: `kind:decision status:rejected path:booking`
    (comma lists allowed; `in:` = `path:`). Returns (query without them, {filter: [values]})."""
    found = {}
    for key, val in _FILTER.findall(q):
        key = "path" if key.lower() == "in" else key.lower()
        found.setdefault(key, []).extend(v for v in val.lower().split(",") if v)
    return " ".join(_FILTER.sub(" ", q).split()), found


_PROCEDURE = re.compile(r"(?i)\bhow (?:do|can|should|would) (?:i|we|you)\b|\bhow to\b|\bsteps? (?:to|for)\b|"
                        r"\b(?:procedure|runbook|walk ?through|step by step)\b")


_TESTS = re.compile(r"(?i)\b(?:conftest|fixtures?|tests?\s+(?:for|of|covering|that)|test\s+(?:file|case|suite)s?|"
                    r"which\s+tests?)\b")


def wants_tests(q):
    """The question asks for tests themselves ("the tests for redirects", "which test covers …"): test files keep
    their full score. Testing an app ("in my unit tests") is not that."""
    return bool(_TESTS.search(q))


def wants_procedure(q):
    """A "how do I / steps to" question: runbooks first."""
    return bool(_PROCEDURE.search(q))


_WHERE_CODE = re.compile(r"(?i)\bwhere\s+(?:is|are|was|were|does|do|did)\s+(?!(?:i|we|you|my|our)\b)")


def wants_code(q):
    """A question about code: it names code ("which function …"), or asks where something is done ("where is the
    header masked", not "where do I set …")."""
    return any(w.strip("?!.,;:'`").lower() in CODE_INTENT for w in q.split()) or bool(_WHERE_CODE.search(q))


def _expr(alts, prefix):
    quoted = ['"%s"%s' % (a.replace('"', ""), "*" if prefix and n == 0 else "") for n, a in enumerate(alts)]
    return quoted[0] if len(quoted) == 1 else "(%s)" % " OR ".join(quoted)


def term_groups(q, table=TABLE):
    """One FTS5 expression per query term: the term or a parenthesised OR of it and its synonyms."""
    return [_expr(alts, prefix) for alts, prefix, _ in terms(q, table)]


def term_pairs(q, table=TABLE):
    """[(expression with synonyms, expression as typed)] per query term, so synonyms can count for less."""
    return [(_expr(alts, prefix), _expr(alts[:1], prefix)) for alts, prefix, _ in terms(q, table)]


def clean(q):
    """A NUL or other control character in a query would end the FTS5 string early: they become spaces."""
    return "".join(" " if ord(c) < 32 else c for c in q)


def fts_query(q, op="AND", table=None):
    """Without a table, terms are not expanded (exact lookups, tests)."""
    return (" %s " % op).join(term_groups(q, table if table is not None else {}))
