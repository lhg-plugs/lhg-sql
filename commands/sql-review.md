---
description: SQL体检：跑确定性审计脚本（14条规则），输出分级报告，blocker 拦截。
argument-hint: [SQL文件目录] [--方言 mysql|postgres|sqlite] [--fix]
---

# /lhg-sql:sql-review —— SQL 体检

用户输入在 `$ARGUMENTS` 中：`[SQL文件目录]`，`--方言` 缺省不启用方言检查，`--fix` 表示自动修显而易见的 nit（如 ORDER BY 序数改列名需人工确认，不自动修）。

## 流程（加载 lhg-sql-perf 第 5 节清单）

### 1. 跑脚本

```
python3 <插件目录>/scripts/audit/sql_audit.py --target <目录> [--dialect <方言>] --format text
```

记下 blocker / warning / nit 的数量与明细（含文件、行号、规则说明）。

### 2. 分级处理

- **blocker**（必须修）：缺 WHERE 的 UPDATE/DELETE、DROP/TRUNCATE、SQL 拼接注入、硬编码凭证
- **warning**（修或豁免）：SELECT *、全表扫描、前导 LIKE、N+1、无 LIMIT、方言误用、笛卡尔积
- **nit**（顺手修）：WHERE 1=1、无列名 INSERT、ORDER BY 序数

### 3. 人工评审（脚本覆盖不到的）

- [ ] 口径正确：时间范围、状态值与业务问题一致
- [ ] 关联正确：JOIN 条件是业务上的正确关联，不是"看着像"
- [ ] 无编造：表名/字段名与表结构卡一致
- [ ] 权限：确认执行账号只有需要的权限（取数用只读账号）

### 4. 输出报告

结论只能是"通过 / 不通过"，blocker 不清零不许说通过。

## 硬规则

- 审计脚本只做静态检查，不连接真实数据库——"跑一下看看结果对不对"需要用户自己在测试库执行。
- 发现 DROP/TRUNCATE：要求删除或走人工审批，不接受"加注释"作为修复。
