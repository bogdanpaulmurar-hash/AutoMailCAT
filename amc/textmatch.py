"""Text normalisation and word matching used by every rule.

Matching ignores letter case and Romanian diacritics (ă â î ș ț, also the
older cedilla forms ş ţ), so "Factură" matches "factura". A term matches
whole words only; a trailing * matches any ending ("factur*" matches
"factura", "facturi", "facturilor"). A term with several words is a phrase.
"""
from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

_NON_WORD = re.compile(r"(?:[^\w@.]|_)+", re.UNICODE)
_SPACES = re.compile(r"\s+")


def normalize(text: str | None) -> str:
    """Lower case, no diacritics, punctuation turned into spaces (e-mail addresses are kept)."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = _NON_WORD.sub(" ", text)
    # dots only matter inside addresses: drop the ones at word edges
    text = re.sub(r"(?<!\w)\.|\.(?!\w)", " ", text)
    return _SPACES.sub(" ", text).strip()


@lru_cache(maxsize=4096)
def _term_regex(term: str) -> re.Pattern | None:
    wildcard = term.endswith("*")
    core = normalize(term.rstrip("*"))
    if not core:
        return None
    words = [re.escape(w) for w in core.split(" ")]
    body = r"\s+".join(words)
    if wildcard:
        body += r"[\w.@]*"
    return re.compile(r"(?<![\w@])" + body + r"(?![\w@])")


def find(term: str, normalized_text: str) -> int:
    """Position of the first match of `term` in already normalised text, or -1."""
    rx = _term_regex(term.strip())
    if rx is None:
        return -1
    m = rx.search(normalized_text)
    return m.start() if m else -1


def contains(term: str, normalized_text: str) -> bool:
    return find(term, normalized_text) >= 0


def split_terms(value) -> list[str]:
    """Accepts a list or a text with one term per line / separated by commas or semicolons."""
    if value is None:
        return []
    if isinstance(value, str):
        value = re.split(r"[\n,;]+", value)
    return [str(v).strip() for v in value if str(v).strip()]
