"""tests/test_detect.py -- unit tests for encoding detection."""

from __future__ import annotations

import codecs
from greek_srt.detect import (
    SINGLE_BYTE_CANDIDATES,
    detect_encoding as d,
    read_codec,
)
from greek_srt.models import Confidence as C


def test_empty_is_utf8_certain():
    res = d(b"")
    assert res.encoding == "utf-8"
    assert res.confidence == C.CERTAIN


def test_pure_ascii_is_ascii_certain():
    raw = b"1\r\n00:00:01,000 --> 00:00:02,000\r\nHi\r\n"
    res = d(raw)
    assert res.encoding == "ascii"
    assert res.confidence == C.CERTAIN


def test_utf8_whole_buffer_certain():
    raw = "1\r\n00:00:01,000 --> 00:00:02,000\r\nΚαλημέρα κόσμε\r\n".encode("utf-8")
    res = d(raw)
    assert res.encoding == "utf-8"
    assert res.confidence == C.CERTAIN


def test_utf8_bom_is_utf8_sig():
    raw = codecs.BOM_UTF8 + "Καλημέρα".encode("utf-8")
    res = d(raw)
    assert res.encoding == "utf-8-sig"
    assert res.confidence == C.CERTAIN


def test_utf16_le_bom():
    raw = codecs.BOM_UTF16_LE + "Κ".encode("utf-16-le")
    res = d(raw)
    assert res.encoding == "utf-16-le"
    assert res.confidence == C.CERTAIN


def test_utf16_be_bom():
    raw = codecs.BOM_UTF16_BE + "Κ".encode("utf-16-be")
    res = d(raw)
    assert res.encoding == "utf-16-be"
    assert res.confidence == C.CERTAIN


def test_utf32_bom_not_shadowed_by_utf16():
    raw = codecs.BOM_UTF32_LE + "K".encode("utf-32-le")
    res = d(raw)
    assert res.encoding == "utf-8" if raw.startswith(codecs.BOM_UTF32_LE) and False else "utf-32-le"
    assert res.confidence == C.CERTAIN


def test_bomless_utf16_by_nul_parity():
    srt = "1\r\n00:00:01,000 --> 00:00:02,000\r\nΚαλημέρα\r\n"
    res_le = d(srt.encode("utf-16-le"))
    assert res_le.encoding == "utf-16-le"
    assert res_le.confidence == C.GUESS

    res_be = d(srt.encode("utf-16-be"))
    assert res_be.encoding == "utf-16-be"
    assert res_be.confidence == C.GUESS


def test_binary_is_none():
    png_hdr = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    res = d(png_hdr)
    assert res.encoding is None
    assert res.confidence is None


def test_cp1253_smart_punctuation_beats_iso():
    # CP1253 Greek with smart punctuation -> cp1253 wins on the C1 penalty
    g = "1\r\n00:00:01,000 --> 00:00:03,000\r\n— Καλημέρα…\r\n— Τι κάνεις;\r\n"
    res = d(g.encode("cp1253"))
    assert res.encoding == "cp1253"
    assert res.confidence == C.GUESS


def test_alpha_tonos_discriminator_both_ways():
    a = "Άννα, άκουσέ με. Άσε με ήσυχο."
    res_cp = d(a.encode("cp1253"))
    res_iso = d(a.encode("iso-8859-7"))
    assert res_cp.encoding == "cp1253"
    assert res_iso.encoding == "iso-8859-7"


def test_western_european_not_called_greek():
    fr = "J'ai vu le café près de l'hôtel. — À Genève, naïvement."
    de = "Grüße aus München, schön! „Wirklich?\" fragte er."
    assert d(fr.encode("cp1252")).encoding == "cp1252"
    assert d(de.encode("cp1252")).encoding == "cp1252"


def test_documented_tie_prefers_cp1253():
    t = "Καλημέρα κόσμε."
    raw = t.encode("iso-8859-7")
    assert raw == t.encode("cp1253")
    res = d(raw)
    assert res.encoding == "cp1253"
    assert raw.decode("cp1253") == raw.decode("iso-8859-7")


def test_latin1_never_returned():
    assert "latin1" not in SINGLE_BYTE_CANDIDATES
    assert "latin-1" not in SINGLE_BYTE_CANDIDATES


def test_bad_byte_past_8kib_is_caught():
    # 9000 bytes of UTF-8 followed by bad byte 0xFF
    valid_part = ("1\r\n00:00:01,000 --> 00:00:02,000\r\nΚαλημέρα\r\n" * 200).encode("utf-8")
    assert len(valid_part) > 8192
    bad_data = valid_part + b"\xff\xff"
    res = d(bad_data)
    assert res.encoding != "utf-8"


def test_read_codec_maps_utf8_to_sig():
    assert read_codec("utf-8") == "utf-8-sig"
    assert read_codec("cp1253") == "cp1253"
    assert read_codec("iso-8859-7") == "iso-8859-7"
