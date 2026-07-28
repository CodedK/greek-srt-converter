# Implementation Brief — `greek-srt-converter` v1.0

**Repository:** `https://github.com/CodedK/greek-srt-converter` · MIT · owner `CodedK`
**Repo root on disk:** `c:/Users/CodedK/Desktop/Git/Subtitles`
**Target runtime:** Python **3.10+** (3.11.9 is the reference), Windows 11 primary, **zero third-party runtime dependencies**
**Deliverable:** a `greek_srt` core package plus two front-ends (`cli.py`, `gui.py`) and a `tests/` suite

This document is the complete specification. Every fork is already decided. There is nothing to
choose, nothing to research, and nobody to ask. Where this document contradicts anything you may
infer from the existing code, **this document wins** — the existing code is being fixed, not
preserved.

Every code block marked *reference implementation* was executed and validated on the target machine
before this brief was written. Paste it; do not "improve" it.

---

## 1. What this project is and what you are building

### 1.1 The problem domain

A `.srt` file (SubRip) is a plain-text subtitle file. It looks like this:

```
1
00:00:01,000 --> 00:00:03,500
― Καλημέρα, φίλε.

2
00:00:03,600 --> 00:00:05,900
― Τι κάνεις;
```

Blocks of: an index line, a timecode line containing the literal token `-->`, one or more text
lines, then a blank separator line. **SubRip has no official specification and no encoding
declaration.** The bytes on disk carry no self-description whatsoever, so a program must *guess*
which character encoding a file uses.

Greek subtitles downloaded from the internet arrive in a mix of encodings:

- **UTF-8**, usually with a Byte Order Mark (`EF BB BF`) — the majority of a modern library
- **CP1253** — Windows Greek, the historical default of Greek Windows text editors
- **ISO-8859-7** — the ISO Greek standard, what old standalone hardware players and TVs expect
- occasionally **UTF-16** with a BOM

A media player configured for one and fed another renders *mojibake* — `Καλημέρα` becomes
`ÎšÎ±Î»Î·Î¼Î­ÏÎ±` or `Ãáëçìýñá`. The tool's job is to normalise a whole folder to one chosen
encoding, in place, safely.

### 1.2 What you are building

A GUI is being added to an existing command-line script, and the script is being fixed. Concretely:

1. **Extract a core package** `greek_srt/` with exactly two public entry points:
   - `scan(...)` — reads only, **structurally incapable of writing**, returns a list of verdicts
   - `convert(...)` — the only function in the entire codebase that writes to disk
2. **Rebuild the existing CLI** on top of that core (`cli.py`).
3. **Add a tkinter GUI** (`gui.py`) that is a thin rendering of `list[FileReport]`.
4. **Fix three confirmed bugs** in the existing script plus a fourth found during research.
5. **Add a pytest suite.**

The scan/convert split is the whole point of the architecture. It gives the user a read-only preview
of exactly what will happen — including which characters will be lost — before a single byte is
written, and it gives the CLI a working dry-run for free.

### 1.3 Two directions, chosen per run

| Target | Codec | Why a user picks it |
|---|---|---|
| **UTF-8** | `utf-8` (never `utf-8-sig` — no BOM is ever written) | Modern players, VLC, phones, Plex |
| **Greek ISO-8859-7** | `iso-8859-7` | Old standalone DVD players, hardware media boxes, TVs |

ISO-8859-7 is a single-byte encoding that can only represent Greek, ASCII and a small punctuation
set. Converting *to* it is inherently lossy for anything else, which is why the loss guard in §5.5
is mandatory.

### 1.4 Delivery, now and later

**Now:** runs from source. `python gui.py` and `python cli.py`. Nothing to install.

**Later (explicitly a separate phase — do not build it):** a standalone Windows `.exe` via
PyInstaller. That future phase imposes four constraints on the code you write **today**, all of
which are non-negotiable:

1. **Zero third-party runtime dependencies.** Standard library only. `pytest` is dev-only.
2. **No dynamic imports.** No `importlib.import_module(computed_name)`, no `__import__(name)`, no
   plugin discovery. Every import must be a literal `import x` / `from x import y` that a static
   analyser can see.
3. **Never derive writable paths from `__file__` or `sys.argv[0]`.** Under `--onefile` the app runs
   from a temp extraction directory that is deleted on exit. Settings go in `%APPDATA%`.
4. **`sys.stdout` and `sys.stderr` are `None` under `--windowed`.** `gui.py` must never call
   `sys.stdout.write()` or rely on `print()` for anything the user needs. `cli.py` may print freely.

For reference, a measured build of an equivalent app: `--windowed --onefile` = **9.20 MB**,
onedir = **14.70 MB**, both exit 0. No `--hidden-import` or `--add-data` is required for tkinter.
**Do not attempt `--exclude-module` trimming** — excluding `urllib` breaks `pathlib` outright, and a
conservative exclusion set saved only 0.36 MB.

---

## 2. Current state: the existing script and its bugs

### 2.1 The file

`c:/Users/CodedK/Desktop/Git/Subtitles/CONVERT TO GREEK THEN UTF8.py` — 431 lines, 15,280 bytes,
one commit (`b4b3b90 Initial commit`). The spaces in the filename make it un-importable as a Python
module, which is why it is being renamed.

Its four functions:

| Lines | Function | What it does |
|---|---|---|
| 10–37 | `detect_encoding(file_path)` | Tries 7 codecs in a fixed order, returns the first that decodes `read(1024)` |
| 40–117 | `clean_for_iso_8859_7(text)` | 23-entry replacement table, then drops unencodable characters |
| 120–326 | `convert_srt_encoding(...)` | Globs `*.srt`, detects, backs up, re-encodes in place, prints a log |
| 329–426 | `main()` | Interactive prompts: mode, folder, recursive, backup, dry-run |

Its user-visible behaviour: prompt for mode `1` (→ UTF-8) or `2` (→ ISO-8859-7), a folder path, a
recursive yes/no, a backup yes/no (default yes), a dry-run yes/no. Then it prints a numbered file
list and a per-file technical log, writing `__orig__<name>.srt` backups.

### 2.2 BUG 1 — `clean_for_iso_8859_7()` is dead code

Confirmed: the function defined at line 40 is **never called anywhere in the file**.

The consequence is that the headline feature does not work. At line 263 the ISO-8859-7 path calls
`content.encode("iso-8859-7")` on the **raw** decoded text. The moment that text contains a curly
double quote, an em dash or an ellipsis — which is most subtitle files — the encode raises, and
lines 273–285 catch it and **write UTF-8 instead**. The user asked for ISO-8859-7 *because their
player needs it*; silently handing back UTF-8 produces exactly the mojibake they were trying to
avoid.

**Also confirmed by measurement:** a UTF-8-with-BOM file in Greek mode fails at line 263 because
`'\ufeff'.encode('iso-8859-7')` raises. So for BOM'd files — 305 of 391 in the reference library —
**Greek mode is unconditionally a no-op.**

**Fix:** wire the folder in before the encode, and **delete the UTF-8 fallback entirely**. After
folding, `.encode("iso-8859-7")` cannot fail by construction (fuzz-verified: 0 failures over 600k
random codepoints and an exhaustive 65,024-codepoint BMP sweep).

**Also confirmed:** 8 of the table's 23 entries destroy characters ISO-8859-7 represents natively.
The corrected table is §6.

### 2.3 BUG 2 — `detect_encoding()` is unsound

**(a) It does not validate the whole file.** The brief that spawned this project said "1024
characters". That is wrong in an interesting way. `TextIOWrapper.read(1024)` pulls a full
`BufferedReader` chunk from the raw stream, so it actually validates the first **8191 bytes**.
Binary-searched: a bad byte at offset 8000 is caught; at offset 8192 it is missed and the later full
read raises. The bug is real; the boundary is a CPython buffering implementation detail
(`io.DEFAULT_BUFFER_SIZE`), not a documented constant. **Reading the whole buffer once removes the
dependence on it.**

**(b) The catch-all is `iso-8859-7`, not `latin1`.** The original brief blamed `latin1` at list
position 5. Measured: `iso-8859-7` sits at position **2** and has only **3 undefined byte values**
(`0xAE`, `0xD2`, `0xFF`), so it already accepts 253/256 single bytes. `windows-1252`, `cp1253`,
`latin1` and `ascii` are **unreachable dead entries**. `latin1` is genuinely a catch-all (0 undefined
slots) but is never reached.

The consequence is worse than "detection never fails". Measured end-to-end:

```
cp1253 greek             -> detected 'iso-8859-7'   WRONG
cp1253 greek + smart     -> detected 'iso-8859-7'   WRONG
utf-8-sig greek          -> detected 'utf-8'        BOM left in the text
utf-16 with BOM          -> detected 'windows-1252' WRONG (utf-16 is listed last)
binary PNG               -> detected 'latin1'       a PNG "successfully decoded"
```

CP1253 — the single most common encoding for Greek subtitles on Windows — **can never be
returned at all**. And because line 214 then compares `detected == target`, a genuine CP1253 file in
Greek mode is *skipped as "already ISO-8859-7"*. In UTF-8 mode it is decoded with the wrong table:
measured, `'Ά, «Τι κάνεις;» — είπε'` silently becomes `'’, «Τι κάνεις;» \x97 είπε'`.

**Fix:** §5. Note that the *originally proposed* fix — "score by how many undefined slots are
hit" — was tested and **does not work**; see §5.2 for why and what replaces it.

### 2.4 BUG 3 — writes are not atomic

Lines 266 and 289 both do `open(srt_file, "w", encoding=...)`. Measured: the file's size is **0
bytes immediately after `open()` returns, before any write**. `"w"` truncates first. A crash, a
power loss, or a `UnicodeEncodeError` between truncate and write destroys the subtitle.

**Fix:** write a temp file in the **same directory**, `fsync` it, then `os.replace()`. §7.

### 2.5 BUG 4 (found during research) — backups are re-scanned and destroyed

`folder.glob("*.srt")` and `folder.rglob("*.srt")` both match `__orig__Ep01.srt`. Measured: both
return `['Ep01.srt', '__orig__Ep01.srt']`.

So on the **second** run of the tool:

1. `__orig__Ep01.srt` is detected and marked for conversion;
2. it is converted — **destroying the only pristine copy of the original**;
3. `__orig____orig__Ep01.srt` is written as its "backup".

**Fix:** exclude names starting with `__orig__`, case-insensitively (NTFS is case-insensitive).

### 2.6 Undocumented behaviour that also changes

Not a listed bug, but it mutates every file the script touches and must be stated. The script reads
and writes in **text mode with the default `newline=None`**. Universal-newline translation collapses
`\r\n`/`\r`/`\n` to `\n` on read and expands `\n` to `os.linesep` on write. Measured:

| Input | Bytes in → out | Byte-identical |
|---|---|---|
| CRLF `.srt` | 43 → 43 | yes (by accident) |
| **LF `.srt`** | **39 → 43** | **no — every line ending rewritten** |
| **Mixed CRLF/LF/CR** | **52 → 54** | **no** |
| **CR-only (classic Mac)** | **39 → 43** | **no** |

Same input, different output bytes depending on the platform. The new core is **bytes in, bytes
out** and preserves line endings exactly (§7.2).

Line 251 also uses `content.splitlines()` for its line count. `str.splitlines()` splits on `\x0b`,
`\x0c`, `\x1c`, `\x1d`, `\x1e`, `\x85`, `\u2028` and `\u2029` as well as CR/LF — measured, a 3-line
string reports 6 lines. **`splitlines()` is banned project-wide.**

---

## 3. Target architecture

### 3.1 Final file layout (paths relative to repo root)

```
greek_srt/
    __init__.py      re-exports only, no logic
    models.py        immutable value types; imports nothing from the package
    detect.py        encoding detection; pure functions over bytes; no filesystem access
    clean.py         ISO-8859-7 folding + render(); pure functions over str; no filesystem access
    fileio.py        the ONLY module that touches the filesystem          [added on research evidence]
    convert.py       scan() + convert(); orchestration only
cli.py               interactive CLI, rebuilt on the core
gui.py               tkinter front-end
conftest.py          empty; its presence puts the repo root on sys.path for pytest
requirements-dev.txt  contains exactly: pytest>=7
tests/
    test_detect.py
    test_clean.py
    test_fileio.py
    test_convert.py
    test_gui_smoke.py
README.md            updated (§11 step 12)
LICENSE              unchanged
```

> **`greek_srt/fileio.py` is added on research evidence.** Reason: the guarantee "`scan()` is
> structurally incapable of writing" is only auditable if there is exactly one module that can write
> and `scan()` provably calls none of its writing functions. The atomic-write, long-path, backup and
> read-only-attribute logic is ~180 lines and would otherwise drown `convert.py`.

### 3.2 Dependency direction — strictly one-way

```
models  <-  detect
models  <-  clean
models, clean  <-  fileio
models, detect, clean, fileio  <-  convert
greek_srt  <-  cli.py, gui.py
```

- `models.py` must not import from any sibling.
- Nothing in `greek_srt/` may import `tkinter`, `argparse`, or call `print()`. **The core never
  prints and never prompts. `input()` must not appear anywhere in `greek_srt/`.**
- `cli.py` and `gui.py` must never touch the filesystem directly except through `greek_srt`. The one
  exception is `gui.py`'s settings file in `%APPDATA%`, which is not subtitle data.

### 3.3 The scan/convert boundary — two invariants

**INV-1 — `scan()` is read-only.** After `scan()` returns, every file in the tree is byte-identical
to before, and every `st_mtime_ns` is unchanged. This is a test assertion (§10), not a comment.
`scan()` calls only `fileio.stamp()`, `fileio.read_bytes()` and `fileio.iter_srt_files()`.

**INV-2 — no partial writes.** At every instant, a subtitle path holds either the complete old
content or the complete new content. Never truncated, never empty, never half-written.
**`open(path, "w")` is banned project-wide.**

### 3.4 The rename

```bash
git mv "CONVERT TO GREEK THEN UTF8.py" cli.py
```

History is preserved. This is decided; do not create a new file and delete the old one.

---

## 4. Full API contract

### 4.1 `greek_srt/models.py` — complete and final

```python
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
```

**Two type decisions, stated so they are not "improved" later.**

*Lossy is `tuple[LossyChange, ...]`, not a dict.* A `dict` field on a `frozen=True` dataclass makes
`hash()` raise `TypeError: unhashable type: 'dict'` (measured), so the model could not go in a set
or be a dict key; `frozen=True` does not freeze a dict's contents, so the immutability claim would be
a lie; and a tuple carries a defined order that the GUI needs for stable rows and the tests need for
stable assertions. Order is **descending by `count`, ties broken ascending by `ord(char)`**.

*Preview is `tuple[str, ...]`.* Produced by `clean.split_lines(text)[:PREVIEW_LINES]` — line contents
only, terminators already separated, so no entry contains `\n` or `\r`. Empty tuple for UNREADABLE.

### 4.2 `greek_srt/detect.py` — public surface

```python
def score_decoded(text: str) -> int: ...
def detect_encoding(raw: bytes) -> Detection: ...
def read_codec(name: str) -> str: ...

class Detection(NamedTuple):
    encoding: str | None
    confidence: Confidence | None
    reason: str
```

Full reference implementation in §5.4.

### 4.3 `greek_srt/clean.py` — public surface

```python
ISO_FOLD_MAP: dict[str, str]                  # 119 entries, section 6.2
INDEX_RE: re.Pattern[str]
TIMECODE_RE: re.Pattern[str]

class StructureChanged(Exception): ...

class Rendered(NamedTuple):
    data: bytes
    lossy: tuple[LossyChange, ...]
    loss_ratio: float

def split_lines_keep(text: str) -> list[tuple[str, str]]: ...
def split_lines(text: str) -> list[str]: ...
def fold_to_iso(line: str) -> tuple[str, dict[str, int], dict[str, int]]: ...
def fold_document(text: str) -> tuple[str, dict[str, int], dict[str, int]]: ...
def render(text: str, target: Target) -> Rendered: ...
```

Full reference implementation in §6.

### 4.4 `greek_srt/fileio.py` — public surface

```python
BACKUP_PREFIX = "__orig__"
TEMP_PREFIX   = ".srtconv-"
TEMP_SUFFIX   = ".tmp"

class FileOpError(Exception):
    code: str
    path: Path
    detail: object

def long_path(p) -> str: ...
def is_excluded(name: str) -> bool: ...
def iter_srt_files(folder: Path, *, recursive: bool) -> list[Path]: ...
def count_temp_files(folder: Path, *, recursive: bool) -> int: ...
def stamp(path) -> FileStamp: ...
def read_bytes(path: Path) -> bytes: ...
def write_backup(source: Path) -> tuple[str, Path | None]: ...
def atomic_write_bytes(target: Path, data: bytes) -> None: ...
```

