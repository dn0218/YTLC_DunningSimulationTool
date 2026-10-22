# -*- coding: utf-8 -*-
"""
skg_tab.py - TAB3: SKG Blacklist lookup + SKGBlacklistSyncJob trigger.

Two independent features share one tab:

    * blacklist query - cc.SPECIAL_GROUP_SYNC, plain table browse or an
      IMEI substring search over EXT_ATTR (15-digit input searches both
      the 15 and the 14-digit variant);
    * sync trigger - fires SKGBlacklistSyncJob via jobservermgr
      (group=_jobserver_, params QRY_DATE=...|REPROCESS=Y|SP_ID=101)
      after a confirmation dialog; QRY_DATE defaults to today.
"""

import datetime
import tkinter as tk
from tkinter import ttk

from ...services import SKGLookupError
from ..base_tab import BaseTab
from ..widgets import ResultTable


class SKGTab(BaseTab):
    title = "SKG Blacklist"

    def __init__(self, parent, ctx):
        # instance state must exist BEFORE super().__init__ -> build()
        self._busy = False
        super().__init__(parent, ctx)

    # ------------------------------------------------------------------
    def build(self):
        # ---- header ----------------------------------------------------
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="cc.SPECIAL_GROUP_SYNC",
                  style="Muted.TLabel").pack(side="left")

        # ---- query frame (left feature: table lookup) ------------------
        query = ttk.LabelFrame(self, text=" Query ")
        query.pack(fill="x", pady=4)

        self.lbl_imei = ttk.Label(query, text="IMEI:")
        self.lbl_imei.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self.imei_entry = ttk.Entry(query, width=24)
        self.imei_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        self.imei_entry.bind("<Return>", lambda e: self.on_query())

        self.btn_query = ttk.Button(query, text="Query IMEI",
                                    command=self.on_query)
        self.btn_query.grid(row=0, column=2, padx=8, pady=8)

        self.btn_default = ttk.Button(query, text="Default Query",
                                      command=self.on_default_query)
        self.btn_default.grid(row=0, column=3, padx=8, pady=8)

        self.lbl_hint = ttk.Label(
            query,
            text="(EXT_ATTR substring match; 15 digits -> 15+14 pair)",
            style="Muted.TLabel")
        self.lbl_hint.grid(row=0, column=4, padx=8, pady=8, sticky="w")

        # ---- result table ----------------------------------------------
        result = ttk.LabelFrame(self, text=" Result ")
        result.pack(fill="both", expand=True, pady=4)
        self.table = ResultTable(result)
        self.table.pack_table(padx=4, pady=4)

        # ---- trigger frame (right feature: sync job) --------------------
        trigger = ttk.LabelFrame(self, text=" SKG Sync Job ")
        trigger.pack(fill="x", pady=(4, 0))

        self.lbl_date = ttk.Label(trigger, text="QRY_DATE:")
        self.lbl_date.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self.date_var = tk.StringVar(
            value=datetime.date.today().strftime("%Y-%m-%d"))
        self.date_entry = ttk.Entry(trigger, width=14,
                                    textvariable=self.date_var)
        self.date_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")

        self.btn_trigger = ttk.Button(trigger, text="Trigger Sync Job",
                                      command=self.on_trigger)
        self.btn_trigger.grid(row=0, column=2, padx=8, pady=8)

        self.lbl_trigger_hint = ttk.Label(
            trigger,
            text="SKGBlacklistSyncJob  (QRY_DATE|REPROCESS=Y|SP_ID=101)",
            style="Muted.TLabel")
        self.lbl_trigger_hint.grid(row=0, column=3, padx=8, pady=8,
                                   sticky="w")

        # ---- status line ------------------------------------------------
        self.status_var = tk.StringVar(value="")
        self.status = ttk.Label(self, textvariable=self.status_var,
                                style="Muted.TLabel", anchor="w")
        self.status.pack(fill="x", pady=(6, 0))

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _set_busy(self, busy):
        self._busy = busy
        state = "disabled" if busy else "!disabled"
        for btn in (self.btn_query, self.btn_default, self.btn_trigger):
            btn.state([state])
        if busy:
            self.status_var.set(self.tr("Querying..."))

    def _status(self, text):
        self.status_var.set(text)

    # ------------------------------------------------------------------
    # event handlers (main thread)
    # ------------------------------------------------------------------
    def on_query(self):
        if self._busy:
            return
        value = self.imei_entry.get().strip()
        self._set_busy(True)
        self.run_worker(self._do_query, value)

    def on_default_query(self):
        if self._busy:
            return
        self._set_busy(True)
        self.run_worker(self._do_default)

    def on_trigger(self):
        """Confirm, then fire SKGBlacklistSyncJob on a worker thread."""
        if self._busy:
            return
        date_text = self.date_var.get().strip()
        # validate date BEFORE asking so bad input fails fast & cheap
        try:
            date_str = self.ctx.skg._validate_date(date_text)
        except SKGLookupError as exc:
            self._status(str(exc))
            self.bridge.show_warning(self.tr("Input"), str(exc))
            return
        message = self.tr(
            "Trigger SKGBlacklistSyncJob?\n\nQRY_DATE: {date}\n"
            "REPROCESS=Y, SP_ID=101", date=date_str)
        if not self.bridge.ask_yes_no(
                self.tr("Confirm"), message):
            self._status(self.tr("Trigger cancelled."))
            return
        self._set_busy(True)
        self.run_worker(self._do_trigger, date_str)

    # ------------------------------------------------------------------
    # workers (background threads)
    # ------------------------------------------------------------------
    def _do_query(self, value):
        try:
            result = self.ctx.skg.lookup_imei(value)
            self.bridge.run_on_ui(self._show_result, result)
        except SKGLookupError as e:
            self.bridge.run_on_ui(self._show_error, str(e), True)
        except Exception as e:
            self.bridge.run_on_ui(self._show_error, str(e), False)

    def _do_default(self):
        try:
            columns, rows = self.ctx.skg.lookup_default()
            self.bridge.run_on_ui(self._show_rows, columns, rows)
        except Exception as e:
            self.bridge.run_on_ui(self._show_error, str(e), False)

    def _do_trigger(self, date_str):
        try:
            self.ctx.skg.trigger_sync_job(date_str)
            self.bridge.run_on_ui(self._show_trigger_done, date_str)
        except Exception as e:
            self.bridge.run_on_ui(self._show_error, str(e), False)

    # ------------------------------------------------------------------
    # UI updates (main thread)
    # ------------------------------------------------------------------
    def _show_rows(self, columns, rows, status=None):
        self.table.load(columns, rows)
        self._set_busy(False)
        self._status(status or self.tr(
            "{n} row(s) returned.", n=len(rows or [])))

    def _show_result(self, result):
        status = self.tr(
            "IMEI {imei}: 15-digit {r15}, 14-digit {r14}.",
            imei=result["input"],
            r15=self._yes_no(result["found15"]),
            r14=self._yes_no(result["found14"]))
        self._show_rows(result["columns"], result["rows"], status)

    def _show_trigger_done(self, date_str):
        self._set_busy(False)
        self._status(self.tr(
            "SKGBlacklistSyncJob triggered for {date}.", date=date_str))
        self.bridge.show_info(
            self.tr("Success"),
            self.tr("SKGBlacklistSyncJob triggered for {date}.",
                    date=date_str))

    def _show_error(self, message, is_validation):
        self._set_busy(False)
        self._status(message)
        if is_validation:
            self.bridge.show_warning(self.tr("IMEI"), message)
        else:
            self.bridge.show_error(self.tr("Query Error"), message)

    def _yes_no(self, flag):
        return self.tr("Yes") if flag else self.tr("No")

    # ------------------------------------------------------------------
    def retranslate(self):
        self.lbl_imei.configure(text=self.tr("IMEI:"))
        self.btn_query.configure(text=self.tr("Query IMEI"))
        self.btn_default.configure(text=self.tr("Default Query"))
        self.lbl_hint.configure(
            text=self.tr(
                "(EXT_ATTR substring match; 15 digits -> 15+14 pair)"))
        self.lbl_date.configure(text=self.tr("QRY_DATE:"))
        self.btn_trigger.configure(text=self.tr("Trigger Sync Job"))
        self.lbl_trigger_hint.configure(
            text=self.tr(
                "SKGBlacklistSyncJob  (QRY_DATE|REPROCESS=Y|SP_ID=101)"))
