# Developer & Agent Guidelines — greek-srt-converter

Repository guide and developer instructions for working on `greek-srt-converter`.

---

## 1. Quick Reference & Commands

- **Run GUI**: `python gui.py`
- **Run CLI**: `python cli.py`
- **Run Unit Tests**: `python -m pytest -q`
- **Run Specific Test**: `python -m pytest tests/test_detect.py`
- **Build Executable**: `python build_exe.py`

---

## 2. Project Architecture & Hierarchy

```
greek_srt/
    ├── __init__.py      # Re-exports public API and metadata
    ├── models.py        # Immutable value types (Target, Action, FileReport, LossyChange, etc.)
    ├── detect.py        # Whole-buffer encoding detection & heuristic scoring
    ├── clean.py         # ISO-8859-7 character folding table & document renderer
    ├── fileio.py        # Exclusive filesystem access (atomic writes, backups, long paths)
    └── convert.py       # Orchestration layer (scan() preview & convert() execution)
cli.py                   # Interactive CLI shell (rebuilt on core API)
gui.py                   # Modern, DPI-aware Tkinter GUI
conftest.py              # Root conftest for pytest path resolution
requirements-dev.txt     # Dev dependencies (pytest>=7)
tests/                   # Pytest suite
```

### Dependency Direction (Strictly One-Way)
```text
models  <-  detect
models  <-  clean
models, clean  <-  fileio
models, detect, clean, fileio  <-  convert
greek_srt  <-  cli.py, gui.py
```

---

## 3. Strict Development Invariants

1. **Zero Runtime Dependencies**: Use Python standard library only. `pytest` is dev-only. Do not add runtime requirements to `setup.py` or `requirements.txt`.
2. **Core Separation**: Modules under `greek_srt/` must **never** import `tkinter`, `argparse`, call `print()`, or invoke `input()`. The core is purely programmatic.
3. **Scan is Read-Only (`INV-1`)**: `scan()` inspects files read-only and must never modify files, create temp files, or alter `mtime`.
4. **Atomic Writes (`INV-2`)**: Writing via `open(path, "w")` is banned project-wide. All filesystem writes MUST go through `fileio.atomic_write_bytes()`, which writes to `.srtconv-*.tmp`, `fsync`s, handles read-only flags, and calls `os.replace()`.
5. **No BOM Output Policy**: `Target.codec` for UTF-8 is `"utf-8"`, never `"utf-8-sig"`. Input BOMs are stripped before rendering. No BOM is ever written.
6. **Line Ending Preservation**: Binary I/O end-to-end (`"rb"` / `"wb"`). Universal newline translation is disabled on write. CRLF, LF, and CR line endings are preserved byte-for-byte.
7. **Backup Policy**: `write_backup()` copies originals to `__orig__<name>.srt` before replacement. Existing backups are **never** overwritten (first backup wins). `__orig__*` files are excluded from scan globbing.
8. **Exception Handling**: Core code must **never** catch bare `Exception` or `ValueError` (since `UnicodeDecodeError` / `UnicodeEncodeError` subclass `ValueError`). Catch only explicit, narrow exceptions (`OSError`, `UnicodeDecodeError`, `UnicodeEncodeError`, `FileOpError`, `StructureChanged`).
9. **GUI Thread Safety**: `gui.py` widgets must ONLY be modified on the main Tk thread. Worker threads communicate exclusively via `queue.Queue` drained by `_pump()`.
10. **GUI DPI Awareness**: `enable_dpi_awareness()` MUST be called before `tk.Tk()` is instantiated. `rowheight` and column measurements must be calculated dynamically at runtime.