Full reference implementation in §7.

### 4.5 `greek_srt/convert.py` — public surface

```python
PREVIEW_LINES  = 40
MAX_FILE_BYTES = 8 * 1024 * 1024      # 8 MiB
LOSS_GUARD     = 0.20

@dataclass(frozen=True, slots=True)
class Progress:
    phase: str                        # "scan" | "convert"
    done: int                         # 1-based, runs 1..total with no gaps
    total: int                        # constant for the whole run
    path: Path
    report: FileReport | None = None  # set during "scan"
    result: ConvertResult | None = None   # set during "convert"

ProgressCallback = Callable[[Progress], None]

def scan_one(path: Path, target: Target) -> FileReport: ...

def scan(
    folder: str | os.PathLike[str],
    *,
    recursive: bool = False,
    target: Target,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> list[FileReport]: ...

def convert(
    reports: Sequence[FileReport],
    *,
    backup: bool = True,
    on_progress: ProgressCallback | None = None,
    cancel: threading.Event | None = None,
) -> list[ConvertResult]: ...
```

### 4.6 `greek_srt/__init__.py` — complete

```python
"""Greek SRT converter core. Two entry points: scan() reads, convert() writes."""

from .models import (
    Action,
    Confidence,
    ConvertResult,
    FileReport,
    FileStamp,
    LossyChange,
    Target,
)
from .clean import StructureChanged
from .fileio import BACKUP_PREFIX, FileOpError
from .convert import (
    LOSS_GUARD,
    MAX_FILE_BYTES,
    PREVIEW_LINES,
    Progress,
    ProgressCallback,
    convert,
    scan,
    scan_one,
)

__all__ = [
    "Action", "Confidence", "ConvertResult", "FileReport", "FileStamp",
    "LossyChange", "Target", "StructureChanged", "FileOpError",
    "Progress", "ProgressCallback", "convert", "scan", "scan_one",
    "BACKUP_PREFIX", "PREVIEW_LINES", "MAX_FILE_BYTES", "LOSS_GUARD",
]
__version__ = "1.0.0"
```

### 4.7 The `on_progress` contract

**Signature:** `Callable[[Progress], None]`. One positional argument, return value ignored. A frozen
dataclass rather than loose arguments so a future field cannot break existing callers.

**When it fires:** exactly once per file, **after** that file has been fully processed and its report
or result appended to the return list. Never before a file. Never for a file skipped by cancellation.
Zero files means zero calls.

**Thread guarantee — the one that matters:** the callback runs on **whatever thread called `scan()`
or `convert()`**, synchronously, inside the file loop. **The core creates no threads, no executors
and no timers, ever.** In the GUI that thread is the worker thread, so:

> The `on_progress` callback **MUST NOT touch any Tk widget.** Its only permitted action is
> `queue.put(progress)`. A widget call from a worker thread raises
> `RuntimeError: main thread is not in main loop`.

`on_progress` must not raise. If it does, the exception propagates out and aborts the run; the core
does not catch it, because swallowing it would hide a front-end bug.

### 4.8 The cancellation contract

**A `threading.Event` passed in as the keyword-only `cancel` parameter.** Not a returned handle.
Rationale: `scan()` and `convert()` stay ordinary synchronous functions a test can call with no
thread involved; the GUI already owns its worker thread and needs one flag spanning both phases plus
its own teardown.

Semantics:

- Checked **between files**, at the top of the loop, **before** starting each file. Never mid-file,
  so a file is never half-written.
- On cancellation the function **returns normally with partial results**. It does not raise, and
  there is no `Cancelled` exception. The caller detects it via `len(results) < len(reports)`.
- An event already set on entry yields `[]` and zero filesystem writes.
- `cancel=None` (the default) disables checking entirely.
- Cancel does not roll back. Files already converted stay converted and keep their backups.

### 4.9 The error-handling policy

The bare `except Exception` at line 308 of the old script is the anti-pattern being removed. It
catches `TypeError`, `AttributeError` and `NameError` and reports them as *file* failures, so a
genuine bug looks like a bad subtitle.

**The core must never catch `Exception`. It must never catch `BaseException` except in
`atomic_write_bytes` for temp cleanup with an immediate re-raise. It must never catch `ValueError`.**

That last rule is load-bearing: `UnicodeDecodeError` and `UnicodeEncodeError` are **subclasses of
`ValueError`, not of `OSError`** (MRO verified). A `ValueError` clause intended to catch a programmer
error would silently swallow every decode and encode failure; and a bare `except OSError` will **not**
catch them.

The only permitted catch clauses anywhere in `greek_srt/` are:

```
except OSError            except UnicodeError
except UnicodeDecodeError except UnicodeEncodeError
except FileOpError        except StructureChanged
```

`MemoryError`, `KeyboardInterrupt` and `SystemExit` always propagate untouched.

**Raised eagerly — caller/programmer errors:**

| Exception | Raised by | When |
|---|---|---|
| `FileNotFoundError` | `scan` | `folder` does not exist |
| `NotADirectoryError` | `scan` | `folder` exists but is not a directory |
| `TypeError` | `scan` | `target` is not a `Target` member |
| `ValueError` | `convert` | any report has `action` not in `{CONVERT, NEEDS_REVIEW}` |
| `ValueError` | `convert` | any report has `encoding is None` |
| `ValueError` | `convert` | the reports do not all share one `target` |

`convert()` validates **all** reports before touching any file, so a bad batch writes nothing at all.

**Invariants asserted in tests:** `result.ok is True` iff `result.error is None`; and
`result.ok is False` implies `result.bytes_written == 0`.

Error strings are formatted `f"{type(exc).__name__}: {exc}"` so the front-ends can display something
useful without holding the exception object.

---

## 5. The detection algorithm

### 5.1 Facts the algorithm is built on

Measured with CPython 3.11 against a **real 391-file corpus** of the user's own subtitle library
(`D:\Downloads\Cinema`, `D:\Downloads\Σειρές`). These are not negotiable; the algorithm is a direct
consequence of them.

1. **`iso-8859-7` has only three undefined bytes: `0xAE`, `0xD2`, `0xFF`.** It maps the whole C1
   range `0x80`–`0x9F` to control characters U+0080–U+009F and **does not raise**. None of the three
   occurs in any of the 391 real files.
2. **`cp1253` has seventeen undefined bytes:**
   `0x81 0x88 0x8A 0x8C 0x8D 0x8E 0x8F 0x90 0x98 0x9A 0x9C 0x9D 0x9E 0x9F 0xAA 0xD2 0xFF`.
3. **`cp1252` (alias `windows-1252`) has five:** `0x81 0x8D 0x8F 0x90 0x9D`.
4. **`latin1` has none.** It decodes any byte sequence. **It must never appear in a candidate list**,
   because it makes detection unfalsifiable.
5. **Bytes `0xB7`–`0xFE` are byte-identical in `iso-8859-7` and `cp1253`.** That run covers the
   entire Greek alphabet: Α–Ω, α–ω, final sigma, every accented and dialytika vowel, and Έ Ή Ί Ό Ύ Ώ.
   Counting Greek characters is therefore almost always an exact tie.
6. **Exactly two Greek codepoints sit at different bytes:**

   | codepoint | `iso-8859-7` | `cp1253` |
   |---|---|---|
   | `Ά` U+0386 | `0xB6` | `0xA2` |
   | `΅` U+0385 | `0xB5` | `0xA1` |

7. **The real discriminator is C1 control characters in the decoded output.** CP1253 defines 18
   punctuation characters in `0x80`–`0x9F` (`€ ‚ ƒ „ … † ‡ ‰ ‹ ' ' " " • – — ™ ›`). Decoding those
   bytes as ISO-8859-7 yields control characters, which no subtitle tool ever emits. A typical CP1253
   file with smart punctuation scores **8 C1 controls under ISO-8859-7 and 0 under CP1253.**
8. **`"utf-8"` does not strip a BOM; `"utf-8-sig"` does.** `"utf-8-sig"` is also safe on BOM-less
   UTF-8 (identical output). Always read UTF-8 with `"utf-8-sig"`.
9. **Bare `"utf-16"` on BOM-less input does not raise** — it silently assumes native endianness.
   Never use it for detection. Also, `"utf-16-le"`/`"utf-16-be"` do **not** strip a BOM.
10. A whole-buffer strict UTF-8 decode is a **safe** certainty signal: 0 false positives in 140,000
    trials of realistic Greek CP1253 text, and 0/200,000 on 16 random high bytes. Corpus sizes:
    median 614 B, p95 94 KB, max 149 KB — every real file is far past the point where the
    false-positive rate is unmeasurable.

### 5.2 What was proposed, tested, and rejected

> **The draft design's heuristic — "score by how much output lands in the Greek block vs how many
> undefined slots are hit" — was implemented literally and does not work. Do not implement it.**

Two independent failure modes, both measured:

- **The Greek count is almost always exactly equal.** On a plain Greek SRT the two decodes produce
  **byte-for-byte identical strings** (greek 164 vs 164). Fact 5 is why.
- **The undefined count is 0 for both, always.** On all 84 real single-byte files, strict decoding
  succeeded under **both** codecs (84/84). ISO-8859-7 does not raise on CP1253's punctuation range —
  it silently yields C1 controls. The metric is blind to precisely the evidence that exists. On a
  realistic CP1253 file with smart quotes the proposed heuristic scores **0 vs 0**.

Worse, the undefined-slot penalty is *systematically biased*: ISO-8859-7 has 3 undefined slots and
CP1253 has 17, so ISO-8859-7 wins almost every undefined-slot contest regardless of truth.

The correct discriminator is **C1 control characters in the output**, penalised at **−100 each**. On
the same file that scored 0 vs 0, the corrected scorer gives `cp1253 +102` vs `iso-8859-7 −204`.

**One further guard is mandatory.** A Greek reward with no script-mixing guard misclassifies Western
European text: under `cp1253`, `café` decodes as `cafι` (`0xE9` → Greek iota) and beats `cp1252` on
Greek count alone. **A Greek character adjacent to an ASCII letter `[A-Za-z]` scores −10 instead of
+6.** With that guard, French / Spanish / German / English-smart all resolve to `cp1252` (4/4,
margins 52–88).

### 5.3 The algorithm, normative

`detect_encoding(raw: bytes) -> Detection`. Read the file **once, in full**, with
`Path.read_bytes()`. **Never detect on a prefix** — that is BUG 2(a).

Steps execute strictly in order; the first match returns.

1. **Empty.** `raw == b""` → `("utf-8", CERTAIN, "empty file")`.
   (Classification then rejects it as UNREADABLE at §5.5 test 2; detection itself stays total.)

2. **BOM**, matched as an exact byte prefix, in this order:

   | bytes | encoding |
   |---|---|
   | `FF FE 00 00` | `utf-32-le` |
   | `00 00 FE FF` | `utf-32-be` |
   | `EF BB BF` | `utf-8-sig` |
   | `FF FE` | `utf-16-le` |
   | `FE FF` | `utf-16-be` |

   → `CERTAIN`. **UTF-32 must precede UTF-16**: `BOM_UTF32_LE` starts with `BOM_UTF16_LE`.
   **This step must precede everything else**: `EF BB BF` decodes without error as `ο»Ώ` under both
   Greek codecs, so a BOM'd file would otherwise reach the scorer intact — and that is the 305-of-391
   majority case.

3. **NUL byte present.** No text subtitle contains one (0/391 confirmed). Over the first 4096 bytes,
   count NULs at even and odd offsets:
   - `odd > even * 4` and `odd > len(head)//8` → `("utf-16-le", GUESS, ...)`
   - `even > odd * 4` and `even > len(head)//8` → `("utf-16-be", GUESS, ...)`
   - otherwise → `(None, None, ...)` → binary → UNREADABLE.

   Verified: PNG, MP4, ZIP, all-zero and BOM-less UTF-32 all fall through to the binary branch.

4. **Pure ASCII.** No byte `>= 0x80` → `("ascii", CERTAIN, ...)`. Verified harmless: such a file
   decodes identically under utf-8, cp1253 and iso-8859-7.

5. **Strict whole-buffer UTF-8.** `raw.decode("utf-8")` succeeds → `("utf-8", CERTAIN, ...)`. Do not
   pass `errors=`; strict is the default. Double-encoded mojibake is **not** valid UTF-8 and will not
   be falsely marked certain.

6. **Single-byte scoring.** For each candidate in this exact order —
   `("cp1253", "iso-8859-7", "cp1252")` — attempt a strict decode. A `UnicodeDecodeError`
   **eliminates** that candidate. Score each survivor with `score_decoded` (§5.4). Highest score
   wins. Confidence is **always `GUESS`** in this branch.
   - **On an exact tie, take the first tied candidate in the declared order.** This is provably safe:
     a tie means no discriminating byte is present, and it was verified on every tie file that
     `decode(cp1253) == decode(iso-8859-7)` **and** `text.encode("iso-8859-7") == raw` **and**
     `text.encode("cp1253") == raw`. The label is cosmetic.
   - If nothing decodes → `(None, None, ...)` → UNREADABLE.

Candidate order is empirically justified: **84/84** single-byte files in the real corpus are CP1253,
and `0xB6`/`0xB5` appear in **zero** files.

**Accepted, deliberate bias:** the Greek reward makes `cp1253` outscore `cp1252` on genuine Greek.
`cp1252` exists only as a last resort. The −10 mixed-script rule is what keeps Western European text
correct; **do not add a symmetric Latin-letter bonus** — CP1253 Greek bytes decode to accented Latin
letters under CP1252, so that would reintroduce the ambiguity.

### 5.4 The scoring formula and reference implementation

| condition | delta |
|---|---|
| `ord(ch) < 0x80` | `0` — identical across all candidates, carries no information |
| `0x80 <= ord(ch) <= 0x9F` (C1 control) | **`-100`** |
| Greek `U+0370`–`U+03FF` **and** previous or next character is ASCII `[A-Za-z]` | **`-10`** |
| Greek `U+0370`–`U+03FF`, otherwise | `+6` |
| Latin-1 letter `U+00C0`–`U+00FF` except `×` U+00D7 and `÷` U+00F7, or one of `Œ œ Š š Ÿ Ž ž ƒ` | `+3` |
| in `PLAUSIBLE_PUNCT` | `+2` |
| any other character `>= 0x80` | `-8` |

**Paste as `greek_srt/detect.py`.** This exact code passed every vector in §5.6 on the target machine.

```python
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
```

### 5.5 Classification — how `scan()` turns a `Detection` into an `Action`

Tests are applied **in this order**; the first that matches wins.

#### UNREADABLE

The file is not something this tool may rewrite. `encoding = None`, `confidence = None`,
`lossy = ()`, `preview = ()`, `error` set. The GUI greys the row, shows the reason in Status, and
**the checkbox is inert**. `convert()` raises `ValueError` if such a report is passed in.

| # | Condition | `error` string |
|---|---|---|
| 1 | `stat()` raises `OSError` | `cannot read: {type}: {exc}` |
| 2 | `size == 0` | `file is empty (0 bytes)` |
| 3 | `size > MAX_FILE_BYTES` (8 MiB) | `larger than 8 MiB ({n} bytes)` |
| 4 | `read_bytes()` raises `OSError` | `cannot read: {type}: {exc}` |
| 5 | `detect_encoding()` returns `encoding is None` | the `reason` detection gave |
| 6 | decode raises `UnicodeDecodeError` | `{type}: {exc}` |
| 7 | BOM-stripped text `.strip()` is empty | `whitespace only` |
| 8 | no line matches `TIMECODE_RE` | `no SubRip timecode line found` |
| 9 | `fold_document()` raises `StructureChanged` | the exception message |

> **Tests 3 and 8 are added on research evidence.** Test 3 bounds memory for the read-everything
> design (real subtitles are 20–100 KB; 8 MiB is ~80× the largest plausible file). Test 8 is the
> single strongest protection against rewriting a file that is not a subtitle at all — a README, a
> `.nfo`, an HTML error page a scraper saved with an `.srt` extension. One timecode line is enough.

#### ALREADY_TARGET

**Definition: `render(decoded_text, target).data == raw_bytes`.** That is, the file already *is*,
byte for byte, what `convert()` would write. Nothing else counts.

