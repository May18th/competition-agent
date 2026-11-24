#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""线上只读验证：用待部署的清理链跑真实历史正文，对比新旧效果。

只 import 补丁文件、只读数据库，不写库、不重启服务。
"""
import importlib.util
import json
import re
import sqlite3
import sys

sys.path.insert(0, "/opt/comp-agent")   # 脚本在 /tmp 下执行，需让扁平模块可导入
DB = "/opt/comp-agent/competition.db"
PATCHED = "/opt/comp-agent/_agents_cleanup_tmp.py"

spec = importlib.util.spec_from_file_location("ca_new", PATCHED)
ca = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ca)          # 只加载函数定义，不发任何请求

FIELDS = ("proposal", "proposal_outline", "judge_feedback", "proposal_analysis",
          "project_summary", "social_value", "tech_solution", "competitor_analysis",
          "business_model", "risk_analysis", "implementation_plan", "defense_questions",
          "ppt_outline", "speech_script", "parsed_rules", "similarity_report", "one_liner")

PLACEHOLDER = re.compile(r"【[^】]*】|待你填写|待补充|(?<![A-Za-z])TBD|(?<![A-Za-z])TODO")
CLICHE_WORDS = ("赋能", "闭环", "抓手", "进一步提升", "不断完善", "积极探索", "高度重视", "显著提高")
REVISION = re.compile(r"^\s*(?:#{1,3}\s*)?(?:修订说明|修改说明|本次修订|本次修改)", re.M)
PENDING = re.compile(r"^#{1,6}\s+.*(?:待(?:替换|补充|核实)|需替换)", re.M)


def old_chain(t):
    return ca._strip_fabricated_times(ca._downgrade_fabrication(
        ca._strip_placeholders(ca._dedupe_consecutive(t))))


def new_chain(t):
    return ca._strip_cliches(ca._strip_ai_artifacts(ca._fix_mislabeled_measured(
        ca._strip_fabricated_times(ca._downgrade_fabrication(
            ca._strip_placeholders(ca._dedupe_consecutive(
                ca._strip_pending_sections(ca._strip_revision_note(t)))))))))


def main():
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "SELECT id, mode, result_data FROM history ORDER BY id DESC LIMIT 40").fetchall()

    stat = {"records": 0, "cliche_before": 0, "cliche_after": 0,
            "ph_before": 0, "ph_after": 0, "rev_before": 0, "rev_after": 0,
            "pending_before": 0, "pending_after": 0,
            "changed": 0, "shrink": [], "warnings": []}

    for hid, mode, data in rows:
        try:
            rec = json.loads(data or "{}")
        except Exception:
            continue
        proposal = rec.get("proposal") or ""
        if not proposal.strip():
            continue
        stat["records"] += 1

        before_all = "\n".join(str(rec.get(k) or "") for k in FIELDS)
        after = {}
        for k in FIELDS:
            v = rec.get(k)
            if isinstance(v, str) and v:
                after[k] = new_chain(v)
        after_all = "\n".join(after.get(k, "") for k in FIELDS)

        stat["cliche_before"] += sum(before_all.count(w) for w in CLICHE_WORDS)
        stat["cliche_after"] += sum(after_all.count(w) for w in CLICHE_WORDS)
        stat["ph_before"] += len(PLACEHOLDER.findall(before_all))
        stat["ph_after"] += len(PLACEHOLDER.findall(after_all))
        stat["rev_before"] += len(REVISION.findall(rec.get("proposal") or ""))
        stat["rev_after"] += len(REVISION.findall(after.get("proposal", "")))
        stat["pending_before"] += len(PENDING.findall(rec.get("proposal") or ""))
        stat["pending_after"] += len(PENDING.findall(after.get("proposal", "")))

        if after_all != before_all:
            stat["changed"] += 1
            p0, p1 = proposal, after.get("proposal", proposal)
            stat["shrink"].append((hid, mode, len(p0), len(p1)))

        # 安全检查：正文被删到不足原文 60% 视为异常，逐条列出
        p1 = after.get("proposal", proposal)
        if len(proposal) > 500 and len(p1) < len(proposal) * 0.6:
            stat["warnings"].append((hid, mode, len(proposal), len(p1)))

    print("样本 %d 条历史记录" % stat["records"])
    print("套话词   %d -> %d" % (stat["cliche_before"], stat["cliche_after"]))
    print("占位符   %d -> %d" % (stat["ph_before"], stat["ph_after"]))
    print("修订说明 %d -> %d" % (stat["rev_before"], stat["rev_after"]))
    print("待办章节 %d -> %d" % (stat["pending_before"], stat["pending_after"]))
    print("有改动的记录 %d 条" % stat["changed"])
    print("\n正文长度前 8 个变化（hid, mode, 原 -> 现）:")
    for w in stat["shrink"][:8]:
        print("  %s %-4s %d -> %d (%+d)" % (w[0], w[1], w[2], w[3], w[3] - w[2]))
    if stat["warnings"]:
        print("\n⚠ 正文缩水超过 40%%（需人工确认）:")
        for w in stat["warnings"]:
            print("  hid=%s %s %d -> %d" % w)
    else:
        print("\n无异常缩水（>40% 的删减为零）")


if __name__ == "__main__":
    main()
