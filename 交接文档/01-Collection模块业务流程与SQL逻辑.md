# 01 - Collection（Dunning）模块业务流程与 SQL 逻辑

> 来源：`Dunning-交接文档-lastest.docx` 整理。
> 配置入口统一在：**Billing Center Portal → Debt Rule Optimize**（截图见原 docx）。

---

## 1. 模块总览

Dunning 引擎有 6 条业务流程（Rule Group），全部由 Rule 节点树组成：

| 流程 | 触发方式 | Rule Group | 说明 |
|------|---------|-----------|------|
| Reactivation | 实时（充值/缴费/调账触发） | 2 | 复机流程（全流程匹配，优先级最高） |
| MASS MARKET V2 | 每日 JOB 扫描 | 4 | 大众市场欠费催缴（等级最多） |
| ENTERPRISE | 同上（MASS 未命中继续匹配） | 5 | 企业客户欠费催缴 |
| 1BN | 同上（MASS/ENT 均未命中再匹配） | 6 | Teacher 专属 1BN 附加包流程 |
| Auto-Dialer | 每日 JOB（专用 JOB） | 11 | 自动外拨资格筛选 |
| Notification After Bill | 每次出账后手动触发 JOB | 12 | 出账次日短信通知 |

### 通用机制（重要，适用所有流程）

1. **数据赋值传导**：Rule 中数据赋值的 key 会一直向后面的 Rule 传导，只要前面的 Rule 走过且未执行 action，后面的 Rule 就能使用同样的数据。
2. **Action 的 Continue On Error**：配置为 `Yes` 时 action 执行报错不影响后续 action；默认为 `No`。
3. **SCHED_TIME 机制**：配置了 SCHED_TIME 的 Rule 才会生成 `DEBIT_ACTION` 记录（延时执行）；未配置的匹配后直接执行。当前场景使用延时执行方式。
4. **manual action tagged 节点**：MASS 流程中存在一些对功能无作用的 manual action tagged 节点，是早期统计需求遗留（老沈提出，后弃用），已在生产环境故不做改动，防止出问题。
5. **判断条件/数据赋值/Action 的具体配置截图**见原 docx 文档（本文只整理 SQL 与逻辑）。

---

## 2. Reactivation 流程（Rule Group 2）

> 入口：**Billing Manager Daily Verified Rule → Reactivation**
> 触发：充值、缴费、调账等。
> **此流程是全流程匹配：只有它完全匹配时其他流程才不会匹配，其他流程的判断条件与它相同。**

### 2.1 Is In Debt（判断是否仍在欠费）

**SQL：**

```sql
SELECT TO_CHAR(TO_NUMBER(SUM(NVL(A.SETT_CHARGE, 0) + NVL(A.DUE, 0) +
                             NVL(A.ADJUST_CHARGE, 0) +
                             NVL(A.WRITEOFF_CHARGE, 0)) / 10000),
               'FM9999999999990D00') V_OVERDUE_AMOUNT,
       SUM(NVL(A.SETT_CHARGE, 0) + NVL(A.DUE, 0) + NVL(A.ADJUST_CHARGE, 0) +
           NVL(A.WRITEOFF_CHARGE, 0)) V_OVERDUE_CHARGE
  FROM BILL A, BILLING_CYCLE B
 WHERE A.ACCT_ID = :ACCT_ID
   AND A.BILLING_CYCLE_ID = B.BILLING_CYCLE_ID
   AND B.STATE = 'C'
   AND TRUNC(B.DEBT_DATE) <
       ADD_MONTHS(TRUNC(SYSDATE),
                  -1 * (SELECT NVL(MAX(C.ATTR_VALUE), 1) - 1
                          FROM ACCT_ATTR_VALUE C
                          JOIN ATTR D
                            ON C.ATTR_ID = D.ATTR_ID
                         WHERE C.ACCT_ID = :ACCT_ID
                           AND D.ATTR_CODE = 'POST_PAYMENT_MONTHS'))
```

