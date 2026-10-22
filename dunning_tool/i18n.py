# -*- coding: utf-8 -*-
"""
i18n.py - static UI label translations (English -> Chinese).

Level names come from the database (DEBIT_RULE.RULE_NAME) and are therefore
NOT translated; only static UI strings live here.
"""

TRANSLATIONS = {
    # ---- UI labels ----
    "Account ID or Number:": "账户ID或号码:",
    "Get Account": "获取账户",
    "USER_ACCT: None": "USER_ACCT: 无",
    "Run Initial Setup": "运行初始设置",
    "Customer Type:": "客户类型:",
    "Level:": "等级:",
    "Run Simulation": "运行模拟",
    "Language:": "语言:",
    "English": "英文",
    "Chinese": "中文",
    "Massive": "大众",
    "Enterprise": "企业",
    "Hybrid": "混合",
    "Status: Ready": "状态: 就绪",
    "Status: Running...": "状态: 运行中...",
    "Status: Done": "状态: 完成",
    "Status: Error": "状态: 错误",
    "Clear Log": "清空日志",
    "Test Connections": "测试连接",

    # ---- messagebox titles ----
    "Config": "配置",
    "DB Error": "数据库错误",
    "Input": "输入",
    "Not Found": "未找到",
    "Query Error": "查询错误",
    "Debt Check": "欠款检查",
    "Billing Cycle": "账期",
    "Setup": "设置",
    "Setup Error": "设置错误",
    "Error": "错误",
    "Verification": "验证",
    "Success": "成功",
    "Simulation Error": "模拟错误",
    "No Account": "无账户",
    "Busy": "忙",
    "Connection Test": "连接测试",

    # ---- button / info messages ----
    "Default config.json created, please edit with correct credentials.":
        "默认 config.json 已创建，请编辑填入正确的凭据。",
    "Database connection failed.": "数据库连接失败。",
    "SSH connection failed.": "SSH 连接失败。",
    "API endpoint unreachable.": "API 接口不可达。",
    "All connections OK.": "所有连接正常。",
    "Please enter account_id or account_number.": "请输入 account_id 或 account_number。",
    "Account not found.": "未找到该账户。",
    "Please get account first.": "请先获取账户。",
    "Please run Initial Setup first.": "请先运行初始设置。",
    "Account has no debt, please perform debit adjustment.":
        "账户没有欠款，请执行 debit adjustment。",
    "No billing cycle found.": "没有找到账期。",
    "Initial setup completed.": "初始设置完成。",
    "Invalid level selection.": "无效的等级选择。",
    "Current customer type has no rule defined for Level {level}.":
        "当前客户类型未定义等级 {level} 的催缴规则！",
    "Failed to generate action for Rule ID={rule}.":
        "未能成功生成 Rule ID={rule} 的动作。",
    "Level {label} simulation succeeded!": "等级 {label} 模拟成功！",
    "EXEC_TIME not set, simulation did not complete.":
        "EXEC_TIME 未设置，模拟未成功完成。",
    "Another operation is already running.": "已有操作正在运行，请稍候。",

    # ---- log messages ----
    "Database connection successful.": "数据库连接成功。",
    "DB connection error: {error}": "数据库连接错误: {error}",
    "DB connection closed.": "数据库连接已关闭。",
    "Switched customer type to [{type}], level options updated.":
        "客户类型手动切换为 [{type}]，已更新可用的 Level 选项。",
    "Unknown CUST_TYPE code [{code}], treating as MASSIVE.":
        "未知的 CUST_TYPE 代码 [{code}]，默认按 MASSIVE 处理。",
    "No CUST_TYPE record found, treating as MASSIVE.":
        "未查询到对应的 CUST_TYPE 记录，默认按 MASSIVE 处理。",
    "Error querying CUST_TYPE: {error}": "查询 CUST_TYPE 异常: {error}",
    "Found USER_ACCT: {acct}, customer type: {type}":
        "找到 USER_ACCT: {acct}, 客户类型: {type}",
    "Rule group resolved to {group} (attr={attr}, cust_type={ctype})":
        "规则组判定为 {group} (attr={attr}, cust_type={ctype})",
    "Account does not exist.": "账户不存在。",
    "Query error: {error}": "查询错误: {error}",

    "Starting initial setup for [{type}]": "开始初始设置 [{type}]",
    "Current host: {host}, IP: {ip}": "当前连接的主机: {host}, IP: {ip}",
    "Account missing ATTR_ID=907207, inserting default: {val}":
        "当前账户缺少 ATTR_ID=907207 属性，插入默认值: {val}",
    "Attribute inserted successfully.": "属性插入成功。",
    "Account already has valid attribute value [{val}], no change needed.":
        "当前账户已存在合规属性值 [{val}]，无需修改。",
    "Attribute value [{val}] not in valid list {list}, updating to default: {default}":
        "当前账户属性值 [{val}] 不在合法列表中 {list}，更新为: {default}",
    "Attribute updated successfully.": "属性更新成功。",
    "Error: Account has no debt, please perform debit adjustment.":
        "错误：账户没有欠款，请执行 debit adjustment。",
    "Debt check passed.": "欠款检查通过。",
    "Error: No billing cycle found.": "错误：没有找到账期。",
    "Found USER_BC: {bc}": "确定 USER_BC: {bc}",
    "Billing Cycle state is 'B' (billing in progress), retry in {interval} seconds... (attempt {attempt}/{max})":
        "账期状态为 'B'（出账中），{interval} 秒后重试... (第 {attempt}/{max} 次)",
    "Billing Cycle still in 'B' state after {max} checks, aborting setup.":
        "账期在 {max} 次检查后仍为 'B' 状态，中止初始设置。",
    "Billing Cycle state is not 'B', proceeding.": "账期状态不是 'B'，继续。",
    "Billing cycle updated (STATE='C', DEBT_DATE=sysdate-3).":
        "账期已更新 (STATE='C', DEBT_DATE=sysdate-3)。",
    "Account has active auto-pay, disabling...": "账户有自动扣款，正在禁用...",
    "Auto-pay disabled.": "自动扣款已禁用。",
    "No active auto-pay.": "无激活的自动扣款。",
    "Preparing temp table TMP_DUNNING...": "准备临时表 TMP_DUNNING...",
    "TMP_DUNNING table does not exist, creating...":
        "TMP_DUNNING 表不存在，正在创建...",
    "ACCT_ID {acct} inserted into TMP_DUNNING.": "ACCT_ID {acct} 已插入 TMP_DUNNING。",
    "System config parameters updated.": "系统配置参数更新完毕。",
    "Initial setup completed successfully, overdue instance INST_ID={inst} generated.":
        "初始设置成功完成，已生成逾期实例 INST_ID={inst}",
    "Level 0 rule not found in instance after setup (expected rule {rule}).":
        "初始设置后实例中未找到 Level 0 规则 (期望规则 {rule})。",
    "DebitActionJob failed to generate overdue instance, please check service logs.":
        "DebitActionJob 未能生成逾期实例，请检查服务日志。",

    "SSH to server to restart jobserver...": "SSH 到服务器重启 jobserver...",
    "Executing remote command: {cmd}": "执行远程命令: {cmd}",
    "Command timed out after {timeout} seconds.": "命令执行超时 ({timeout}秒)",
    "Failed to execute command: {cmd}, error: {error}":
        "执行命令失败: {cmd}, 错误: {error}",
    "Jobserver stopped successfully.": "Jobserver 停止成功。",
    "Retrying to start Jobserver (attempt {attempt})...":
        "重试启动 Jobserver (尝试 {attempt})...",
    "Jobserver process started successfully.": "Jobserver 进程启动成功。",
    "Failed to start Jobserver after retries.": "Jobserver 启动失败：重试多次后仍无有效进程。",
    "SSH operation failed: {error}": "SSH 操作失败: {error}",

    "Triggering API: {url}": "触发 API: {url}",
    "API response status: {code}, body: {body}": "API 响应状态: {code}, 返回: {body}",
    "API call failed: {error}": "API 调用失败: {error}",

    "Rule cache loaded: {n} groups, {m} levels total.":
        "规则缓存已加载: {n} 个规则组，共 {m} 个等级。",
    "No actionable levels found for rule group {group}.":
        "规则组 {group} 未找到可用的等级规则。",
    "Loaded {n} levels for rule group {group}: {rules}":
        "规则组 {group} 已加载 {n} 个等级: {rules}",
    "Could not parse offset from comments '{comments}' (rule {rule}), using default {offset}.":
        "无法从注释 '{comments}' (规则 {rule}) 解析偏移天数，使用默认值 {offset}。",

    "Regenerating overdue instance for {label}": "开始重新生成逾期实例，目标等级 {label}",
    "Closed all active overdue instances for this account.":
        "已关闭当前所有活跃逾期实例。",
    "Updated BILLING_CYCLE.DEBT_DATE to {date}": "已更新 BILLING_CYCLE.DEBT_DATE 为 {date}",
    "BILLING_CYCLE.DEBT_DATE left unchanged (internal rebuild).":
        "内部重建：BILLING_CYCLE.DEBT_DATE 保持不变。",
    "Retry with explicit Level-0 DEBT_DATE update...":
        "重试：显式更新 Level-0 的 DEBT_DATE...",
    "BILLING_CYCLE.STATE was '{state}', forced to 'C' for instance generation.":
        "BILLING_CYCLE.STATE 为 '{state}'，已强制设为 'C' 以生成实例。",
    "BILLING_CYCLE.STATE already 'C', ready for instance generation.":
        "BILLING_CYCLE.STATE 已为 'C'，可生成实例。",
    "DEBT_DATE {date} is not earlier than SYSDATE for rule {rule}; clamping to {clamped}.":
        "规则 {rule} 的 DEBT_DATE {date} 不早于 SYSDATE，已收敛为 {clamped}。",
    "Matched rule ID: {rule}, ACTION_ID: {action}": "匹配到规则 ID: {rule}, ACTION_ID: {action}",
    "No action found for rule ID = {rule}.": "未匹配到规则 ID = {rule} 的动作。",
    "Advanced sched_time for debit_action (action_id={action})":
        "已推进计划时间 debit_action.sched_time (action_id={action})",
    "EXEC_TIME generated: {time}": "EXEC_TIME 已生成: {time}",
    "EXEC_TIME is still NULL.": "EXEC_TIME 依然为空。",
    "Updated instance {inst} DUE_DATE to {date}": "已更新实例 {inst} 的 DUE_DATE 为 {date}",
    "Starting simulation for {label} (expected rule ID: {rule})":
        "开始模拟 {label} (期望规则 ID: {rule})",
    "Current instance has higher rule (Rule ID: {rule}), resetting to level 0...":
        "当前实例已处于更高规则 (Rule ID: {rule})，正在重置重建 Level 0 实例...",
    "No active overdue instance found, building automatically...":
        "未找到活跃逾期实例，正在自动构建...",
    "Failed to generate valid overdue instance.": "无法生成有效的逾期实例。",
    "Instance {inst} does not contain rule {rule}, recalculating DUE_DATE...":
        "实例 {inst} 尚未包含规则 {rule}，尝试重新计算 DUE_DATE...",
    "Detected prerequisite rule Rule {prereq} for target rule {rule}, executing prerequisite action...":
        "检测到目标规则 {rule} 的依赖前置规则 Rule {prereq}，先执行前置动作...",
    "Prerequisite action processed, regenerating target action...":
        "前置动作已处理，重新计算生成目标动作...",
    "Auto-progression failed, falling back to recreate a fresh instance...":
        "自动推进失败，降级为【重建全新实例】...",
    "Overdue instance regeneration timed out.": "重新生成逾期实例超时。",
    "Target rule could not be generated, simulation aborted.":
        "目标规则未能成功生成，模拟中断。",
    "Preparing to execute action (ACTION_ID: {action}, RULE_ID: {rule})...":
        "准备执行动作 (ACTION_ID: {action}, RULE_ID: {rule})...",
    "Task command sent, waiting for result...": "任务指令已发送，等待校验结果...",
    "Level {label} simulation succeeded!": "{label} 模拟成功！",
    "EXEC_TIME field not updated, simulation did not complete successfully.":
        "EXEC_TIME 字段未刷新，模拟未成功完成。",
    "Simulation exception: {error}": "模拟过程发生异常: {error}",
    "DEBIT_ACTION_HIS.STATE = {state} for action {action}":
        "动作 {action} 的 DEBIT_ACTION_HIS.STATE = {state}",
    "Error message from history: {msg}": "历史记录中的错误信息: {msg}",
    "Waiting {seconds} seconds before restoring BILLING_CYCLE...":
        "等待 {seconds} 秒后还原 BILLING_CYCLE...",
    "Restored BILLING_CYCLE.CYCLE_END_DATE to original value":
        "收尾动作：已恢复 BILLING_CYCLE.CYCLE_END_DATE 为原始值",
    "Based on CYCLE_END_DATE ({date}) set BILLING_CYCLE.STATE to '{state}'":
        "根据 CYCLE_END_DATE ({date}) 判定，将 BILLING_CYCLE.STATE 更新为 '{state}'",
    "Exception while restoring BILLING_CYCLE state: {error}":
        "收尾还原 BILLING_CYCLE 表状态时发生异常: {error}",
    "Waiting for overdue instance to be generated (max {timeout}s)...":
        "正在轮询等待逾期实例生成（最长等待 {timeout} 秒）...",
    "[Level 0 specific] Updated BILLING_CYCLE.CYCLE_END_DATE to SYSDATE - 1":
        "[Level 0 专项] 已更新 BILLING_CYCLE.CYCLE_END_DATE 为 SYSDATE - 1",

    # ---- Level-0 window guard (refinement) ----
    "[Level 0] DEBT_DATE set to {date} (SYSDATE - offset) before any job trigger":
        "[Level 0] 任何 job 触发前，已将 DEBT_DATE 设为 {date}（SYSDATE - 偏移量）",
    "[Level 0] CYCLE_END_DATE set to SYSDATE - 1 (held for the whole simulation)":
        "[Level 0] 已将 CYCLE_END_DATE 设为 SYSDATE - 1（整个模拟期间保持）",
    "[Level 0] BILLING_CYCLE.STATE was '{state}', forced to 'C'.":
        "[Level 0] BILLING_CYCLE.STATE 原为 '{state}'，已强制设为 'C'。",
    "[Level 0] DEBT_DATE ({date}) was not later than SYSDATE, re-set to {target}":
        "[Level 0] DEBT_DATE ({date}) 不晚于 SYSDATE，已重设为 {target}",
    "[Level 0] CYCLE_END_DATE ({date}) was not earlier than SYSDATE, re-set to SYSDATE - 1":
        "[Level 0] CYCLE_END_DATE ({date}) 不早于 SYSDATE，已重设为 SYSDATE - 1",
    "[Level 0] DEBT_DATE already set to the future Level-0 date by the window guard.":
        "[Level 0] DEBT_DATE 已由窗口守护设为 Level-0 的未来日期。",

    # ---- new notebook UI (v4.1) ----
    "Dunning Simulation": "Dunning 模拟",
    "IMEI Blacklist / Whitelist": "IMEI 黑名单 / 白名单",
    "Blacklist": "黑名单",
    "Whitelist": "白名单",
    "Query": "查询",
    "Query IMEI": "查询 IMEI",
    "Default Query": "默认查询",
    "Querying...": "查询中...",
    "IMEI:": "IMEI:",
    "IMEI": "IMEI",
    "Log": "日志",
    "Result": "查询结果",
    "Yes": "是",
    "No": "否",
    "{n} row(s) returned.": "返回 {n} 行。",
    "Querying {table} (latest {n} rows)...": "正在查询 {table}（最近 {n} 行）...",
    "Querying {table} for IMEI {imei}...": "正在查询 {table}，IMEI {imei}...",
    "IMEI {imei}: 15-digit {r15}, 14-digit {r14}.": "IMEI {imei}: 15位 {r15}, 14位 {r14}。",
    "Pair check FAILED - not all variants found.": "配对校验失败 - 并非所有变体都查到记录。",
    "Please enter an IMEI.": "请输入 IMEI。",
    "IMEI must contain digits only (got '{value}').": "IMEI 只能包含数字（当前输入 '{value}'）。",
    "IMEI must be 14 or 15 digits (got {n} digits: '{value}').": "IMEI 必须为 14 或 15 位数字（当前 {n} 位: '{value}'）。",
    "(14 digits: single lookup; 15 digits: 15+14 pair, both must match)": "(14位: 单值查询; 15位: 15+14 配对查询, 两者都须命中)",
    # ---- TAB2: CTOS blacklist / whitelist (v4.2) ----
    "CTOS Blacklist / Whitelist": "CTOS 黑名单 / 白名单",
    "Query ACCT_NBR": "查询 ACCT_NBR",
    "ACCT_NBR:": "ACCT_NBR:",
    "ACCT_NBR": "ACCT_NBR",
    "ACCT_NBR {value}: {found}.": "ACCT_NBR {value}: {found}。",
    "(exact match, string comparison)": "(精确匹配，字符串比较)",
    "Please enter an ACCT_NBR.": "请输入 ACCT_NBR。",
    "ACCT_NBR too long (max 60 chars, got {n}).": "ACCT_NBR 过长（最多 60 字符，当前 {n}）。",
    "Querying {table} for ACCT_NBR {value}...": "正在查询 {table}，ACCT_NBR {value}...",
    "Row Detail": "行详情",
    "Close": "关闭",

    # ---- TAB3: SKG blacklist (v4.3) ----
    "SKG Blacklist": "SKG 黑名单",
    "Trigger Sync Job": "触发同步任务",
    "QRY_DATE:": "QRY_DATE:",
    "SKG Sync Job": "SKG 同步任务",
    "(EXT_ATTR substring match; 15 digits -> 15+14 pair)":
        "(EXT_ATTR 子串匹配; 15位 -> 15+14 配对)",
    "SKGBlacklistSyncJob  (QRY_DATE|REPROCESS=Y|SP_ID=101)":
        "SKGBlacklistSyncJob（QRY_DATE|REPROCESS=Y|SP_ID=101）",
    "Trigger SKGBlacklistSyncJob?\n\nQRY_DATE: {date}\nREPROCESS=Y, SP_ID=101":
        "确认触发 SKGBlacklistSyncJob？\n\nQRY_DATE: {date}\nREPROCESS=Y, SP_ID=101",
    "Confirm": "确认",
    "Trigger cancelled.": "已取消触发。",
    "Triggering SKGBlacklistSyncJob for {date}...":
        "正在触发 SKGBlacklistSyncJob（{date}）...",
    "SKGBlacklistSyncJob triggered for {date}.":
        "SKGBlacklistSyncJob 已触发（{date}）。",
    "QRY_DATE must be YYYY-MM-DD (got '{value}').":
        "QRY_DATE 必须为 YYYY-MM-DD 格式（当前 '{value}'）。",

    # ---- TAB4: dunning instance lookup (v4.4) ----
    "Dunning Instance": "催缴实例",
    "ACCT_NBR:": "ACCT_NBR:",
    "Query": "查询",
    "(select a row, then view its rule actions)":
        "（选择一行后查看其规则动作）",
    "View Actions": "查看动作",
    "Back": "返回",
    "Actions for INST_ID {inst}": "INST_ID {inst} 的动作",
    "{n} instance(s) loaded": "已加载 {n} 条实例",
    "No instance selected yet": "尚未选择实例",
    "Select an instance row first.": "请先选择一条实例记录。",
    "{n} action(s) for INST_ID {inst}.":
        "INST_ID {inst} 共 {n} 条动作。",
    "Please enter an ACCT_NBR.": "请输入 ACCT_NBR。",
    "ACCT_NBR must contain digits only (got '{value}').":
        "ACCT_NBR 只能包含数字（当前 '{value}'）。",
    "INST_ID must contain digits only (got '{value}').":
        "INST_ID 只能包含数字（当前 '{value}'）。",
    "Querying {table} for ACCT_NBR {acct}...":
        "正在查询 {table}（ACCT_NBR: {acct}）...",
    "Querying actions for INST_ID {inst}...":
        "正在查询 INST_ID {inst} 的动作...",

}


def tr(text, lang="en", **kwargs):
    """Return translated text for the given language, with optional formatting."""
    if lang == "zh":
        translated = TRANSLATIONS.get(text, text)
    else:
        translated = text  # source strings are English
    if kwargs:
        try:
            return translated.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return translated
    return translated
