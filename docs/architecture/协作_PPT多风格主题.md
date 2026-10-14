# 协作：PPT 多风格主题（Codex → WorkBuddy）

> 日期：2026-09-25
> 后端（Codex）已完成多风格主题落地，本文档说明改动 + 前端需要配合的事项。

## 一、后端已完成的改动

### 1. `pptx_builder.py`（只追加，未改原有主题）
- 新增两个主题，`THEMES` 从 8 个扩到 10 个：
  - `academic` 学术答辩（论文/开题/结题/科研类，克莱因蓝）
  - `cyber` 科技紫·AI（人工智能/大数据/赛博未来类，深紫霓虹）
- `THEME_ORDER` 末尾追加 `academic`、`cyber`。
- 原有 8 个主题（tech/ink/medical/edu/agri/finance/craft/social）未动。

### 2. `chart_renderer.py`（只追加，`render_charts()` 旧契约保留）
- 新增 `_CHART_THEMES` 字典 + `set_theme(theme)` 函数。
- `render(chart, out_dir, theme=None)` 新增可选 `theme` 参数，开头调 `set_theme(theme)`。
- 图表 PNG 的系列色/背景色现在能跟随 PPT 主题（与 `pptx_builder` 的 `chart` 色板对齐）。

### 3. `rich_pipeline.py`
- `build_rich_assets(result, competition="", idea="", theme=None)` 新增 `theme` 参数。
- 传给 `chart_renderer.render(..., theme=theme)`，并把 `theme` 写入 `deck["theme"]`。

### 4. `app.py`
- `/api/generate` 深度版富媒体链路：`build_rich_assets(..., data.get("theme"))`。
- `/api/export_pptx`：`deck.setdefault('theme', data.get('theme') or 'tech')` 和 `variant`。

## 二、前端需要配合（待办）

1. 生成接口：深度版生成请求体里传 `theme` 字段（可选，默认 tech），例如：
   ```json
   { "mode": "deep", "idea": "...", "theme": "academic" }
   ```
2. PPT 导出：`/api/export_pptx` 请求体里传 `theme`（和可选 `variant`）。
3. 主题选择 UI（可选）：调 `pptx_builder.list_themes()` 拿主题/版式清单渲染下拉框。

## 三、主题清单（10 个）

| key | 名称 | 适用 |
|---|---|---|
| tech | 科技蓝 | AI/算法/硬件/数据 |
| ink | 水墨丹青 | 文化/非遗/文创/古籍 |
| medical | 生命青绿 | 医疗/健康/护理 |
| edu | 暖橙活力 | 教育/教学/校园 |
| agri | 大地丰绿 | 农业/种植/生态 |
| finance | 商务藏金 | 金融/支付/商业 |
| craft | 匠心工业 | 智能制造/机械/建筑 |
| social | 公益暖阳 | 公益/助老/社区 |
| academic | 学术答辩 | 论文/开题/结题（新） |
| cyber | 科技紫·AI | 人工智能/大数据/赛博（新） |

版式（variant）4 套：`v1` 流光·卡片、`v2` 左色块·极简、`v3` 色带·序号、`v4` 居中·留白。

## 四、注意

- 改动均为「追加」，未覆盖 WorkBuddy 之前的 `wb_fix_writer_quality.py`、`render()` 补丁等。
- 改了后端需重启 Flask（`taskkill /F /IM python.exe` 后重新 `python run.py`）。
- 前端主题选择后，深度版生成的图表 PNG 和导出的 PPT 会自动统一成同一套配色。
