#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把本地清理链的 5 个缺失函数移植到线上文件（保持各自行尾）。

线上已有：_dedupe_consecutive / _strip_placeholders / _downgrade_fabrication / _strip_fabricated_times
线上缺：_strip_revision_note / _strip_pending_sections / _strip_cliches /
        _strip_ai_artifacts / _fix_mislabeled_measured（含所用常量）

用法（在放有 agents_online.py / app_online.py 的目录执行）：
    python _patch_online_cleanup.py
产出 agents_patched.py / app_patched.py，只做文本插入，不改已有函数体。
"""
import io
import os
import re
import sys

LOCAL_AGENTS = r"D:\competition-agent\backend\competition_agents.py"


def grab(text, start_marker, end_marker):
    """按显式起止标记切片。

    不能用「下一个顶层 def」做边界：`_CLICHE_REPLACE` 是常量，它后面紧跟的
    `def _strip_cliches` 会被当成边界切掉函数体（实测出现过常量重复插入、
    函数整个丢失）。起止都写死，谁也别猜。
    """
    i = text.index(start_marker)
    j = text.index(end_marker, i + len(start_marker))
    return text[i:j].rstrip() + "\n"


def main():
    local = io.open(LOCAL_AGENTS, encoding="utf-8").read()

    consts = grab(local, "_PENDING_HEADING = re.compile(", "def _strip_revision_note(text):")
    rev = grab(local, "def _strip_revision_note(text):", "def _strip_pending_sections(text):")
    pending = grab(local, "def _strip_pending_sections(text):", "_CLICHE_REPLACE = (")
    cliche = grab(local, "_CLICHE_REPLACE = (", "def _strip_ai_artifacts(text):")
    ai = grab(local, "def _strip_ai_artifacts(text):", "def _fix_mislabeled_measured(text):")
    measured = grab(local, "def _fix_mislabeled_measured(text):", "def _theme_drifted(")

    for name, body in (("consts", consts), ("rev", rev), ("pending", pending),
                       ("cliche", cliche), ("ai", ai), ("measured", measured)):
        if not body.strip():
            sys.exit("抽取失败：%s" % name)

    block = "\n\n".join([consts, rev, pending, cliche, ai, measured])

    for fn in ("def _strip_revision_note", "def _strip_pending_sections",
               "def _strip_cliches", "def _strip_ai_artifacts",
               "def _fix_mislabeled_measured"):
        if fn not in block:
            sys.exit("块内缺函数：%s" % fn)
    if block.count("_CLICHE_REPLACE = (") != 1:
        sys.exit("_CLICHE_REPLACE 次数异常：%d" % block.count("_CLICHE_REPLACE = ("))
    print("块校验通过：5 个函数 + 4 个常量，共 %d 行" % block.count("\n"))

    # ---------- competition_agents.py（CRLF） ----------
    raw = io.open("agents_online.py", "rb").read()
    crlf = b"\r\n" in raw
    text = raw.decode("utf-8")
    anchor = "def _strip_placeholders(text):"
    if text.count(anchor) != 1:
        sys.exit("agents 锚点数量异常：%d" % text.count(anchor))
    if "_strip_cliches" in text:
        sys.exit("agents 已含 _strip_cliches，疑似重复打补丁，终止")

    ins = block.replace("\n", "\r\n") if crlf else block
    out = text.replace(anchor, ins.rstrip("\r\n") + ("\r\n\r\n\r\n" if crlf else "\n\n\n") + anchor, 1)
    io.open("agents_patched.py", "w", encoding="utf-8", newline="").write(out)
    print("agents: %d -> %d 字符, CRLF=%s, 新增 %d 行"
          % (len(text), len(out), crlf, out.count("\n") - text.count("\n")))

    # ---------- app.py（LF） ----------
    app = io.open("app_online.py", encoding="utf-8", newline="").read()
    old_imp = ("from competition_agents import _dedupe_consecutive, _strip_placeholders, "
               "_downgrade_fabrication, _strip_fabricated_times")
    new_imp = ("from competition_agents import (\n"
               "            _dedupe_consecutive, _strip_placeholders, _downgrade_fabrication,\n"
               "            _strip_fabricated_times, _fix_mislabeled_measured, _strip_ai_artifacts,\n"
               "            _strip_cliches, _strip_pending_sections, _strip_revision_note)")
    if app.count(old_imp) != 1:
        sys.exit("app 导入行数量异常：%d" % app.count(old_imp))
    app = app.replace(old_imp, new_imp, 1)

    old_chain = ("payload[_k] = _strip_fabricated_times(_downgrade_fabrication("
                 "_strip_placeholders(_dedupe_consecutive(payload[_k]))))")
    new_chain = ("payload[_k] = _strip_cliches(_strip_ai_artifacts(_fix_mislabeled_measured(\n"
                 "                    _strip_fabricated_times(_downgrade_fabrication(\n"
                 "                        _strip_placeholders(_dedupe_consecutive(\n"
                 "                            _strip_pending_sections(\n"
                 "                                _strip_revision_note(payload[_k])))))))))")
    if app.count(old_chain) != 1:
        sys.exit("app 链式调用数量异常：%d" % app.count(old_chain))
    app = app.replace(old_chain, new_chain, 1)
    io.open("app_patched.py", "w", encoding="utf-8", newline="").write(app)
    print("app: 导入与调用链已更新")


if __name__ == "__main__":
    main()
