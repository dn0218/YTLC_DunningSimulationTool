# -*- coding: utf-8 -*-
"""
dunning_tool package.

Modular Dunning Simulation Tool for telecom billing system testing.

Modules:
    i18n            - translation dictionary and tr() helper
    config_loader   - loads config.json
    db_manager      - Oracle access layer (oracledb/cx_Oracle, single connection)
    ssh_manager     - remote command execution (paramiko) with timeout/retry
    api_manager     - HTTP trigger calls (requests) with timeout/retry
    rule_cache      - dynamic DEBIT_RULE / DEBIT_RULE_ACTION mapping cache
    engine          - DunningEngine core business logic
    services        - business service layer (IMEI lookup, ...)
    ui              - notebook GUI (theme / tabs / widgets / bridge)
    gui             - backwards-compatible shim -> dunning_tool.ui
    app             - entry point (python -m dunning_tool)
"""

__version__ = "4.0.0"
