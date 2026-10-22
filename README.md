# Dunning Simulation Tool v4

Standalone GUI tool for telecom billing system **test environments** that
simulates dunning (collections) levels for a subscriber account by driving the
backend jobs the same way production does - just faster.

The tool:

1. resolves an account and its rule group (`DEBIT_RULE_GROUP_ID` 4 / 5 / 14),
2. prepares the account (attribute, billing cycle, auto-pay, temp table),
3. restarts the remote jobserver over SSH,
4. triggers `DebitActionJob` / `DebitActionDealJob` over HTTP,
5. verifies the expected rule action and `EXEC_TIME`,
6. restores `BILLING_CYCLE` dates afterwards.

> **Test environment only.** `CONFIG_ITEM_PARAM` is intentionally *not*
> restored after a simulation.

---

## Project layout

```
main.py                     # launcher (python main.py / PyInstaller target)
config.json                 # runtime configuration (NOT bundled into the exe)
config.template.json        # template copied by the build script
requirements.txt
build_exe.bat               # PyInstaller build script
dunning_tool/
    __init__.py
    app.py                  # python -m dunning_tool entry point
    gui.py                  # backwards-compat shim -> dunning_tool.ui
    engine.py               # DunningEngine - setup / simulation / cleanup
    db_manager.py           # DatabaseManager - all SQL (oracledb / cx_Oracle)
    ssh_manager.py          # SSHManager - jobserver restart via paramiko
    api_manager.py          # APIManager - triggerJob calls via requests
    rule_cache.py           # RuleCache - dynamic DEBIT_RULE mapping
    config_loader.py        # ConfigLoader - config.json handling
    i18n.py                 # EN/ZH translations for static labels
    services/               # business service layer
        imei_lookup.py      #   IMEILookupService - TAB1 blacklist/whitelist
        acct_lookup.py      #   AcctLookupService - TAB2 CTOS lookup (ACCT_NBR)
    ui/                     # notebook GUI (preprod-tools stack style)
        theme.py            #   centralized clam theme + colors
        threading_bridge.py #   queue-based worker->UI marshal
        base_tab.py         #   AppContext + BaseTab
        widgets.py          #   ConsoleWidget, ResultTable
        main_window.py      #   MainWindow - notebook + engine boot
        tabs/
            dunning_tab.py  #     TAB0 Dunning Simulation (v4 features)
            imei_tab.py     #     TAB1 IMEI Blacklist / Whitelist
            ctos_tab.py     #     TAB2 CTOS Blacklist / Whitelist

test_ui_refactor.py         # unit tests: IMEI validation, SQL builders, i18n
test_ctos_tab.py            # unit tests: TAB2 service + ResultTable + smoke
test_gui_smoke.py           # GUI smoke tests (mocked DB, real Tk)
```

## GUI architecture (v4.1)

The GUI was refactored to the notebook architecture used by the preprod
tools stack:

* `ui/theme.py` - one clam-based ttk theme (colors, fonts, styles) for the
  whole app.
* `ui/threading_bridge.py` - worker threads never touch Tk directly; calls
  are queued and drained by an `after()` poller on the main thread.
* `ui/base_tab.py` - `AppContext` (config/engine/services) + `BaseTab`
  (build/retranslate/run_worker/handle_error).
* `ui/main_window.py` - notebook hosting all tabs, engine boot on a worker
  thread, language switching, status bar.
* `services/` - one service class per feature area on top of the shared
  `DatabaseManager`.

### TAB1: IMEI Blacklist / Whitelist

Pure table lookup with two switchable tables in one tab:

| Mode      | Table                        |
|-----------|------------------------------|
| Blacklist | `cc.SUBS_SPECIAL_GROUP`      |
| Whitelist | `cc.SUBS_SPECIAL_GROUP_HIS`  |

* **Default query** (no IMEI): latest 50 rows joined with
  `SPECIAL_GROUP_TYPE_NAME`, ordered by `CREATED_DATE DESC`.
* **IMEI query**: input must be 14 or 15 digits.
  * 15 digits -> the last digit is stripped; the SQL binds BOTH the
    15-digit and 14-digit values (`WHERE ssg.IMEI = :imei15 OR ssg.IMEI =
    :imei14`, string bind) and the result panel reports whether BOTH
    variants returned rows (pair check).
  * 14 digits -> used as-is (single value, no pair check).
  * Results are capped at 20 rows, ordered by `CREATED_DATE DESC`.

### TAB3: SKG Blacklist

