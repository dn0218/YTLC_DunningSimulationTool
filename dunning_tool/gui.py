# -*- coding: utf-8 -*-
"""
gui.py - backwards-compatible entry point.

The GUI implementation moved to dunning_tool.ui (preprod-tools-style
notebook architecture). This shim keeps `from dunning_tool.gui import run`
(and `DunningApp`) working for the launcher scripts.
"""

from .ui.main_window import MainWindow, run  # noqa: F401


def DunningApp(root=None):
    """Legacy class name - returns the new MainWindow.

    Old code instantiated ``DunningApp(root)`` with its own Tk root; the
    new MainWindow IS a Tk root, so we just create and return it (the
    caller-supplied root, if any, is kept for lifetime reference).
    """
    return MainWindow()


# legacy import alias used by main.py / app.py
run = run
