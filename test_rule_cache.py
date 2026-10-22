# -*- coding: utf-8 -*-
"""
test_rule_cache.py - offline validation of RuleCache against the CSV exports.

Simulates the DB rows from DEBIT_RULE.csv / DEBIT_RULE_ACTION.csv and checks:
  * group 4 / 5 / 14 level lists match the spec,
  * '.1' / 'manual action' sub-levels are excluded,
  * rules without actions are excluded,
  * offset parsing handles 'before' / '+n' / 'after n' / fallback.
"""

import csv
import sys

sys.path.insert(0, ".")

from dunning_tool.rule_cache import RuleCache, parse_offset_days  # noqa: E402


class FakeDB:
    """Returns the CSV rows exactly as the Oracle query would."""

    def load_rule_rows(self):
        rows = []
        with open("DEBIT_RULE.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append((
                    int(r["DEBIT_RULE_ID"]),
                    int(r["DEBIT_RULE_GROUP_ID"]),
                    int(r["PARENT_RULE_ID"]) if r["PARENT_RULE_ID"] else None,
                    r["RULE_NAME"],
                    r["COMMENTS"],
                ))
        # mimic ORDER BY group_id, rule_id
        rows.sort(key=lambda x: (x[1], x[0]))
        return rows

    def load_rule_action_rows(self):
        rows = []
        with open("DEBIT_RULE_ACTION.csv", newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                rows.append((
                    int(r["DEBIT_RULE_ID"]),
                    int(r["SEQ"]),
                    int(r["DEBIT_ACTION_TYPE"]),
                    r["NAME"],
                ))
        rows.sort(key=lambda x: (x[0], x[1]))
        return rows


def main():
    logs = []
    cache = RuleCache(FakeDB(), log=logs.append).load()

    failures = []

    def check(name, actual, expected):
        if actual != expected:
            failures.append("%s\n  expected: %s\n  actual:   %s"
                            % (name, expected, actual))
        else:
            print("PASS  %s" % name)

    # ---- group 4 (MASSIVE) ------------------------------------------
    g4 = [(lv.rule_id, lv.name, lv.offset_days, lv.seq)
          for lv in cache.levels_for_group(4)]
    check("group4 ids", [x[0] for x in g4], [14, 15, 17, 18, 19, 21, 23, 25, 26, 27])
    check("group4 offsets", [x[2] for x in g4],
          [-5, 1, 10, 20, 30, 40, 45, 60, 95, 105])
    check("group4 seqs", [x[3] for x in g4], list(range(10)))

    # 28 (Post Termination Notification) has NO actions -> excluded
    check("rule28 excluded (no actions)", cache.get_by_rule_id(28), None)
    # 82/86/87/88 are '.1' / 'manual action' sub-levels -> excluded
    for rid in (82, 86, 87, 88):
        check("rule%d excluded (sub-level)" % rid, cache.get_by_rule_id(rid), None)

    # ---- group 5 (ENTERPRISE) ----------------------------------------
    # rule 31: name says 'before 25 days', comments say '5 days before' -
    # the NAME is authoritative (legacy config window is [0, 25]).
    g5 = [(lv.rule_id, lv.offset_days) for lv in cache.levels_for_group(5)]
    check("group5 ids", [x[0] for x in g5], [31, 32, 34, 35, 37, 40])
    check("group5 offsets", [x[1] for x in g5], [-25, 1, 20, 30, 80, 105])

    # ---- group 14 (HYBRID) -------------------------------------------
    # HYBRID rules have NO comments - offsets must come from RULE_NAME.
    g14 = [(lv.rule_id, lv.offset_days) for lv in cache.levels_for_group(14)]
    check("group14 ids", [x[0] for x in g14], [106, 113, 114])
    check("group14 offsets from name", [x[1] for x in g14], [31, 53, 60])

    # ---- offset parser unit cases -------------------------------------
    cases = [
        ("25(5 days before Payment Due Date)", None, -5),
        ("60(Payment Due Date + 30 days)", None, 30),
        ("Next BC(Payment Due Date + 1 day)", None, 1),
        ("7 days before Payment Due Date", None, -7),
        ("Payment Due Date + 10 days", None, 10),
        ("MASS MARKET V2", 21, 21),          # fallback to OWE_DAYS
        ("send Sms", None, 0),               # unparseable -> default
        ("", None, 0),
    ]
    for text, owe, want in cases:
        got = parse_offset_days(text, owe_days=owe)
        check("parse %r (owe=%s)" % (text, owe), got, want)

    # ---- labels --------------------------------------------------------
    lv14 = cache.get_by_rule_id(14)
    check("label rule14",
          "Level 0 -before 5 days [Rule 14, -5 d]" == lv14.label, True)
    lv23 = cache.get_by_rule_id(23)
    check("label rule23",
          "Level 6-after 45 days-CTOS Blacklist [Rule 23, +45 d]" == lv23.label, True)

    # ---- engine DEBT_DATE / DUE_DATE sign convention --------------------
    # The dunning job matches overdue_days = SYSDATE - DEBT_DATE against the
    # rule windows, so the engine must set DEBT_DATE = SYSDATE - offset_days:
    #   'after 30 days' (+30) -> 30 days in the PAST   (looks overdue)
    #   'before 5 days' (-5)  ->  5 days in the FUTURE (not yet due)
    from datetime import datetime, timedelta

    from dunning_tool.engine import DunningEngine  # noqa: E402

    class StubDB:
        def __init__(self):
            self.debt_date = None
            self.due_date = None
            self.debt_writes = 0

        def close_active_overdue_inst(self, acct_id):
            return 0

        def set_billing_cycle_debt_date(self, bc_id, target_date):
            self.debt_writes += 1
            self.debt_date = target_date

        def set_inst_due_date(self, inst_id, target_date):
            self.due_date = target_date

        def get_billing_cycle_state(self, bc_id):
            return "C"

        def get_billing_cycle_debt_date(self, bc_id):
            return None          # None -> guard re-writes the L0 future date

        def get_cycle_end_date(self, bc_id):
            return None

        def set_cycle_end_date_sysdate_minus(self, bc_id, days=1):
            self.cycle_end = datetime.now() - timedelta(days=days)

    class NullAPI:
        def trigger_debit_action_job(self):
            return True

    cfg = {"db": {}, "ssh": {}, "api": {}, "general": {"poll_interval": 0,
                                                       "max_wait": 0}}
    eng = DunningEngine(cfg, log=lambda m: None, tr=lambda s, **k: s.format(**k))
    stub = StubDB()
    eng.db = stub
    eng.api = NullAPI()
    eng.user_acct = 1
    eng.user_bc = 2954

    before = datetime.now()
    eng.regenerate_overdue_inst_for_level(cache.get_by_rule_id(19))  # +30 d
    delta = stub.debt_date - before          # ~ -30 days
    check("rule19 DEBT_DATE ~30d in the past",
          timedelta(days=-30) <= delta <= timedelta(days=-30, seconds=90), True)

    before = datetime.now()
    eng.regenerate_overdue_inst_for_level(cache.get_by_rule_id(14))  # -5 d
    delta = stub.debt_date - before
    check("rule14 DEBT_DATE ~5d in the future",
          timedelta(days=5, seconds=90) >= delta >= timedelta(days=5), True)

    eng.update_inst_due_date_and_recalc(123, cache.get_by_rule_id(19))
    delta = stub.due_date - before           # ~ -30 days
    check("rule19 DUE_DATE ~30d in the past",
          timedelta(days=-30) <= delta <= timedelta(days=-30, seconds=90), True)

    # ---- guard: non-Level-0 DEBT_DATE must be strictly earlier than NOW --
    class ZeroOffsetLevel:
        """Simulates a mis-parsed offset of 0 (e.g. unparseable rule text)."""
        rule_id = 999
        seq = 2
        offset_days = 0
        label = "Broken Level [Rule 999, +0 d]"

    before = datetime.now()
    guarded = eng._debt_date_for_level(ZeroOffsetLevel())
    delta = guarded - before
    check("offset=0 non-L0 clamped to SYSDATE-1",
          timedelta(days=-1) <= delta < timedelta(0), True)

    # internal rebuild (reset path) must NOT touch DEBT_DATE at all
    writes_before = stub.debt_writes
    eng.regenerate_overdue_inst_for_level(cache.get_by_rule_id(14),
                                          update_debt_date=False)
    check("internal rebuild leaves DEBT_DATE untouched",
          (stub.debt_writes, stub.debt_date), (writes_before, stub.debt_date))

    # ---- prerequisite chain must walk THROUGH excluded sub-levels ----------
    # real DB chain: 23 <- 21 <- 86('Level 4.1 manual action', EXCLUDED)
    #                <- 19 <- 15 <- 14.  When rule 21 has no action yet, the
    # walk must skip the excluded 86 via PARENT_RULE_ID and execute 19.
    class ChainStubDB(StubDB):
        parents = {"23": "21", "21": "86", "86": "19", "19": "15", "15": "14"}

        def get_parent_rule_id(self, rule_id):
            return self.parents.get(str(rule_id))

        def verify_rule_action(self, inst_id, rule_id):
            return {"21": None, "86": None, "19": 555}.get(str(rule_id))

    chain_db = ChainStubDB()
    eng.db = chain_db
    eng._execute_action = lambda action_id, rule_id: None
    eng._sleep = lambda s: None
    triggered = []
    eng.api.trigger_debit_action_job = lambda: triggered.append(1)
    ok = eng._run_prerequisite_chain(1, cache.get_by_rule_id(23))
    check("prereq chain skips excluded rule 86, executes rule 19",
          (ok, len(triggered)), (True, 1))

    # ---- STATE must be forced to 'C' before every instance generation ------
    class GenStubDB(StubDB):
        """Cycle stuck at 'A' (post-cleanup) like the failing Level-6 run."""

        def __init__(self):
            StubDB.__init__(self)
            self.state = "A"
            self.state_writes = []
            self.closed = False
            self.calls = []          # ordered record of DB operations

        def get_billing_cycle_state(self, bc_id):
            self.calls.append(("get_state",))
            return self.state

        def set_billing_cycle_state(self, bc_id, state):
            self.state_writes.append(state)
            self.state = state

        def close_active_overdue_inst(self, acct_id):
            self.closed = True
            self.calls.append(("close",))

        def set_billing_cycle_debt_date(self, bc_id, d):
            self.debt_writes += 1
            self.calls.append(("debt", d))

    gen_db = GenStubDB()
    eng.db = gen_db
    eng.user_bc = 2965
    made_instances = []
    eng.wait_for_overdue_inst = lambda timeout=None, interval=None: \
        (made_instances.append(1) or (111, None))

    eng.regenerate_overdue_inst_for_level(cache.get_by_rule_id(19),
                                          update_debt_date=False)
    check("rebuild forces STATE 'A'->'C' before closing instances",
          (gen_db.state, gen_db.closed), ("C", True))
    check("rebuild does not write DEBT_DATE on internal path",
          gen_db.debt_writes, 0)
    # 'get_state' then 'close' order proves the state fix happens FIRST
    first_two = [c[0] for c in gen_db.calls[:2]]
    check("state check precedes instance close",
          first_two, ["get_state", "close"])

    class L0Level:
        rule_id = 14
        seq = 0
        offset_days = -5
        label = "L0"

    before = datetime.now()
    l0_date = eng._debt_date_for_level(L0Level())
    delta = l0_date - before
    check("L0 keeps future DEBT_DATE (no clamp)",
          timedelta(days=5) - timedelta(seconds=1) < delta < timedelta(days=5, seconds=5),
          True)

    # ---- spec 7: STATE re-derivation runs after EVERY simulation --------
    # _restore_billing_cycle must always re-derive STATE from CYCLE_END_DATE
    # (end > sysdate -> 'A' else 'C'), even when CYCLE_END_DATE was never
    # shifted (non-Level-0 runs must not skip the STATE fix-up).
    class RestoreStubDB(StubDB):
        def __init__(self, end_date):
            StubDB.__init__(self)
            self.cycle_end_date = end_date
            self.state_set = None
            self.restored_to = None

        def get_cycle_end_date(self, bc_id):
            return self.cycle_end_date

        def restore_cycle_end_date(self, bc_id, original_date):
            self.restored_to = original_date
            return 1

        def set_billing_cycle_state(self, bc_id, state):
            self.state_set = state
            return 1

    eng.restore_wait = 0
    eng._sleep = lambda s: None            # no real waiting in tests

    # case 1: non-Level-0 rule, end date in the FUTURE -> STATE must go 'A'
    s1 = RestoreStubDB(datetime.now() + timedelta(days=10))
    eng.db = s1
    eng._restore_billing_cycle(None)       # no CYCLE_END_DATE shift happened
    check("non-L0 run, future end date -> STATE='A'", s1.state_set, "A")
    check("non-L0 run, CYCLE_END_DATE untouched", s1.restored_to, None)

    # case 2: non-Level-0 rule, end date in the PAST -> STATE must go 'C'
    s2 = RestoreStubDB(datetime.now() - timedelta(days=10))
    eng.db = s2
    eng._restore_billing_cycle(None)
    check("non-L0 run, past end date -> STATE='C'", s2.state_set, "C")

    # case 3: Level-0 run, original end date restored first, then STATE='A'
    s3 = RestoreStubDB(datetime.now() + timedelta(days=10))
    eng.db = s3
    eng._restore_billing_cycle(datetime.now() + timedelta(days=10))
    check("L0 run restores CYCLE_END_DATE then STATE='A'",
          (s3.restored_to is not None, s3.state_set), (True, "A"))

    # ---- Level-0 window: held for the WHOLE simulation -------------------
    # Refinement: DEBT_DATE>SYSDATE and CYCLE_END_DATE<SYSDATE must be in
    # place BEFORE the first curl and stay until the finally-restore.
    class L0WindowStubDB:
        """Tracks BILLING_CYCLE mutations + trigger order for an L0 run."""

        def __init__(self):
            self.state = "A"                       # post-cleanup, worst case
            self.debt_date = datetime.now() - timedelta(days=3)   # past!
            self.cycle_end = datetime.now() + timedelta(days=30)  # future!
            self.events = []                       # ordered op log
            self.original_end_saved = None

        # -- reads
        def get_billing_cycle_state(self, bc):
            return self.state

        def get_billing_cycle_debt_date(self, bc):
            return self.debt_date

        def get_cycle_end_date(self, bc):
            return self.cycle_end

        # -- writes
        def set_billing_cycle_state(self, bc, st):
            self.state = st
            self.events.append(("state", st))

        def set_billing_cycle_debt_date(self, bc, d):
            self.debt_date = d
            self.events.append(("debt", d))

        def set_cycle_end_date_sysdate_minus(self, bc, days=1):
            self.cycle_end = datetime.now() - timedelta(days=days)
            self.events.append(("end_minus", days))

        def restore_cycle_end_date(self, bc, d):
            self.cycle_end = d
            self.events.append(("end_restore", d))

        # -- instance flow (single happy path)
        def get_overdue_inst(self, acct):
            return (None, None)

        def close_active_overdue_inst(self, acct):
            self.events.append(("close",))
            return 0

        def verify_rule_action(self, inst, rule):
            self.events.append(("verify", rule))
            return 777 if rule == 14 else None

        def advance_debit_action_sched_time(self, act):
            self.events.append(("sched", act))
            return 1

        def get_exec_time(self, inst):
            return datetime.now()

        def get_action_his_state(self, act):
            return "S"

        def get_action_his_error(self, inst):
            return None

    l0_db = L0WindowStubDB()

    class OrderedAPI:
        def __init__(self, db):
            self.db = db
            self.n_job = 0
            self.n_deal = 0

        def trigger_debit_action_job(self):
            self.db.events.append(("curl_job", self.n_job))
            self.n_job += 1

        def trigger_debit_action_deal_job(self):
            self.db.events.append(("curl_deal", self.n_deal))
            self.n_deal += 1

    api2 = OrderedAPI(l0_db)
    eng.db = l0_db
    eng.api = api2
    eng.user_acct = 123456
    eng.user_bc = 2954
    eng._sleep = lambda s: None
    eng.wait_for_overdue_inst = lambda timeout=None, interval=None: (999, None)

    l0 = cache.get_by_rule_id(14)                # MASSIVE Level 0, offset -5
    result = eng.run_simulation(l0)

    # window must exist before the FIRST curl: find first curl index
    first_curl = next(i for i, e in enumerate(l0_db.events)
                      if str(e[0]).startswith("curl_"))
    before_curl = [e[0] for e in l0_db.events[:first_curl]]
    check("L0: STATE forced to 'C' before first curl",
          "state" in before_curl, True)
    check("L0: future DEBT_DATE written before first curl",
          "debt" in before_curl, True)
    check("L0: CYCLE_END_DATE shifted past before first curl",
          "end_minus" in before_curl, True)

    # window conditions themselves
    debt_written = [e[1] for e in l0_db.events if e[0] == "debt"]
    check("L0: DEBT_DATE written is in the FUTURE (>SYSDATE)",
          debt_written and debt_written[0] > datetime.now() - timedelta(seconds=5),
          True)
    check("L0: CYCLE_END_DATE finally restored",
          any(e[0] == "end_restore" for e in l0_db.events), True)
    check("L0: run succeeded", result.get("ok"), True)

    # after the finally-restore the cycle is back: end>SYSDATE -> STATE 'A'
    check("L0: cleanup re-derives STATE='A' after restore",
          l0_db.state, "A")

    # ---- window guard unit checks: each violated condition is fixed --------
    class DriftedDB(L0WindowStubDB):
        """All three conditions violated simultaneously."""

        def __init__(self):
            L0WindowStubDB.__init__(self)
            self.state = "A"
            self.debt_date = datetime.now() - timedelta(days=1)
            self.cycle_end = datetime.now() + timedelta(days=1)

    d = DriftedDB()
    eng.db = d
    eng._l0_cycle_end_shifted = False
    eng._ensure_level0_window(l0)
    check("guard fixes STATE to 'C'", d.state, "C")
    check("guard fixes DEBT_DATE to future", d.debt_date > datetime.now(), True)
    check("guard fixes CYCLE_END_DATE to past",
          d.cycle_end < datetime.now(), True)

    # non-L0 levels must NOT get the window guard (their DEBT_DATE is past)
    d2 = DriftedDB()
    eng.db = d2
    eng.regenerate_overdue_inst_for_level(cache.get_by_rule_id(19),
                                          update_debt_date=True)
    check("non-L0 rebuild keeps DEBT_DATE in the past",
          d2.debt_date < datetime.now(), True)

    print()
    if failures:
        print("FAILURES (%d):" % len(failures))
        for f in failures:
            print(f)
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
