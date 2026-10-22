# -*- coding: utf-8 -*-
"""
rule_cache.py - dynamic DEBIT_RULE / DEBIT_RULE_ACTION mapping (spec 3).

Replaces the old static rules_config.json.  At startup we query:

    DEBIT_RULE        (groups 4, 5, 14; RULE_NAME LIKE '%Level%')
    DEBIT_RULE_ACTION (must have >= 1 action for the rule to be actionable)

Filtering:
    * exclude names containing '.1'            (sub-levels like 'Level1.1')
    * exclude names containing 'manual action' (tagged manual sub-levels)
    * sort by DEBIT_RULE_ID ascending

Offset parsing (spec: RULE_NAME is authoritative, then COMMENTS, then
OWE_DAYS).  Both word orders are recognised:
    "25(5 days before Payment Due Date)"  -> -5     ("5 days before")
    "Level 0 -EP- before 25 days"          -> -25    ("before 25 days")
    "60(Payment Due Date + 30 days)"       -> 30     ("+ 30 days")
    "Level 0 - HYBRID - after 31 days"     -> 31     ("after 31 days")
HYBRID rules carry no COMMENTS, so their offsets come from the name.
"'before N days'" (negative) means the Payment Due Date is N days in the
FUTURE; "'after N days'" (positive) means it is N days in the PAST.
"""

import re

# groups handled by this tool
KNOWN_GROUPS = (4, 5, 14)

GROUP_LABELS = {4: "MASSIVE", 5: "ENTERPRISE", 14: "HYBRID"}

DEFAULT_OFFSET = 0

# offset extraction patterns (ordered; first match wins).
# Both word orders are covered: "N days before" / "before N days".
_BEFORE_PATTERNS = [
    re.compile(r"(\d+)\s*days?\s+before", re.IGNORECASE),
    re.compile(r"before\s+(\d+)\s*days?", re.IGNORECASE),
    re.compile(r"-\s*(\d+)\s*days?", re.IGNORECASE),
]
_AFTER_PATTERNS = [
    re.compile(r"\+\s*(\d+)\s*days?", re.IGNORECASE),
    re.compile(r"(\d+)\s*days?\s+after", re.IGNORECASE),
    re.compile(r"after\s+(\d+)\s*days?", re.IGNORECASE),
    re.compile(r"\+\s*(\d+)\s*day\b", re.IGNORECASE),
    re.compile(r"(\d+)\s*day\b\s*(?!\s*before)", re.IGNORECASE),
]

# Any of these signals means the rule carries readable timing information.
_OFFSET_HINTS = _BEFORE_PATTERNS + _AFTER_PATTERNS + [
    re.compile(r"\bdays?\b", re.IGNORECASE),
    re.compile(r"\bday\b", re.IGNORECASE),
]


def parse_offset_days(text, owe_days=None, default=DEFAULT_OFFSET):
    """Extract the offset in days from free text (RULE_NAME or COMMENTS).

    'before' -> negative, 'after'/'+n' -> positive.  Both word orders are
    recognised: "5 days before" and "before 25 days".
    Returns `default` when nothing can be parsed; falls back to OWE_DAYS
    when provided and text yields nothing.
    """
    text = str(text or "").strip()
    if text:
        for pat in _BEFORE_PATTERNS:
            m = pat.search(text)
            if m:
                return -int(m.group(1))
        for pat in _AFTER_PATTERNS:
            m = pat.search(text)
            if m:
                return int(m.group(1))
    if owe_days not in (None, ""):
        try:
            return int(owe_days)
        except (TypeError, ValueError):
            pass
    return default


class RuleLevel:
    """One selectable dunning level."""

    __slots__ = ("rule_id", "group_id", "parent_rule_id", "name", "comments",
                 "offset_days", "seq", "actions")

    def __init__(self, rule_id, group_id, parent_rule_id, name, comments,
                 offset_days, seq):
        self.rule_id = int(rule_id)
        self.group_id = int(group_id)
        self.parent_rule_id = parent_rule_id
        self.name = (name or "").strip()
        self.comments = comments
        self.offset_days = offset_days
        self.seq = seq  # 0-based position inside the group (level number)
        self.actions = []

    @property
    def label(self):
        """Display label - DB rule name plus offset hint."""
        return "%s [Rule %d, %s%d d]" % (self.name, self.rule_id,
                                         "+" if self.offset_days >= 0 else "",
                                         self.offset_days)

    @property
    def level_number(self):
        return self.seq

    def __repr__(self):
        return "RuleLevel(%d, %s)" % (self.rule_id, self.name)


