"""Deterministic extraction: evidence-quote candidates and entities. No model calls."""

import json
import re
from pathlib import Path

BOUNDARY = re.compile(r"[.!?]+\s+|\n+")


def parts(text, min_chars=25, max_parts=12):
    """Split a review into contiguous sentence-like parts. Every part is an exact substring of the text."""
    cuts = [0, *[m.end() for m in BOUNDARY.finditer(text)], len(text)]
    spans = [(a, b) for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]
    merged = []
    for span in spans:
        # Fold fragments that are too short to stand as evidence into their neighbour.
        if merged and len(text[merged[-1][0]:merged[-1][1]].strip()) < min_chars:
            merged[-1] = (merged[-1][0], span[1])
        else:
            merged.append(span)
    if len(merged) > 1 and len(text[merged[-1][0]:merged[-1][1]].strip()) < min_chars:
        merged[-2:] = [(merged[-2][0], merged[-1][1])]
    if len(merged) > max_parts:
        size = -(-len(merged) // max_parts)
        merged = [(merged[i][0], merged[min(i + size, len(merged)) - 1][1]) for i in range(0, len(merged), size)]
    return [text[a:b].strip() for a, b in merged]


def load_lexicon(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))["entities"]
    return [(name, re.compile("|".join(patterns), re.IGNORECASE)) for name, patterns in data.items()]


def entities(text, lexicon):
    """Lexicon entities named in the text, ordered by first appearance."""
    found = []
    for name, pattern in lexicon:
        match = pattern.search(text)
        if match:
            found.append((match.start(), name))
    return [name for _, name in sorted(found)]


def has_ascii_letters(text):
    return any("a" <= c <= "z" or "A" <= c <= "Z" for c in text)
