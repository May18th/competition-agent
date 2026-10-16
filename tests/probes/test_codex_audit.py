#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
只读审计脚本：复核 Codex 的优化是否真落地（不改任何源文件）。
用法：python tests/probes/test_codex_audit.py
只做 grep / 读文件，绝不动手改项目代码。
"""
import re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # D:/competition-agent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"

def read(p):
    if not p.exists():
        return ""
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return f"__READ_ERROR__{e}"

def grep(text, pat, flags=re.I|re.M):
    return [m.group(0) for m in re.finditer(pat, text, flags)]

def line_hits(text, pat, n=3):
    out=[]
    for i,line in enumerate(text.splitlines(),1):
        if re.search(pat, line, re.I):
            out.append(f"  L{i}: {line.strip()[:120]}")
            if len(out)>=n: break
    return out

REPORT=[]

def check(title, status, detail_lines):
    REPORT.append((title, status, detail_lines))

# ---------- 后端 ----------
llm = read(BACKEND/"llm_factory.py")
app = read(BACKEND/"app.py")
applog = read(BACKEND/"app_log.py")

# 1) 思考模式：默认 disabled；环境变量 enabled 才开
if "_thinking_kwargs" in llm and re.search(r'thinking.*type.*disabled|"type"\s*:\s*"disabled"', llm, re.I):
    check("后端-思考模式默认关闭", "PASS", line_hits(llm, r"_thinking_kwargs|DEEPSEEK_THINKING|type.*disabled")[:4])
elif "thinking" in llm.lower():
    check("后端-思考模式(需人工确认)", "WARN", line_hits(llm, r"thinking")[:4] + ["  有 thinking 控制但未见默认 disabled 标记"])
else:
    check("后端-思考模式", "FAIL", ["  未在 llm_factory.py 发现 thinking 控制"])

# 2) 429 限流粒度：按 identity + scope 分桶（uid/IP × 接口名）
has_rate_fn = "def _rate_limited(" in app
has_identity_scope = re.search(r"key\s*=\s*\(\s*identity\s*,\s*scope\s*\)|identity.*scope.*key", app, re.I)
has_scope_calls = len(re.findall(r"_rate_limited\([\"']\w+[\"']\)", app)) >= 2
if has_rate_fn and (has_identity_scope or has_scope_calls):
    detail = line_hits(app, r"def _rate_limited|key\s*=\s*\(|_rate_limited\([\"']")[:6]
    check("后端-429按用户+接口分桶", "PASS", detail)
else:
    check("后端-429限流粒度(需人工确认)", "WARN",
          line_hits(app, r"429|rate.?limit|限流|ratelimit")[:6] +
          ["  未见 (identity, scope) 分桶实现，需人工确认是否为全局锁"])

# 3) token 埋点
htok = line_hits(applog, r"token|usage|prompt_tokens|completion_tokens") + line_hits(app, r"prompt_tokens|completion_tokens")
if htok:
    check("后端-token埋点", "PASS", htok[:5])
else:
    check("后端-token埋点", "FAIL", ["  未见按用户/任务的 token 消耗记录"])

# ---------- 导出件 ----------
docx = read(BACKEND/"docx_render.py")
qg = read(BACKEND/"quality_gate.py")
charts_mod = read(BACKEND/"docx_charts.py")
# 汇总所有后端源码，用于找 inject_charts 调用点
backend_all = "\n".join(read(p) for p in BACKEND.glob("*.py"))

# 4) Word 图表内嵌（调用链可能在 app.py 而不是 docx_render.py）
inject_sites = line_hits(backend_all, r"inject_charts\s*\(")
if inject_sites:
    check("导出-Word图表内嵌调用链", "PASS", inject_sites[:5])
elif re.search(r"inject_charts|docx_charts", charts_mod, re.I):
    check("导出-Word图表内嵌", "WARN", ["  docx_charts.py 存在但后端未见 inject_charts 调用"])
else:
    check("导出-Word图表内嵌", "FAIL", ["  后端无图表注入调用"])

# 5) 去AI禁令入质量门
banned = ["随着","综上所述","赋能","生态","一站式","闭环","深度融合","值得注意的是","在当今"]
found_qg = [w for w in banned if w in qg]
if found_qg:
    check("导出-去AI禁令入质量门", "PASS", [f"  quality_gate.py 命中违禁词: {found_qg[:6]}"] + line_hits(qg, r"随着|赋能|闭环|生态")[:3])
else:
    check("导出-去AI禁令入质量门", "FAIL", ["  quality_gate.py 未见违禁词断言，仍只靠 prompt 自律"])

# 6) 文档作者露AI痕迹
if "科创赛事多智能体" in docx or "多智能体协同" in docx:
    check("导出-文档作者AI痕迹", "WARN", ["  docx_render.py 仍含 '科创赛事多智能体...' 作者名，建议改中性/留空"])
else:
    check("导出-文档作者AI痕迹", "PASS", ["  未见 AI 特征作者名"])

# ---------- 前端 ----------
css = read(FRONTEND/"static/style.css")
html = read(FRONTEND/"index.html")
js = read(FRONTEND/"static/app.js")

fe_items = {
    "进度环(progress-ring)": r"progress.?ring|progress-ring|ring-spin",
    "大留白卡片化(option-card)": r"option-card|wb-card-option|select-card|radio-card",
    "表单面分隔(form-surface)": r"form-surface|form--surface|section-surface",
    "错误态插画(error-illustration)": r"error-illustration|error-art|wb-error|empty-art",
    "长文层级(prose)": r"wb-prose|prose-|long-text|article-body",
}
fe_result=[]
for name,pat in fe_items.items():
    if re.search(pat, css, re.I) or re.search(pat, html, re.I):
        fe_result.append(f"  [有] {name}")
    else:
        fe_result.append(f"  [缺] {name}")
check("前端-5条漏项落地情况", "INFO", fe_result + ["  (视觉最终需 headless 截图复核)"])

# ---------- 输出 ----------
print("="*60)
print("CODEX 优化审计 (基线快照，仅读取)")
print("="*60)
order={"PASS":0,"INFO":1,"WARN":2,"FAIL":3}
for title,status,lines in REPORT:
    print(f"\n[{status}] {title}")
    for l in lines:
        print(l)
print("\n" + "="*60)
n_fail=sum(1 for _,s,_ in REPORT if s=="FAIL")
n_warn=sum(1 for _,s,_ in REPORT if s=="WARN")
print(f"摘要: FAIL={n_fail}  WARN={n_warn}  (WARN/INFO 需人工确认, 非必错)")
print("注意: 本脚本只查代码是否落地，不验证真实渲染/运行效果。")
