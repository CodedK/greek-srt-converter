"""tests/test_convert.py -- unit tests for scan and convert orchestration."""

from __future__ import annotations

import hashlib
import os
import threading
import pytest
from pathlib import Path

from greek_srt.convert import MAX_FILE_BYTES, convert, scan
from greek_srt.fileio import count_temp_files
from greek_srt.models import Action, FileReport, Target


def _hash_tree(folder: Path) -> dict[str, tuple[str, int]]:
    snapshot = {}
    for p in folder.rglob("*"):
        if p.is_file():
            snapshot[str(p)] = (
                hashlib.sha256(p.read_bytes()).hexdigest(),
                p.stat().st_mtime_ns,
            )
    return snapshot


def test_scan_leaves_folder_byte_identical(tmp_path: Path):
    for i in range(5):
        (tmp_path / f"file{i}.srt").write_text(
            f"1\n00:00:01,000 --> 00:00:02,000\nSample {i}\n", encoding="utf-8"
        )

    before = _hash_tree(tmp_path)
    scan(tmp_path, target=Target.UTF_8)
    after = _hash_tree(tmp_path)
    assert before == after


def test_roundtrip_all_encodings_both_targets(tmp_path: Path):
    text = "1\r\n00:00:01,000 --> 00:00:02,000\r\n― Καλημέρα, φίλε.\r\n"
    encodings = [
        ("cp1253", text.encode("cp1253")),
        ("iso-8859-7", text.encode("iso-8859-7")),
        ("utf-8", text.encode("utf-8")),
        ("utf-8-sig", b"\xef\xbb\xbf" + text.encode("utf-8")),
        ("utf-16-le", b"\xff\xfe" + text.encode("utf-16-le")),
        ("utf-16-be", b"\xfe\xff" + text.encode("utf-16-be")),
        ("ascii", "1\r\n00:00:01,000 --> 00:00:02,000\r\nHello\r\n".encode("ascii")),
    ]

    for target in [Target.UTF_8, Target.ISO_8859_7]:
        sub_folder = tmp_path / target.value
        sub_folder.mkdir()
        for name, data in encodings:
            (sub_folder / f"{name}.srt").write_bytes(data)

        reports = scan(sub_folder, target=target)
        writable = [r for r in reports if r.writable]
        results = convert(writable)
        for r in results:
            assert r.ok, f"Failed for {r.path}: {r.error}"


def test_already_target_is_label_independent(tmp_path: Path):
    # Pure Greek text encodable in ISO-8859-7
    data = "1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("iso-8859-7")
    p = tmp_path / "iso.srt"
    p.write_bytes(data)

    reports = scan(tmp_path, target=Target.ISO_8859_7)
    assert len(reports) == 1
    assert reports[0].action is Action.ALREADY_TARGET


def test_idempotence(tmp_path: Path):
    p = tmp_path / "test.srt"
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\n— Καλημέρα…\n".encode("cp1253"))

    reports1 = scan(tmp_path, target=Target.UTF_8)
    convert([r for r in reports1 if r.writable])

    reports2 = scan(tmp_path, target=Target.UTF_8)
    assert reports2[0].action is Action.ALREADY_TARGET

    results2 = convert([r for r in reports2 if r.writable])
    assert len(results2) == 0  # no writable reports


def test_bug1_iso_output_is_really_iso(tmp_path: Path):
    text = "1\n00:00:01,000 --> 00:00:02,000\n— Καλημέρα…\n"
    p = tmp_path / "test.srt"
    p.write_bytes(text.encode("utf-8"))

    reports = scan(tmp_path, target=Target.ISO_8859_7)
    results = convert(reports)
    assert results[0].ok

    out_bytes = p.read_bytes()
    # Must decode as ISO-8859-7
    decoded = out_bytes.decode("iso-8859-7")
    assert "― Καλημέρα..." in decoded
    # Output must NOT be valid UTF-8 for the Greek characters
    with pytest.raises(UnicodeDecodeError):
        out_bytes.decode("utf-8")


def test_bug3_no_temp_litter(tmp_path: Path):
    for i in range(10):
        (tmp_path / f"test{i}.srt").write_bytes(
            "1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253")
        )
    reports = scan(tmp_path, target=Target.UTF_8)
    convert(reports)
    assert count_temp_files(tmp_path, recursive=False) == 0


def test_bug4_second_run_ignores_backups(tmp_path: Path):
    p = tmp_path / "test.srt"
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253"))

    reports1 = scan(tmp_path, target=Target.UTF_8)
    convert(reports1, backup=True)

    reports2 = scan(tmp_path, target=Target.UTF_8)
    assert len(reports2) == 1
    assert reports2[0].path.name == "test.srt"
    assert not (tmp_path / "__orig____orig__test.srt").exists()


def test_lossy_reporting_counts(tmp_path: Path):
    # 4 double quotes, 2 em dashes, 1 ellipsis
    text = "1\n00:00:01,000 --> 00:00:02,000\n“one” “two” — — …\n"
    p = tmp_path / "lossy.srt"
    p.write_bytes(text.encode("utf-8"))

    reports = scan(tmp_path, target=Target.ISO_8859_7)
    report = reports[0]
    assert len(report.lossy) >= 3
    # Ordered by count descending
    counts = [c.count for c in report.lossy]
    assert counts == sorted(counts, reverse=True)


def test_loss_guard_flags_cjk(tmp_path: Path):
    cjk_text = "1\n00:00:01,000 --> 00:00:02,000\n你好世界 こんにちは\n"
    p = tmp_path / "chinese.srt"
    p.write_bytes(cjk_text.encode("utf-8"))

    reports = scan(tmp_path, target=Target.ISO_8859_7)
    assert reports[0].action is Action.NEEDS_REVIEW
    assert reports[0].loss_ratio > 0.8