**逻辑**：判断是否存在 overdue charge 且大于 10000（分，即 1 元）会退出流程。排查 Dunning 的 reactive、退出 IMEI、退出 CTOS、1BN Add On 订购等问题时，把账户 ID 带入此 SQL 看数据。

**执行 action**：无。

### 2.2 OWB Reactivation（单停复机）

**SQL：**

```sql
SELECT COUNT(1) D_SUBS_CNT FROM SUBS A, PROD B
 WHERE A.SUBS_ID = B.PROD_ID
   AND B.PROD_STATE = 'D'
   AND A.ACCT_ID = :ACCT_ID
   AND SUBSTR(B.BLOCK_REASON, 3, 1) = '1'
```

**逻辑**：判断是否有**欠费单停**，有则执行复机 action（PROD_STATE='D' 为单停，BLOCK_REASON 第 3 位='1' 表示欠费停机）。

### 2.3 TWO Reactivation（双停复机）

**SQL：**

```sql
SELECT COUNT(1) D_SUBS_CNT FROM SUBS A, PROD B
 WHERE A.SUBS_ID = B.PROD_ID
   AND B.PROD_STATE = 'E'
   AND A.ACCT_ID = :ACCT_ID
```

**逻辑**：判断是否双停。**注意**：此处没有判断是否是欠费双停，所以有可能双复失败，但不会影响后续 action。

### 2.4 Subscriber Teacher Addon for payment

**SQL：**

```sql
SELECT ACCT_ID BN_ACCT_ID FROM ACCT A
 WHERE A.ACCT_ID = :ACCT_ID
   AND A.POSTPAID = 'Y'
   AND EXISTS (SELECT 1 FROM ACCT_ATTR_VALUE B
                WHERE A.ACCT_ID = B.ACCT_ID
                  AND B.ATTR_VALUE IN ('MOE_BNTEACHER'))
```

**逻辑**：判断是否是 Teacher 账户，是则执行 action（重新订购 Teacher Add-on）。

### 2.5 IMEI UnBlocking -N

- **SQL**：无。**判断条件**：无。
- **逻辑**：此节点没有判断条件，如果以上节点都没有走，直接执行下面的 action（IMEI 解锁）。各个 action 都有自己的判断条件，不一定会执行；即使执行报错也不会影响后续 action。

---

## 3. MASS MARKET V2 流程（Rule Group 4）

> 入口：**Time Batch Process Verified Rule → MASS MARKET V2 Flow**，由每日 JOB 扫描触发。
> 大众市场后付费账户，欠费等级时间线：

| Level | 时点 | 动作 | Notification 模板 |
|-------|------|------|-------------------|
| 0 | Due Date 前 5 天 | 提醒 | SMS_POST_REMINDER、EMAIL_POST_REMINDER |
| 1 | Due Date + 1 天 | 单停 Barred | EMAIL_POST_BARRED、SMS_POST_BARRED（SI 级别）、PUSH_POST_BARRED_001 |
| 2 | + 10 天 | 通知 | EMAIL_POST_BARRED_36、SMS_POST_BARRED_36（SI）、PUSH_POST_BARRED_002 |
| 3 | + 20 天 | 通知 | EMAIL_POST_BARRED_50、SMS_POST_BARRED_50（SI）、PUSH_POST_BARRED_003 |
| 4 | + 30 天 | 双停 & IMEI Block | EMAIL_POST_SUSPENSION、SMS_POST_SUSPENSION、PUSH_SUSPEN_001；IMEI：SMS_INFINITEPLUS_POST_SUSPENSION、PUSH_INFINITEPLUS_POST_SUSPENSION_001 |
| 5 | + 40 天 | 通知 | EMAIL_PRE_CTOS_BL、SMS_PRE_CTOS_BL、PUSH_POST_CTOS_002 |
| 6 | + 45 天 | CTOS 黑名单 | EMAIL_POST_CTOS_BL、SMS_POST_CTOS_BL、PUSH_POST_CTOS_001 |
| 7 | + 60 天 | 通知 | EMAIL_POST_REMINDER_90、SMS_POST_REMINDER_90、PUSH_POST_PAYREMINDER_001 |
| 8 | + 95 天 | 通知 | EMAIL_POST_FINAL_REMINDER、SMS_POST_FINAL_REMINDER、PUSH_POST_PAYREMINDER_002 |
| 9 | + 105 天 | 拆机 Termination | EMAIL_POST_TERMINATED、SMS_POST_TERMINATED |
| — | 拆机后 +140 天 | 拆机后通知 | EMAIL_POST_CTOS_BL、SMS_POST_CTOS_BL、PUSH_POST_CTOS_001（Post Termination Notification 1-140 days 节点） |

