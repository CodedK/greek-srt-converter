# Developer & Agent Guidelines — greek-srt-converter

Repository guide and developer instructions for working on `greek-srt-converter`.

---

## 1. Quick Reference & Commands

- **Run GUI**: `python gui.py`
- **Run CLI**: `python cli.py`
- **Register Context Menu**: `python setup_context_menu.py install`
- **Run Unit Tests**: `python -m pytest -q`
- **Run Specific Test**: `python -m pytest tests/test_timing.py`
- **Build Executable**: `python build_exe.py`

---

## 2. Project Architecture & Hierarchy

```
greek_srt/
    ├── __init__.py      # Re-exports public API and metadata
    ├── models.py        # Immutable value types (Target, Action, FileReport, LossyChange, etc.)
    ├── detect.py        # Whole-buffer encoding detection & heuristic scoring
    ├── clean.py         # ISO-8859-7 character folding table & document renderer
    ├── timing.py        # SubRip timecode parsing, shifting (+/- ms), and formatting
    ├── fileio.py        # Exclusive filesystem access (atomic writes, backups, long paths)
    └── convert.py       # Orchestration layer (scan() preview & convert() execution)
cli.py                   # Interactive CLI shell (rebuilt on core API)
gui.py                   # Modern, DPI-aware Tkinter GUI with Dark Mode & Time Shift
setup_context_menu.py    # Windows Explorer right-click shell context menu setup
build_exe.py             # PyInstaller packaging script
conftest.py              # Root conftest for pytest path resolution
requirements-dev.txt     # Dev dependencies (pytest>=7)
.github/workflows/ci.yml # GitHub Actions CI/CD workflow
tests/                   # Pytest suite (79 unit tests)
```

### Dependency Direction (Strictly One-Way)
```text
models  <-  detect
models  <-  clean
clean   <-  timing
models, clean, timing  <-  fileio
models, detect, clean, timing, fileio  <-  convert
greek_srt  <-  cli.py, gui.py
```

---

## 3. Strict Development Invariants

1. **Zero Runtime Dependencies**: Use Python standard library only. `pytest` is dev-only. Do not add runtime requirements to `setup.py` or `requirements.txt`.
2. **Core Separation**: Modules under `greek_srt/` must **never** import `tkinter`, `argparse`, call `print()`, or invoke `input()`. The core is purely programmatic.
3. **Scan is Read-Only (`INV-1`)**: `scan()` inspects files read-only and must never modify files, create temp files, or alter `mtime`.
4. **Atomic Writes (`INV-2`)**: Writing via `open(path, "w")` is banned project-wide. All filesystem writes MUST go through `fileio.atomic_write_bytes()`, which writes to `.srtconv-*.tmp`, `fsync`s, handles read-only flags, and calls `os.replace()`.
5. **Time Shift Handling**: Subtitle timecode shifting is handled by `timing.py`. Negative offsets are clamped at `00:00:00,000`. Formatting tags (`X1:... Y1:...`) must be preserved.
6. **No BOM Output Policy**: `Target.codec` for UTF-8 is `"utf-8"`, never `"utf-8-sig"`. Input BOMs are stripped before rendering. No BOM is ever written.
7. **Line Ending Preservation**: Binary I/O end-to-end (`"rb"` / `"wb"`). Universal newline translation is disabled on write. CRLF, LF, and CR line endings are preserved byte-for-byte.
8. **Backup Policy**: `write_backup()` copies originals to `__orig__<name>.srt` before replacement. Existing backups are **never** overwritten (first backup wins). `__orig__*` files are excluded from scan globbing.
9. **Exception Handling**: Core code must **never** catch bare `Exception` or `ValueError` (since `UnicodeDecodeError` / `UnicodeEncodeError` subclass `ValueError`). Catch only explicit, narrow exceptions (`OSError`, `UnicodeDecodeError`, `UnicodeEncodeError`, `FileOpError`, `StructureChanged`).
10. **GUI Thread Safety**: `gui.py` widgets must ONLY be modified on the main Tk thread. Worker threads communicate exclusively via `queue.Queue` drained by `_pump()`.
11. **GUI DPI Awareness**: `enable_dpi_awareness()` MUST be called before `tk.Tk()` is instantiated. `rowheight` and column measurements must be calculated dynamically at runtime.
