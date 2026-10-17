"""Short codes: uppercase A-Z0-9 only."""
import re

_NON_ALNUM = re.compile(r"[^A-Z0-9]")


def clean_code(raw: str, max_len: int = 16) -> str:
    return _NON_ALNUM.sub("", (raw or "").upper())[:max_len]
