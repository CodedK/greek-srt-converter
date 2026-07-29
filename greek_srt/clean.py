"""greek_srt/clean.py -- ISO-8859-7 character folding and byte rendering.

Pure functions over str. This module never touches the filesystem.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple

from .models import LossyChange, Target

# ---------------------------------------------------------------- line handling

# Splits into (content, terminator) pairs. Rejoining reproduces the input EXACTLY,
# including mixed and CR-only line endings. NEVER use str.splitlines(): it also
# splits on \x0b \x0c \x1c \x1d \x1e \x85 \u2028 \u2029 and silently changes the
# line count.
_LINE_RE = re.compile(r"([^\r\n]*)(\r\n|\r|\n|\Z)")


def split_lines_keep(text: str) -> list[tuple[str, str]]:
    """Return [(content, terminator), ...]; "".join(c + t for c, t in ...) == text."""
    out: list[tuple[str, str]] = []
    for m in _LINE_RE.finditer(text):
        content, term = m.group(1), m.group(2)
        if content == "" and term == "":
            continue                      # zero-width match at end of string
        out.append((content, term))
    return out


def split_lines(text: str) -> list[str]:
    """Line contents only, terminators discarded. Used for the preview."""
    return [c for c, _ in split_lines_keep(text)]


# ASCII-only whitespace classes are REQUIRED. Python's \s matches U+1680,
# U+2000-200A, U+202F, U+205F, U+3000, U+2028, U+2029 -- none of which
# ISO-8859-7 can encode. A \s-based regex would classify "1\u2003" as an index
# line, skip folding, and the encode would then raise.
INDEX_RE = re.compile(r"^[ \t]*\d{1,9}[ \t]*$")
TIMECODE_RE = re.compile(
    r"^[ \t]*-?\d{1,4}:[0-5]\d:[0-5]\d[,.]\d{1,3}"
    r"[ \t]*-->[ \t]*"
    r"-?\d{1,4}:[0-5]\d:[0-5]\d[,.]\d{1,3}"
    r"(?:[ \t]+X1:\d+[ \t]+X2:\d+[ \t]+Y1:\d+[ \t]+Y2:\d+)?[ \t]*$"
)

# ---------------------------------------------------------------- the fold table

ISO_FOLD_MAP: dict[str, str] = {
    # --- Quotation marks -------------------------------------------------
    "\u2018": "'",        # LEFT SINGLE QUOTATION MARK   (byte A1 = GBP-conflict: shows as ΅ on cp1253)
    "\u2019": "'",        # RIGHT SINGLE QUOTATION MARK  (byte A2: shows as Ά on cp1253)
    "\u201a": "'",        # SINGLE LOW-9 QUOTATION MARK
    "\u201b": "'",        # SINGLE HIGH-REVERSED-9 QUOTATION MARK
    "\u2032": "'",        # PRIME
    "\u02bc": "'",        # MODIFIER LETTER APOSTROPHE
    "\u2039": "'",        # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
    "\u203a": "'",        # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
    "\u00b4": "\u0384",   # ACUTE ACCENT -> GREEK TONOS (byte B4)
    "\u201c": "\"",       # LEFT DOUBLE QUOTATION MARK
    "\u201d": "\"",       # RIGHT DOUBLE QUOTATION MARK
    "\u201e": "\"",       # DOUBLE LOW-9 QUOTATION MARK
    "\u201f": "\"",       # DOUBLE HIGH-REVERSED-9 QUOTATION MARK
    "\u2033": "\"",       # DOUBLE PRIME
    "\u3003": "\"",       # DITTO MARK
    # U+00AB / U+00BB guillemets are ABSENT on purpose: bytes AB/BB, cp1253 agrees.
    # --- Dashes ----------------------------------------------------------
    # U+2015 HORIZONTAL BAR is ABSENT on purpose: byte AF, identical in cp1253.
    # It is THE Greek dialogue dash, and is the fold TARGET for en/em dashes.
    "\u2013": "\u2015",   # EN DASH  -> HORIZONTAL BAR
    "\u2014": "\u2015",   # EM DASH  -> HORIZONTAL BAR
    "\u2010": "-",        # HYPHEN
    "\u2011": "-",        # NON-BREAKING HYPHEN
    "\u2012": "-",        # FIGURE DASH
    "\u2212": "-",        # MINUS SIGN
    "\u2043": "-",        # HYPHEN BULLET
    "\ufe58": "-",        # SMALL EM DASH
    "\ufe63": "-",        # SMALL HYPHEN-MINUS
    "\uff0d": "-",        # FULLWIDTH HYPHEN-MINUS
    "\u00af": "-",        # MACRON
    "\u2500": "-",        # BOX DRAWINGS LIGHT HORIZONTAL
    # --- Ellipsis --------------------------------------------------------
    "\u2026": "...",      # HORIZONTAL ELLIPSIS
    "\u2025": "..",       # TWO DOT LEADER
    "\u22ef": "...",      # MIDLINE HORIZONTAL ELLIPSIS
    # --- Greek-specific --------------------------------------------------
    "\u037e": ";",        # GREEK QUESTION MARK -> ASCII semicolon
    "\u0387": "\u00b7",   # GREEK ANO TELEIA -> MIDDLE DOT (byte B7)
    "\u037a": "",         # GREEK YPOGEGRAMMENI (byte AA, undefined in cp1253)
    "\u02b9": "\u0384",   # MODIFIER LETTER PRIME
    "\u02ca": "\u0384",   # MODIFIER LETTER ACUTE ACCENT
    "\u00b5": "\u03bc",   # MICRO SIGN -> GREEK SMALL MU
    # --- Spaces -> plain space -------------------------------------------
    "\u00a0": " ", "\u1680": " ",
    "\u2000": " ", "\u2001": " ", "\u2002": " ", "\u2003": " ", "\u2004": " ",
    "\u2005": " ", "\u2006": " ", "\u2007": " ", "\u2008": " ", "\u2009": " ",
    "\u200a": " ", "\u202f": " ", "\u205f": " ", "\u3000": " ",
    # --- Invisible -> deleted --------------------------------------------
    "\u200b": "", "\u200c": "", "\u200d": "", "\u200e": "", "\u200f": "",
    "\u2060": "", "\ufeff": "", "\u00ad": "",
    "\u202a": "", "\u202b": "", "\u202c": "", "\u202d": "", "\u202e": "",
    # --- Music glyphs (song lyrics: very common in subtitles) ------------
    "\u266a": "#",        # EIGHTH NOTE
    "\u266b": "#",        # BEAMED EIGHTH NOTES
    "\u266c": "#",        # BEAMED SIXTEENTH NOTES
    "\u2669": "#",        # QUARTER NOTE
    "\U0001f3b5": "#",    # MUSICAL NOTE (emoji)
    "\U0001f3b6": "#",    # MULTIPLE MUSICAL NOTES (emoji)
    "\u266f": "#",        # MUSIC SHARP SIGN
    "\u266d": "b",        # MUSIC FLAT SIGN
    "\u266e": "",         # MUSIC NATURAL SIGN
    # --- Bullets and marks -----------------------------------------------
    "\u2022": "*", "\u2023": "*", "\u25cf": "*", "\u25aa": "*", "\u25a0": "*",
    "\u2020": "+", "\u2021": "++",
    "\u2764": "<3", "\u2665": "<3",
    # --- Symbols ----------------------------------------------------------
    "\u00ae": "(R)",      # REGISTERED SIGN
    "\u2122": "(TM)",     # TRADE MARK SIGN
    "\u00d7": "x", "\u00f7": "/", "\u2044": "/", "\u2215": "/",
    "\u2030": "%%",       # PER MILLE
    "\u2116": "No.",      # NUMERO SIGN
    "\u00b9": "1", "\u00bc": "1/4", "\u00be": "3/4",
    "\u00a2": "c", "\u00a5": "YEN", "\u00a4": "", "\u00b6": "",
    "\u00aa": "a", "\u00ba": "o", "\u00a1": "!", "\u00bf": "?",
    # U+00A9 U+00A3 U+00B1 U+00BD U+00B2 U+00B3 U+00A7 U+00B0 U+00A6 U+00B7
    # are ABSENT on purpose: all ISO-8859-7-encodable and cp1253 agrees.
    # --- Currency sitting on cp1253-conflicting slots ---------------------
    "\u20ac": "EUR",      # EURO SIGN    (byte A4 = currency sign in cp1253)
    "\u20af": "GRD",      # DRACHMA SIGN (byte A5 = yen sign in cp1253)
    # --- Latin ligatures / stroked letters (foreign names) ----------------
    "\u0152": "OE", "\u0153": "oe", "\u00c6": "AE", "\u00e6": "ae",
    "\u00df": "ss", "\u0141": "L", "\u0142": "l",
    "\u00d8": "O", "\u00f8": "o", "\u00d0": "D", "\u00f0": "d",
    "\u00de": "Th", "\u00fe": "th", "\u0110": "D", "\u0111": "d",
}

_KEEP_CONTROLS = frozenset({0x09, 0x0A, 0x0D})


class StructureChanged(Exception):
    """The folder altered the cue skeleton. Never write such a file."""


class Rendered(NamedTuple):
    data: bytes
    lossy: tuple[LossyChange, ...]
    loss_ratio: float


def fold_to_iso(text: str) -> tuple[str, dict[str, tuple[str, int]], dict[str, int]]:
    """Fold one TEXT line. Total: the result always encodes to iso-8859-7.

    Returns (folded, replaced_map, dropped_counts) where replaced_map is
    char -> (substitution, count).
    """
    replaced: dict[str, tuple[str, int]] = {}
    dropped: dict[str, int] = {}
    out: list[str] = []
    for ch in text:
        cp = ord(ch)
        # R6: controls are all ISO-8859-7-encodable, so they need this rule.
        if (cp < 0x20 or cp == 0x7F or 0x80 <= cp <= 0x9F) and cp not in _KEEP_CONTROLS:
            dropped[ch] = dropped.get(ch, 0) + 1
            continue
        sub = ISO_FOLD_MAP.get(ch)
        if sub is not None:
            if sub == "":
                dropped[ch] = dropped.get(ch, 0) + 1
            else:
                prev_sub, prev_n = replaced.get(ch, (sub, 0))
                replaced[ch] = (sub, prev_n + 1)
            out.append(sub)
            continue
        try:
            ch.encode("iso-8859-7")
            out.append(ch)
            continue
        except UnicodeEncodeError:
            pass
        # Generic fallback: strip combining marks.
        stripped = "".join(c for c in unicodedata.normalize("NFKD", ch)
                           if not unicodedata.combining(c))
        try:
            stripped.encode("iso-8859-7")
        except UnicodeEncodeError:
            stripped = ""
        if stripped:
            prev_sub, prev_n = replaced.get(ch, (stripped, 0))
            replaced[ch] = (stripped, prev_n + 1)
            out.append(stripped)
        else:
            dropped[ch] = dropped.get(ch, 0) + 1
    return "".join(out), replaced, dropped


def fold_document(text: str) -> tuple[str, dict[str, tuple[str, int]], dict[str, int]]:
    """Fold a whole document, leaving structural lines verbatim.

    Line terminators are preserved EXACTLY, including mixed and CR-only files.
    Raises StructureChanged if the cue skeleton moved or a '-->' was forged.
    """
    parts = split_lines_keep(text)
    before = [i for i, (c, _) in enumerate(parts) if TIMECODE_RE.match(c)]
    out: list[tuple[str, str]] = []
    replaced: dict[str, tuple[str, int]] = {}
    dropped: dict[str, int] = {}
    for content, term in parts:
        if TIMECODE_RE.match(content) or INDEX_RE.match(content):
            out.append((content, term))     # structural: verbatim, never folded
            continue
        folded, r, d = fold_to_iso(content)
        for k, (sub, v) in r.items():
            prev_sub, prev_n = replaced.get(k, (sub, 0))
            replaced[k] = (sub, prev_n + v)
        for k, v in d.items():
            dropped[k] = dropped.get(k, 0) + v
        out.append((folded, term))
    after = [i for i, (c, _) in enumerate(out) if TIMECODE_RE.match(c)]
    if len(out) != len(parts) or before != after:
        raise StructureChanged(f"cue skeleton changed: {before} -> {after}")
    for i, (c, _) in enumerate(out):
        if "-->" in c and "-->" not in parts[i][0]:
            raise StructureChanged(
                f"line {i} gained a '-->' token: {parts[i][0]!r} -> {c!r}")
    return "".join(c + t for c, t in out), replaced, dropped


def _to_lossy(replaced: dict[str, tuple[str, int]], dropped: dict[str, int]
              ) -> tuple[LossyChange, ...]:
    items = [LossyChange(ch, sub, n) for ch, (sub, n) in replaced.items()]
    items += [LossyChange(ch, "", n) for ch, n in dropped.items()]
    items.sort(key=lambda c: (-c.count, ord(c.char)))
    return tuple(items)


def render(text: str, target: Target) -> Rendered:
    """The EXACT bytes convert() will write. Pure; the single source of truth.

    Preconditions: `text` has already had every U+FEFF removed by the caller.
    Postcondition for ISO_8859_7: the encode cannot raise (fuzz-verified).
    """
    if target is Target.ISO_8859_7:
        folded, replaced, dropped = fold_document(text)
    else:
        folded, replaced, dropped = text, {}, {}
    lossy = _to_lossy(replaced, dropped)
    non_ascii = sum(1 for ch in text if ord(ch) >= 0x80)
    lost = sum(c.count for c in lossy if c.dropped and ord(c.char) >= 0x80)
    ratio = (lost / non_ascii) if non_ascii else 0.0
    return Rendered(folded.encode(target.codec), lossy, ratio)
