# 04 - Dunning 模拟工具（DunningTool_v4）部署手册

> 工程目录：`DunningTool_v4`（本工作区）。
> 工具用途：**测试环境专用**，通过驱动与生产相同的后台 JOB（DebitActionJob / DebitActionDealJob）快速模拟任意欠费等级的催缴动作。

---

## 1. 源码结构

```
main.py                     # 启动器（python main.py / PyInstaller 打包目标）
config.json                 # 运行时配置（不打包进 exe）
config.template.json        # 模板（构建后复制为 dist\config.json）
requirements.txt            # 依赖：oracledb / paramiko / requests / pyinstaller
build_exe.bat               # PyInstaller 打包脚本（必须用 .venv）
DunningSimulationTool.spec  # PyInstaller spec
dunning_tool/
    __init__.py             # 包说明（版本 4.0.0）
    app.py                  # python -m dunning_tool 入口
    gui.py                  # DunningApp：tkinter GUI（449 行，线程 + i18n + 日志队列）
    engine.py               # DunningEngine：核心业务流程（setup / 模拟 / 清理）
    db_manager.py           # DatabaseManager：全部 Oracle SQL（oracledb/cx_Oracle 双驱动）
    ssh_manager.py          # SSHManager：paramiko 重启 jobserver
    api_manager.py          # APIManager：HTTP triggerJob 调用
    rule_cache.py           # RuleCache：DEBIT_RULE/DEBIT_RULE_ACTION 动态等级映射
    config_loader.py        # ConfigLoader：config.json 定位/生成默认模板
    i18n.py                 # EN/ZH 翻译字典
dunning_simulator_pro.py    # 旧版单文件模拟器（v3 及之前，已被 v4 模块化版本取代，留作参考）
test_rule_cache.py          # RuleCache 离线单元测试（用 DEBIT_RULE*.csv 模拟 DB 行）
DEBIT_RULE.csv              # DEBIT_RULE 表导出（测试数据源）
DEBIT_RULE_ACTION.csv       # DEBIT_RULE_ACTION 表导出
rules_config.json           # 旧版静态规则映射（v4 改为 DB 动态加载后不再使用，保留参考）
```

---

## 2. 环境准备

### 2.1 依赖安装

- Python 3.8+（建议 3.10/3.11）
- 默认 Oracle 驱动 **python-oracledb**（thin 模式，**无需安装 Oracle Client**）
  - 如 DB 必须厚模式（老版本/SSO），装 Oracle Instant Client 并改用 `cx_Oracle`（工具自动回落，两者 API 兼容）

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

requirements.txt 内容：

```
oracledb>=1.0
paramiko>=2.11
requests>=2.28
pyinstaller>=6.0   ; 仅打包时需要
```

### 2.2 网络可达性

工具所在机器需能访问（测试环境）：

| 目标 | 用途 |
|------|------|
| `10.26.128.32:11521`（Oracle，service `cc`） | 全部数据读写 |
| `10.26.128.43:22`（SSH，用户 cvbsjob） | 重启 jobserver（`/job/cvbsjob/r13` 下 bosstool） |
| `10.26.128.43:7000`（HTTP） | `POST /jobservermgr/api/triggerJob?jobName=...&jobGroup=Collection&params=...` |

---

## 3. 源码运行

```bat
pip install -r requirements.txt
python main.py          # 或 python -m dunning_tool
```

---

## 4. 配置文件（config.json）

查找顺序（config_loader.py）：exe 同目录 → 模块目录 → 当前目录。缺失时自动写默认模板并报 ConfigError。

| Section | 键 | 说明 |
|---------|----|------|
| `db` | `host` `port` `service_name` `user` `password` | Oracle 连接 |
| `ssh` | `host` `port` `username` `password` `connect_timeout`(15) `command_timeout`(60) `retries`(3) | jobserver SSH |
| `api` | `base_url` `timeout`(30) `retries`(3) | 触发 JOB 的 HTTP |
| `general` | `poll_interval`(3) `max_wait`(60) `b_state_retries`(3) `b_state_interval`(10) `post_trigger_wait`(10) `restore_wait`(5) `settle_wait`(4) | 轮询/等待节奏（秒） |

