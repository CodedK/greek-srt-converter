# greek-srt-converter

Batch re-encodes `.srt` subtitle files. Point it at a folder, and it auto-detects each
file's encoding and rewrites it as **UTF-8** or **ISO-8859-7** (Greek) — the encoding
older hardware media players and TVs expect for Greek subtitles.

## Why

Greek subtitles downloaded from the web arrive in a mix of encodings: UTF-8, CP1253,
ISO-8859-7, sometimes UTF-16. Standalone media players that only understand ISO-8859-7
render anything else as mojibake. This tool normalises a whole folder in one pass.

## Usage

Requires Python 3.8+. No third-party dependencies.

```bash
python "CONVERT TO GREEK THEN UTF8.py"
```

The script is interactive and prompts for:

| Prompt | Meaning |
| --- | --- |
| Conversion mode | `1` = auto-detect → UTF-8, `2` = auto-detect → UTF-8 → ISO-8859-7 |
| Folder path | Folder to scan for `.srt` files |
| Recursive | Also process subfolders |
| Backup | Copy each original to `__orig__<name>.srt` before writing |
| Dry run | List what would be converted, change nothing |

Conversion is **in place**. Keep backups enabled unless you have your own copies.

### Encoding detection

Candidate encodings are tried in order — UTF-8, ISO-8859-7, Windows-1252, CP1253,
Latin-1, UTF-16, ASCII — and the first that decodes the file's opening bytes wins.
This is a heuristic, not a guarantee: several single-byte encodings will decode almost
any byte sequence without error, so a file can be "successfully" decoded as the wrong
one. Use dry-run mode and spot-check the output on an unfamiliar batch.

## Status

Working CLI, with known defects documented below. A folder-picker GUI and a corrected
`greek_srt` core package are specified in full in
[the implementation brief](docs/superpowers/specs/2026-07-28-greek-srt-gui-design.md).

Known defects in the current script, all fixed by that brief:

- `clean_for_iso_8859_7()` is never called, so the ISO-8859-7 mode silently falls back to UTF-8
- encoding detection validates only a buffered prefix, and `iso-8859-7` acts as a catch-all that
  prevents CP1253 from ever being returned
- writes truncate the target before writing, so an interruption destroys the subtitle
- `__orig__*.srt` backups match the `*.srt` glob, so a second run converts its own backups

## License

[MIT](LICENSE)
