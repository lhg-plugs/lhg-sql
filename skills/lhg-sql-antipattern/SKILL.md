---
name: lhg-sql-antipattern
description: SQL反模式图鉴：SELECT */N+1/笛卡尔积/前导LIKE/无WHERE更新等12种经典坑，附"闻到味道→确诊→改法"。
license: MIT
compatibility: 适用于任何支持 Markdown 指令的 AI 编程助手
metadata:
  version: 1.0.0
  author: 刘洪光
---

# lhg-sql-antipattern：SQL 反模式图鉴

目标：把"我踩过的坑"变成"一眼认出"。每个反模式按"味道 → 确诊 → 改法"三段写，看到味道就能开药方。

## 1. 何时使用

- 写 SQL 时对照自查 → 重点看第 3 节
- 评审别人的 SQL → 按图鉴逐条过
- 慢查询定位 → 先看性能类（P1–P4）

## 2. 输入与输出

**输入**：待评审的 SQL。

**输出**：命中的反模式清单（编号+改法），无命中则写"本次未发现反模式"。

## 3. 分步方法论：反模式图鉴

### 安全类（见一个修一个）

**S1：无 WHERE 的 UPDATE/DELETE**

- 味道：`UPDATE t SET ...;` 结尾没有 WHERE
- 确诊：审计脚本 SQL-BLK-001
- 改法：补 WHERE；先写 `SELECT ... WHERE <条件>` 确认影响行数，再改成 UPDATE/DELETE

**S2：SQL 拼接**

- 味道：代码里 `f"SELECT ... {var}"` / `"..." + var` / `"..." % var`
- 确诊：审计脚本 SQL-SEC-001
- 改法：参数化查询，`cursor.execute(sql, (var,))`，变量不进 SQL 文本

**S3：硬编码凭证**

- 味道：`password = "xxxx"` 写在代码里
- 确诊：审计脚本 SQL-SEC-002
- 改法：环境变量；已泄露的凭证立即轮换

### 性能类（数据量越大越疼）

**P1：SELECT ***

- 味道：`SELECT * FROM`
- 确诊：审计脚本 SQL-QLT-001
- 改法：显式列出需要的列（`COUNT(*)` 例外）

**P2：N+1 查询**

- 味道：`for` 循环里 `cursor.execute(...)`
- 确诊：审计脚本 SQL-PERF-003
- 改法：一次 `WHERE id IN (...)` 查回，循环只做内存处理；或改 JOIN

**P3：前导通配符 LIKE**

- 味道：`LIKE '%关键词'`
- 确诊：审计脚本 SQL-PERF-002
- 改法：后置通配符 `'关键词%'`，或全文索引

**P4：无 LIMIT 的大查询**

- 味道：`SELECT ... FROM ...` 没有 LIMIT，表是百万级
- 确诊：审计脚本 SQL-PERF-004
- 改法：先 `LIMIT 100` 验证逻辑；全量走分页或流式导出

**P5：笛卡尔积**

- 味道：`FROM a, b` 或 `CROSS JOIN`，无关联条件
- 确诊：审计脚本 SQL-QLT-002
- 改法：显式 `JOIN ... ON`；确认就是要交叉时在注释写清原因

### 规范类（今天不疼，明天疼）

**N1：WHERE 1=1**

- 味道：`WHERE 1=1 AND ...`
- 确诊：审计脚本 SQL-QLT-003
- 改法：删掉；动态拼接改参数化

**N2：INSERT 不写列名**

- 味道：`INSERT INTO t VALUES (...)`
- 确诊：审计脚本 SQL-QLT-004
- 改法：`INSERT INTO t (a, b) VALUES (...)`

**N3：ORDER BY 序数**

- 味道：`ORDER BY 1`
- 确诊：审计脚本 SQL-QLT-005
- 改法：`ORDER BY 列名`

**N4：方言函数误用**

- 味道：MySQL 里出现 `ILIKE` / `::` / `RETURNING`
- 确诊：审计脚本 SQL-DIA-001（`--dialect` 指定后）
- 改法：查 `lhg-sql-dialect` 对照表换等价写法

## 4. 三个最贵的事故复盘（记住味道）

**事故一：少了 WHERE，全表涨价**

- 经过：`UPDATE products SET price = price * 0.9;` 忘了加 `WHERE id IN (...)`，全场商品打九折。
- 味道：UPDATE 结尾没有 WHERE（S1）。
- 教训：写操作先 SELECT 验证影响行数，是铁律不是建议。

**事故二：f-string 里的单引号**

- 经过：`f"SELECT ... WHERE name = '{name}'"`，用户输入 `o'brien`，SQL 直接报错；换成恶意输入就是注入。
- 味道：f-string 拼 SQL（S2）。
- 教训：变量永远只当参数传，不进 SQL 文本。

**事故三：循环里查了 3 万次**

- 经过：`for id in ids: cursor.execute(...)`，3 万个 id 跑了 40 分钟，改成 `WHERE id IN (...)` 后 3 秒。
- 味道：循环内 execute（P2）。
- 教训：N+1 在小数据量时"感觉还行"，正是改掉它的最好时机。

## 5. 反模式

- ❌ "这个 SQL 能跑，反模式以后再改"——S 类反模式没有"以后"，上线就是事故
- ❌ 只记改法不记味道——下次换个马甲（`WHERE 2=2`）又认不出来
- ❌ "小表无所谓"当口头禅——小表会长大，习惯不会自己变好
- ❌ 评审时只看逻辑不看写法——逻辑对但 S2 拼接，上线照样被注入
- ❌ 图鉴背下来就觉得自己不会踩坑——味道是用来"闻"的，不是用来"背"的，写完对照过一遍才算数

## 6. 自检与反馈

**质检门**（评审结论发布前逐项打勾）：

- [ ] 安全类 S1–S3 逐条确认无命中（有命中直接判不通过）
- [ ] 性能类 P1–P5 结合数据量级逐条确认（小表可豁免，写理由）
- [ ] 规范类 N1–N4 顺手修掉
- [ ] 审计脚本跑过，结论与人工评审一致（不一致时以更严的为准）

**标准冒烟用例**：用本仓库 `fixtures/bad/bad.sql` 对照图鉴 → 应命中 S1、P1、P3、P5、N1、N2、N3、N4 共 8 类；用 `fixtures/good/good.sql` → 0 命中。

**一键提 issue**：发现新反模式或图鉴错误，以 `[QC] <一句话问题>` 为标题提交到 https://github.com/lhg-plugs/lhg-sql/issues，正文写清"复现步骤 → 实际表现 → 期望表现"。

## 7. 出品：刘洪光

本 skill 由真人出镜 IP「刘洪光」（安徽合肥）出品，归属 [lhg-skills](https://github.com/lhg-skills)。

- GitHub 主页：https://github.com/lhg-skills —— 全部 skill 开源在此，欢迎 star
- 视频号：搜「刘洪光实名上网」
- 微信：lhgsmsw