> 所有外部调用都带超时；DB/SSH/HTTP 异常全部 try/except 并把完整 traceback 打到 GUI 日志区。
> **config.json 含明文密码，勿提交 git、勿随 exe 外发。**

---

## 5. 打包 exe

```bat
build_exe.bat
```

要点（脚本已固化）：

1. **必须用项目 `.venv`**（机器上有多个 Python，用错解释器 exe 启动即报 "No Oracle driver installed"）；
2. 脚本流程：检查 venv → 装依赖 → 校验 `import oracledb / paramiko / requests` → 清理旧 build → PyInstaller `--onefile --windowed`；
3. **hidden-import 清单**：oracledb 的 Cython 扩展运行时动态 import 标准库，PyInstaller 静态分析看不到，必须强制打包（`secrets getpass uuid socket select decimal base64 contextvars queue array struct copy enum functools json string time datetime numbers pickle types abc keyword token xml html`），否则 exe 启动报 `ModuleNotFoundError: secrets`（然后 getpass、uuid……）；
4. 产物：`dist\DunningSimulationTool.exe`（单文件、无控制台）；
5. 构建后脚本自动 `copy config.template.json dist\config.json`——**部署时改 dist\config.json 为真实凭据**；config.json 必须与 exe 同目录，运行时加载、从不打包。

---

## 6. 使用流程（GUI）

1. 输入 `account_id` 或 `account_number` → **Get Account**：解析账户、识别 Rule Group（见下表）、填充等级下拉框；
2. **Run Initial Setup**：校验欠费/账期 → 处理属性 → 关自动扣款 → 准备 `TMP_DUNNING` → 改 `DEBIT_DEAL_SEARCH_SQL` → SSH 重启 jobserver → 触发 DebitActionJob → 等待 Level 0 实例生成；
3. 选等级 → **Run Simulation**：按规则 offset 调整 DUE_DATE → 触发 JOB → 必要时走 PARENT_RULE_ID 前置链 → 执行动作 → 校验 EXEC_TIME / DEBIT_ACTION_HIS.STATE / ERROR_MSG；
4. Level 0 运行结束后恢复 CYCLE_END_DATE 并按恢复值重推 BILLING_CYCLE.STATE。

**账户类型 → Rule Group 识别（db_manager.resolve_rule_group）**：

| 条件 | Group |
|------|-------|
| `ACCT_ATTR_VALUE`(ATTR_ID=907207) = `NON_VIP_HYBRID` | 14（HYBRID） |
| `CUST_TYPE='A'` 且属性 ∈ FIZ_CONSUMER, HOME_USERS, NON_VIP_CUSTOMER, TESTLINE, TESTUSER | 4（MASSIVE） |
| `CUST_TYPE='C'` 且属性 ∈ NON_VIP_ENT, TESTLINE, SMI_SME | 5（ENTERPRISE） |
| 默认 | 4 |

**等级动态加载（rule_cache.py，rules_config.json 已废弃）**：

- 组 4/5/14，`RULE_NAME LIKE '%Level%'`、`STATE='A'` 且 `DEBIT_RULE_ACTION` 至少一行；
- 剔除名称含 `.1` 或 `manual action` 的子级，剔除 exit/reactivation/unblocking 分支；
- 按 `DEBIT_RULE_ID` 升序；offset 从 `COMMENTS` 解析（`25(5 days before Payment Due Date)` → `-5`；`60(Payment Due Date + 30 days)` → `+30`），失败回落 `OWE_DAYS`，再回落 0；
- 语言切换（English/Chinese）只翻静态标签，等级名始终来自 DB。

---

## 7. 卸载 / 清理

- 删除 `dist\`、`build\`、`.venv\`、`__pycache__\` 即可；DB 侧工具残留处理见 05 文档 §7。