class RuleCache:
    """Loads and caches the level mapping per DEBIT_RULE_GROUP_ID."""

    EXCLUDE_MARKERS = (".1", "manual action")

    # Exit / reactivation rules hang off the dunning tree but are not
    # dunning levels (their offset cannot be mapped to a level number).
    EXCLUDE_NAME_KEYWORDS = ("exit", "reactivation", "unblocking")

    def __init__(self, db, log=None, tr=None):
        self._db = db
        self._log = log or (lambda msg: None)
        self._tr = tr or (lambda text, **kw: text.format(**kw) if kw else text)
        self._groups = {}          # group_id -> [RuleLevel, ...]
        self._by_rule_id = {}      # rule_id  -> RuleLevel

    # ------------------------------------------------------------------
    def load(self):
        """Populate the cache from DEBIT_RULE / DEBIT_RULE_ACTION."""
        rule_rows = self._db.load_rule_rows()
        action_rows = self._db.load_rule_action_rows()

        actions_by_rule = {}
        for rule_id, seq, action_type, name in action_rows:
            actions_by_rule.setdefault(int(rule_id), []).append(
                (int(seq), int(action_type), name))

        groups = {g: [] for g in KNOWN_GROUPS}
        unparsed = []

        for rule_id, group_id, parent_id, rule_name, comments in rule_rows:
            group_id = int(group_id)
            if group_id not in groups:
                continue
            if not actions_by_rule.get(int(rule_id)):
                continue  # must have at least one action in DEBIT_RULE_ACTION
            lname = str(rule_name or "")
            low = lname.lower()
            if any(marker in low for marker in self.EXCLUDE_MARKERS):
                continue
            if any(kw in low for kw in self.EXCLUDE_NAME_KEYWORDS):
                continue  # exit/reactivation branches are not levels
            # 'Level' must appear as a standalone word ('Post Termination
            # Notification 1-140 days' has actions but is not a Level row).
            # HYBRID (group 14) rules carry no 'Level' text and no COMMENTS,
            # so they are accepted on name alone.
            has_level_word = bool(re.search(r"\blevels?\b", low))
            has_timing = any(pat.search(str(comments or ""))
                             for pat in _OFFSET_HINTS)
            if group_id == 14:
                if not (has_level_word or low):
                    continue
            elif not has_level_word:
                continue
            if not has_timing and group_id != 14:
                continue  # no readable timing info -> not a timed level

            # Offset resolution: RULE_NAME first (canonical level wording,
            # e.g. ENT Level 0 'before 25 days' - its COMMENTS still say
            # '5 days before' from a copy-paste), then COMMENTS, then none.
            offset = parse_offset_days(lname)
            if offset == DEFAULT_OFFSET:
                offset = parse_offset_days(comments)
            if offset == DEFAULT_OFFSET and comments:
                unparsed.append((int(rule_id), comments, offset))

            level = RuleLevel(rule_id, group_id, parent_id, lname, comments,
                              offset, 0)
            level.actions = actions_by_rule.get(int(rule_id), [])
            groups[group_id].append(level)

        for group_id in groups:
            groups[group_id].sort(key=lambda lv: lv.rule_id)
            for idx, level in enumerate(groups[group_id]):
                level.seq = idx

        self._groups = groups
        self._by_rule_id = {lv.rule_id: lv for lv in
                            (l for g in groups.values() for l in g)}

        total = sum(len(v) for v in groups.values())
        self._log(self._tr("Rule cache loaded: {n} groups, {m} levels total.",
                           n=len([g for g in groups if groups[g]]), m=total))
        for rule_id, comments, offset in unparsed:
            self._log(self._tr(
                "Could not parse offset from comments '{comments}' (rule {rule}), "
                "using default {offset}.",
                comments=comments, rule=rule_id, offset=offset))
        for group_id in KNOWN_GROUPS:
            levels = groups.get(group_id, [])
            if levels:
                self._log(self._tr("Loaded {n} levels for rule group {group}: {rules}",
                                   n=len(levels), group=group_id,
                                   rules=", ".join(str(lv.rule_id)
                                                   for lv in levels)))
        return self

    # ------------------------------------------------------------------
    def levels_for_group(self, group_id):
        return list(self._groups.get(int(group_id), []))

    def get_by_rule_id(self, rule_id):
        return self._by_rule_id.get(int(rule_id))

    def first_rule_id(self, group_id):
        levels = self._groups.get(int(group_id), [])
        return levels[0].rule_id if levels else None

    def level_for_rule(self, group_id, rule_id):
        for lv in self._groups.get(int(group_id), []):
            if lv.rule_id == int(rule_id):
                return lv
        return None

    @property
    def group_ids(self):
        return [g for g in KNOWN_GROUPS if self._groups.get(g)]
