#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给线上 app.py 加「创新点兜底补写」（在篇幅闸门之前调用）。

用法（在 app_live4.py 同目录）：python _patch_online_autopatch.py
产出 app_autopatch.py，行尾沿用（线上 app.py 是 LF）。
"""
import io
import sys

SRC = "app_live4.py"
OUT = "app_autopatch.py"

HELPER = '''def _auto_patch_innovation(result, data):
    """创新点兜底：诊断发现「创新点可数」缺失时，定向补一次。

    prompt 里已写明「在技术方案章用一句话编号列出」，但模型在篇幅配额压力下
    经常把这一句省掉（实测同题两次：一次写「创新有三：①②③」，一次完全没写）。
    prompt 属于概率约束，这里做确定性兜底——补在篇幅闸门之前，超长会被闸门压回。

    只补表达类缺口：专利/查新/实测这类事实缺口在 scorecard_patch 里已排除，
    不会代写。分数没涨就回退，等于没改。
    """
    from scorecard import diagnose
    from scorecard_patch import innovation_missing, patch_until_clean
    mode = "deep" if str(data.get("mode") or "fast").lower() == "deep" else "fast"
    comp = data.get("competition_name", "")
    track = (data.get("track") or "").strip() or None
    diag = diagnose(result, comp, track, mode)
    if not diag.get("available") or not innovation_missing(diag):
        return ""
    rep = patch_until_clean(result, comp, track, mode, limit=1,
                            force_labels=("创新点可数",))
    if (rep.get("after") or 0) <= (rep.get("before") or 0):
        return ""
    result["proposal"] = rep["proposal"]
    return "%s -> %s（%s）" % (rep.get("before"), rep.get("after"),
                              (rep.get("applied") or [{}])[0].get("chapter", ""))


'''

CALL = '''    # 创新点兜底补写：必须在篇幅闸门之前——补进来的字超长会被闸门一起压回去。
    try:
        _innov = _auto_patch_innovation(result, data)
        if _innov:
            print(f"🧩 创新点兜底补写：{_innov}")
    except Exception as _e:
        print(f"[innovation-autopatch] 跳过，保留原文：{_e}")

'''


def main():
    s = io.open(SRC, encoding="utf-8", newline="").read()

    checks = {"def _run_generation(data):": 1,
              "final-length-gate": 1,
              "_auto_patch_innovation": 0,
              "api/scorecard": 2,
              "scorecard_patch_api": 1}
    for needle, want in checks.items():
        got = s.count(needle)
        if got != want:
            sys.exit("基线异常：%s 出现 %d 次，期望 %d（别用旧文件当基线）" % (needle, got, want))

    anchor = "def _run_generation(data):"
    s = s.replace(anchor, HELPER + anchor, 1)

    gate = "    # 最终篇幅闸门（简洁版）：writer 出口的压缩管不到 revise 节点——"
    if s.count(gate) != 1:
        sys.exit("闸门锚点异常：%d" % s.count(gate))
    s = s.replace(gate, CALL + gate, 1)

    io.open(OUT, "w", encoding="utf-8", newline="").write(s)
    print("ok: 新增 %d 行" % (s.count("\n") - io.open(SRC, encoding="utf-8",
                                                    newline="").read().count("\n")))


if __name__ == "__main__":
    main()
