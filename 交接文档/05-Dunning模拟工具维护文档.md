# 05 - Dunning 模拟工具（DunningTool_v4）维护文档

> 面向接手开发的工程师：核心逻辑、数据流、逐模块职责、修改指引、测试、已知问题。

---

## 1. 总体架构

```
gui.py (DunningApp, tkinter)
   │  worker 线程发起，root.after 回主线程，日志经 queue 线程安全
   ▼
engine.py (DunningEngine)  ←— rule_cache.py (RuleCache: DB 动态等级映射)
   │                │                ▲
   │                │                └── db_manager.py (DatabaseManager)
   ├── db_manager.py (全部 Oracle SQL, 线程锁 RLock, 懒连接)
   ├── ssh_manager.py (paramiko, jobserver 重启)
   └── api_manager.py (requests, triggerJob)
i18n.py 提供 tr(text, **kw)；engine 不 import tkinter（log/tr 全部回调注入）
```

- 异常体系：`DunningError`（业务）、`DatabaseError`、`SSHError`、`APIError`。
- GUI `_spawn()` 统一在 worker 线程跑任务并按异常类型分发弹窗。

---

## 1.5 v4.1 变更：GUI 重构 + TAB1（IMEI 黑/白名单）

> **GUI 已重构为 notebook 多 Tab 架构**（借鉴 preprod tools 技术栈）。
> `gui.py` 保留为兼容 shim，`from dunning_tool.gui import run` 依旧可用，
> `main.py` / `app.py` 启动路径不变。

### 新增模块

```
dunning_tool/
    services/
        __init__.py
        imei_lookup.py      # IMEILookupService（TAB1 业务）
        acct_lookup.py      # AcctLookupService（TAB2 业务）
    ui/
        __init__.py
        theme.py            # 集中式 clam 主题（颜色/字体/样式）
        threading_bridge.py # 队列式 worker->UI 线程桥（after 轮询）
        base_tab.py         # AppContext + BaseTab
        widgets.py          # ConsoleWidget / ResultTable
        main_window.py      # MainWindow：Notebook + engine 启动 + 语言切换
        tabs/
            __init__.py
            dunning_tab.py  # TAB0：Dunning 模拟（原 gui.py 全部功能）
            imei_tab.py     # TAB1：IMEI 黑名单/白名单
            ctos_tab.py     # TAB2：CTOS 黑名单/白名单（ACCT_NBR）
```

### 线程模型（重要）

worker 线程**绝不**直接调用 Tk（mainloop 未跑时会抛
"main thread is not in main loop"）。所有跨线程调用经
`UIThreadBridge.run_on_ui()` 入队，由主线程 `after(80ms)` 轮询执行。
轮询器在 `MainWindow.__init__` 中启动（`bridge.start()`）。

### TAB1: IMEI 黑名单 / 白名单

| 模式 | 表 |
|------|-----|
| Blacklist | `cc.SUBS_SPECIAL_GROUP` |
| Whitelist | `cc.SUBS_SPECIAL_GROUP_HIS` |

- **默认查询**（无参）：`ORDER BY CREATED_DATE DESC FETCH FIRST 50 ROWS ONLY`，
  SELECT `st.SPECIAL_GROUP_TYPE_NAME, ssg.*`（JOIN `cc.SPECIAL_GROUP_TYPE`）。
- **IMEI 查询**：仅接受 14/15 位纯数字（否则 `IMEILookupError` 提示）。
  - 15 位 -> 去尾数得 14 位，`:imei15` / `:imei14` 两个**字符串绑定**入 SQL
    （`WHERE ssg.IMEI = :imei15 OR ssg.IMEI = :imei14`）；
    **两个变体都必须返回行**（结果面板逐项显示命中情况，配对失败明确提示）；
  - 14 位 -> 单值直查，无配对要求；
  - 结果 `FETCH FIRST 20 ROWS ONLY`，`CREATED_DATE DESC`。
- IMEI 列类型已核实：两张表均为 `VARCHAR2(255)`，库中存量为 14 位串。
- `db_manager` 新增 `query_with_columns(sql, params)` -> `(列名, 行)`，
  供任意结果集表格渲染使用。

### 测试

- `test_ui_refactor.py`：IMEI 校验/配对/SQL 构造/i18n/导入（16 用例）。
- `test_gui_smoke.py`：真实 Tk 窗口冒烟（构建/切换/查询流/语言切换，4 用例）。
- 真实 DB 探针已验证两条默认 SQL 与配对 SQL 均可执行（50 行/20 行上限）。

### 回滚

