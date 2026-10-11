"""Secret filter: everything memcrumbs indexes, prints or writes passes through here. Best effort (SECURITY.md).

Rules catch key=value secrets (any key that ends in a secret word: DB_PASSWORD, apiKey, x-api-key …), CLI
flags, auth headers, credentials in URLs, XML values, bot tokens, private keys and long random strings, while
leaving digests, UUIDs, git SHAs, lockfile hashes, data URIs, paths, code references and prose alone.
A per-project deny list (<project>/secrets.deny, git-ignored) holds known values, ideally only as hashes.
A failure inside the filter raises RedactionError: callers then drop the item instead of passing it through.
"""
import fnmatch
import hashlib
import re
from pathlib import Path


class RedactionError(Exception):
    """The filter itself failed; the text must not be indexed or printed."""


_KEY_ENDS = ("password", "passwd", "passphrase", "passcode", "pwd", "secret", "token", "apikey", "privatekey",
             "signingkey", "hmackey", "encryptionkey", "accesskey", "secretkey", "masterkey", "clientkey")
_KW = r"(?:pass\w*|pwd|secret|token|key)"
_PLACEHOLDER = re.compile(
    r"(?i)^(?:none|null|nil|true|false|undefined|empty|unset|required|optional|changeme|change[-_]?me|example|sample"
    r"|dummy|test|placeholder|redacted|secret|password|token|todo|tbd|n/?a|[*x.#-]+)$|^your[-_ ]|[-_ ]here$|^xxx")
_WORDS = re.compile(r"[a-z]+(?:[-_][a-z]+)*")
_CODE_REF = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+|[A-Z][a-z]+(?:-[A-Z][a-z]+)+")   # obj.attr, Verb-Noun
_DIGEST_BEFORE = re.compile(r"(?i)(?:sha\d*|md5|blake\d*\w*|digest|checksum|hash|integrity|etag)[\W_]{0,5}$")
_TOKEN = re.compile(r"[^\s`\"'()<>\[\]{},;]+")
_UNQ = r"[^\s\"',;&()\[\]{}]"
# an unquoted value runs on across & ; , unless a new `name=` follows (`pass=x&user=y`, `Password=a;Database=b`):
# stopping at the first & left the rest of a password like `Tr0ub4dor&3` visible
_QVAL = (r"(?P<q>[\"'])?(?P<val>(?(q)[^\n]*?(?=(?P=q)(?:[\s,;)}\]>/]|$))|" + _UNQ + r"+(?:[&;,](?![\w.-]+[=:])"
         + _UNQ + r"+)*))")

_KV = re.compile(r"(?i)(?<![\w.$-])(?P<key>(?:[a-z_][\w.-]*?)?" + _KW + r")(?P<sep>[\"']?[ \t]*(?:=>|:=|[:=])[ \t]*)" + _QVAL)
_FLAG = re.compile(r"(?i)(?<![\w-])(?P<key>--?(?:[a-z][\w-]*?)?" + _KW + r")(?P<sep>[ \t]+|=)" + _QVAL)
_XML_EL = re.compile(r"(?i)<(?P<key>[\w:.-]*?" + _KW + r")>(?P<val>[^<\n]+)</")
_XML_ADD = re.compile(r"(?i)\bkey\s*=\s*([\"'])(?P<key>[^\"'\n]+)\1\s+value\s*=\s*([\"'])(?P<val>[^\"'\n]*)\3")
_SECURE = re.compile(r"(?i)ConvertTo-SecureString\s+(?:-String\s+)?([\"'])(?P<val>[^\n]+?)\1")
_URL_PASS = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s:/@\"']+:(?P<val>[^\s@/\"']+)(?=@)")
_AUTH = re.compile(r"(?i)\b(?:proxy-)?authorization[\"']?\s*[:=]\s*[\"']?(?:bearer|basic|token|digest|negotiate)\s+"
                   r"(?P<val>[^\s\"']+)")
_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----|\Z)",
                  re.S)
_PEM_TAIL = re.compile(r"\A(?:(?!-----BEGIN ).)*?-----END [A-Z0-9 ]*PRIVATE KEY(?: BLOCK)?-----", re.S)  # chunk cut mid-key
_BOT = re.compile(r"(?<!\d)\d{8,10}:[A-Za-z0-9_-]{30,}")
_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{48,}(?![0-9a-fA-F])")
_RANDOM = re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{40,}={0,2}")


