"""Hello API: a tiny example service used by the memcrumbs example project."""
import json

DEFAULT_PORT = 8080


def load_config(path):
    """Read the JSON config once at start-up."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Handler:
    """Routes requests."""

    def health(self):
        return {"ok": True}

    def hello(self, name="world"):
        return {"hello": name}
