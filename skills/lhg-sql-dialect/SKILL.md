---
name: lhg-sql-dialect
description: 方言适配：MySQL / PostgreSQL / SQLite 三方言对照，一份 SQL 在三种库上都能跑对。写完 SQL 后按对照表逐项打勾。
license: MIT
compatibility: 适用于任何支持 Markdown 指令的 AI 编程助手
metadata:
  version: 1.0.0
  author: 刘洪光
---

# lhg-sql-dialect：方言适配

目标：一份 SQL，目标库是什么方言，就按什么方言写对。核心纪律：**写完先查表，再谈执行**——90% 的"在我本地能跑"都是方言差异。

## 1. 何时使用

- SQL 生成后、交付前 → 按第 3 节对照表逐项检查
- 跨库迁移（MySQL → PostgreSQL 等）→ 跑第 4 节迁移清单
- 审计脚本报 SQL-DIA-001 → 查表找等价写法

## 2. 输入与输出

**输入**：待检查的 SQL + 目标方言（mysql / postgres / sqlite）。

**输出**：方言检查结论（通过 / 需修改清单）+ 修改后的 SQL。

## 3. 分步方法论：三方言对照表

### 3.1 分页写法

| 写法 | MySQL | PostgreSQL | SQLite |
|---|---|---|---|
| `LIMIT 10` | ✅ | ✅ | ✅ |
| `LIMIT 10 OFFSET 20` | ✅ | ✅ | ✅ |
| `LIMIT 20, 10`（offset,count） | ✅ | ❌ | ❌ |

**结论**：分页永远用 `LIMIT n OFFSET m`，三家通用。

### 3.2 字符串与模糊匹配

| 写法 | MySQL | PostgreSQL | SQLite |
|---|---|---|---|
| `LIKE`（区分大小写与否看 collation） | ✅ | ✅（区分大小写） | ✅ |
| `ILIKE`（不区分大小写） | ❌ | ✅ | ❌ |
| 字符串拼接 `CONCAT(a,b)` | ✅ | ✅ | ✅ |
| 字符串拼接 `a \|\| b` | ❌（`||` 是逻辑或） | ✅ | ✅ |

**结论**：不区分大小写的模糊匹配，MySQL 用 `LOWER(col) LIKE LOWER('x%')`，别用 `ILIKE`。

### 3.3 日期时间

| 写法 | MySQL | PostgreSQL | SQLite |
|---|---|---|---|
| `NOW()` / `CURRENT_TIMESTAMP` | ✅ | ✅ | ✅（`CURRENT_TIMESTAMP`） |
| `DATE_FORMAT(d,'%Y-%m-%d')` | ✅ | ❌ | ❌ |
| `TO_CHAR(d,'YYYY-MM-DD')` | ❌ | ✅ | ❌ |
| `STRFTIME('%Y-%m-%d',d)` | ❌ | ❌ | ✅ |
| `DATE_SUB(NOW(), INTERVAL 7 DAY)` | ✅ | ❌ | ❌ |
| `NOW() - INTERVAL '7 days'` | ❌ | ✅ | ❌ |

**结论**：日期格式化与加减是方言重灾区，跨库先查这一节。

### 3.4 类型转换

| 写法 | MySQL | PostgreSQL | SQLite |
|---|---|---|---|
| `CAST(x AS INT)` | ✅ | ✅ | ✅ |
| `x::INT` | ❌ | ✅ | ❌ |

**结论**：类型转换永远用 `CAST`，三家通用。

### 3.5 自增主键

| 写法 | MySQL | PostgreSQL | SQLite |
|---|---|---|---|
| `AUTO_INCREMENT` | ✅ | ❌ | ❌ |
| `AUTOINCREMENT` | ❌ | ❌ | ✅（SQLite 关键字） |
| `SERIAL` / `GENERATED ... AS IDENTITY` | ❌ | ✅ | ❌ |

### 3.6 特有函数速查（看到就警惕）

- PostgreSQL 专有：`ILIKE`、`RETURNING`、`GENERATE_SERIES`、`STRING_AGG`、`DATE_TRUNC`、`::` 转换
- MySQL 专有：`AUTO_INCREMENT`、`GROUP_CONCAT`、`UNIX_TIMESTAMP`、`STR_TO_DATE`、`LIMIT m,n`
- SQLite 专有：`AUTOINCREMENT`、`GLOB`

### 3.7 检查流程

