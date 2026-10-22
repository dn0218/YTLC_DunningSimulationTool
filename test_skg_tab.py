# -*- coding: utf-8 -*-
"""Offline tests for TAB3 (SKG blacklist) + sync job trigger.

Run:  python -X utf8 test_skg_tab.py
No database / no display required for the service tests; the widget tests
need a display (tk works on this machine).

GUI tests deliberately patch out every modal messagebox and the engine
boot thread (same pattern as test_ctos_tab.py): an unattended modal would
hang the run forever, and the boot thread would swap ctx services
mid-test.
"""

import datetime
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
# 1. SKGLookupService validation + SQL builders (pure)
# ----------------------------------------------------------------------
class TestSKGLookupService(unittest.TestCase):
    def setUp(self):
        from dunning_tool.services.skg_lookup import SKGLookupService
        self.svc = SKGLookupService(db=None)

    def test_default_sql(self):
        sql = self.svc._default_sql()
        self.assertIn("cc.SPECIAL_GROUP_SYNC", sql)
        self.assertIn("ORDER BY CREATED_DATE DESC", sql)
        self.assertIn("FETCH FIRST 50 ROWS ONLY", sql)
        self.assertNotIn("WHERE", sql)

    def test_by_imei_sql(self):
        sql = self.svc._by_imei_sql()
        self.assertIn("cc.SPECIAL_GROUP_SYNC", sql)
        self.assertIn("EXT_ATTR LIKE :imei15", sql)
        self.assertIn("EXT_ATTR LIKE :imei14", sql)
        self.assertIn("ORDER BY CREATED_DATE DESC", sql)
        self.assertIn("FETCH FIRST 20 ROWS ONLY", sql)

    def test_validate_ok(self):
        self.assertEqual(self.svc._validate(" 12345678901234 "), "12345678901234")
        self.assertEqual(self.svc._validate("123456789012345"), "123456789012345")

    def test_validate_empty(self):
        from dunning_tool.services.skg_lookup import SKGLookupError
        for bad in ("", "   ", None):
            with self.assertRaises(SKGLookupError):
                self.svc._validate(bad)

    def test_validate_non_digit(self):
        from dunning_tool.services.skg_lookup import SKGLookupError
        with self.assertRaises(SKGLookupError):
            self.svc._validate("1234567890123a")

    def test_validate_bad_length(self):
        from dunning_tool.services.skg_lookup import SKGLookupError
        with self.assertRaises(SKGLookupError):
            self.svc._validate("1234567890123")      # 13
        with self.assertRaises(SKGLookupError):
            self.svc._validate("1234567890123456")   # 16

    def test_imei_pair(self):
        # 15 digits -> strip exactly one trailing digit
        self.assertEqual(self.svc._imei_pair("123456789012345"),
                         ("123456789012345", "12345678901234"))
        # 14 digits -> same value in both slots
        self.assertEqual(self.svc._imei_pair("12345678901234"),
                         ("12345678901234", "12345678901234"))

    # ---- QRY_DATE validation ------------------------------------------
    def test_date_default_today(self):
        got = self.svc._validate_date(None)
        self.assertEqual(got, datetime.date.today().strftime("%Y-%m-%d"))
        got = self.svc._validate_date("   ")
        self.assertEqual(got, datetime.date.today().strftime("%Y-%m-%d"))

    def test_date_ok(self):
        self.assertEqual(self.svc._validate_date("2026-01-15"), "2026-01-15")
        # slashes are tolerated and normalized
        self.assertEqual(self.svc._validate_date("2026/01/15"), "2026-01-15")

    def test_date_invalid(self):
        from dunning_tool.services.skg_lookup import SKGLookupError
        for bad in ("not-a-date", "2026-13-01", "2026-02-30",
                    "15-01-2026", "20260115"):
            with self.assertRaises(SKGLookupError):
                self.svc._validate_date(bad)


