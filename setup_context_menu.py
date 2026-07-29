"""setup_context_menu.py -- Windows Explorer Context Menu integration for Greek SRT Converter.

Registers/unregisters a user-level right-click menu ("Convert Greek SRT Subtitles here") for folders in Windows Explorer.
No Administrator rights required (uses HKCU).

Run:
  python setup_context_menu.py install
  python setup_context_menu.py uninstall
"""

from __future__ import annotations

import os
import sys
import winreg

REG_KEY_PATH = r"Software\Classes\Directory\shell\GreekSrtConverter"
MENU_LABEL = "Convert Greek SRT Subtitles here"


def is_installed() -> bool:
    """Check if the Explorer context menu registry key exists."""
    if sys.platform != "win32":
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH)
        winreg.CloseKey(key)
        return True
    except OSError:
        return False


def install() -> bool:
    if sys.platform != "win32":
        print("Context menu integration is supported on Windows only.")
        return False

    script_path = os.path.abspath("gui.py")
    if not os.path.exists(script_path):
        print(f"Error: gui.py not found at {script_path}")
        return False

    pythonw_exe = os.path.join(sys.prefix, "pythonw.exe")
    if not os.path.exists(pythonw_exe):
        pythonw_exe = sys.executable

    command_str = f'"{pythonw_exe}" "{script_path}" "%1"'

    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH)
        winreg.SetValue(key, "", winreg.REG_SZ, MENU_LABEL)
        winreg.SetValueEx(key, "Icon", 0, winreg.REG_SZ, pythonw_exe)
        winreg.CloseKey(key)

        cmd_key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{REG_KEY_PATH}\command")
        winreg.SetValue(cmd_key, "", winreg.REG_SZ, command_str)
        winreg.CloseKey(cmd_key)

        print(f"Successfully registered Explorer Context Menu:\n  '{MENU_LABEL}'\n  Command: {command_str}")
        return True
    except OSError as exc:
        print(f"Failed to register context menu: {exc}")
        return False


def uninstall() -> bool:
    if sys.platform != "win32":
        print("Context menu integration is supported on Windows only.")
        return False

    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{REG_KEY_PATH}\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH)
        print("Successfully removed Explorer Context Menu registration.")
        return True
    except FileNotFoundError:
        print("Context menu entry was not registered.")
        return True
    except OSError as exc:
        print(f"Failed to unregister context menu: {exc}")
        return False


def main() -> int:
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else "install"
    if cmd == "install":
        return 0 if install() else 1
    elif cmd in ("uninstall", "remove"):
        return 0 if uninstall() else 1
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python setup_context_menu.py [install|uninstall]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