重构前快照：`_backups/DunningTool_v4_pre-gui-refactor_*.zip`（整包含文档），
解压即恢复 v4.0。

---

## 1.6 v4.2 变更：TAB2（CTOS 黑/白名单）+ ResultTable 展示优化

### TAB2: CTOS Blacklist / Whitelist

与 TAB1 同构（双表按钮切换、后台线程查询、ResultTable 渲染），差异仅在
表名与查询参数：

| 模式 | 表 |
|------|-----|
| Blacklist | `cc.ACCT_SPECIAL_GROUP` |
| Whitelist | `cc.ACCT_SPECIAL_GROUP_HIS` |

- **默认查询**（无参）：`SELECT asg.* FROM <表> asg ORDER BY CREATED_DATE
  DESC FETCH FIRST 50 ROWS ONLY`；
- **ACCT_NBR 查询**：`WHERE asg.ACCT_NBR = :acct_nbr`（**字符串绑定**，
  列类型 VARCHAR2(60)，空白拒绝、>60 字符拒绝 -> `AcctLookupError`），
  `ORDER BY CREATED_DATE DESC FETCH FIRST 20 ROWS ONLY`；
- 无 IMEI 配对逻辑——TAB2 的输入就是一个 ACCT_NBR 字符串；
- 服务层：`services/acct_lookup.py`（AcctLookupService），与
  imei_lookup 平行；UI：`ui/tabs/ctos_tab.py`。

### ResultTable 展示优化（横向看不全的修复）

- **数据驱动列宽**：按表头 + 抽样单元格内容计算每列宽度
  （`MIN_W=70` / `MAX_W=320`），`stretch=False`，列宽固定不再互相挤压；
- **超长单元格截断显示**（>40 字符加 `…`），**双击行（或回车）弹出行
  详情窗口**，完整内容可复制（COMMENTS 里的超长错误文本不再丢内容）；
- **横向滚动**：底部水平滚动条常驻，支持 Shift+滚轮、滚轮侧键
  （Button-6/7）、Ctrl+滚轮横向平移；新结果加载后自动回到最左上角；
- **点击表头排序**：同一列反复点击在升/降序之间切换（数字/字符串混合
  安全：None 排最后）。

### 测试

- `test_ctos_tab.py`：18 个离线用例（SQL 构造、ACCT_NBR 校验、mock 查询、
  列宽/截断/排序/横滚/详情弹窗、CTOSTab 注册/切换/查询/校验冒烟）；
  **注意**：GUI 用例会 patch 掉所有 `tkinter.messagebox` 弹窗并旁路
  `_boot_engine`——模态弹窗无人点击会永久挂起测试，boot 线程会中途
  换掉 `ctx.acct/ctx.db`；
- 真实 DB 冒烟：两表默认查询（各 50 行 × 20 列）、黑/白名单参数查询、
  未命中路径、校验拒绝均通过（`_tmp_tab2_smoke*.py`，可删）。

---

## 2. 关键业务逻辑（engine.py）

### 2.1 初始设置 run_initial_setup()

1. 属性检查/修复：ATTR_ID=907207；组5 用 ENT_VALID/ENT_DEFAULT，其余 MASSIVE_VALID/MASSIVE_DEFAULT；缺则插、非法则改为默认（SP_ID=101, ROUTING_ID=1, EFF_DATE=SYSDATE-10）；
2. 欠费检查：`ACCT_ITEM.STATE='C'` 必须存在，否则报"请先做 debit adjustment"；
3. 账期：取 `MAX(BILLING_CYCLE_ID)`（来自 ACCT_ITEM STATE='C'）；STATE='B'（出账中）时按 `b_state_retries/b_state_interval` 重试，超限中止；然后 `UPDATE BILLING_CYCLE SET STATE='C', DEBT_DATE=SYSDATE-3`；
4. 关自动扣款：`POST_AUTO_PAY_SIGN STATE='A' → 'X'`；
5. 临时表 + 配置：`TRUNCATE/CREATE TMP_DUNNING` 并插入账户；`UPDATE config_item_param SET PARAM_VALUE='SELECT ACCT_ID FROM TMP_DUNNING' WHERE CONFIG_ITEM_ID IN (46,234) AND param_code='DEBIT_DEAL_SEARCH_SQL'`（**不还原，见 §7**）；
6. SSH 重启 jobserver → 触发 `DebitActionJob`（参数 `DEBIT_GROUP_TYPE=B|SP_ID=101`）→ 轮询 `debit_acct_overdue_inst STATE='A'`（poll_interval/max_wait）；
7. 校验 Level 0 规则动作已生成（`debit_acct_overdue_rela_action`）。