This is deliberately **not** "the detected encoding name equals the target name", which is what the
old code does at line 214 and which is wrong in four separate ways:

- a UTF-8 file **with** a BOM is not already-target under a no-BOM policy;
- a file missing bytes the folder would change is not already-target;
- a misdetected CP1253 file reported as `iso-8859-7` is skipped precisely when it most needs
  converting;
- on a scoring tie the label is arbitrary even though the bytes are provably interchangeable.

Byte equality is exact, label-independent, makes `scan()` and `convert()` provably agree, and makes
conversion **idempotent by construction**. Verified end to end: after converting each of 7 corpus
file kinds to each of 2 targets, re-classifying always yields `ALREADY_TARGET` (14/14).

The GUI renders `already target`, **unticked and inert** — rewriting such a file is a guaranteed
no-op.

#### NEEDS_REVIEW

Applies **only** when `target is Target.ISO_8859_7`. Compute

```
loss_ratio = (non-ASCII characters dropped by folding) / (total non-ASCII characters)
```

If `loss_ratio > LOSS_GUARD` (0.20) → `Action.NEEDS_REVIEW`.

**This guard is mandatory, not optional.** Measured on the user's own 391-file library, per file, the
fraction of non-ASCII characters ISO-8859-7 would drop:

```
219 files  >=80% lost   <- CJK / other-language subtitles
118 files    0% lost    <- clean Greek
 26 files   <2% lost    <- Greek + smart punctuation
 22 files   no non-ascii
  6 files  20-80% lost
```

**219 of 391 files would be destroyed by an unguarded ISO-8859-7 run.** The 0.20 threshold separates
the two populations almost perfectly — only 6 files land in the intermediate band.

The GUI shows `NEEDS REVIEW - {pct}% of non-ASCII lost`, colours the row red, leaves it **unticked
by default**, but the checkbox **is** toggleable so a determined user can force it.

#### CONVERT

Everything else. When `dropped_count > 0` the Status column shows `N chars stripped (!)` with the
orange warning tag. Characters that were *replaced* are not a warning — that is the normal, intended
folding.

When the only difference is a BOM, Status shows `will convert (BOM removed)`.

### 5.6 Detection test vectors — exact expectations, all verified passing

```python
import codecs
from greek_srt.detect import detect_encoding as d
from greek_srt.models import Confidence as C

assert d(b"")[0:2]                                             == ("utf-8", C.CERTAIN)
assert d(b"1\r\n00:00:01,000 --> 00:00:02,000\r\nHi\r\n")[0:2] == ("ascii", C.CERTAIN)
assert d("Καλημέρα κόσμε".encode("utf-8"))[0:2]                == ("utf-8", C.CERTAIN)
assert d(codecs.BOM_UTF8 + "Καλημέρα".encode("utf-8"))[0:2]    == ("utf-8-sig", C.CERTAIN)
assert d(codecs.BOM_UTF16_LE + "Κ".encode("utf-16-le"))[0:2]   == ("utf-16-le", C.CERTAIN)
assert d(codecs.BOM_UTF16_BE + "Κ".encode("utf-16-be"))[0:2]   == ("utf-16-be", C.CERTAIN)

# BOM-less UTF-16, caught by NUL offset parity
srt = "1\r\n00:00:01,000 --> 00:00:02,000\r\nΚαλημέρα\r\n"
assert d(srt.encode("utf-16-le"))[0:2] == ("utf-16-le", C.GUESS)
assert d(srt.encode("utf-16-be"))[0:2] == ("utf-16-be", C.GUESS)

# CP1253 Greek with smart punctuation -> cp1253 wins on the C1 penalty.
# Measured: scores=[(102,'cp1253'), (54,'cp1252'), (-204,'iso-8859-7')] margin=48
g = "1\r\n00:00:01,000 --> 00:00:03,000\r\n— Καλημέρα…\r\n— Τι κάνεις;\r\n"
assert d(g.encode("cp1253"))[0:2] == ("cp1253", C.GUESS)

# The Ά discriminator, both directions
a = "Άννα, άκουσέ με. Άσε με ήσυχο."
assert d(a.encode("cp1253"))[0]     == "cp1253"      # Ά == 0xA2
assert d(a.encode("iso-8859-7"))[0] == "iso-8859-7"  # Ά == 0xB6

# Western European must NOT be called Greek
fr = "J'ai vu le café près de l'hôtel. — À Genève, naïvement."
de = "Grüße aus München, schön! „Wirklich?" fragte er."
assert d(fr.encode("cp1252"))[0] == "cp1252"
assert d(de.encode("cp1252"))[0] == "cp1252"

# Documented tie: no discriminating byte. Label is cosmetic and provably safe.
t = "Καλημέρα κόσμε."
raw = t.encode("iso-8859-7")
assert raw == t.encode("cp1253")
assert d(raw)[0] == "cp1253"                              # tie-break order
assert raw.decode("cp1253") == raw.decode("iso-8859-7")
assert raw.decode("cp1253").encode("iso-8859-7") == raw   # ALREADY_TARGET still correct
```

---

## 6. The cleaning + encoding pipeline

### 6.1 Design rules — each one is enforced by a test

- **R1** No key of `ISO_FOLD_MAP` is ASCII → timecode and index lines, which are pure ASCII, can
  never be altered.
- **R2** No value contains `:`, `,` or `>` → a timecode line cannot be forged and the `-->` token
  cannot be created.
- **R3** Every value is itself ISO-8859-7-encodable.
- **R4** No entry folds a character that ISO-8859-7 encodes *and* CP1253 agrees on byte-for-byte —
  **except** `U+00A0` (NBSP) and `U+00AD` (soft hyphen), which are folded on purpose because they are
  invisible and render unpredictably in players.
- **R5** Characters ISO-8859-7 encodes but which land on a **CP1253-conflicting** byte are folded to
  ASCII **if and only if doing so costs no Greek**. Folded: `'`(A1) `'`(A2) `€`(A4) `₯`(A5) `ͺ`(AA).
  **Kept:** `΅`(B5) and `Ά`(B6), because `Ά` is an ordinary Greek capital (`Άννα`, `Άσε`) and folding
  it would mangle Greek words.
- **R6** Control characters `U+0000`–`U+001F` (except `\t \n \r`), `U+007F` and `U+0080`–`U+009F` are
  dropped **explicitly**. They are all ISO-8859-7-encodable, so the "drop the unencodable" pass will
  **not** remove them, and a mis-decoded UTF-16 file would otherwise leave NULs in the output.

### 6.2 Corrections to the existing table, and why

The existing 23-entry table at lines 53–84 is wrong in three ways.

**(a) Eight entries destroy characters ISO-8859-7 represents natively.**

| char | native byte | old table wrongly emits | disposition |
|---|---|---|---|
| `―` U+2015 | `0xAF` | `-` | **REMOVED** — this is *the* Greek dialogue dash |
| `©` U+00A9 | `0xA9` | `(C)` | **REMOVED** |
| `£` U+00A3 | `0xA3` | `GBP` | **REMOVED** |
| `±` U+00B1 | `0xB1` | `+/-` | **REMOVED** |
| NBSP U+00A0 | `0xA0` | space | **KEPT as a deliberate R4 exception** (invisible) |
| `'` U+2018 | `0xA1` | `'` | **KEPT under R5** — see below |
| `'` U+2019 | `0xA2` | `'` | **KEPT under R5** |
| `€` U+20AC | `0xA4` | `EUR` | **KEPT under R5** |

The R5 four are subtle and easy to get wrong in either direction. They *are* encodable, but bytes
A1/A2/A4 are exactly where ISO-8859-7 and CP1253 disagree: a CP1253-configured player renders them as
`΅`, `Ά`, `¤`. Since the ISO-8859-7 target exists **for old players**, and Greek TVs are commonly
CP1253-configured, folding these to ASCII is the safer rendering — and it costs no Greek.

Also natively encodable and correctly absent from the table: `« »` (AB/BB), `·` (B7), `΄ ΅` (B4/B5),
`§ ¨ ¬ ° ² ³ ½ ¦`.

**(b) The old table can FORGE the SRT block delimiter.** With `– → "-"` and `→ → "->"`, the input
`–→` folds to `-->`. Measured. All four arrow entries are deleted and R2 forbids `>` in any value.

**(c) The dash target is wrong.** `—` U+2014 and `–` U+2013 fold to **`―` U+2015**, not to ASCII
`-`. U+2015 is the conventional Greek dialogue bar, it lives at byte `0xAF`, and — verified —
**both `iso-8859-7` and `cp1253` map `0xAF` to U+2015**, so it is safe under R4/R5. This also
*reduces* forge risk by producing fewer ASCII hyphens.

### 6.3 `greek_srt/clean.py` — reference implementation

**Paste this whole file.** Written with `\uXXXX` escapes on purpose so it survives copy/paste through
any tool. Validated: 119 entries, R1–R6 all pass, forge search over 1,953,125 three-character
combinations, totality fuzz over 48,000 random codepoints, idempotence, and newline preservation.

```python
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
# Accented Latin letters (e u n a c ...) are NOT listed. They are handled
# generically by the NFKD fallback in fold_to_iso, which strips combining
# marks: "cafe-acute" -> "cafe".

_KEEP_CONTROLS = frozenset({0x09, 0x0A, 0x0D})


class StructureChanged(Exception):
    """The folder altered the cue skeleton. Never write such a file."""


class Rendered(NamedTuple):
    data: bytes
    lossy: tuple[LossyChange, ...]
    loss_ratio: float


def fold_to_iso(text: str) -> tuple[str, dict[str, int], dict[str, int]]:
    """Fold one TEXT line. Total: the result always encodes to iso-8859-7.

    Returns (folded, replaced_counts, dropped_counts).
    """
    replaced: dict[str, int] = {}
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
            replaced[ch] = replaced.get(ch, 0) + 1
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
            replaced[ch] = replaced.get(ch, 0) + 1
            out.append(stripped)
        else:
            dropped[ch] = dropped.get(ch, 0) + 1
    return "".join(out), replaced, dropped


def fold_document(text: str) -> tuple[str, dict[str, int], dict[str, int]]:
    """Fold a whole document, leaving structural lines verbatim.

    Line terminators are preserved EXACTLY, including mixed and CR-only files.
    Raises StructureChanged if the cue skeleton moved or a '-->' was forged.
    """
    parts = split_lines_keep(text)
    before = [i for i, (c, _) in enumerate(parts) if TIMECODE_RE.match(c)]
    out: list[tuple[str, str]] = []
    replaced: dict[str, int] = {}
    dropped: dict[str, int] = {}
    for content, term in parts:
        if TIMECODE_RE.match(content) or INDEX_RE.match(content):
            out.append((content, term))     # structural: verbatim, never folded
            continue
        folded, r, d = fold_to_iso(content)
        for k, v in r.items():
            replaced[k] = replaced.get(k, 0) + v
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


def _to_lossy(replaced: dict[str, int], dropped: dict[str, int]
              ) -> tuple[LossyChange, ...]:
    items = [LossyChange(ch, ISO_FOLD_MAP.get(ch, ""), n) for ch, n in replaced.items()]
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
```

**Note on `_to_lossy` for the NFKD path.** A character folded by NFKD (e.g. `é` → `e`) is recorded in
`replaced` but has no `ISO_FOLD_MAP` entry, so `LossyChange.replacement` comes back `""` and it would
read as "dropped". That is wrong. **Fix it by recording the substitution at fold time**: change
`fold_to_iso` to accumulate `replaced` as `dict[str, tuple[str, int]]` mapping char → (substitution,
count), and have `fold_document` merge on count. Do this; the signature change is confined to
`clean.py`. The public `render()` contract is unchanged.

### 6.4 BOM policy — normative

**No BOM is ever written, for either target.**

- Read UTF-8 input with **`utf-8-sig`**, never plain `utf-8`. `read_codec()` does this.
- **`scan()` and `convert()` remove every occurrence of `U+FEFF` from the decoded text**, not just a
  leading one, *before* calling `render()`. A U+FEFF appearing mid-file (concatenated subtitle files)
  is not encodable in ISO-8859-7 and would otherwise crash or pollute the loss report.
- Consequence, intentional and visible: a `utf-8-sig` file targeted at UTF-8 round-trips **unequal**
  and is reported as `CONVERT` with status text `will convert (BOM removed)`. Expect this to affect
  most of a typical library (305 of 391 reference files). The user can untick the row.
- `encoding="utf-8-sig"` on **write** *adds* a BOM. Never use it. `Target.codec` returns `"utf-8"`.

Why no BOM: a BOM makes the first index line literally `"\ufeff1"`, which strict SRT parsers fail to
parse, dropping the first cue. Omitting it costs at most an editor's auto-detection.

### 6.5 Line-ending policy — normative, and the most easily-missed rule

> **The converter changes the character encoding and nothing else. Line endings are preserved
> exactly as found, byte for byte, including files with inconsistent endings.**

**Implementation: binary I/O end to end.** `Path.read_bytes()` → explicit `.decode()` → explicit
`.encode()` → `os.replace()` of a temp file opened `"wb"`. No newline translation exists in binary
mode, so the trap is structurally impossible.

**Forbidden, all measured:**

- `open(path, "w", encoding=...)` with `newline` omitted → emits `os.linesep`, CRLF-ifying every LF
  file. This is what the old script does.
- `newline=""` on read combined with `newline="\r\n"` on write → produces `\r\r\n` on every line.
- "Normalise to CRLF because it is Windows." It is not the tool's job. It would also make an
  already-target conversion non-idempotent.

If text mode is ever used anywhere (it is not, in this design), it **must** pass `newline=""` on both
read and write — verified byte-equivalent to binary I/O for utf-8, utf-8-sig, utf-16 and cp1253.

**Decision recorded:** one research stream recommended normalising to CRLF plus a guaranteed final
newline, on the grounds that SubRip emits CRLF and one TV was documented to fail on LF-only files.
**That recommendation is rejected.** Preservation is unconditionally safe — it cannot introduce a
change the user did not ask for — and two of the three independent research streams found
preservation necessary for byte-equality `ALREADY_TARGET` and idempotence to hold. There is no
"normalise line endings" checkbox; it is not in the approved UI and is out of scope.

**Accepted limitation:** a CR-only (classic Mac) `.srt` stays CR-only and will remain unreadable in
most players. Deliberate. The old code accidentally "repaired" such files; the new code does not.

---

## 7. The write path

### 7.1 Scope

`greek_srt/fileio.py` is the **only** module permitted to create, modify, rename or delete a file.
`detect.py`, `clean.py` and `models.py` must import nothing from `os`, `shutil` or `tempfile` that
can mutate the filesystem.

### 7.2 `greek_srt/fileio.py` — reference implementation

