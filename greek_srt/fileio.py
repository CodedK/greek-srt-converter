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
    plain: list[Path] = []
    for p in found:
        s = os.path.abspath(str(p))
        if s.startswith("\\\\?\\UNC\\"):
            plain.append(Path("\\\\" + s[8:]))
        elif s.startswith(_EXT_PREFIX):
            plain.append(Path(s[len(_EXT_PREFIX):]))
        else:
            plain.append(Path(s))
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
