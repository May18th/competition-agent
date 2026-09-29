# Codex 回执：417 轮交付质量专项（后端 5 项，2026-09-30）

## 已完成（Codex 后端，py_compile 全部通过）

### 5 · 智能辅助声明（P0）
- `app.py` `AI_NOTICE_LINE` 由「AI 辅助制作 · 文中数据…」改为「本材料由智能助手辅助起草，已按官方要求排版，请以团队真实情况核对补充后提交。」（禁用「AI」、措辞温和）。
- `app.py` 结果区 `disclaimer` 由「AI 辅助生成」改为「智能助手辅助生成」。
- 覆盖：说明书 Word/PDF、各分析报告、答辩问题（统一走 `_append_ai_notice`）。

### 4 · PDF 页数/体积校验（P0）
- `quality_gate.py` `check_pdf`：体积上限 3MB→50MB（原来误伤含图 20 页 PDF），新增页数上限校验 + 超限给出删减建议文案。
- `app.py` 新增 `_pdf_limits(competition_name)`：从 `competition_profiles.json` 的 `word_requirement.official` 解析「X 页 / Y MB」；`export_pdf` 传赛事口径给 `check_pdf`。默认 20 页 / 50MB。

### 1 · Word 封面标题与目录（P0）
- 已核实 `docx_render.py` 封面 + 静态目录 + TOC 域本就齐全（doc_type=default/report 时）。
- `app.py` `export_zip` 的 `build_doc`：申报书封面主标题由泛名「项目申报书全文」改为项目名，页眉仍用「项目申报书」；school/team/advisor/subtitle 已正确传入。
- 注：school/team/advisor 只在导出请求里、不落 history，打包导出（zip）走 `_fetch_record_from_source` 拿后端原文时仍可能缺这三项（需前端打包时把 school/team/advisor 一起传，见下方 WB 待办）。

### 2 · PPT 页数与大纲对齐（P0）
- `competition_agents.py` 深度版大纲 prompt：15～20 页 → 8～12 页，与 `rich_media_agent` 的 deck.slides 8-12 页对齐（评委对比大纲与 PPT 不再对不上）。

### 3 · PPT 图表数据用实测（P1）
- `competition_agents.py` `rich_media_agent`：prompt 增加「申报书正文（图表必须优先取这里的实测数据）」+ 明确「优先实测、缺失才测算并在标题标（测算）」。

## WB 待办（前端/ppt 模板）
1. PPT 结尾页（`pptx_builder.py` 的 `_slide_closing`）加一行小字「本材料由智能助手辅助起草，请以团队真实情况核对后提交」（pptx_builder 归 WB，Codex 不动）。
2. 前端打包导出时把 school/team/advisor 一并传 `/api/export_zip`，保证 zip 里的申报书封面带团队署名。

## 提交清单
`app.py`、`quality_gate.py`、`competition_agents.py`（三文件）。