```python
"""greek_srt/fileio.py -- the ONLY module in this project that writes."""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
import time
from pathlib import Path

from .models import FileStamp

BACKUP_PREFIX = "__orig__"     # lowercase; compared case-insensitively
TEMP_PREFIX = ".srtconv-"
TEMP_SUFFIX = ".tmp"

_REPLACE_ATTEMPTS = 3
_REPLACE_BACKOFF = (0.10, 0.25)          # len == _REPLACE_ATTEMPTS - 1
_EXT_PREFIX = "\\\\?\\"


class FileOpError(Exception):
    """Every filesystem failure the core reports. `code` is a stable token."""

    def __init__(self, code: str, path, detail):
        super().__init__(f"{code}: {path}: {detail}")
        self.code = code
        self.path = Path(str(path))
        self.detail = detail


def long_path(p) -> str:
    r"""Windows extended-length form of p. Identity on non-Windows.

    The \\?\ prefix disables MAX_PATH *and* all path normalisation, so the input
    must be absolute with no '.', '..' or forward slashes -- which is exactly
    what os.path.abspath guarantees.
    """
    s = os.fspath(p)
    if os.name != "nt":
        return str(s)
    s = os.path.abspath(str(s))
    if s.startswith(_EXT_PREFIX):
        return s                                   # idempotent
    if s.startswith("\\\\"):                       # UNC: \\server\share\...
        return _EXT_PREFIX + "UNC" + s[1:]         # -> \\?\UNC\server\share\...
    return _EXT_PREFIX + s


def is_excluded(name: str) -> bool:
    low = name.lower()
    return low.startswith(BACKUP_PREFIX) or low.startswith(TEMP_PREFIX)


def iter_srt_files(folder: Path, *, recursive: bool) -> list[Path]:
    """Plain Paths of convertible .srt files, sorted, exclusions applied.

    Suffix matching is case-INSENSITIVE via p.suffix.lower(), not glob("*.srt"):
    glob is case-insensitive on Windows and case-sensitive on Linux, which would
    make the suite pass on the dev machine and fail in CI.
    """
    root = Path(long_path(folder))
    candidates = root.rglob("*") if recursive else root.glob("*")
    found = [
        p for p in candidates
        if p.suffix.lower() == ".srt" and not is_excluded(p.name) and p.is_file()
    ]
    # Return PLAIN paths: the \\?\ prefix must never reach the UI or a report.
    plain = [Path(os.path.abspath(str(p)).removeprefix(_EXT_PREFIX)) for p in found]
    return sorted(plain, key=lambda p: str(p).casefold())


def count_temp_files(folder: Path, *, recursive: bool) -> int:
    """Leftover .srtconv-*.tmp files from an interrupted run. Reported, never deleted."""
    root = Path(long_path(folder))
    candidates = root.rglob("*") if recursive else root.glob("*")
    return sum(1 for p in candidates
               if p.name.startswith(TEMP_PREFIX) and p.name.endswith(TEMP_SUFFIX))


def stamp(path) -> FileStamp:
    st = os.stat(long_path(path))
    return FileStamp(st.st_size, st.st_mtime_ns)


def read_bytes(path: Path) -> bytes:
    with open(long_path(path), "rb") as fh:
        return fh.read()


def _clear_readonly(target: Path) -> bool:
    """Clear the read-only attribute. True if it was set and we cleared it."""
    try:
        mode = os.stat(long_path(target)).st_mode
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise FileOpError("STAT_FAILED", target, exc) from exc
    if mode & stat.S_IWRITE:
        return False
    try:
        os.chmod(long_path(target), mode | stat.S_IWRITE)
    except OSError as exc:
        raise FileOpError("READ_ONLY", target, exc) from exc
    return True


def _set_readonly(target: Path) -> None:
    """Best-effort restore. Never raises -- cosmetic only."""
    try:
        mode = os.stat(long_path(target)).st_mode
        os.chmod(long_path(target), mode & ~stat.S_IWRITE)
    except OSError:
        pass


def write_backup(source: Path) -> tuple[str, Path | None]:
    """Copy source to __orig__<name>.srt. NEVER overwrites an existing backup."""
    backup = source.parent / (BACKUP_PREFIX + source.name)
    if backup.exists():
        return "kept-existing", backup             # first backup wins
    try:
        shutil.copy2(long_path(source), long_path(backup))
    except OSError as exc:                         # SameFileError is an OSError
        raise FileOpError("BACKUP_FAILED", backup, exc) from exc
    # copy2 copies the read-only attribute across. Clear it on the backup so the
    # user can delete it.
    try:
        mode = os.stat(long_path(backup)).st_mode
        if not mode & stat.S_IWRITE:
            os.chmod(long_path(backup), mode | stat.S_IWRITE)
    except OSError:
        pass                                       # cosmetic only
    return "created", backup


def atomic_write_bytes(target: Path, data: bytes) -> None:
    """Replace `target` with `data`, atomically, or leave it untouched.

    The temp file is created in target's OWN directory: os.replace is atomic
    only within a volume (cross-volume raises OSError errno=18/winerror=17).
    """
    target = Path(target)
    tmp_path = None
    cleared_ro = False
    try:
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=long_path(target.parent),
                prefix=TEMP_PREFIX,
                suffix=TEMP_SUFFIX,
            )
        except OSError as exc:
            raise FileOpError("TEMP_CREATE_FAILED", target, exc) from exc

        try:
            with os.fdopen(fd, "wb") as fh:      # binary: no newline translation
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())            # data on disk BEFORE the rename
        except OSError as exc:
            raise FileOpError("WRITE_FAILED", target, exc) from exc
        # NOTE: do NOT fsync the parent directory. That POSIX idiom raises
        # PermissionError (errno 13) on Windows -- measured.

        cleared_ro = _clear_readonly(target)

        last = None
        for attempt in range(_REPLACE_ATTEMPTS):
            try:
                os.replace(tmp_path, long_path(target))
                tmp_path = None                  # ownership transferred
                break
            except PermissionError as exc:       # winerror 5 (locked/read-only)
                last = exc                       # or winerror 32 (temp in use)
                if attempt < _REPLACE_ATTEMPTS - 1:
                    time.sleep(_REPLACE_BACKOFF[attempt])
            except OSError as exc:               # NOT a PermissionError subclass
                if exc.errno == 18 or getattr(exc, "winerror", None) == 17:
                    raise FileOpError("CROSS_VOLUME", target, exc) from exc
                raise FileOpError("REPLACE_FAILED", target, exc) from exc
        else:
            raise FileOpError("LOCKED", target, last) from last

        if cleared_ro:
            _set_readonly(target)                # re-apply to the NEW file
            cleared_ro = False
    finally:
        if cleared_ro:
            _set_readonly(target)                # failure path: undo our change
        if tmp_path is not None:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
```

### 7.3 Why each step is there

- **`mkstemp`, not `NamedTemporaryFile`.** `mkstemp` hands back a raw fd so `os.fdopen` fixes the
  mode exactly, and the `prefix`/`suffix` are controlled — which is what keeps orphans out of the
  `*.srt` glob.
- **Temp in the target's own directory.** `os.replace` across volumes raises `OSError errno=18
  winerror=17` (verified `D:\` → `C:\`). `%TEMP%` is frequently on a different drive from a media
  library.
- **`.tmp` suffix, not `.srt`.** Verified: an orphaned `.srtconv-ebjyjsza.tmp` is not matched by
  `glob("*.srt")`, so a crashed run cannot leave a file the next scan tries to convert.
- **`flush()` + `os.fsync()`.** Guarantees durability before the rename, so a power loss cannot yield
  a renamed-but-empty file. Cost measured at ~1.5 ms/file (0.36 → 1.84 ms on a 22 KB payload) —
  ~1.5 s for 1000 files. Keep it.
- **Read-only clear/restore.** `os.replace` onto a read-only destination raises `PermissionError
  errno=13 winerror=5`. The `finally` restores the attribute if the replace failed.
- **Retry with backoff.** The realistic transient holder is Windows Defender or the Search indexer
  briefly opening a just-created file. Three attempts over ~350 ms clears those. A media player
  holding the file will not clear — hence fail-fast rather than a long loop.
- **`except PermissionError` before `except OSError`.** The cross-volume error is a *plain* `OSError`
  (verified `isinstance(e, PermissionError) is False`).

### 7.4 Backup semantics — normative

> **An existing `__orig__<name>.srt` is never overwritten. The first backup wins. Conversion
> proceeds anyway.**

This replaces the interactive `input()` prompt at old line 229. It is a correctness decision, not a
UX convenience: `shutil.copy2` over an existing writable backup silently overwrites (measured), and
on a second run the source is the *already-converted* file — so overwriting would replace the pristine
original with a converted copy and **destroy the only recovery path**. Keeping the older backup is
strictly safer even if it is stale.

The two alternatives are both wrong: "overwrite" destroys the original; "skip the file" refuses to do
the work the user asked for, on a file that is already safely backed up.

**Ordering is mandatory: the backup is written *before* the atomic replace.** If `backup=True` and
`write_backup` raises, the file is **not** converted and the result code is `BACKUP_FAILED`. A
conversion with a missing backup is worse than no conversion.

A file whose rendered bytes equal its current bytes is never backed up: `backup="not-needed"`.

The GUI shows `kept-existing` in the row's status so the user is informed rather than prompted.

### 7.5 Error cases — exact exception type and required handling

All types below were observed, not inferred. `winerror=None` means the exception came from CRT-level
code and carries only `errno`.

| # | Case | Exception (measured) | `code` | Handling |
|---|---|---|---|---|
| 1 | Destination held open by another process (player, editor, AV) | `PermissionError errno=13 winerror=5` | `LOCKED` | Retry 3× (0.10 s, 0.25 s), then fail the file. Original untouched, temp deleted. Status **"locked — close the player and retry"**. Run continues; GUI offers "Retry failed". |
| 2 | Destination has the read-only attribute | `PermissionError errno=13 winerror=5` | — | Cleared before replace, re-applied after. Not user-visible. |
| 3 | Read-only cannot be cleared (ACL denies) | `PermissionError errno=13` | `READ_ONLY` | Fail the file. Status "read-only / access denied". |
| 4 | Temp source still open when replacing | `PermissionError winerror=32` | `LOCKED` | Cannot occur (the `with` closes first). Treated as `LOCKED`. |
| 5 | Temp and target on different volumes | **plain `OSError` errno=18 winerror=17** | `CROSS_VOLUME` | Cannot occur. Keep the branch as an assertion; `except PermissionError` alone would miss it. |
| 6 | Target directory not writable | `PermissionError errno=13` | `TEMP_CREATE_FAILED` | Fail the file. Status "folder is not writable". |
| 7 | Directory vanished mid-run (removable drive) | `FileNotFoundError errno=2` (winerror 3 or 2) | `TEMP_CREATE_FAILED` / `REPLACE_FAILED` | Fail the file. |
| 8 | UNC host unreachable | `FileNotFoundError errno=2 winerror=53` | `TEMP_CREATE_FAILED` | Fail the file. Status "network path unavailable". |
| 9 | Unmapped drive letter `Z:\` | `FileNotFoundError errno=2 winerror=None` | — | Rejected at folder-selection time. |
| 10 | Disk full | `OSError errno=28` — **inferred from CPython's errno mapping, not measured** | `WRITE_FAILED` | Fail the file; temp unlinked in `finally`; original intact. |
| 11 | File deleted between scan and convert | `FileNotFoundError errno=2` | `OS` | Fail the file. Status "file no longer exists". |
| 12 | File modified between scan and convert | none — detected by comparing `FileStamp` | `SOURCE_CHANGED` | Fail the file. Status **"changed since scan — rescan"**. Never convert with a stale detected encoding. |
| 13 | Bytes do not decode under the detected encoding | `UnicodeDecodeError` (**`ValueError`, not `OSError`**) | `CODEC` | Should be unreachable. Fail the file. |
| 14 | Cleaned text still will not encode | `UnicodeEncodeError` (**`ValueError`, not `OSError`**) | `CODEC` | Unreachable for `iso-8859-7` by construction. **Never fall back to writing UTF-8** (BUG 1). |
| 15 | Path component >255 chars, or an illegal character | `OSError errno=22` | `TEMP_CREATE_FAILED` | Fail the file. Status "invalid path". |
| 16 | Path exceeds `MAX_PATH` and `LongPathsEnabled=0` | `OSError`/`FileNotFoundError`, winerror 3 or 206 — **not measured** | — | Prevented by `long_path()`. |
| 17 | `.srt` entry is actually a directory | `PermissionError errno=13` on read | — | Prevented by the `p.is_file()` filter. |
| 18 | Backup destination exists | none | — | Never overwrite; `backup="kept-existing"`; convert anyway. |
| 19 | Backup fails for any reason while `backup=True` | any `OSError` | `BACKUP_FAILED` | **Do not convert the file.** |
| 20 | Folding forged a `-->` or moved the cue skeleton | `StructureChanged` | `STRUCTURE` | Fail the file; never write it. |
| 21 | Cancel pressed mid-run | none | — | Flag checked **between** files, never inside `atomic_write_bytes`. |

**One failed file never aborts the run.**

### 7.6 Accepted limitations of `os.replace` — state these in the README, do not "fix" them

- **Metadata is not preserved.** The destination becomes the temp file, so `mtime` is reset to now
  and HIDDEN/SYSTEM attributes and explicit ACLs are lost (measured `0x2` → `0x20`). Only the
  read-only attribute is explicitly restored. Resetting mtime matches the current in-place behaviour
  and is therefore not a regression.
- **A file open in another process cannot be replaced,** under any share mode — including
  `FILE_SHARE_DELETE`. **This is a behavioural regression versus today's code, and it is deliberate.**
  Measured on the same held file: `open(held, "w")` **succeeds and truncates**, while `os.replace`
  raises `PermissionError winerror=5`. The old path could destroy the file; the new one visibly
  fails. It must surface as a `LOCKED` status with a retry affordance, never be swallowed.
- **Rejected alternative: `ReplaceFileW` via `ctypes`.** It does preserve attributes and did succeed
  against a `FILE_SHARE_DELETE` handle in testing. Rejected because it is not a single atomic
  primitive (multi-step backup/rename dance with its own failure modes) and a Windows-only `ctypes`
  path conflicts with the zero-dependency, testable-on-any-OS goal. **Do not introduce it.**

### 7.7 Crash recovery

Nothing is lost and nothing needs repairing. The original is only ever modified by the single
`os.replace`. An orphan is named `.srtconv-<random>.tmp`, so the next scan cannot pick it up.

**No startup cleanup sweep.** Deleting stray temps at startup would race with a second copy of the
app running against the same folder. `scan()` reports the count via `count_temp_files()` and the GUI
logs `"N leftover temp file(s) from an interrupted run"` in the status bar; the user deletes them if
they care.

### 7.8 `greek_srt/convert.py` — reference implementation

```python
"""greek_srt/convert.py -- the two public entry points: scan() reads, convert() writes."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from . import clean as _clean
from . import detect as _detect
from . import fileio as _io
from .models import (
    Action, Confidence, ConvertResult, FileReport, FileStamp, LossyChange, Target,
)

PREVIEW_LINES = 40
MAX_FILE_BYTES = 8 * 1024 * 1024
LOSS_GUARD = 0.20

_WRITABLE_ACTIONS = (Action.CONVERT, Action.NEEDS_REVIEW)


@dataclass(frozen=True, slots=True)
class Progress:
    phase: str
    done: int
    total: int
    path: Path
    report: FileReport | None = None
    result: ConvertResult | None = None


ProgressCallback = Callable[[Progress], None]


def _unreadable(path: Path, target: Target, st: FileStamp, why: str) -> FileReport:
    return FileReport(path=path, stamp=st, encoding=None, confidence=None,
                      action=Action.UNREADABLE, target=target, lossy=(),
                      loss_ratio=0.0, preview=(), error=why)


def scan_one(path: Path, target: Target) -> FileReport:
    """Inspect one file. Opens it read-only. Never raises for a per-file problem."""
    zero = FileStamp(0, 0)
    try:
        st = _io.stamp(path)
    except OSError as exc:
        return _unreadable(path, target, zero, f"cannot read: {type(exc).__name__}: {exc}")
    if st.size == 0:
        return _unreadable(path, target, st, "file is empty (0 bytes)")
    if st.size > MAX_FILE_BYTES:
        return _unreadable(path, target, st, f"larger than 8 MiB ({st.size} bytes)")
    try:
        raw = _io.read_bytes(path)
    except OSError as exc:
        return _unreadable(path, target, st, f"cannot read: {type(exc).__name__}: {exc}")

    det = _detect.detect_encoding(raw)
    if det.encoding is None:
        return _unreadable(path, target, st, det.reason)
    try:
        text = raw.decode(_detect.read_codec(det.encoding))
    except UnicodeDecodeError as exc:
        return _unreadable(path, target, st, f"{type(exc).__name__}: {exc}")

    text = text.replace("\ufeff", "")          # every BOM, not just a leading one
    if not text.strip():
        return _unreadable(path, target, st, "whitespace only")
    lines = _clean.split_lines(text)
    if not any(_clean.TIMECODE_RE.match(ln) for ln in lines):
        return _unreadable(path, target, st, "no SubRip timecode line found")

    try:
        rendered = _clean.render(text, target)
    except _clean.StructureChanged as exc:
        return _unreadable(path, target, st, str(exc))
    except UnicodeEncodeError as exc:
        return _unreadable(path, target, st, f"{type(exc).__name__}: {exc}")

    if rendered.data == raw:
        action = Action.ALREADY_TARGET
    elif target is Target.ISO_8859_7 and rendered.loss_ratio > LOSS_GUARD:
        action = Action.NEEDS_REVIEW
    else:
        action = Action.CONVERT

    return FileReport(
        path=path, stamp=st, encoding=det.encoding, confidence=det.confidence,
        action=action, target=target, lossy=rendered.lossy,
        loss_ratio=rendered.loss_ratio,
        preview=tuple(lines[:PREVIEW_LINES]), error=None,
    )


def scan(folder, *, recursive: bool = False, target: Target,
         on_progress: ProgressCallback | None = None,
         cancel: threading.Event | None = None) -> list[FileReport]:
    """Inspect every .srt file under `folder`. Opens files read-only; NEVER writes."""
    if not isinstance(target, Target):
        raise TypeError(f"target must be a Target member, got {target!r}")
    root = Path(os.fspath(folder))
    if not root.exists():
        raise FileNotFoundError(f"Folder does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    paths = _io.iter_srt_files(root, recursive=recursive)
    total = len(paths)
    reports: list[FileReport] = []
    for i, path in enumerate(paths, 1):
        if cancel is not None and cancel.is_set():
            break
        report = scan_one(path, target)
        reports.append(report)
        if on_progress is not None:
            on_progress(Progress("scan", i, total, path, report=report))
    return reports


def _failed(report: FileReport, code: str, detail: str) -> ConvertResult:
    return ConvertResult(path=report.path, ok=False, status="failed", code=code,
                         source_encoding=report.encoding,
                         target_encoding=report.target.codec, backup="not-needed",
                         backup_path=None, lossy=report.lossy, bytes_written=0,
                         error=detail)


def _convert_one(report: FileReport, *, backup: bool) -> ConvertResult:
    src = report.path
    # TOCTOU guard: the user may have edited the file between Scan and Convert.
    if _io.stamp(src) != report.stamp:
        raise _io.FileOpError("SOURCE_CHANGED", src, "modified since scan")

    raw = _io.read_bytes(src)
    text = raw.decode(_detect.read_codec(report.encoding)).replace("\ufeff", "")
    rendered = _clean.render(text, report.target)     # encode happens BEFORE any write

    if rendered.data == raw:
        return ConvertResult(path=src, ok=True, status="unchanged", code=None,
                             source_encoding=report.encoding,
                             target_encoding=report.target.codec,
                             backup="not-needed", backup_path=None,
                             lossy=rendered.lossy, bytes_written=0, error=None)

    if backup:
        backup_status, backup_path = _io.write_backup(src)
    else:
        backup_status, backup_path = "disabled", None

    _io.atomic_write_bytes(src, rendered.data)
    return ConvertResult(path=src, ok=True, status="converted", code=None,
                         source_encoding=report.encoding,
                         target_encoding=report.target.codec,
                         backup=backup_status, backup_path=backup_path,
                         lossy=rendered.lossy, bytes_written=len(rendered.data),
                         error=None)


def convert(reports: Sequence[FileReport], *, backup: bool = True,
            on_progress: ProgressCallback | None = None,
            cancel: threading.Event | None = None) -> list[ConvertResult]:
    """Rewrite each file. The ONLY function in the codebase that writes to disk."""
    batch = list(reports)
    targets = {r.target for r in batch}
    if len(targets) > 1:
        raise ValueError(f"reports mix targets: {sorted(t.value for t in targets)}")
    for r in batch:
        if r.action not in _WRITABLE_ACTIONS:
            raise ValueError(f"report for {r.path} has action {r.action.value}; "
                             f"only CONVERT and NEEDS_REVIEW may be converted")
        if r.encoding is None:
            raise ValueError(f"report for {r.path} has no detected encoding")

    total = len(batch)
    results: list[ConvertResult] = []
    for i, report in enumerate(batch, 1):
        if cancel is not None and cancel.is_set():
            break
        try:
            result = _convert_one(report, backup=backup)
        except _io.FileOpError as exc:
            result = _failed(report, exc.code, str(exc.detail))
        except _clean.StructureChanged as exc:
            result = _failed(report, "STRUCTURE", str(exc))
        except (UnicodeDecodeError, UnicodeEncodeError) as exc:
            result = _failed(report, "CODEC", f"{type(exc).__name__}: {exc}")
        except OSError as exc:
            result = _failed(report, "OS", f"{type(exc).__name__}: {exc}")
        results.append(result)
        if on_progress is not None:
            on_progress(Progress("convert", i, total, report.path, result=result))
    return results
```

**Three properties fall out of this ordering and must survive any refactor:**

1. **The encode happens before any file is touched.** A `UnicodeEncodeError` or `StructureChanged`
   cannot leave a temp file or a damaged original.
2. **`rendered.data == raw` short-circuits the write.** An already-correct file is never opened for
   writing, never backed up, and its mtime never changes. Running the tool twice is a no-op.
3. **No BOM is written.** `Target.codec` is `"utf-8"`, never `"utf-8-sig"`.

---

## 8. The GUI

### 8.1 Approved layout

```
Greek SRT Converter
===================================================
Folder: [ D:/Movies/Series      ] [Browse]  [x] Recurse
Mode:   ( ) UTF-8   (o) Greek ISO-8859-7      [ Scan ]
---------------------------------------------------
  v   File          Detected     Status
 [x]  Ep01.srt      CP1253       will convert
 [x]  Ep02.srt      UTF-8        will convert
 [ ]  Ep03.srt      ISO-8859-7   already target
 [x]  Ep04.srt      UTF-8        3 chars stripped (!)
---------------------------------------------------
Preview - Ep04.srt
   00:01:12,400 --> 00:01:14,900
   <Greek subtitle text renders here>
---------------------------------------------------
[x] Backup originals      [ Convert 3 selected ]
```

Plus a sunken status bar at the very bottom (progress text, scan summary, leftover-temp count) and a
`Cancel` button + `ttk.Progressbar` beside the Convert button.

### 8.2 Widget tree

```
tk.Tk (root)
└── ConverterApp(ttk.Frame)                        pack(fill=both, expand=True)
    ├── top: ttk.Frame                             pack(fill=x)
    │   ├── ttk.Label "Folder:"                    grid 0,0
    │   ├── ttk.Entry  folder_var                  grid 0,1 sticky=ew  (weight 1)
    │   ├── ttk.Button "Browse…"                   grid 0,2
    │   └── ttk.Checkbutton "Recurse" recurse_var  grid 0,3
    ├── mode: ttk.Frame                            pack(fill=x)
    │   ├── ttk.Label "Mode:"                      pack(left)
    │   ├── ttk.Radiobutton "UTF-8"       value="utf-8"       pack(left)
    │   ├── ttk.Radiobutton "Greek ISO-8859-7" value="iso-8859-7" pack(left)
    │   └── ttk.Button "Scan"                      pack(right)
    ├── mid: ttk.Frame                             pack(fill=both, expand=True)
    │   ├── ttk.Treeview cols=(sel,file,encoding,status) show="headings"
    │   └── ttk.Scrollbar vertical
    ├── pane: ttk.LabelFrame "Preview"             pack(fill=both, expand=True)
    │   ├── tk.Text (the ONLY classic tk widget)
    │   └── ttk.Scrollbar vertical + horizontal
    ├── bottom: ttk.Frame                          pack(fill=x)
    │   ├── ttk.Checkbutton "Backup originals" backup_var   pack(left)
    │   ├── ttk.Button "Convert N selected"                 pack(right)
    │   ├── ttk.Button "Cancel"                             pack(right)
    │   └── ttk.Progressbar                                 pack(right)
    └── ttk.Label status  (packed on root, side=bottom, relief=sunken)
```

**Rule: `ttk.*` everywhere. `tk.Text` is the only permitted classic widget** — ttk has no text
widget. Give it `relief="solid", borderwidth=1` so it blends.

### 8.3 DPI awareness — must run before `tk.Tk()`

```python
import ctypes
import sys


def enable_dpi_awareness() -> None:
    """MUST be called before tkinter.Tk() is constructed."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # PROCESS_SYSTEM_DPI_AWARE
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()    # Windows 7/8 fallback
        except (AttributeError, OSError):
            pass
