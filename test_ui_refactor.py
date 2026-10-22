# -*- coding: utf-8 -*-
"""Offline smoke tests for the v4.1 GUI refactor + IMEI lookup logic.

Run:  python -X utf8 test_ui_refactor.py
No database / no display required.
"""

import importlib
import sys
import unittest
from unittest import mock


# ----------------------------------------------------------------------
# 1. IMEI validation logic (pure, no DB)
# ----------------------------------------------------------------------
class TestIMEIValidation(unittest.TestCase):
    def setUp(self):
        from dunning_tool.services.imei_lookup import IMEILookupService
        self.svc = IMEILookupService(db=None)

    def test_validate_empty(self):
        from dunning_tool.services.imei_lookup import IMEILookupError
        with self.assertRaises(IMEILookupError):
            self.svc._validate("")
        with self.assertRaises(IMEILookupError):
            self.svc._validate("   ")
        with self.assertRaises(IMEILookupError):
            self.svc._validate(None)

    def test_validate_non_digit(self):
        from dunning_tool.services.imei_lookup import IMEILookupError
        for bad in ("1234567890abc", "1234-5678-9012", "abcdefghijklmno"):
            with self.assertRaises(IMEILookupError):
                self.svc._validate(bad)

    def test_validate_bad_length(self):
        from dunning_tool.services.imei_lookup import IMEILookupError
        for bad in ("1234567890123",     # 13
                    "1234567890123456",  # 16
                    "1"):                # 1
            with self.assertRaises(IMEILookupError):
                self.svc._validate(bad)

    def test_validate_ok_14_15(self):
        self.assertEqual(self.svc._validate(" 12345678901234 "), "12345678901234")
        self.assertEqual(self.svc._validate("123456789012345"), "123456789012345")

    def test_imei_pair_15(self):
        pair = self.svc._imei_pair("123456789012345")
        self.assertEqual(pair, ("123456789012345", "12345678901234"))

    def test_imei_pair_14(self):
        pair = self.svc._imei_pair("12345678901234")
        self.assertEqual(pair, ("12345678901234", "12345678901234"))

    def test_has_imei(self):
        cols = ["SPECIAL_GROUP_TYPE_NAME", "IMEI", "STATE"]
        rows = [("BLACK", "12345678901234", "A"),
                ("BLACK", "123456789012345", "A")]
        self.assertTrue(self.svc._has_imei(rows, cols, "123456789012345"))
        self.assertTrue(self.svc._has_imei(rows, cols, "12345678901234"))
        self.assertFalse(self.svc._has_imei(rows, cols, "99999999999999"))

    def test_sql_builders(self):
        sql = self.svc._by_imei_sql(self.svc.TABLE_BLACKLIST)
        self.assertIn("cc.SUBS_SPECIAL_GROUP", sql)
        self.assertIn(":imei15", sql)
        self.assertIn(":imei14", sql)
        self.assertIn("FETCH FIRST 20 ROWS ONLY", sql)
        sql_h = self.svc._by_imei_sql(self.svc.TABLE_WHITELIST)
        self.assertIn("cc.SUBS_SPECIAL_GROUP_HIS", sql_h)
        sql_d = self.svc._default_sql(self.svc.TABLE_BLACKLIST)
        self.assertIn("FETCH FIRST 50 ROWS ONLY", sql_d)
        self.assertNotIn("WHERE", sql_d)


# ----------------------------------------------------------------------
# 2. lookup_imei full flow with a mocked db
# ----------------------------------------------------------------------
class TestLookupIMEIMocked(unittest.TestCase):
    def _svc(self, columns, rows):
        from dunning_tool.services.imei_lookup import IMEILookupService
        db = mock.MagicMock()
        db.query_with_columns.return_value = (columns, rows)
        return IMEILookupService(db), db

    def test_15digit_both_found(self):
        cols = ["T", "IMEI"]
        rows = [("X", "123456789012345"), ("X", "12345678901234")]
        svc, db = self._svc(cols, rows)
        res = svc.lookup_imei("123456789012345")
        self.assertTrue(res["both_found"])
        self.assertTrue(res["found15"])
        self.assertTrue(res["found14"])
        params = db.query_with_columns.call_args[0][1]
        self.assertEqual(params, {"imei15": "123456789012345",
                                  "imei14": "12345678901234"})

    def test_15digit_only_one_found(self):
        cols = ["T", "IMEI"]
        rows = [("X", "123456789012345")]          # missing the 14-digit row
        svc, _ = self._svc(cols, rows)
        res = svc.lookup_imei("123456789012345")
        self.assertFalse(res["both_found"])
        self.assertTrue(res["found15"])
        self.assertFalse(res["found14"])

    def test_14digit_single(self):
        cols = ["T", "IMEI"]
        rows = [("X", "12345678901234")]
        svc, db = self._svc(cols, rows)
        res = svc.lookup_imei("12345678901234")
        self.assertTrue(res["both_found"])
        self.assertTrue(res["found14"])
        params = db.query_with_columns.call_args[0][1]
        self.assertEqual(params, {"imei15": "12345678901234",
                                  "imei14": "12345678901234"})

    def test_invalid_input_raises_before_db(self):
        svc, db = self._svc([], [])
        from dunning_tool.services.imei_lookup import IMEILookupError
        with self.assertRaises(IMEILookupError):
            svc.lookup_imei("123")
        db.query_with_columns.assert_not_called()


# ----------------------------------------------------------------------
# 3. i18n coverage for new keys
# ----------------------------------------------------------------------
class TestI18nNewKeys(unittest.TestCase):
    def test_keys_exist(self):
        from dunning_tool import i18n
        keys = ["Blacklist", "Whitelist", "Query IMEI", "Default Query",
                "IMEI Blacklist / Whitelist", "Dunning Simulation",
                "Please enter an IMEI.", "Yes", "No"]
        for k in keys:
            self.assertEqual(i18n.tr(k, "zh") != k, True,
                             "missing zh translation for %r" % k)


# ----------------------------------------------------------------------
# 4. module import graph (no display needed)
# ----------------------------------------------------------------------
class TestImports(unittest.TestCase):
    def test_import_services(self):
        import dunning_tool.services as s
        self.assertTrue(hasattr(s, "IMEILookupService"))

    def test_import_gui_shim(self):
        import dunning_tool.gui as g
        self.assertTrue(callable(g.run))
        self.assertTrue(callable(g.DunningApp))

    def test_import_ui_main_window(self):
        import dunning_tool.ui.main_window as mw
        self.assertTrue(hasattr(mw, "MainWindow"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