### 2.2 模拟 run_simulation(level)

日期约定（`_debt_date_for_level`）：**DEBT_DATE = SYSDATE − offset**。`after N days`（offset +N）→ 欠费 N 天（过去）；`before N days`（offset −N）→ 未来。非 Level 0 的目标日期若 ≥ SYSDATE 会被**钳制到 SYSDATE−1**（防 offset 解析失败导致永远不欠费）。

流程：

1. **Level 0 窗口**（`_open_level0_window`，在任何触发前）：DEBT_DATE 设为未来日期；CYCLE_END_DATE=SYSDATE−1（记 `_l0_cycle_end_shifted`，结束后恢复原值）；每次触发前 `_ensure_level0_window` 重新断言三条件（STATE='C'、DEBT_DATE>SYSDATE、CYCLE_END_DATE<SYSDATE），因为别的作业可能翻回去；
2. 实例已存在且 `MAX(DEBIT_RULE_ID) > 目标` → 内部重建（`update_debt_date=False`，不动 DEBT_DATE，只重生成实例）；
3. 无实例 → 重建（写目标 DEBT_DATE）；
4. 找目标动作：实例里没有 → `update_inst_due_date_and_recalc`（改实例 DUE_DATE 再触发）；还没有 → `_run_prerequisite_chain` 沿 `PARENT_RULE_ID` 上溯（被剔除的子级不在缓存，直接查 DB 继续上溯，最多 10 层），执行最近的有动作祖先的前置动作；再没有 → 全新重建实例（Level 0 额外重试一次）；
5. 执行动作：`UPDATE debit_action SET sched_time=SYSDATE-1 WHERE debit_action_id=:id` → 触发 `DebitActionDealJob`（参数 `DEBIT_ACTION_DEAL,SP_ID=101`）；
6. 校验：`EXEC_TIME` 非空 = 成功；为空则查 `debit_action_his.STATE`、`debit_rule_action_inst_his.ERROR_MSG`；
7. **finally 清理（每次模拟后必跑）**：恢复 CYCLE_END_DATE（仅 Level 0 动过时）；STATE 按"恢复后 CYCLE_END_DATE > SYSDATE → 'A'，否则 'C'"重推。

### 2.3 jobserver 重启（ssh_manager）

```
cd /job/cvbsjob/r13 && ./bosstool stop jobserver   (最多2次, 认 "jobserver shutdown ok.")
cd /job/cvbsjob/r13 && ./bosstool start jobserver  (retries 次, 每次后 ps -ef|grep -w 'Dz_app=jobserver' 确认)
```

### 2.4 API 触发（api_manager）

`POST {base_url}/jobservermgr/api/triggerJob?jobName=<name>&jobGroup=Collection&params=<params>`，transport 错误按 `retries` 重试（间隔 2s），HTTP 非 2xx 抛错。

---

## 3. 模块职责速查

| 模块 | 行数 | 职责 | 维护要点 |
|------|------|------|---------|
| `gui.py` | 449 | 界面、线程调度、i18n 切换、busy 防重入 | 所有长任务必须走 `_spawn`；禁止在 worker 线程直接碰控件 |
| `engine.py` | 692 | 业务编排、状态机、清理 | 改流程先读 §2.2；清理在 finally，新增写库必须考虑对应恢复 |
| `db_manager.py` | 465 | 全部 SQL（唯一入口），RLock 单连接 | 新 SQL 加到这里，命名意图化；错误信息自动附 squashed SQL |
| `ssh_manager.py` | 133 | jobserver 重启 | BOSS_DIR / STOP_OK / PROC_PATTERN 常量若环境变更需同步 |
| `api_manager.py` | 64 | triggerJob | 参数串格式见 §2.4（注意 DealJob 用逗号分隔） |
| `rule_cache.py` | 231 | 等级映射 | §4 |
| `config_loader.py` | 148 | config 定位/默认模板 | DEFAULT_CONFIG 有两个 general 段（重复键，Python dict 后者覆盖——值相同无影响，重构时清理） |
| `i18n.py` | ~14KB | EN/ZH 字典 | 新增用户可见文案要同时加两种语言 |

---

## 4. RuleCache 细节（改等级识别必读）

