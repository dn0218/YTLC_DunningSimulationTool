# -*- coding: utf-8 -*-
"""Offline tests for TAB2 (CTOS lookup) + ResultTable improvements.

Run:  python -X utf8 test_ctos_tab.py
No database / no display required for the service tests; the widget tests
need a display (tk works on this machine).

GUI tests deliberately patch out every modal messagebox and the engine
boot thread: an unattended modal would hang the run forever, and the
boot thread would swap ctx.acct/ctx.db mid-test.
"""

import gc
import time
import tkinter as tk
import unittest
from unittest import mock


def _patch_modals(testcase):
    """Make every messagebox a no-op so tests can never block on a dialog."""
    for name in ("showinfo", "showwarning", "showerror", "askyesno"):
        p = mock.patch("tkinter.messagebox." + name)
        p.start()
        testcase.addCleanup(p.stop)


# ----------------------------------------------------------------------
# 1. AcctLookupService validation + SQL builders (pure)
# ----------------------------------------------------------------------
class TestAcctLookupService(unittest.TestCase):
    def setUp(self):
        from dunning_tool.services.acct_lookup import AcctLookupService
        self.svc = AcctLookupService(db=None)

    def test_sql_builders(self):
        sql = self.svc._default_sql(self.svc.TABLE_BLACKLIST)
        self.assertIn("cc.ACCT_SPECIAL_GROUP ", sql)
        self.assertNotIn("_HIS", sql)
        self.assertIn("FETCH FIRST 50 ROWS ONLY", sql)
        self.assertNotIn("WHERE", sql)

        sql_h = self.svc._default_sql(self.svc.TABLE_WHITELIST)
        self.assertIn("cc.ACCT_SPECIAL_GROUP_HIS", sql_h)

        sql_p = self.svc._by_acct_sql(self.svc.TABLE_BLACKLIST)
        self.assertIn("WHERE asg.ACCT_NBR = :acct_nbr", sql_p)
        self.assertIn("FETCH FIRST 20 ROWS ONLY", sql_p)

    def test_validate_ok(self):
        self.assertEqual(self.svc._validate(" 300350757 "), "300350757")
        self.assertEqual(self.svc._validate("A123"), "A123")

    def test_validate_empty(self):
        from dunning_tool.services.acct_lookup import AcctLookupError
        for bad in ("", "   ", None):
            with self.assertRaises(AcctLookupError):
                self.svc._validate(bad)

    def test_validate_too_long(self):
        from dunning_tool.services.acct_lookup import AcctLookupError
        with self.assertRaises(AcctLookupError):
            self.svc._validate("9" * 61)
        self.assertEqual(self.svc._validate("9" * 60), "9" * 60)


# ----------------------------------------------------------------------
# 2. lookup_acct full flow with a mocked db
# ----------------------------------------------------------------------
class TestLookupAcctMocked(unittest.TestCase):
    def _svc(self, columns, rows):
        from dunning_tool.services.acct_lookup import AcctLookupService
        db = mock.MagicMock()
        db.query_with_columns.return_value = (columns, rows)
        return AcctLookupService(db), db

    def test_found(self):
        cols = ["ACCT_NBR", "CUST_NAME"]
        rows = [("300350757", "BHAVYAWAPI_1310")]
        svc, db = self._svc(cols, rows)
        res = svc.lookup_acct("300350757")
        self.assertTrue(res["found"])
        self.assertEqual(res["input"], "300350757")
        params = db.query_with_columns.call_args[0][1]
        self.assertEqual(params, {"acct_nbr": "300350757"})  # string bind

    def test_not_found(self):
        svc, _ = self._svc([], [])
        res = svc.lookup_acct("000000000")
        self.assertFalse(res["found"])
        self.assertEqual(res["rows"], [])

    def test_invalid_input_raises_before_db(self):
        svc, db = self._svc([], [])
        from dunning_tool.services.acct_lookup import AcctLookupError
        with self.assertRaises(AcctLookupError):
            svc.lookup_acct("   ")
        db.query_with_columns.assert_not_called()

    def test_default_query(self):
        svc, db = self._svc(["A"], [(1,), (2,)])
        cols, rows = svc.lookup_default()
        self.assertEqual(cols, ["A"])
        self.assertEqual(len(rows), 2)
        sql = db.query_with_columns.call_args[0][0]
        self.assertIn("FETCH FIRST 50", sql)


