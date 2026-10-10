#!/usr/bin/env python3
"""lhg-sql 确定性 SQL 审计：14 条规则，零第三方依赖。

扫描目标目录的 .sql 文件与 Python 代码中的 SQL 用法：
  - blocker：缺 WHERE 的 UPDATE/DELETE、DROP/TRUNCATE、SQL 拼接注入、硬编码凭证
  - warning：SELECT *、全表扫描、前导 LIKE、N+1、无 LIMIT、方言误用、笛卡尔积
  - nit：WHERE 1=1、无列名 INSERT、ORDER BY 序数

用法：
    python3 sql_audit.py --target <目录> [--format json|text]
        [--fail-on blocker|warning|nit] [--dialect mysql|postgres|sqlite]

有 blocker 时以 exit code 2 退出（供 hooks 与 CI 使用）。
--dialect 指定方言后启用方言函数误用检查；不指定时只检查 PG/MySQL 混用。

规则文案均为本项目原创（方言差异事实依据为各数据库官方文档，
未复制任何第三方原文）。
"""

import argparse
import json
import os
import re
import sys

VERSION = "1.0.0"
TOOL = "lhg-sql/audit"

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", "dist", "build", "venv", ".venv",
    "fixtures", "tests", "test",
}
SCAN_EXTS = {".sql", ".py"}


class Finding:
    __slots__ = ("rule_id", "severity", "category", "title", "file", "line",
                 "snippet", "detail")

    def __init__(self, rule_id, severity, category, title, file, line,
                 snippet, detail):
        self.rule_id = rule_id
        self.severity = severity
        self.category = category
        self.title = title
        self.file = file
        self.line = line
        self.snippet = snippet
        self.detail = detail

    def to_dict(self):
        return {
            "rule_id": self.rule_id, "severity": self.severity,
            "category": self.category, "title": self.title,
            "file": self.file, "line": self.line,
            "snippet": self.snippet, "detail": self.detail,
        }


class Ctx:
    def __init__(self, path, text, dialect):
        self.path = path
        self.text = text
        self.lines = text.split("\n")
        self.dialect = dialect
        self.findings = []

    def add(self, rule_id, severity, category, title, line, snippet, detail):
        self.findings.append(Finding(rule_id, severity, category, title,
                                     self.path, line, snippet.strip()[:160],
                                     detail))


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def collect_files(target):
    out = []
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            _, ext = os.path.splitext(f)
            if ext in SCAN_EXTS:
                out.append(os.path.join(root, f))
    return sorted(out)


# ---------------------------------------------------------------- SQL 切分

def strip_comments(sql):
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--[^\n]*", " ", sql)
    return sql


def split_statements(text):
    """按分号切分语句（启发式：忽略引号内的分号），返回 [(起始行号, 语句)]。"""
    stmts = []
    buf, start_line, line = [], 1, 1
    in_str, q = False, ""
    for ch in text:
        if ch == "\n":
            line += 1
        if in_str:
            buf.append(ch)
            if ch == q:
                in_str = False
        elif ch in ("'", '"', "`"):
            in_str, q = True, ch
            buf.append(ch)
        elif ch == ";" and not in_str:
            s = "".join(buf).strip()
            if s:
                stmts.append((start_line, s))
            buf, start_line = [], line
        else:
            buf.append(ch)
    s = "".join(buf).strip()
    if s:
        stmts.append((start_line, s))
    return stmts


# ---------------------------------------------------------------- 方言函数表

PG_ONLY = [
    (re.compile(r"\bILIKE\b", re.I), "ILIKE"),
    (re.compile(r"::\s*(text|int|integer|timestamp|date|jsonb|numeric)\b", re.I), ":: 类型转换"),
    (re.compile(r"\bRETURNING\b", re.I), "RETURNING"),
    (re.compile(r"\bGENERATE_SERIES\b", re.I), "GENERATE_SERIES"),
    (re.compile(r"\bSTRING_AGG\b", re.I), "STRING_AGG"),
    (re.compile(r"\bDATE_TRUNC\b", re.I), "DATE_TRUNC"),
]
MYSQL_ONLY = [
    (re.compile(r"\bAUTO_INCREMENT\b", re.I), "AUTO_INCREMENT"),
    (re.compile(r"\bGROUP_CONCAT\b", re.I), "GROUP_CONCAT"),
    (re.compile(r"\bUNIX_TIMESTAMP\b", re.I), "UNIX_TIMESTAMP"),
    (re.compile(r"\bSTR_TO_DATE\b", re.I), "STR_TO_DATE"),
    (re.compile(r"\bLIMIT\s+\d+\s*,\s*\d+", re.I), "LIMIT offset,count 写法"),
]
SQLITE_ONLY = [
    (re.compile(r"\bAUTOINCREMENT\b", re.I), "AUTOINCREMENT"),
    (re.compile(r"\bGLOB\b", re.I), "GLOB"),
]

