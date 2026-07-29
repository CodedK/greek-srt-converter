"""tests/test_gui_smoke.py -- smoke import test for gui.py."""

from __future__ import annotations

import pytest


def test_gui_imports():
    import gui
    assert hasattr(gui, "main")
    assert hasattr(gui, "ConverterApp")


def test_gui_constructs():
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display")
    import gui
    app = gui.ConverterApp(root)
    assert app is not None
    root.destroy()
