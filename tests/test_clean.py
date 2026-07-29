"""tests/test_clean.py -- unit tests for clean.py ISO-8859-7 character folding."""

from __future__ import annotations

import itertools
import pytest
from greek_srt.clean import (
    INDEX_RE,
    ISO_FOLD_MAP,
    TIMECODE_RE,
    StructureChanged,
    fold_document,
    fold_to_iso,
    render,
    split_lines_keep,
)
from greek_srt.models import Target


def test_table_R1_no_ascii_keys():
    for k in ISO_FOLD_MAP:
        assert ord(k) >= 128, f"Key {k!r} has ord < 128"


def test_table_R2_no_colon_comma_gt_in_values():
    for k, v in ISO_FOLD_MAP.items():
        assert ":" not in v, f"Value for {k!r} contains ':'"
        assert "," not in v, f"Value for {k!r} contains ','"
        assert ">" not in v, f"Value for {k!r} contains '>'"


def test_table_R3_values_encodable():
    for k, v in ISO_FOLD_MAP.items():
        v.encode("iso-8859-7")  # Should not raise


def test_table_no_identity_entries():
    for k, v in ISO_FOLD_MAP.items():
        assert k != v, f"Identity mapping for {k!r}"


def test_table_R4_no_needless_folding():
    for k in ISO_FOLD_MAP:
        if k in ("\u00a0", "\u00ad"):  # Deliberate exceptions
            continue
        try:
            k_iso = k.encode("iso-8859-7")
            k_cp = k.encode("cp1253")
            assert k_iso != k_cp, f"Key {k!r} (U+{ord(k):04X}) encodable natively with identical bytes"
        except UnicodeEncodeError:
            pass


def test_table_R5_keeps_alpha_tonos():
    assert "\u0386" not in ISO_FOLD_MAP  # GREEK CAPITAL LETTER ALPHA WITH TONOS
    assert "\u0385" not in ISO_FOLD_MAP  # GREEK DIALYTIKA TONOS
    assert "\u2018" in ISO_FOLD_MAP
    assert "\u2019" in ISO_FOLD_MAP
    assert "\u20ac" in ISO_FOLD_MAP
    assert "\u20af" in ISO_FOLD_MAP
    assert "\u037a" in ISO_FOLD_MAP


def test_table_keeps_native_chars():
    native_chars = ["\u2015", "\u00b7", "\u00ab", "\u00bb", "\u00a9", "\u00a3", "\u00b1", "\u00bd"]
    for ch in native_chars:
        assert ch not in ISO_FOLD_MAP, f"Native character {ch!r} should not be folded"


def test_forge_search_3char():
    alphabet = list(ISO_FOLD_MAP.keys()) + list("-<>. a")
    for combo in itertools.product(alphabet, repeat=3):
        inp = "".join(combo)
        folded, _, _ = fold_to_iso(inp)
        if "-->" in folded and "-->" not in inp:
            doc = f"1\n00:00:01,000 --> 00:00:02,000\n{inp}\n"
            with pytest.raises(StructureChanged):
                fold_document(doc)


def test_structural_inertness():
    cases = [
        "1",
        "0001",
        "999999",
        "00:01:12,400 --> 00:01:14,900",
        "00:00:01,000 --> 00:00:03,500 X1:100 X2:600 Y1:20 Y2:50",
        "01:02:03.456 --> 01:02:05.000",
    ]
    for c in cases:
        folded, r, d = fold_to_iso(c)
        assert folded == c
        assert not r
        assert not d
        if TIMECODE_RE.match(c):
            assert TIMECODE_RE.match(folded)
        if INDEX_RE.match(c):
            assert INDEX_RE.match(folded)


def test_totality_fuzz():
    # Test random codepoints in U+0020..U+11000
    for cp in range(0x0020, 0x1100, 7):
        if 0xD800 <= cp <= 0xDFFF:  # Skip surrogates
            continue
        ch = chr(cp)
        folded, _, _ = fold_to_iso(ch)
        folded.encode("iso-8859-7")  # Must never raise


def test_idempotence():
    text = "— Καλημέρα… «Τι κάνεις;» \u201ctest\u201d café"
    folded1, r1, d1 = fold_document(text)
    folded2, r2, d2 = fold_document(folded1)
    assert folded1 == folded2
    assert not r2
    assert not d2


def test_guard_fires_on_forged_arrow():
    doc = "1\n00:00:01,000 --> 00:00:02,000\n\u2010\u2010> nai\n"
    with pytest.raises(StructureChanged) as exc_info:
        fold_document(doc)
    assert "gained a '-->'" in str(exc_info.value)


def test_guard_allows_real_arrow_in_text():
    doc = "1\n00:00:01,000 --> 00:00:02,000\nWait --> what?\n"
    res, _, _ = fold_document(doc)
    assert "Wait --> what?" in res


def test_c0_c1_controls_dropped():
    text = "Hello\x00 World\x1f!\x85\x9f\t\n\r"
    folded, _, dropped = fold_to_iso(text)
    assert "\x00" not in folded
    assert "\x1f" not in folded
    assert "\x85" not in folded
    assert "\x9f" not in folded
    assert "\t" in folded
    assert "\n" in folded
    assert "\r" in folded


def test_split_lines_keep_roundtrip():
    cases = [
        "line1\r\nline2\r\n",
        "line1\nline2\n",
        "line1\rline2\r",
        "line1\r\nline2\nline3\r",
        "",
    ]
    for c in cases:
        pairs = split_lines_keep(c)
        rejoined = "".join(content + term for content, term in pairs)
        assert rejoined == c


def test_render_preserves_newlines():
    text = "1\r\n00:00:01,000 --> 00:00:02,000\r\nHi\r\n"
    rendered = render(text, Target.UTF_8)
    assert rendered.data == text.encode("utf-8")


def test_render_strips_all_bom():
    text = "\ufeff1\n00:00:01,000 --> 00:00:02,000\nHello \ufeffworld\n"
    text_clean = text.replace("\ufeff", "")
    rendered = render(text_clean, Target.ISO_8859_7)
    assert b"\xef\xbb\xbf" not in rendered.data


def test_analyze_agrees_with_fold():
    text = "Test \u201cquote\u201d and drop \u200b null"
    rendered = render(text, Target.ISO_8859_7)
    lossy_chars = {change.char for change in rendered.lossy}
    assert "\u201c" in lossy_chars
    assert "\u201d" in lossy_chars
    assert "\u200b" in lossy_chars