```

Two measured rules:

1. **Call it before `tk.Tk()`.** Tk samples the screen DPI once at startup. Calling it afterwards
   changes nothing at all — screen stayed 2560×1440, `tk scaling` stayed 1.3340, `TkDefaultFont`
   linespace stayed 15 px.
2. **Do NOT also call `root.tk.call("tk", "scaling", ...)`.** Tk 8.6.12 already derives `tk scaling`
   from the real DPI. Measured with awareness enabled: 3840×2160, `winfo fpixels 1i` = 144.07,
   `tk scaling` = 2.0010, linespace = 25 px — **identical with and without the manual call**. The
   ubiquitous StackOverflow line is a no-op here, and at worst double-scales.

Font sizes are specified in **points**; Tk converts via `tk scaling`, so `("Consolas", 10)` scales
automatically. **Never specify a font in pixels** (a negative size).

Accepted limitation: system-DPI-aware only. On a mixed-DPI multi-monitor setup the window is
bitmap-stretched on the secondary display. Tk 8.6 does not re-scale on the fly regardless.

### 8.4 Theming

```python
style = ttk.Style()
if "vista" in style.theme_names():
    style.theme_use("vista")

base = tkfont.nametofont("TkDefaultFont")
row_height = base.metrics("linespace") + 10      # 25 px @96dpi, 35 px @144dpi
style.configure("Treeview", rowheight=row_height)
style.configure("Treeview.Heading", padding=(6, 4))
style.configure("TButton", padding=(10, 4))
```

- **`vista` is already the default theme on Windows.** `ttk` widgets under it look native Windows 11
  out of the box. **Do not switch to `clam`** — it is the cross-platform fallback and looks *less*
  native here.
- `rowheight` **must** be computed, not hardcoded. The vista Treeview's default is unset and far too
  tight.
- `ttk.Treeview` tag styling is fully functional under vista on Tk 8.6.12 (verified by rendering):
  `background`, `foreground` and `font` tags all work, multiple tags combine, and the selection
  highlight correctly overrides a tag foreground.
- **Always pass `variable=` to a `ttk.Checkbutton`.** Without it the widget starts in the `alternate`
  state and renders as a filled blue box with a dash — it looks checked but is neither.
- **Minimum Tk: 8.6.10.** `ttk.Treeview` tag colours were broken by a Tk 8.6.9 regression. Python
  3.9+ on Windows ships 8.6.10 or newer, so this is free.

### 8.5 The Treeview checkbox pattern

`ttk.Treeview` has no checkable rows. Use a first **named** column holding a ballot glyph, with
`show="headings"`.

**Do the glyphs render?** Yes — but not from the font you think. Segoe UI (`TkDefaultFont`),
Consolas, Courier New, Tahoma, Arial and Lucida Console **do not contain** U+2610/U+2611/U+2612
(confirmed by parsing their `cmap` tables). Tk 8.6.12 does per-character font fallback and
substitutes a CJK font that does. Verified pixel-by-pixel against a true-notdef control character and
visually inspected: ☐ ☑ ☒ all render correctly and distinctly.

The practical consequence: **the substituted glyph is full-width and metrically unrelated to the row
font** (36 px vs 31 px for Segoe UI Symbol at size 18/144 DPI). Therefore:

```python
CHECKED   = "\u2611"   # BALLOT BOX WITH CHECK
UNCHECKED = "\u2610"   # BALLOT BOX

# size the column from a RUNTIME measurement, never a hardcoded pixel count
glyph_w = max(base.measure(CHECKED), base.measure(UNCHECKED)) + 22
tree.column("sel", width=glyph_w, minwidth=glyph_w, stretch=False, anchor="center")
```

No fallback is required. If one is ever wanted it is a two-line change:
`CHECKED, UNCHECKED = "[x]", "[ ]"`.

**Do not use a `tk.PhotoImage` variant.** Images can only be displayed in the tree column `#0` —
setting one into a named column silently renders the literal string `pyimage1`. Adopting it would
also change the hit test from `region == "cell"` to `region == "tree"`. The glyph approach specified
here is simpler; use it.

**Click routing.** Measured `identify_*` return values with `show="headings"`:

| click target | region | column | row |
|---|---|---|---|
| column header | `'heading'` | `'#1'` | `''` |
| first data cell | `'cell'` | `'#1'` | `'I001'` |
| header separator | `'separator'` | `'#1'` | `''` |
| empty area below rows | `'nothing'` | `'#1'` | `''` |

```python
def on_tree_click(self, event):
    region = self.tree.identify_region(event.x, event.y)
    if region == "separator":
        return None                       # let ttk resize the column
    if region == "heading":
        return None                       # heading command= handles select-all
    if region != "cell":
        return None                       # 'nothing' -> ignore
    if self.tree.identify_column(event.x) != "#1":
        return None                       # other columns: normal row selection
    row = self.tree.identify_row(event.y)
    if not row:
        return None
    self.toggle_row(row)
    return "break"                        # suppress selection change + drag start
```

Returning `"break"` **only** for column `#1` is what makes this feel right: clicking the checkbox
toggles without moving the selection (verified: `tree.selection()` stays `()`), while clicking any
other column selects the row and refreshes the preview.

Bind with `add="+"` so the built-in Treeview bindings are not replaced.

**Toggleability rule (decided):** only rows whose action is `CONVERT` or `NEEDS_REVIEW` are
toggleable. `ALREADY_TARGET` and `UNREADABLE` rows render `UNCHECKED` and a click on their checkbox
cell is a **no-op**. This removes the possibility of a `ValueError` from `convert()` entirely.

**Select-all header.** Put a `command` on the heading; the `<Button-1>` handler above deliberately
does not swallow it. The header glyph doubles as the state readout. Select-all ticks only `CONVERT`
rows — never `NEEDS_REVIEW`, which is the whole point of that action.

### 8.6 The preview pane

Widget: `tk.Text`. Greek renders correctly — verified by both `cmap` inspection and on-screen
rendering. Consolas, Courier New, Segoe UI, Tahoma and Arial all cover the complete modern Greek
repertoire including Ά Έ Ή Ί Ό Ύ Ώ, Ϊ Ϋ ϊ ϋ and the composed ΐ ΰ. On accented **capitals** the tonos
is drawn to the upper-**left** (`Ήταν`) — that is correct Greek typographic convention, not clipping.

**Pick the font at runtime.** A missing family does not raise and does not draw boxes — Tk silently
substitutes **Arial**, a *proportional* font, which would quietly destroy timecode alignment.

```python
def pick_mono_font(root) -> str:
    """First installed monospace family that covers modern Greek."""
    available = set(tkfont.families(root))
    for family in ("Consolas", "Courier New", "Lucida Console"):
        if family in available:
            return family
    return tkfont.nametofont("TkFixedFont").actual("family")
```

**Do not hardcode Cascadia Mono / Cascadia Code.** They are listed by `tkfont.families()` on the
reference machine but exist in **neither** `C:\Windows\Fonts` **nor** `%LOCALAPPDATA%\Microsoft\
Windows\Fonts` **nor** the font registry — they ship with the Windows Terminal MSIX package.

Use `wrap="none"` plus a horizontal scrollbar. Wrapping a subtitle line changes its apparent shape
and undermines the point of the preview.

#### CRITICAL: the disabled-Text trap

The pane is read-only, so it lives at `state="disabled"`. But **`insert()` and `delete()` on a
disabled Text are silently ignored — no exception is raised.** Verified. Forget the dance below and
the preview stays permanently blank with zero diagnostics. Since the preview is the entire safety
mechanism of this design, this is the single most important line-level rule in the GUI:

```python
def on_tree_select(self, _event=None):
    sel = self.tree.selection()
    if not sel:
        return
    report = self.reports.get(sel[0])
    if report is None:
        return
    self.preview.configure(state="normal")      # 1. enable
    self.preview.delete("1.0", "end")           # 2. mutate
    self.preview.insert("1.0", "\n".join(report.preview))
    self.preview.configure(state="disabled")    # 3. re-disable
    self.preview.yview_moveto(0.0)
```

`get()` still works while disabled, and the user can still select and Ctrl-C the text.

### 8.7 Threading model

**Invariant: widgets are touched only on the Tk main thread.** The worker's sole output channel is
`queue.Queue.put()`.

Message protocol — the worker emits `(kind, payload)` tuples:

| kind | payload | handled by |
|---|---|---|
| `"progress"` | `(done, total, filename)` | progress bar + status line |
| `"row"` | a `FileReport` | insert one Treeview row |
| `"result"` | a `ConvertResult` | update that row's status cell |
| `"done"` | summary string | status line |
| `"error"` | `repr(exc)` | error dialog |
| `"finished"` | `None` | re-enable buttons, clear `self.worker` |

`"finished"` is emitted from a `finally:` so it is guaranteed even if the worker raises.

