# -*- coding: utf-8 -*-
"""
db_manager.py - all Oracle SQL access.

The manager keeps a single lazy connection (singleton per instance) and
exposes small, intention-revealing query/command helpers so the engine never
touches raw cursors.

DRIVER: python-oracledb (successor of cx_Oracle) is preferred - it installs
as a plain wheel (no Oracle Client needed in thin mode).  If only cx_Oracle
is available it is used instead; the API subset used here is identical
(connect/cursor/execute/fetch/commit/rollback/makedsn).
"""

import sys
import threading

try:
    import oracledb as _ora            # thin mode, no client libs needed
except ImportError as _ora_err:        # keep the reason to show the real cause
    try:
        import cx_Oracle as _ora       # requires Oracle Instant Client on PATH
    except ImportError:
        _ora = None
    _ORA_IMPORT_ERROR = str(_ora_err)
else:
    _ORA_IMPORT_ERROR = None


def _driver_missing():
    where = sys.executable or "python"
    if getattr(sys, "frozen", False):
        return DatabaseError(
            "No Oracle driver installed: the packaged .exe is missing the\n"
            "oracledb module (bad build). Rebuild with build_exe.bat and make\n"
            "sure 'oracledb' installs without errors during step 2/4."
        )
    return DatabaseError(
        "No Oracle driver installed in this Python interpreter.\n"
        "Interpreter: " + where + "\n"
        "Import failure: " + (_ORA_IMPORT_ERROR or "module not found") + "\n"
        "Fix (run with the SAME interpreter that starts the app):\n"
        "  \"" + where + "\" -m pip install oracledb\n"
        "(cx_Oracle also works, but needs the Oracle Instant Client on PATH.)"
    )


class DatabaseError(Exception):
    """Wrapper for database related failures."""