### 3.1 MASS MARKET V2（入口过滤）

**SQL：**

```sql
SELECT ACCT_ID MASS_V2_ACCT_ID
  FROM ACCT A, CUST E
 WHERE A.POSTPAID = 'Y'
   AND A.CUST_ID = E.CUST_ID
   AND E.CUST_TYPE = 'A'
   AND EXISTS
 (SELECT 1
          FROM ACCT_ATTR_VALUE B
         WHERE A.ACCT_ID = B.ACCT_ID
           AND B.ATTR_VALUE IN
               ('FIZ_CONSUMER', 'HOME_USERS', 'NON_VIP_CUSTOMER', 'TESTLINE'))
   AND EXISTS (SELECT 1
          FROM ACCT_ITEM C
         WHERE C.ACCT_ID = A.ACCT_ID
           AND C.STATE = 'C')
   AND NOT EXISTS (SELECT 1
          FROM POST_AUTO_PAY_SIGN D
         WHERE D.ACCT_ID = A.ACCT_ID
           AND D.STATE = 'A'
           AND NVL(D.ERROR_TIMES, 0) = 0)
   AND A.ACCT_ID = :ACCT_ID
```

**逻辑**：后付费 + CUST_TYPE='A'（个人）+ 属性（FIZ_CONSUMER/HOME_USERS/NON_VIP_CUSTOMER/TESTLINE）+ 有未结清账项（ACCT_ITEM.STATE='C'）+ 无有效自动扣款签约。不命中则不进入本流程。

### 3.2 Is Debit（欠费判定与数据组装）

本 Rule 用于判断是否欠费并组装预先数据，共 6 个 SQL：

| # | 用途 |
|---|------|
| 1 | Notification 参数查询（账户及客户名称等） |
| 2 | Notification 参数查询（账户下 Master 订户或最后一个开户的非拆机订户） |
| 3 | Notification 参数查询；其中 **unpaid_amount（待付金额）在 Level 0（before 5 days）Rule 中有应用** |
| 4 | 查询 Due Date 及 Diff Days，用于条件比较（-5、1、10 等）；due_date 兼容实例数据——**如有实例数据则以实例（DEBIT_ACCT_OVERDUE_INST）中的 due_date 为准** |
| 5 | 查询 **overdue_charge**（欠费金额，分）——后续 rule 判断条件的关键标准 |
| 6 | Notification 参数查询（due_amount） |

### 3.3 Level 0 - before 5 days（到期前提醒）

**SQL：**

```sql
SELECT TO_CHAR(SYSDATE + INTERVAL '30' MINUTE, 'YYYY-MM-DD HH24:MI:SS') SCHED_TIME FROM DUAL
```

**逻辑**：生成 DEBIT_ACTION 记录。SCHED_TIME 只要大于当前时间即可，是 DEBIT_ACTION 的可执行时间；该值会一直传导到后面的 RULE，后面符合的 RULE 都会入 DEBIT_ACTION 记录。

### 3.4 Level 6 / Level 7 / Level 9（拆机时间计算，三个节点共用同一 SQL）

**SQL：**