```python
def _spawn(self, fn, args: tuple) -> None:
    def runner() -> None:
        try:
            fn(*args)
        except Exception as exc:
            self.queue.put(("error", repr(exc)))
        finally:
            self.queue.put(("finished", None))
    self.worker = threading.Thread(target=runner, daemon=True, name="srt-worker")
    self.worker.start()
    self._schedule_pump()


def _schedule_pump(self) -> None:
    self._after_id = self.root.after(50, self._pump)


def _pump(self) -> None:
    """Runs on the Tk main thread. The ONLY place widgets get touched."""
    self._after_id = None
    try:
        while True:                              # drain FULLY each tick
            kind, payload = self.queue.get_nowait()
            self._handle(kind, payload)
    except queue.Empty:
        pass
    if self.worker is not None and self.worker.is_alive():
        self._schedule_pump()                    # self-terminating
```

The loop **drains the queue fully** on every tick rather than taking one item — with a fast scan the
producer easily outruns a 50 ms tick and one-item-per-tick would fall behind unboundedly. It stores
`self._after_id` so shutdown can cancel a pending callback.

**`except Exception` in `runner()` is correct and is the one place it is permitted** — it is a
front-end top-level handler whose entire job is to route an unexpected failure to a dialog instead of
a dead thread. This does not relax §4.9, which governs `greek_srt/` only.

#### WM_DELETE_WINDOW while a worker is running

Three distinct failures, all reproduced:

1. **Worker touches a widget after `destroy()`** → `RuntimeError: main thread is not in main loop`.
2. **A pending `after()` callback survives `destroy()`** → Tcl prints
   `invalid command name "2167466516608pump" while executing … ("after" script)`. This goes to the
   process's **C-level stderr**, so `sys.stderr` redirection does **not** capture it — and in a
   `--windowed` build it goes nowhere at all.
3. **Worst: `destroy()` without setting the cancel flag leaves the worker running.** Measured: 66
   further work items executed after the window was gone, then the daemon thread killed abruptly at
   interpreter exit — potentially mid-write.

| close style | Tcl stderr | worker alive after | work items |
|---|---|---|---|
| `destroy()` only | `invalid command name …` | **True** | 66 |
| `after_cancel` only | clean | **True** | 65 |
| `after_cancel` + cancel + `join` | clean | **False** | 21 |

**The correct handler — order matters:**

```python
def on_close(self) -> None:
    if self.worker is not None and self.worker.is_alive():
        if not messagebox.askokcancel(
                APP_NAME, "A job is still running. Stop it and quit?", parent=self.root):
            return
    self.cancel.set()                                  # 1. tell the worker to stop
    if self._after_id is not None:                     # 2. kill the pending after()
        try:
            self.root.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None
    if self.worker is not None:                        # 3. wait for it to finish
        self.worker.join(timeout=5.0)
    save_settings(...)
    self.root.destroy()                                # 4. only now destroy
```

### 8.8 Folder picking and persisted settings

```python
seed = self.folder_var.get().strip() or self.settings.get("last_folder", "")
if not seed or not os.path.isdir(seed):
    seed = os.path.expanduser("~")
chosen = filedialog.askdirectory(
    parent=self.root,
    title="Choose the folder containing your .srt files",
    initialdir=seed,
    mustexist=True,
)
if not chosen:                       # Cancel returns "" (empty str) -- NEVER None
    return
folder = os.path.normpath(chosen)    # returns FORWARD slashes on Windows
```

Measured: returns a `str` with forward slashes on success (`'C:/Users/.../fixtures'`), `''` on
Cancel. `initialdir` genuinely seeds it; `title` is applied. On Windows 11 / Tk 8.6.12 this is the
**modern `IFileDialog` folder picker**, DPI-crisp because the process is DPI-aware.

Settings: `%APPDATA%\GreekSrtConverter\settings.json`, JSON, UTF-8, best-effort (never let a settings
failure break the app). Round-trip verified including a Greek path (`D:\Movies\Σειρές`). Persist
`last_folder`, `recurse`, `target`, `backup`. Write on folder pick and on close.

### 8.9 Surfacing errors

In a `--windowed` build there is no console, so an unhandled exception in a Tk callback vanishes:

```python
def report_exception(exc, val, tb):
    import traceback
    messagebox.showerror(APP_NAME, "".join(traceback.format_exception(exc, val, tb))[-1500:])

root.report_callback_exception = report_exception
```

### 8.10 Row rendering rules

| `action` | Status text | tags | ticked | toggleable |
|---|---|---|---|---|
| `UNREADABLE` | `unreadable - {error}` | `bad` (`#c02626`) | no | **no** |
| `ALREADY_TARGET` | `already target` | `skip` (`#8a8a8a`) | no | **no** |
| `NEEDS_REVIEW` | `NEEDS REVIEW - {pct}% of non-ASCII lost` | `review` (`#c02626`, bold) | **no** | yes |
| `CONVERT`, `dropped_count > 0` | `{n} chars stripped (!)` | `warn` (`#b35c00`) | **yes** | yes |
| `CONVERT`, BOM-only change | `will convert (BOM removed)` | — | **yes** | yes |
| `CONVERT`, otherwise | `will convert` | — | **yes** | yes |

Even rows also get the `stripe` tag (`background="#f5f7fa"`).

The `Detected` column renders `f"{report.encoding} ({report.confidence.value})"`, e.g.
`cp1253 (guess)`, `utf-8-sig (certain)`. On a scoring tie this reads `cp1253 (guess)` for a file the
user may believe is ISO-8859-7 — that is correct and harmless (§5.3), and no extra tie marker is
added.

### 8.11 `gui.py` — reference implementation

This file was executed end to end with synthetic events and passes every assertion against fixtures
in CP1253, ISO-8859-7, UTF-8, UTF-8-BOM, UTF-16-LE and UTF-8-with-smart-punctuation. **Paste it.**

```python
"""gui.py -- tkinter front-end for greek_srt. Run: python gui.py"""

from __future__ import annotations

import ctypes
import json
import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter import font as tkfont

from greek_srt import Action, FileReport, Target, convert, scan
from greek_srt.fileio import count_temp_files

APP_NAME = "Greek SRT Converter"
CHECKED = "\u2611"      # BALLOT BOX WITH CHECK
UNCHECKED = "\u2610"    # BALLOT BOX
SETTINGS = Path(os.environ.get("APPDATA", Path.home())) / "GreekSrtConverter" / "settings.json"


def enable_dpi_awareness() -> None:
    """MUST be called before tkinter.Tk() is constructed."""
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(data: dict) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def pick_mono_font(root: tk.Misc) -> str:
    available = set(tkfont.families(root))
    for family in ("Consolas", "Courier New", "Lucida Console"):
        if family in available:
            return family
    return tkfont.nametofont("TkFixedFont").actual("family")


def row_text(report: FileReport) -> tuple[str, list[str], bool]:
    """-> (status text, extra tags, ticked-and-toggleable)."""
    if report.action is Action.UNREADABLE:
        return f"unreadable - {report.error}", ["bad"], False
    if report.action is Action.ALREADY_TARGET:
        return "already target", ["skip"], False
    if report.action is Action.NEEDS_REVIEW:
        return (f"NEEDS REVIEW - {report.loss_ratio:.0%} of non-ASCII lost",
                ["review"], False)
    if report.dropped_count:
        return f"{report.dropped_count} chars stripped (!)", ["warn"], True
    if report.encoding == "utf-8-sig" and report.target is Target.UTF_8:
        return "will convert (BOM removed)", [], True
    return "will convert", [], True


class ConverterApp(ttk.Frame):
    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master, padding=0)
        self.root: tk.Tk = master
        self.settings = load_settings()
        self.queue: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.worker: threading.Thread | None = None
        self._after_id: str | None = None
        self.checked: dict[str, bool] = {}
        self.reports: dict[str, FileReport] = {}

        self.mono = pick_mono_font(master)
        self._init_style()
        self.pack(fill="both", expand=True)
        self._build()
        master.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------- style
    def _init_style(self) -> None:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
        base = tkfont.nametofont("TkDefaultFont")
        self.row_height = base.metrics("linespace") + 10
        style.configure("Treeview", rowheight=self.row_height)
        style.configure("Treeview.Heading", padding=(6, 4))
        style.configure("TButton", padding=(10, 4))

    # ------------------------------------------------------------- widgets
    def _build(self) -> None:
        base = tkfont.nametofont("TkDefaultFont")

        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Folder:").grid(row=0, column=0, sticky="w")
        self.folder_var = tk.StringVar(value=self.settings.get("last_folder", ""))
        ttk.Entry(top, textvariable=self.folder_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Browse\u2026", command=self.browse).grid(row=0, column=2)
        self.recurse_var = tk.BooleanVar(value=bool(self.settings.get("recurse", False)))
        ttk.Checkbutton(top, text="Recurse", variable=self.recurse_var,
                        onvalue=True, offvalue=False).grid(row=0, column=3, padx=(12, 0))
        top.columnconfigure(1, weight=1)

        mode = ttk.Frame(self, padding=(12, 4))
        mode.pack(fill="x")
        ttk.Label(mode, text="Mode:").pack(side="left")
        self.target_var = tk.StringVar(value=self.settings.get("target", "utf-8"))
        ttk.Radiobutton(mode, text="UTF-8", variable=self.target_var,
                        value="utf-8").pack(side="left", padx=(8, 0))
        ttk.Radiobutton(mode, text="Greek ISO-8859-7", variable=self.target_var,
                        value="iso-8859-7").pack(side="left", padx=(10, 0))
        self.scan_btn = ttk.Button(mode, text="Scan", command=self.start_scan)
        self.scan_btn.pack(side="right")

        mid = ttk.Frame(self, padding=(12, 6))
        mid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(mid, columns=("sel", "file", "encoding", "status"),
                                 show="headings", selectmode="browse", height=8)
        self.tree.heading("sel", text=CHECKED, command=self.toggle_all)
        self.tree.heading("file", text="File", anchor="w")
        self.tree.heading("encoding", text="Detected", anchor="w")
        self.tree.heading("status", text="Status", anchor="w")
        glyph_w = max(base.measure(CHECKED), base.measure(UNCHECKED)) + 22
        self.tree.column("sel", width=glyph_w, minwidth=glyph_w, stretch=False, anchor="center")
        self.tree.column("file", width=280, minwidth=140, anchor="w")
        self.tree.column("encoding", width=140, minwidth=90, anchor="w")
        self.tree.column("status", width=260, minwidth=120, anchor="w")
        bar = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        mid.rowconfigure(0, weight=1)
        mid.columnconfigure(0, weight=1)

        self.tree.tag_configure("stripe", background="#f5f7fa")
        self.tree.tag_configure("warn", foreground="#b35c00")
        self.tree.tag_configure("skip", foreground="#8a8a8a")
        self.tree.tag_configure("bad", foreground="#c02626")
        self.tree.tag_configure(
            "review", foreground="#c02626",
            font=(base.actual("family"), base.actual("size"), "bold"))
        self.tree.bind("<Button-1>", self.on_tree_click, add="+")
        self.tree.bind("<space>", self.on_space)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        pane = ttk.LabelFrame(self, text="Preview", padding=(8, 6))
        pane.pack(fill="both", expand=True, padx=12, pady=(0, 6))
        self.preview = tk.Text(pane, height=9, wrap="none", undo=False,
                               font=(self.mono, 10), background="#ffffff",
                               foreground="#111111", relief="solid", borderwidth=1,
                               spacing1=1, spacing3=1, padx=6, pady=4)
        pv = ttk.Scrollbar(pane, orient="vertical", command=self.preview.yview)
        ph = ttk.Scrollbar(pane, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=pv.set, xscrollcommand=ph.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        pv.grid(row=0, column=1, sticky="ns")
        ph.grid(row=1, column=0, sticky="ew")
        pane.rowconfigure(0, weight=1)
        pane.columnconfigure(0, weight=1)
        self.preview.configure(state="disabled")

        bottom = ttk.Frame(self, padding=(12, 0, 12, 10))
        bottom.pack(fill="x")
        self.backup_var = tk.BooleanVar(value=bool(self.settings.get("backup", True)))
        ttk.Checkbutton(bottom, text="Backup originals", variable=self.backup_var,
                        onvalue=True, offvalue=False).pack(side="left")
        self.convert_btn = ttk.Button(bottom, text="Convert 0 selected",
                                      state="disabled", command=self.start_convert)
        self.convert_btn.pack(side="right")
        self.cancel_btn = ttk.Button(bottom, text="Cancel", state="disabled",
                                     command=self.cancel.set)
        self.cancel_btn.pack(side="right", padx=(0, 8))
        self.progress = ttk.Progressbar(bottom, mode="determinate", length=180)
        self.progress.pack(side="right", padx=(0, 10))

        self.status = ttk.Label(self.root, text="Ready", relief="sunken",
                                anchor="w", padding=(8, 3))
        self.status.pack(fill="x", side="bottom")

    # ------------------------------------------------------------- folder
    def browse(self) -> None:
        seed = self.folder_var.get().strip() or self.settings.get("last_folder", "")
        if not seed or not os.path.isdir(seed):
            seed = os.path.expanduser("~")
        chosen = filedialog.askdirectory(
            parent=self.root,
            title="Choose the folder containing your .srt files",
            initialdir=seed, mustexist=True)
        if not chosen:            # Cancel returns "" (empty str), never None
            return
        self.folder_var.set(os.path.normpath(chosen))
        self.settings["last_folder"] = os.path.normpath(chosen)
        save_settings(self.settings)

    # ------------------------------------------------------------- checkbox
    def _toggleable(self, iid: str) -> bool:
        report = self.reports.get(iid)
        return report is not None and report.writable

    def on_tree_click(self, event: tk.Event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "separator" or region == "heading" or region != "cell":
            return None
        if self.tree.identify_column(event.x) != "#1":
            return None
        row = self.tree.identify_row(event.y)
        if not row:
            return None
        if self._toggleable(row):
            self.set_checked(row, not self.checked.get(row, False))
        return "break"

    def on_space(self, _event: tk.Event) -> str:
        for iid in self.tree.selection():
            if self._toggleable(iid):
                self.set_checked(iid, not self.checked.get(iid, False))
        return "break"

    def set_checked(self, iid: str, value: bool) -> None:
        self.checked[iid] = value
        self.tree.set(iid, "sel", CHECKED if value else UNCHECKED)
        self.refresh_convert_button()

    def toggle_all(self) -> None:
        rows = [i for i in self.tree.get_children("")
                if self.reports[i].action is Action.CONVERT]
        if not rows:
            return
        new_value = not all(self.checked.get(i, False) for i in rows)
        for iid in rows:
            self.checked[iid] = new_value
            self.tree.set(iid, "sel", CHECKED if new_value else UNCHECKED)
        self.tree.heading("sel", text=CHECKED if new_value else UNCHECKED)
        self.refresh_convert_button()

    def refresh_convert_button(self) -> None:
        n = sum(1 for i in self.tree.get_children("") if self.checked.get(i))
        self.convert_btn.configure(text=f"Convert {n} selected",
                                   state="normal" if n else "disabled")

    # ------------------------------------------------------------- preview
    def on_tree_select(self, _event: tk.Event | None = None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        report = self.reports.get(sel[0])
        if report is None:
            return
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", "\n".join(report.preview))
        self.preview.configure(state="disabled")
        self.preview.yview_moveto(0.0)

    # ------------------------------------------------------------- workers
    def _set_busy(self, busy: bool) -> None:
        self.scan_btn.configure(state="disabled" if busy else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")
        if busy:
            self.convert_btn.configure(state="disabled")
        else:
            self.refresh_convert_button()

    def start_scan(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        folder = self.folder_var.get().strip()
        if not os.path.isdir(folder):
            messagebox.showerror(APP_NAME, "Pick an existing folder first.", parent=self.root)
            return
        self.tree.delete(*self.tree.get_children(""))
        self.checked.clear()
        self.reports.clear()
        self.cancel.clear()
        self._set_busy(True)
        self.status.configure(text="Scanning\u2026")
        self._spawn(self._scan_worker,
                    (folder, self.recurse_var.get(), Target(self.target_var.get())))

    def start_convert(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        chosen = [(i, self.reports[i]) for i in self.tree.get_children("")
                  if self.checked.get(i)]
        if not chosen:
            return
        risky = sum(1 for _, r in chosen if r.action is Action.NEEDS_REVIEW)
        extra = f"\n\n{risky} file(s) are flagged NEEDS REVIEW." if risky else ""
        if not messagebox.askyesno(
                APP_NAME,
                f"Overwrite {len(chosen)} file(s) in place?\n\n"
                f"Backups: {'ON' if self.backup_var.get() else 'OFF'}{extra}",
                parent=self.root):
            return
        self._row_by_path = {r.path: i for i, r in chosen}
        self.cancel.clear()
        self._set_busy(True)
        self._spawn(self._convert_worker,
                    ([r for _, r in chosen], self.backup_var.get()))

    def _spawn(self, fn, args: tuple) -> None:
        def runner() -> None:
            try:
                fn(*args)
            except Exception as exc:
                self.queue.put(("error", repr(exc)))
            finally:
                self.queue.put(("finished", None))
        self.worker = threading.Thread(target=runner, daemon=True, name="srt-worker")
        self.worker.start()
        self._schedule_pump()

    def _schedule_pump(self) -> None:
        self._after_id = self.root.after(50, self._pump)

    def _pump(self) -> None:
        """Runs on the Tk main thread. The ONLY place widgets get touched."""
        self._after_id = None
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                self._handle(kind, payload)
        except queue.Empty:
            pass
        if self.worker is not None and self.worker.is_alive():
            self._schedule_pump()

    def _handle(self, kind: str, payload) -> None:
        if kind == "progress":
            done, total, name = payload
            self.progress.configure(maximum=max(total, 1), value=done)
            self.status.configure(text=f"{done}/{total}  {name}")
        elif kind == "row":
            self._insert_row(payload)
        elif kind == "result":
            self._apply_result(payload)
        elif kind == "done":
            self.status.configure(text=payload)
        elif kind == "error":
            self.status.configure(text="Error")
            messagebox.showerror(APP_NAME, str(payload), parent=self.root)
        elif kind == "finished":
            self.worker = None
            self._set_busy(False)

    def _insert_row(self, report: FileReport) -> None:
        n = len(self.tree.get_children(""))
        tags: list[str] = ["stripe"] if n % 2 else []
        status, extra, ticked = row_text(report)
        tags.extend(extra)
        enc = (f"{report.encoding} ({report.confidence.value})"
               if report.encoding else "-")
        iid = self.tree.insert("", "end",
                               values=(CHECKED if ticked else UNCHECKED,
                                       report.path.name, enc, status),
                               tags=tuple(tags))
        self.checked[iid] = ticked
        self.reports[iid] = report
        self.refresh_convert_button()

    def _apply_result(self, result) -> None:
        iid = getattr(self, "_row_by_path", {}).get(result.path)
        if iid is None:
            return
        if result.ok and result.status == "converted":
            text = f"converted (backup: {result.backup})"
        elif result.ok:
            text = "unchanged"
        else:
            text = f"FAILED [{result.code}] {result.error}"
        self.tree.set(iid, "status", text)
        self.tree.set(iid, "sel", UNCHECKED)
        self.checked[iid] = False
        self.refresh_convert_button()

    # ------------------------------------------------------------- core calls
    def _scan_worker(self, folder: str, recurse: bool, target: Target) -> None:
        def on_progress(p) -> None:
            self.queue.put(("progress", (p.done, p.total, p.path.name)))
            self.queue.put(("row", p.report))
        reports = scan(folder, recursive=recurse, target=target,
                       on_progress=on_progress, cancel=self.cancel)
        leftovers = count_temp_files(Path(folder), recursive=recurse)
        note = f"; {leftovers} leftover temp file(s) from an interrupted run" if leftovers else ""
        verb = "Cancelled after" if self.cancel.is_set() else "Scanned"
        self.queue.put(("done", f"{verb} {len(reports)} file(s){note}"))

    def _convert_worker(self, reports: list[FileReport], backup: bool) -> None:
        def on_progress(p) -> None:
            self.queue.put(("progress", (p.done, p.total, p.path.name)))
            self.queue.put(("result", p.result))
        results = convert(reports, backup=backup,
                          on_progress=on_progress, cancel=self.cancel)
        ok = sum(1 for r in results if r.ok)
        bad = len(results) - ok
        self.queue.put(("done", f"Converted {ok} file(s), {bad} failed"))

    # ------------------------------------------------------------- shutdown
    def on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            if not messagebox.askokcancel(
                    APP_NAME, "A job is still running. Stop it and quit?", parent=self.root):
                return
        self.cancel.set()                                  # 1. tell worker to stop
        if self._after_id is not None:                     # 2. kill pending after()
            try:
                self.root.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self.worker is not None:                        # 3. wait for it
            self.worker.join(timeout=5.0)
        self.settings.update(last_folder=self.folder_var.get().strip(),
                             recurse=self.recurse_var.get(),
                             target=self.target_var.get(),
                             backup=self.backup_var.get())
        save_settings(self.settings)
        self.root.destroy()                                # 4. only now destroy


def main() -> None:
    enable_dpi_awareness()          # BEFORE Tk()
    root = tk.Tk()
    root.title(APP_NAME)
    root.minsize(760, 560)

    def report_exception(exc, val, tb):
        import traceback
        messagebox.showerror(APP_NAME,
                             "".join(traceback.format_exception(exc, val, tb))[-1500:])
    root.report_callback_exception = report_exception

    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
```

