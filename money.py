"""Paisa (integer) helpers. Float kabhi use nahi hota."""
import re

MAX_PAISE = 10_000_000 * 100  # Rs 1 crore se zyada allow nahi
_RE = re.compile(r"^\d{1,9}(\.\d{1,2})?$")


def parse_rupees(text, allow_zero=False):
    """'50', '50.5', 'Rs 50.25', '1,000' -> paise (int). Galat input par None."""
    if text is None:
        return None
    t = text.strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    t = t.replace(" ", "")
    if not _RE.match(t):
        return None
    whole, _, frac = t.partition(".")
    paise = int(whole) * 100 + int((frac + "00")[:2])
    if paise > MAX_PAISE:
        return None
    if paise == 0 and not allow_zero:
        return None
    return paise


def fmt(paise):
    sign = "-" if paise < 0 else ""
    p = abs(int(paise))
    return f"{sign}₹{p // 100}.{p % 100:02d}"
