"""Prompt-injection tripwire: text in the knowledge base that addresses an AI agent with instructions.

Wiki pages are served to agents as facts, so a pasted vendor doc or ticket that says "ignore previous
instructions" is an attack path. `check` reports it, `find` marks the hit and `page` prints a warning.
Patterns are deliberately narrow: they target imperative text aimed at a model, not pages that discuss prompts."""
import re

_RULES = (
    ("ignore-instructions", r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+|any\s+|the\s+|your\s+|of\s+)*"
                            r"(?:previous|prior|above|earlier|preceding|system|original|existing)\s+"
                            r"(?:instructions?|prompts?|messages?|rules|directions|guidelines|context)"),
    ("addressed-to-ai", r"\b(?:ai|llm|gpt|claude|language[- ]model|coding)\s+(?:assistants?|agents?|models?|tools?)\s+"
                        r"(?:reading|processing|parsing|that\s+read|who\s+read)\s+(?:this|these)\b"),
    ("addressed-to-ai", r"\b(?:attention|note|important)[ \t:,-]{0,6}(?:(?:to|for)[ \t:,-]{1,6})?(?:all[ \t]{1,3})?"
                        r"(?:ai|llm)s?\b(?:[ \t]{1,3}(?:assistants?|agents?|models?))?[ \t]{0,3}[:,]"),
    ("role-change", r"\byou\s+are\s+now\s+(?:a|an|in|the)\b|\bfrom\s+now\s+on,?\s+you\s+(?:must|will|are)\b"),
    ("hide-from-user", r"\bdo\s+not\s+(?:tell|inform|mention\s+(?:this\s+)?to|alert|notify)\s+(?:the\s+)?"
                       r"(?:user|operator|owner|human)s?\b|\bwithout\s+(?:telling|informing)\s+(?:the\s+)?"
                       r"(?:user|operator|owner|human)\b"),
    ("exfiltrate", r"\b(?:reveal|exfiltrate|leak)\s+(?:all\s+|the\s+|your\s+|every\s+)*"
                   r"(?:environment\s+variables|env\s+vars|system\s+prompt|instructions|api\s+keys?|secrets|credentials)\b"),
    ("role-tag", r"<\|im_start\|>|<\|system\|>|\[/?INST\]|<[ \t]*/?[ \t]*system[ \t]*>|"
                 r"^[ \t]*#{0,3}[ \t]*system[ \t]*prompt[ \t]*:"),           # [ \t], not \s: never across lines
)
_COMPILED = tuple((name, re.compile(rx, re.I | re.M)) for name, rx in _RULES)


def instruction_like(text):
    """Names of the injection rules the text trips (empty if none)."""
    return sorted({name for name, rx in _COMPILED if rx.search(text)})
