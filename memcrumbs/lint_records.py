"""`check` rules for the shape of records. Each is a curation step (I): it says what to add.
- an incident names its symptom, so a repeat is found by what someone sees first;
- a rejected or parked decision keeps its evidence (the numbers and where they came from);
- a runbook has preconditions, a verify step and a rollback (or says "Rollback: none (irreversible)");
- a page that replaces another says so (`supersedes:` or a [[link]]), so the link runs both ways."""
import re

from memcrumbs import markdown

PRE = re.compile(r"(?i)\b(pre-?conditions?|prerequisites?|before you (start|begin)|requirements?|you need|preparation)\b")
VERIFY = re.compile(r"(?i)\b(verify|verification|check|validat\w*|confirm|test|smoke)")
ROLLBACK = re.compile(r"(?i)\b(rollback|roll back|undo|revert|back out|restore the previous)")
NO_ROLLBACK = re.compile(r"(?im)^\W*rollback\W+none\b")
EVIDENCE = re.compile(r"(?i)\b(evidence|results?|numbers|data|measured|measurements?|benchmarks?|findings|what we found)\b")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}$")


def _names(v):
    return [str(x).strip().lower().removesuffix(".md") for x in (v if isinstance(v, list) else [v] if v else [])]


def findings(where, kind, meta, body):
    out = []
    heads = [h for _, _, h in markdown.headings(body.splitlines())]
    status = str(meta.get("status") or "").lower()
    if kind == "incident" and not meta.get("symptom") and not any(re.match(r"(?i)\s*symptoms?\b", h) for h in heads):
        out.append(("I", where, "no symptom: add `symptom:` (what someone sees first, in their words), so a repeat "
                                "is found by it"))
    if kind == "decision" and status in ("rejected", "parked") and not meta.get("evidence") and \
            not any(EVIDENCE.search(h) for h in heads):
        out.append(("I", where, "%s without evidence: add an Evidence section (the numbers and where they came from)"
                    % status))
    if kind == "runbook":
        miss = [name for name, rx in (("preconditions", PRE), ("a verify step", VERIFY), ("a rollback", ROLLBACK))
                if not any(rx.search(h) for h in heads)]
        if "a rollback" in miss and NO_ROLLBACK.search(body):
            miss.remove("a rollback")
        if miss:
            out.append(("I", where, "runbook without %s: add the heading%s (or \"Rollback: none (irreversible)\")"
                        % (", ".join(miss), "s" if len(miss) > 1 else "")))
        if meta.get("tested") and not DATE.match(str(meta["tested"])):
            out.append(("W", where, "tested must be YYYY-MM-DD (the day the steps were last run)"))
    return out


def two_way(pages):
    """pages: {stem: (where, meta, body)}. A page another one is `superseded_by` should name it back."""
    out = []
    for stem, (where, meta, _) in sorted(pages.items()):
        by = str(meta.get("superseded_by") or "").lower().removesuffix(".md").rsplit("/", 1)[-1]
        if not by or by not in pages:
            continue
        b_where, b_meta, b_body = pages[by]
        if stem not in _names(b_meta.get("supersedes")) and stem not in [x.lower() for x in markdown.links(b_body)]:
            out.append(("I", b_where, "replaces [[%s]] (it says superseded_by %s): add `supersedes: %s`"
                        % (stem, by, stem)))
    return out
