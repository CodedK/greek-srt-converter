"""
This module converts all .srt files in the folder from various encodings to UTF-8 or ISO-8859-7.
"""

import shutil
from pathlib import Path
import datetime


def detect_encoding(file_path):
    """
    Detect the encoding of a file by trying common encodings.

    :param file_path: Path to the file
    :return: Detected encoding name or None
    """
    # Common encodings to try, in order of preference
    encodings_to_try = [
        "utf-8",
        "iso-8859-7",  # Greek
        "windows-1252",  # Western European
        "cp1253",  # Greek (Windows)
        "latin1",  # ISO-8859-1
        "utf-16",
        "ascii",
    ]

    for encoding in encodings_to_try:
        try:
            with open(file_path, "r", encoding=encoding) as file:
                # Try to read the first 1KB to test encoding
                file.read(1024)
                return encoding
        except (UnicodeDecodeError, UnicodeError):
            continue

    return None


def clean_for_iso_8859_7(text):
    """
    Clean text to be compatible with ISO-8859-7 encoding by removing or replacing illegal characters.

    :param text: Input text string
    :return: Cleaned text string compatible with ISO-8859-7
    """
    # Remove BOM (Byte Order Mark) if present
    if text.startswith("\ufeff"):
        text = text[1:]
        print("   CLEANING: Removed BOM (Byte Order Mark)")

    # Character replacements for common problematic characters
    replacements = {
        # Smart quotes
        "\u2018": "'",  # Left single quotation mark
        "\u2019": "'",  # Right single quotation mark
        "\u201c": '"',  # Left double quotation mark
        "\u201d": '"',  # Right double quotation mark
        # Dashes
        "\u2013": "-",  # En dash
        "\u2014": "-",  # Em dash
        "\u2015": "-",  # Horizontal bar
        # Ellipsis
        "\u2026": "...",  # Horizontal ellipsis
        # Other common characters
        "\u00a0": " ",  # Non-breaking space
        "\u2022": "*",  # Bullet
        "\u00ae": "(R)",  # Registered trademark
        "\u00a9": "(C)",  # Copyright
        "\u2122": "(TM)",  # Trademark
        # Currency symbols (replace with text)
        "\u20ac": "EUR",  # Euro sign
        "\u00a3": "GBP",  # Pound sign
        "\u00a5": "YEN",  # Yen sign
        # Mathematical symbols
        "\u00d7": "x",  # Multiplication sign
        "\u00f7": "/",  # Division sign
        "\u00b1": "+/-",  # Plus-minus sign
        # Arrows
        "\u2190": "<-",  # Leftwards arrow
        "\u2192": "->",  # Rightwards arrow
        "\u2191": "^",  # Upwards arrow
        "\u2193": "v",  # Downwards arrow
    }

    # Apply replacements
    replaced_count = 0
    for old_char, new_char in replacements.items():
        if old_char in text:
            text = text.replace(old_char, new_char)
            replaced_count += 1

    if replaced_count > 0:
        print(f"   CLEANING: Replaced {replaced_count} types of special characters")

    # Remove any remaining characters that can't be encoded in ISO-8859-7
    cleaned_text = ""
    removed_chars = set()

    for char in text:
        try:
            char.encode("iso-8859-7")
            cleaned_text += char
        except UnicodeEncodeError:
            # Character can't be encoded, skip it
            removed_chars.add(char)

    if removed_chars:
        print(
            f"   CLEANING: Removed {len(removed_chars)} types of illegal characters: {', '.join(repr(c) for c in sorted(removed_chars)[:10])}"
        )
        if len(removed_chars) > 10:
            print(
                f"   CLEANING: ... and {len(removed_chars) - 10} more character types"
            )

    return cleaned_text


