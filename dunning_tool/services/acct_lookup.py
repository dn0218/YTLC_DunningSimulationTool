# -*- coding: utf-8 -*-
"""
acct_lookup.py - CTOS blacklist / IMEI-whitelist lookup service (TAB2).

Same dual-table pattern as imei_lookup (TAB1), but for account-level CTOS
records queried by ACCT_NBR:

    blacklist: cc.ACCT_SPECIAL_GROUP      (current records)
    whitelist: cc.ACCT_SPECIAL_GROUP_HIS  (history records)

Query rules (as specified):
    * default query: latest 50 rows by CREATED_DATE;
    * parameter query: exact ACCT_NBR match (string bind), latest 20 rows.

No IMEI 15/14 pair logic here - the user input is an ACCT_NBR string.
"""

from ..db_manager import DatabaseManager


class AcctLookupError(Exception):
    """Validation / lookup failure with a user-facing message (i18n key)."""


class AcctLookupService:
    """CTOS blacklist / whitelist ACCT_NBR lookups."""

    TABLE_BLACKLIST = "cc.ACCT_SPECIAL_GROUP"
    TABLE_WHITELIST = "cc.ACCT_SPECIAL_GROUP_HIS"

    DEFAULT_ROWS = 50
    ACCT_ROWS = 20

    def __init__(self, db: DatabaseManager, log=None, tr=None):
        self.db = db
        self.log = log or (lambda msg: None)
        self.tr = tr or (lambda text, **kw: text)

    # ------------------------------------------------------------------
    # SQL builders (kept explicit so they can be reviewed against spec)
    # ------------------------------------------------------------------
    def _default_sql(self, table):
        return ("SELECT asg.* FROM " + table + " asg "
                "ORDER BY CREATED_DATE DESC "
                "FETCH FIRST %d ROWS ONLY" % self.DEFAULT_ROWS)

    def _by_acct_sql(self, table):
        return ("SELECT asg.* FROM " + table + " asg "
                "WHERE asg.ACCT_NBR = :acct_nbr "
                "ORDER BY CREATED_DATE DESC "
                "FETCH FIRST %d ROWS ONLY" % self.ACCT_ROWS)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def lookup_default(self, table=None):
        """Latest records without an ACCT_NBR filter -> (columns, rows)."""
        table = table or self.TABLE_BLACKLIST
        self.log(self.tr("Querying {table} (latest {n} rows)...",
                         table=table, n=self.DEFAULT_ROWS))
        return self.db.query_with_columns(self._default_sql(table))

    def lookup_acct(self, acct_nbr, table=None):
        """Look up records for one ACCT_NBR -> result dict (see below).

        Raises AcctLookupError on invalid input.

        Result dict keys:
            input          - cleaned user input
            columns / rows - the raw result set
            found          - whether at least one row matched
        """
        table = table or self.TABLE_BLACKLIST
        value = self._validate(acct_nbr)

        self.log(self.tr("Querying {table} for ACCT_NBR {value}...",
                         table=table, value=value))
        columns, rows = self.db.query_with_columns(
            self._by_acct_sql(table), {"acct_nbr": value})

        return {
            "input": value,
            "columns": columns,
            "rows": rows,
            "found": bool(rows),
        }

    # ------------------------------------------------------------------
    # validation helpers
    # ------------------------------------------------------------------
    def _validate(self, acct_nbr):
        value = str(acct_nbr or "").strip()
        if not value:
            raise AcctLookupError(self.tr("Please enter an ACCT_NBR."))
        if len(value) > 60:
            raise AcctLookupError(
                self.tr("ACCT_NBR too long (max 60 chars, got {n}).",
                        n=len(value)))
        return value
