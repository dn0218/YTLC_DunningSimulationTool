# -*- coding: utf-8 -*-
"""
test_instance_tab.py - TAB4 service + tab smoke tests.

GUI tests patch the messagebox functions and the engine boot thread, and
call gc.collect() right after every window destroy: a leftover tk-Variable
reference cycle that gets collected on a worker thread dead-locks the Tcl
interpreter (cross-thread call), which once froze the whole suite.
"""

import gc
import time
import unittest
from unittest import mock

from dunning_tool.services.instance_lookup import (
    InstanceLookupError,
    InstanceLookupService,
)

INST_COLUMNS = ["ACCT_NBR", "INST_ID", "ACCT_ID", "STATE", "CREATE_DATE"]
INST_ROWS = [
    ("845202832", 363, 204451442, "C", "2018-08-10 01:45:40"),
    ("845202832", 365, 204466165, "A", "2018-01-10 03:35:18"),
]
ACTION_COLUMNS = ["RULE_NAME", "INST_ID", "DEBIT_ACTION_ID",
                  "DEBIT_RULE_ID", "EXEC_TIME"]
ACTION_ROWS = [
    ("Level 8-after 95 days", 363, None, 26, "2018-10-28"),
    ("Level 0 -before 5 days", 363, None, 14, None),
]


# ----------------------------------------------------------------------
# 1. pure validation / SQL building
# ----------------------------------------------------------------------
class TestInstanceLookupService(unittest.TestCase):
    def _svc(self):
        return InstanceLookupService(None)

    def test_instances_sql(self):
        sql = self._svc()._instances_sql()
        self.assertIn("SELECT a.ACCT_NBR, d.*", sql)
        self.assertIn("JOIN cc.ACCT a ON d.acct_id = a.acct_id", sql)
        self.assertIn("WHERE a.ACCT_NBR = :acct_nbr", sql)
        self.assertIn("ORDER BY d.CREATE_DATE DESC", sql)

    def test_actions_sql(self):
        sql = self._svc()._actions_sql()
        self.assertIn("SELECT dr.rule_name, dra.*", sql)
        self.assertIn("JOIN cc.DEBIT_RULE dr", sql)
        self.assertIn("WHERE dra.inst_id = :inst_id", sql)

    def test_validate_acct_ok(self):
        self.assertEqual(self._svc()._validate_acct(" 845202832 "),
                         "845202832")

    def test_validate_acct_empty(self):
        with self.assertRaises(InstanceLookupError):
            self._svc()._validate_acct("   ")

    def test_validate_acct_non_digit(self):
        with self.assertRaises(InstanceLookupError):
            self._svc()._validate_acct("84-52832x")

    def test_validate_inst_int_passthrough(self):
        self.assertEqual(self._svc()._validate_inst(363), 363)

    def test_validate_inst_digit_string(self):
        self.assertEqual(self._svc()._validate_inst(" 363 "), 363)

    def test_validate_inst_bad(self):
        for bad in ("", None, "abc", "3-63"):
            with self.assertRaises(InstanceLookupError):
                self._svc()._validate_inst(bad)


# ----------------------------------------------------------------------
# 2. queries with mocked db
# ----------------------------------------------------------------------
class TestInstanceLookupMocked(unittest.TestCase):
    def _svc(self, columns, rows):
        db = mock.MagicMock()
        db.query_with_columns.return_value = (columns, rows)
        return InstanceLookupService(db), db

    def test_lookup_by_acct_binds_acct_nbr(self):
        svc, db = self._svc(INST_COLUMNS, INST_ROWS)
        cols, rows = svc.lookup_by_acct("845202832")
        sql, params = (db.query_with_columns.call_args[0][0],
                       db.query_with_columns.call_args[0][1])
        self.assertIn(":acct_nbr", sql)
        self.assertEqual(params, {"acct_nbr": "845202832"})
        self.assertEqual(rows, INST_ROWS)
        self.assertEqual(cols, INST_COLUMNS)

    def test_lookup_by_acct_invalid_before_db(self):
        svc, db = self._svc([], [])
        with self.assertRaises(InstanceLookupError):
            svc.lookup_by_acct("x")
        db.query_with_columns.assert_not_called()

    def test_lookup_actions_binds_inst_id(self):
        svc, db = self._svc(ACTION_COLUMNS, ACTION_ROWS)
        cols, rows = svc.lookup_actions(363)
        sql, params = (db.query_with_columns.call_args[0][0],
                       db.query_with_columns.call_args[0][1])
        self.assertIn(":inst_id", sql)
        self.assertEqual(params, {"inst_id": 363})
        self.assertEqual(rows, ACTION_ROWS)
        self.assertEqual(cols, ACTION_COLUMNS)

    def test_lookup_actions_invalid_before_db(self):
        svc, db = self._svc([], [])
        with self.assertRaises(InstanceLookupError):
            svc.lookup_actions("bad-id")
        db.query_with_columns.assert_not_called()