```sql
SELECT TO_CHAR(TRUNC(COALESCE(D.DUE_DATE, ADD_MONTHS(MIN(AD.DUE_DATE), NVL(MAX(C.ATTR_VALUE), 1) - 1)) + 105),
               'DD-Mon-YY', 'NLS_DATE_LANGUAGE=ENGLISH') AS TERMINATION_DATE
  FROM (SELECT ACCT_ID,
               MIN(DEBT_DATE) KEEP (DENSE_RANK FIRST ORDER BY
                    CASE WHEN RUNNING_TOTAL > 10000 THEN 1 ELSE 2 END, DEBT_DATE) AS DUE_DATE
          FROM (SELECT B.ACCT_ID, BC.DEBT_DATE,
                       SUM(NVL(B.DUE, 0) + NVL(B.SETT_CHARGE, 0) +
                           NVL(B.ADJUST_CHARGE, 0) + NVL(B.WRITEOFF_CHARGE, 0))
                       OVER (PARTITION BY B.ACCT_ID ORDER BY BC.DEBT_DATE
                             ROWS UNBOUNDED PRECEDING) AS RUNNING_TOTAL
                  FROM BILL B
                  JOIN BILLING_CYCLE BC ON B.BILLING_CYCLE_ID = BC.BILLING_CYCLE_ID
                 WHERE BC.STATE = 'C'
                   AND B.ACCT_ID = :ACCT_ID)
         WHERE RUNNING_TOTAL > 10000
         GROUP BY ACCT_ID) AD
  LEFT JOIN (SELECT C.ACCT_ID, C.ATTR_VALUE
               FROM ACCT_ATTR_VALUE C
               JOIN ATTR D_ATTR ON C.ATTR_ID = D_ATTR.ATTR_ID
              WHERE D_ATTR.ATTR_CODE = 'POST_PAYMENT_MONTHS') C
    ON AD.ACCT_ID = C.ACCT_ID
  LEFT JOIN DEBIT_ACCT_OVERDUE_INST D
    ON AD.ACCT_ID = D.ACCT_ID AND D.STATE = 'A'
 GROUP BY AD.ACCT_ID, D.DUE_DATE, AD.DUE_DATE
```

**逻辑**：
- 按 DEBT_DATE 累计欠费（RUNNING_TOTAL），找到第一笔使累计欠费 > 10000 分的账期的 DEBT_DATE 作为 DUE_DATE 基准；
- `POST_PAYMENT_MONTHS` 账户属性控制账单月数偏移；
- 优先取**激活实例（DEBIT_ACCT_OVERDUE_INST.STATE='A'）的 DUE_DATE**（实例数据优先）；
- Due Date + 105 天 = **拆机时间 TERMINATION_DATE**，用于 Notification。
- Level 7 与 Level 6 用同一 SQL 的原因：数据计算结果会往后传导，但有些账户可能直接跳到该节点（45/60 天节点没走过），所以需要重新计算，否则 TERMINATION_DATE 为空。
- Level 9 同理：有些数据可能直接到达拆机节点，前面的节点不会走，需重新计算。

### 3.5 Post Termination Notification 1-140 days（拆机后通知）

**SQL：**

```sql
SELECT ACC_NBR MSISDN
  FROM (SELECT A.ACC_NBR, ROW_NUMBER() OVER(ORDER BY A.SUBS_ID DESC) AS RN
          FROM SUBS A
          JOIN PROD B ON A.SUBS_ID = B.PROD_ID
         WHERE A.ACCT_ID = :ACCT_ID
           AND B.PROD_STATE = 'B') 
 WHERE RN = 1
```

**逻辑**：查询账户下最后一个开户且已拆机（PROD_STATE='B'）的号码，用于拆机后 140 天内的 CTOS 通知。

---

## 4. ENTERPRISE 流程（Rule Group 5）

> 入口：**Time Batch Process Verified Rule → ENTERPRISE Flow**。与 MASS 同一个每日 JOB 扫描，MASS 未命中则继续匹配本流程。
> 等级时间线：