class DatabaseManager:
    """Encapsulates every SQL statement used by the dunning tool."""

    ATTR_ID = 907207

    # Attribute values considered valid per customer family (see spec 4).
    MASSIVE_VALID = ("FIZ_CONSUMER", "HOME_USERS", "NON_VIP_CUSTOMER",
                     "TESTLINE", "TESTUSER")
    ENT_VALID = ("NON_VIP_ENT", "TESTLINE", "SMI_SME")
    MASSIVE_DEFAULT = "NON_VIP_CUSTOMER"
    ENT_DEFAULT = "NON_VIP_ENT"

    def __init__(self, db_config):
        self._cfg = db_config
        self._conn = None
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # connection handling
    # ------------------------------------------------------------------
    def connect(self, force=False):
        """Open the connection if needed. Returns True on success."""
        with self._lock:
            if _ora is None:
                raise _driver_missing()
            if self._conn is not None and not force:
                try:
                    cur = self._conn.cursor()
                    cur.execute("SELECT 1 FROM DUAL")
                    cur.close()
                    return True
                except _ora.Error:
                    self._close_locked()

            dsn = _ora.makedsn(self._cfg["host"], int(self._cfg["port"]),
                               service_name=self._cfg["service_name"])
            try:
                self._conn = _ora.connect(user=self._cfg["user"],
                                          password=self._cfg["password"],
                                          dsn=dsn)
            except _ora.Error as exc:
                raise DatabaseError(str(exc))
            return True

    def close(self):
        with self._lock:
            self._close_locked()

    def _close_locked(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except _ora.Error:
                pass
            self._conn = None

    @property
    def connected(self):
        return self._conn is not None

    # ------------------------------------------------------------------
    # low level helpers
    # ------------------------------------------------------------------
    def query_one(self, sql, params=None):
        """Run a SELECT and return the first row (tuple) or None."""
        with self._lock:
            self.connect()
            cur = self._conn.cursor()
            try:
                cur.execute(sql, params or {})
                return cur.fetchone()
            except _ora.Error as exc:
                raise DatabaseError("%s [SQL: %s]" % (exc, _squash(sql)))
            finally:
                cur.close()

    def query_all(self, sql, params=None):
        """Run a SELECT and return all rows."""
        with self._lock:
            self.connect()
            cur = self._conn.cursor()
            try:
                cur.execute(sql, params or {})
                return cur.fetchall()
            except _ora.Error as exc:
                raise DatabaseError("%s [SQL: %s]" % (exc, _squash(sql)))
            finally:
                cur.close()

    def query_with_columns(self, sql, params=None):
        """Run a SELECT and return (column_names, rows).

        Used by lookup tabs that render arbitrary result sets in a table
        widget: the column list comes from the cursor description so the
        GUI never hard-codes schema information.
        """
        with self._lock:
            self.connect()
            cur = self._conn.cursor()
            try:
                cur.execute(sql, params or {})
                columns = ([d[0] for d in cur.description]
                           if cur.description else [])
                return columns, cur.fetchall()
            except _ora.Error as exc:
                raise DatabaseError("%s [SQL: %s]" % (exc, _squash(sql)))
            finally:
                cur.close()

    def execute(self, sql, params=None):
        """Run a DML statement and commit."""
        with self._lock:
            self.connect()
            cur = self._conn.cursor()
            try:
                cur.execute(sql, params or {})
                self._conn.commit()
                return cur.rowcount
            except _ora.Error as exc:
                self._conn.rollback()
                raise DatabaseError("%s [SQL: %s]" % (exc, _squash(sql)))
            finally:
                cur.close()

    def execute_many_steps(self, steps):
        """Execute a list of (sql, params) in one transaction; commit at end.

        On any error the whole batch is rolled back.
        """
        with self._lock:
            self.connect()
            cur = self._conn.cursor()
            try:
                for sql, params in steps:
                    cur.execute(sql, params or {})
                self._conn.commit()
            except _ora.Error as exc:
                self._conn.rollback()
                raise DatabaseError("%s [SQL: %s]" % (exc, _squash(sql)))
            finally:
                cur.close()

    # ------------------------------------------------------------------
    # account / customer type
    # ------------------------------------------------------------------
    def find_account(self, value):
        """Resolve account id (numeric input) or account number to ACCT_ID."""
        try:
            acct_id = int(value)
        except (TypeError, ValueError):
            acct_id = None
        if acct_id is not None:
            row = self.query_one("SELECT acct_id FROM acct WHERE acct_id = :val",
                                 {"val": acct_id})
            if row:
                return row[0]
        row = self.query_one("SELECT acct_id FROM acct WHERE acct_nbr = :val",
                             {"val": value})
        return row[0] if row else None

    def get_cust_type_code(self, acct_id):
        """Return CUST.CUST_TYPE ('A' massive / 'C' enterprise) or None."""
        row = self.query_one(
            """
            SELECT c.CUST_TYPE
              FROM CUST c
              JOIN ACCT a ON a.CUST_ID = c.CUST_ID
             WHERE a.ACCT_ID = :acct_id
            """,
            {"acct_id": acct_id})
        return row[0] if row else None

    def get_attr_value(self, acct_id):
        """Return ACCT_ATTR_VALUE.ATTR_VALUE for ATTR_ID=907207 or None."""
        row = self.query_one(
            "SELECT ATTR_VALUE FROM ACCT_ATTR_VALUE "
            "WHERE ACCT_ID = :acct AND ATTR_ID = 907207",
            {"acct": acct_id})
        return row[0] if row else None

    def insert_attr_value(self, acct_id, attr_value):
        self.execute(
            """
            INSERT INTO ACCT_ATTR_VALUE
                   (ACCT_ID, ATTR_ID, ATTR_VALUE, EFF_DATE, EXP_DATE,
                    UPDATE_DATE, NEED_UPLOAD, SP_ID, ROUTING_ID, CREATED_DATE)
            VALUES (:acct_id, 907207, :attr_val, SYSDATE-10, NULL,
                    SYSDATE-10, 'N', 101, 1, SYSDATE)
            """,
            {"acct_id": acct_id, "attr_val": attr_value})

    def update_attr_value(self, acct_id, attr_value):
        self.execute(
            "UPDATE ACCT_ATTR_VALUE SET ATTR_VALUE = :attr_val, UPDATE_DATE = SYSDATE "
            "WHERE ACCT_ID = :acct_id AND ATTR_ID = 907207",
            {"attr_val": attr_value, "acct_id": acct_id})

    def resolve_rule_group(self, acct_id, log=None):
        """Determine the DEBIT_RULE_GROUP_ID for an account (spec 4).

        Returns (group_id, attr_value, cust_type_code).
        """
        cust_code = self.get_cust_type_code(acct_id)
        attr_value = self.get_attr_value(acct_id)

        if attr_value == "NON_VIP_HYBRID":
            return 14, attr_value, cust_code
        if cust_code == "A" and attr_value in self.MASSIVE_VALID:
            return 4, attr_value, cust_code
        if cust_code == "C" and attr_value in self.ENT_VALID:
            return 5, attr_value, cust_code
        return 4, attr_value, cust_code

    # ------------------------------------------------------------------
    # rule cache loading (spec 3)
    # ------------------------------------------------------------------
    def load_rule_rows(self):
        """All relevant DEBIT_RULE rows for groups 4/5/14 with parent links."""
        return self.query_all(
            """
            SELECT r.DEBIT_RULE_ID, r.DEBIT_RULE_GROUP_ID, r.PARENT_RULE_ID,
                   r.RULE_NAME, r.COMMENTS
              FROM DEBIT_RULE r
             WHERE r.DEBIT_RULE_GROUP_ID IN (4, 5, 14)
               AND UPPER(r.RULE_NAME) LIKE '%LEVEL%'
               AND r.STATE = 'A'
             ORDER BY r.DEBIT_RULE_GROUP_ID, r.DEBIT_RULE_ID
            """)

    def load_rule_action_rows(self):
        """All DEBIT_RULE_ACTION rows keyed by DEBIT_RULE_ID."""
        return self.query_all(
            """
            SELECT a.DEBIT_RULE_ID, a.SEQ, a.DEBIT_ACTION_TYPE, a.NAME
              FROM DEBIT_RULE_ACTION a
             ORDER BY a.DEBIT_RULE_ID, a.SEQ
            """)

    def get_parent_rule_id(self, rule_id):
        row = self.query_one(
            "SELECT PARENT_RULE_ID FROM DEBIT_RULE WHERE DEBIT_RULE_ID = :rid",
            {"rid": rule_id})
        return row[0] if row else None

    # ------------------------------------------------------------------
    # initial setup
    # ------------------------------------------------------------------
    def get_server_info(self):
        row = self.query_one(
            "SELECT SYS_CONTEXT('USERENV','SERVER_HOST'), "
            "SYS_CONTEXT('USERENV','IP_ADDRESS') FROM DUAL")
        return row  # (host, ip) or None

    def has_debt(self, acct_id):
        row = self.query_one(
            "SELECT 1 FROM ACCT_ITEM WHERE ACCT_ID = :acct AND STATE='C' "
            "AND ROWNUM = 1", {"acct": acct_id})
        return row is not None

    def get_latest_billing_cycle(self, acct_id):
        row = self.query_one(
            "SELECT max(BILLING_CYCLE_ID) FROM ACCT_ITEM "
            "WHERE ACCT_ID = :acct AND STATE='C'", {"acct": acct_id})
        return row[0] if row else None

    def get_billing_cycle_state(self, bc_id):
        row = self.query_one(
            "SELECT STATE FROM BILLING_CYCLE WHERE BILLING_CYCLE_ID = :bc",
            {"bc": bc_id})
        return row[0] if row else None

    def get_billing_cycle_debt_date(self, bc_id):
        """Return BILLING_CYCLE.DEBT_DATE for the cycle or None."""
        row = self.query_one(
            "SELECT DEBT_DATE FROM BILLING_CYCLE WHERE BILLING_CYCLE_ID = :bc",
            {"bc": bc_id})
        return row[0] if row else None

    def set_billing_cycle_debt(self, bc_id, days_back=3):
        return self.execute(
            "UPDATE BILLING_CYCLE SET STATE='C', DEBT_DATE = SYSDATE - :days "
            "WHERE BILLING_CYCLE_ID = :bc",
            {"days": days_back, "bc": bc_id})

    def has_active_autopay(self, acct_id):
        row = self.query_one(
            "SELECT 1 FROM POST_AUTO_PAY_SIGN WHERE ACCT_ID = :acct "
            "AND STATE='A' AND ROWNUM = 1", {"acct": acct_id})
        return row is not None

    def disable_autopay(self, acct_id):
        return self.execute(
            "UPDATE POST_AUTO_PAY_SIGN SET STATE='X' "
            "WHERE ACCT_ID = :acct AND STATE='A'", {"acct": acct_id})

    def prepare_tmp_dunning(self, acct_id):
        """Create-or-truncate TMP_DUNNING and insert the account id."""
        with self._lock:
            self.connect()
            cur = self._conn.cursor()
            try:
                try:
                    cur.execute("TRUNCATE TABLE TMP_DUNNING")
                except _ora.Error:
                    self._conn.rollback()
                    cur.execute("CREATE TABLE TMP_DUNNING (ACCT_ID NUMBER)")
                cur.execute("INSERT INTO TMP_DUNNING (ACCT_ID) VALUES (:acct)",
                            {"acct": acct_id})
                self._conn.commit()
            except _ora.Error as exc:
                self._conn.rollback()
                raise DatabaseError(str(exc))
            finally:
                cur.close()

    def update_config_item_param(self):
        return self.execute(
            """
            UPDATE config_item_param
               SET PARAM_VALUE = 'SELECT ACCT_ID FROM TMP_DUNNING'
             WHERE CONFIG_ITEM_ID IN (46, 234)
               AND param_code = 'DEBIT_DEAL_SEARCH_SQL'
            """)

    # ------------------------------------------------------------------
    # overdue instance handling
    # ------------------------------------------------------------------
    def get_overdue_inst(self, acct_id):
        row = self.query_one(
            "SELECT INST_ID, DUE_DATE FROM debit_acct_overdue_inst "
            "WHERE acct_id = :acct AND STATE='A'", {"acct": acct_id})
        return (row[0], row[1]) if row else (None, None)

    def close_active_overdue_inst(self, acct_id):
        return self.execute(
            "UPDATE debit_acct_overdue_inst SET STATE='C' "
            "WHERE acct_id = :acct AND STATE='A'", {"acct": acct_id})

    def set_billing_cycle_debt_date(self, bc_id, target_date):
        return self.execute(
            "UPDATE BILLING_CYCLE SET DEBT_DATE = TO_DATE(:dt,'YYYY-MM-DD HH24:MI:SS') "
            "WHERE BILLING_CYCLE_ID = :bc",
            {"dt": target_date.strftime("%Y-%m-%d %H:%M:%S"), "bc": bc_id})

    def set_inst_due_date(self, inst_id, target_date):
        return self.execute(
            "UPDATE debit_acct_overdue_inst "
            "SET DUE_DATE = TO_DATE(:dt,'YYYY-MM-DD HH24:MI:SS') WHERE INST_ID = :inst",
            {"dt": target_date.strftime("%Y-%m-%d %H:%M:%S"), "inst": inst_id})

    def verify_rule_action(self, inst_id, rule_id):
        row = self.query_one(
            "SELECT DEBIT_RULE_ID, DEBIT_ACTION_ID "
            "FROM debit_acct_overdue_rela_action "
            "WHERE INST_ID = :inst AND DEBIT_RULE_ID = :rule_id",
            {"inst": inst_id, "rule_id": rule_id})
        return row[1] if row else None

    def get_current_max_rule_id(self, inst_id):
        row = self.query_one(
            "SELECT MAX(DEBIT_RULE_ID) FROM debit_acct_overdue_rela_action "
            "WHERE INST_ID = :inst", {"inst": inst_id})
        return row[0] if row else None

    def advance_debit_action_sched_time(self, action_id):
        return self.execute(
            "UPDATE debit_action SET sched_time = SYSDATE - 1 "
            "WHERE debit_action_id = :act", {"act": action_id})

    def get_exec_time(self, inst_id):
        row = self.query_one(
            "SELECT T.EXEC_TIME FROM debit_acct_overdue_rela_action T "
            "WHERE T.INST_ID = :inst AND T.EXEC_TIME IS NOT NULL "
            "AND ROWNUM = 1", {"inst": inst_id})
        return row[0] if row else None

    def get_action_his_state(self, action_id):
        """Optional check on DEBIT_ACTION_HIS.STATE for an executed action."""
        row = self.query_one(
            "SELECT STATE FROM debit_action_his WHERE DEBIT_ACTION_ID = :act",
            {"act": action_id})
        return row[0] if row else None

    def get_action_his_error(self, inst_id):
        """Return the latest ERROR_MSG from debit_rule_action_inst_his."""
        row = self.query_one(
            """
            SELECT ERROR_MSG FROM debit_rule_action_inst_his
             WHERE INST_ID = :inst AND ERROR_MSG IS NOT NULL
               AND ROWNUM = 1
            """,
            {"inst": inst_id})
        return row[0] if row else None

    # ------------------------------------------------------------------
    # billing cycle restore (spec 7)
    # ------------------------------------------------------------------
    LEVEL0_RULE_IDS = (14, 31, 97)  # groups 4, 5, 14

    def get_cycle_end_date(self, bc_id):
        row = self.query_one(
            "SELECT CYCLE_END_DATE FROM BILLING_CYCLE WHERE BILLING_CYCLE_ID = :bc",
            {"bc": bc_id})
        return row[0] if row else None

    def set_cycle_end_date_sysdate_minus(self, bc_id, days=1):
        return self.execute(
            "UPDATE BILLING_CYCLE SET CYCLE_END_DATE = SYSDATE - :days "
            "WHERE BILLING_CYCLE_ID = :bc", {"days": days, "bc": bc_id})

    def set_cycle_end_date(self, bc_id, target_date):
        """Write an absolute CYCLE_END_DATE (Level-0 window precondition)."""
        return self.execute(
            "UPDATE BILLING_CYCLE SET CYCLE_END_DATE = "
            "TO_DATE(:dt,'YYYY-MM-DD HH24:MI:SS') "
            "WHERE BILLING_CYCLE_ID = :bc",
            {"dt": target_date.strftime("%Y-%m-%d %H:%M:%S"), "bc": bc_id})

    def restore_cycle_end_date(self, bc_id, original_date):
        return self.execute(
            "UPDATE BILLING_CYCLE SET CYCLE_END_DATE = :orig "
            "WHERE BILLING_CYCLE_ID = :bc",
            {"orig": original_date, "bc": bc_id})

    def set_billing_cycle_state(self, bc_id, state):
        """Set BILLING_CYCLE.STATE ('A' active / 'C' closed / 'B' billing)."""
        return self.execute(
            "UPDATE BILLING_CYCLE SET STATE = :st WHERE BILLING_CYCLE_ID = :bc",
            {"st": state, "bc": bc_id})


def _squash(sql):
    """Collapse whitespace in SQL so error messages stay on one line."""
    return " ".join(str(sql).split())
