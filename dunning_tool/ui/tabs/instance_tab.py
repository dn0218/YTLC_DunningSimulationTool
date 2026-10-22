# -*- coding: utf-8 -*-
"""
instance_tab.py - TAB4: Dunning Instance lookup with drill-down.

Workflow (spec):

    1. enter an ACCT_NBR -> "Query" lists cc.DEBIT_ACCT_OVERDUE_INST rows
       (joined with cc.ACCT) for that account, latest first;
    2. select one row -> "View Actions" uses its INST_ID to list the
       linked cc.DEBIT_ACCT_OVERDUE_RELA_ACTION rows (joined with
       cc.DEBIT_RULE for RULE_NAME);
    3. "Back" returns to the instance list without re-querying the DB.
"""

import tkinter as tk
from tkinter import ttk

from ...services import InstanceLookupError
from ..base_tab import BaseTab
from ..widgets import ResultTable

VIEW_INSTANCES = "instances"
VIEW_ACTIONS = "actions"


class InstanceTab(BaseTab):
    title = "Dunning Instance"

    def __init__(self, parent, ctx):
        # instance state must exist BEFORE super().__init__ -> build()
        self._busy = False
        self._view = VIEW_INSTANCES
        self._inst_columns = []
        self._inst_rows = []
        self._current_inst_id = None
        self._selection_var = tk.StringVar(value="")
        super().__init__(parent, ctx)

    # ------------------------------------------------------------------
    def build(self):
        # ---- header ----------------------------------------------------
        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 8))
        ttk.Label(header, text="cc.DEBIT_ACCT_OVERDUE_INST",
                  style="Muted.TLabel").pack(side="left")

        # ---- query frame -----------------------------------------------
        query = ttk.LabelFrame(self, text=" Query ")
        query.pack(fill="x", pady=4)

        self.lbl_acct = ttk.Label(query, text="ACCT_NBR:")
        self.lbl_acct.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self.acct_entry = ttk.Entry(query, width=24)
        self.acct_entry.grid(row=0, column=1, padx=8, pady=8, sticky="w")
        self.acct_entry.bind("<Return>", lambda e: self.on_query())

        self.btn_query = ttk.Button(query, text="Query",
                                    command=self.on_query)
        self.btn_query.grid(row=0, column=2, padx=8, pady=8)

        self.lbl_hint = ttk.Label(
            query,
            text="(select a row, then view its rule actions)",
            style="Muted.TLabel")
        self.lbl_hint.grid(row=0, column=3, padx=8, pady=8, sticky="w")

        # ---- result table ----------------------------------------------
        result = ttk.LabelFrame(self, text=" Result ")
        result.pack(fill="both", expand=True, pady=4)
        self.table = ResultTable(result)
        self.table.pack_table(padx=4, pady=4)
        self.table.bind("<<TreeviewSelect>>", self._on_selection_changed)

        # ---- drill-down frame ------------------------------------------
        drill = ttk.LabelFrame(self, text=" Drill-down ")
        drill.pack(fill="x", pady=(4, 0))

        self.lbl_selection = ttk.Label(drill, textvariable=self._selection_var,
                                       style="Muted.TLabel")
        self.lbl_selection.grid(row=0, column=0, padx=8, pady=8, sticky="w")

        self.btn_actions = ttk.Button(drill, text="View Actions",
                                      command=self.on_view_actions,
                                      state="disabled")
        self.btn_actions.grid(row=0, column=1, padx=8, pady=8)

        self.btn_back = ttk.Button(drill, text="Back",
                                   command=self.on_back,
                                   state="disabled")
        self.btn_back.grid(row=0, column=2, padx=8, pady=8)

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
        self.btn_query.state([state])
        self._refresh_buttons()

    def _status(self, text):
        self.status_var.set(text)

    def _selected_inst_id(self):
        """INST_ID (raw value) of the selected instance row, or None."""
        sel = self.table.selection()
        if not sel:
            return None
        try:
            col = [c.upper() for c in self._inst_columns].index("INST_ID")
        except ValueError:
            return None
        row_idx = self.table.index(sel[0])
        if row_idx >= len(self._inst_rows):
            return None
        row = self._inst_rows[row_idx]
        return row[col] if col < len(row) else None

    def _refresh_buttons(self):
        """Enable drill-down buttons according to the current view/state."""
        if self._busy:
            self.btn_actions.state(["disabled"])
            self.btn_back.state(["disabled"])
            return
        if self._view == VIEW_ACTIONS:
            # viewing actions: Back is the way out, View Actions is done
            self.btn_actions.state(["disabled"])
            self.btn_back.state(["!disabled"])
        else:  # instances view: Back has nothing to return from
            has_selection = self._selected_inst_id() is not None
            self.btn_actions.state(
                ["!disabled"] if has_selection else ["disabled"])
            self.btn_back.state(["disabled"])

    def _selection_text(self):
        inst = self._current_inst_id
        if self._view == VIEW_ACTIONS and inst is not None:
            return self.tr("Actions for INST_ID {inst}", inst=inst)
        count = len(self._inst_rows)
        if count:
            return self.tr("{n} instance(s) loaded", n=count)
        return self.tr("No instance selected yet")

    # ------------------------------------------------------------------
    # event handlers (main thread)
    # ------------------------------------------------------------------
    def on_query(self):
        if self._busy:
            return
        value = self.acct_entry.get().strip()
        self._set_busy(True)
        self.run_worker(self._do_query, value)

    def on_view_actions(self):
        if self._busy or self._view != VIEW_INSTANCES:
            return
        inst_id = self._selected_inst_id()
        if inst_id is None:
            self._status(self.tr("Select an instance row first."))
            return
        self._current_inst_id = inst_id
        self._set_busy(True)
        self.run_worker(self._do_actions, inst_id)

    def on_back(self):
        """Restore the cached instance list without re-querying the DB."""
        if self._busy or self._view != VIEW_ACTIONS:
            return
        self._view = VIEW_INSTANCES
        self._current_inst_id = None
        self.table.load(self._inst_columns, self._inst_rows)
        self._refresh_buttons()
        self._status(self.tr(
            "{n} instance(s) loaded", n=len(self._inst_rows)))

    def _on_selection_changed(self, _event=None):
        if self._view == VIEW_INSTANCES and not self._busy:
            self._refresh_buttons()

    # ------------------------------------------------------------------
    # workers (background threads)
    # ------------------------------------------------------------------
    def _do_query(self, value):
        try:
            columns, rows = self.ctx.inst.lookup_by_acct(value)
            self.bridge.run_on_ui(self._show_instances, columns, rows)
        except InstanceLookupError as e:
            self.bridge.run_on_ui(self._show_error, str(e), True)
        except Exception as e:
            self.bridge.run_on_ui(self._show_error, str(e), False)

    def _do_actions(self, inst_id):
        try:
            columns, rows = self.ctx.inst.lookup_actions(inst_id)
            self.bridge.run_on_ui(self._show_actions, columns, rows)
        except InstanceLookupError as e:
            self.bridge.run_on_ui(self._show_error, str(e), True)
        except Exception as e:
            self.bridge.run_on_ui(self._show_error, str(e), False)

    # ------------------------------------------------------------------
    # UI updates (main thread)
    # ------------------------------------------------------------------
    def _show_instances(self, columns, rows):
        self._view = VIEW_INSTANCES
        self._inst_columns = list(columns or [])
        self._inst_rows = [tuple(r) for r in (rows or [])]
        self._current_inst_id = None
        self.table.load(self._inst_columns, self._inst_rows)
        self._set_busy(False)
        self._selection_var.set(self._selection_text())
        self._status(self.tr("{n} row(s) returned.", n=len(self._inst_rows)))

    def _show_actions(self, columns, rows):
        self._view = VIEW_ACTIONS
        self.table.load(columns, rows)
        self._set_busy(False)
        self._selection_var.set(self._selection_text())
        self._status(self.tr(
            "{n} action(s) for INST_ID {inst}.",
            n=len(rows or []), inst=self._current_inst_id))

    def _show_error(self, message, is_validation):
        self._set_busy(False)
        self._status(message)
        if is_validation:
            self.bridge.show_warning(self.tr("Input"), message)
        else:
            self.bridge.show_error(self.tr("Query Error"), message)

    # ------------------------------------------------------------------
    def retranslate(self):
        self.lbl_acct.configure(text=self.tr("ACCT_NBR:"))
        self.btn_query.configure(text=self.tr("Query"))
        self.lbl_hint.configure(
            text=self.tr("(select a row, then view its rule actions)"))
        self.btn_actions.configure(text=self.tr("View Actions"))
        self.btn_back.configure(text=self.tr("Back"))
        self._selection_var.set(self._selection_text())