# ----------------------------------------------------------------------
# 2. lookup + trigger with mocked db/api
# ----------------------------------------------------------------------
class TestSKGLookupMocked(unittest.TestCase):
    def _svc(self, columns, rows, api=None):
        from dunning_tool.services.skg_lookup import SKGLookupService
        db = mock.MagicMock()
        db.query_with_columns.return_value = (columns, rows)
        return SKGLookupService(db, api), db

    def test_lookup_imei_15digit(self):
        ext = "abc;IMEI=12345678901234;xyz"
        cols = ["ID", "EXT_ATTR"]
        rows = [(1, ext)]
        svc, db = self._svc(cols, rows)
        res = svc.lookup_imei("123456789012345")
        params = db.query_with_columns.call_args[0][1]
        self.assertEqual(params["imei15"], "%123456789012345%")
        self.assertEqual(params["imei14"], "%12345678901234%")
        self.assertTrue(res["found14"])     # only the 14 variant is in EXT
        self.assertFalse(res["found15"])

    def test_lookup_imei_14digit(self):
        ext = "abc;IMEI=12345678901234;xyz"
        svc, db = self._svc(["ID", "EXT_ATTR"], [(1, ext)])
        res = svc.lookup_imei("12345678901234")
        params = db.query_with_columns.call_args[0][1]
        self.assertEqual(params["imei15"], "%12345678901234%")
        self.assertEqual(params["imei14"], "%12345678901234%")
        self.assertTrue(res["found14"])

    def test_lookup_not_found(self):
        svc, _ = self._svc(["ID"], [])
        res = svc.lookup_imei("12345678901234")
        self.assertFalse(res["found15"])
        self.assertFalse(res["found14"])
        self.assertEqual(res["rows"], [])

    def test_invalid_input_raises_before_db(self):
        svc, db = self._svc([], [])
        from dunning_tool.services.skg_lookup import SKGLookupError
        with self.assertRaises(SKGLookupError):
            svc.lookup_imei("12x")
        db.query_with_columns.assert_not_called()

    def test_trigger_uses_api(self):
        api = mock.MagicMock()
        svc, _ = self._svc([], [], api=api)
        svc.trigger_sync_job("2026-01-15")
        api.trigger_skg_blacklist_sync_job.assert_called_once_with("2026-01-15")

    def test_trigger_invalid_date_before_api(self):
        from dunning_tool.services.skg_lookup import SKGLookupError
        api = mock.MagicMock()
        svc, _ = self._svc([], [], api=api)
        with self.assertRaises(SKGLookupError):
            svc.trigger_sync_job("not-a-date")
        api.trigger_skg_blacklist_sync_job.assert_not_called()

    def test_trigger_without_api(self):
        from dunning_tool.services.skg_lookup import SKGLookupError
        svc, _ = self._svc([], [], api=None)
        with self.assertRaises(SKGLookupError):
            svc.trigger_sync_job("2026-01-15")

    # -- CLOB / LOB materialization -----------------------------------
    def test_materialize_rows_reads_and_closes_lobs(self):
        class FakeLob:
            def __init__(self, text):
                self.text, self.reads, self.closed = text, 0, False

            def read(self):
                self.reads += 1
                return self.text

            def close(self):
                self.closed = True

        lob = FakeLob('{"deviceUid":"123456789012345"}')
        svc, _ = self._svc(["ID", "EXT_ATTR"], [(1, lob), (2, None)])
        res = svc.lookup_imei("123456789012345")
        self.assertEqual(lob.reads, 1)
        self.assertTrue(lob.closed)
        rows = res["rows"]
        self.assertEqual(rows[0][1], '{"deviceUid":"123456789012345"}')
        self.assertEqual(rows[1][1], None)          # None stays None
        self.assertTrue(res["found15"])             # hit via materialized text

    def test_materialize_rows_unreadable_lob_is_replaced(self):
        class BadLob:
            def read(self):
                raise RuntimeError("boom")

        svc, _ = self._svc(["EXT_ATTR"], [(BadLob(),)])
        res = svc.lookup_imei("123456789012345")
        self.assertEqual(res["rows"][0][0], "<unreadable LOB>")
        self.assertFalse(res["found15"])


