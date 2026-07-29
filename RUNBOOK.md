# Operational Runbook — greek-srt-converter

This runbook documents how to run, test, troubleshoot, build, and maintain the `greek-srt-converter` application.

---

## 1. System Requirements & Setup

- **Runtime**: Python **3.10+** (Python 3.11.9 recommended).
- **Operating System**: Windows 11 (primary target for GUI DPI scaling and atomic renames), Linux/macOS compatible for core and tests.
- **Runtime Dependencies**: **Zero 3rd-party dependencies**. Standard library only (`tkinter`, `dataclasses`, `codecs`, `pathlib`, `ctypes`, `threading`, `queue`, `json`, `re`).
- **Development Dependencies**: `pytest>=7` (listed in `requirements-dev.txt`).

---

## 2. Launching the Interfaces

### 2.1 Graphical Interface (GUI)
```bash
python gui.py
```
- Launching starts the system DPI-aware Tkinter interface.
- Preferences (last folder, target mode, recurse option, backup toggle) are automatically saved to and loaded from `%APPDATA%\GreekSrtConverter\settings.json`.

### 2.2 Command Line Interface (CLI)
```bash
python cli.py
```
- Launches the interactive console shell.
- Prompts step-by-step for target mode, folder path, recursion, backup creation, and dry-run execution.

---

## 3. Testing & Code Quality

### 3.1 Running the Unit Test Suite
```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run the complete test suite
python -m pytest -q
```

### 3.2 Key Test Suites (`tests/`)
- `tests/test_detect.py`: Verifies whole-buffer encoding detection, BOM handling, NUL parity, and CP1253 vs ISO-8859-7 heuristic scoring.
- `tests/test_clean.py`: Verifies R1–R6 folding rules, 1.9M 3-character forge-prevention combinations, NFKD mark stripping, and document structure validation.
- `tests/test_fileio.py`: Verifies atomic file renames, backup protection, read-only attribute handling, extended-length paths (`\\?\`), and file lock retries.
- `tests/test_convert.py`: Verifies read-only `scan()` invariants (`INV-1`), round-trip conversions across 8 encoding formats, cancellation, and `NEEDS_REVIEW` loss guards.
- `tests/test_gui_smoke.py`: Verifies GUI importability and headless window initialization.

---

## 4. Building Standalone Executables (.exe)

To package `gui.py` into a single standalone Windows executable using PyInstaller:

```bash
# Install PyInstaller
pip install pyinstaller

# Run the build script
python build_exe.py
```

The output executable directory will be generated at:
```text
dist/GreekSrtConverter/
```

### PyInstaller Packaging Guidelines
- Building uses `--windowed --onedir` mode.
- Standard library modules must not be excluded with `--exclude-module` (e.g. excluding `urllib` breaks `pathlib`).
- The application relies on no external asset files (`--add-data` not required).

---

## 5. Troubleshooting & Operational Procedures

### 5.1 Handling Locked Files (`LOCKED` / `PermissionError`)
- **Symptom**: Conversion status displays `FAILED [LOCKED] WinError 5: Access is denied` or `close the player and retry`.
- **Cause**: A media player (e.g., VLC, MPC-HC, Plex Media Server) or text editor holds an open lock on the `.srt` file.
- **Resolution**: Close the application holding the subtitle file and click **Convert** or re-run the CLI conversion batch.

### 5.2 Handling `NEEDS_REVIEW` Flagged Files
- **Symptom**: Status displays `NEEDS REVIEW - XX% of non-ASCII lost` and the row checkbox is unticked by default.
- **Cause**: The subtitle contains non-Greek text (e.g., CJK characters or foreign scripts) that ISO-8859-7 cannot represent, resulting in >20% character loss.
- **Resolution**: Verify if the subtitle is intended to be Greek. If it is a foreign subtitle, leave it unticked. If conversion is explicitly desired, tick the row manually.

### 5.3 Leftover Temp Files (`.srtconv-*.tmp`)
- **Symptom**: Status bar indicates `N leftover temp file(s) from an interrupted run`.
- **Cause**: A previous run was abruptly terminated (e.g., power loss, process kill) during atomic writing.
- **Resolution**: Leftover temp files do not interfere with normal `.srt` operations. You can manually delete `.srtconv-*.tmp` files from the target directory if desired.

### 5.4 Resetting GUI Settings
- **Location**: `%APPDATA%\GreekSrtConverter\settings.json`
- **Resolution**: Delete `settings.json` to restore default initial directory and mode selections.