# ----------------------------------------------------------------------
# 3. ResultTable: widths / eliding / horizontal scroll / detail
# ----------------------------------------------------------------------
class TestResultTable(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        self.root.geometry("800x400")
        from dunning_tool.ui.widgets import ResultTable
        self.frame = tk.Frame(self.root)
        self.frame.pack(fill="both", expand=True)
        self.table = ResultTable(self.frame)
        self.table.pack_table()

    def tearDown(self):
        self.root.destroy()
        gc.collect()   # collect tk-Variable cycles on the main thread

    def _wide_dataset(self, nrows=8):
        long_text = ("Connect to 10.26.64.22:3128 failed: Connection "
                     "refused (Connection refused) retry loop detail ") * 3
        cols = ["ID", "ACCT_NBR", "CUST_NAME", "COMMENTS", "SCAN_STATE"]
        rows = []
        for i in range(nrows):
            rows.append((11014309 + i, "30035075%d" % i, "CUST_%d" % i,
                         long_text, "E"))
        return cols, rows

    def test_load_and_widths(self):
        cols, rows = self._wide_dataset()
        self.table.load(cols, rows)
        # all 5 columns got explicit widths within [MIN_W, MAX_W]
        for cid in self.table._col_ids:
            w = self.table.column(cid, "width")
            self.assertGreaterEqual(w, self.table.MIN_W)
            self.assertLessEqual(w, self.table.MAX_W)
        # long column capped near MAX_W (no squeezing of other columns)
        comments_w = self.table.column(self.table._col_ids[3], "width")
        self.assertGreaterEqual(comments_w, self.table.MAX_W - 3 * 7)
        self.assertLessEqual(comments_w, self.table.MAX_W)
        # all rows rendered
        self.assertEqual(len(self.table.get_children()), len(rows))

    def test_eliding_long_cells(self):
        cols, rows = self._wide_dataset(2)
        self.table.load(cols, rows)
        first = self.table.get_children()[0]
        vals = self.table.item(first, "values")
        self.assertTrue(vals[3].endswith("…"))
        self.assertLessEqual(len(vals[3]), self.table.CLIP)
        self.assertFalse(vals[1].endswith("…"))     # short cell untouched

    def test_sort_toggle_explicit(self):
        cols = ["ACCT_NBR"]
        rows = [("300350759",), ("300350751",), ("300350755",)]
        self.table.load(cols, rows)
        cid = self.table._col_ids[0]
        # explicit directions sort exactly as asked
        self.table.sort_by(cid, True)
        top = self.table.item(self.table.get_children()[0], "values")
        self.assertEqual(top[0], "300350759")
        self.table.sort_by(cid, False)
        top = self.table.item(self.table.get_children()[0], "values")
        self.assertEqual(top[0], "300350751")

    def test_sort_by_acct(self):
        cols = ["ACCT_NBR"]
        rows = [("300350759",), ("300350751",), ("300350755",)]
        self.table.load(cols, rows)
        cid = self.table._col_ids[0]
        self.table.sort_by(cid, False)      # first click: ascending
        top = self.table.item(self.table.get_children()[0], "values")
        self.assertEqual(top[0], "300350751")
        self.table.sort_by(cid, None)       # second click: toggle -> desc
        top = self.table.item(self.table.get_children()[0], "values")
        self.assertEqual(top[0], "300350759")

    def test_xview_scrolls_after_load(self):
        cols = ["C%02d" % i for i in range(12)]
        rows = [tuple("v%d-%d" % (r, c) for c in range(12))
                for r in range(5)]
        self.table.load(cols, rows)
        self.root.update()
        self.assertEqual(self.table.xview(), (0.0, self.table.xview()[1]))
        # simulate horizontal wheel: scroll right (large step on purpose)
        self.table.xview_scroll(200, "units")
        self.root.update()
        self.assertGreater(self.table.xview()[0], 0.0)

    def test_detail_popup_content(self):
        cols = ["ACCT_NBR", "COMMENTS"]
        rows = [("300350757", "x" * 200)]
        self.table.load(cols, rows)
        child = self.table.get_children()[0]
        self.table.selection_set(child)
        self.table.focus(child)
        self.table._on_detail()
        self.root.update()
        # popup exists and shows the FULL (unelided) value. Walk the whole
        # widget tree: the toplevel's Tk pathname is nested under the
        # table, so root.winfo_children() alone may not reveal it.
        tops = []
        def _walk(w):
            for ch in w.winfo_children():
                if isinstance(ch, tk.Toplevel):
                    tops.append(ch)
                _walk(ch)
        _walk(self.root)
        try:
            self.assertEqual(len(tops), 1)
            popup = tops[0]
            from tkinter import scrolledtext as st
            texts = []
            def _find_texts(w):
                for ch in w.winfo_children():
                    if isinstance(ch, st.ScrolledText):
                        texts.append(ch)
                    _find_texts(ch)
            _find_texts(popup)
            self.assertEqual(len(texts), 1)
            content = texts[0].get("1.0", "end")
            self.assertIn("x" * 200, content)   # full value, not elided
        finally:
            for t in tops:
                t.destroy()


# ----------------------------------------------------------------------
# 4. CTOSTab smoke (mocked service, no modals, no engine boot thread)
# ----------------------------------------------------------------------
class TestCTOSTabSmoke(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        _patch_modals(self)
        # keep the engine boot worker out: it would swap ctx.acct/ctx.db
        # mid-test and needs a live DB we don't have offline.
        from dunning_tool.ui.main_window import MainWindow
        p = mock.patch.object(MainWindow, "_boot_engine", lambda self: None)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.root.destroy()
        gc.collect()   # collect tk-Variable cycles on the main thread

    def _win(self):
        from dunning_tool.ui.main_window import MainWindow
        win = MainWindow()
        win.update_idletasks()
        return win

    def test_ctos_tab_registered(self):
        win = self._win()
        try:
            self.assertEqual(len(win.tabs), 5)
            self.assertEqual(win.tabs[2].title, "CTOS Blacklist / Whitelist")
            titles = [win.notebook.tab(i, "text") for i in range(5)]
            self.assertEqual(titles[2], "CTOS Blacklist / Whitelist")
            self.assertEqual(titles[3], "SKG Blacklist")
            self.assertEqual(titles[4], "Dunning Instance")
        finally:
            win.destroy()

    def test_ctos_mode_switch_and_query(self):
        win = self._win()
        try:
            tab = win.tabs[2]
            self.assertIn("ACCT_SPECIAL_GROUP", tab.table_label.cget("text"))
            self.assertNotIn("_HIS", tab.table_label.cget("text"))
            tab.on_switch_whitelist()
            self.assertIn("ACCT_SPECIAL_GROUP_HIS",
                          tab.table_label.cget("text"))

            tab.on_switch_blacklist()
            tab.acct_entry.insert(0, "300350757")
            cols = ["ACCT_NBR", "CUST_NAME"]
            rows = [("300350757", "BHAVYAWAPI_1310")]
            with mock.patch.object(tab.ctx.acct.db, "query_with_columns",
                                   return_value=(cols, rows)):
                tab.on_query()
                self._wait_busy_done(win, tab)
            self.assertFalse(tab._busy)
            self.assertEqual(len(tab.table.get_children()), 1)
        finally:
            win.destroy()

    def test_ctos_default_query(self):
        win = self._win()
        try:
            tab = win.tabs[2]
            cols = ["ACCT_NBR", "GROUP_CODE"]
            rows = [("300350757", "BLACK"), ("300350758", "BLACK")]
            with mock.patch.object(tab.ctx.acct.db, "query_with_columns",
                                   return_value=(cols, rows)) as qm:
                tab.on_default_query()
                self._wait_busy_done(win, tab)
            self.assertFalse(tab._busy)
            self.assertEqual(len(tab.table.get_children()), 2)
            sql = qm.call_args[0][0]
            self.assertIn("cc.ACCT_SPECIAL_GROUP ", sql)
            self.assertNotIn("_HIS", sql)
        finally:
            win.destroy()

    def test_ctos_validation_error(self):
        win = self._win()
        try:
            tab = win.tabs[2]
            tab.acct_entry.insert(0, " ")   # blank -> validation error
            tab.on_query()
            self._wait_busy_done(win, tab)
            self.assertFalse(tab._busy)
            self.assertIn("ACCT_NBR", tab.status_var.get())
        finally:
            win.destroy()

    @staticmethod
    def _wait_busy_done(win, tab, timeout=5.0):
        """Pump the event loop until the tab's worker result lands."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            win.update()
            if not tab._busy and tab.status_var.get():
                return
            time.sleep(0.02)
        # let assertions inspect the final state anyway
        win.update()


if __name__ == "__main__":
    unittest.main(verbosity=2)