def secret_hash(value):
    """Deny-list line for a secret without storing it: `memcrumbs secret-add` writes this."""
    return "sha256:%d:%s" % (len(value), hashlib.sha256(value.encode("utf-8")).hexdigest())


def secret_key(name, extra=()):
    """Does this key name hold a secret? DB_PASSWORD, apiKey, x-api-key, smtp_pass yes; token_type, max_tokens no."""
    k = re.sub(r"[^a-z0-9]", "", name.lower())
    if k.endswith(_KEY_ENDS) or re.search(r"(?:^|[_.-])pass$", name.lower()):
        return True
    return any(fnmatch.fnmatchcase(k, pat.lower()) for pat in extra)


def looks_secret(v, key=""):
    """Filter prose, placeholders, references and paths ("password: rotate monthly", "token = None",
    "key: C:/keys/a.txt", "${{ secrets.X }}"): a secret value has a digit, a capital or a symbol, or is long."""
    if not v or v[0] in "<$%{«*" or v.startswith(("/", "\\", "./", "../", "~")) or re.match(r"[A-Za-z]:[\\/]", v):
        return False
    if _PLACEHOLDER.search(v):
        return False
    if v.isdigit() and len(v) < 6 and not re.search(r"(?i)pass|pin|code|pwd", key):
        return False                                  # a small number under a secret-ish key is a setting
    if _WORDS.fullmatch(v):                          # plain words; a word-list passphrase still counts
        return len(re.split(r"[-_]", v)) >= 3 and bool(re.search(r"(?i)pass|pwd", key))
    return len(v) >= 16 or any(c.isdigit() or c.isupper() or not c.isalnum() for c in v)


_KEYISH = re.compile(r"(?i)key$")


def _strong(v):
    """A short value that still reads as random: 12+ chars with a digit and mixed case or a symbol, switching
    character class often (not `user_id_2024`, `cache:123:x` or a path)."""
    if len(v) < 12 or not looks_secret(v) or _CODE_REF.fullmatch(v) or not re.search(r"\d", v):
        return False
    if not (re.search(r"[A-Z]", v) and re.search(r"[a-z]", v) or re.search(r"[!@#$%^&*+=~?]", v)):
        return False
    s = [c for c in v if c.isalnum()]
    return sum(1 for a, b in zip(s, s[1:]) if _cls(a) != _cls(b)) >= 4


def _cls(c):
    return 0 if c.isdigit() else 1 if c.isupper() else 2


def _randomish(tok, least=32):
    """Long token that reads as random (not CamelCase, a path or a word list): mixed classes that switch often."""
    s = [c for c in tok if c.isalnum()]
    if len(s) < least or {_cls(c) for c in s} != {0, 1, 2} or sum(c.isdigit() for c in s) < 2:
        return False
    switches = sum(1 for a, b in zip(s, s[1:]) if _cls(a) != _cls(b))
    return switches / (len(s) - 1) >= 0.4


_WORD = re.compile(r"^[A-Za-z][a-z]{2,}(?:[A-Z][a-z]+)?$")      # Temp, folders, AppData, src


def _pathlike(tok):
    """A file path, not a key: two or more slashes and at least two plain-word segments (`Users/AppData/Local`).
    A base64 key has slashes too, but its pieces are random mixes, so this almost never holds for one."""
    parts = tok.split("/")
    return len(parts) >= 3 and sum(1 for p in parts if _WORD.match(p)) >= 2


