# -*- coding: utf-8 -*-
"""检查：下拉的 11 个赛事 vs data/*.txt 能否互相匹配"""
import os, re, glob

# 从 index.html 抽出 option value
html = open('index.html', encoding='utf-8').read()
block = html.split('id="competition"')[1].split('</select>')[0]
options = re.findall(r'value="([^"]+)"', block)

files = [os.path.basename(p).replace('.txt','') for p in sorted(glob.glob('data/*.txt'))]

print("下拉 %d 个赛事 / data 里 %d 个文件\n" % (len(options), len(files)))
print("%-40s %-8s %s" % ("下拉赛事", "命中?", "匹配到的知识库文件"))
print("-"*85)
hit = 0
for o in options:
    m = [f for f in files if f in o or o in f]
    if m: hit += 1
    print("%-40s %-8s %s" % (o, "YES" if m else "NO", ", ".join(m) or "（空！AI 拿不到评分标准）"))
print("-"*85)
print("覆盖：%d/%d" % (hit, len(options)))
