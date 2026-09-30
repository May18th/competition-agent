# -*- coding: utf-8 -*-
"""
417 轮 P0：给 build_docx 生成的文档底部统一加「智能辅助」声明

- 措辞温和，且禁用「AI」字样（418 轮全站清理口径，官方术语除外）
- 幂等：已打过补丁就跳过；正文里已有该句也不会重复追加
- 不动封面/目录/页眉等既有逻辑，避免与 Codex 正在改的 417-1/2/4 冲突
"""
import io
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
P = os.path.join(BASE, "docx_render.py")
MARK = "_WB_ASSIST_DECL_417"
DECL = "本材料由智能助手辅助起草，已按官方要求排版，请以团队真实情况核对补充后提交。"

s = io.open(P, encoding="utf-8").read()
if MARK in s:
    print("SKIP_ALREADY_PATCHED")
    sys.exit(0)

m = re.search(r"def build_docx\(.*?\):\s*\n", s, re.S)
if not m:
    print("ERR_NO_BUILD_DOCX")
    sys.exit(1)

ins = (
    "    # %s 417 轮 P0：所有生成文档底部统一加「智能辅助」声明\n"
    "    # 措辞温和、禁用「AI」字样（418 轮口径）；幂等，重复执行不会叠加。\n"
    "    if '本材料由智能助手辅助起草' not in (text or ''):\n"
    "        text = (text or '') + '\\n\\n' + '%s'\n" % (MARK, DECL)
)
s = s[:m.end()] + ins + s[m.end():]
io.open(P, "w", encoding="utf-8").write(s)
print("PATCHED at offset %d" % m.end())
