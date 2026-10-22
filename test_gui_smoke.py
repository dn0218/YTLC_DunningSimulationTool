# -*- coding: utf-8 -*-
"""GUI smoke test: builds the real Tk window with a mocked engine boot.

Verifies:
    * MainWindow constructs, both tabs appear in the notebook
    * IMEI tab mode switching updates labels/table
    * IMEI query path works end-to-end (mocked db)
    * language switch retranslates tabs

Run:  python -X utf8 test_gui_smoke.py
"""

import gc
import tkinter as tk
import unittest
from unittest import mock


def _fake_query_with_columns(sql, params=None):
    cols = ["SPECIAL_GROUP_TYPE_NAME", "IMEI", "STATE", "CREATED_DATE"]
    rows = [
        ("BLACK_IMEI", "123456789012345", "A", "2025-01-01"),
        ("BLACK_IMEI", "12345678901234", "A", "2025-01-01"),
    ]
    return cols, rows


class TestGUISmoke(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root_avail = True
        except Exception:
            cls.root_avail = False

    def _make_window(self):
        from dunning_tool.ui.main_window import MainWindow
        win = MainWindow()
        win.update_idletasks()
        return win

    def test_window_builds(self):
        win = self._make_window()
        try:
            self.assertEqual(len(win.tabs), 5)
            titles = [t.title for t in win.tabs]
            self.assertEqual(titles[0], "Dunning Simulation")
            self.assertEqual(titles[1], "IMEI Blacklist / Whitelist")
            self.assertEqual(titles[2], "CTOS Blacklist / Whitelist")
            self.assertEqual(titles[3], "SKG Blacklist")
            self.assertEqual(titles[4], "Dunning Instance")
            # tab 0 is a DunningTab with a console
            dtab = win.tabs[0]
            self.assertTrue(hasattr(dtab, "log_text"))
            # tab 1 is the IMEI tab with switcher + table
            itab = win.tabs[1]
            self.assertTrue(hasattr(itab, "table"))
            self.assertTrue(hasattr(itab, "imei_entry"))
            # tab 2 is the CTOS tab with switcher + ACCT_NBR entry
            ctab = win.tabs[2]
            self.assertTrue(hasattr(ctab, "table"))
            self.assertTrue(hasattr(ctab, "acct_entry"))
        finally:
            win.destroy()
            gc.collect()   # collect tk-Variable cycles on the main thread

    def test_imei_tab_mode_switch(self):
        win = self._make_window()
        try:
            itab = win.tabs[1]
            self.assertIn("SUBS_SPECIAL_GROUP", itab.table_label.cget("text"))
            self.assertNotIn("_HIS", itab.table_label.cget("text"))
            itab.on_switch_whitelist()
            self.assertIn("SUBS_SPECIAL_GROUP_HIS",
                          itab.table_label.cget("text"))
            itab.on_switch_blacklist()
            self.assertIn("SUBS_SPECIAL_GROUP", itab.table_label.cget("text"))
            self.assertNotIn("_HIS", itab.table_label.cget("text"))
        finally:
            win.destroy()
            gc.collect()   # collect tk-Variable cycles on the main thread

    def test_imei_query_flow(self):
        win = self._make_window()
        try:
            itab = win.tabs[1]
            itab.imei_entry.insert(0, "123456789012345")
            with mock.patch.object(itab.ctx.imei.db,
                                   "query_with_columns",
                                   side_effect=_fake_query_with_columns):
                itab.on_query()
                # let the worker + bridge schedule run
                win.update()
                for _ in range(20):
                    win.update()
                    try:
                        itab.ctx.bridge._root.after_idle(lambda: None)
                    except Exception:
                        pass
            # worker marshals via after(0); pump the event loop
            import time
            deadline = time.time() + 5
            while time.time() < deadline:
                win.update()
                if not itab._busy and itab.status_var.get():
                    break
                time.sleep(0.05)
            self.assertFalse(itab._busy)
            self.assertIn("2", itab.status_var.get())
            children = itab.table.get_children()
            self.assertEqual(len(children), 2)
        finally:
            win.destroy()
            gc.collect()   # collect tk-Variable cycles on the main thread

    def test_language_switch(self):
        win = self._make_window()
        try:
            win.lang_var.set("Chinese")
            win.on_language_changed()
            self.assertEqual(win.notebook.tab(1, "text"),
                             "IMEI 黑名单 / 白名单")
            itab = win.tabs[1]
            self.assertEqual(itab.btn_query.cget("text"), "查询 IMEI")
            win.lang_var.set("English")
            win.on_language_changed()
            self.assertEqual(win.notebook.tab(1, "text"),
                             "IMEI Blacklist / Whitelist")
        finally:
            win.destroy()
            gc.collect()   # collect tk-Variable cycles on the main thread


if __name__ == "__main__":
    unittest.main(verbosity=2)
