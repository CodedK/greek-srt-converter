"""greek_srt/timing.py -- SubRip timecode parsing, shifting (+/- ms), and formatting.

Pure functions over str. This module never touches the filesystem.
"""

from __future__ import annotations

import re
from .clean import TIMECODE_RE, split_lines_keep

_TC_SUB_RE = re.compile(
    r"^([ \t]*)(-?\d{1,4}:[0-5]\d:[0-5]\d[,.]\d{1,3})"
    r"([ \t]*-->[ \t]*)"
    r"(-?\d{1,4}:[0-5]\d:[0-5]\d[,.]\d{1,3})"
    r"((?:[ \t]+X1:\d+[ \t]+X2:\d+[ \t]+Y1:\d+[ \t]+Y2:\d+)?[ \t]*)$"
)


def parse_timecode(tc_str: str) -> int:
    """Parse HH:MM:SS,mmm or HH:MM:SS.mmm to total milliseconds."""
    tc_str = tc_str.strip()
    is_negative = tc_str.startswith("-")
    if is_negative:
        tc_str = tc_str[1:]

    parts = tc_str.replace(".", ",").split(",")
    hms = parts[0].split(":")
    ms = int(parts[1].ljust(3, "0")[:3]) if len(parts) > 1 else 0

    hours = int(hms[0])
    minutes = int(hms[1])
    seconds = int(hms[2])

    total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + ms
    return -total_ms if is_negative else total_ms


def format_timecode(ms: int) -> str:
    """Convert total milliseconds to HH:MM:SS,mmm format (clamped at 0)."""
    if ms < 0:
        ms = 0

    seconds, milliseconds = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def shift_timecode_line(line: str, delta_ms: int) -> str:
    """Shift start and end timecodes in a SubRip timecode line by `delta_ms`."""
    if delta_ms == 0:
        return line

    m = _TC_SUB_RE.match(line)
    if not m:
        return line

    prefix, start_str, arrow, end_str, suffix = m.groups()

    start_ms = parse_timecode(start_str) + delta_ms
    end_ms = parse_timecode(end_str) + delta_ms

    new_start = format_timecode(start_ms)
    new_end = format_timecode(end_ms)

    return f"{prefix}{new_start}{arrow}{new_end}{suffix}"


def shift_document_timing(text: str, delta_ms: int) -> str:
    """Shift all timecode lines in a document by `delta_ms`, preserving line endings."""
    if delta_ms == 0:
        return text

    parts = split_lines_keep(text)
    out: list[tuple[str, str]] = []

    for content, term in parts:
        if TIMECODE_RE.match(content):
            shifted = shift_timecode_line(content, delta_ms)
            out.append((shifted, term))
        else:
            out.append((content, term))

    return "".join(c + t for c, t in out)
