"""Har user input ki validation."""
import re
from html import escape

_UPI_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,255}@[a-z][a-z0-9]{1,63}$")
_CODE_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")


def clean_upi(text):
    t = (text or "").strip().lower()
    return t if _UPI_RE.match(t) else None


def clean_code(text):
    t = (text or "").strip().upper()
    return t if _CODE_RE.match(t) else None


def clean_text(text, max_len, min_len=1):
    t = (text or "").strip()
    if len(t) < min_len or len(t) > max_len:
        return None
    return t


def parse_int(text, min_value=0, max_value=10**12):
    t = (text or "").strip()
    if not t.isdigit():
        return None
    v = int(t)
    return v if min_value <= v <= max_value else None


def esc(value):
    return escape(str(value if value is not None else ""))


def mask_name(name):
    n = (name or "").strip()
    if not n:
        return "User***"
    return esc(n[:2]) + "***"
