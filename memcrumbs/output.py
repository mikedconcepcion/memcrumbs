"""Every command's output goes through `Out`: each line is redacted (a filter failure withholds the line), the
total is capped with a notice that names the next command, `--json` emits the same facts as one object,
and the size (never the content) is logged for `stats --usage`."""
import json
import time

from memcrumbs import usage
from memcrumbs.redact import Redactor, RedactionError, safe

TOKEN_CHARS = 4                      # tokens are estimated as chars/4 and labelled as estimates
CAPS = {"find": 2400, "status": 6000}
DEFAULT_CAP = 8000                   # ≈ 2,000 tokens: no command goes past this without --full
FULL_CAP = 200_000                   # --full is still capped


def est_tokens(chars):
    return (chars + TOKEN_CHARS - 1) // TOKEN_CHARS


class Out:
    def __init__(self, cmd, project=None, redact=None, json_mode=False, cap=None, full=False, list_key=None):
        self.cmd, self.project, self.json = cmd, project, json_mode
        self.redact = redact or (project.redact if project else Redactor())
        self.cap = FULL_CAP if full else (cap or CAPS.get(cmd, DEFAULT_CAP))
        self.lines, self.data, self.next, self.list_key = [], {}, None, list_key
        self.t0 = time.perf_counter()
        self.closed = False

    def __call__(self, line=""):
        self.lines.extend(str(line).split("\n"))

    def set(self, **kw):
        self.data.update(kw)

    def hint(self, next_cmd):
        """The command to run for more than this output shows (used in the truncation notice)."""
        self.next = next_cmd

    # ---- rendering
    def _redact_lines(self):
        try:
            return self.redact("\n".join(self.lines)).split("\n")
        except RedactionError:
            return [safe(self.redact, ln) for ln in self.lines]

    def render_text(self):
        lines, out, used, truncated = self._redact_lines(), [], 0, False
        for i, ln in enumerate(lines):
            if used + len(ln) + 1 > self.cap:
                rest = lines[i:]
                out.append("… cut %d more lines (~%d tokens est.) to stay under ~%d tokens. Next: %s" % (
                    len(rest), est_tokens(sum(len(x) + 1 for x in rest)), est_tokens(self.cap),
                    self.next or "rerun with --full"))
                truncated = True
                break
            out.append(ln)
            used += len(ln) + 1
        return "\n".join(out), truncated

    def _clean(self, v):
        if isinstance(v, str):
            return safe(self.redact, v)
        if isinstance(v, dict):
            return {k: self._clean(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [self._clean(x) for x in v]
        return v

    def render_json(self):
        payload = self._clean(dict(cmd=self.cmd, **self.data))
        text = json.dumps(payload, ensure_ascii=False)
        truncated = False
        key = self.list_key
        while len(text) > self.cap and key and isinstance(payload.get(key), list) and payload[key]:
            payload[key].pop()
            payload["truncated"], payload["next"] = True, self.next or "rerun with --full"
            truncated = True
            text = json.dumps(payload, ensure_ascii=False)
        if len(text) > self.cap:
            payload = {"cmd": self.cmd, "truncated": True, "error": "output over the cap",
                       "next": self.next or "rerun with --full"}
            truncated, text = True, json.dumps(payload)
        return text, truncated

    def close(self):
        if self.closed:
            return
        self.closed = True
        text, truncated = self.render_json() if self.json else self.render_text()
        print(text)
        if self.project is not None:
            items = self.data.get(self.list_key) if self.list_key else None
            usage.record(self.project, self.cmd, len(text), truncated, (time.perf_counter() - self.t0) * 1000, self.json,
                         len(items) if isinstance(items, list) else None)
        return text
