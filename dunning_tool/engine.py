# -*- coding: utf-8 -*-
"""
engine.py - DunningEngine: core business logic (specs 4-7).

Owns the full workflow and coordinates DatabaseManager / SSHManager /
APIManager / RuleCache.  Every method takes a `tr` callable so log messages
are localised; the engine itself never imports tkinter.
"""

import time
import traceback
from datetime import datetime, timedelta

from .db_manager import DatabaseManager
from .ssh_manager import SSHManager
from .api_manager import APIManager
from .rule_cache import RuleCache, GROUP_LABELS


class DunningError(Exception):
    """Business level failure with a user-friendly message."""


class DunningEngine:
    def __init__(self, config, log, tr):
        """
        config -- loaded config.json dict
        log    -- callable(str) for the GUI log area
        tr     -- callable(text, **kwargs) translator
        """
        self.config = config
        self.log = log
        self.tr = tr

        self.db = DatabaseManager(config["db"])
        self.ssh = SSHManager(config["ssh"], log=log, tr=tr)
        self.api = APIManager(config["api"], log=log, tr=tr)
        self.rules = RuleCache(self.db, log=self._log_rule_cache)

        g = config["general"]
        self.poll_interval = int(g.get("poll_interval", 3))
        self.max_wait = int(g.get("max_wait", 60))
        self.b_state_retries = int(g.get("b_state_retries", 3))
        self.b_state_interval = int(g.get("b_state_interval", 10))
        self.post_trigger_wait = int(g.get("post_trigger_wait", 10))
        self.restore_wait = int(g.get("restore_wait", 5))
        # settle pause between successive table updates / API triggers so the
        # jobserver and DB never see back-to-back writes (refinement: ~3-5 s)
        self.settle_wait = float(g.get("settle_wait", 4))

        # session state
        self.user_acct = None
        self.user_bc = None
        self.group_id = None
        self.attr_value = None
        self.cust_code = None
        self.inst_id = None
        # true while a Level-0 run holds CYCLE_END_DATE shifted to
        # SYSDATE-1 so cleanup knows it must restore the original value
        self._l0_cycle_end_shifted = False

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _log_rule_cache(self, msg):
        """RuleCache logs i18n keys already resolved for the current lang."""
        self.log(msg)

    def _sleep(self, seconds):
        time.sleep(float(seconds))

    def _fmt(self, dt):
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    # ------------------------------------------------------------------
    # startup / teardown
    # ------------------------------------------------------------------
    def start(self):
        """Connect DB and load the rule cache. Raises on failure."""
        self.db.connect()
        self.log(self.tr("Database connection successful."))
        self.rules.load()

    def close(self):
        self.ssh.close()
        self.db.close()
        self.log(self.tr("DB connection closed."))

    def reload_rules(self):
        self.rules.load()

    # ------------------------------------------------------------------
    # account handling (spec 4)
    # ------------------------------------------------------------------
    def get_account(self, value):
        """Resolve the account, detect its rule group, refresh levels."""
        acct_id = self.db.find_account(value)
        if acct_id is None:
            raise DunningError(self.tr("Account not found."))

        group_id, attr_value, cust_code = self.db.resolve_rule_group(acct_id)
        if cust_code not in ("A", "C"):
            if cust_code is None:
                self.log(self.tr("No CUST_TYPE record found, treating as MASSIVE."))
            else:
                self.log(self.tr("Unknown CUST_TYPE code [{code}], treating as MASSIVE.",
                                 code=cust_code))

        self.user_acct = acct_id
        self.group_id = group_id
        self.attr_value = attr_value
        self.cust_code = cust_code
        self.inst_id = None
        self.user_bc = None

        label = GROUP_LABELS.get(group_id, str(group_id))
        self.log(self.tr("Found USER_ACCT: {acct}, customer type: {type}",
                         acct=acct_id, type=label))
        self.log(self.tr("Rule group resolved to {group} (attr={attr}, cust_type={ctype})",
                         group=group_id, attr=attr_value, ctype=cust_code))
        return acct_id

    @property
    def group_label(self):
        return GROUP_LABELS.get(self.group_id, str(self.group_id))

    def levels(self):
        """Selectable levels for the current rule group."""
        if self.group_id is None:
            return []
        return self.rules.levels_for_group(self.group_id)

    # ------------------------------------------------------------------
    # Level-0 window management (refinement: keep the Level-0 conditions
    # DEBT_DATE > SYSDATE and CYCLE_END_DATE < SYSDATE in place for the
    # WHOLE simulation, not just around the final action execution)
    # ------------------------------------------------------------------
    def _open_level0_window(self, level):
        """Create the Level-0 conditions BEFORE any curl/trigger runs.

        1. DEBT_DATE = SYSDATE - offset  (Level 0 has a negative offset,
           so the date lands in the FUTURE: the account is "not yet due",
           which is exactly the Level-0 rule window).
        2. CYCLE_END_DATE = SYSDATE - 1  (shifted back so the cycle looks
           closed; restored by _restore_billing_cycle at the end).
        Both writes settle before the caller continues.
        """
        t = self.tr
        target_date = self._debt_date_for_level(level)
        self.db.set_billing_cycle_debt_date(self.user_bc, target_date)
        self.log(t("[Level 0] DEBT_DATE set to {date} (SYSDATE - offset) "
                   "before any job trigger", date=self._fmt(target_date)))
        self._sleep(self.settle_wait)

        self._l0_cycle_end_shifted = True
        self.db.set_cycle_end_date_sysdate_minus(self.user_bc, days=1)
        self.log(t("[Level 0] CYCLE_END_DATE set to SYSDATE - 1 "
                   "(held for the whole simulation)"))
        self._sleep(self.settle_wait)

    def _ensure_level0_window(self, level):
        """Re-assert the Level-0 window before EVERY curl/trigger.

        A previous run's cleanup or another job may have flipped STATE
        back to 'A' or nudged DEBT_DATE/CYCLE_END_DATE.  Because the
        DebitActionJob that (re)generates instances reads those columns,
        each trigger site calls this first so the account is guaranteed
        to sit inside the Level-0 window at the moment the job runs.
        """
        t = self.tr
        changed = False

        # (a) STATE='C' is required for DebitActionJob to pick up the cycle
        state = self.db.get_billing_cycle_state(self.user_bc)
        if state != "C":
            self.db.set_billing_cycle_state(self.user_bc, "C")
            self.log(t("[Level 0] BILLING_CYCLE.STATE was '{state}', "
                       "forced to 'C'.", state=state))
            changed = True

        # (b) DEBT_DATE must be > SYSDATE (future) for the Level-0 window
        debt = self.db.get_billing_cycle_debt_date(self.user_bc)
        if debt is None or debt <= datetime.now():
            target_date = self._debt_date_for_level(level)
            self.db.set_billing_cycle_debt_date(self.user_bc, target_date)
            self.log(t("[Level 0] DEBT_DATE ({date}) was not later than "
                       "SYSDATE, re-set to {target}",
                       date=self._fmt(debt) if debt else "NULL",
                       target=self._fmt(target_date)))
            changed = True

        # (c) CYCLE_END_DATE must be < SYSDATE (looks like a closed cycle)
        end = self.db.get_cycle_end_date(self.user_bc)
        if end is None or end >= datetime.now():
            self._l0_cycle_end_shifted = True
            self.db.set_cycle_end_date_sysdate_minus(self.user_bc, days=1)
            self.log(t("[Level 0] CYCLE_END_DATE ({date}) was not earlier "
                       "than SYSDATE, re-set to SYSDATE - 1",
                       date=self._fmt(end) if end else "NULL"))
            changed = True

        if changed:
            self._sleep(self.settle_wait)

    # ------------------------------------------------------------------
    # initial setup (spec 5)
    # ------------------------------------------------------------------
    def run_initial_setup(self):
        if self.user_acct is None:
            raise DunningError(self.tr("Please get account first."))

        t = self.tr
        group_label = self.group_label

        self.log("\n================ %s ================" % t(
            "Starting initial setup for [{type}]", type=group_label))

        info = self.db.get_server_info()
        if info:
            self.log(t("Current host: {host}, IP: {ip}", host=info[0], ip=info[1]))

        # -- 1. attribute check / fix ------------------------------------
        current = self.db.get_attr_value(self.user_acct)
        if self.group_id == 5:
            valid, default = self.db.ENT_VALID, self.db.ENT_DEFAULT
        else:
            valid, default = self.db.MASSIVE_VALID, self.db.MASSIVE_DEFAULT

        if current is None:
            self.log(t("Account missing ATTR_ID=907207, inserting default: {val}",
                       val=default))
            self.db.insert_attr_value(self.user_acct, default)
            self.log(t("Attribute inserted successfully."))
            self.attr_value = default
        elif current == "NON_VIP_HYBRID" or current in valid:
            self.log(t("Account already has valid attribute value [{val}], no change needed.",
                       val=current))
            self.attr_value = current
        else:
            self.log(t("Attribute value [{val}] not in valid list {list}, updating to default: {default}",
                       val=current, list=list(valid), default=default))
            self.db.update_attr_value(self.user_acct, default)
            self.log(t("Attribute updated successfully."))
            self.attr_value = default
            # group may change after the fix (e.g. attr now matches C list)
            self.group_id, self.attr_value, self.cust_code = \
                self.db.resolve_rule_group(self.user_acct)

        # -- 2. debt check ------------------------------------------------
        if not self.db.has_debt(self.user_acct):
            self.log(t("Error: Account has no debt, please perform debit adjustment."))
            raise DunningError(t("Account has no debt, please perform debit adjustment."))
        self.log(t("Debt check passed."))

        # -- 3. billing cycle ---------------------------------------------
        bc = self.db.get_latest_billing_cycle(self.user_acct)
        if bc is None:
            self.log(t("Error: No billing cycle found."))
            raise DunningError(t("No billing cycle found."))
        self.user_bc = bc
        self.log(t("Found USER_BC: {bc}", bc=bc))

        for attempt in range(1, self.b_state_retries + 1):
            state = self.db.get_billing_cycle_state(self.user_bc)
            if state == "B":
                if attempt < self.b_state_retries:
                    self.log(t("Billing Cycle state is 'B' (billing in progress), retry in {interval} seconds... (attempt {attempt}/{max})",
                               interval=self.b_state_interval, attempt=attempt,
                               max=self.b_state_retries))
                    self._sleep(self.b_state_interval)
                else:
                    msg = t("Billing Cycle still in 'B' state after {max} checks, aborting setup.",
                            max=self.b_state_retries)
                    self.log(msg)
                    raise DunningError(msg)
            else:
                self.log(t("Billing Cycle state is not 'B', proceeding."))
                break

        self.db.set_billing_cycle_debt(self.user_bc, days_back=3)
        self.log(t("Billing cycle updated (STATE='C', DEBT_DATE=sysdate-3)."))
        self._sleep(self.settle_wait)

        # -- 4. disable auto-pay ------------------------------------------
        if self.db.has_active_autopay(self.user_acct):
            self.log(t("Account has active auto-pay, disabling..."))
            self.db.disable_autopay(self.user_acct)
            self._sleep(self.settle_wait)
            self.log(t("Auto-pay disabled."))
        else:
            self.log(t("No active auto-pay."))

        # -- 5. temp table + config ---------------------------------------
        self.log(t("Preparing temp table TMP_DUNNING..."))
        self.db.prepare_tmp_dunning(self.user_acct)
        self.log(t("ACCT_ID {acct} inserted into TMP_DUNNING.", acct=self.user_acct))
        self._sleep(self.settle_wait)
        self.db.update_config_item_param()
        self.log(t("System config parameters updated."))
        self._sleep(self.settle_wait)

        # -- 6. restart jobserver, trigger, wait ---------------------------
        self.log(t("SSH to server to restart jobserver..."))
        self.ssh.restart_jobserver()
        self._sleep(self.settle_wait)

        self.api.trigger_debit_action_job()

        inst_id, _due = self.wait_for_overdue_inst()
        if inst_id is None:
            msg = t("DebitActionJob failed to generate overdue instance, please check service logs.")
            self.log(msg)
            raise DunningError(msg)
        self.inst_id = inst_id
        self.log(t("Initial setup completed successfully, overdue instance INST_ID={inst} generated.",
                   inst=inst_id))

        # -- 7. verify Level 0 rule ----------------------------------------
        level0_rule = self.rules.first_rule_id(self.group_id)
        if level0_rule is not None:
            action = self.db.verify_rule_action(inst_id, level0_rule)
            if action is None:
                self.log(t("Level 0 rule not found in instance after setup (expected rule {rule}).",
                           rule=level0_rule))
            else:
                self.log(t("Matched rule ID: {rule}, ACTION_ID: {action}",
                           rule=level0_rule, action=action))
        return inst_id

    # ------------------------------------------------------------------
    # polling helper
    # ------------------------------------------------------------------
    def wait_for_overdue_inst(self, timeout=None, interval=None):
        timeout = int(timeout or self.max_wait)
        interval = int(interval or self.poll_interval)
        self.log(self.tr("Waiting for overdue instance to be generated (max {timeout}s)...",
                         timeout=timeout))
        start = time.time()
        while time.time() - start < timeout:
            inst_id, due = self.db.get_overdue_inst(self.user_acct)
            if inst_id is not None:
                return inst_id, due
            self._sleep(interval)
        return None, None

    # ------------------------------------------------------------------
    # simulation (spec 6)
    # ------------------------------------------------------------------
    def _debt_date_for_level(self, level, now=None):
        """Compute the DEBT_DATE that makes the account look overdue for `level`.

        The dunning job derives overdue_days = SYSDATE - DEBT_DATE and picks
        the rule whose window contains it, so 'after N days' (offset +N)
        needs the debt N days in the PAST and 'before N days' (offset -N)
        needs it N days in the FUTURE:  DEBT_DATE = SYSDATE - offset_days.

        GUARD (refinement): for every level EXCEPT Level 0 the result must be
        strictly EARLIER than SYSDATE.  A mis-parsed offset of 0 (or any
        non-negative value) would put DEBT_DATE at/after SYSDATE, i.e. the
        account would not look overdue at all; such dates are clamped to
        SYSDATE - 1 so a valid instance is always generated.
        """
        now = now or datetime.now()
        target = now - timedelta(days=level.offset_days)
        is_level0 = level.seq == 0
        if not is_level0 and target >= now:
            clamped = now - timedelta(days=1)
            self.log(self.tr(
                "DEBT_DATE {date} is not earlier than SYSDATE for rule {rule}; "
                "clamping to {clamped}.",
                date=self._fmt(target), rule=level.rule_id, clamped=self._fmt(clamped)))
            return clamped
        return target

    def _ensure_state_c_for_generation(self):
        """DebitActionJob only picks up accounts whose cycle STATE='C'.

        Runs BEFORE every instance (re)generation.  If a previous simulation
        restored STATE to 'A' (spec 7 cleanup), the next run would silently
        generate nothing - so force 'C' first, always.
        """
        state = self.db.get_billing_cycle_state(self.user_bc)
        if state != "C":
            self.db.set_billing_cycle_state(self.user_bc, "C")
            self.log(self.tr(
                "BILLING_CYCLE.STATE was '{state}', forced to 'C' for instance generation.",
                state=state))
            self._sleep(self.settle_wait)
        else:
            self.log(self.tr("BILLING_CYCLE.STATE already 'C', ready for instance generation."))

    def regenerate_overdue_inst_for_level(self, level, update_debt_date=True):
        """Close the active instance and rebuild it via DebitActionJob.

        update_debt_date -- write BILLING_CYCLE.DEBT_DATE for `level` first.
            True  for a user-selected level (Level 0 gets its future date,
                  higher levels get a date strictly earlier than SYSDATE).
            False for INTERNAL rebuilds (e.g. resetting an instance that is
                  already past the target level): DEBT_DATE must be left as-is
                  and the instance regenerated under the existing date.

        For Level-0 rebuilds (any caller, internal or user-selected) the
        Level-0 window (STATE='C', DEBT_DATE>SYSDATE, CYCLE_END_DATE<SYSDATE)
        is asserted up front, so the job always regenerates the instance
        under the Level-0 conditions.
        """
        t = self.tr
        if self.user_bc is None:
            raise DunningError(t("Please run Initial Setup first."))

        self.log(t("Regenerating overdue instance for {label}", label=level.label))
        # DebitActionJob requires STATE='C': force it before generating,
        # a previous run's spec-7 cleanup may have set it back to 'A'.
        # A USER-SELECTED Level-0 run asserts the FULL window (STATE='C',
        # DEBT_DATE future, CYCLE_END_DATE past); INTERNAL rebuilds (reset
        # during a higher-level run) leave the dates alone as before.
        if update_debt_date and level.seq == 0:
            self._ensure_level0_window(level)
        else:
            self._ensure_state_c_for_generation()
        self.db.close_active_overdue_inst(self.user_acct)
        self._sleep(self.settle_wait)
        self.log(t("Closed all active overdue instances for this account."))

        if update_debt_date:
            if level.seq == 0:
                # _ensure_level0_window already wrote the future DEBT_DATE
                # (and CYCLE_END_DATE) before instances were closed; the
                # account sits in the Level-0 window for the whole rebuild.
                self.log(t("[Level 0] DEBT_DATE already set to the future "
                           "Level-0 date by the window guard."))
            else:
                target_date = self._debt_date_for_level(level)
                self.db.set_billing_cycle_debt_date(self.user_bc, target_date)
                self.log(t("Updated BILLING_CYCLE.DEBT_DATE to {date}",
                           date=self._fmt(target_date)))
                self._sleep(self.settle_wait)
        else:
            self.log(t("BILLING_CYCLE.DEBT_DATE left unchanged (internal rebuild)."))

        self.api.trigger_debit_action_job()
        return self.wait_for_overdue_inst()

    def update_inst_due_date_and_recalc(self, inst_id, level):
        t = self.tr
        # Same convention as DEBT_DATE: overdue window is measured from the
        # instance DUE_DATE, so 'after N days' -> DUE_DATE N days in the past.
        target_date = self._debt_date_for_level(level)
        self.db.set_inst_due_date(inst_id, target_date)
        self.log(t("Updated instance {inst} DUE_DATE to {date}",
                   inst=inst_id, date=self._fmt(target_date)))
        self._sleep(self.settle_wait)
        if level.seq == 0:
            # keep the full Level-0 window (STATE='C', DEBT_DATE future,
            # CYCLE_END_DATE past) asserted before this trigger too
            self._ensure_level0_window(level)
        else:
            self._ensure_state_c_for_generation()
        self.api.trigger_debit_action_job()
        self._sleep(self.poll_interval)

    def _execute_action(self, action_id, rule_id):
        """sched_time = SYSDATE-1 then DebitActionDealJob."""
        t = self.tr
        self.log(t("Preparing to execute action (ACTION_ID: {action}, RULE_ID: {rule})...",
                   action=action_id, rule=rule_id))
        self.db.advance_debit_action_sched_time(action_id)
        self.log(t("Advanced sched_time for debit_action (action_id={action})",
                   action=action_id))
        self._sleep(self.settle_wait)
        self.api.trigger_debit_action_deal_job()

    def _run_prerequisite_chain(self, inst_id, target_level):
        """Walk PARENT_RULE_ID chain and execute prerequisite actions (spec 6).

        Parents that are excluded sub-levels ('Level 4.1 manual action' etc.)
        are not in the cache, but the chain must keep walking UP to the
        nearest included ancestor (e.g. rule 23 -> [86 excluded] -> 19).
        The prerequisite action for the nearest ancestor that HAS an action
        in the instance is executed so DebitActionJob can then generate the
        target rule.
        """
        t = self.tr
        parent_id = self.db.get_parent_rule_id(target_level.rule_id)
        executed = False
        depth = 0
        while parent_id and depth < 10:
            depth += 1
            parent_level = self.rules.get_by_rule_id(parent_id)
            prereq_action = self.db.verify_rule_action(inst_id, parent_id)
            if prereq_action is not None:
                self.log(t("Detected prerequisite rule Rule {prereq} for target rule {rule}, executing prerequisite action...",
                           prereq=parent_id, rule=target_level.rule_id))
                self._execute_action(prereq_action, parent_id)
                self._sleep(self.post_trigger_wait)
                executed = True
                break
            # walk UP: excluded parents have no cache entry, so follow their
            # PARENT_RULE_ID directly from the DB instead of stopping
            if parent_level is not None:
                parent_id = parent_level.parent_rule_id
            else:
                parent_id = self.db.get_parent_rule_id(parent_id)
        if executed:
            self.log(t("Prerequisite action processed, regenerating target action..."))
            if target_level.seq == 0:
                self._ensure_level0_window(target_level)
            else:
                self._ensure_state_c_for_generation()
            self.api.trigger_debit_action_job()
            self._sleep(self.poll_interval)
        return executed

    # ------------------------------------------------------------------
    def run_simulation(self, level):
        """Full simulation flow for a selected RuleLevel."""
        t = self.tr
        if self.user_acct is None:
            raise DunningError(t("Please get account first."))
        if self.user_bc is None:
            raise DunningError(t("Please run Initial Setup first."))

        target_rule = level.rule_id
        self.log("\n================ %s ================" % t(
            "Starting simulation for {label} (expected rule ID: {rule})",
            label=level.label, rule=target_rule))

        original_cycle_end_date = None
        is_level0 = level.seq == 0          # Level 0 = first level of group

        try:
            # Level-0 window is created BEFORE any curl/trigger runs and kept
            # in place until the finally-block restores the cycle, so the job
            # always sees DEBT_DATE>SYSDATE and CYCLE_END_DATE<SYSDATE.
            # Inside the try so a mid-open failure still triggers the restore.
            if is_level0 and self.user_bc:
                original_cycle_end_date = self.db.get_cycle_end_date(self.user_bc)
                self._open_level0_window(level)

            inst_id, _due = self.db.get_overdue_inst(self.user_acct)

            # -- reset if current max rule > target rule ------------------
            if inst_id is not None:
                max_rule = self.db.get_current_max_rule_id(inst_id)
                if max_rule is not None and max_rule > target_rule:
                    self.log(t("Current instance has higher rule (Rule ID: {rule}), resetting to level 0...",
                               rule=max_rule))
                    level0 = self.rules.levels_for_group(self.group_id)[0]
                    # Internal reset only: DEBT_DATE is NOT touched here.  A
                    # future DEBT_DATE write is exclusively reserved for a
                    # user-selected Level 0 run; the target action is reached
                    # afterwards via the DUE_DATE recalculation path.
                    inst_id, _due = self.regenerate_overdue_inst_for_level(
                        level0, update_debt_date=False)
                    if inst_id is None:
                        raise DunningError(t("Failed to generate valid overdue instance."))

            if inst_id is None:
                self.log(t("No active overdue instance found, building automatically..."))
                inst_id, _due = self.regenerate_overdue_inst_for_level(level)
                if inst_id is None:
                    raise DunningError(t("Failed to generate valid overdue instance."))
            self.inst_id = inst_id

            # -- locate / generate the target action -----------------------
            action_id = self.db.verify_rule_action(inst_id, target_rule)

            if action_id is None:
                self.log(t("Instance {inst} does not contain rule {rule}, recalculating DUE_DATE...",
                           inst=inst_id, rule=target_rule))
                self.update_inst_due_date_and_recalc(inst_id, level)
                action_id = self.db.verify_rule_action(inst_id, target_rule)

            if action_id is None:
                if self._run_prerequisite_chain(inst_id, level):
                    action_id = self.db.verify_rule_action(inst_id, target_rule)

            if action_id is None:
                self.log(t("Auto-progression failed, falling back to recreate a fresh instance..."))
                inst_id, _due = self.regenerate_overdue_inst_for_level(level)
                if inst_id is None and is_level0:
                    # L0 rebuild timed out (e.g. window/instance state still
                    # inconsistent from a previous higher-level attempt):
                    # retry once after re-asserting the full Level-0 window.
                    self.log(t("Retry with explicit Level-0 DEBT_DATE update..."))
                    inst_id, _due = self.regenerate_overdue_inst_for_level(level)
                if inst_id is None:
                    raise DunningError(t("Overdue instance regeneration timed out."))
                self.inst_id = inst_id
                action_id = self.db.verify_rule_action(inst_id, target_rule)

            if action_id is None:
                self.log(t("Target rule could not be generated, simulation aborted."))
                raise DunningError(t("Failed to generate action for Rule ID={rule}.",
                                     rule=target_rule))

            # -- level 0 window re-asserted before execution --------------
            if is_level0 and self.user_bc:
                # The window was opened before the first trigger; re-check
                # it right before executing the action so nothing has
                # drifted while instances were being generated.
                self._ensure_level0_window(level)

            # -- execute ----------------------------------------------------
            self._execute_action(action_id, target_rule)
            self.log(t("Task command sent, waiting for result..."))
            self._sleep(self.post_trigger_wait)

            exec_time = self.db.get_exec_time(inst_id)
            if exec_time is not None:
                self.log(t("EXEC_TIME generated: {time}", time=exec_time))
                his_state = self.db.get_action_his_state(action_id)
                if his_state is not None:
                    self.log(t("DEBIT_ACTION_HIS.STATE = {state} for action {action}",
                               state=his_state, action=action_id))
                self.log(t("Level {label} simulation succeeded!", label=level.label))
                return {"ok": True, "inst_id": inst_id, "action_id": action_id,
                        "exec_time": exec_time}

            self.log(t("EXEC_TIME is still NULL."))
            err = self.db.get_action_his_error(inst_id)
            if err:
                self.log(t("Error message from history: {msg}", msg=err))
            self.log(t("EXEC_TIME field not updated, simulation did not complete successfully."))
            return {"ok": False, "inst_id": inst_id, "action_id": action_id,
                    "exec_time": None}

        finally:
            # spec 7: runs after EVERY simulation, whatever the level.
            self._restore_billing_cycle(original_cycle_end_date)

    # ------------------------------------------------------------------
    # cleanup (spec 7)
    # ------------------------------------------------------------------
    def _restore_billing_cycle(self, original_cycle_end_date):
        """Post-simulation cleanup - runs after EVERY simulation.

        1. CYCLE_END_DATE: restored only when we temporarily shifted it
           (Level-0 runs hold it at SYSDATE-1 for the whole simulation).
        2. STATE: ALWAYS re-derived from (possibly restored) CYCLE_END_DATE:
               CYCLE_END_DATE > SYSDATE  ->  STATE='A' (active cycle)
               CYCLE_END_DATE <= SYSDATE ->  STATE='C' (closed cycle)
        """
        t = self.tr
        if not self.user_bc:
            return
        try:
            self.log(t("Waiting {seconds} seconds before restoring BILLING_CYCLE...",
                       seconds=self.restore_wait))
            self._sleep(self.restore_wait)

            if original_cycle_end_date is not None:
                self.db.restore_cycle_end_date(self.user_bc, original_cycle_end_date)
                self.log(t("Restored BILLING_CYCLE.CYCLE_END_DATE to original value"))
            self._l0_cycle_end_shifted = False

            end_date = self.db.get_cycle_end_date(self.user_bc)
            if end_date is not None:
                state = "A" if end_date > datetime.now() else "C"
                self.db.set_billing_cycle_state(self.user_bc, state)
                self.log(t("Based on CYCLE_END_DATE ({date}) set BILLING_CYCLE.STATE to '{state}'",
                           date=self._fmt(end_date), state=state))
        except Exception as exc:
            self.log(t("Exception while restoring BILLING_CYCLE state: {error}",
                       error=exc))
            self.log(traceback.format_exc())

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------
    def test_connections(self):
        """Quick connectivity probe used by the GUI 'Test Connections'."""
        results = {}
        try:
            self.db.connect()
            results["db"] = True
        except Exception:
            results["db"] = False
        try:
            self.ssh.run("echo ok", timeout=10)
            results["ssh"] = True
        except Exception:
            results["ssh"] = False
            self.ssh.close()
        try:
            import requests
            base = str(self.config["api"]["base_url"]).rstrip("/")
            requests.get(base, timeout=int(self.config["api"].get("timeout", 10)))
            results["api"] = True
        except Exception:
            results["api"] = False
        return results
