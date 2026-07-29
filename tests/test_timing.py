"""tests/test_timing.py -- unit tests for SubRip timecode parsing and shifting."""

from __future__ import annotations

from greek_srt.timing import (
    format_timecode,
    parse_timecode,
    shift_document_timing,
    shift_timecode_line,
)


def test_parse_and_format_timecode():
    assert parse_timecode("00:01:12,400") == 72400
    assert parse_timecode("01:00:00,000") == 3600000
    assert parse_timecode("00:00:00.500") == 500

    assert format_timecode(72400) == "00:01:12,400"
    assert format_timecode(3600000) == "01:00:00,000"
    assert format_timecode(500) == "00:00:00,500"


def test_format_timecode_clamping():
    assert format_timecode(-5000) == "00:00:00,000"


def test_shift_timecode_line_positive():
    line = "00:00:01,000 --> 00:00:03,500"
    shifted = shift_timecode_line(line, 2000)  # +2.0 seconds
    assert shifted == "00:00:03,000 --> 00:00:05,500"


def test_shift_timecode_line_negative():
    line = "00:00:03,000 --> 00:00:05,500"
    shifted = shift_timecode_line(line, -2000)  # -2.0 seconds
    assert shifted == "00:00:01,000 --> 00:00:03,500"


def test_shift_timecode_line_negative_clamping():
    line = "00:00:01,000 --> 00:00:03,000"
    shifted = shift_timecode_line(line, -5000)  # -5.0 seconds
    assert shifted == "00:00:00,000 --> 00:00:00,000"


def test_shift_timecode_line_preserves_tags():
    line = "00:00:01,000 --> 00:00:03,500 X1:100 X2:600 Y1:20 Y2:50"
    shifted = shift_timecode_line(line, 1000)
    assert shifted == "00:00:02,000 --> 00:00:04,500 X1:100 X2:600 Y1:20 Y2:50"


def test_shift_document_timing():
    doc = (
        "1\r\n"
        "00:00:01,000 --> 00:00:02,000\r\n"
        "― Καλημέρα, φίλε.\r\n"
        "\r\n"
        "2\r\n"
        "00:00:03,600 --> 00:00:05,900\r\n"
        "― Τι κάνεις;\r\n"
    )
    shifted_doc = shift_document_timing(doc, 2000)
    expected = (
        "1\r\n"
        "00:00:03,000 --> 00:00:04,000\r\n"
        "― Καλημέρα, φίλε.\r\n"
        "\r\n"
        "2\r\n"
        "00:00:05,600 --> 00:00:07,900\r\n"
        "― Τι κάνεις;\r\n"
    )
    assert shifted_doc == expected