**`gui.py` must stay importable without side effects.** All startup work lives in `main()` behind
`if __name__ == "__main__":`. This is what makes the smoke-import test possible and PyInstaller's
static analysis clean.

---

## 9. The CLI rebuild

`cli.py` keeps the existing interactive flow — same prompts, same order, same defaults — but calls
the core. **No `argparse`, no flags.** It remains a purely interactive console app.

Structure:

```python
"""cli.py -- interactive command-line front-end for greek_srt. Run: python cli.py"""

from __future__ import annotations

import datetime
import sys
from pathlib import Path

from greek_srt import (
    Action, ConvertResult, FileReport, Progress, Target, convert, scan,
)
from greek_srt.fileio import count_temp_files


def _prompt_target() -> Target: ...
def _prompt_folder() -> str | None: ...          # None means quit
def _print_table(reports: list[FileReport]) -> None: ...
def _print_summary(results: list[ConvertResult]) -> None: ...
def run_once() -> bool: ...                      # False means quit
def main() -> int: ...


if __name__ == "__main__":
    raise SystemExit(main())
```

Behaviour, prompt by prompt:

1. **Banner.** `SRT File Encoding Converter`, then
   `Detects: UTF-8 (BOM/BOM-less), UTF-16, UTF-32, CP1253, ISO-8859-7, CP1252, ASCII`.
   The old banner's encoding list was wrong (it advertised `latin1`, which is now deliberately absent)
   and must be corrected.
2. **Conversion mode.** `1` → `Target.UTF_8`, `2` → `Target.ISO_8859_7`. Re-prompt on anything else.
   The old warning *"Characters not supported by ISO-8859-7 will cause fallback to UTF-8"* is
   **deleted** — it is now false. Replace with:
   `Note: characters ISO-8859-7 cannot represent are folded or dropped; the scan table shows exactly which.`
3. **Folder path.** `quit`/`exit`/`q` exits. Empty re-prompts. Strip surrounding quotes with
   `.strip("\"'")` (paste convenience).
4. **Recursive?** `y`/`yes` → True, default False. Keep the "this will process ALL subfolders" confirm.
5. **Backup?** default **Yes** (`n`/`no` → False).
6. **Dry run?** default No. **This is the fixed BUG:** dry-run now runs `scan()` and prints the full
   table, then returns without calling `convert()`. The old code returned at line 176 before
   detecting anything.
7. **Scan.** `scan(folder, recursive=..., target=..., on_progress=...)`. `on_progress` prints
   `[{done}/{total}] {name}`. Then print the table and, if `count_temp_files() > 0`, a line
   `NOTE: {n} leftover temp file(s) from an interrupted run.`
8. **If dry run:** stop here, print `DRY RUN - no files were modified`, return.
9. **Confirm.** Print counts by action; if any `NEEDS_REVIEW`, print a bold warning listing them and
   require an explicit `y` to include them. Default is to convert only `Action.CONVERT` reports.
10. **Convert.** `convert(selected, backup=..., on_progress=...)`, then the summary.
11. **"Process another folder?"** loop, as today.

Table format (mirrors the GUI columns):

```
   #  FILE                              DETECTED           STATUS
   1  Ep01.srt                          cp1253 (guess)     will convert
   2  Ep02.srt                          utf-8-sig (certain) will convert (BOM removed)
   3  Ep03.srt                          iso-8859-7 (guess) already target
   4  Ep04.srt                          utf-8 (certain)    3 chars stripped (!)
   5  chinese.srt                       utf-8 (certain)    NEEDS REVIEW - 97% of non-ASCII lost
   6  notes.srt                         -                  unreadable - no SubRip timecode line found
```

For rows with `lossy`, print an indented detail line listing up to 10 `LossyChange` entries as
`U+201C '"' x4` (replaced) or `U+4F60 DROPPED x31`.

Summary:

```
CONVERSION SUMMARY - Completed at 2026-07-28 20:41:02
   Successfully converted: 12
   Unchanged:               3
   Failed:                  1
   Backups created:        12  (kept existing: 0)
```

Exit code: `main()` returns `0` if no result has `ok is False`, else `1`.

`cli.py` may `print()` freely — it is a console app. It must never import `tkinter`.

---

## 10. Testing plan

`pytest` over `tmp_path` fixtures. `requirements-dev.txt` contains exactly `pytest>=7`. An **empty
`conftest.py` at the repo root** is required so pytest puts the repo root on `sys.path` and
`import greek_srt` works.

Run: `python -m pytest -q`

### `tests/test_detect.py`

| Test name | Asserts |
|---|---|
| `test_empty_is_utf8_certain` | `d(b"")[0:2] == ("utf-8", CERTAIN)` |
| `test_pure_ascii_is_ascii_certain` | ASCII SRT → `("ascii", CERTAIN)` |
| `test_utf8_whole_buffer_certain` | Greek UTF-8 → `("utf-8", CERTAIN)` |
| `test_utf8_bom_is_utf8_sig` | `BOM_UTF8 + …` → `("utf-8-sig", CERTAIN)` |
| `test_utf16_le_bom` / `test_utf16_be_bom` | correct name, `CERTAIN` |
| `test_utf32_bom_not_shadowed_by_utf16` | `FF FE 00 00` → `utf-32-le`, not `utf-16-le` |
| `test_bomless_utf16_by_nul_parity` | both endiannesses → `GUESS` |
| `test_binary_is_none` | PNG header bytes → `encoding is None` |
| `test_cp1253_smart_punctuation_beats_iso` | **BUG 2 regression.** CP1253 + `— …` → `cp1253` |
| `test_alpha_tonos_discriminator_both_ways` | `Ά` text: cp1253 bytes → `cp1253`; iso bytes → `iso-8859-7` |
| `test_western_european_not_called_greek` | French, Spanish, German, English-smart in cp1252 → `cp1252` (4 cases) |
| `test_documented_tie_prefers_cp1253` | plain Greek → `cp1253`; decodes identical; both re-encodes round-trip |
| `test_latin1_never_returned` | `"latin1" not in SINGLE_BYTE_CANDIDATES` |
| `test_bad_byte_past_8kib_is_caught` | **BUG 2a regression.** 9000-byte UTF-8 with a bad tail is not reported `utf-8` |
| `test_read_codec_maps_utf8_to_sig` | `read_codec("utf-8") == "utf-8-sig"`; everything else identity |

### `tests/test_clean.py`

| Test name | Asserts |
|---|---|
| `test_table_R1_no_ascii_keys` | no key has `ord < 128` |
| `test_table_R2_no_colon_comma_gt_in_values` | no value contains `:`, `,` or `>` |
| `test_table_R3_values_encodable` | every value `.encode("iso-8859-7")` succeeds |
| `test_table_no_identity_entries` | no `k == v` |
| `test_table_R4_no_needless_folding` | for every key except U+00A0/U+00AD, not (`encode(iso) == encode(cp1253)`) |
| `test_table_R5_keeps_alpha_tonos` | `\u0386` and `\u0385` are **not** in the table; `\u2018 \u2019 \u20ac \u20af \u037a` **are** |
| `test_table_keeps_native_chars` | `\u2015 \u00b7 \u00ab \u00bb \u00a9 \u00a3 \u00b1 \u00bd` are not in the table |
| `test_forge_search_3char` | over `list(ISO_FOLD_MAP) + list("-<>. a")`, every 3-char input whose fold contains `-->` must have contained it already. **Expected: 120 raw hits at `fold_to_iso` level, all of the class "two dash-producing chars + literal `>`". Assert `fold_document` raises `StructureChanged` for each.** |
| `test_structural_inertness` | `fold_to_iso(s) == s` with empty maps for `"1"`, `"0001"`, `"999999"`, `"00:01:12,400 --> 00:01:14,900"`, `"00:00:01,000 --> 00:00:03,500 X1:100 X2:600 Y1:20 Y2:50"`, `"01:02:03.456 --> 01:02:05.000"` |
| `test_totality_fuzz` | 6 × 8000 random codepoints in `U+0020..U+11000` (surrogates excluded); `fold_to_iso(s).encode("iso-8859-7")` never raises |
| `test_idempotence` | `fold_to_iso(fold_to_iso(x)[0])` returns `x` unchanged with empty maps |
| `test_guard_fires_on_forged_arrow` | `fold_document("1\n00:00:01,000 --> 00:00:02,000\n\u2010\u2010> nai\n")` raises `StructureChanged` with `"gained a '-->'"` |
| `test_guard_allows_real_arrow_in_text` | a line literally containing `Wait --> what?` passes through untouched |
| `test_c0_c1_controls_dropped` | `\x00`, `\x1f`, `\x85`, `\x9f` dropped; `\t \n \r` kept |
| `test_split_lines_keep_roundtrip` | for CRLF / LF / CR-only / mixed / empty, rejoining reproduces the input exactly |
| `test_render_preserves_newlines` | for each of CRLF/LF/CR/mixed and each target, output CR/LF/CRLF counts equal input counts |
| `test_render_strips_all_bom` | a text with U+FEFF at position 0 and mid-file yields bytes with neither |
| `test_analyze_agrees_with_fold` | the `lossy` tuple's dropped set equals the characters actually absent from the folded output |

### `tests/test_fileio.py`

| Test name | Asserts |
|---|---|
| `test_backup_never_overwritten` | pre-create `__orig__x.srt` with sentinel bytes; convert; sentinel survives, `backup == "kept-existing"` |
| `test_backup_created_preserves_mtime` | `copy2` mtime equality |
| `test_backup_readonly_bit_cleared` | backup is writable even from a read-only source |
| `test_orig_prefix_excluded` | folder with `Ep01.srt` + `__orig__Ep01.srt` → `iter_srt_files` returns exactly one |
| `test_orig_prefix_excluded_case_insensitive` | `__ORIG__Ep01.srt` also excluded |
| `test_temp_files_excluded` | `.srtconv-abc.tmp` is not returned and not matched as `.srt` |
| `test_suffix_match_is_case_insensitive` | `Ep01.SRT` is found |
| `test_atomicity_on_replace_failure` | monkeypatch `os.replace` to raise `PermissionError(13, "Access is denied", None, 5)`; original bytes unchanged, **no `.srtconv-*.tmp` remains**, `FileOpError.code == "LOCKED"` |
| `test_no_temp_left_after_encode_failure` | force a `StructureChanged`; original unchanged, no temp, and **no UTF-8 fallback file written** |
| `test_readonly_target_converted_and_restored` | `os.chmod(p, stat.S_IREAD)`; convert succeeds; read-only still set afterwards. `@pytest.mark.skipif(os.name != "nt")` |
| `test_locked_file_reports_LOCKED` | hold the target open in a `subprocess`; result `code == "LOCKED"`, original bytes survive. `@pytest.mark.skipif(os.name != "nt")` |
| `test_long_path_idempotent` | `long_path(long_path(p)) == long_path(p)`; UNC maps to `\\?\UNC\...` |

### `tests/test_convert.py`