def convert_srt_encoding(
    folder_path,
    create_backup=True,
    dry_run=False,
    recursive=False,
    force_iso_8859_7=False,
):
    """
    Converts all .srt files in the folder from various encodings to UTF-8 or ISO-8859-7.

    :param folder_path: Path to the folder containing .srt files.
    :param create_backup: Whether to create backup files before conversion.
    :param dry_run: If True, only shows what would be converted without making changes.
    :param recursive: If True, processes subfolders recursively.
    :param force_iso_8859_7: If True, converts to UTF-8 first then forces to ISO-8859-7.
    """
    # Validate folder path
    folder = Path(folder_path)
    if not folder.exists():
        print(f"ERROR: Folder '{folder_path}' does not exist.")
        return False

    if not folder.is_dir():
        print(f"ERROR: '{folder_path}' is not a directory.")
        return False

    # Find all .srt files (recursive or not)
    if recursive:
        srt_files = list(folder.rglob("*.srt"))
        print(f"SCANNING: Recursively searching for .srt files in '{folder_path}'...")
    else:
        srt_files = list(folder.glob("*.srt"))
        print(f"SCANNING: Searching for .srt files in '{folder_path}'...")

    if not srt_files:
        print(
            f"INFO: No .srt files found in '{folder_path}'{' (including subfolders)' if recursive else ''}."
        )
        return True

    print(f"FOUND: {len(srt_files)} .srt file(s) to process.")

    # Show conversion mode
    if force_iso_8859_7:
        print(
            "CONVERSION MODE: Auto-detect -> UTF-8 -> ISO-8859-7 (forced with character cleaning)"
        )
    else:
        print("CONVERSION MODE: Auto-detect -> UTF-8")

    # Show file list for confirmation
    print("\nFILES TO PROCESS:")
    for i, srt_file in enumerate(srt_files, 1):
        relative_path = srt_file.relative_to(folder)
        print(f"   {i:2d}. {relative_path}")

    if dry_run:
        print("\nDRY RUN MODE - No files will be modified")
        return True

    converted_count = 0
    failed_count = 0
    skipped_count = 0
    already_target_count = 0

    # Technical log header
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nTECHNICAL LOG - Started at {timestamp}")
    print("=" * 80)

    # Process each .srt file
    for i, srt_file in enumerate(srt_files, 1):
        relative_path = srt_file.relative_to(folder)
        print(f"\n[{i}/{len(srt_files)}] Processing: {relative_path}")

        try:
            # Check file size
            file_size = srt_file.stat().st_size
            print(f"   File size: {file_size} bytes")

            # Detect encoding
            print("   DETECTING: File encoding...")
            detected_encoding = detect_encoding(srt_file)

            if not detected_encoding:
                print("   ERROR: Could not detect file encoding")
                failed_count += 1
                continue

            print(f"   DETECTED: {detected_encoding.upper()} encoding")

            # Check if conversion is needed
            target_encoding = "iso-8859-7" if force_iso_8859_7 else "utf-8"

            if detected_encoding.lower() == target_encoding:
                print(
                    f"   INFO: File is already {target_encoding.upper()} encoded, skipping"
                )
                already_target_count += 1
                continue

            # Create backup if requested
            if create_backup:
                backup_name = f"__orig__{srt_file.name}"
                backup_path = srt_file.parent / backup_name

                # Check if backup already exists
                if backup_path.exists():
                    print(f"   WARNING: Backup already exists: {backup_name}")
                    overwrite = (
                        input("   Overwrite existing backup? (y/N): ").strip().lower()
                    )
                    if overwrite not in ["y", "yes"]:
                        print(f"   SKIPPED: {relative_path} (backup exists)")
                        skipped_count += 1
                        continue

                shutil.copy2(srt_file, backup_path)
                print(f"   BACKUP: Created {backup_name}")

            # Read the file with detected encoding
            print(f"   READING: With {detected_encoding.upper()} encoding...")
            with open(srt_file, "r", encoding=detected_encoding) as file:
                content = file.read()

            # Validate content
            if not content.strip():
                print("   WARNING: File is empty, skipping conversion")
                skipped_count += 1
                continue

            lines_count = len(content.splitlines())
            chars_count = len(content)
            print(f"   CONTENT: {lines_count} lines, {chars_count} characters")

            if force_iso_8859_7:
                # Two-step conversion: First to UTF-8, then to ISO-8859-7 with cleaning
                print("   STEP 1: Converting to UTF-8...")
                # Content is already in UTF-8 format in memory

                print("   STEP 2: Converting to ISO-8859-7...")
                try:
                    # Test if content can be encoded to ISO-8859-7
                    content.encode("iso-8859-7")

                    # Write with ISO-8859-7 encoding
                    with open(srt_file, "w", encoding="iso-8859-7") as file:
                        file.write(content)

                    print(
                        f"   SUCCESS: Converted {relative_path} ({detected_encoding.upper()} -> UTF-8 -> ISO-8859-7)"
                    )

                except UnicodeEncodeError as e:
                    print(
                        "   WARNING: Cannot encode to ISO-8859-7, saving as UTF-8 instead"
                    )
                    print(f"   REASON: {e}")

                    # Fallback to UTF-8
                    with open(srt_file, "w", encoding="utf-8") as file:
                        file.write(content)

                    print(
                        f"   SUCCESS: Converted {relative_path} ({detected_encoding.upper()} -> UTF-8)"
                    )
            else:
                # Standard conversion to UTF-8
                print("   WRITING: With UTF-8 encoding...")
                with open(srt_file, "w", encoding="utf-8") as file:
                    file.write(content)

                print(
                    f"   SUCCESS: Converted {relative_path} ({detected_encoding.upper()} -> UTF-8)"
                )

            converted_count += 1

        except UnicodeDecodeError as e:
            print(f"   DECODE ERROR: {relative_path} - {e}")
            print("      Could not decode file with any supported encoding")
            failed_count += 1
        except UnicodeEncodeError as e:
            print(f"   ENCODE ERROR: {relative_path} - {e}")
            failed_count += 1
        except OSError as e:
            print(f"   FILE SYSTEM ERROR: {relative_path} - {e}")
            failed_count += 1
        except Exception as e:
            print(f"   UNEXPECTED ERROR: {relative_path} - {e}")
            failed_count += 1

    # Final summary
    end_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("\n" + "=" * 80)
    print(f"CONVERSION SUMMARY - Completed at {end_timestamp}")
    print(f"   Successfully converted: {converted_count}")
    target_name = "ISO-8859-7" if force_iso_8859_7 else "UTF-8"
    print(f"   Already {target_name}: {already_target_count}")
    print(f"   Failed conversions: {failed_count}")
    print(f"   Skipped files: {skipped_count}")
    print(f"   Total files found: {len(srt_files)}")

    if create_backup and converted_count > 0:
        print("   Backup files created with '__orig__' prefix")

    return failed_count == 0