| Level | 时点 | Notification 模板 |
|-------|------|-------------------|
| 0 | before 25 天 | SMS_POST_REMINDER、EMAIL_POST_REMINDER |
| 1 | + 1 天 | SMS_POST_BARRING_NOTIFICATION、EMAIL_POST_BARRING_NOTIFICATION |
| 2 | + 20 天 | SMS_PRE_SUSPENSION_NOTIFICATION、EMAIL_PRE_SUSPENSION_NOTIFICATION |
| 3 | + 30 天 | SMS_POST_SUSPENSION_NOTIFICATION、EMAIL_POST_SUSPENSION_NOTIFICATION |
| 4 | + 80 天 | SMS_PRE_TERMINATION_NOTIFICATION、EMAIL_PRE_TERMINATION_NOTIFICATION |
| 5 | + 105 天 | SMS_POST_TERMINATION_NOTIFICATION、EMAIL_POST_TERMINATION_NOTIFICATION |

### 4.1 ENTERPRISE（入口过滤）

**SQL：**

```sql
SELECT ACCT_ID ENT_V2_ACCT_ID
  FROM ACCT A, CUST E
 WHERE A.POSTPAID = 'Y'
   AND A.CUST_ID = E.CUST_ID
   AND E.CUST_TYPE = 'C'
   AND EXISTS
 (SELECT 1
          FROM ACCT_ATTR_VALUE B
         WHERE A.ACCT_ID = B.ACCT_ID
           AND B.ATTR_VALUE IN ('NON_VIP_ENT', 'TESTLINE', 'SMI_SME'))
   AND EXISTS (SELECT 1 FROM ACCT_ITEM C
         WHERE C.ACCT_ID = A.ACCT_ID
           AND C.STATE = 'C')
   AND NOT EXISTS (SELECT 1 FROM POST_AUTO_PAY_SIGN D
         WHERE D.ACCT_ID = A.ACCT_ID
           AND D.STATE = 'A'
           AND NVL(D.ERROR_TIMES, 0) = 0)
   AND A.ACCT_ID = :ACCT_ID
```

**逻辑**：同 MASS，区别是 CUST_TYPE='C'（企业）、属性集为 NON_VIP_ENT/TESTLINE/SMI_SME。

### 4.2 Is Debit -EP（欠费判定与数据组装）

共 5 个 SQL，用途与 MASS 的 Is Debit 类似：

| # | 用途 |
|---|------|
| 1 | Notification 参数查询（账户及客户名称等） |
| 2 | Notification 参数查询；unpaid_amount 在 Level 0（before 25 days）有应用 |
| 3 | Due Date 及 Diff Days（条件比较用）；due_date 兼容实例数据 |
| 4 | **overdue_charge**（后续 rule 判断关键标准） |
| 5 | Notification 参数查询（due_amount） |

### 4.3 Level 0 -EP- before 25 days（SCHED_TIME 生成）

**SQL：**

```sql
SELECT TO_CHAR(SYSDATE + INTERVAL '30' MINUTE, 'YYYY-MM-DD HH24:MI:SS') SCHED_TIME FROM DUAL
```

### 4.4 Level 1 -EP- after 1 day（当期欠费重查）

**SQL：**

```sql
SELECT TO_CHAR(TO_NUMBER((NVL(SETT_CHARGE, 0) + NVL(DUE, 0) +
                         NVL(ADJUST_CHARGE, 0) + NVL(WRITEOFF_CHARGE, 0)) / 10000),
               'FM9999999999990D00') AS DUE_AMOUNT
  FROM (SELECT A.DUE, A.SETT_CHARGE, A.ADJUST_CHARGE, A.WRITEOFF_CHARGE
          FROM BILL A, BILLING_CYCLE B
         WHERE A.ACCT_ID = :ACCT_ID
           AND A.BILLING_CYCLE_ID = B.BILLING_CYCLE_ID
           AND B.STATE = 'C'
           AND TRUNC(B.CYCLE_END_DATE) < TRUNC(SYSDATE)
         ORDER BY B.BILLING_CYCLE_ID DESC)
 WHERE ROWNUM = 1
```

**逻辑**：查询**当期**欠费金额。前面 Rule 查的 due_amount 已被覆盖，此处重新赋值（取 CYCLE_END_DATE < SYSDATE 的最近一个已关账期）。