1. 数据源：`DEBIT_RULE`（组 4/5/14、`UPPER(RULE_NAME) LIKE '%LEVEL%'`、STATE='A'）+ `DEBIT_RULE_ACTION`（有 ≥1 action 才算可执行等级）；
2. 排除：名称含 `.1` / `manual action`（子级）；名称含 exit/reactivation/unblocking（非等级分支）；"Level" 必须是独立单词；COMMENTS 必须含可解析时间信息（组 14 例外，HYBRID 规则无名无注释，仅凭名称收留）；
3. **offset 解析顺序**：RULE_NAME → COMMENTS → OWE_DAYS → 0。模式覆盖两种语序："5 days before"/"before 25 days"→负，"+ 30 days"/"after 31 days"→正；
4. 排序按 DEBIT_RULE_ID 升序，seq 即下拉框顺序（seq==0 即 Level 0）；
5. 组 14（HYBRID）规则（106/113/114）无 COMMENTS，offset 从名称取（after 31/53/60 days）。

等级→Rule ID 对照（详见 `rules_config.json`（旧）与 DEBIT_RULE.csv）：

- 组 4 MASSIVE：14,15,17,18,19,21,23,25,26,27（+28 拆机后通知）
- 组 5 ENT：31,32,34,35,37,40
- 组 14 HYBRID：106,113,114

---

## 5. 测试

- `test_rule_cache.py`：离线单元测试，用 `DEBIT_RULE.csv`/`DEBIT_RULE_ACTION.csv` 模拟 DB 行（FakeDB），断言 4/5/14 组等级清单、子级剔除、无动作剔除、offset 各模式。**改 rule_cache.py 后必跑**（不需要连 DB）。
- 冒烟：`python main.py` → Get Account → Initial Setup → 各 Level 模拟一遍。

```bat
.venv\Scripts\python.exe test_rule_cache.py
```

---

## 6. 已知问题与设计取舍

1. **CONFIG_ITEM_PARAM 不还原**：工具把 46/234 的 `DEBIT_DEAL_SEARCH_SQL` 指到 TMP_DUNNING 后**故意不恢复**（README 明示）。后果：该环境下每日 Dunning JOB 只扫 TMP_DUNNING 里的账户。**生产严禁使用本工具**；测试环境共享者需知悉。
2. **DebitActionDealJob 生产分页遗漏**：数据量多时 4/5/6 点的 JOB 会漏数据（02 文档 §4.2），与工具无关但模拟"动作没执行"时要先排除。
3. **双停复机不判欠费原因**（Reactivation TWO 节点，01 文档 §2.3）：可能双复失败但不影响后续 action。
4. **config_loader.DEFAULT_CONFIG 重复 general 段**：无害但建议重构。
5. **旧版 `dunning_simulator_pro.py`**（50KB 单文件）已被 v4 取代，仅留参考；其 TRANSLATIONS 字典与 v4 i18n 不互通。
6. settle_wait（默认 4s）散布在每次写库/触发之间，是为了让 jobserver 与 DB 不吃背靠背写；调小需谨慎。

---

## 7. 模拟后的 DB 残留与手工清理

工具自动恢复：BILLING_CYCLE.CYCLE_END_DATE（Level 0）、BILLING_CYCLE.STATE（按日期重推）。
**不自动恢复**（模拟账号属测试数据，通常无需处理；如需干净状态手工执行）：

```sql
-- 1. 还原扫描范围配置（重要：影响该环境所有 Dunning JOB！）
UPDATE CONFIG_ITEM_PARAM
   SET PARAM_VALUE = '<原SQL或留空>'     -- 部署前的原值要自己留档！
 WHERE CONFIG_ITEM_ID IN (46, 234)
   AND PARAM_CODE = 'DEBIT_DEAL_SEARCH_SQL';

-- 2. 关闭模拟实例
UPDATE DEBIT_ACCT_OVERDUE_INST SET STATE='C'
 WHERE ACCT_ID = :ACCT_ID AND STATE='A';

-- 3. 清临时表
TRUNCATE TABLE TMP_DUNNING;
COMMIT;
```

> 建议（接手后改进项）：在 engine.close() 里加"还原 CONFIG_ITEM_PARAM 原值"逻辑（初始设置时先 SELECT 留存原值）。

---

## 8. 常见改需求指引

| 需求 | 改哪里 |
|------|--------|
| 新增/调整等级时间线 | 生产 Debt Rule Optimize 配置改（02 文档），工具端**零修改**（动态加载）；仅当名称不含 "Level" 或无 COMMENTS 时需调 rule_cache 过滤逻辑 |
| 换环境（DB/SSH/API） | 改 config.json 即可；BOSS_DIR 变了才改 ssh_manager |
| 改等待节奏 | config.json general 段 |
| 新增语言 | i18n.py 加字典 + gui.py 语言下拉 |
| 新增校验项 | db_manager 加查询 → engine run_simulation 成功分支调用 → i18n 加文案 |
| 修改打包 | build_exe.bat（hiddenimports 清单别删） |