def test_loss_guard_passes_greek_with_punctuation(tmp_path: Path):
    text = "1\n00:00:01,000 --> 00:00:02,000\n— Καλημέρα… «Τι κάνεις;»\n"
    p = tmp_path / "greek.srt"
    p.write_bytes(text.encode("utf-8"))

    reports = scan(tmp_path, target=Target.ISO_8859_7)
    assert reports[0].action is Action.CONVERT
    assert reports[0].loss_ratio < 0.05


def test_unreadable_empty(tmp_path: Path):
    p = tmp_path / "empty.srt"
    p.write_bytes(b"")
    reports = scan(tmp_path, target=Target.UTF_8)
    assert reports[0].action is Action.UNREADABLE
    assert "empty" in reports[0].error


def test_unreadable_too_big(tmp_path: Path):
    p = tmp_path / "big.srt"
    p.write_bytes(b"A" * (MAX_FILE_BYTES + 100))
    reports = scan(tmp_path, target=Target.UTF_8)
    assert reports[0].action is Action.UNREADABLE
    assert "8 MiB" in reports[0].error


def test_unreadable_binary(tmp_path: Path):
    p = tmp_path / "binary.srt"
    p.write_bytes(b"\x00\x00\x00\x00\x00\x00\x00\x00")
    reports = scan(tmp_path, target=Target.UTF_8)
    assert reports[0].action is Action.UNREADABLE


def test_unreadable_no_timecode(tmp_path: Path):
    p = tmp_path / "readme.srt"
    p.write_bytes(b"Just plain text without timecodes")
    reports = scan(tmp_path, target=Target.UTF_8)
    assert reports[0].action is Action.UNREADABLE
    assert "no SubRip timecode" in reports[0].error


def test_unreadable_whitespace(tmp_path: Path):
    p = tmp_path / "space.srt"
    p.write_bytes(b"   \n\t\r\n  ")
    reports = scan(tmp_path, target=Target.UTF_8)
    assert reports[0].action is Action.UNREADABLE


def test_cancel_preset_writes_nothing(tmp_path: Path):
    p = tmp_path / "test.srt"
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253"))

    evt = threading.Event()
    evt.set()
    reports = scan(tmp_path, target=Target.UTF_8, cancel=evt)
    assert len(reports) == 0


def test_cancel_midrun_partial(tmp_path: Path):
    for i in range(5):
        (tmp_path / f"test{i}.srt").write_bytes(
            "1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253")
        )

    evt = threading.Event()
    count = 0

    def progress(p):
        nonlocal count
        count += 1
        if count == 2:
            evt.set()

    reports = scan(tmp_path, target=Target.UTF_8, on_progress=progress, cancel=evt)
    assert len(reports) == 2


def test_progress_fires_once_per_file(tmp_path: Path):
    for i in range(3):
        (tmp_path / f"test{i}.srt").write_bytes(
            "1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253")
        )

    calls = []
    tid = threading.get_ident()

    def progress(p):
        assert threading.get_ident() == tid
        calls.append(p.done)

    scan(tmp_path, target=Target.UTF_8, on_progress=progress)
    assert calls == [1, 2, 3]


def test_progress_on_worker_thread(tmp_path: Path):
    (tmp_path / "test.srt").write_bytes(
        "1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253")
    )

    worker_tid = None

    def progress(p):
        nonlocal worker_tid
        worker_tid = threading.get_ident()

    def runner():
        scan(tmp_path, target=Target.UTF_8, on_progress=progress)

    t = threading.Thread(target=runner)
    t.start()
    t.join()

    assert worker_tid == t.ident
    assert worker_tid != threading.get_ident()


def test_missing_folder_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        scan(tmp_path / "nonexistent", target=Target.UTF_8)

    file_path = tmp_path / "file.txt"
    file_path.write_bytes(b"hello")
    with pytest.raises(NotADirectoryError):
        scan(file_path, target=Target.UTF_8)

    with pytest.raises(TypeError):
        scan(tmp_path, target="utf-8")


def test_convert_rejects_non_writable_action(tmp_path: Path):
    p = tmp_path / "unreadable.srt"
    p.write_bytes(b"empty")
    reports = scan(tmp_path, target=Target.UTF_8)
    assert reports[0].action is Action.UNREADABLE

    with pytest.raises(ValueError) as exc_info:
        convert(reports)
    assert "only CONVERT and NEEDS_REVIEW" in str(exc_info.value)


def test_convert_rejects_mixed_targets(tmp_path: Path):
    p1 = tmp_path / "t1.srt"
    p2 = tmp_path / "t2.srt"
    p1.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253"))
    p2.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253"))

    r1 = scan(tmp_path, target=Target.UTF_8)[0]
    r2 = scan(tmp_path, target=Target.ISO_8859_7)[1]

    with pytest.raises(ValueError) as exc_info:
        convert([r1, r2])
    assert "reports mix targets" in str(exc_info.value)


def test_source_changed_detected(tmp_path: Path):
    p = tmp_path / "test.srt"
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253"))

    reports = scan(tmp_path, target=Target.UTF_8)
    # Modify file after scan
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nEdited!\n".encode("utf-8"))

    results = convert(reports)
    assert not results[0].ok
    assert results[0].code == "SOURCE_CHANGED"


def test_models_frozen_and_hashable(tmp_path: Path):
    p = tmp_path / "test.srt"
    p.write_bytes("1\n00:00:01,000 --> 00:00:02,000\nΚαλημέρα\n".encode("cp1253"))
    reports = scan(tmp_path, target=Target.UTF_8)
    report = reports[0]

    assert hash(report) is not None
    with pytest.raises(AttributeError):
        report.action = Action.ALREADY_TARGET
