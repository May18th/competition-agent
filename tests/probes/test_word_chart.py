#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""轻量验证：docx_charts.inject_charts 是否真把图插进 Word（不调用 LLM）。"""
import os, sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
GEN_DIR = BACKEND / "generated"
os.makedirs(GEN_DIR, exist_ok=True)

# 用仓库里现成的有效 PNG，避免手造图片格式问题
SRC_PNG = ROOT / "frontend" / "static" / "logo.png"
PNG_PATH = GEN_DIR / "test_chart.png"
if SRC_PNG.exists():
    shutil.copy(SRC_PNG, PNG_PATH)
else:
    raise FileNotFoundError(f"找不到测试用 PNG: {SRC_PNG}")

sys.path.insert(0, str(BACKEND))
from docx_render import build_docx
from docx_charts import inject_charts

md = """# 项目申报书

## 一、市场分析

这里是市场分析正文。

## 二、团队分工

这里是团队分工正文。
"""

doc = build_docx("测试项目", md, doc_type="report")
charts = [{
    "id": "c_test",
    "title": "市场规模趋势",
    "caption": "2024-2026 年预测市场规模",
    "url": "/generated/test_chart.png",
    "spec": {"type": "line"}
}]
inserted = inject_charts(doc, charts, width_in=3.0)

OUT = ROOT / "tests" / "probes" / "test_word_chart_output.docx"
doc.save(str(OUT))

print("="*60)
print("Word 图表内嵌实测")
print("="*60)
print(f"输入图表数: {len(charts)}")
print(f"实际插入数: {inserted}")
print(f"输出文件: {OUT}")

# 用 zip 结构确认 docx 里真含图片
import zipfile
with zipfile.ZipFile(OUT, 'r') as z:
    media = [n for n in z.namelist() if n.startswith('word/media/')]
print(f"docx 内图片文件: {media}")
print("结论:", "PASS" if inserted == 1 and media else "FAIL")
