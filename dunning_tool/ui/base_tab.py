# -*- coding: utf-8 -*-
"""
base_tab.py - tab base class + application context passed to every tab
(preprod tools stack style, adapted to the dunning_tool package).
"""

import threading
from tkinter import ttk

from ..engine import DunningEngine
from ..api_manager import APIManager
from ..services import (IMEILookupService, AcctLookupService,
                        SKGLookupService, InstanceLookupService)
from .threading_bridge import UIThreadBridge


class AppContext:
    """Shared application objects handed to every tab."""

    def __init__(self, root, config, bridge=None):
        self.config = config
        self.bridge = bridge or UIThreadBridge(root)
        self.translate = lambda text, **kw: text   # set by MainWindow

        # Core engine (owns db/ssh/api managers + rule cache). Created
        # unconnected; MainWindow boots it on a worker thread and calls
        # boot_engine() to rewire log/tr to the GUI.
        self.engine = DunningEngine(config, lambda msg: None,
                                    lambda t, **kw: t)
        self.db = self.engine.db
        self.imei = IMEILookupService(self.db)
        self.acct = AcctLookupService(self.db)
        # SKG service owns its own APIManager so the tab can fire the
        # sync job even when the dunning engine was never booted.
        self.skg = SKGLookupService(self.db, APIManager(config["api"]))
        # TAB4: dunning overdue-instance lookup + action drill-down.
        self.inst = InstanceLookupService(self.db)

    @staticmethod
    def make_bridge(root):
        """Create the (not yet started) UI thread bridge."""
        return UIThreadBridge(root)

    def boot_engine(self, log, tr):
        """(Re)create the engine with the GUI logger/translator attached."""
        self.engine = DunningEngine(self.config, log, tr)
        self.db = self.engine.db
        self.imei = IMEILookupService(self.db, log=log, tr=tr)
        self.acct = AcctLookupService(self.db, log=log, tr=tr)
        self.skg = SKGLookupService(
            self.db, APIManager(self.config["api"], log=log, tr=tr),
            log=log, tr=tr)
        self.inst = InstanceLookupService(self.db, log=log, tr=tr)
        return self.engine


class BaseTab(ttk.Frame):
    """Common behaviour for all feature tabs."""

    title = "Tab"

    def __init__(self, parent, ctx):
        # ctx needed by build(); assign before super().__init__ calls build()
        self.ctx = ctx
        self.bridge = ctx.bridge
        super().__init__(parent, padding=10)
        self.build()

    # ------------------------------------------------------------------
    # To be implemented by subclasses
    # ------------------------------------------------------------------
    def build(self):
        """Create the tab's widgets. Override in subclasses."""
        raise NotImplementedError

    def retranslate(self):
        """Refresh static texts after a language switch. Optional."""
        pass

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------
    def display_title(self, lang="en"):
        """Notebook tab caption for the current language."""
        from .. import i18n
        return i18n.tr(self.title, lang)

    def run_worker(self, target, *args):
        """Run target(*args) in a daemon thread."""
        threading.Thread(target=target, args=args, daemon=True).start()

    def handle_error(self, error, prefix="Error"):
        """Report an exception to the user (safe from any thread)."""
        self.bridge.show_error(prefix, str(error))

    def tr(self, text, **kwargs):
        """Translate via the main window's current language."""
        return self.ctx.translate(text, **kwargs)
