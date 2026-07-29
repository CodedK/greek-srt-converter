# greek-srt-converter

Batch re-encodes `.srt` subtitle files. Point it at a folder, and it auto-detects each file's encoding and rewrites it as **UTF-8** or **ISO-8859-7** (Greek) — the encoding older hardware media players and TVs expect for Greek subtitles.

---

## Quick Start

Requires Python 3.10+ (Standard Library only, zero runtime dependencies).

### Graphical Interface (GUI)
```bash
python gui.py
```

### Command Line Interface (CLI)
```bash
python cli.py
```

---

## Features & Highlights

- **Dual Interfaces**: Modern, DPI-aware Tkinter GUI ([`gui.py`](file:///c:/Users/CodedK/Desktop/Git/Subtitles/gui.py)) and interactive CLI ([`cli.py`](file:///c:/Users/CodedK/Desktop/Git/Subtitles/cli.py)).
- **Scan/Preview Phase**: Complete preview of actions (`CONVERT`, `ALREADY_TARGET`, `NEEDS_REVIEW`, `UNREADABLE`) and lossy character replacements before any bytes are written to disk.
- **Accurate Encoding Detection**: Heuristic scoring engine over complete file buffers distinguishing CP1253, ISO-8859-7, UTF-8 (BOM/BOM-less), UTF-16, UTF-32, CP1252, and ASCII.
- **Safe ISO-8859-7 Folding**: Map non-encodable characters (smart quotes, dialogue dashes, currency symbols, ligatures) safely without altering SubRip timecodes or cue structure.
- **`NEEDS_REVIEW` Safety Guard**: Automatically flags non-Greek subtitles (e.g. CJK or foreign language subtitles) when targeting ISO-8859-7 if character loss exceeds 20%.
- **Atomic File Operations**: Writes to temporary `.srtconv-*.tmp` files with `fsync()` before replacement (`os.replace`). Original files are never truncated or lost.
- **Line Ending Preservation**: Preserves original CRLF, LF, or CR line endings without forced universal newline translations.
- **No BOM Policy**: Never outputs Byte Order Marks (`EF BB BF`), ensuring compatibility with strict subtitle parsers.
- **Safe Backups**: Preserves pristine original files as `__orig__<name>.srt` without overwriting existing backups on subsequent runs.

---

## Documentation & Developer Resources

- **[RUNBOOK.md](RUNBOOK.md)**: Operational guide for running, testing, troubleshooting, and packaging the application.
- **[CLAUDE.md](CLAUDE.md)**: Architecture rules, developer invariants, and code guidelines.
- **[Implementation Brief](docs/superpowers/specs/2026-07-28-greek-srt-gui-design.md)**: Complete design brief and technical specifications.

---

## Developer Setup & Testing

Install development dependencies:
```bash
pip install -r requirements-dev.txt
```

Run the complete test suite:
```bash
python -m pytest -q
```

---

## Building Standalone Executable (.exe)

To bundle `gui.py` into a single standalone Windows executable using PyInstaller:

```bash
pip install pyinstaller
python build_exe.py
```

The resulting executable will be placed in `dist/GreekSrtConverter/`.

---

## License

[MIT](LICENSE)
