# -*- coding: utf-8 -*-
"""
418 轮 P0：全站「AI」产品自述字样清理（仅面向用户的展示文案）

原则（337 轮定的口径）：
- 产品自述里的 AI 一律换成「智能 / 智能系统 / 智能评审」等表述；
- 官方术语保留：AI应用创新挑战赛、AI辅助教学、iCAN 官方扣分点「AI 只做套壳点缀」、
  关键词「人工智能/AI」检索词表、学术诚信里「关于 AI 使用的相关规定」；
- 代码注释里的 AI 不动（用户看不到，改了只会徒增 diff 与冲突风险）；
- 导出文件名前后端必须同步改，否则下载出来的文件名与界面不一致。
"""
import io
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# (文件, 原串, 新串) —— 顺序敏感：先替换长的/带标签的，再替换短的
RULES = [
    # ---------- index.html ----------
    ("index.html", "去掉「AI 味」", "去掉「模板腔」"),
    ("index.html", "去 AI 味（强）", "去模板腔（强）"),
    ("index.html", "「去 AI 味」=", "「去模板腔」="),
    ("index.html", "用「去 AI 味」重跑", "用「去模板腔」重跑"),
    ("index.html", "AI 自评参考（文档质量）", "智能自评参考（文档质量）"),
    ("index.html", "<span>AI 自评参考</span>", "<span>智能自评参考</span>"),
    ("index.html", "这个分数由 AI 依据公开评审规则给出", "这个分数由智能系统依据公开评审规则给出"),
    ("index.html", "<b>AI 撰写的示范范文</b>", "<b>智能生成的示范范文</b>"),
    ("index.html", "AI 评审参考意见.docx", "智能评审参考意见.docx"),
    ("index.html", "exportOne('judgeFeedback', 'AI 评审参考意见')",
     "exportOne('judgeFeedback', '智能评审参考意见')"),
    ("index.html", "之前页数和顺序全看 AI 心情", "之前页数和顺序全看随机"),

    # ---------- static/app.js ----------
    ("static/app.js", "本评审由 AI 参考多位专家视角生成", "本评审由智能系统参考多位专家视角生成"),
    ("static/app.js", "AI 正在生成，内容将实时流出", "正在生成，内容将实时流出"),
    ("static/app.js", "评委正在挑刺，AI 替你先挨一轮批", "评委正在挑刺，智能评审替你先挨一轮批"),
    ("static/app.js", "AI正在' + (isOptimize ? '优化' : '生成')",
     "正在' + (isOptimize ? '优化' : '生成')"),
    ("static/app.js", "正文完成，AI 评委开始挑刺", "正文完成，智能评审开始挑刺"),
    ("static/app.js", "<b>AI 路演 PPT</b>", "<b>智能路演 PPT</b>"),
    ("static/app.js", "加 AI 示范范文片段", "加智能示范范文片段"),
    ("static/app.js", "AI 自动识别并填到对应位置", "智能识别并填到对应位置"),
    ("static/app.js", "AI 在原文上优化", "在原文上智能优化"),
    ("static/app.js", "AI 生成的内容请自行核对数据", "生成的内容请自行核对数据"),
    ("static/app.js", "'AI 质量 ' + sc", "'智能评分 ' + sc"),

    # ---------- app.py（后端导出文件名，须与前端同步）----------
    ("app.py", "AI 评审参考意见.docx", "智能评审参考意见.docx"),
]


def main():
    total = 0
    missing = []
    by_file = {}
    for rel, old, new in RULES:
        path = os.path.join(BASE, rel)
        if not os.path.isfile(path):
            missing.append(rel)
            continue
        s = io.open(path, encoding="utf-8").read()
        n = s.count(old)
        if n:
            s = s.replace(old, new)
            io.open(path, "w", encoding="utf-8").write(s)
            by_file.setdefault(rel, {})[old] = n
            total += n
    for rel in sorted(by_file):
        print("[%s]" % rel)
        for old, n in by_file[rel].items():
            print("   %d x  %s" % (n, old[:56]))
    if missing:
        print("!! 文件不存在: %s" % ", ".join(missing))
    print("TOTAL_REPLACED=%d" % total)


if __name__ == "__main__":
    main()
