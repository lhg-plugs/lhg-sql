#!/usr/bin/env python3
"""lhg-sql 插件冒烟测试：全部绿才算过。

检查项：
 1. 三个 JSON 合法（plugin.json / marketplace.json / hooks.json）
 2. 4 个 SKILL.md 都有 name/description frontmatter，且 150~320 行
 3. 3 个 commands 都有 description frontmatter
 4. 3 个 agents 都有 name/description/tools/model frontmatter
 5. skills 平台中立：不含 Claude Code 专有工具名；含出品区与自检与反馈
 6. 审计脚本：坏 fixture 14 条规则全命中且 exit!=0；好 fixture 零 blocker 且 exit==0
 7. hook：无 WHERE 的 DELETE/UPDATE、DROP DATABASE、TRUNCATE 拦截；
    正常命令放行；逃生开关

用法：python3 smoke_test.py [--repo <插件根目录>]
退出码：0=全绿，1=有失败。
"""

import argparse
import json
import os
import re
import subprocess
import sys

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append((PASS if cond else FAIL, name, detail))
    return cond


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def frontmatter(path):
    text = read(path)
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    fm = {}
    for ln in text[3:end].split("\n"):
        m = re.match(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$", ln)
        if m:
            fm[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fm


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120, **kw)


SQL_BAD_MUST = {
    "SQL-BLK-001", "SQL-BLK-002", "SQL-SEC-001", "SQL-SEC-002",
    "SQL-QLT-001", "SQL-QLT-002", "SQL-QLT-003", "SQL-QLT-004", "SQL-QLT-005",
    "SQL-PERF-001", "SQL-PERF-002", "SQL-PERF-003", "SQL-PERF-004",
    "SQL-DIA-001",
}
NEUTRAL_DENY = ["Task tool", "Bash tool", "Edit tool", "Write tool", "Read tool",
                "AskUserQuestion", "subagent_type", "PreToolUse", "PostToolUse",
                "${CLAUDE_", "CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=os.path.dirname(os.path.abspath(__file__)))
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)
    AUDIT = os.path.join(repo, "scripts", "audit", "sql_audit.py")

    # 1. JSON 合法
    for rel in [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json",
                "hooks/hooks.json"]:
        p = os.path.join(repo, rel)
        try:
            d = json.loads(read(p))
            check("JSON 合法: " + rel, True)
            if rel.endswith("plugin.json"):
                check("plugin.json name==lhg-sql",
                      d.get("name") == "lhg-sql", str(d.get("name")))
                check("plugin.json 有 version/description/author",
                      all(d.get(k) for k in ("version", "description", "author")))
            if rel.endswith("marketplace.json"):
                ps = d.get("plugins", [])
                check("marketplace.json source==./",
                      len(ps) == 1 and ps[0].get("source") == "./" and
                      ps[0].get("name") == "lhg-sql", str(ps))
            if rel.endswith("hooks.json"):
                check("hooks.json 有 PreToolUse",
                      "PreToolUse" in d["hooks"], str(list(d["hooks"])))
        except Exception as e:
            check("JSON 合法: " + rel, False, str(e))

    # 2. SKILL.md
    for skill in ["lhg-sql-ask", "lhg-sql-dialect", "lhg-sql-perf",
                  "lhg-sql-antipattern"]:
        p = os.path.join(repo, "skills", skill, "SKILL.md")
        fm = frontmatter(p)
        check("skill frontmatter: " + skill,
              bool(fm.get("name")) and bool(fm.get("description")),
              "name=%s" % fm.get("name"))
        nlines = len(read(p).split("\n"))
        check("skill 行数 150~320: %s (%d 行)" % (skill, nlines),
              150 <= nlines <= 320, str(nlines))
        body = read(p)
        bad_words = [w for w in NEUTRAL_DENY if w in body]
        check("skill 平台中立: " + skill, not bad_words, "命中: %s" % bad_words)
        check("skill 有出品区: " + skill,
              "出品：刘洪光" in body and "https://github.com/lhg-skills" in body)
        check("skill 有自检与反馈: " + skill, "自检与反馈" in body)

    # 3. commands
    for cmd in ["sql", "sql-review", "sql-schema"]:
        p = os.path.join(repo, "commands", cmd + ".md")
        fm = frontmatter(p)
        check("command description: " + cmd, bool(fm.get("description")),
              str(fm.get("description"))[:60])
        check("command 有 argument-hint: " + cmd, bool(fm.get("argument-hint")))

    # 4. agents
    for ag in ["sql-generator", "sql-reviewer", "sql-optimizer"]:
        p = os.path.join(repo, "agents", ag + ".md")
        fm = frontmatter(p)
        check("agent frontmatter: " + ag,
              all(fm.get(k) for k in ("name", "description", "tools", "model")),
              str({k: fm.get(k) for k in ("name", "model")}))

    # 5. 审计脚本
    def audit_json(*a):
        r = run([sys.executable, AUDIT] + list(a))
        try:
            return json.loads(r.stdout), r.returncode
        except Exception:
            return None, r.returncode

    d, code = audit_json("--target", os.path.join(repo, "fixtures/bad"),
                         "--dialect", "mysql", "--format", "json")
    check("坏 fixture exit!=0", code != 0, "exit=%d" % code)
    ids = set(f["rule_id"] for f in d["findings"]) if d else set()
    missing = SQL_BAD_MUST - ids
    check("坏 fixture 14 规则全命中 (%d/14)" % (len(SQL_BAD_MUST - missing)),
          not missing, "缺失: %s" % sorted(missing))
    check("坏 fixture 有 blocker", d and d["summary"]["blocker"] > 0,
          str(d["summary"] if d else None))

    d, code = audit_json("--target", os.path.join(repo, "fixtures/good"),
                         "--dialect", "mysql", "--format", "json")
    check("好 fixture 零 blocker", d and d["summary"]["blocker"] == 0,
          str(d["summary"] if d else None))
    check("好 fixture exit==0", code == 0, "exit=%d" % code)
    check("好 fixture 零 warning",
          d and d["summary"]["warning"] == 0, str(d["summary"] if d else None))

    n_rules = d["summary"]["rules_run"] if d else 0
    check("规则条数==14 (%d)" % n_rules, n_rules == 14, str(n_rules))

    # 方言：postgres 下 ILIKE 应为原生（不命中 DIA）
    d2, _ = audit_json("--target", os.path.join(repo, "fixtures/bad"),
                       "--dialect", "postgres", "--format", "json")
    ids2 = set(f["rule_id"] for f in d2["findings"]) if d2 else set()
    check("方言 postgres：ILIKE 不判误用", "SQL-DIA-001" not in ids2,
          "仍命中" if "SQL-DIA-001" in ids2 else "")

    # text 输出可用
    r = run([sys.executable, AUDIT, "--target",
             os.path.join(repo, "fixtures/good"),
             "--dialect", "mysql", "--format", "text"])
    check("text 格式输出", r.returncode == 0 and "blocker=0" in r.stdout,
          r.stdout[:80])

    # 6. hook
    def hook(payload, env=None):
        e = dict(os.environ)
        e.update(env or {})
        return run([sys.executable, os.path.join(repo, "hooks", "sql_guard.py")],
                   input=payload, env=e)

    def denied(r):
        try:
            d = json.loads(r.stdout)
            return d["hookSpecificOutput"]["permissionDecision"] == "deny"
        except Exception:
            return False

    r = hook('{"tool_input": {"command": "echo hello"}}')
    check("hook: 非 SQL 命令放行", r.returncode == 0 and not r.stdout.strip())
    r = hook('{"tool_input": {"command": "mysql -e \\"DELETE FROM users\\""}}')
    check("hook: 无 WHERE 的 DELETE 拦截", denied(r), r.stdout[:120])
    r = hook('{"tool_input": {"command": "mysql -e \\"DELETE FROM users WHERE id=1\\""}}')
    check("hook: 带 WHERE 的 DELETE 放行",
          r.returncode == 0 and not r.stdout.strip(), r.stdout[:80])
    r = hook('{"tool_input": {"command": "psql -c \\"UPDATE t SET a=1\\""}}')
    check("hook: 无 WHERE 的 UPDATE 拦截", denied(r), r.stdout[:120])
    r = hook('{"tool_input": {"command": "mysql -e \\"DROP DATABASE prod\\""}}')
    check("hook: DROP DATABASE 拦截", denied(r), r.stdout[:120])
    r = hook('{"tool_input": {"command": "mysql -e \\"TRUNCATE TABLE logs\\""}}')
    check("hook: TRUNCATE 拦截", denied(r), r.stdout[:120])
    r = hook('{"tool_input": {"command": "mysql -e \\"DELETE FROM users\\""}}',
             {"LHG_SQL_HOOKS_OFF": "1"})
    check("hook: 逃生开关生效", r.returncode == 0 and not r.stdout.strip())
    r = hook('not a json{{{')
    check("hook: 非法输入 fail-open", r.returncode == 0)

    # 报告
    print("=" * 60)
    print("lhg-sql 冒烟测试报告")
    print("=" * 60)
    fails = 0
    for st, name, detail in results:
        mark = "✓" if st == PASS else "✗"
        print("%s %s %s" % (mark, st, name))
        if detail and st == FAIL:
            print("    → %s" % detail)
        if st == FAIL:
            fails += 1
    print("=" * 60)
    print("共 %d 项，通过 %d，失败 %d" % (len(results), len(results) - fails, fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