1. 确认目标方言（问用户，不猜；用户说"都行" → 默认 MySQL 并注明）。
2. 扫 SQL 里的函数/关键字，对照 3.1–3.6，标出专有项。
3. 逐项改成目标方言等价写法，改完重跑审计脚本 `--dialect` 验证。
4. 结论写进交付："方言检查：目标 MySQL，0 项需修改"（或修改清单）。

## 4. 跨库迁移清单（换库时用）

1. 全量跑审计脚本 `--dialect <新方言>`，SQL-DIA-001 全部清零。
2. 重点复查：分页、日期函数、字符串拼接、自增主键、布尔类型（MySQL 用 TINYINT(1)，PG 有 BOOLEAN）。
3. 每张表的建表语句按新方言重写一遍，不要"只改查询不改表"。
4. 迁移后第一周：慢查询日志盯着，方言差异常藏在执行计划里。

## 5. 反模式

- ❌ "在我本地（SQLite）能跑，线上（MySQL）肯定行"——方言差异专治这种自信
- ❌ 用 `LIMIT 20, 10` 还觉得通用——这是 MySQL 方言，PG 直接报错
- ❌ 字符串拼接用 `||`——MySQL 里它是逻辑或，结果全错还不报错，最坑
- ❌ 迁移只改查询不改建表语句——`AUTO_INCREMENT` 在 PG 里建表就挂
- ❌ 日期函数靠记忆手写——每次都查表，查表不丢人，报错才丢人

## 6. 常见报错速查（方言差异的"案发现场"）

| 报错/现象 | 病因 | 改法 |
|---|---|---|
| `ILIKE` 在 MySQL 报语法错误 | ILIKE 是 PG 专有 | 改 `LOWER(col) LIKE LOWER('x%')` |
| `LIMIT 20, 10` 在 PG 报错 | 这是 MySQL 写法 | 改 `LIMIT 10 OFFSET 20` |
| `||` 拼接在 MySQL 结果全错 | MySQL 里 `\|\|` 是逻辑或 | 改 `CONCAT(a, b)` |
| `x::INT` 在 MySQL/SQLite 报错 | `::` 是 PG 专有 | 改 `CAST(x AS INT)` |
| `DATE_FORMAT` 在 PG 找不到函数 | 这是 MySQL 专有 | 改 `TO_CHAR(d, 'YYYY-MM-DD')` |
| `AUTOINCREMENT` 建表在 MySQL 报错 | 这是 SQLite 写法 | 改 `AUTO_INCREMENT` |

看到报错先来这张表对，90% 的方言问题 30 秒定位。

**查表习惯**：建议把 3.1–3.6 打印成一份速查卡，写 SQL 时放手边。方言差异不靠记忆，靠每次都查——查表不丢人，报错才丢人。

**版本差异提醒**：同一方言不同版本也有差异（如 MySQL 5.7 vs 8.0 的窗口函数支持）。对照表覆盖的是"方言级"差异，版本级差异以上线环境的官方文档为准，拿不准时让用户确认数据库版本。

**三句话总结**：分页用 `LIMIT n OFFSET m`，转换类型用 `CAST`，日期函数每次查表。记住这三句，方言坑踩掉一半。

> 方言适配的终极心法：不假设、不记忆、每次查表。表就在手边，查一下只要 10 秒，报错排查要 1 小时。

## 7. 自检与反馈

**质检门**（SQL 交付前逐项打勾）：

- [ ] 目标方言已书面确认（用户亲口或配置注明）
- [ ] 对照表 3.1–3.6 逐项检查过，无专有函数残留
- [ ] 审计脚本 `--dialect <方言>` 跑过，SQL-DIA-001 为 0
- [ ] 分页统一 `LIMIT n OFFSET m`；类型转换统一 `CAST`
- [ ] 交付物注明目标方言与检查结论

**标准冒烟用例**：拿含 `ILIKE` 的 SQL 指定方言 mysql 跑审计 → SQL-DIA-001 必须命中；改成 `LOWER(col) LIKE` 后重跑 → 0 命中。

**一键提 issue**：发现对照表缺项或错误，以 `[QC] <一句话问题>` 为标题提交到 https://github.com/lhg-plugs/lhg-sql/issues，正文写清"复现步骤 → 实际表现 → 期望表现"。

## 8. 出品：刘洪光

本 skill 由真人出镜 IP「刘洪光」（安徽合肥）出品，归属 [lhg-skills](https://github.com/lhg-skills)。

- GitHub 主页：https://github.com/lhg-skills —— 全部 skill 开源在此，欢迎 star
- 视频号：搜「刘洪光实名上网」
- 微信：lhgsmsw