DIALECT_TABLE = {"postgres": PG_ONLY, "mysql": MYSQL_ONLY, "sqlite": SQLITE_ONLY}


def foreign_functions(text, dialect):
    """返回不属于指定方言的函数命中 [(方言名, 函数名)]。"""
    hits = []
    for dname, table in DIALECT_TABLE.items():
        if dname == dialect:
            continue
        for pat, label in table:
            if pat.search(text):
                hits.append((dname, label))
    return hits


# ---------------------------------------------------------------- 规则定义

RULES = []


def rule(rule_id, severity, category, title, detail):
    def deco(fn):
        RULES.append({
            "id": rule_id, "severity": severity, "category": category,
            "title": title, "detail": detail, "check": fn,
        })
        return fn
    return deco


def is_sql_file(ctx):
    return ctx.path.endswith(".sql")


def sql_statements(ctx):
    return split_statements(strip_comments(ctx.text))


@rule("SQL-BLK-001", "blocker", "安全",
      "UPDATE/DELETE 缺 WHERE 条件",
      "没有 WHERE 的 UPDATE/DELETE 会改掉/删掉整表。这是取数场景最贵的误操作：先写 SELECT 验证条件，再改成 UPDATE/DELETE。")
def _r_blk_001(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        up = stmt.upper()
        if re.match(r"\s*UPDATE\b", up, re.I) and not re.search(r"\bWHERE\b", up, re.I):
            ctx.add("SQL-BLK-001", "blocker", "安全", "UPDATE 缺 WHERE 条件",
                    lineno, stmt, "补上 WHERE；先用 SELECT <条件> 确认影响行数。")
        if re.match(r"\s*DELETE\s+FROM\b", up, re.I) and not re.search(r"\bWHERE\b", up, re.I):
            ctx.add("SQL-BLK-001", "blocker", "安全", "DELETE 缺 WHERE 条件",
                    lineno, stmt, "补上 WHERE；先用 SELECT <条件> 确认影响行数。")


@rule("SQL-BLK-002", "blocker", "安全",
      "破坏性操作：DROP / TRUNCATE",
      "DROP DATABASE/TABLE 与 TRUNCATE 不可逆。取数场景不应该出现这些语句；出现在脚本里一律 blocker，先确认再谈。")
def _r_blk_002(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        m = re.search(r"\b(DROP\s+(DATABASE|SCHEMA|TABLE)|TRUNCATE\s+(TABLE\s+)?)\s*(\w+)?",
                      stmt, re.I)
        if m:
            ctx.add("SQL-BLK-002", "blocker", "安全",
                    "破坏性操作：%s" % m.group(1).strip().upper(),
                    lineno, stmt, "取数不需要 DROP/TRUNCATE。如确需执行，走人工审批，不走脚本。")


@rule("SQL-SEC-001", "blocker", "安全",
      "SQL 字符串拼接（注入风险）",
      "用 f-string / format / % / + 拼接把变量拼进 SQL，是 SQL 注入的经典来源。改成参数化查询（占位符 %s / ? / :name），变量只当参数传。")
def _r_sec_001(ctx):
    if is_sql_file(ctx):
        return
    for i, ln in enumerate(ctx.lines, 1):
        has_sql_kw = re.search(r"\b(SELECT|INSERT|UPDATE|DELETE)\b", ln, re.I)
        if not has_sql_kw:
            continue
        concat = (
            re.search(r"""f['"]""", ln) and "{" in ln,           # f-string 插值
            bool(re.search(r"""\.format\s*\(""", ln)),            # .format(
            bool(re.search(r"""['"]\s*%\s*(\(|\w)""", ln)),      # "..." % var / % (var,)
            bool(re.search(r"""['"]\s*\+\s*\w+""", ln)),        # ' + var
        )
        if any(concat):
            ctx.add("SQL-SEC-001", "blocker", "安全", "SQL 字符串拼接（注入风险）",
                    i, ln, "改参数化查询：cursor.execute(sql, (var,))，变量不进 SQL 文本。")


@rule("SQL-SEC-002", "blocker", "安全",
      "硬编码数据库凭证",
      "代码里直接写了数据库密码/API Key。换成环境变量或密钥管理，绝不进代码仓库。")
def _r_sec_002(ctx):
    if is_sql_file(ctx):
        return
    cred_re = re.compile(
        r"""(?i)\b(password|passwd|pwd|api[_-]?key|secret[_-]?key)\b"""
        r"""\s*[:=]\s*['"][^'"]{3,}['"]"""
    )
    for i, ln in enumerate(ctx.lines, 1):
        if cred_re.search(ln):
            ctx.add("SQL-SEC-002", "blocker", "安全", "硬编码数据库凭证", i, ln,
                    "凭证改走环境变量读取，当前明文必须删除并轮换已泄露的凭证。")


@rule("SQL-QLT-001", "warning", "规范",
      "SELECT * 全列查询",
      "SELECT * 把不需要的列也拉回来：浪费带宽、表加列就可能打崩下游。显式写出需要的列名。")
def _r_qlt_001(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        if re.search(r"\bSELECT\s+\*", stmt, re.I) and \
                not re.search(r"\bCOUNT\s*\(\s*\*\s*\)", stmt, re.I):
            ctx.add("SQL-QLT-001", "warning", "规范", "SELECT * 全列查询",
                    lineno, stmt, "显式列出需要的列；COUNT(*) 不受此条限制。")


@rule("SQL-PERF-001", "warning", "性能",
      "无 WHERE 的全表扫描风险",
      "SELECT 带 FROM 却无 WHERE，大概率全表扫描。确认是业务需要（如全量导出），否则补条件；大表务必先看执行计划。")
def _r_perf_001(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        up = stmt.upper()
        if re.search(r"\bSELECT\b", up) and re.search(r"\bFROM\b", up) \
                and not re.search(r"\bWHERE\b", up) \
                and not re.match(r"\s*(UPDATE|DELETE|INSERT)", up):
            ctx.add("SQL-PERF-001", "warning", "性能", "无 WHERE 的全表扫描风险",
                    lineno, stmt, "补 WHERE 条件，或确认全量是业务所需并加 LIMIT。")


@rule("SQL-PERF-002", "warning", "性能",
      "前导通配符 LIKE（索引失效）",
      "LIKE '%关键词' 前导通配符用不上索引，大表上就是全表扫描。改后置通配符、前缀索引或全文检索。")
def _r_perf_002(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        if re.search(r"\bLIKE\s+['\"]%", stmt, re.I):
            ctx.add("SQL-PERF-002", "warning", "性能", "前导通配符 LIKE（索引失效）",
                    lineno, stmt, "确需模糊搜索用全文索引；否则改 '关键词%' 后置通配符。")


@rule("SQL-PERF-003", "warning", "性能",
      "循环内执行 SQL（N+1 模式）",
      "在 for/while 循环里调 cursor.execute()：循环 1 万次 = 1 万次查询。改成一次 IN 查询或 JOIN，循环里只做内存处理。")
def _r_perf_003(ctx):
    if is_sql_file(ctx):
        return
    in_loop, loop_line = False, 0
    for i, ln in enumerate(ctx.lines, 1):
        if re.match(r"\s*(for|while)\b", ln):
            in_loop, loop_line = True, i
        if in_loop and re.search(r"\.execute\s*\(", ln):
            ctx.add("SQL-PERF-003", "warning", "性能", "循环内执行 SQL（N+1 模式）",
                    i, ln, "循环（第 %d 行起）内执行查询：改 WHERE id IN (...) 一次查回。" % loop_line)
            in_loop = False  # 每个循环只报一次


@rule("SQL-PERF-004", "warning", "性能",
      "查询无 LIMIT 限制",
      "SELECT 无 LIMIT/TOP/FETCH，第一页就要全量结果。取数先加 LIMIT 100 验证逻辑，确认无误再放开。")
def _r_perf_004(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        up = stmt.upper()
        if re.search(r"\bSELECT\b", up) and re.search(r"\bFROM\b", up) \
                and not re.search(r"\b(LIMIT|TOP\s+\d|FETCH\s+FIRST)\b", up):
            ctx.add("SQL-PERF-004", "warning", "性能", "查询无 LIMIT 限制",
                    lineno, stmt, "先加 LIMIT 100 跑通逻辑；全量导出走分页或流式。")


@rule("SQL-DIA-001", "warning", "方言",
      "方言函数误用/混用",
      "用了当前方言不支持的函数（如 MySQL 里用 PostgreSQL 的 ILIKE/::/RETURNING）。上线前按目标方言逐个核对，跨库迁移时重点查这一项。")
def _r_dia_001(ctx):
    if not is_sql_file(ctx):
        return
    text = strip_comments(ctx.text)
    if ctx.dialect:
        hits = foreign_functions(text, ctx.dialect)
        for dname, label in hits:
            ctx.add("SQL-DIA-001", "warning", "方言",
                    "方言误用：%s 是 %s 的函数，当前方言 %s 不支持"
                    % (label, dname, ctx.dialect), 1, label,
                    "换成 %s 的等价写法。" % ctx.dialect)
    else:
        pg = any(p.search(text) for p, _ in PG_ONLY)
        my = any(p.search(text) for p, _ in MYSQL_ONLY)
        if pg and my:
            ctx.add("SQL-DIA-001", "warning", "方言", "疑似混用 PG 与 MySQL 函数",
                    1, "", "同一文件出现两家方言专有函数，确认目标库后统一。")


@rule("SQL-QLT-002", "warning", "规范",
      "笛卡尔积风险",
      "FROM 后逗号连接多表且无关联条件，或显式 CROSS JOIN，会产生笛卡尔积。改显式 JOIN ... ON，或确认就是要做交叉。")
def _r_qlt_002(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        if re.search(r"\bCROSS\s+JOIN\b", stmt, re.I):
            ctx.add("SQL-QLT-002", "warning", "规范", "显式 CROSS JOIN（笛卡尔积）",
                    lineno, stmt, "确认业务就是要交叉；否则改 JOIN ... ON。")
        elif re.search(r"\bFROM\s+\w+(\s+\w+)?\s*,\s*\w+", stmt, re.I):
            ctx.add("SQL-QLT-002", "warning", "规范", "逗号连接多表（疑似笛卡尔积）",
                    lineno, stmt, "改显式 JOIN ... ON 写法，关联条件一目了然。")


@rule("SQL-QLT-003", "nit", "规范",
      "WHERE 1=1 恒真条件",
      "WHERE 1=1 通常是动态拼接 SQL 的占位残留。静态 SQL 里删掉它；动态拼接改用参数化。")
def _r_qlt_003(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        if re.search(r"\bWHERE\s+1\s*=\s*1\b", stmt, re.I):
            ctx.add("SQL-QLT-003", "nit", "规范", "WHERE 1=1 恒真条件",
                    lineno, stmt, "删掉恒真条件，保持 SQL 干净。")


@rule("SQL-QLT-004", "nit", "规范",
      "INSERT 未指定列名",
      "INSERT INTO t VALUES (...) 不写列名：表加列就错位。显式写出列名， schema 变更时不翻车。")
def _r_qlt_004(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        if re.search(r"\bINSERT\s+INTO\s+\w+\s+VALUES\b", stmt, re.I):
            ctx.add("SQL-QLT-004", "nit", "规范", "INSERT 未指定列名",
                    lineno, stmt, "改成 INSERT INTO t (a, b) VALUES (...)。")


@rule("SQL-QLT-005", "nit", "规范",
      "ORDER BY 用序数",
      "ORDER BY 1 按第一列排序：SELECT 加列就悄悄变了语义。写列名，意图明确。")
def _r_qlt_005(ctx):
    if not is_sql_file(ctx):
        return
    for lineno, stmt in sql_statements(ctx):
        if re.search(r"\bORDER\s+BY\s+\d+", stmt, re.I):
            ctx.add("SQL-QLT-005", "nit", "规范", "ORDER BY 用序数",
                    lineno, stmt, "改成 ORDER BY 列名。")


# ---------------------------------------------------------------- 主流程

SEVERITY_ORDER = {"blocker": 0, "warning": 1, "nit": 2}


def run_target_audit(target, dialect=None):
    findings = []
    for path in collect_files(target):
        text = read_text(path)
        if not text.strip():
            continue
        ctx = Ctx(path, text, dialect)
        for r in RULES:
            try:
                r["check"](ctx)
            except Exception:
                continue
        findings.extend(f.to_dict() for f in ctx.findings)
    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), f["file"]))
    return findings


def summarize(findings):
    s = {"blocker": 0, "warning": 0, "nit": 0, "rules_run": len(RULES)}
    for f in findings:
        if f["severity"] in s:
            s[f["severity"]] += 1
    return s


def main(argv=None):
    ap = argparse.ArgumentParser(description="lhg-sql 确定性 SQL 审计")
    ap.add_argument("--target", required=True, help="SQL/代码目录")
    ap.add_argument("--format", choices=["json", "text"], default="text")
    ap.add_argument("--fail-on", choices=["blocker", "warning", "nit"],
                    default="blocker")
    ap.add_argument("--dialect", choices=["mysql", "postgres", "sqlite"],
                    default=None, help="目标方言，启用方言函数误用检查")
    args = ap.parse_args(argv)

    findings = run_target_audit(args.target, args.dialect)
    summary = summarize(findings)
    if args.format == "json":
        print(json.dumps({"tool": TOOL, "version": VERSION,
                          "summary": summary, "findings": findings},
                         ensure_ascii=False, indent=2))
    else:
        print("== %s v%s ==" % (TOOL, VERSION))
        print("blocker=%d warning=%d nit=%d（规则 %d 条）" % (
            summary["blocker"], summary["warning"], summary["nit"],
            summary["rules_run"]))
        for f in findings:
            print("[%s][%s] %s:%s %s" % (
                f["severity"], f["rule_id"], f["file"], f["line"], f["title"]))
            print("    %s" % f["detail"])
    order = SEVERITY_ORDER
    bad = any(order.get(f["severity"], 9) <= order[args.fail_on]
              for f in findings)
    return 2 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
