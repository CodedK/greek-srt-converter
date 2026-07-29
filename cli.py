"""cli.py -- interactive command-line front-end for greek_srt. Run: python cli.py"""

from __future__ import annotations

import datetime
import os
import sys
from pathlib import Path

from greek_srt import (
    Action,
    ConvertResult,
    FileReport,
    Progress,
    Target,
    convert,
    scan,
)
from greek_srt.fileio import count_temp_files


def _prompt_target() -> Target:
    print("\nSelect target encoding:")
    print("  1) UTF-8 (no BOM)")
    print("  2) Greek ISO-8859-7")
    while True:
        choice = input("Enter choice (1/2) [default: 1]: ").strip()
        if choice in ("", "1"):
            return Target.UTF_8
        if choice == "2":
            print("Note: characters ISO-8859-7 cannot represent are folded or dropped; the scan table shows exactly which.")
            return Target.ISO_8859_7
        print("Invalid choice. Enter 1 or 2.")


def _prompt_folder() -> str | None:
    while True:
        inp = input("\nEnter folder path (or 'q' to quit): ").strip().strip("\"'")
        if inp.lower() in ("q", "quit", "exit"):
            return None
        if not inp:
            continue
        if os.path.isdir(inp):
            return os.path.normpath(inp)
        print(f"Directory not found: {inp}")


def _prompt_yes_no(prompt: str, default: bool) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        ans = input(prompt + suffix).strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes"):
            return True
        if ans in ("n", "no"):
            return False
        print("Please answer 'y' or 'n'.")


def _print_table(reports: list[FileReport]) -> None:
    print("\n   #  FILE                              DETECTED           STATUS")
    print("-" * 75)
    for i, r in enumerate(reports, 1):
        filename = r.path.name
        if len(filename) > 32:
            filename = filename[:29] + "..."
        enc_str = f"{r.encoding} ({r.confidence.value})" if r.encoding else "-"
        if r.action is Action.UNREADABLE:
            status_str = f"unreadable - {r.error}"
        elif r.action is Action.ALREADY_TARGET:
            status_str = "already target"
        elif r.action is Action.NEEDS_REVIEW:
            status_str = f"NEEDS REVIEW - {r.loss_ratio:.0%} of non-ASCII lost"
        elif r.dropped_count:
            status_str = f"{r.dropped_count} chars stripped (!)"
        elif r.encoding == "utf-8-sig" and r.target is Target.UTF_8:
            status_str = "will convert (BOM removed)"
        else:
            status_str = "will convert"

        print(f"{i:>4}  {filename:<32}  {enc_str:<18}  {status_str}")

        if r.lossy:
            for change in r.lossy[:10]:
                codepoint = f"U+{ord(change.char):04X}"
                if change.dropped:
                    desc = f"{codepoint} DROPPED x{change.count}"
                else:
                    desc = f"{codepoint} {change.replacement!r} x{change.count}"
                print(f"      -> {desc}")


def _print_summary(results: list[ConvertResult]) -> None:
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ok_count = sum(1 for r in results if r.ok and r.status == "converted")
    unchanged_count = sum(1 for r in results if r.ok and r.status == "unchanged")
    failed_count = sum(1 for r in results if not r.ok)
    backups_created = sum(1 for r in results if r.backup == "created")
    backups_kept = sum(1 for r in results if r.backup == "kept-existing")

    print(f"\nCONVERSION SUMMARY - Completed at {now_str}")
    print(f"   Successfully converted: {ok_count:>4}")
    print(f"   Unchanged:               {unchanged_count:>4}")
    print(f"   Failed:                  {failed_count:>4}")
    print(f"   Backups created:        {backups_created:>4}  (kept existing: {backups_kept})")


def run_once() -> bool:
    print("\n" + "=" * 60)
    print("SRT File Encoding Converter")
    print("Detects: UTF-8 (BOM/BOM-less), UTF-16, UTF-32, CP1253, ISO-8859-7, CP1252, ASCII")
    print("=" * 60)

    target = _prompt_target()
    folder = _prompt_folder()
    if folder is None:
        return False

    recursive = _prompt_yes_no("Search subfolders recursively?", default=False)
    backup = _prompt_yes_no("Create backups (__orig__*.srt)?", default=True)
    dry_run = _prompt_yes_no("Dry run (scan only, do not write)?", default=False)

    print(f"\nScanning {folder}...")

    def on_scan_progress(p: Progress) -> None:
        print(f"\r[{p.done}/{p.total}] Scanning {p.path.name}", end="", flush=True)

    reports = scan(folder, recursive=recursive, target=target, on_progress=on_scan_progress)
    print()  # Newline after progress

    if not reports:
        print("No .srt files found.")
        return True

    _print_table(reports)

    leftovers = count_temp_files(Path(folder), recursive=recursive)
    if leftovers > 0:
        print(f"\nNOTE: {leftovers} leftover temp file(s) from an interrupted run.")

    if dry_run:
        print("\nDRY RUN - no files were modified.")
        return True

    writable_reports = [r for r in reports if r.action is Action.CONVERT]
    review_reports = [r for r in reports if r.action is Action.NEEDS_REVIEW]

    if not writable_reports and not review_reports:
        print("\nNo files need conversion.")
        return True

    selected_reports = list(writable_reports)
    if review_reports:
        print(f"\nWARNING: {len(review_reports)} file(s) are flagged NEEDS REVIEW (high character loss).")
        if _prompt_yes_no("Include flagged NEEDS REVIEW files in conversion?", default=False):
            selected_reports.extend(review_reports)

    if not selected_reports:
        print("\nNo files selected for conversion.")
        return True

    if not _prompt_yes_no(f"\nProceed to convert {len(selected_reports)} file(s)?", default=True):
        print("Aborted.")
        return True

    print("\nConverting files...")

    def on_convert_progress(p: Progress) -> None:
        print(f"\r[{p.done}/{p.total}] Converting {p.path.name}", end="", flush=True)

    results = convert(selected_reports, backup=backup, on_progress=on_convert_progress)
    print()

    _print_summary(results)
    return True


def main() -> int:
    try:
        while run_once():
            if not _prompt_yes_no("\nProcess another folder?", default=False):
                break
        print("\nGoodbye!")
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
