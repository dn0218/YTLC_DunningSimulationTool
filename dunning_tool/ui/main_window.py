# -*- coding: utf-8 -*-
"""
main_window.py - notebook main window (preprod tools stack style).

Owns the AppContext (config, engine, services), boots the engine on a
worker thread and hosts all feature tabs. Language switching and status
reporting live here so tabs stay focused.
"""

import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox

from .. import i18n
from ..config_loader import ConfigLoader, ConfigError
from ..engine import DunningEngine, DunningError
from ..db_manager import DatabaseError
from ..ssh_manager import SSHError
from ..api_manager import APIError
from .base_tab import AppContext
from .theme import apply_theme
from .tabs import DunningTab, IMEITab, CTOSTab, SKGTab, InstanceTab


class MainWindow(tk.Tk):
    """Top-level window: owns config, context and tabs."""

    TAB_CLASSES = [DunningTab, IMEITab, CTOSTab, SKGTab, InstanceTab]

    def __init__(self):
        super().__init__()
        self.title("Dunning Simulation Tool v4")
        self.geometry("1020x780")
        self.minsize(900, 700)

        self.lang = "en"
        self.ctx = None
        self.tabs = []

        try:
            config = ConfigLoader().load()
        except ConfigError as exc:
            messagebox.showwarning(self.tr("Config"), str(exc))
            self._failed_boot = str(exc)
            self._init_failure_mode()
            return

        apply_theme(self)

        # status bar first so tabs can report into it
        self._build_status_bar()

        # thread-safe bridge poller must run on the main thread
        self._bridge_holder = AppContext.make_bridge(self)
        self._bridge_holder.start()

        self.ctx = AppContext(self, config,
                              bridge=self._bridge_holder)
        self.ctx.translate = self.tr      # tabs call ctx.translate()
        self._build_notebook()
        self._boot_engine()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # failure mode (bad/missing config): show message, allow close
    # ------------------------------------------------------------------
    def _init_failure_mode(self):
        from .threading_bridge import UIThreadBridge
        UIThreadBridge(self).start()
        self._build_status_bar()
        self.status_var.set(self._failed_boot)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    def _build_status_bar(self):
        bar = ttk.Frame(self)
        bar.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value=self.tr("Status: Ready"))
        self.status_label = ttk.Label(bar, textvariable=self.status_var,
                                      anchor="w", padding=(8, 4))
        self.status_label.pack(side="left", fill="x", expand=True)

        self.lbl_lang = ttk.Label(bar, text=self.tr("Language:"))
        self.lbl_lang.pack(side="right", padx=(4, 0))
        self.lang_var = tk.StringVar(value="English")
        self.lang_combo = ttk.Combobox(bar, textvariable=self.lang_var,
                                       values=["English", "Chinese"],
                                       state="readonly", width=8)
        self.lang_combo.pack(side="right", padx=8)
        self.lang_combo.bind("<<ComboboxSelected>>", self.on_language_changed)

    def _build_notebook(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        self.notebook = notebook
        for tab_cls in self.TAB_CLASSES:
            tab = tab_cls(notebook, self.ctx)
            notebook.add(tab, text=tab.display_title(self.lang))
            self.tabs.append(tab)

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def tr(self, text, **kwargs):
        return i18n.tr(text, self.lang, **kwargs)

    def on_language_changed(self, event=None):
        self.lang = "zh" if self.lang_var.get() == "Chinese" else "en"
        self._apply_language()

    def _apply_language(self):
        self.lbl_lang.configure(text=self.tr("Language:"))
        cur_status = self.status_var.get()
        for key in ("Status: Ready", "Status: Running...", "Status: Done",
                    "Status: Error"):
            if cur_status == i18n.tr(key, self._other_lang()):
                self.status_var.set(self.tr(key))
                break
        if self.lang == "zh":
            self.lang_var.set("Chinese")
        else:
            self.lang_var.set("English")
        for i, tab in enumerate(self.tabs):
            tab.retranslate()
            self.notebook.tab(i, text=tab.display_title(self.lang))

    def _other_lang(self):
        return "en" if self.lang == "zh" else "zh"

    # ------------------------------------------------------------------
    # engine boot
    # ------------------------------------------------------------------
    def _boot_engine(self):
        self.status_var.set(self.tr("Status: Running..."))

        def worker():
            try:
                engine = self.ctx.boot_engine(self.log_boot, self.tr)
                engine.start()
                self.ctx.bridge.run_on_ui(self._on_engine_ready)
            except ConfigError as exc:
                self.ctx.bridge.run_on_ui(self._fatal_config, str(exc))
            except Exception as exc:
                self.ctx.bridge.run_on_ui(self._fatal_db, str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def log_boot(self, msg):
        """Route engine boot logs into the dunning tab console."""
        for tab in self.tabs:
            if isinstance(tab, DunningTab):
                tab.log(msg)
                return
        # dunning tab not built yet (should not happen) - print as fallback
        print(msg)

    def _on_engine_ready(self):
        self.status_var.set(self.tr("Status: Ready"))
        for tab in self.tabs:
            if isinstance(tab, DunningTab):
                tab.log(self.tr("Database connection successful."))
                tab.on_engine_ready()

    def _fatal_config(self, msg):
        self.log_boot(msg)
        self.status_var.set(self.tr("Status: Error"))
        messagebox.showwarning(self.tr("Config"), msg)

    def _fatal_db(self, msg):
        self.log_boot(self.tr("DB connection error: {error}", error=msg))
        self.log_boot(traceback.format_exc())
        self.status_var.set(self.tr("Status: Error"))
        messagebox.showerror(self.tr("DB Error"),
                             self.tr("Database connection failed."))

    # ------------------------------------------------------------------
    def _on_close(self):
        """Release remote resources before quitting."""
        try:
            if self.ctx and self.ctx.engine:
                self.ctx.engine.close()
        except Exception:
            pass
        finally:
            self.destroy()


def run():
    MainWindow().mainloop()
