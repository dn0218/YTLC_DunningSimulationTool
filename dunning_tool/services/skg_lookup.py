# -*- coding: utf-8 -*-
"""
skg_lookup.py - SKG blacklist lookup service (TAB3).

Single physical table, one lookup feature + one job trigger helper:

    table: cc.SPECIAL_GROUP_SYNC

Query rules (as specified):
    * default query (no IMEI): latest 50 rows by CREATED_DATE;
    * IMEI query: EXT_ATTR is a free-text/CLOB blob that *contains* the
      IMEI somewhere inside, so the match is LIKE '%<imei>%'. A 15-digit
      input is stripped to 14 and BOTH values are OR-ed into the LIKE
      (same 14/15 pair convention as TAB1, but substring semantics and
      no pair-both-must-hit requirement);
    * SKG job trigger: built on APIManager.trigger_skg_blacklist_sync_job
      (QRY_DATE=YYYY-MM-DD|REPROCESS=Y|SP_ID=101, group=_jobserver_).

    * EXT_ATTR is a CLOB: oracledb thin mode returns LOB locators, so
      result rows are post-processed to read + close the locators. This
      keeps the GUI strings readable and makes found15/found14 work.

Values are always bound (:imei15 / :imei14), never interpolated.
"""

from ..db_manager import DatabaseManager
from ..api_manager import APIManager

TABLE = "cc.SPECIAL_GROUP_SYNC"


class SKGLookupError(Exception):
    """Validation / lookup failure with a user-facing message (i18n key)."""


class SKGLookupService:
    """SKG blacklist lookups over cc.SPECIAL_GROUP_SYNC + sync trigger."""

    TABLE = TABLE

    DEFAULT_ROWS = 50
    IMEI_ROWS = 20

    def __init__(self, db: DatabaseManager, api: APIManager = None,
                 log=None, tr=None):
        self.db = db
        self.api = api
        self.log = log or (lambda msg: None)
        self.tr = tr or (lambda text, **kw: text)

    # ------------------------------------------------------------------
    # SQL builders (kept explicit so they can be reviewed against spec)
    # ------------------------------------------------------------------
    def _default_sql(self):
        return ("SELECT skg.* FROM " + TABLE + " skg "
                "ORDER BY CREATED_DATE DESC "
                "FETCH FIRST %d ROWS ONLY" % self.DEFAULT_ROWS)

    def _by_imei_sql(self):
        return ("SELECT skg.* FROM " + TABLE + " skg "
                "WHERE EXT_ATTR LIKE :imei15 OR EXT_ATTR LIKE :imei14 "
                "ORDER BY CREATED_DATE DESC "
                "FETCH FIRST %d ROWS ONLY" % self.IMEI_ROWS)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def lookup_default(self):
        """Latest records without an IMEI filter -> (columns, rows)."""
        self.log(self.tr("Querying {table} (latest {n} rows)...",
                         table=TABLE, n=self.DEFAULT_ROWS))
        columns, rows = self.db.query_with_columns(self._default_sql())
        return columns, self._materialize_rows(rows)

    def lookup_imei(self, imei):
        """Substring-search EXT_ATTR for the 15/14-digit IMEI pair.

        Raises SKGLookupError on invalid input.

        Result dict keys:
            input          - cleaned user input
            imei15 / imei14 - the pair sent to the SQL (identical when the
                        input was 14 digits)
            columns / rows  - the raw result set
            found15 / found14 - whether rows exist for each variant
        """
        imei_clean = self._validate(imei)
        imei15, imei14 = self._imei_pair(imei_clean)

        params = {"imei15": "%" + imei15 + "%",
                  "imei14": "%" + imei14 + "%"}
        self.log(self.tr("Querying {table} for IMEI {imei}...",
                         table=TABLE, imei=imei_clean))
        columns, rows = self.db.query_with_columns(
            self._by_imei_sql(), params)
        rows = self._materialize_rows(rows)

        found15 = self._rows_contain(rows, imei15)
        found14 = self._rows_contain(rows, imei14)

        return {
            "input": imei_clean,
            "imei15": imei15,
            "imei14": imei14,
            "columns": columns,
            "rows": rows,
            "found15": found15,
            "found14": found14,
        }

    # ------------------------------------------------------------------
    # job trigger
    # ------------------------------------------------------------------
    def trigger_sync_job(self, qry_date=None):
        """Fire SKGBlacklistSyncJob for the given date (default: today).

        Returns the requests.Response from APIManager (or a mock in tests).
        """
        if self.api is None:
            raise SKGLookupError("APIManager not configured.")
        date_str = self._validate_date(qry_date)
        self.log(self.tr("Triggering SKGBlacklistSyncJob for {date}...",
                         date=date_str))
        return self.api.trigger_skg_blacklist_sync_job(date_str)

    # ------------------------------------------------------------------
    # validation helpers
    # ------------------------------------------------------------------
    def _validate(self, imei):
        imei = (imei or "").strip()
        if not imei:
            raise SKGLookupError(self.tr("Please enter an IMEI."))
        if not imei.isdigit():
            raise SKGLookupError(
                self.tr("IMEI must contain digits only (got '{value}').",
                        value=imei))
        if len(imei) not in (14, 15):
            raise SKGLookupError(
                self.tr("IMEI must be 14 or 15 digits (got {n} digits: '{value}').",
                        n=len(imei), value=imei))
        return imei

    @staticmethod
    def _imei_pair(imei):
        """(imei15, imei14) for the validated input.

        15 digits keeps both variants (last digit stripped for the 14);
        14 digits is used as-is for both slots (SQL degenerates to one
        effective condition - harmless duplicate LIKE).
        """
        if len(imei) == 15:
            return imei, imei[:-1]
        return imei, imei

    @classmethod
    def _materialize_rows(cls, rows):
        """Read + close any LOB locator so rows are plain Python values.

        oracledb thin mode returns LOB objects for CLOB columns; leaving
        them as-is would render '<oracledb.LOB object ...>' in the table
        widget and break the substring hit detection.
        """
        out = []
        for row in rows:
            new_row = []
            for value in row:
                if value is not None and hasattr(value, "read"):
                    try:
                        text = value.read()
                    except Exception:
                        value = "<unreadable LOB>"
                    else:
                        try:
                            value.close()
                        except Exception:
                            pass
                        value = text
                new_row.append(value)
            out.append(tuple(new_row))
        return out

    @staticmethod
    def _rows_contain(rows, imei):
        """True when any row's text mentions the IMEI (EXT_ATTR scan)."""
        for row in rows:
            for value in row:
                if value is not None and imei in str(value):
                    return True
        return False

    def _validate_date(self, value):
        """Accept YYYY-MM-DD (or YYYY/MM/DD); default = today (sysdate)."""
        import datetime
        text = (value or "").strip()
        if not text:
            text = datetime.date.today().strftime("%Y-%m-%d")
        normalized = text.replace("/", "-")
        try:
            parsed = datetime.datetime.strptime(normalized, "%Y-%m-%d")
        except ValueError:
            raise SKGLookupError(self.tr(
                "QRY_DATE must be YYYY-MM-DD (got '{value}').",
                value=text))
        return parsed.strftime("%Y-%m-%d")