# ----------------------------------------------------------------------
# 3. SKGTab smoke (mocked service, no modals, no engine boot thread)
# ----------------------------------------------------------------------
class TestSKGTabSmoke(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("no display")
        _patch_modals(self)
        # keep the engine boot worker out: it would swap ctx services
        # mid-test and needs a live DB we don't have offline.
        from dunning_tool.ui.main_window import MainWindow
        p = mock.patch.object(MainWindow, "_boot_engine", lambda self: None)
        p.start()
        self.addCleanup(p.stop)

    def tearDown(self):
        self.root.destroy()
        # Collect reference cycles HERE on the main thread. Windows keep
        # tk Variables (StringVar...) in cycles; if they survive until a
        # GC runs inside a later WORKER thread (e.g. while a MagicMock
        # child is allocated), Variable.__del__ calls Tcl cross-thread on
        # a destroyed interpreter and hangs the worker forever. This is
        # exactly the same hardening test_ctos_tab.py uses.
        gc.collect()

    def _win(self):
        from dunning_tool.ui.main_window import MainWindow
        win = MainWindow()
        win.update_idletasks()
        return win

    @staticmethod
    def _wait_busy_done(win, tab, timeout=5.0):
        """Pump the event loop until the tab's worker result lands."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            win.update()
            if not tab._busy and tab.status_var.get():
                return
            time.sleep(0.02)
        win.update()

    def test_skg_tab_registered(self):
        win = self._win()
        try:
            self.assertEqual(len(win.tabs), 5)
            self.assertEqual(win.tabs[3].title, "SKG Blacklist")
            titles = [win.notebook.tab(i, "text") for i in range(5)]
            self.assertEqual(titles[3], "SKG Blacklist")
            self.assertEqual(titles[4], "Dunning Instance")
        finally:
            win.destroy()

    def test_skg_default_query(self):
        win = self._win()
        try:
            tab = win.tabs[3]
            cols = ["ID", "EXT_ATTR"]
            rows = [(1, "a"), (2, "b")]
            with mock.patch.object(tab.ctx.skg.db, "query_with_columns",
                                   return_value=(cols, rows)) as qm:
                tab.on_default_query()
                self._wait_busy_done(win, tab)
            self.assertFalse(tab._busy)
            self.assertEqual(len(tab.table.get_children()), 2)
            sql = qm.call_args[0][0]
            self.assertIn("cc.SPECIAL_GROUP_SYNC", sql)
        finally:
            win.destroy()

    def test_skg_imei_query_flow(self):
        win = self._win()
        try:
            tab = win.tabs[3]
            tab.imei_entry.insert(0, "123456789012345")
            cols = ["ID", "EXT_ATTR"]
            rows = [(1, "x;IMEI=12345678901234;y")]
            with mock.patch.object(tab.ctx.skg.db, "query_with_columns",
                                   return_value=(cols, rows)):
                tab.on_query()
                self._wait_busy_done(win, tab)
            self.assertFalse(tab._busy)
            self.assertEqual(len(tab.table.get_children()), 1)
            status = tab.status_var.get()
            self.assertIn("15-digit", status)
            self.assertIn("14-digit", status)
        finally:
            win.destroy()

    def test_skg_validation_error(self):
        win = self._win()
        try:
            tab = win.tabs[3]
            tab.imei_entry.insert(0, " ")   # blank -> validation error
            tab.on_query()
            self._wait_busy_done(win, tab)
            self.assertFalse(tab._busy)
            self.assertIn("IMEI", tab.status_var.get())
        finally:
            win.destroy()

    def test_skg_trigger_confirmed(self):
        win = self._win()
        try:
            tab = win.tabs[3]
            api = mock.MagicMock()
            tab.ctx.skg.api = api
            with mock.patch.object(tab.bridge, "ask_yes_no",
                                   return_value=True) as ask:
                tab.on_trigger()
                self._wait_busy_done(win, tab)
            ask.assert_called_once()
            today = datetime.date.today().strftime("%Y-%m-%d")
            api.trigger_skg_blacklist_sync_job.assert_called_once_with(today)
            self.assertFalse(tab._busy)
            self.assertIn("triggered", tab.status_var.get())
        finally:
            win.destroy()

    def test_skg_trigger_cancelled(self):
        win = self._win()
        try:
            tab = win.tabs[3]
            api = mock.MagicMock()
            tab.ctx.skg.api = api
            with mock.patch.object(tab.bridge, "ask_yes_no",
                                   return_value=False):
                tab.on_trigger()
                win.update()
            self.assertIn("cancel", tab.status_var.get().lower())
            api.trigger_skg_blacklist_sync_job.assert_not_called()
        finally:
            win.destroy()

    def test_skg_trigger_bad_date_fails_before_confirm(self):
        win = self._win()
        try:
            tab = win.tabs[3]
            api = mock.MagicMock()
            tab.ctx.skg.api = api
            tab.date_var.set("not-a-date")
            with mock.patch.object(tab.bridge, "ask_yes_no",
                                   return_value=True) as ask:
                tab.on_trigger()
                win.update()
            # validation runs BEFORE the confirm dialog
            ask.assert_not_called()
            api.trigger_skg_blacklist_sync_job.assert_not_called()
            self.assertIn("QRY_DATE", tab.status_var.get())
        finally:
            win.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