def main():
    """Main function with user interaction and options."""
    print("SRT File Encoding Converter")
    print("=" * 60)
    print(
        "Supported encodings: UTF-8, ISO-8859-7 (Greek), Windows-1252, CP1253, Latin1, UTF-16, ASCII"
    )

    while True:
        # Conversion mode selection
        print("\nCONVERSION MODES:")
        print("1. Auto-detect -> UTF-8 (Standard)")
        print("2. Auto-detect -> UTF-8 -> ISO-8859-7 (Forced Greek)")

        while True:
            mode_choice = input("\nSelect conversion mode (1 or 2): ").strip()
            if mode_choice in ["1", "2"]:
                break
            print("Please enter 1 or 2")

        force_iso_8859_7 = mode_choice == "2"

        if force_iso_8859_7:
            print("\nSelected: Auto-detect -> UTF-8 -> ISO-8859-7 (Forced Greek)")
            print(
                "Note: Files will be converted to UTF-8 first, then forced to ISO-8859-7"
            )
            print(
                "Warning: Characters not supported by ISO-8859-7 will cause fallback to UTF-8"
            )
        else:
            print("\nSelected: Auto-detect -> UTF-8 (Standard)")

        folder_path = input(
            "\nEnter the folder path containing .srt files (or 'quit' to exit): "
        ).strip()

        if folder_path.lower() in ["quit", "exit", "q"]:
            print("Goodbye!")
            break

        if not folder_path:
            print("WARNING: Please enter a valid folder path.")
            continue

        # Remove quotes if present
        folder_path = folder_path.strip("\"'")

        # Ask for recursive processing
        recursive = input(
            "Process subfolders recursively? (y/N): "
        ).strip().lower() in ["y", "yes"]

        if recursive:
            confirm_recursive = (
                input(
                    "WARNING: This will process ALL .srt files in ALL subfolders. Continue? (y/N): "
                )
                .strip()
                .lower()
            )
            if confirm_recursive not in ["y", "yes"]:
                print("Recursive processing cancelled.")
                continue

        # Ask for other options
        print("\nOptions:")
        create_backup = input(
            "Create backup files with '__orig__' prefix? (Y/n): "
        ).strip().lower() not in ["n", "no"]
        dry_run = input("Dry run (preview only)? (y/N): ").strip().lower() in [
            "y",
            "yes",
        ]

        print(f"\nProcessing folder: {folder_path}")
        if recursive:
            print("Mode: Recursive (including subfolders)")
        if dry_run:
            print("Mode: Dry run (preview only)")
        if create_backup and not dry_run:
            print("Backups: Enabled with '__orig__' prefix")

        success = convert_srt_encoding(
            folder_path, create_backup, dry_run, recursive, force_iso_8859_7
        )

        if success:
            print("\nOperation completed successfully!")
        else:
            print("\nOperation completed with errors.")

        # Ask if user wants to continue
        if input("\nProcess another folder? (y/N): ").strip().lower() not in [
            "y",
            "yes",
        ]:
            break


if __name__ == "__main__":
    main()
