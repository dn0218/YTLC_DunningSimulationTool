# -*- coding: utf-8 -*-
"""
dunning_tab.py - the original Dunning Simulation feature, migrated from the
single-window gui.py into the new notebook architecture.

Behaviour (unchanged from v4):
    * get account (id or number) -> detect customer type / rule group
    * run initial setup
    * run level simulation

All engine calls run on worker threads; results are marshalled back via
the UIThreadBridge.
"""

import traceback
import tkinter as tk
from tkinter import ttk, messagebox

from ...engine import DunningError
from ...db_manager import DatabaseError
from ...ssh_manager import SSHError
from ...api_manager import APIError
from ..base_tab import BaseTab
from ..widgets import ConsoleWidget


class DunningTab(BaseTab):
    title = "Dunning Simulation"

    GROUP_ORDER = (4, 5, 14)
    GROUP_NAMES = {4: "MASSIVE", 5: "ENTERPRISE", 14: "HYBRID"}
    GROUP_I18N = {"MASSIVE": "Massive", "ENTERPRISE": "Enterprise",
                  "HYBRID": "Hybrid"}

    def __init__(self, parent, ctx):
        # instance state must exist BEFORE super().__init__ -> build()
        self.levels = []            # list[RuleLevel] currently shown
        self._busy = False
        super().__init__(parent, ctx)

    # ------------------------------------------------------------------
    def build(self):
        # ---- top: account + language ---------------------------------
        top = ttk.Frame(self)
        top.pack(pady=6, fill="x")

        self.lbl_acct = ttk.Label(top, text=self.tr("Account ID or Number:"))
        self.lbl_acct.pack(side=tk.LEFT)
        self.acct_entry = ttk.Entry(top, width=20)
        self.acct_entry.pack(side=tk.LEFT, padx=5)
        self.acct_entry.bind("<Return>", lambda e: self.on_get_account())

        self.get_acct_btn = ttk.Button(top, text=self.tr("Get Account"),
                                       command=self.on_get_account)
        self.get_acct_btn.pack(side=tk.LEFT, padx=5)

        self.acct_label = ttk.Label(top, text=self.tr("USER_ACCT: None"),
                                    foreground="#0056b3")
        self.acct_label.pack(side=tk.LEFT, padx=10)

        # ---- setup button ---------------------------------------------
        self.setup_btn = ttk.Button(
            self, text=self.tr("Run Initial Setup"),
            command=self.on_run_setup, style="Success.TButton")
        self.setup_btn.pack(pady=5)

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=8)

        # ---- simulation row --------------------------------------------
        sim = ttk.Frame(self)
        sim.pack(pady=5, fill="x")

        self.lbl_group = ttk.Label(sim, text=self.tr("Customer Type:"))
        self.lbl_group.pack(side=tk.LEFT)
        self.group_var = tk.StringVar()
        self.group_combo = ttk.Combobox(sim, textvariable=self.group_var,
                                        state="readonly", width=14)
        self.group_combo.pack(side=tk.LEFT, padx=5)
        self.group_combo.bind("<<ComboboxSelected>>", self.on_group_changed)

        self.lbl_level = ttk.Label(sim, text=self.tr("Level:"))
        self.lbl_level.pack(side=tk.LEFT, padx=(10, 0))
        self.level_var = tk.StringVar()
        self.level_combo = ttk.Combobox(sim, textvariable=self.level_var,
                                        state="readonly", width=52)
        self.level_combo.pack(side=tk.LEFT, padx=5, fill="x", expand=True)

        self.sim_btn = ttk.Button(sim, text=self.tr("Run Simulation"),
                                  command=self.on_run_simulation,
                                  style="Success.TButton")
        self.sim_btn.pack(side=tk.LEFT, padx=10)

        # ---- log --------------------------------------------------------
        log_frame = ttk.LabelFrame(self, text=" " + self.tr("Log") + " ")
        log_frame.pack(fill="both", expand=True, pady=6)
        self.log_text = ConsoleWidget(log_frame, height=14)
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

        self._enable_buttons(False)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def log(self, msg):
        self.bridge.run_on_ui(self.log_text.append, str(msg))

    def _set_status(self, key):
        self.log(self.tr(key))

    def _enable_buttons(self, enabled):
        state = tk.NORMAL if enabled else tk.DISABLED
        for btn in (self.get_acct_btn, self.setup_btn, self.sim_btn):
            btn.config(state=state)
        self.group_combo.config(state="readonly" if enabled else tk.DISABLED)
        self.level_combo.config(state="readonly" if enabled else tk.DISABLED)

    def _set_busy(self, busy):
        self._busy = busy
        self._enable_buttons(not busy)
        self._set_status("Status: Running..." if busy else "Status: Ready")

    def _guard(self):
        if self._busy:
            messagebox.showwarning(self.tr("Busy"),
                                   self.tr("Another operation is already running."))
            return False
        if self.ctx.engine is None:
            messagebox.showerror(self.tr("DB Error"),
                                 self.tr("Database connection failed."))
            return False
        return True

    def _spawn(self, fn, on_success=None):
        """Run fn on a worker thread; centralised error handling."""
        def runner():
            try:
                result = fn()
            except DunningError as exc:
                # bind via default arg: `exc` is deleted when the except
                # block ends, a closure over it would raise NameError later
                self.bridge.run_on_ui(self._on_error, str(exc), "Verification")
                return
            except (DatabaseError, SSHError, APIError) as exc:
                self.bridge.run_on_ui(self._on_error, str(exc), "Error")
                return
            except Exception as exc:  # unexpected
                self.bridge.run_on_ui(self._on_unexpected, str(exc))
                return
            if on_success:
                self.bridge.run_on_ui(on_success, result)
            else:
                self.bridge.run_on_ui(self._set_busy, False)
        self.run_worker(runner)

    def _on_error(self, msg, title_key):
        self.log(msg)
        self._set_busy(False)
        self._set_status("Status: Error")
        messagebox.showerror(self.tr(title_key), msg)

    def _on_unexpected(self, exc_str):
        self.log(self.tr("Simulation exception: {error}", error=exc_str))
        self.log(traceback.format_exc())
        self._set_busy(False)
        self._set_status("Status: Error")
        messagebox.showerror(self.tr("Simulation Error"), exc_str)

    # ------------------------------------------------------------------
    # level / group combo handling
    # ------------------------------------------------------------------
    def _group_display_list(self):
        labels = []
        for gid in self.GROUP_ORDER:
            if self.ctx.engine and self.ctx.engine.rules.levels_for_group(gid):
                labels.append(self.tr(self.GROUP_I18N[self.GROUP_NAMES[gid]]))
        return labels

    def _selected_group_id(self):
        shown = self.group_var.get()
        for gid in self.GROUP_ORDER:
            label = self.tr(self.GROUP_I18N[self.GROUP_NAMES[gid]])
            if label == shown:
                return gid
        return None

    def _refresh_levels(self):
        if self.ctx.engine is None:
            return
        gid = self._selected_group_id() or self.ctx.engine.group_id or 4
        # keep combobox in sync with what the engine will use
        if self.ctx.engine.group_id not in (None, gid):
            gid = self.ctx.engine.group_id
        self.levels = self.ctx.engine.rules.levels_for_group(gid)
        self.level_combo["values"] = [lv.label for lv in self.levels]
        if self.levels:
            self.level_combo.current(0)
        else:
            self.level_var.set("")
            self.log(self.tr("No actionable levels found for rule group {group}.",
                             group=gid))

    def _sync_group_combo(self):
        names = self.GROUP_NAMES
        current = names.get(self.ctx.engine.group_id, "MASSIVE")
        self.group_var.set(self.tr(self.GROUP_I18N[current]))
        self.group_combo["values"] = self._group_display_list()

    def on_engine_ready(self):
        """Called by the main window once the engine booted successfully."""
        if self.ctx.engine.group_id is None:
            self.ctx.engine.group_id = 4
        self._sync_group_combo()
        self._refresh_levels()
        self._enable_buttons(True)

    # ------------------------------------------------------------------
    # event handlers
    # ------------------------------------------------------------------
    def on_group_changed(self, event=None):
        gid = self._selected_group_id()
        if gid is None or self.ctx.engine is None:
            return
        self.ctx.engine.group_id = gid
        self._refresh_levels()
        self.log(self.tr("Switched customer type to [{type}], level options updated.",
                         type=self.group_var.get()))

    def on_get_account(self):
        if not self._guard():
            return
        value = self.acct_entry.get().strip()
        if not value:
            messagebox.showwarning(self.tr("Input"),
                                   self.tr("Please enter account_id or account_number."))
            return
        self._set_busy(True)

        def work():
            return self.ctx.engine.get_account(value)

        def done(acct):
            self.acct_label.config(
                text="USER_ACCT: %s (%s)" % (acct, self.tr(
                    self.GROUP_I18N[self.GROUP_NAMES.get(self.ctx.engine.group_id,
                                                         "MASSIVE")])))
            self._sync_group_combo()
            self._refresh_levels()
            self._set_busy(False)
            self._set_status("Status: Done")

        self._spawn(work, on_success=done)

    def on_run_setup(self):
        if not self._guard():
            return
        if self.ctx.engine.user_acct is None:
            messagebox.showwarning(self.tr("No Account"),
                                   self.tr("Please get account first."))
            return
        self._set_busy(True)

        def work():
            return self.ctx.engine.run_initial_setup()

        def done(inst_id):
            self._set_busy(False)
            self._set_status("Status: Done")
            messagebox.showinfo(self.tr("Setup"),
                                self.tr("Initial setup completed."))

        self._spawn(work, on_success=done)

    def on_run_simulation(self):
        if not self._guard():
            return
        if self.ctx.engine.user_acct is None:
            messagebox.showwarning(self.tr("No Account"),
                                   self.tr("Please get account first."))
            return
        idx = self.level_combo.current()
        if idx < 0 or idx >= len(self.levels):
            messagebox.showerror(self.tr("Error"),
                                 self.tr("Invalid level selection."))
            return
        level = self.levels[idx]
        self._set_busy(True)

        def work():
            return self.ctx.engine.run_simulation(level)

        def done(result):
            self._set_busy(False)
            if result and result.get("ok"):
                self._set_status("Status: Done")
                self.log(self.tr("Level {label} simulation succeeded!",
                                 label=level.label))
                messagebox.showinfo(self.tr("Success"),
                                    self.tr("Level {label} simulation succeeded!",
                                            label=level.name))
            else:
                self._set_status("Status: Error")
                messagebox.showerror(
                    self.tr("Verification"),
                    self.tr("EXEC_TIME not set, simulation did not complete."))

        self._spawn(work, on_success=done)

    # ------------------------------------------------------------------
    def retranslate(self):
        self.lbl_acct.configure(text=self.tr("Account ID or Number:"))
        self.get_acct_btn.configure(text=self.tr("Get Account"))
        self.setup_btn.configure(text=self.tr("Run Initial Setup"))
        self.lbl_group.configure(text=self.tr("Customer Type:"))
        self.lbl_level.configure(text=self.tr("Level:"))
        self.sim_btn.configure(text=self.tr("Run Simulation"))
        if self.ctx.engine and self.ctx.engine.user_acct:
            self.acct_label.config(
                text="USER_ACCT: %s (%s)" % (self.ctx.engine.user_acct,
                                             self.tr(self.GROUP_I18N[
                                                 self.GROUP_NAMES.get(
                                                     self.ctx.engine.group_id,
                                                     "MASSIVE")])))
        else:
            self.acct_label.config(text=self.tr("USER_ACCT: None"))
        self._sync_group_combo()
        self._refresh_levels()
