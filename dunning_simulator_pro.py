import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import oracledb
import paramiko
import requests
import json
import os
import sys
import time
from datetime import datetime, timedelta

class DunningApp:
    # 翻译字典：原文（英文） -> 中文
    TRANSLATIONS = {
        # 界面标签
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

        # 按钮消息
        "Default config.json created, please edit with correct credentials.": "默认 config.json 已创建，请编辑填入正确的凭据。",
        "Database connection failed.": "数据库连接失败。",
        "Please enter account_id or account_number.": "请输入 account_id 或 account_number。",
        "Account not found.": "未找到该账户。",
        "No Account": "无账户",
        "Please get account first.": "请先获取账户。",
        "Debt Check": "欠款检查",
        "Account has no debt, please perform debit adjustment.": "账户没有欠款，请执行 debit adjustment。",
        "Billing Cycle": "账期",
        "No billing cycle found.": "没有找到账期。",
        "Setup": "设置",
        "Initial setup completed.": "初始设置完成。",
        "Setup Error": "设置错误",
        "Invalid level selection.": "无效的等级选择。",
        "Error": "错误",
        "Current customer type has no rule defined for Level {level}.": "当前客户类型未定义等级 {level} 的催缴规则！",
        "Verification": "验证",
        "Failed to generate action for Rule ID={rule}.": "未能成功生成 Rule ID={rule} 的动作。",
        "Success": "成功",
        "Level {level} simulation succeeded!": "等级 {level} 模拟成功！",
        "EXEC_TIME not set, simulation did not complete.": "EXEC_TIME 未设置，模拟未成功完成。",
        "Simulation Error": "模拟错误",

        # 日志消息
        "Database connection successful.": "数据库连接成功。",
        "DB connection error: {error}": "数据库连接错误: {error}",
        "Switched customer type to [{type}], level options updated.": "客户类型手动切换为 [{type}]，已更新可用的 Level 选项。",
        "Unknown CUST_TYPE code [{code}], treating as MASSIVE.": "未知的 CUST_TYPE 代码 [{code}]，默认按 MASSIVE 处理。",
        "No CUST_TYPE record found, treating as MASSIVE.": "未查询到对应的 CUST_TYPE 记录，默认按 MASSIVE 处理。",
        "Error querying CUST_TYPE: {error}": "查询 CUST_TYPE 异常: {error}",
        "Found USER_ACCT: {acct}, customer type: {type}": "找到 USER_ACCT: {acct}, 客户类型: {type}",
        "Account does not exist.": "账户不存在。",
        "Query error: {error}": "查询错误: {error}",
        "Starting initial setup for [{type}]": "开始初始设置 [{type}]",
        "Current host: {host}, IP: {ip}": "当前连接的主机: {host}, IP: {ip}",
        "Account missing ATTR_ID=907207, inserting default: {val}": "当前账户缺少 ATTR_ID=907207 属性，插入默认值: {val}",
        "Attribute inserted successfully.": "属性插入成功。",
        "Account already has valid attribute value [{val}], no change needed.": "当前账户已存在合规属性值 [{val}]，无需修改。",
        "Attribute value [{val}] not in valid list {list}, updating to default: {default}": "当前账户属性值 [{val}] 不在合法列表中 {list}，更新为: {default}",
        "Attribute updated successfully.": "属性更新成功。",
        "Error: Account has no debt, please perform debit adjustment.": "错误：账户没有欠款，请执行 debit adjustment。",
        "Debt check passed.": "欠款检查通过。",
        "Error: No billing cycle found.": "错误：没有找到账期。",
        "Found USER_BC: {bc}": "确定 USER_BC: {bc}",
        "Billing cycle updated (STATE='C', DEBT_DATE=sysdate-3).": "账期已更新 (STATE='C', DEBT_DATE=sysdate-3)。",
        "Account has active auto-pay, disabling...": "账户有自动扣款，正在禁用...",
        "Auto-pay disabled.": "自动扣款已禁用。",
        "No active auto-pay.": "无激活的自动扣款。",
        "Preparing temp table TMP_DUNNING...": "准备临时表 TMP_DUNNING...",
        "TMP_DUNNING table does not exist, creating...": "TMP_DUNNING 表不存在，正在创建...",
        "ACCT_ID {acct} inserted into TMP_DUNNING.": "ACCT_ID {acct} 已插入 TMP_DUNNING。",
        "System config parameters updated.": "系统配置参数更新完毕。",
        "Initial setup completed successfully, overdue instance INST_ID={inst} generated.": "初始设置成功完成，已生成逾期实例 INST_ID={inst}",
        "SSH to server to restart jobserver...": "SSH 到服务器重启 jobserver...",
        "Executing remote command: {cmd}": "执行远程命令: {cmd}",
        "Command timed out after {timeout} seconds.": "命令执行超时 ({timeout}秒)",
        "Failed to execute command: {cmd}, error: {error}": "执行命令失败: {cmd}, 错误: {error}",
        "Jobserver stopped successfully.": "Jobserver 停止成功。",
        "Retrying to start Jobserver (attempt {attempt})...": "重试启动 Jobserver (尝试 {attempt})...",
        "Jobserver process started successfully.": "Jobserver 进程启动成功。",
        "Failed to start Jobserver after 3 retries.": "Jobserver 启动失败：重试 3 次后仍无有效进程。",
        "SSH operation failed: {error}": "SSH 操作失败: {error}",
        "Triggering API: {url}": "触发 API: {url}",
        "API response status: {code}, body: {body}": "API 响应状态: {code}, 返回: {body}",
        "API call failed: {error}": "API 调用失败: {error}",
        "Regenerating overdue instance for level {level}": "开始重新生成逾期实例，目标等级 Level {level}",
        "Closed all active overdue instances for this account.": "已关闭当前所有活跃逾期实例。",
        "Updated BILLING_CYCLE.DEBT_DATE to {date}": "已更新 BILLING_CYCLE.DEBT_DATE 为 {date}",
        "Matched rule ID: {rule}, ACTION_ID: {action}": "匹配到规则 ID: {rule}, ACTION_ID: {action}",
        "No action found for rule ID = {rule}.": "未匹配到规则 ID = {rule} 的动作。",
        "Advanced sched_time for debit_action (action_id={action})": "已推进计划时间 debit_action.sched_time (action_id={action})",
        "EXEC_TIME generated: {time}": "EXEC_TIME 已生成: {time}",
        "EXEC_TIME is still NULL.": "EXEC_TIME 依然为空。",
        "Updated instance {inst} DUE_DATE to {date}": "已更新实例 {inst} 的 DUE_DATE 为 {date}",
        "Starting simulation for Level {level} (expected rule ID: {rule})": "开始模拟 Level {level} (期望规则 ID: {rule})",
        "Current instance has higher rule (Rule ID: {rule}), resetting to Level 0...": "当前实例已处于更高规则 (Rule ID: {rule})，正在重置重建 Level 0 实例...",
        "No active overdue instance found, building automatically...": "未找到活跃逾期实例，正在自动构建...",
        "Failed to generate valid overdue instance.": "无法生成有效的逾期实例。",
        "Instance {inst} does not contain rule {rule}, recalculating DUE_DATE...": "实例 {inst} 尚未包含规则 {rule}，尝试重新计算 DUE_DATE...",
        "Detected prerequisite rule Rule {prereq} (Level {level}) for Rule 23, executing prerequisite action...": "检测到 Rule 23 的依赖前置规则 Rule {prereq} (Level {level})，先执行前置动作...",
        "Prerequisite action processed, regenerating target action...": "前置动作已处理，重新计算生成目标动作...",
        "Auto-progression failed, falling back to recreate a fresh instance...": "自动推进失败，降级为【重建全新实例】...",
        "Overdue instance regeneration timed out.": "重新生成逾期实例超时。",
        "Target rule could not be generated, simulation aborted.": "目标规则未能成功生成，模拟中断。",
        "Preparing to execute action (ACTION_ID: {action}, RULE_ID: {rule})...": "准备执行动作 (ACTION_ID: {action}, RULE_ID: {rule})...",
        "Task command sent, waiting 10 seconds for result...": "任务指令已发送，等待 10 秒后校验结果...",
        "Level {level} simulation succeeded!": "Level {level} 模拟成功！",
        "EXEC_TIME field not updated, simulation did not complete successfully.": "EXEC_TIME 字段未刷新，模拟未成功完成。",
        "Simulation exception: {error}": "模拟过程发生异常: {error}",
        "Restored BILLING_CYCLE.CYCLE_END_DATE to original value": "收尾动作：已恢复 BILLING_CYCLE.CYCLE_END_DATE 为原始值",
        "Based on CYCLE_END_DATE ({date}) set BILLING_CYCLE.STATE to '{state}'": "根据 CYCLE_END_DATE ({date}) 判定，将 BILLING_CYCLE.STATE 更新为 '{state}'",
        "Exception while restoring BILLING_CYCLE state: {error}": "收尾还原 BILLING_CYCLE 表状态时发生异常: {error}",
        "Waiting for overdue instance to be generated (max {timeout}s)...": "正在轮询等待逾期实例生成（最长等待 {timeout} 秒）...",
        "[Level 0 specific] Updated BILLING_CYCLE.CYCLE_END_DATE to SYSDATE - 1": "[Level 0 专项] 已更新 BILLING_CYCLE.CYCLE_END_DATE 为 SYSDATE - 1",
        "Massive": "大众",
        "Enterprise": "企业",
    }

    def __init__(self, root):
        self.root = root
        self.root.title("Brainless Dunning Simulation Tool")
        self.root.geometry("820x650")
        self.lang = "en"  # 默认英文，可选 "zh"
        self.config = self.load_config()
        self.rules_config = self.load_rules_config()  # 加载规则配置文件
        self.db_conn = None
        self.user_acct = None
        self.user_bc = None
        self.inst_id = None
        self.current_cust_type = None
        self.create_widgets()

    def tr(self, text, **kwargs):
        """返回当前语言下的翻译，支持变量插值"""
        if self.lang == "zh":
            trans = self.TRANSLATIONS.get(text, text)
        else:
            trans = text  # 英文模式直接返回原文（原文即英文）
        if kwargs:
            return trans.format(**kwargs)
        return trans

    def get_resource_path(self, relative_path):
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

    def load_config(self):
        config_path = self.get_resource_path('config.json')
        if not os.path.exists(config_path):
            default = {
                "db": {
                    "host": "10.26.128.32",
                    "port": 11521,
                    "service_name": "cc",
                    "user": "cc",
                    "password": "CHANGE_ME"
                },
                "ssh": {
                    "host": "10.26.128.43",
                    "username": "cvbsjob",
                    "password": "cvbsjob"
                },
                "api": {
                    "base_url": "http://10.26.128.43:7000"
                }
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Config", self.tr("Default config.json created, please edit with correct credentials."))
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_rules_config(self):
        """加载 rules_config.json 并在不存在时自动生成默认值"""
        rules_path = self.get_resource_path('rules_config.json')
        if not os.path.exists(rules_path):
            default_rules = {
                "MASSIVE": {
                    "ATTR_VALID_VALUES": ["FIZ_CONSUMER", "HOME_USERS", "NON_VIP_CUSTOMER", "TESTLINE", "TESTUSER"],
                    "DEFAULT_ATTR_VALUE": "NON_VIP_CUSTOMER",
                    "LEVEL_OFFSETS": {
                        "0": [0, 5],
                        "1": [-9, -1],
                        "2": [-19, -10],
                        "3": [-29, -20],
                        "4": [-39, -30],
                        "5": [-44, -40],
                        "6": [-59, -45],
                        "7": [-94, -60],
                        "8": [-104, -95],
                        "9": [-125, -105]
                    },
                    "LEVEL_RULES": {
                        "0": 14, "1": 15, "2": 17, "3": 18, "4": 19,
                        "5": 21, "6": 23, "7": 25, "8": 26, "9": 27
                    },
                    "LEVEL_DISPLAY_EN": {
                        "0": "Level 0 - before 5 days",
                        "1": "Level 1 - after 1 day - Barred",
                        "2": "Level 2 - after 10 days Notification",
                        "3": "Level 3 - after 20 days Notification",
                        "4": "Level 4 - after 30 days - suspension&IMEI Block",
                        "5": "Level 5 - after 40 days Notification",
                        "6": "Level 6 - after 45 days - CTOS Blacklist",
                        "7": "Level 7 - after 60 days Notification",
                        "8": "Level 8 - after 95 days Notification",
                        "9": "Level 9 - after 105 days - Termination"
                    }
                },
                "ENT": {
                    "ATTR_VALID_VALUES": ["NON_VIP_ENT", "TESTLINE", "SMI_SME"],
                    "DEFAULT_ATTR_VALUE": "NON_VIP_ENT",
                    "LEVEL_OFFSETS": {
                        "0": [0, 25],
                        "1": [-19, -1],
                        "2": [-29, -20],
                        "3": [-79, -30],
                        "4": [-104, -80],
                        "5": [-125, -105]
                    },
                    "LEVEL_RULES": {
                        "0": 31, "1": 32, "2": 34, "3": 35, "4": 37, "5": 40
                    },
                    "LEVEL_DISPLAY_EN": {
                        "0": "Level 0 - before 25 days",
                        "1": "Level 1 - after 1 day - Barring",
                        "2": "Level 2 - after 20 days - Pre-suspend Notification",
                        "3": "Level 3 - after 30 days Suspension",
                        "4": "Level 4 - after 80 days Notification",
                        "5": "Level 5 - after 105 days - Termination"
                    }
                }
            }
            with open(rules_path, 'w', encoding='utf-8') as f:
                json.dump(default_rules, f, indent=4, ensure_ascii=False)

        with open(rules_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)

        # 格式转换：将 JSON 中的字符串键解析回 int 格式，方便逻辑判断
        parsed_config = {}
        for cust_type, content in raw_data.items():
            parsed_config[cust_type] = {
                "ATTR_VALID_VALUES": tuple(content.get("ATTR_VALID_VALUES", [])),
                "DEFAULT_ATTR_VALUE": content.get("DEFAULT_ATTR_VALUE", ""),
                "LEVEL_OFFSETS": {int(k): tuple(v) for k, v in content.get("LEVEL_OFFSETS", {}).items()},
                "LEVEL_RULES": {int(k): int(v) for k, v in content.get("LEVEL_RULES", {}).items()},
                "LEVEL_DISPLAY_EN": {int(k): str(v) for k, v in content.get("LEVEL_DISPLAY_EN", {}).items()}
            }
        return parsed_config

    def db_connect(self):
        if self.db_conn is None:
            try:
                dsn = f"{self.config['db']['host']}:{self.config['db']['port']}/{self.config['db']['service_name']}"
                self.db_conn = oracledb.connect(
                    user=self.config['db']['user'],
                    password=self.config['db']['password'],
                    dsn=dsn
                )
                self.log(self.tr("Database connection successful."))
            except Exception as e:
                messagebox.showerror("DB Error", self.tr("Database connection failed."))
                self.log(self.tr("DB connection error: {error}", error=e))
                return False
        return True

    def log(self, msg):
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def create_widgets(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(pady=10, fill=tk.X, padx=10)

        tk.Label(top_frame, text=self.tr("Account ID or Number:")).pack(side=tk.LEFT)
        self.acct_entry = tk.Entry(top_frame, width=20)
        self.acct_entry.pack(side=tk.LEFT, padx=5)
        self.get_acct_btn = tk.Button(top_frame, text=self.tr("Get Account"), command=self.get_account)
        self.get_acct_btn.pack(side=tk.LEFT, padx=5)
        self.acct_label = tk.Label(top_frame, text=self.tr("USER_ACCT: None"), fg="blue")
        self.acct_label.pack(side=tk.LEFT, padx=10)

        tk.Label(top_frame, text=self.tr("Language:")).pack(side=tk.LEFT, padx=(20, 5))
        self.lang_var = tk.StringVar(value="English" if self.lang == "en" else "Chinese")
        self.lang_combo = ttk.Combobox(top_frame, textvariable=self.lang_var,
                                       values=[self.tr("English"), self.tr("Chinese")],
                                       state="readonly", width=8)
        self.lang_combo.pack(side=tk.LEFT, padx=5)
        self.lang_combo.bind("<<ComboboxSelected>>", self.change_language)

        self.setup_btn = tk.Button(self.root, text=self.tr("Run Initial Setup"),
                                   command=self.run_initial_setup, bg="#e1f5fe")
        self.setup_btn.pack(pady=5)

        ttk.Separator(self.root, orient='horizontal').pack(fill=tk.X, padx=10, pady=10)

        sim_frame = tk.Frame(self.root)
        sim_frame.pack(pady=10, fill=tk.X, padx=10)

        tk.Label(sim_frame, text=self.tr("Customer Type:")).pack(side=tk.LEFT)
        self.cust_type = ttk.Combobox(sim_frame, values=[self.tr("Massive"), self.tr("Enterprise")],
                                      state="readonly", width=12)
        self.cust_type.set(self.tr("Massive"))
        self.cust_type.pack(side=tk.LEFT, padx=5)
        self.cust_type.bind("<<ComboboxSelected>>", self.on_cust_type_changed)

        tk.Label(sim_frame, text=self.tr("Level:")).pack(side=tk.LEFT, padx=(10, 0))
        self.level_var = tk.StringVar()
        self.level_combo = ttk.Combobox(
            sim_frame,
            textvariable=self.level_var,
            state="readonly",
            width=45
        )
        self.level_combo.pack(side=tk.LEFT, padx=5)

        self.update_level_options()

        self.sim_btn = tk.Button(sim_frame, text=self.tr("Run Simulation"),
                                 command=self.run_simulation, bg="#e8f5e9")
        self.sim_btn.pack(side=tk.LEFT, padx=10)

        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.log_text = scrolledtext.ScrolledText(log_frame, height=20)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def get_current_level_display_map(self):
        """返回当前客户类型对应的等级显示映射"""
        c_type = self.get_cust_type()
        return self.rules_config[c_type]["LEVEL_DISPLAY_EN"]

    def update_level_options(self):
        level_map = self.get_current_level_display_map()
        display_values = [self.tr(text) for text in level_map.values()]
        self.level_combo['values'] = display_values
        if display_values:
            self.level_combo.set(display_values[0])

    def on_cust_type_changed(self, event=None):
        self.update_level_options()
        self.log(self.tr("Switched customer type to [{type}], level options updated.",
                         type=self.cust_type.get()))

    def get_cust_type_from_db(self, acct_id):
        sql = """
            SELECT c.CUST_TYPE 
            FROM CUST c 
            JOIN ACCT a ON a.CUST_ID = c.CUST_ID 
            WHERE a.ACCT_ID = :acct_id
        """
        cursor = self.db_conn.cursor()
        try:
            cursor.execute(sql, {"acct_id": acct_id})
            row = cursor.fetchone()
            if row and row[0]:
                cust_type_code = str(row[0]).strip().upper()
                if cust_type_code == 'C':
                    return 'ENT'
                elif cust_type_code == 'A':
                    return 'MASSIVE'
                else:
                    self.log(self.tr("Unknown CUST_TYPE code [{code}], treating as MASSIVE.", code=cust_type_code))
                    return 'MASSIVE'
            else:
                self.log(self.tr("No CUST_TYPE record found, treating as MASSIVE."))
                return 'MASSIVE'
        except Exception as e:
            self.log(self.tr("Error querying CUST_TYPE: {error}", error=e))
            return 'MASSIVE'
        finally:
            cursor.close()

    def get_account(self):
        input_val = self.acct_entry.get().strip()
        if not input_val:
            messagebox.showwarning("Input", self.tr("Please enter account_id or account_number."))
            return
        if not self.db_connect():
            return

        cursor = self.db_conn.cursor()
        try:
            target_acct = None
            try:
                int_val = int(input_val)
                sql = "SELECT acct_id FROM acct WHERE acct_id = :val"
                cursor.execute(sql, {"val": int_val})
                row = cursor.fetchone()
                if row:
                    target_acct = row[0]
            except ValueError:
                pass

            if not target_acct:
                sql = "SELECT acct_id FROM acct WHERE acct_nbr = :val"
                cursor.execute(sql, {"val": input_val})
                row = cursor.fetchone()
                if row:
                    target_acct = row[0]

            if target_acct:
                self.user_acct = target_acct
                db_cust_type = self.get_cust_type_from_db(self.user_acct)
                self.current_cust_type = db_cust_type

                type_display = self.tr("Enterprise") if db_cust_type == 'ENT' else self.tr("Massive")
                self.cust_type.set(type_display)
                self.update_level_options()

                self.acct_label.config(text=f"USER_ACCT: {self.user_acct} ({self.current_cust_type})")
                self.log(self.tr("Found USER_ACCT: {acct}, customer type: {type}",
                                 acct=self.user_acct, type=self.current_cust_type))
            else:
                messagebox.showerror("Not Found", self.tr("Account not found."))
                self.log(self.tr("Account does not exist."))
        except Exception as e:
            messagebox.showerror("Query Error", self.tr("Query error: {error}", error=e))
            self.log(self.tr("Query error: {error}", error=e))
        finally:
            cursor.close()

    def get_cust_type(self):
        ui_type = self.cust_type.get()
        if ui_type == self.tr("Enterprise"):
            return 'ENT'
        else:
            return 'MASSIVE'

    def get_current_rules_and_offsets(self):
        c_type = self.get_cust_type()
        return self.rules_config[c_type]["LEVEL_RULES"], self.rules_config[c_type]["LEVEL_OFFSETS"]

    def run_initial_setup(self):
        if self.user_acct is None:
            messagebox.showwarning(self.tr("No Account"), self.tr("Please get account first."))
            return
        if not self.db_connect():
            return

        cursor = self.db_conn.cursor()
        try:
            cursor.execute("SELECT SYS_CONTEXT('USERENV','SERVER_HOST'), SYS_CONTEXT('USERENV','IP_ADDRESS') FROM DUAL")
            host, ip = cursor.fetchone()

            # 1. 优先获取当前属性值 (ATTR_ID = 907207)
            query_sql = "SELECT ATTR_VALUE FROM ACCT_ATTR_VALUE WHERE ACCT_ID = :acct AND ATTR_ID = 907207"
            cursor.execute(query_sql, {"acct": self.user_acct})
            row = cursor.fetchone()

            base_cust_type = self.get_cust_type()  # 数据库层面查出的原始类型，如 'MASSIVE'

            # 2. 特殊逻辑判断：如果当前属性是 NON_VIP_HYBRID，则动态使用 MASSIVE_HYBRID 配置
            current_val = row[0] if row else None
            if current_val == "NON_VIP_HYBRID":
                cust_type = "MASSIVE_HYBRID"
            else:
                cust_type = base_cust_type

            # 读取对应的 json 节点配置
            cfg = self.rules_config.get(cust_type, self.rules_config.get(base_cust_type))
            valid_values = cfg["ATTR_VALID_VALUES"]
            default_value = cfg["DEFAULT_ATTR_VALUE"]

            type_name = self.tr("Enterprise") if base_cust_type == 'ENT' else self.tr("Massive")
            self.log(f"\n================ {self.tr('Starting initial setup for [{type}]', type=type_name)} ================")
            self.log(self.tr("Current host: {host}, IP: {ip}", host=host, ip=ip))

            # 3. 属性值校验与处理
            if not row:
                self.log(self.tr("Account missing ATTR_ID=907207, inserting default: {val}", val=default_value))
                insert_sql = """
                    INSERT INTO ACCT_ATTR_VALUE
                    (ACCT_ID, ATTR_ID, ATTR_VALUE, EFF_DATE, EXP_DATE, UPDATE_DATE, NEED_UPLOAD, SP_ID, ROUTING_ID, CREATED_DATE)
                    VALUES
                    (:acct_id, 907207, :attr_val, SYSDATE-10, NULL, SYSDATE-10, 'N', 101, 1, SYSDATE)
                """
                cursor.execute(insert_sql, {"acct_id": self.user_acct, "attr_val": default_value})
                self.db_conn.commit()
                self.log(self.tr("Attribute inserted successfully."))
            else:
                # 如果是 NON_VIP_HYBRID，或者是该配置节点允许的值，则予以保留，不执行 UPDATE
                if current_val in valid_values:
                    self.log(self.tr("Account already has valid attribute value [{val}], no change needed.", val=current_val))
                else:
                    self.log(self.tr("Attribute value [{val}] not in valid list {list}, updating to default: {default}",
                                     val=current_val, list=valid_values, default=default_value))
                    update_sql = "UPDATE ACCT_ATTR_VALUE SET ATTR_VALUE = :default_val, UPDATE_DATE = SYSDATE WHERE ACCT_ID = :acct_id AND ATTR_ID = 907207"
                    cursor.execute(update_sql, {"default_val": default_value, "acct_id": self.user_acct})
                    self.db_conn.commit()
                    self.log(self.tr("Attribute updated successfully."))

            # 4. 后续欠款校验、Billing Cycle 更新等逻辑保持不变
            sql = "SELECT * FROM ACCT_ITEM WHERE ACCT_ID = :acct AND STATE='C'"
            cursor.execute(sql, {"acct": self.user_acct})
            if not cursor.fetchone():
                self.log(self.tr("Error: Account has no debt, please perform debit adjustment."))
                messagebox.showerror(self.tr("Debt Check"), self.tr("Account has no debt, please perform debit adjustment."))
                return
            self.log(self.tr("Debt check passed."))

            sql = "SELECT max(BILLING_CYCLE_ID) FROM ACCT_ITEM WHERE ACCT_ID = :acct AND STATE='C'"
            cursor.execute(sql, {"acct": self.user_acct})
            row = cursor.fetchone()
            if not row or row[0] is None:
                self.log(self.tr("Error: No billing cycle found."))
                messagebox.showerror(self.tr("Billing Cycle"), self.tr("No billing cycle found."))
                return
            self.user_bc = row[0]
            self.log(self.tr("Found USER_BC: {bc}", bc=self.user_bc))

            max_checks = 3
            check_interval = 10
            for attempt in range(1, max_checks + 1):
                cursor.execute("SELECT STATE FROM BILLING_CYCLE WHERE BILLING_CYCLE_ID = :bc", {"bc": self.user_bc})
                bc_row = cursor.fetchone()
                if bc_row and bc_row[0] == 'B':
                    if attempt < max_checks:
                        self.log(self.tr(
                            "Billing Cycle state is 'B' (billing in progress), retry in {interval} seconds... (attempt {attempt}/{max})",
                            interval=check_interval, attempt=attempt, max=max_checks
                        ))
                        time.sleep(check_interval)
                    else:
                        error_msg = self.tr(
                            "Billing Cycle still in 'B' state after {max} checks, aborting setup.",
                            max=max_checks
                        )
                        self.log(error_msg)
                        messagebox.showerror(self.tr("Setup Error"), error_msg)
                        return
                else:
                    self.log(self.tr("Billing Cycle state is not 'B', proceeding."))
                    break

            sql = "UPDATE BILLING_CYCLE SET STATE='C', DEBT_DATE = sysdate-3 WHERE BILLING_CYCLE_ID = :bc"
            cursor.execute(sql, {"bc": self.user_bc})
            self.db_conn.commit()
            self.log(self.tr("Billing cycle updated (STATE='C', DEBT_DATE=sysdate-3)."))

            sql = "SELECT * FROM POST_AUTO_PAY_SIGN WHERE ACCT_ID=:acct AND STATE='A'"
            cursor.execute(sql, {"acct": self.user_acct})
            if cursor.fetchone():
                self.log(self.tr("Account has active auto-pay, disabling..."))
                sql = "UPDATE POST_AUTO_PAY_SIGN SET STATE='X' WHERE ACCT_ID=:acct AND STATE='A'"
                cursor.execute(sql, {"acct": self.user_acct})
                self.db_conn.commit()
                self.log(self.tr("Auto-pay disabled."))
            else:
                self.log(self.tr("No active auto-pay."))

            self.log(self.tr("Preparing temp table TMP_DUNNING..."))
            try:
                cursor.execute("TRUNCATE TABLE TMP_DUNNING")
            except Exception:
                self.log(self.tr("TMP_DUNNING table does not exist, creating..."))
                cursor.execute("CREATE TABLE TMP_DUNNING (ACCT_ID NUMBER)")
                self.db_conn.commit()

            cursor.execute("INSERT INTO TMP_DUNNING (ACCT_ID) VALUES (:acct)", {"acct": self.user_acct})
            self.db_conn.commit()
            self.log(self.tr("ACCT_ID {acct} inserted into TMP_DUNNING.", acct=self.user_acct))

            sql = """
                UPDATE config_item_param 
                SET PARAM_VALUE = 'SELECT ACCT_ID FROM TMP_DUNNING' 
                WHERE CONFIG_ITEM_ID IN (46,234) 
                  AND param_code = 'DEBIT_DEAL_SEARCH_SQL'
            """
            cursor.execute(sql)
            self.db_conn.commit()
            self.log(self.tr("System config parameters updated."))

            self.ssh_restart_jobserver()
            self.trigger_curl("DebitActionJob", "DEBIT_GROUP_TYPE=B|SP_ID=101")

            inst_id, due_date = self.wait_for_overdue_inst(timeout=30, interval=3)
            if inst_id is None:
                raise Exception("DebitActionJob failed to generate overdue instance, please check service logs.")
            self.inst_id = inst_id
            self.log(self.tr("Initial setup completed successfully, overdue instance INST_ID={inst} generated.", inst=inst_id))
            messagebox.showinfo(self.tr("Setup"), self.tr("Initial setup completed."))

        except Exception as e:
            self.db_conn.rollback()
            self.log(self.tr("Simulation exception: {error}", error=e))
            messagebox.showerror(self.tr("Setup Error"), str(e))
        finally:
            cursor.close()

    def ssh_restart_jobserver(self):
        self.log(self.tr("SSH to server to restart jobserver..."))
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            ssh.connect(
                hostname=self.config['ssh']['host'],
                username=self.config['ssh']['username'],
                password=self.config['ssh']['password'],
                timeout=10
            )

            def exec_cmd(cmd, timeout=60):
                self.log(self.tr("Executing remote command: {cmd}", cmd=cmd))
                try:
                    stdin, stdout, stderr = ssh.exec_command(cmd, get_pty=True)
                    start = time.time()
                    while not stdout.channel.exit_status_ready():
                        if time.time() - start > timeout:
                            stdout.channel.close()
                            stderr.channel.close()
                            raise Exception(self.tr("Command timed out after {timeout} seconds.", timeout=timeout))
                        time.sleep(0.1)
                    exit_status = stdout.channel.recv_exit_status()
                    out = stdout.read().decode('utf-8', errors='ignore')[:5000]
                    err = stderr.read().decode('utf-8', errors='ignore')[:5000]
                    return out, err, exit_status
                except Exception as e:
                    raise Exception(self.tr("Failed to execute command: {cmd}, error: {error}", cmd=cmd, error=e))

            for attempt in range(2):
                out, err, status = exec_cmd("cd /job/cvbsjob/r13 && ./bosstool stop jobserver", timeout=60)
                if "jobserver shutdown ok." in out or "jobserver shutdown ok." in err:
                    self.log(self.tr("Jobserver stopped successfully."))
                    break
                time.sleep(3)

            def check_jobserver_running():
                out, err, _ = exec_cmd("ps -ef | grep -w 'Dz_app=jobserver' | grep -v grep", timeout=10)
                return bool(out.strip())

            for attempt in range(3):
                if attempt > 0:
                    self.log(self.tr("Retrying to start Jobserver (attempt {attempt})...", attempt=attempt+1))
                    exec_cmd("cd /job/cvbsjob/r13 && ./bosstool stop jobserver", timeout=60)
                    time.sleep(5)

                out, err, status = exec_cmd("cd /job/cvbsjob/r13 && ./bosstool start jobserver", timeout=30)
                time.sleep(5)

                if check_jobserver_running():
                    self.log(self.tr("Jobserver process started successfully."))
                    return

            raise Exception(self.tr("Failed to start Jobserver after 3 retries."))

        except Exception as e:
            self.log(self.tr("SSH operation failed: {error}", error=e))
            raise
        finally:
            ssh.close()

    def trigger_curl(self, job_name, params):
        url = f"{self.config['api']['base_url']}/jobservermgr/api/triggerJob"
        full_url = f"{url}?jobName={job_name}&jobGroup=Collection&params={params}"
        self.log(self.tr("Triggering API: {url}", url=full_url))
        try:
            response = requests.post(full_url, timeout=30)
            self.log(self.tr("API response status: {code}, body: {body}",
                             code=response.status_code, body=response.text))
            response.raise_for_status()
            return response
        except Exception as e:
            self.log(self.tr("API call failed: {error}", error=e))
            raise

    def get_overdue_inst(self):
        cursor = self.db_conn.cursor()
        try:
            sql = "SELECT INST_ID, DUE_DATE FROM debit_acct_overdue_inst WHERE acct_id = :acct AND STATE='A'"
            cursor.execute(sql, {"acct": self.user_acct})
            row = cursor.fetchone()
            if row:
                return row[0], row[1]
            return None, None
        finally:
            cursor.close()

    def regenerate_overdue_inst_for_level(self, level):
        if self.user_bc is None:
            raise Exception(self.tr("Billing cycle not initialized, please run Initial Setup first."))

        _, current_offsets = self.get_current_rules_and_offsets()

        self.log(self.tr("Regenerating overdue instance for level {level}", level=level))
        cursor = self.db_conn.cursor()

        try:
            cursor.execute("UPDATE debit_acct_overdue_inst SET STATE='C' WHERE acct_id = :acct AND STATE='A'", {"acct": self.user_acct})
            self.db_conn.commit()
            self.log(self.tr("Closed all active overdue instances for this account."))

            low, high = current_offsets[level]
            mid = (low + high) // 2
            target_date = datetime.now() + timedelta(days=mid)
            date_str = target_date.strftime("%Y-%m-%d %H:%M:%S")

            update_sql = "UPDATE BILLING_CYCLE SET DEBT_DATE = TO_DATE(:dt, 'YYYY-MM-DD HH24:MI:SS') WHERE BILLING_CYCLE_ID = :bc"
            cursor.execute(update_sql, {"dt": date_str, "bc": self.user_bc})
            self.db_conn.commit()
            self.log(self.tr("Updated BILLING_CYCLE.DEBT_DATE to {date}", date=date_str))
        finally:
            cursor.close()

        self.trigger_curl("DebitActionJob", "DEBIT_GROUP_TYPE=B|SP_ID=101")
        return self.wait_for_overdue_inst(timeout=30, interval=3)

    def verify_rule_action(self, inst_id, expected_rule_id):
        cursor = self.db_conn.cursor()
        try:
            sql = """
                SELECT DEBIT_RULE_ID, DEBIT_ACTION_ID 
                FROM debit_acct_overdue_rela_action 
                WHERE INST_ID = :inst AND DEBIT_RULE_ID = :rule_id
            """
            cursor.execute(sql, {"inst": inst_id, "rule_id": expected_rule_id})
            row = cursor.fetchone()
            if row:
                rule_id, action_id = row
                self.log(self.tr("Matched rule ID: {rule}, ACTION_ID: {action}", rule=rule_id, action=action_id))
                return action_id
            else:
                self.log(self.tr("No action found for rule ID = {rule}.", rule=expected_rule_id))
                return None
        finally:
            cursor.close()

    def get_current_max_rule_id(self, inst_id):
        cursor = self.db_conn.cursor()
        try:
            sql = "SELECT MAX(DEBIT_RULE_ID) FROM debit_acct_overdue_rela_action WHERE INST_ID = :inst"
            cursor.execute(sql, {"inst": inst_id})
            row = cursor.fetchone()
            return row[0] if row and row[0] is not None else None
        finally:
            cursor.close()

    def update_debit_action_sched_time(self, action_id):
        cursor = self.db_conn.cursor()
        try:
            sql = "UPDATE debit_action SET sched_time = sysdate-1 WHERE debit_action_id = :act"
            cursor.execute(sql, {"act": action_id})
            self.db_conn.commit()
            self.log(self.tr("Advanced sched_time for debit_action (action_id={action})", action=action_id))
        finally:
            cursor.close()

    def verify_exec_time(self, inst_id):
        cursor = self.db_conn.cursor()
        try:
            sql = "SELECT T.EXEC_TIME FROM debit_acct_overdue_rela_action T WHERE T.INST_ID = :inst AND T.EXEC_TIME IS NOT NULL"
            cursor.execute(sql, {"inst": inst_id})
            row = cursor.fetchone()
            if row:
                self.log(self.tr("EXEC_TIME generated: {time}", time=row[0]))
                return True
            self.log(self.tr("EXEC_TIME is still NULL."))
            return False
        finally:
            cursor.close()

    def update_inst_due_date_and_recalc(self, inst_id, level):
        _, current_offsets = self.get_current_rules_and_offsets()

        low, high = current_offsets[level]
        mid = (low + high) // 2
        target_date = datetime.now() + timedelta(days=mid)
        date_str = target_date.strftime("%Y-%m-%d %H:%M:%S")

        cursor = self.db_conn.cursor()
        try:
            cursor.execute(
                "UPDATE debit_acct_overdue_inst SET DUE_DATE = TO_DATE(:dt, 'YYYY-MM-DD HH24:MI:SS') WHERE INST_ID = :inst",
                {"dt": date_str, "inst": inst_id}
            )
            self.db_conn.commit()
            self.log(self.tr("Updated instance {inst} DUE_DATE to {date}", inst=inst_id, date=date_str))
        finally:
            cursor.close()

        self.trigger_curl("DebitActionJob", "DEBIT_GROUP_TYPE=B|SP_ID=101")
        time.sleep(3)

    def run_simulation(self):
        if self.user_acct is None:
            messagebox.showwarning(self.tr("No Account"), self.tr("Please get account first."))
            return
        if not self.db_connect():
            return

        selected_text = self.level_var.get()
        level_map_en = self.get_current_level_display_map()
        reverse_map = {}
        for k, v in level_map_en.items():
            reverse_map[self.tr(v)] = k

        level = reverse_map.get(selected_text)
        if level is None:
            messagebox.showerror(self.tr("Error"), self.tr("Invalid level selection."))
            return

        current_rules, _ = self.get_current_rules_and_offsets()

        if level not in current_rules:
            messagebox.showerror(self.tr("Error"),
                                 self.tr("Current customer type has no rule defined for Level {level}.", level=level))
            return

        expected_rule = current_rules[level]
        self.log(f"\n================ {self.tr('Starting simulation for Level {level} (expected rule ID: {rule})', level=level, rule=expected_rule)} ================")

        original_cycle_end_date = None

        try:
            inst_id, due_date = self.get_overdue_inst()

            if level == 0 and inst_id is not None:
                max_rule = self.get_current_max_rule_id(inst_id)
                level_0_rule = current_rules[0]
                if max_rule and max_rule > level_0_rule:
                    self.log(self.tr("Current instance has higher rule (Rule ID: {rule}), resetting to Level 0...",
                                     rule=max_rule))
                    inst_id, due_date = self.regenerate_overdue_inst_for_level(0)

            if inst_id is None:
                self.log(self.tr("No active overdue instance found, building automatically..."))
                inst_id, due_date = self.regenerate_overdue_inst_for_level(level)
                if inst_id is None:
                    raise Exception(self.tr("Failed to generate valid overdue instance."))

            action_id = self.verify_rule_action(inst_id, expected_rule)

            if action_id is None:
                self.log(self.tr("Instance {inst} does not contain rule {rule}, recalculating DUE_DATE...",
                                 inst=inst_id, rule=expected_rule))
                self.update_inst_due_date_and_recalc(inst_id, level)
                action_id = self.verify_rule_action(inst_id, expected_rule)

            if action_id is None and expected_rule == 23 and self.get_cust_type() == 'MASSIVE':
                level4_rule = current_rules.get(4, 19)
                level4_action_id = self.verify_rule_action(inst_id, level4_rule)

                if level4_action_id:
                    self.log(self.tr("Detected prerequisite rule Rule {prereq} (Level {level}) for Rule 23, executing prerequisite action...",
                                     prereq=level4_rule, level=4))
                    self.update_debit_action_sched_time(level4_action_id)
                    self.trigger_curl("DebitActionDealJob", "DEBIT_ACTION_DEAL,SP_ID=101")
                    time.sleep(5)

                    self.log(self.tr("Prerequisite action processed, regenerating target action..."))
                    self.trigger_curl("DebitActionJob", "DEBIT_GROUP_TYPE=B|SP_ID=101")
                    time.sleep(3)
                    action_id = self.verify_rule_action(inst_id, expected_rule)

            if action_id is None:
                self.log(self.tr("Auto-progression failed, falling back to recreate a fresh instance..."))
                inst_id, due_date = self.regenerate_overdue_inst_for_level(level)
                if inst_id is None:
                    raise Exception(self.tr("Overdue instance regeneration timed out."))
                action_id = self.verify_rule_action(inst_id, expected_rule)

            if action_id is None:
                self.log(self.tr("Target rule could not be generated, simulation aborted."))
                messagebox.showerror(self.tr("Verification"),
                                     self.tr("Failed to generate action for Rule ID={rule}.", rule=expected_rule))
                return

            if level == 0 and self.user_bc:
                cursor = self.db_conn.cursor()
                try:
                    cursor.execute(
                        "SELECT CYCLE_END_DATE FROM BILLING_CYCLE WHERE BILLING_CYCLE_ID = :bc",
                        {"bc": self.user_bc}
                    )
                    row = cursor.fetchone()
                    if row:
                        original_cycle_end_date = row[0]

                    cursor.execute(
                        "UPDATE BILLING_CYCLE SET CYCLE_END_DATE = SYSDATE - 1 WHERE BILLING_CYCLE_ID = :bc",
                        {"bc": self.user_bc}
                    )
                    self.db_conn.commit()
                    self.log(self.tr("[Level 0 specific] Updated BILLING_CYCLE.CYCLE_END_DATE to SYSDATE - 1"))
                finally:
                    cursor.close()

            self.log(self.tr("Preparing to execute action (ACTION_ID: {action}, RULE_ID: {rule})...",
                             action=action_id, rule=expected_rule))
            self.update_debit_action_sched_time(action_id)
            self.trigger_curl("DebitActionDealJob", "DEBIT_ACTION_DEAL,SP_ID=101")
            self.log(self.tr("Task command sent, waiting 10 seconds for result..."))

            time.sleep(10)
            if self.verify_exec_time(inst_id):
                self.log(self.tr("Level {level} simulation succeeded!", level=level))
                messagebox.showinfo(self.tr("Success"),
                                    self.tr("Level {level} simulation succeeded!", level=level))
            else:
                self.log(self.tr("EXEC_TIME field not updated, simulation did not complete successfully."))
                messagebox.showerror(self.tr("Verification"),
                                     self.tr("EXEC_TIME not set, simulation did not complete."))

        except Exception as e:
            self.log(self.tr("Simulation exception: {error}", error=e))
            messagebox.showerror(self.tr("Simulation Error"), str(e))
        finally:
            if self.user_bc and self.db_conn:
                self.log(self.tr("Waiting 5 seconds before restoring BILLING_CYCLE..."))
                time.sleep(5)

                cursor = self.db_conn.cursor()
                try:
                    if level == 0 and original_cycle_end_date is not None:
                        cursor.execute(
                            "UPDATE BILLING_CYCLE SET CYCLE_END_DATE = :orig_date WHERE BILLING_CYCLE_ID = :bc",
                            {"orig_date": original_cycle_end_date, "bc": self.user_bc}
                        )
                        self.log(self.tr("Restored BILLING_CYCLE.CYCLE_END_DATE to original value"))

                    cursor.execute(
                        "SELECT CYCLE_END_DATE FROM BILLING_CYCLE WHERE BILLING_CYCLE_ID = :bc",
                        {"bc": self.user_bc}
                    )
                    row = cursor.fetchone()

                    if row and row[0]:
                        current_end_date = row[0]
                        if current_end_date > datetime.now():
                            target_state = 'A'
                        else:
                            target_state = 'C'

                        cursor.execute(
                            "UPDATE BILLING_CYCLE SET STATE = :st WHERE BILLING_CYCLE_ID = :bc",
                            {"st": target_state, "bc": self.user_bc}
                        )
                        self.log(self.tr("Based on CYCLE_END_DATE ({date}) set BILLING_CYCLE.STATE to '{state}'",
                                         date=current_end_date.strftime('%Y-%m-%d %H:%M:%S'), state=target_state))

                    self.db_conn.commit()
                except Exception as restore_err:
                    self.db_conn.rollback()
                    self.log(self.tr("Exception while restoring BILLING_CYCLE state: {error}", error=restore_err))
                finally:
                    cursor.close()

    def wait_for_overdue_inst(self, timeout=30, interval=2):
        self.log(self.tr("Waiting for overdue instance to be generated (max {timeout}s)...", timeout=timeout))
        start = time.time()
        while time.time() - start < timeout:
            cursor = self.db_conn.cursor()
            try:
                sql = "SELECT INST_ID, DUE_DATE FROM debit_acct_overdue_inst WHERE acct_id = :acct AND STATE='A'"
                cursor.execute(sql, {"acct": self.user_acct})
                row = cursor.fetchone()
                if row:
                    return row[0], row[1]
            finally:
                cursor.close()
            time.sleep(interval)
        return None, None

    def change_language(self, event=None):
        selected = self.lang_var.get()
        if selected == self.tr("English"):
            self.lang = "en"
        elif selected == self.tr("Chinese"):
            self.lang = "zh"
        else:
            return
        self.update_ui_texts()
        self.update_level_options()

    def update_ui_texts(self):
        self.get_acct_btn.config(text=self.tr("Get Account"))
        self.setup_btn.config(text=self.tr("Run Initial Setup"))
        self.sim_btn.config(text=self.tr("Run Simulation"))
        self.cust_type['values'] = [self.tr("Massive"), self.tr("Enterprise")]
        self.lang_combo['values'] = [self.tr("English"), self.tr("Chinese")]
        if self.user_acct:
            self.acct_label.config(text=f"USER_ACCT: {self.user_acct} ({self.current_cust_type})")
        else:
            self.acct_label.config(text=self.tr("USER_ACCT: None"))


if __name__ == "__main__":
    root = tk.Tk()
    app = DunningApp(root)
    root.mainloop()