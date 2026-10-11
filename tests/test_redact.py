"""Redaction corpus (tests/corpus/redaction.json): true secrets must never survive; known false-positive shapes
must pass unchanged. Secret values are stored as short fragments and joined here, so the repo holds none."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memcrumbs.redact import RedactionError, Redactor, looks_secret, safe, secret_hash, secret_key

CORPUS = json.loads((Path(__file__).parent / "corpus" / "redaction.json").read_text(encoding="utf-8"))


def secrets():
    for s in CORPUS["secrets"]:
        value = "".join(s["fragments"])
        for ctx in s["contexts"]:
            yield s["id"], value, ctx.replace("{S}", value)


def leaked(value, text, run=12):
    if value in text:
        return value
    if len(value) >= 16:
        return next((value[i:i + run] for i in range(len(value) - run + 1) if value[i:i + run] in text), None)
    return None


class CorpusTest(unittest.TestCase):
    def test_secrets_never_survive(self):
        r = Redactor()
        for sid, value, text in secrets():
            with self.subTest(sid, text=text[:60]):
                self.assertIsNone(leaked(value, r(text)))
                self.assertTrue(r.find(text), "scan must report it")

    def test_scan_flags_every_secret_line_by_line(self):
        r = Redactor()                                   # `scan` sees one line at a time
        for sid, value, text in secrets():
            with self.subTest(sid, text=text[:60]):
                self.assertTrue(any(r.find(ln) for ln in text.splitlines()))

    def test_private_key_cut_between_chunks(self):
        r = Redactor()                                   # an index chunk boundary may fall inside a key block
        for s in CORPUS["secrets"]:
            value = "".join(s["fragments"])
            if "PRIVATE KEY" not in value:
                continue
            lines = ("before\n" + value + "\nafter").splitlines()
            for cut in range(1, len(lines)):
                out = r("\n".join(lines[:cut])) + "\n" + r("\n".join(lines[cut:]))
                for part in value.splitlines():
                    if len(part) >= 12 and not part.startswith("-----"):
                        with self.subTest(s["id"], cut=cut):
                            self.assertIsNone(leaked(part, out))

    def test_benign_shapes_pass_unchanged(self):
        r = Redactor()
        for b in CORPUS["benign"]:
            with self.subTest(b["id"]):
                self.assertEqual(r(b["text"]), b["text"])
                self.assertEqual(r.find(b["text"]), [])


class RedactTest(unittest.TestCase):
    def test_key_values(self):
        r = Redactor()
        fake = "abcDEF" + "1234567"                                          # built at runtime: no literal secret in the repo
        self.assertEqual(r("api_key=" + fake), "api_key=«redacted»")             # memcrumbs:allow
        self.assertEqual(r("password: changed yesterday"), "password: changed yesterday")   # prose, not a secret
        self.assertEqual(r("presets contain CfgServiceKey: never print"), "presets contain CfgServiceKey: never print")
        self.assertIn("«bot-token»", r("token " + "123456789:" + "AAH" + "x" * 32 + " end"))
        self.assertIn("«hex-secret»", r("hmac " + "ab" * 32))

    def test_wheel_record_digests(self):
        line = "memcrumbs/cli.py,sha256=Zq3vL0pXk9Rm2Tb7Yc4Wd1Ne8Hf5Ga6Js0Ku9Lv3Mw,8123"
        self.assertEqual(Redactor()(line), line)

    def test_any_key_with_a_random_value(self):
        r = Redactor()
        fake = "Zq8" + "Lm2" + "Wx7" + "Tb4"
        self.assertEqual(r("CfgPanelKey=" + fake), "CfgPanelKey=«redacted»")                 # memcrumbs:allow
        self.assertEqual(r('license_key: "%s"' % fake), 'license_key: "«redacted»"')
        for benign in ("sort_key = created_at_2024", "cache_key = user:1234:profile", "primary_key = id",
                       "registry_key = HKLM/Software/Example", "partition_key: tenant_42"):
            self.assertEqual(r(benign), benign)

    def test_a_value_is_redacted_whole_and_a_tally_is_kept(self):
        r = Redactor()
        self.assertEqual(r("pass: Tr0ub4dor&3 ok"), "pass: «redacted» ok")         # memcrumbs:allow (& must not leak)
        self.assertEqual(r("db?pass=Zx9Kq2&user=ann"), "db?pass=«redacted»&user=ann")   # memcrumbs:allow
        self.assertEqual(r("Password=abc9X;Database=main"), "Password=«redacted»;Database=main")  # memcrumbs:allow
        for tally in ("PASS: 15 of 15 jobs", "PASS: 3/4 checks"):
            self.assertEqual(r(tally), tally)
        self.assertEqual(r("pwd: 1234"), "pwd: «redacted»")                        # memcrumbs:allow (a PIN)

    def test_temp_paths_are_not_secrets_but_random_pieces_are(self):
        r = Redactor()
        for path in ("/var/folders/36/tjdph2t965j8snz9_vkdnw0r0000gn/T/tmpkc3l1o26/x.py",     # macOS temp (CI)
                     "C:/Users/RUNNER~1/AppData/Local/Temp/tmp0a45nur6/src/leak.txt",          # Windows 8.3 (CI)
                     "github.com/org/repo/security/advisories/GHSA-w48q-cv73-mx4w"):
            self.assertEqual(r(path), path)
        fake = "Q" + "k8vR2mZp7XyL4nTb9WcH3sDf6GjK1aE5uY0iO"                  # memcrumbs:allow (invented)
        self.assertNotIn(fake, r("see /api/keys/stored/%s/x" % fake))           # a random piece in a path still goes

    def test_project_secret_keys(self):
        fake = "Zq8" + "Lm2" + "Wx"
        self.assertEqual(Redactor()("CfgPanelKey=" + fake), "CfgPanelKey=" + fake)       # short: needs the config · memcrumbs:allow
        self.assertEqual(Redactor(secret_keys=["cfg*key"])("CfgPanelKey=" + fake), "CfgPanelKey=«redacted»")  # memcrumbs:allow
        self.assertTrue(secret_key("DB_PASSWORD") and secret_key("x-api-key") and secret_key("smtp_pass"))
        self.assertFalse(secret_key("token_type") or secret_key("max_tokens") or secret_key("compass_heading"))

    def test_hashed_deny_list(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "secrets.deny"
            f.write_text(secret_hash("Hunter2!") + "\n", encoding="utf-8")
            r = Redactor(f)
            self.assertEqual(r("the pass is `Hunter2!`."), "the pass is `«redacted»`.")
            self.assertEqual(r("ends a sentence Hunter2!."), "ends a sentence «redacted».")
            self.assertTrue(r.find("x Hunter2! y"))
            self.assertNotIn("Hunter2!", f.read_text(encoding="utf-8"))

    def test_looks_secret(self):
        self.assertFalse(looks_secret("never"))
        self.assertFalse(looks_secret("C:\\keys\\a.txt"))
        self.assertFalse(looks_secret("<placeholder>"))
        self.assertTrue(looks_secret("Zx9!kq"))

    def test_fails_closed(self):
        r = Redactor()
        with mock.patch.object(Redactor, "_apply", side_effect=ValueError("boom")):
            with self.assertRaises(RedactionError):
                r("anything")
            self.assertEqual(safe(r, "anything"), "«withheld: redaction failed»")


if __name__ == "__main__":
    unittest.main()
