# 367 评委预审报告 · 后端接口契约（Codex → WorkBuddy）

## 接口
`POST /api/judge_preview`（纯规则、不调 LLM、不写库，演示只读也可用）

请求（JSON）：
```json
{"proposal": "正文全文", "mode": "deep|fast", "title": "项目名"}
```

响应：
```json
{
  "success": true,
  "report": {
    "total": 10,
    "pass": 8,
    "summary": "10 项中 8 项通过，2 项需关注",
    "items": [
      {"key": "project_name", "label": "项目名一眼看懂", "status": "pass|doubt|missing", "note": "判据一句话"}
    ]
  }
}
```

10 项 key（固定顺序）：project_name / pain_quantified / measured_data / competitor / disclosure / team / finance / word_count / format / plagiarism。

## 前端要做
- 结果页新增「评委预审」入口，调此接口，把 items 渲染成 10 项检查表。
- 每项按 status 显示：pass=绿「通过」、doubt=黄「存疑」、missing=红「缺失」，note 作判据小字。
- 任一 status != pass 时，顶部横幅「建议先处理 X 项再导出」（配合 374 健康度仪表盘）。

## 验收
- 传样例 demo 正文，能返回 10 项、每项有 status+note；样例能展示红绿状态。
