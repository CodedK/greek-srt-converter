"""tests/test_fileio.py -- unit tests for fileio.py filesystem operations."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
import pytest
from pathlib import Path

from greek_srt.fileio import (
    FileOpError,
    atomic_write_bytes,
    count_temp_files,
    is_excluded,
    iter_srt_files,
    long_path,
    write_backup,
)


def test_backup_never_overwritten(tmp_path: Path):
    src = tmp_path / "Ep01.srt"
    src.write_bytes(b"original content")
    backup = tmp_path / "__orig__Ep01.srt"
    backup.write_bytes(b"pristine content")

    status, b_path = write_backup(src)
    assert status == "kept-existing"
    assert b_path == backup
    assert backup.read_bytes() == b"pristine content"


def test_backup_created_preserves_mtime(tmp_path: Path):
    src = tmp_path / "Ep01.srt"
    src.write_bytes(b"content")
    st_before = src.stat()

    status, b_path = write_backup(src)
    assert status == "created"
    assert b_path is not None
    assert b_path.exists()
    st_backup = b_path.stat()
    assert abs(st_backup.st_mtime - st_before.st_mtime) < 0.1


def test_backup_readonly_bit_cleared(tmp_path: Path):
    src = tmp_path / "Ep01.srt"
    src.write_bytes(b"content")
    os.chmod(src, stat.S_IREAD)

    status, b_path = write_backup(src)
    assert status == "created"
    assert b_path is not None
    mode = os.stat(b_path).st_mode
    assert mode & stat.S_IWRITE  # Read-only cleared on backup

    # Reset src mode so tmp_path cleanup works cleanly
    os.chmod(src, stat.S_IWRITE)


def test_orig_prefix_excluded(tmp_path: Path):
    (tmp_path / "Ep01.srt").write_bytes(b"srt")
    (tmp_path / "__orig__Ep01.srt").write_bytes(b"orig")
    files = iter_srt_files(tmp_path, recursive=False)
    assert len(files) == 1
    assert files[0].name == "Ep01.srt"


def test_orig_prefix_excluded_case_insensitive(tmp_path: Path):
    (tmp_path / "Ep01.srt").write_bytes(b"srt")
    (tmp_path / "__ORIG__Ep01.srt").write_bytes(b"orig")
    files = iter_srt_files(tmp_path, recursive=False)
    assert len(files) == 1
    assert files[0].name == "Ep01.srt"


def test_temp_files_excluded(tmp_path: Path):
    (tmp_path / "Ep01.srt").write_bytes(b"srt")
    (tmp_path / ".srtconv-abc.tmp").write_bytes(b"tmp")
    files = iter_srt_files(tmp_path, recursive=False)
    assert len(files) == 1
    assert count_temp_files(tmp_path, recursive=False) == 1


def test_suffix_match_is_case_insensitive(tmp_path: Path):
    (tmp_path / "Ep01.SRT").write_bytes(b"srt")
    files = iter_srt_files(tmp_path, recursive=False)
    assert len(files) == 1
    assert files[0].name == "Ep01.SRT"


def test_atomicity_on_replace_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = tmp_path / "Ep01.srt"
    target.write_bytes(b"initial data")

    def mock_replace(src, dst):
        raise PermissionError(13, "Access is denied", None, 5)

    monkeypatch.setattr(os, "replace", mock_replace)

    with pytest.raises(FileOpError) as exc_info:
        atomic_write_bytes(target, b"new data")

    assert exc_info.value.code == "LOCKED"
    assert target.read_bytes() == b"initial data"
    assert count_temp_files(tmp_path, recursive=False) == 0


def test_no_temp_left_after_encode_failure(tmp_path: Path):
    target = tmp_path / "Ep01.srt"
    target.write_bytes(b"initial data")

    with pytest.raises(FileOpError):
        # Passing parent path instead of file path to trigger error
        atomic_write_bytes(tmp_path, b"data")

    assert count_temp_files(tmp_path, recursive=False) == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows read-only attribute test")
def test_readonly_target_converted_and_restored(tmp_path: Path):
    target = tmp_path / "Ep01.srt"
    target.write_bytes(b"initial data")
    os.chmod(target, stat.S_IREAD)

    atomic_write_bytes(target, b"new content")
    assert target.read_bytes() == b"new content"
    mode = os.stat(target).st_mode
    assert not (mode & stat.S_IWRITE)  # Restored to read-only

    # Clean up mode
    os.chmod(target, stat.S_IWRITE)


@pytest.mark.skipif(os.name != "nt", reason="Windows file locking test")
def test_locked_file_reports_LOCKED(tmp_path: Path):
    target = tmp_path / "Ep01.srt"
    target.write_bytes(b"initial data")

    # Hold the file open in Python subprocess
    cmd = [
        sys.executable,
        "-c",
        f"import time; f=open(r'{target}', 'rb+'); time.sleep(2)",
    ]
    proc = subprocess.Popen(cmd)
    try:
        time.sleep(0.3)  # Give process time to lock
        with pytest.raises(FileOpError) as exc_info:
            atomic_write_bytes(target, b"new content")
        assert exc_info.value.code == "LOCKED"
        assert target.read_bytes() == b"initial data"
    finally:
        proc.kill()
        proc.wait()


def test_long_path_idempotent(tmp_path: Path):
    p = str(tmp_path / "test.txt")
    lp1 = long_path(p)
    lp2 = long_path(lp1)
    assert lp1 == lp2
    if os.name == "nt":
        assert lp1.startswith("\\\\?\\")

    unc = "\\\\server\\share\\folder\\file.txt"
    lp_unc = long_path(unc)
    if os.name == "nt":
        assert lp_unc.startswith("\\\\?\\UNC\\")