class Redactor:
    def __init__(self, deny_file=None, secret_keys=()):
        self.deny, self.hashed, self.malformed = [], {}, 0          # literals; {length: {sha256 hex}}; bad lines
        self.keys = tuple(secret_keys)
        if deny_file and Path(deny_file).exists():
            for ln in Path(deny_file).read_text(encoding="utf-8", errors="replace").splitlines():
                ln = ln.strip()
                if ln.startswith("sha256:"):
                    parts = ln.split(":")
                    if len(parts) == 3 and parts[1].isdigit() and re.fullmatch(r"[0-9a-fA-F]{64}", parts[2]):
                        self.hashed.setdefault(int(parts[1]), set()).add(parts[2].lower())
                    else:
                        self.malformed += 1               # skipped and counted (doctor), never echoed
                elif ln and not ln.startswith("#") and len(ln) >= 4:
                    self.deny.append(ln)
        self.deny.sort(key=len, reverse=True)

    def _unhash(self, text):
        def sub(m):
            t = m.group(0)
            for cut in (t, t.rstrip(".:")):              # a secret followed by "." or ":" at a sentence end
                hs = self.hashed.get(len(cut))
                if hs and hashlib.sha256(cut.encode("utf-8")).hexdigest() in hs:
                    return "«redacted»" + t[len(cut):]
            return t
        return _TOKEN.sub(sub, text)

    # each rule: (regex, label, keep(match) -> True when the match is not a secret); the value group is replaced
    def _rules(self):
        def kv(m):
            v = m.group("val")
            quoted = "q" in m.re.groupindex and m.group("q")
            if not quoted and (re.fullmatch(r"\d{1,4}/\d{1,4}", v) or
                               v.isdigit() and re.match(r" of \d", m.string[m.end():m.end() + 6])):
                return True                                   # a tally ("PASS: 15 of 15 jobs"), not a PIN
            if not quoted and (_CODE_REF.fullmatch(v) or m.string[m.end():m.end() + 1] in ("(", "[") and v.isidentifier()):
                return True                                   # code: settings.KEY, Read-Host, getpass(
            key = m.group("key").lstrip("-<")
            if secret_key(key, self.keys):
                return not looks_secret(v, key)
            return not (_KEYISH.search(key) and _strong(v))  # CfgPanelKey = <random>: any *key with a random value

        def flag(m):
            return m.group("val").startswith("-") or kv(m)

        def plain(m):
            return not looks_secret(m.group("val"))

        def hexdigest(m):
            before, after = m.string[max(0, m.start() - 24):m.start()], m.string[m.end():m.end() + 2]
            return bool(_DIGEST_BEFORE.search(before)) or after == "  " or after.startswith(" *")

        def random(m):
            t, before = m.group(0), m.string[max(0, m.start() - 24):m.start()]
            if _pathlike(t):                             # a temp or cache path: each piece is judged on its own
                return not any(_randomish(p, 20) for p in t.split("/"))
            return bool(re.match(r"(?i)sha\d+-", t) or before.endswith("base64,") or _DIGEST_BEFORE.search(before)) \
                or not _randomish(t)                     # SRI, data URIs, wheel RECORD `sha256=…` digests

        return ((_PEM, "«private-key»", None), (_PEM_TAIL, "«private-key»", None), (_URL_PASS, "«redacted»", plain),
                (_AUTH, "«redacted»", plain), (_SECURE, "«redacted»", plain), (_XML_ADD, "«redacted»", kv), (_XML_EL, "«redacted»", kv),
                (_FLAG, "«redacted»", flag), (_KV, "«redacted»", kv), (_BOT, "«bot-token»", None),
                (_HEX, "«hex-secret»", hexdigest), (_RANDOM, "«long-secret»", random))

    def _apply(self, text, hits=None):
        if self.hashed:
            new = self._unhash(text)
            if new != text and hits is not None:
                hits.append("deny-listed value")
            text = new
        for lit in self.deny:
            if lit in text:
                text = text.replace(lit, "«redacted»")
                if hits is not None:
                    hits.append("deny-listed value")
        for rx, label, keep in self._rules():
            def sub(m):
                if keep and keep(m):
                    return m.group(0)
                if hits is not None:
                    hits.append("secret value for %s" % m.group("key") if "key" in rx.groupindex else label)
                if "val" not in rx.groupindex:
                    return label
                a, b = m.span("val")
                return m.string[m.start():a] + label + m.string[b:m.end()]
            text = rx.sub(sub, text)
        return text

    def __call__(self, text):
        if not text:
            return text
        try:
            return self._apply(text)
        except Exception as e:                         # fail closed: never pass unfiltered text on
            raise RedactionError(type(e).__name__) from None

    def find(self, text):
        """Short descriptions of secret-looking spans (for `memcrumbs check` / `scan`), never the values."""
        hits = []
        try:
            self._apply(text, hits)
        except Exception as e:
            raise RedactionError(type(e).__name__) from None
        return hits


def safe(redact, text, withheld="«withheld: redaction failed»"):
    """Redact for output: a filter failure withholds the text instead of printing it."""
    try:
        return redact(text)
    except RedactionError:
        return withheld