Single sync table \`cc.SPECIAL_GROUP_SYNC\` (Samsung Knox Guard dunning
records synced from the SKG platform):

* **Default query** (no IMEI): latest 50 rows, \`ORDER BY CREATED_DATE
  DESC FETCH FIRST 50 ROWS ONLY\`.
* **IMEI query**: \`EXT_ATTR\` is a CLOB holding a JSON blob
  (paymentId / deviceUid / tel / message), searched by substring:
  \`WHERE EXT_ATTR LIKE :imei15 OR EXT_ATTR LIKE :imei14\`, latest 20 rows.
  * 15 digits -> BOTH the 15-digit value and its 14-digit prefix (last
    digit stripped) are searched; the status line reports hits per variant.
  * 14 digits -> used as-is for both binds.
* CLOB locators are read + closed right after the query, so EXT_ATTR
  renders as plain text and substring hit detection works.
* **Trigger Sync Job** button: after a confirmation dialog it fires
  \`SKGBlacklistSyncJob\` (jobGroup \`_jobserver_\`, params
  \`QRY_DATE=<date>|REPROCESS=Y|SP_ID=101\`) through the jobservermgr REST
  API. \`QRY_DATE\` defaults to today (sysdate); \`YYYY-MM-DD\` and
  \`YYYY/MM/DD\` are accepted.
* The REST reply (\`success\`) only means the trigger was ACCEPTED. Real
  execution can be audited in the DB:
  \`SELECT * FROM cc.poll_scheduler_monitor WHERE info LIKE
  '%SKGBlacklistSyncJob%' ORDER BY event_date DESC\` (added/scheduled/finalized
  events per run).


## Running from source

```bat
pip install -r requirements.txt
python main.py
```

The default Oracle driver is **python-oracledb** (`pip install oracledb`),
which runs in *thin mode* - no Oracle Client install needed.  If your DB
requires thick mode (old DB version / SSO), install the Oracle Instant
Client and the app can also use `cx_Oracle` as a drop-in.

## Configuration

`config.json` is looked up next to the executable (or module, when running from
source).  Sections:

| Section   | Keys                                                                    |
|-----------|-------------------------------------------------------------------------|
| `db`      | `host`, `port`, `service_name`, `user`, `password`                       |
| `ssh`     | `host`, `port`, `username`, `password`, `connect_timeout`, `command_timeout`, `retries` |
| `api`     | `base_url`, `timeout`, `retries`                                         |
| `general` | `poll_interval`, `max_wait`, `b_state_retries`, `b_state_interval`, `post_trigger_wait`, `restore_wait` |

### Password encryption (ENC1)

`password` fields in the `db` / `ssh` sections may be stored obfuscated as
`ENC1:<base64>` so they are not readable at a glance (screenshots, grep).
The loader accepts both plain text and `ENC1:` values - old config files
keep working. Convert a config in place with:

    python encrypt_config.py                # encrypt ./config.json
    python encrypt_config.py other.json     # encrypt a specific file
    python encrypt_config.py --decrypt      # back to plain text

Note this is deliberate obfuscation, not real cryptography - anyone with
the tool source can decode it. For real secrecy use an OS keyring / vault.

All external calls honour these timeouts; every DB/SSH/HTTP call is wrapped in
try/except with full tracebacks logged to the GUI log area.

## Dynamic rule mapping

Levels are **loaded from the database at startup** - `rules_config.json` is no
longer used.  For groups 4, 5 and 14:

* keep rules with `RULE_NAME LIKE '%Level%'`, `STATE='A'` and at least one row
  in `DEBIT_RULE_ACTION`,
* drop names containing `.1` or `manual action` (sub-levels),
* sort by `DEBIT_RULE_ID` ascending; `RULE_NAME` is the display label,
* offset days come from `COMMENTS`
  (`25(5 days before Payment Due Date)` → `-5`,
  `60(Payment Due Date + 30 days)` → `+30`), falling back to `OWE_DAYS` and
  finally `0` when parsing fails.

### Account type detection

| Condition                                                     | Group |
|---------------------------------------------------------------|-------|
| `ACCT_ATTR_VALUE` (ATTR_ID 907207) = `NON_VIP_HYBRID`          | 14    |
| `CUST_TYPE='A'` and attr in `FIZ_CONSUMER, HOME_USERS, NON_VIP_CUSTOMER, TESTLINE, TESTUSER` | 4 |
| `CUST_TYPE='C'` and attr in `NON_VIP_ENT, TESTLINE, SMI_SME`    | 5     |
| default                                                        | 4     |

## Building the .exe

```bat
build_exe.bat
```

produces `dist\DunningSimulationTool.exe` (single file, windowed).  The script
copies `config.template.json` to `dist\config.json` - edit it with real
credentials.  Keep `config.json` **next to** the exe; it is loaded at runtime,
never bundled, so credentials can be changed without rebuilding.

## Usage

1. Enter `account_id` or `account_number`, press **Get Account** - the rule
   group is detected and levels fill the combo.
2. Press **Run Initial Setup** - validates debt/billing cycle, disables
   auto-pay, prepares `TMP_DUNNING`, restarts jobserver, triggers
   `DebitActionJob` and waits for the overdue instance (Level 0).
3. Pick a level and press **Run Simulation** - adjusts `DUE_DATE` by the rule
   offset, triggers the job, resolves prerequisite rules via the
   `PARENT_RULE_ID` chain when needed, executes the action and verifies
   `EXEC_TIME` (plus `DEBIT_ACTION_HIS.STATE` and any `ERROR_MSG`).
4. For Level 0 rules (14 / 31 / 97) `CYCLE_END_DATE` is restored after the run
   and `BILLING_CYCLE.STATE` re-derived from the restored date.

The language combo toggles English / Chinese for static labels; level names
always come from the DB and stay as-is.
