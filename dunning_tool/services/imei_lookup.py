# -*- coding: utf-8 -*-
"""
imei_lookup.py - IMEI blacklist/whitelist lookup service.

Pure table-lookup features for the Dunning tool. Two physical tables share
the exact same schema and query semantics:

    blacklist: cc.SUBS_SPECIAL_GROUP      (current records)
    whitelist: cc.SUBS_SPECIAL_GROUP_HIS  (history records)

Query rules (as specified):
    * default query (no IMEI): latest 50 rows, joined with the group type
      name so the operator can see what kind of records exist;
    * IMEI query: a 15-digit input is validated first - the last digit is
      stripped and BOTH the 15-digit and 14-digit values must return rows;
      a 14-digit input is used as-is (single value, no pair check).

Values are always bound as strings (:imei15 / :imei14 bind variables), never
interpolated into the SQL text.
"""

from ..db_manager import DatabaseManager


class IMEILookupError(Exception):
    """Validation / lookup failure with a user-facing message (i18n key)."""


class IMEILookupService:
    """Blacklist / whitelist IMEI lookups over SUBS_SPECIAL_GROUP(_HIS)."""

    TABLE_BLACKLIST = "cc.SUBS_SPECIAL_GROUP"
    TABLE_WHITELIST = "cc.SUBS_SPECIAL_GROUP_HIS"

    DEFAULT_ROWS = 50
    IMEI_ROWS = 20

    def __init__(self, db: DatabaseManager, log=None, tr=None):
        self.db = db
        self.log = log or (lambda msg: None)
        self.tr = tr or (lambda text, **kw: text)

    # ------------------------------------------------------------------
    # SQL builders (kept explicit so they can be reviewed against spec)
    # ------------------------------------------------------------------
    def _base_select(self, table):
        return (
            "SELECT st.SPECIAL_GROUP_TYPE_NAME, ssg.* "
            "FROM " + table + " ssg "
            "JOIN cc.SPECIAL_GROUP_TYPE st "
            "  ON ssg.SPECIAL_GROUP_TYPE_ID = st.SPECIAL_GROUP_TYPE_ID "
        )

    def _default_sql(self, table):
        return (self._base_select(table) +
                "ORDER BY CREATED_DATE DESC "
                "FETCH FIRST %d ROWS ONLY" % self.DEFAULT_ROWS)

    def _by_imei_sql(self, table):
        return (self._base_select(table) +
                "WHERE ssg.IMEI = :imei15 OR ssg.IMEI = :imei14 "
                "ORDER BY CREATED_DATE DESC "
                "FETCH FIRST %d ROWS ONLY" % self.IMEI_ROWS)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------
    def lookup_default(self, table=None):
        """Latest records without an IMEI filter. Returns (columns, rows)."""
        table = table or self.TABLE_BLACKLIST
        sql = self._default_sql(table)
        self.log(self.tr("Querying {table} (latest {n} rows)...",
                         table=table, n=self.DEFAULT_ROWS))
        return self.db.query_with_columns(sql)

    def lookup_imei(self, imei, table=None):
        """Look up one IMEI. Returns a result dict (see below).

        Raises IMEILookupError on invalid input (bad length / non-digit).

        Result dict keys:
            input     - cleaned user input
            imei15 / imei14 - the pair sent to the SQL (identical when the
                        input was 14 digits)
            columns / rows  - the raw result set
            found15 / found14 - whether rows exist for each variant
            both_found - True when every requested variant has rows
                        (15-digit input requires BOTH; 14-digit input only
                        requires the one)
        """
        table = table or self.TABLE_BLACKLIST
        imei_clean = self._validate(imei)
        imei15, imei14 = self._imei_pair(imei_clean)

        sql = self._by_imei_sql(table)
        params = {"imei15": imei15, "imei14": imei14}
        self.log(self.tr("Querying {table} for IMEI {imei}...",
                         table=table, imei=imei_clean))
        columns, rows = self.db.query_with_columns(sql, params)

        found15 = self._has_imei(rows, columns, imei15)
        found14 = self._has_imei(rows, columns, imei14)

        if imei15 == imei14:            # 14-digit input: single value
            both_found = found15 or found14
        else:                           # 15-digit input: pair must BOTH hit
            both_found = found15 and found14

        return {
            "input": imei_clean,
            "imei15": imei15,
            "imei14": imei14,
            "columns": columns,
            "rows": rows,
            "found15": found15,
            "found14": found14,
            "both_found": both_found,
        }

    # ------------------------------------------------------------------
    # validation helpers
    # ------------------------------------------------------------------
    def _validate(self, imei):
        imei = (imei or "").strip()
        if not imei:
            raise IMEILookupError(self.tr("Please enter an IMEI."))
        if not imei.isdigit():
            raise IMEILookupError(
                self.tr("IMEI must contain digits only (got '{value}').",
                        value=imei))
        if len(imei) not in (14, 15):
            raise IMEILookupError(
                self.tr("IMEI must be 14 or 15 digits (got {n} digits: '{value}').",
                        n=len(imei), value=imei))
        return imei

    @staticmethod
    def _imei_pair(imei):
        """Return (imei15, imei14) pair for the validated input.

        A 15-digit IMEI keeps both variants; a 14-digit IMEI is used as-is
        for both slots so the SQL pair-check degenerates to a single value.
        """
        if len(imei) == 15:
            return imei, imei[:-1]
        return imei, imei

    @staticmethod
    def _has_imei(rows, columns, imei):
        """True when at least one row carries the given IMEI value."""
        upper = [str(c).upper() for c in columns]
        try:
            idx = upper.index("IMEI")
        except ValueError:
            return bool(rows)
        for row in rows:
            value = row[idx]
            if value is not None and str(value).strip() == imei:
                return True
        return False
