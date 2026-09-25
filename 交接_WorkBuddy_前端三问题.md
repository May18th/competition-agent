# 交接给 WorkBuddy：前端三问题（含精确修复代码）

> 生成时间：2026-09-26
> 分工：Codex（后端）已排查确认，以下三项均为**前端 `index.html` 问题**，后端无需改动。

---

## 问题 1 & 2：社会价值与应用前景、项目简介 显示空白

### 根因（已确认）

后端**已经正确生成并返回**这两个字段（查数据库，最新深度版记录里 `social_value` 1597 字、`project_summary` 296 字，`_run_generation` 的 payload 也包含 `social_value` / `project_summary`）。

前端 HTML 里**有**对应的展示 div：

```html
<!-- 前期分析 tab，约 1042 行 -->
<div class="content-block" id="socialValue"></div>

<!-- 申报与评审 tab，约 1134 行 -->
<div class="content-block" id="projectSummary"></div>
```

但**结果渲染 JS 漏了往这两个 div 写内容的代码**（约 2030~2041 行那一段），所以显示空白。

### 修复（补两行 JS）

在渲染结果那段 JS 里（`techSolution` 那行附近）补上：

```js
if (data.data.social_value) document.getElementById('socialValue').innerHTML = marked.parse(data.data.social_value);
if (data.data.project_summary) document.getElementById('projectSummary').innerHTML = marked.parse(data.data.project_summary);
```

字段名对应关系：`social_value` → `#socialValue`、`project_summary` → `#projectSummary`。

---

## 问题 3：AI 智能图表点击放大

### 需求

用户希望**单击某个图表就能放大查看**，现在只能靠缩放整个网页来看图。

### 建议实现（二选一）

1. **图片灯箱（最简单）**：给图表图片容器加 `click` 事件，点开后用一个全屏 `overlay` + 大图展示，点击关闭或按 Esc 关闭。
2. **ECharts 原生**：点图表时用全屏 overlay 重绘一个放大的 ECharts 实例（`dataZoom` 或直接放大容器尺寸）。

图表数据来源是 `/api/status/<task_id>` 返回的 `data.rich_charts`（每个元素含 `url` / `title` / `caption`）。

---

## 后端结论（供参考，无需改动）

- 深度版工作流已包含 `social_value_agent`（社会价值）和 `summary_agent`（项目简介），链路上正确。
- `app.py` 的 `_run_generation` 已返回 `social_value`、`project_summary` 字段。
- 问题 1&2 纯前端漏写渲染 JS；问题 3 是前端新增交互功能。