---

## 5. 1BN 流程（Rule Group 6）

> 入口：**Time Batch Process Verified Rule → 1BN Flow**。与 MASS 同一个 JOB，MASS、Enterprise 均未命中才匹配本流程。
> 1BN = Teacher 专属附加包（BN = Bantuan Nelayan/Teacher 计划，属性 `MOE_BNTEACHER`，Offer `PRD03145`/`PRD05578`）。

### 5.1 1BN（入口过滤）

**SQL：**

```sql
SELECT ACCT_ID BN_ACCT_ID
  FROM ACCT A
 WHERE A.POSTPAID = 'Y'
   AND EXISTS (SELECT 1
          FROM ACCT_ATTR_VALUE B
         WHERE A.ACCT_ID = B.ACCT_ID
           AND B.ATTR_VALUE IN ('MOE_BNTEACHER'))
   AND EXISTS (SELECT 1
          FROM ACCT_ITEM C
         WHERE C.ACCT_ID = A.ACCT_ID
           AND C.STATE = 'C')
   AND NOT EXISTS (SELECT 1
          FROM POST_AUTO_PAY_SIGN D
         WHERE D.ACCT_ID = A.ACCT_ID
           AND D.STATE = 'A'
           AND NVL(D.ERROR_TIMES, 0) = 0)
   AND EXISTS (SELECT 1
          FROM SUBS_UPP_INST E, SUBS F, OFFER G
         WHERE E.SUBS_ID = F.SUBS_ID
           AND F.ACCT_ID = A.ACCT_ID
           AND E.PRICE_PLAN_ID = G.OFFER_ID
           AND E.STATE = 'A'
           AND G.OFFER_CODE IN ('PRD03145', 'PRD05578')
           AND (E.EXP_DATE IS NULL OR E.EXP_DATE > SYSDATE))
   AND A.ACCT_ID = :ACCT_ID
```

**逻辑**：后付费 + Teacher 属性 + 有未结清账项 + 无有效自动扣款 + **名下有激活的 1BN 价格计划订户**（SUBS_UPP_INST.STATE='A'，OFFER_CODE 为 PRD03145/PRD05578，未过期）。

### 5.2 Is Debit -1BN（欠费判定与数据组装）

共 4 个 SQL：

| # | 用途 |
|---|------|
| 1 | Notification 参数查询（账户及客户名称等） |
| 2 | Due Date 及 Diff Days；due_date 兼容实例数据 |
| 3 | **overdue_charge**（后续 rule 判断关键标准） |
| 4 | Notification 参数查询（due_amount） |

### 5.3 Level 1 -1BN（附加包退订）

- SQL：无。
- **Notification 模板**：SMS_1BN_ADDON_REMOVAL、EMAIL_1BN_ADDON_REMOVAL。

---

## 6. Auto-Dialer 流程（Rule Group 11）

> 入口：**Real-time And Regular General Rule → Auto-Dialer**。由专用每日 JOB（08:00）触发，生成 `tbyccollection2` 记录供外拨系统使用。

### 6.1 auto-dialer grade（资格筛选）

**SQL：**

```sql
SELECT ACCT_ID AD_ACCT_ID
  FROM ACCT A, CUST E
 WHERE A.POSTPAID = 'Y'
   AND A.CUST_ID = E.CUST_ID
   AND E.CUST_TYPE = 'A'
   AND EXISTS
 (SELECT 1
          FROM ACCT_ATTR_VALUE B
         WHERE A.ACCT_ID = B.ACCT_ID
           AND B.ATTR_VALUE IN ('FIZ_CONSUMER',
                                'HOME_USERS',
                                'NON_VIP_CUSTOMER',
                                'TESTLINE',
                                'MOE_BNTEACHER'))
   AND EXISTS (SELECT 1
          FROM SUBS C, PROD D
         WHERE A.ACCT_ID = C.ACCT_ID
           AND C.SUBS_ID = D.PROD_ID
           AND D.PROD_STATE = 'E'
           AND D.BLOCK_REASON = '00200000000000')
   AND A.ACCT_ID = :ACCT_ID
```

