"""Immutable value types exchanged across the greek_srt core boundary.

This module imports nothing from its siblings. Dependency direction is strictly
models <- detect, clean <- fileio <- convert.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path


class Target(enum.Enum):
    """The encoding a run converts *to*. Chosen once per run, never per file."""

    UTF_8 = "utf-8"
    ISO_8859_7 = "iso-8859-7"

    @property
    def codec(self) -> str:
        """Exact Python codec name for str.encode(). Never 'utf-8-sig' -- no BOM is written."""
        return self.value

    @property
    def label(self) -> str:
        """Human-facing name for the GUI radio button and the CLI menu."""
        return "UTF-8" if self is Target.UTF_8 else "Greek ISO-8859-7"


class Action(enum.Enum):
    """What convert() will do with a file. Decided entirely by scan()."""

    CONVERT = "convert"
    """Bytes differ from the target rendering; convert() will rewrite the file."""

    NEEDS_REVIEW = "needs_review"
    """Same as CONVERT, but folding would drop more than LOSS_GUARD of the file's
    non-ASCII characters -- almost always a non-Greek subtitle aimed at ISO-8859-7.
    convert() will process it, but the GUI leaves the row UNTICKED by default."""

    ALREADY_TARGET = "already_target"
    """Re-rendering reproduces the bytes on disk exactly; convert() writes nothing."""

    UNREADABLE = "unreadable"
    """The file may not be rewritten; `error` explains why."""


class Confidence(enum.Enum):
    """How much trust to place in FileReport.encoding."""

    CERTAIN = "certain"
    """Proven by a BOM, by a strict whole-buffer UTF-8 decode, or by pure ASCII."""

    GUESS = "guess"
    """Chosen by heuristic scoring between single-byte codecs; may be wrong."""


@dataclass(frozen=True, slots=True, order=True)
class LossyChange:
    """One source character that folding rewrites or deletes, with its tally."""

    char: str
    """The offending source character; always exactly one code point."""

    replacement: str
    """What it becomes; the empty string means the character is deleted outright."""

    count: int
    """Occurrences in the whole decoded file; always >= 1."""

    @property
    def dropped(self) -> bool:
        return self.replacement == ""


@dataclass(frozen=True, slots=True)
class FileStamp:
    """Staleness token captured at scan time and re-checked before writing."""

    size: int
    mtime_ns: int


@dataclass(frozen=True, slots=True)
class FileReport:
    """Read-only verdict on a single .srt file, produced by scan()."""

    path: Path
    """Absolute path to the .srt file. Plain Path -- never the \\\\?\\ long-path form."""

    stamp: FileStamp
    """Size + mtime at scan time; convert() re-checks it to detect edits."""

    encoding: str | None
    """Python codec name detected for the source; None iff action is UNREADABLE."""

    confidence: Confidence | None
    """Trust level of `encoding`; None iff action is UNREADABLE."""

    action: Action
    target: Target
    """The target this report was scanned against; convert() rejects mixed targets."""

    lossy: tuple[LossyChange, ...]
    """Characters folding would rewrite or drop, sorted by (-count, ord(char))."""

    loss_ratio: float
    """dropped non-ASCII characters / total non-ASCII characters. 0.0 for UTF-8."""

    preview: tuple[str, ...]
    """Up to PREVIEW_LINES decoded line contents, terminators stripped."""

    error: str | None
    """Reason the file is UNREADABLE; None for every other action."""

    time_offset_ms: int = 0
    """Time offset in milliseconds applied during rendering."""

    @property
    def size(self) -> int:
        return self.stamp.size

    @property
    def dropped_count(self) -> int:
        """Total characters that would be deleted; the GUI's 'N chars stripped' badge."""
        return sum(c.count for c in self.lossy if c.dropped)

    @property
    def replaced_count(self) -> int:
        return sum(c.count for c in self.lossy if not c.dropped)

    @property
    def writable(self) -> bool:
        """True iff convert() will accept this report."""
        return self.action in (Action.CONVERT, Action.NEEDS_REVIEW)


@dataclass(frozen=True, slots=True)
class ConvertResult:
    """Outcome of one file, produced by convert(). Exactly one per input report."""

    path: Path
    ok: bool
    """True iff the file on disk now holds the rendered bytes."""

    status: str
    """'converted' | 'unchanged' | 'failed'."""

    code: str | None
    """Stable failure token; None iff ok. See the table in section 7.5."""

    source_encoding: str | None
    target_encoding: str
    backup: str
    """'created' | 'kept-existing' | 'disabled' | 'not-needed'."""

    backup_path: Path | None
    lossy: tuple[LossyChange, ...]
    bytes_written: int
    """Size of the new file; exactly 0 when ok is False or status is 'unchanged'."""

    error: str | None
    """Human-readable failure reason; None iff ok is True."""

    time_offset_ms: int = 0
    """Time offset in milliseconds applied during rendering."""
