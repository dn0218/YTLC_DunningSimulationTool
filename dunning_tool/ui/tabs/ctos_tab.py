# -*- coding: utf-8 -*-
"""
ctos_tab.py - TAB2: CTOS Blacklist / IMEI Whitelist lookup.

Same dual-table pattern as TAB1 (imei_tab), but the tables are
account-level CTOS records and the user input is an ACCT_NBR:

    blacklist -> cc.ACCT_SPECIAL_GROUP
    whitelist -> cc.ACCT_SPECIAL_GROUP_HIS
"""

import tkinter as tk
from tkinter import ttk

from ...services import AcctLookupError
from ..base_tab import BaseTab
from ..widgets import ResultTable


class CTOSTab(BaseTab):
    title = "CTOS Blacklist / Whitelist"

    MODE_BLACKLIST = "blacklist"
    MODE_WHITELIST = "whitelist"

    def __init__(self, parent, ctx):
        # instance state must exist BEFORE super().__init__ -> build()
        self._mode = self.MODE_BLACKLIST
        self._busy = False
        super().__init__(parent, ctx)

    # ------------------------------------------------------------------
    def build(self):
        # ---- mode switcher row ----------------------------------------
        top = ttk.Frame(self)
        top.pack(fill="x", pady=(0, 8))

        self.btn_blacklist = ttk.Button(
            top, text="Blacklist", style="Toggle.TButton",
            command=self.on_switch_blacklist)
        self.btn_blacklist.pack(side="left", padx=(0, 4))

        self.btn_whitelist = ttk.Button(
            top, text="Whitelist", style="Toggle.TButton",
            command=self.on_switch_whitelist)
        self.btn_whitelist.pack(side="left", padx=4)

        self.table_label = ttk.Label(top, text="", style="Muted.TLabel")
        self.table_label.pack(side="left", padx=12)

        # ---- query frame ----------------------------------------------
        query = ttk.LabelFrame(self, text=" Query ")
        query.pack(fill="x", pady=4)

        self.lbl_acct = ttk.Label(query, text="ACCT_NBR:")
        self.lbl_acct.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self.acct_entry = ttk.Entry(query, width=24)
        self.acct_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        self.acct_entry.bind("<Return>", lambda e: self.on_query())

        self.btn_query = ttk.Button(query, text="Query ACCT_NBR",
                                    command=self.on_query)
        self.btn_query.grid(row=0, column=2, padx=8, pady=8)

        self.btn_default = ttk.Button(query, text="Default Query",
                                      command=self.on_default_query)
        self.btn_default.grid(row=0, column=3, padx=8, pady=8)

        self.lbl_hint = ttk.Label(
            query, text="(exact match, string comparison)",
            style="Muted.TLabel")
        self.lbl_hint.grid(row=0, column=4, padx=8, pady=8, sticky="w")

        # ---- result table ----------------------------------------------
        result = ttk.LabelFrame(self, text=" Result ")
        result.pack(fill="both", expand=True, pady=4)
        self.table = ResultTable(result)
        self.table.pack_table(padx=4, pady=4)

        # ---- status line ------------------------------------------------
        self.status_var = tk.StringVar(value="")
        self.status = ttk.Label(self, textvariable=self.status_var,
                                style="Muted.TLabel", anchor="w")
        self.status.pack(fill="x", pady=(6, 0))

        self._apply_mode()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _current_table(self):
        return (self.ctx.acct.TABLE_BLACKLIST
                if self._mode == self.MODE_BLACKLIST
                else self.ctx.acct.TABLE_WHITELIST)

    def _apply_mode(self):
        # mark the active mode on the button label (● prefix)
        if self._mode == self.MODE_BLACKLIST:
            self.btn_blacklist.configure(text="● " + self.tr("Blacklist"))
            self.btn_whitelist.configure(text=self.tr("Whitelist"))
        else:
            self.btn_blacklist.configure(text=self.tr("Blacklist"))
            self.btn_whitelist.configure(text="● " + self.tr("Whitelist"))
        self.table_label.configure(text=self._current_table())
        self.table.clear()
        self.status_var.set("")

    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "!disabled"
        for btn in (self.btn_query, self.btn_default,
                    self.btn_blacklist, self.btn_whitelist):
            btn.state([state])
        if busy:
            self.status_var.set(self.tr("Querying..."))

    # ------------------------------------------------------------------
    # event handlers
    # ------------------------------------------------------------------
    def on_switch_blacklist(self):
        if self._mode != self.MODE_BLACKLIST:
            self._mode = self.MODE_BLACKLIST
            self._apply_mode()

    def on_switch_whitelist(self):
        if self._mode != self.MODE_WHITELIST:
            self._mode = self.MODE_WHITELIST
            self._apply_mode()

    def on_query(self):
        if self._busy:
            return
        value = self.acct_entry.get().strip()
        table = self._current_table()
        self._set_busy(True)
        self.run_worker(self._do_query, value, table)

    def on_default_query(self):
        if self._busy:
            return
        table = self._current_table()
        self._set_busy(True)
        self.run_worker(self._do_default, table)

    # ------------------------------------------------------------------
    # workers (background threads)
    # ------------------------------------------------------------------
    def _do_query(self, value, table):
        try:
            result = self.ctx.acct.lookup_acct(value, table)
            self.bridge.run_on_ui(self._show_result, result)
        except AcctLookupError as e:
            self.bridge.run_on_ui(self._show_error, str(e), True)
        except Exception as e:
            self.bridge.run_on_ui(self._show_error, str(e), False)

    def _do_default(self, table):
        try:
            columns, rows = self.ctx.acct.lookup_default(table)
            self.bridge.run_on_ui(self._show_rows, columns, rows)
        except Exception as e:
            self.bridge.run_on_ui(self._show_error, str(e), False)

    # ------------------------------------------------------------------
    # UI updates (main thread)
    # ------------------------------------------------------------------
    def _show_rows(self, columns, rows, status=None):
        self.table.load(columns, rows)
        self._set_busy(False)
        self.status_var.set(status or self.tr(
            "{n} row(s) returned.", n=len(rows or [])))

    def _show_result(self, result):
        status = self.tr("ACCT_NBR {value}: {found}.",
                         value=result["input"],
                         found=self._yes_no(result["found"]))
        self._show_rows(result["columns"], result["rows"], status)

    def _show_error(self, message, is_validation):
        self._set_busy(False)
        self.status_var.set(message)
        if is_validation:
            self.bridge.show_warning(self.tr("ACCT_NBR"), message)
        else:
            self.bridge.show_error(self.tr("Query Error"), message)

    def _yes_no(self, flag):
        return self.tr("Yes") if flag else self.tr("No")

    # ------------------------------------------------------------------
    def retranslate(self):
        self.lbl_acct.configure(text=self.tr("ACCT_NBR:"))
        self.btn_query.configure(text=self.tr("Query ACCT_NBR"))
        self.btn_default.configure(text=self.tr("Default Query"))
        self.lbl_hint.configure(text=self.tr("(exact match, string comparison)"))
        self._apply_mode()