# ----------------------------------------------------------------------
# 3. tab smoke (mocked service, no modals, no engine boot thread)
# ----------------------------------------------------------------------
class TestInstanceTabSmoke(unittest.TestCase):
    LANGS = ("en", "zh")

    def setUp(self):
        import tkinter as tk
        self._modal_patches = [
            mock.patch("tkinter.messagebox." + name)
            for name in ("showinfo", "showwarning", "showerror", "askyesno")
        ]
        for p in self._modal_patches:
            p.start()
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()
        gc.collect()  # collect tk-Variable cycles on the main thread
        for p in self._modal_patches:
            p.stop()

    def _make_window(self):
        """MainWindow with the engine boot bypassed (no DB/network)."""
        from dunning_tool.ui.main_window import MainWindow
        with mock.patch.object(MainWindow, "_boot_engine", lambda self: None):
            return MainWindow()

    def _pump(self, window, tab, timeout=5.0):
        """Run the tk event loop until the tab leaves the busy state."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            window.update()
            if not tab._busy:
                return True
            time.sleep(0.02)
        return False

    # -- registration --------------------------------------------------
    def test_instance_tab_registered(self):
        window = self._make_window()
        try:
            self.assertEqual(len(window.tabs), 5)
            from dunning_tool.ui.tabs.instance_tab import InstanceTab
            self.assertIsInstance(window.tabs[4], InstanceTab)
            titles = [t.display_title("en") for t in window.tabs]
            self.assertIn("Dunning Instance", titles)
        finally:
            window.destroy()
            gc.collect()

    # -- instance query flow ---------------------------------------------
    def test_instance_query_flow(self):
        window = self._make_window()
        try:
            tab = window.tabs[4]
            svc = mock.MagicMock()
            svc.lookup_by_acct.return_value = (INST_COLUMNS, INST_ROWS)
            tab.ctx.inst = svc

            tab.acct_entry.delete(0, "end")
            tab.acct_entry.insert(0, "845202832")
            tab.on_query()
            self.assertTrue(self._pump(window, tab))

            svc.lookup_by_acct.assert_called_once_with("845202832")
            self.assertEqual(len(tab.table.get_children()), 2)
            self.assertIn("2", tab.status_var.get())
            # nothing selected yet -> drill-down disabled
            self.assertIn("disabled", tab.btn_actions.state())
        finally:
            window.destroy()
            gc.collect()

    def test_instance_query_invalid_input_no_db(self):
        window = self._make_window()
        try:
            tab = window.tabs[4]
            svc = mock.MagicMock()
            svc.lookup_by_acct.side_effect = InstanceLookupError("bad input")
            tab.ctx.inst = svc

            tab.acct_entry.insert(0, "abc")
            tab.on_query()
            self.assertTrue(self._pump(window, tab))
            self.assertEqual(len(tab.table.get_children()), 0)
            self.assertIn("bad input", tab.status_var.get())
        finally:
            window.destroy()
            gc.collect()

    # -- drill-down flow -------------------------------------------------
    def test_actions_drilldown_and_back(self):
        window = self._make_window()
        try:
            tab = window.tabs[4]
            svc = mock.MagicMock()
            svc.lookup_by_acct.return_value = (INST_COLUMNS, INST_ROWS)
            svc.lookup_actions.return_value = (ACTION_COLUMNS, ACTION_ROWS)
            tab.ctx.inst = svc

            # step 1: instance query
            tab.acct_entry.insert(0, "845202832")
            tab.on_query()
            self.assertTrue(self._pump(window, tab))
            self.assertIn("disabled", tab.btn_back.state())

            # step 2: select the row whose INST_ID is 365 -> View Actions
            target = next(i for i, r in enumerate(INST_ROWS) if r[1] == 365)
            child = tab.table.get_children()[target]
            tab.table.selection_set(child)
            tab.table.focus(child)
            self.assertEqual(tab._selected_inst_id(), 365)

            tab.on_view_actions()
            self.assertTrue(self._pump(window, tab))
            svc.lookup_actions.assert_called_once_with(365)
            self.assertEqual(len(tab.table.get_children()), 2)
            self.assertIn("INST_ID 365", tab.status_var.get())
            self.assertIn("disabled", tab.btn_actions.state())
            self.assertNotIn("disabled", tab.btn_back.state())

            # step 3: Back restores the cached instance list
            tab.on_back()
            self.assertEqual(len(tab.table.get_children()), 2)
            first = tab.table.item(tab.table.get_children()[0], "values")
            self.assertEqual(str(first[INST_COLUMNS.index("INST_ID")]), "363")
            # table was reloaded -> selection gone -> View Actions disabled
            self.assertIn("disabled", tab.btn_actions.state())
            self.assertIn("disabled", tab.btn_back.state())
        finally:
            window.destroy()
            gc.collect()

    def test_actions_without_selection_shows_hint(self):
        window = self._make_window()
        try:
            tab = window.tabs[4]
            svc = mock.MagicMock()
            svc.lookup_by_acct.return_value = (INST_COLUMNS, INST_ROWS)
            tab.ctx.inst = svc

            tab.acct_entry.insert(0, "845202832")
            tab.on_query()
            self.assertTrue(self._pump(window, tab))

            # no selection -> View Actions must refuse without a DB call
            tab.table.selection_remove(*tab.table.get_children())
            tab.on_view_actions()
            window.update()
            svc.lookup_actions.assert_not_called()
            self.assertIn("Select an instance row first",
                          tab.status_var.get())
        finally:
            window.destroy()
            gc.collect()

    # -- language switch -------------------------------------------------
    def test_language_switch(self):
        window = self._make_window()
        try:
            tab = window.tabs[4]
            for lang in self.LANGS:
                window.lang_var.set(
                    "Chinese" if lang == "zh" else "English")
                window.on_language_changed()
                window.update()
                self.assertEqual(tab.btn_actions.cget("text"),
                                 tab.tr("View Actions"))
                self.assertEqual(tab.btn_back.cget("text"), tab.tr("Back"))
        finally:
            window.destroy()
            gc.collect()


if __name__ == "__main__":
    unittest.main()