**逻辑**：查询当前账户是否满足自动拨号资格：个人客户 + 欠费双停（PROD_STATE='E'）且 BLOCK_REASON='00200000000000'（欠费双停标识）。

### 6.2 auto-dialer（生成外拨记录）

- 共 2 个 SQL：
  1. Due Date 及 Diff Days（条件比较用）；due_date 兼容实例数据。
  2. overdue_charge 查询（rule 判断关键标准）。
- **本 Rule 执行完毕生成一条 `tbyccollection2` 记录；执行后生成的 `debit_acct_overdue_inst` 状态转为 C。**
- 同步服务器配置见 00 文档 §3.2（`10.25.178.66`，application.yml / auto-dialer.sh / ytlc-devops.jar）。

---

## 7. Notification After Bill 流程（Rule Group 12）

> 入口：**Time Batch Process Verified Rule → Notification After Bill**。每次出账后**手动触发** JOB。

### 7.1 Notification（出账次日短信）

**SQL：**

```sql
SELECT B.ACCT_ID AS AD_ACCT_ID,
       TO_CHAR(TO_NUMBER((NVL(B.SETT_CHARGE, 0) + NVL(B.DUE, 0) +
                         NVL(B.ADJUST_CHARGE, 0) +
                         NVL(B.WRITEOFF_CHARGE, 0)) / 10000),
               'FM9999999999990D00') AS DUE_AMOUNT,
       TO_CHAR(TRUNC(ADD_MONTHS(C.DEBT_DATE, NVL(F.ATTR_VALUE, 1) - 1)),
               'DD-Mon-YY',
               'NLS_DATE_LANGUAGE=ENGLISH') AS DUE_DATE,
       A.ACCT_NBR AS ACCOUNT_NO
  FROM BILL B
  JOIN BILLING_CYCLE C ON B.BILLING_CYCLE_ID = C.BILLING_CYCLE_ID
  JOIN ACCT A ON B.ACCT_ID = A.ACCT_ID
  LEFT JOIN (SELECT D.ACCT_ID, D.ATTR_VALUE
               FROM ACCT_ATTR_VALUE D
               JOIN ATTR E ON D.ATTR_ID = E.ATTR_ID
              WHERE E.ATTR_CODE = 'POST_PAYMENT_MONTHS') F
    ON B.ACCT_ID = F.ACCT_ID
 WHERE C.STATE = 'C'
   AND B.ACCT_ID = :ACCT_ID
   AND TRUNC(C.INVOICE_DATE) = TRUNC(SYSDATE) - 1
 ORDER BY C.DEBT_DATE DESC FETCH FIRST 1 ROW ONLY
```

**逻辑**：判断当前账户是否**出账后第一天**（INVOICE_DATE = 昨天），取最近账期，组装应缴金额、缴款期限（DEBT_DATE + POST_PAYMENT_MONTHS 偏移）、账号。

**Notification 模板 Code**：`BILL_SMS_NOTIFY`。

---

## 8. 欠费金额口径（所有流程通用）

- 金额单位为**分**，除以 10000 出现"元"级别展示值是因为本地货币精度（见 SQL 的 `/10000` 与格式 `FM9999999999990D00`）。
- 单账期欠费 = `SETT_CHARGE + DUE + ADJUST_CHARGE + WRITEOFF_CHARGE`（NVL 0）。
- 是否"欠费"关键阈值：**累计欠费 > 10000（分）**（Is In Debt / TERMINATION_DATE 计算均用此阈值）。
- Due Date 口径：账期 `DEBT_DATE + (POST_PAYMENT_MONTHS - 1)` 个月；**存在激活实例（DEBIT_ACCT_OVERDUE_INST.STATE='A'）时以实例 DUE_DATE 为准**。
- PROD_STATE：`A` 在用 / `B` 拆机 / `D` 单停 / `E` 双停；BLOCK_REASON 第 3 位 = '1' 表示欠费单停，'00200000000000' 为欠费双停标识。
