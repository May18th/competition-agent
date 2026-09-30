# -*- coding: utf-8 -*-
"""417 轮：清掉页面/脚本里面向用户的「AI」字样（正当官方术语除外）。

只替换面向用户的文案，不碰：
  - base64 图片里的 AIAAAA.. 片段（不是文案）
  - 赛事别名/关键词表里的 'AI'（那是匹配用户输入用的，改成别的就匹配不上了）
  - 官方赛事名与官方章节名（iCAN AI 挑战赛 / 功能说明与 AI 核心作用）
  - 代码注释与变量名
每条替换都打印实际命中次数，跑完必须自己数 —— 脚本说 ✅ 不代表真替换了。
"""
import io
import os
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

REPL = [
    # (旧文案, 新文案, 文件, 期望最少命中)
    ("AI 多智能体辅助撰写", "多智能体辅助撰写", "index.html", 10),
    ("AI 模拟自评", "系统模拟自评", "index.html", 2),
    ("去 AI 味", "去机器腔", "index.html", 4),
    ("上传或粘贴已有材料，AI 识别后自动填充", "上传或粘贴已有材料，自动识别后填充", "index.html", 1),
    ("，AI 自动识别后填到对应位置", "，系统自动识别后填到对应位置", "index.html", 1),
    ("若 AI 自评分数偏低", "若系统自评分数偏低", "index.html", 1),
    ("这些是 AI 编不出来的真实数据", "这些是系统编不出来的真实数据", "index.html", 1),
    ("AI 撰写的示范范文", "智能助手撰写的示范范文", "index.html", 1),
    ("AI模拟评审意见", "模拟评审意见", "index.html", 2),
    ("AI 智能图表", "智能图表", "index.html", 1),
    ("下面是 AI 替评委挑的", "下面是系统替评委挑的", "index.html", 1),
    ("AI 路演 PPT", "智能路演 PPT", "index.html", 1),
    ("之前页数和顺序全看 AI 心情", "之前页数和顺序全看系统发挥", "index.html", 1),
    ('title="AI 编不出来的内容', 'title="系统编不出来的内容', "index.html", 1),
    ("，AI 识别后自动填到", "，系统识别后自动填到", "index.html", 1),
    ("关于 AI 使用的相关规定", "关于智能辅助工具使用的相关规定", "index.html", 1),

    ("扣分点：AI 只做套壳点缀", "扣分点：智能能力只做套壳点缀", "static/app.js", 1),
    ("未匹配内置知识库，AI 将按通用标准评审", "未匹配内置知识库，将按通用标准评审", "static/app.js", 1),
    ("AI 模拟自评", "系统模拟自评", "static/app.js", 2),
    ("本评审由 AI 模拟多位专家视角生成", "本评审由系统模拟多位专家视角生成", "static/app.js", 1),
    ("按 AI 原始结构导出", "按系统原始结构导出", "static/app.js", 1),
    ("AI 正在生成，内容将实时流出…", "内容正在生成，将实时流出…", "static/app.js", 1),
    ("先让 AI 自己当一次评委…", "先让系统自己当一次评委…", "static/app.js", 1),
    ("评委正在挑刺，AI 替你先挨一轮批", "评委正在挑刺，系统替你先挨一轮批", "static/app.js", 1),
    ("AI正在", "系统正在", "static/app.js", 1),
    ("正文完成，AI 评委开始挑刺…", "正文完成，模拟评委开始挑刺…", "static/app.js", 1),
    ("加 AI 示范范文片段", "加示范范文片段", "static/app.js", 1),
    ("，AI 自动识别并填到对应位置", "，系统自动识别并填到对应位置", "static/app.js", 1),
    ("，AI 在原文上优化", "，在原文上优化", "static/app.js", 1),
    ("AI 生成的内容请自行核对数据", "生成的内容请自行核对数据", "static/app.js", 1),
    ("'AI 质量 ' + sc + ' 分'", "'质检 ' + sc + ' 分'", "static/app.js", 1),
    ("<b>AI 路演 PPT</b>", "<b>智能路演 PPT</b>", "static/app.js", 1),
]

cache = {}
fail = 0
for old, new, path, least in REPL:
    if path not in cache:
        cache[path] = io.open(path, encoding="utf-8").read()
    src = cache[path]
    n = src.count(old)
    if n == 0:
        print("  !! 零命中（目标可能已被改过）：%s | %s" % (path, old[:34]))
        fail += 1
        continue
    cache[path] = src.replace(old, new)
    flag = "" if n >= least else "  (命中 %d < 期望 %d，检查是不是还有漏网的)" % (n, least)
    print("  %-14s x%-3d %s -> %s%s" % (path, n, old[:30], new[:26], flag))

for path, src in cache.items():
    io.open(path, "w", encoding="utf-8").write(src)

print("\n写入完成，失败条目 %d 条" % fail)

# 收尾复核：还剩哪些面向用户的 AI（排除 base64 / 别名表 / 官方赛事名 / 注释 / 变量名）
import re
PAT_KEEP = ("AIAAAA", "AIBRAA", "AI应用创新挑战赛", "iCAN AI挑战赛",
            "功能说明与 AI 核心作用", "AI_NOTICE_LINE", "'AI'", "人工智能")
left = []
for path in ("index.html", "static/app.js"):
    for i, line in enumerate(io.open(path, encoding="utf-8").read().split("\n"), 1):
        if len(line) > 4000:
            continue
        if "AI" not in line:
            continue
        if any(k in line for k in PAT_KEEP):
            continue
        s = line.strip()
        if s.startswith("//") or s.startswith("*") or s.startswith("/*"):
            continue
        m = re.search(r"AI", line)
        left.append("%s:%d | %s" % (path, i, line[max(0, m.start() - 40):m.start() + 40]))
print("\n剩余疑似面向用户的 AI 字面（%d 处）：" % len(left))
for x in left:
    print("  ", x)
sys.exit(0)
