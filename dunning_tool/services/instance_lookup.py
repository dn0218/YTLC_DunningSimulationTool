# -*- coding: utf-8 -*-
"""
instance_lookup.py - TAB4: dunning overdue-instance lookup + drill-down.

Two chained queries over the dunning instance chain:

    1. instance query - cc.DEBIT_ACCT_OVERDUE_INST joined with cc.ACCT,
       filtered by ACCT_NBR, latest first (spec SQL);
    2. action drill-down - cc.DEBIT_ACCT_OVERDUE_RELA_ACTION joined with
       cc.DEBIT_RULE for the INST_ID of a row selected in (1).

Neither result set contains CLOB columns, so no LOB post-processing is
needed - plain bound-parameter queries only.
"""

from ..db_manager import DatabaseManager


class InstanceLookupError(Exception):
    """Validation / lookup failure with a user-facing message (i18n)."""


class InstanceLookupService:
    """Dunning instance lookups + per-instance action drill-down."""

    TABLE = "cc.DEBIT_ACCT_OVERDUE_INST"
    ACTION_TABLE = "cc.DEBIT_ACCT_OVERDUE_RELA_ACTION"

    def __init__(self, db: DatabaseManager, log=None, tr=None):
        self.db = db
        self.log = log or (lambda msg: None)
        self.tr = tr or (lambda text, **kw: text)

    # ------------------------------------------------------------------
    # SQL builders (kept explicit so they can be reviewed against spec)
    # ------------------------------------------------------------------
    def _instances_sql(self):
        return ("SELECT a.ACCT_NBR, d.* "
                "FROM " + self.TABLE + " d "
                "JOIN cc.ACCT a ON d.acct_id = a.acct_id "
                "WHERE a.ACCT_NBR = :acct_nbr "
                "ORDER BY d.CREATE_DATE DESC")

    def _actions_sql(self):
        return ("SELECT dr.rule_name, dra.* "
                "FROM " + self.ACTION_TABLE + " dra "
                "JOIN cc.DEBIT_RULE dr "
                "  ON dr.DEBIT_RULE_ID = dra.DEBIT_RULE_ID "
                "WHERE dra.inst_id = :inst_id "
                "ORDER BY dra.CREATE_DATE DESC")

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def lookup_by_acct(self, acct_nbr):
        """All overdue instances of one account -> (columns, rows)."""
        acct = self._validate_acct(acct_nbr)
        self.log(self.tr("Querying {table} for ACCT_NBR {acct}...",
                         table=self.TABLE, acct=acct))
        return self.db.query_with_columns(
            self._instances_sql(), {"acct_nbr": acct})

    def lookup_actions(self, inst_id):
        """Rule actions linked to one overdue instance -> (columns, rows)."""
        inst = self._validate_inst(inst_id)
        self.log(self.tr("Querying actions for INST_ID {inst}...",
                         inst=inst))
        return self.db.query_with_columns(
            self._actions_sql(), {"inst_id": inst})

    # ------------------------------------------------------------------
    # validation helpers
    # ------------------------------------------------------------------
    def _validate_acct(self, acct_nbr):
        text = (str(acct_nbr) if acct_nbr is not None else "").strip()
        if not text:
            raise InstanceLookupError(self.tr("Please enter an ACCT_NBR."))
        if not text.isdigit():
            raise InstanceLookupError(
                self.tr("ACCT_NBR must contain digits only (got '{value}').",
                        value=text))
        return text

    def _validate_inst(self, inst_id):
        if isinstance(inst_id, int) and not isinstance(inst_id, bool):
            return inst_id
        text = (str(inst_id) if inst_id is not None else "").strip()
        if not text or not text.isdigit():
            raise InstanceLookupError(
                self.tr("INST_ID must contain digits only (got '{value}').",
                        value=text))
        return int(text)
