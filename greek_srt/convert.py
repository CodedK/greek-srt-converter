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


def scan_one(path: Path, target: Target, time_offset_ms: int = 0) -> FileReport:
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
        rendered = _clean.render(text, target, time_offset_ms=time_offset_ms)
    except _clean.StructureChanged as exc:
        return _unreadable(path, target, st, str(exc))
    except UnicodeEncodeError as exc:
        return _unreadable(path, target, st, f"{type(exc).__name__}: {exc}")

    if rendered.data == raw and time_offset_ms == 0:
        action = Action.ALREADY_TARGET
    elif target is Target.ISO_8859_7 and rendered.loss_ratio > LOSS_GUARD:
        action = Action.NEEDS_REVIEW
    else:
        action = Action.CONVERT

    # If time offset is set, update preview lines to reflect shifted timing
    if time_offset_ms != 0:
        shifted_text = _clean.shift_document_timing(text, time_offset_ms)
        lines = _clean.split_lines(shifted_text)

    return FileReport(
        path=path, stamp=st, encoding=det.encoding, confidence=det.confidence,
        action=action, target=target, lossy=rendered.lossy,
        loss_ratio=rendered.loss_ratio,
        preview=tuple(lines[:PREVIEW_LINES]), error=None,
        time_offset_ms=time_offset_ms,
    )


def scan(folder, *, recursive: bool = False, target: Target,
         time_offset_ms: int = 0,
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
        report = scan_one(path, target, time_offset_ms=time_offset_ms)
        reports.append(report)
        if on_progress is not None:
            on_progress(Progress("scan", i, total, path, report=report))
    return reports


def _failed(report: FileReport, code: str, detail: str) -> ConvertResult:
    return ConvertResult(path=report.path, ok=False, status="failed", code=code,
                         source_encoding=report.encoding,
                         target_encoding=report.target.codec, backup="not-needed",
                         backup_path=None, lossy=report.lossy, bytes_written=0,
                         error=detail, time_offset_ms=report.time_offset_ms)


def _convert_one(report: FileReport, *, backup: bool) -> ConvertResult:
    src = report.path
    # TOCTOU guard: the user may have edited the file between Scan and Convert.
    if _io.stamp(src) != report.stamp:
        raise _io.FileOpError("SOURCE_CHANGED", src, "modified since scan")

    raw = _io.read_bytes(src)
    text = raw.decode(_detect.read_codec(report.encoding)).replace("\ufeff", "")
    rendered = _clean.render(text, report.target, time_offset_ms=report.time_offset_ms)     # encode happens BEFORE any write

    if rendered.data == raw and report.time_offset_ms == 0:
        return ConvertResult(path=src, ok=True, status="unchanged", code=None,
                             source_encoding=report.encoding,
                             target_encoding=report.target.codec,
                             backup="not-needed", backup_path=None,
                             lossy=rendered.lossy, bytes_written=0, error=None,
                             time_offset_ms=report.time_offset_ms)

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
                         error=None, time_offset_ms=report.time_offset_ms)


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
