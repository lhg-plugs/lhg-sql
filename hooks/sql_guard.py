#!/usr/bin/env python3
"""lhg-sql 硬门：拦截危险 SQL 执行命令。

触发：PreToolUse / Bash。扫描本次 Bash 命令中的 SQL 文本，发现以下情况
直接拦截（deny）：
  - DROP DATABASE / DROP SCHEMA
  - TRUNCATE（不可逆清表）
  - DELETE FROM <表> 无 WHERE（到语句结束/分号前无 WHERE）
  - UPDATE <表> SET ... 无 WHERE

逃生方式（按推荐度排序）：
  1. 给 DELETE/UPDATE 补上 WHERE 后重新执行（推荐）。
  2. 紧急情况：LHG_SQL_HOOKS_OFF=1（环境变量，单次豁免本次 hook）。
  3. /plugin disable lhg-sql（整个插件停用，hooks 不再触发）。

设计原则：快速放行非目标事件（无 SQL 关键词的命令零开销通过）；
内部出错 fail-open 直接放行，不因插件自身故障骚扰用户；
零第三方依赖。
"""

import json
import os
import re
import sys

DENY_RES = [
    (re.compile(r"(?i)\bDROP\s+(DATABASE|SCHEMA)\b"), "DROP DATABASE/SCHEMA"),
    (re.compile(r"(?i)\bTRUNCATE\b"), "TRUNCATE"),
]


def _span_has_where(text, start):
    """从 start 起到下一个分号（或结尾）之间是否有 WHERE。"""
    end = text.find(";", start)
    span = text[start:end if end != -1 else len(text)]
    return bool(re.search(r"(?i)\bWHERE\b", span))


def find_no_where(cmd):
    """返回 [(类型, 片段)]：无 WHERE 的 DELETE/UPDATE。"""
    hits = []
    for m in re.finditer(r"(?i)\bDELETE\s+FROM\s+[\w.]+", cmd):
        if not _span_has_where(cmd, m.end()):
            hits.append(("DELETE", cmd[m.start():m.end() + 30].split(";")[0]))
    for m in re.finditer(r"(?i)\bUPDATE\s+[\w.]+\s+SET\b", cmd):
        if not _span_has_where(cmd, m.end()):
            hits.append(("UPDATE", cmd[m.start():m.end() + 30].split(";")[0]))
    return hits


def main() -> int:
    # 逃生开关
    if os.environ.get("LHG_SQL_HOOKS_OFF") == "1":
        return 0

    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return 0  # 输入解析失败：fail-open

    tool_input = payload.get("tool_input", {}) or {}
    command = tool_input.get("command", "") or ""
    if not command:
        return 0

    # 非目标事件：无 SQL 关键词快速放行
    if not re.search(r"(?i)\b(SELECT|INSERT|UPDATE|DELETE|DROP|TRUNCATE)\b", command):
        return 0

    reasons = []
    for pat, label in DENY_RES:
        if pat.search(command):
            reasons.append("检测到 %s：不可逆的破坏性操作，已拦截。" % label)
    for typ, snippet in find_no_where(command):
        reasons.append(
            "检测到无 WHERE 的 %s（%s…）：会改掉/删掉整表，已拦截。"
            "请补上 WHERE 条件后重新执行。" % (typ, snippet.strip()[:60]))

    if not reasons:
        return 0

    lines = [
        "危险 SQL 被 lhg-sql 硬门拦截：",
        "",
    ]
    lines += ["- " + r for r in reasons]
    lines += [
        "",
        "修复方式：给 DELETE/UPDATE 补上 WHERE（先 SELECT 验证影响行数）；",
        "紧急豁免（单次）：LHG_SQL_HOOKS_OFF=1 <原命令>",
    ]
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "\n".join(lines),
        }
    }
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
