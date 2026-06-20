"""
Defensively normalizes bibliography fields that should be scalar
strings/ints/bools but might arrive as something else -- most often an
LLM returning a JSON array of authors instead of the single joined
string the prompt asked for (very plausible for a book with several
named authors, like CLRS).

Applied in lookup_bibliography.py right after parsing the LLM's JSON
response, before any of those values get written to a Book row -- so a
malformed value (e.g. a list where a string is expected) can never reach
the database, regardless of how creatively an LLM decides to format its
output on a given run.
"""


def _to_str_or_none(value):
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        joined = ", ".join(str(v).strip() for v in value if v and str(v).strip())
        return joined or None
    text = str(value).strip()
    return text or None


def _to_int_or_none(value):
    if value is None or value == "":
        return None
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
        if value is None:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    if value is None:
        return default
    return bool(value)


def coerce_bibliography_fields(data: dict) -> dict:
    """Returns a copy of data with title/authors/publisher/edition coerced
    to str-or-None, year coerced to int-or-None, and is_editor coerced to
    bool. Any other keys in data are passed through untouched."""
    coerced = dict(data)
    if "title" in coerced:
        coerced["title"] = _to_str_or_none(coerced["title"])
    if "authors" in coerced:
        coerced["authors"] = _to_str_or_none(coerced["authors"])
    if "publisher" in coerced:
        coerced["publisher"] = _to_str_or_none(coerced["publisher"])
    if "edition" in coerced:
        coerced["edition"] = _to_str_or_none(coerced["edition"])
    if "year" in coerced:
        coerced["year"] = _to_int_or_none(coerced["year"])
    if "is_editor" in coerced:
        coerced["is_editor"] = _to_bool(coerced["is_editor"], default=False)
    return coerced
