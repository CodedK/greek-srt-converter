"""build_exe.py -- PyInstaller packaging script for Greek SRT Converter.

Builds a standalone, zero-dependency Windows executable (.exe) from gui.py.
Run: python build_exe.py
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    print("Building Greek SRT Converter standalone executable...")
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller is not installed in the active environment.")
        print("Install it with: pip install pyinstaller")
        return 1

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name=GreekSrtConverter",
        "gui.py",
    ]

    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    if res.returncode == 0:
        dist_path = os.path.abspath(os.path.join("dist", "GreekSrtConverter"))
        print(f"\nBuild successful! Executable directory created at:\n  {dist_path}")
    else:
        print(f"\nBuild failed with exit code {res.returncode}")
    return res.returncode


if __name__ == "__main__":
    sys.exit(main())
