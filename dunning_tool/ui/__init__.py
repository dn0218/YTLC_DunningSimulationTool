# -*- coding: utf-8 -*-
"""
ui - GUI package (preprod tools stack style).

    theme            - centralized colors/styles (clam theme)
    threading_bridge - worker-thread -> Tk main loop marshal
    base_tab         - AppContext + BaseTab
    widgets          - ConsoleWidget, ResultTable
    main_window      - notebook MainWindow + engine boot
    tabs/            - feature tabs (Dunning, IMEI, ...)
"""

from .theme import apply_theme
from .threading_bridge import UIThreadBridge
from .base_tab import BaseTab, AppContext
from .widgets import ConsoleWidget, ResultTable
from .main_window import MainWindow, run

__all__ = ["apply_theme", "UIThreadBridge", "BaseTab", "AppContext",
           "ConsoleWidget", "ResultTable", "MainWindow", "run"]