| Test name | Asserts |
|---|---|
| `test_scan_leaves_folder_byte_identical` | **INV-1.** SHA-256 + `mtime_ns` snapshot of a 10-file tree before and after `scan()`; maps equal |
| `test_roundtrip_all_encodings_both_targets` | 8 source kinds (cp1253, iso-8859-7, utf-8, utf-8-sig, utf-16 LE+BOM, utf-16 BE+BOM, utf-16 LE BOM-less, ascii) × 2 targets; converted bytes decode under the target and the decoded text equals the source text minus BOM and minus folded characters |
| `test_already_target_is_label_independent` | an ISO-8859-7 Greek file detected as `cp1253` still reports `ALREADY_TARGET` for the ISO target |
| `test_idempotence` | convert twice; second run reports `ALREADY_TARGET` at scan and `status == "unchanged"` at convert; bytes identical; mtime unchanged |
| `test_bug1_iso_output_is_really_iso` | **BUG 1 regression.** A file with `" " — …` targeted at ISO-8859-7 produces bytes that `decode("iso-8859-7")` accepts and that are **not** valid UTF-8 for the Greek portion; assert no fallback occurred |
| `test_bug3_no_temp_litter` | **BUG 3 regression.** After a 20-file run, `count_temp_files() == 0` |
| `test_bug4_second_run_ignores_backups` | run twice with backups on; second `scan()` never lists `__orig__*`; no `__orig____orig__*` exists |
| `test_lossy_reporting_counts` | a file with 4× `"`, 2× `—`, 1× `…` reports exactly three `LossyChange` entries with counts 4, 2, 1 in that order |
| `test_loss_guard_flags_cjk` | a Chinese subtitle targeted at ISO-8859-7 → `NEEDS_REVIEW`, `loss_ratio > 0.9` |
| `test_loss_guard_passes_greek_with_punctuation` | Greek + smart quotes → `CONVERT`, `loss_ratio < 0.05` |
| `test_unreadable_empty` / `_too_big` / `_binary` / `_no_timecode` / `_whitespace` | each yields `UNREADABLE` with the specified `error` string |
| `test_cancel_preset_writes_nothing` | a pre-set `Event` → `convert` returns `[]`, folder byte-identical |
| `test_cancel_midrun_partial` | cancel after 3 of 10 → exactly 3 files converted, 7 untouched |
| `test_progress_fires_once_per_file` | `done` values are `1..N` with no gaps; `total` constant; called on the calling thread (assert `threading.get_ident()`) |
| `test_progress_on_worker_thread` | calling `scan()` from a `Thread` runs the callback on that thread, not the main one |
| `test_missing_folder_raises` | `FileNotFoundError`; `NotADirectoryError` for a file path; `TypeError` for `target="utf-8"` |
| `test_convert_rejects_non_writable_action` | passing an `ALREADY_TARGET` report raises `ValueError` and writes nothing |
| `test_convert_rejects_mixed_targets` | `ValueError`, nothing written |
| `test_source_changed_detected` | scan, rewrite the file, convert → `code == "SOURCE_CHANGED"`, file untouched |
| `test_models_frozen_and_hashable` | `hash(FileReport(...))` works; mutating a field raises |

### `tests/test_gui_smoke.py`

Per the agreed trade, the GUI gets a smoke-import test and nothing more. **No GUI automation
framework. Do not propose one.**

```python
def test_gui_imports():
    import gui
    assert hasattr(gui, "main")
    assert hasattr(gui, "ConverterApp")


def test_gui_constructs():
    import pytest
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    import gui
    gui.ConverterApp(root)
    root.destroy()
```

---

## 11. Build order

Each step is independently verifiable. Do them in order.

**Step 1 — Rename and scaffold.**
```bash
cd "c:/Users/CodedK/Desktop/Git/Subtitles"
git mv "CONVERT TO GREEK THEN UTF8.py" cli.py
mkdir greek_srt tests
touch conftest.py greek_srt/__init__.py
printf 'pytest>=7\n' > requirements-dev.txt
```
*Verify:* `git status` shows the rename (not add+delete); `python cli.py` still runs the old flow.

**Step 2 — `greek_srt/models.py`.** Paste §4.1 verbatim, plus the `LossyChange` NFKD note from §6.3.
*Verify:* `python -c "from greek_srt.models import FileReport, Target, Action; print(Target.ISO_8859_7.label)"` prints `Greek ISO-8859-7`. `hash()` on a constructed `FileReport` succeeds.

**Step 3 — `greek_srt/detect.py`.** Paste §5.4 verbatim.
*Verify:* write `tests/test_detect.py` and run it. All 15 tests green. This is BUG 2 fixed.

**Step 4 — `greek_srt/clean.py`.** Paste §6.3, applying the `_to_lossy`/NFKD correction.
*Verify:* write `tests/test_clean.py` and run it. All 18 tests green — in particular the 1,953,125-combination forge search and the totality fuzz. This is BUG 1's precondition satisfied.

**Step 5 — `greek_srt/fileio.py`.** Paste §7.2 verbatim.
*Verify:* write `tests/test_fileio.py` and run it. All 12 tests green. This is BUG 3 and BUG 4 fixed.

**Step 6 — `greek_srt/convert.py`.** Paste §7.8 verbatim.
*Verify:* write `tests/test_convert.py` and run it. All 22 tests green. `scan()` on a real folder returns sane reports and leaves it byte-identical.

**Step 7 — `greek_srt/__init__.py`.** Paste §4.6.
*Verify:* `python -c "import greek_srt; print(greek_srt.__version__, len(greek_srt.__all__))"`.

**Step 8 — `cli.py` rebuild.** Replace the whole file per §9. The old `detect_encoding`,
`clean_for_iso_8859_7` and `convert_srt_encoding` are deleted; only the interactive shell remains,
now calling `scan()` and `convert()`.
*Verify:* run it against a scratch folder with a mixed-encoding fixture set. Dry-run prints the full
table including detected encodings and lossy counts (the old dry-run printed only filenames).
`grep -n "input(" greek_srt/*.py` returns nothing.

**Step 9 — `gui.py`.** Paste §8.11.
*Verify:* `python gui.py`. Scan a fixture folder. Confirm by eye: ballot glyphs render, Greek renders
in the preview in a monospace font, checkbox clicks toggle without changing the selection, clicking
another column selects and refreshes the preview, header click selects/deselects all `CONVERT` rows,
`NEEDS_REVIEW` rows are red and unticked, `ALREADY_TARGET`/`UNREADABLE` checkboxes do nothing.

**Step 10 — GUI shutdown behaviour.** Start a scan on a large folder and close the window mid-run.
*Verify:* no Tcl `invalid command name` on stderr, and the process exits within ~5 s with the worker
dead. Repeat with a convert run and confirm the "A job is still running" dialog appears.

**Step 11 — `tests/test_gui_smoke.py`.**
*Verify:* `python -m pytest -q` — the whole suite green.

**Step 12 — README.** Update: new usage (`python gui.py` / `python cli.py`), the corrected detection
description (delete the "first that decodes wins" paragraph — it describes the bug), the no-BOM and
preserve-line-endings policies, the backup never-overwrite policy, the `NEEDS_REVIEW` guard, and the
two accepted `os.replace` limitations from §7.6 (mtime/attribute loss; cannot replace a file open in
another process).
*Verify:* the README no longer describes any removed behaviour.

**Step 13 — Full-suite gate.** `python -m pytest -q` from the repo root. Zero failures, zero errors.

---

## 12. Acceptance criteria

A reviewer ticks these off. Every one is objectively checkable.

**Structure**

- [ ] `CONVERT TO GREEK THEN UTF8.py` no longer exists; `cli.py` does; `git log --follow cli.py` shows the original commit.
- [ ] `greek_srt/` contains exactly `__init__.py`, `models.py`, `detect.py`, `clean.py`, `fileio.py`, `convert.py`.
- [ ] `grep -rn "import tkinter\|import argparse\|print(" greek_srt/` returns nothing.
- [ ] `grep -rn "input(" greek_srt/` returns nothing.
- [ ] `grep -rn "open(.*['\"]w['\"]" greek_srt/ cli.py gui.py` returns nothing.
- [ ] `grep -rn "splitlines()" greek_srt/ cli.py gui.py` returns nothing.
- [ ] `grep -rn "except Exception\|except BaseException\|except ValueError" greek_srt/` returns nothing except the single documented `except BaseException` — and that clause does not exist in the final `atomic_write_bytes`, which uses `try/finally`, so this grep returns **nothing at all**.
- [ ] `grep -rn "latin1\|latin-1" greek_srt/detect.py` appears only in a comment explaining its exclusion.
- [ ] `grep -rn "importlib\|__import__" greek_srt/ cli.py gui.py` returns nothing.
- [ ] `grep -rn "sys.stdout.write\|sys.stderr.write" gui.py` returns nothing.
- [ ] `pip list` inside a clean venv shows only `pytest` and its own dependencies.

**Bugs fixed**

- [ ] BUG 1: `clean.render()` is called on every ISO-8859-7 conversion; there is **no** UTF-8 fallback path anywhere; `test_bug1_iso_output_is_really_iso` passes.
- [ ] BUG 2: `detect_encoding` takes `bytes` and never reads a prefix; a genuine CP1253 file with smart punctuation detects as `cp1253`; French/German in CP1252 detect as `cp1252`.
- [ ] BUG 3: every write goes through `atomic_write_bytes`; a monkeypatched `os.replace` failure leaves the original intact and no temp file.
- [ ] BUG 4: `iter_srt_files` excludes `__orig__*` case-insensitively; a second run does not produce `__orig____orig__*`.

**Behaviour**

- [ ] `scan()` on a 10-file tree leaves every file byte-identical and every `mtime_ns` unchanged.
- [ ] A CRLF, an LF, a CR-only and a mixed-ending file each keep their exact CR/LF/CRLF counts after conversion in both directions.
- [ ] No output file starts with `EF BB BF`, in either direction.
- [ ] Converting twice is a byte-level no-op; the second scan reports `ALREADY_TARGET` and the second convert reports `status == "unchanged"` with `bytes_written == 0`.
- [ ] A Chinese-language `.srt` targeted at ISO-8859-7 is `NEEDS_REVIEW` and unticked by default.
- [ ] An existing `__orig__x.srt` is never overwritten; `backup == "kept-existing"` and conversion still proceeds.
- [ ] A file held open by another process yields `code == "LOCKED"` and survives byte-identical (Windows).
- [ ] A file edited between scan and convert yields `code == "SOURCE_CHANGED"` and is not written.
- [ ] `convert()` with a pre-set cancel `Event` returns `[]` and writes nothing.

**GUI**

- [ ] `enable_dpi_awareness()` is called before `tk.Tk()`; there is no `root.tk.call("tk", "scaling", ...)` anywhere.
- [ ] Only `tk.Text` is a classic `tk.*` widget; everything else is `ttk.*`; the theme is `vista`.
- [ ] `Treeview` `rowheight` is computed from `TkDefaultFont.metrics("linespace")`, not hardcoded.
- [ ] The checkbox column width comes from a runtime `font.measure()` call.
- [ ] Clicking the `#1` cell toggles and returns `"break"`; `tree.selection()` is unchanged.
- [ ] Clicking a `#2`/`#3`/`#4` cell selects the row and refreshes the preview.
- [ ] Every preview update does the `normal → delete/insert → disabled` dance.
- [ ] The monospace font is chosen via `pick_mono_font()`; Cascadia is not referenced anywhere.
- [ ] `filedialog.askdirectory` Cancel is tested with `if not chosen:`, and the result goes through `os.path.normpath`.
- [ ] `on_close` performs `cancel.set()` → `after_cancel()` → `join(timeout=5)` → `destroy()` in that order.
- [ ] Closing during a run produces no Tcl `invalid command name` output and leaves no live worker.
- [ ] `root.report_callback_exception` is installed.

**Tests**

- [ ] `python -m pytest -q` from the repo root: zero failures, zero errors.
- [ ] Every test name listed in §10 exists.
- [ ] Windows-only tests are guarded with `@pytest.mark.skipif(os.name != "nt")`.

---

## 13. Explicitly out of scope

Do not build any of these. They are deliberately excluded and adding them is a defect, not a bonus.

1. **PyInstaller packaging.** A separate, later phase. Do not create a `.spec` file, do not add build
   scripts, do not add a `--onefile` target. Only honour the four coding constraints in §1.4.
2. **A per-file source-encoding override dropdown.** Deliberately cut to keep the build tight. If
   detection is wrong for a file, the user restores from the `__orig__` backup. Accepted for v1.
3. **A third target encoding (`cp1253`).** Only `utf-8` and `iso-8859-7` exist. `Ά` and `΅` have no
   byte that renders correctly under both Greek codecs; this is documented, not solved.
4. **Line-ending normalisation, in any form.** No "convert to CRLF" checkbox, no final-newline
   injection, no CR-only repair. §6.5 is final.
5. **A BOM-writing option.** No BOM is ever written. Not configurable.
6. **HTML-ish tag stripping** (`<i>`, `<b>`, `<font color=...>`). These are pure ASCII, encode fine,
   and are a *content* decision the user did not ask for.
7. **`ReplaceFileW` via `ctypes`,** or any other Windows-only atomic-write variant. Explicitly
   rejected in §7.6.
8. **`os.utime()` restoration after replace.** mtime resets to now. That matches the current
   behaviour and is not a regression.
9. **A startup sweep that deletes `.srtconv-*.tmp` files.** It would race with a second instance.
   Report the count; never delete.
10. **`argparse` / non-interactive flags for `cli.py`.** It stays purely interactive.
11. **GUI automation testing** (pytest-qt-style harnesses, `pyautogui`, image diffing). A smoke-import
    plus an optional constructor test is the agreed trade.
12. **Any third-party dependency at runtime,** including `chardet`, `charset_normalizer`, `colorama`,
    `rich`, `tqdm`, `send2trash`. `charset_normalizer` happens to be importable on the reference
    machine; it is off the table by decision.
13. **A logging framework, a config file for the CLI, i18n, a plugin system, an undo stack, a
    file-watcher, drag-and-drop, or a window icon.** None were asked for.
14. **A preview that centres on the first altered character.** The preview is the first
    `PREVIEW_LINES` (40) line contents, verbatim. Simple and approved.
15. **Modifying `LICENSE`, `.gitignore`, or `desktop.ini`.**

---

## Appendix A — field validation, 2026-07-28

Before this brief was finalised, a prototype implementing §5 (detection), §6.4 (BOM), §6.5
(line endings) and §7.2 (atomic write) was run against a real library: **26 `.srt` files under
`F:\movies\2026.07`**, converted to UTF-8 with backups. This is independent of the 391-file corpus
cited elsewhere in this document, and it corroborates the two decisions most likely to be
second-guessed.

**Composition.** 21 × CP1253, 3 × UTF-8 with BOM, 1 × UTF-8 without, 1 whose CP1253 bytes were
already byte-identical to its ISO-8859-7 rendering.

**The C1 penalty of §5.4 was necessary but not sufficient here.** Only *one* of the 21 CP1253 files
(`No Country For Old Men`) contained bytes in `0x80–0x9F`, so only that one was decided by the C1
term. The other 20 turned entirely on byte `0xA2` — `Ά` under CP1253, `’` under ISO-8859-7 — which
carries no C1 signal at all. Both codecs decoded all 20 files without error, and the scores tied.
They resolved correctly only because §5.3 fixes CP1253 first in `SINGLE_BYTE_CANDIDATES`.
**That ordering is load-bearing, not cosmetic.** Context confirms CP1253 is right:

| CP1253 (correct) | ISO-8859-7 (wrong) |
|---|---|
| `Τα παιδιά των Άγγλων` | `Τα παιδιά των ’γγλων` |
| `Άκου. Θα απογειωθείς` | `’κου. Θα απογειωθείς` |
| `Κύριε Άρτσερ, ελάτε εδώ.` | `Κύριε ’ρτσερ, ελάτε εδώ.` |
| `- Άντε πνίξου!` | `- ’ντε πνίξου!` |
| `Άλλωστε, είχε πλάκα.` | `’λλωστε, είχε πλάκα.` |

`0xA2` occurred **213 times** across the 21 files. Had the tie broken the other way, 213 capital `Ά`
would have become apostrophes. Note also that these files use ASCII `0x27` for real apostrophes
(`σ' εμένα`), which is corroborating evidence that `0xA2` is never a quote here.

**Add this as `tests/test_detect.py::test_alpha_tonos_tie_breaks_to_cp1253`:** a file containing only
`b"\xc4\xe5\xed \xe8\xdd\xeb\xf9. \xa2\xed\xf4\xe5!"` must detect as `cp1253`, and the decoded text
must contain `Άντε`, not `’ντε`.

**Verification results.** All 26 files round-tripped byte-identically in text content against their
`__orig__` backups; CRLF counts unchanged on every file; zero surviving BOMs; zero `.tmp` orphans;
1 file correctly reported `ALREADY_TARGET` and was never written, so it has no backup. The
`ALREADY_TARGET`-by-byte-equality rule of §5.5 and the never-overwrite backup rule of §7.4 both
behaved as specified.
