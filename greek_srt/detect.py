"""greek_srt/detect.py -- encoding detection. Standard library only.

Pure functions over bytes. This module never touches the filesystem.
"""

from __future__ import annotations

import codecs
from typing import NamedTuple, Optional

from .models import Confidence

GREEK_START, GREEK_END = 0x0370, 0x03FF
C1_START, C1_END = 0x0080, 0x009F

# Characters that legitimately appear in subtitle text. Written as escapes on
# purpose: several are invisible or confusable in an editor.
PLAUSIBLE_PUNCT = frozenset(
    "\u00a0\u00a3\u00a7\u00a9\u00ab\u00ae\u00b0\u00b7\u00bb"
    "\u2013\u2014\u2015\u2018\u2019\u201a\u201c\u201d\u201e"
    "\u2022\u2026\u2039\u203a\u20ac\u2122\u0384\u0385"
)
LATIN_EXTRA_LETTERS = frozenset(
    "\u0152\u0153\u0160\u0161\u0178\u017d\u017e\u0192"  # OE oe S-caron s-caron Y-diaeresis Z-caron z-caron florin
)

# Order is also the tie-break order. `latin1` is deliberately absent: it decodes
# every byte sequence and would make detection unfalsifiable (BUG 2b).
SINGLE_BYTE_CANDIDATES = ("cp1253", "iso-8859-7", "cp1252")

# UTF-32 first: BOM_UTF32_LE starts with BOM_UTF16_LE.
BOM_TABLE = (
    (codecs.BOM_UTF32_LE, "utf-32-le"),
    (codecs.BOM_UTF32_BE, "utf-32-be"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16-le"),
    (codecs.BOM_UTF16_BE, "utf-16-be"),
)

# The one substitution applied when turning a detected name into a read codec.
# "utf-8" does NOT strip a BOM; "utf-8-sig" does, and is byte-identical on
# BOM-less input. 305 of 391 real files carry a UTF-8 BOM.
_READ_OVERRIDES = {"utf-8": "utf-8-sig"}


class Detection(NamedTuple):
    encoding: Optional[str]
    confidence: Optional[Confidence]
    reason: str


def read_codec(name: str) -> str:
    """The codec to actually decode with, given a detected encoding name."""
    return _READ_OVERRIDES.get(name, name)


def _is_greek(ch: str) -> bool:
    return GREEK_START <= ord(ch) <= GREEK_END


def _is_ascii_alpha(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def _is_latin1_letter(ch: str) -> bool:
    o = ord(ch)
    if 0x00C0 <= o <= 0x00FF and o not in (0x00D7, 0x00F7):
        return True
    return ch in LATIN_EXTRA_LETTERS


def score_decoded(text: str) -> int:
    """Higher is more plausible as real subtitle text. See section 5.4."""
    score = 0
    n = len(text)
    for i, ch in enumerate(text):
        o = ord(ch)
        if o < 0x80:
            continue
        if C1_START <= o <= C1_END:
            # No authoring tool emits C1 controls. THIS is the signal that
            # separates cp1253 from iso-8859-7.
            score -= 100
        elif _is_greek(ch):
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < n else ""
            if (prev and _is_ascii_alpha(prev)) or (nxt and _is_ascii_alpha(nxt)):
                score -= 10   # Greek glued to a Latin word => wrong codec
            else:
                score += 6
        elif _is_latin1_letter(ch):
            score += 3
        elif ch in PLAUSIBLE_PUNCT:
            score += 2
        else:
            score -= 8
    return score


def detect_encoding(raw: bytes) -> Detection:
    """Detect the encoding of a WHOLE file buffer. Never pass a prefix."""
    if raw == b"":
        return Detection("utf-8", Confidence.CERTAIN, "empty file")

    for bom, name in BOM_TABLE:
        if raw.startswith(bom):
            return Detection(name, Confidence.CERTAIN, "BOM " + bom.hex(" ").upper())

    if b"\x00" in raw:
        head = raw[:4096]
        even = sum(1 for i in range(0, len(head), 2) if head[i] == 0)
        odd = sum(1 for i in range(1, len(head), 2) if head[i] == 0)
        floor = len(head) // 8
        if odd > even * 4 and odd > floor:
            return Detection("utf-16-le", Confidence.GUESS,
                             "BOM-less UTF-16LE: NULs at odd offsets")
        if even > odd * 4 and even > floor:
            return Detection("utf-16-be", Confidence.GUESS,
                             "BOM-less UTF-16BE: NULs at even offsets")
        return Detection(None, None, "binary content (NUL bytes)")

    if not any(b >= 0x80 for b in raw):
        return Detection("ascii", Confidence.CERTAIN, "no byte >= 0x80")

    try:
        raw.decode("utf-8")
        return Detection("utf-8", Confidence.CERTAIN,
                         "strict UTF-8 decode of whole buffer")
    except UnicodeDecodeError:
        pass

    scored: list[tuple[int, str]] = []
    for candidate in SINGLE_BYTE_CANDIDATES:
        try:
            text = raw.decode(candidate)
        except UnicodeDecodeError:
            continue
        scored.append((score_decoded(text), candidate))

    if not scored:
        return Detection(None, None, "no single-byte candidate decoded")

    best = max(s for s, _ in scored)
    winners = [c for s, c in scored if s == best]
    winner = next(c for c in SINGLE_BYTE_CANDIDATES if c in winners)
    ordered = sorted((s for s, _ in scored), reverse=True)
    margin = ordered[0] - ordered[1] if len(ordered) > 1 else ordered[0]
    if len(winners) > 1:
        return Detection(winner, Confidence.GUESS,
                         f"tie {winners}; decodes identical; tie-break order")
    return Detection(winner, Confidence.GUESS,
                     f"scores={sorted(scored, reverse=True)} margin={margin}")
