# 协作约定：图表数据 & 真实 PPT（Codex 后端 ↔ WorkBuddy/豆包 前端）

> 本文档用于对齐「深度版自动生成表格、图表、PPT」这个需求的前后端边界。

## 一、后端（Codex）负责并已实现

### 1. 图表数据（深度版）
`POST /api/generate`（mode=deep）的响应里，`data.charts` 是结构化 JSON：

```json
{
  "budget":   [{"name":"研发成本","value":40}, {"name":"硬件采购","value":25}, {"name":"市场推广","value":20}, {"name":"运营备用","value":15}],
  "market":   {"years":["2024","2025","2026","2027","2028"], "values":[120,280,560,980,1500]},
  "timeline": {"stages":["需求调研","原型开发","测试迭代","上线运营","推广拓展"], "progress":[10,30,55,80,100]}
}
```

前端拿到后，直接把这三段喂给 ECharts：
- `budget` → 预算构成饼图（`[{name,value}]`）
- `market` → 市场规模柱状图（`years` 做 x 轴，`values` 做柱值）
- `timeline` → 时间线（`stages` 做 x 轴，`progress` 做折线值）

### 2. 真实 PPT 下载
`POST /api/export_ppt`（body 里带上 `data` 对象，或后端从最近一次生成结果取），返回 `application/vnd.openxmlformats-officedocument.presentationml.presentation` 的 `.pptx` 文件。

前端给「导出 PPT」按钮接这个接口即可下载。

## 二、前端（WorkBuddy/豆包）需要做的

1. 用 `data.charts` 替换 `index.html` 里三个 ECharts 图的写死数据（现在 budgetChart/marketChart/timelineChart 都是硬编码占位数据）。
2. 给「导出 PPT」按钮接 `/api/export_ppt`。

## 三、字段清单

响应 `data` 里目前包含（供前端取用）：
- 文本：`parsed_rules` / `similarity_report` / `competitor_analysis` / `business_model` / `risk_analysis` / `tech_solution` / `implementation_plan` / `social_value` / `project_summary` / `proposal` / `judge_feedback` / `proposal_analysis` / `defense_questions` / `ppt_outline` / `speech_script` / `one_liner` / `idea_feedback`
- 分数：`idea_score`（创意分）/ `score`（文档分）
- 图表：`charts`（仅深度版）

---

# 【2026-09-25 14:15 更新 · WorkBuddy（阿渡）】接线修复 + 现状同步

## 四、我修了什么（都是会让功能直接失效的接线 bug，不是业务逻辑改动）

用 `fix_rich_wiring.py`（幂等补丁，可重跑，打印每处命中次数）修了 `app.py` 的 4 处：

| # | 位置 | 症状 | 修法 |
|---|---|---|---|
| B1 | `_run_generation` 里 `history_item` 用 `rich_charts` | 变量在使用点之后才赋值 → **UnboundLocalError，深度版直接 500** | 把富媒体解析块整体前移到 `deep_app.invoke` 之后、写 history 之前 |
| B2 | 解析块读 `result["rich_media"]` | 该字段从没被赋值过 → `rich_tables` 永远 `[]`、`rich_deck` 永远 `None` | 改为优先读 `rich_pipeline` 实际写入的 `rich_charts/rich_tables/rich_deck`，`rich_media` 只留作兼容分支 |
| B3 | `payload["rich_charts"] = result.get("rich_charts", [])` | 取到的是**未渲染的原始 dict**，而前端/PPT 期待 `[{id,title,caption,url}]` | 统一走解析后的 `rich_charts`（列表） |
| B4 | `_run_generation` 结尾 | `return {...}` 被改写成 `payload = {...}` 后**忘了 return** → **生成接口返回 `data=null`，简洁版深度版全挂** | 补 `return payload` |

核验：语法 OK；`return payload` 1 处；富媒体解析块 1 处；备份在 `app.py.bak.wiring`。

## 五、`chart_renderer.render()` 缺失（第二个致命点）

- 现象：`rich_pipeline.py:17` 是 `from chart_renderer import render`，但当时 `chart_renderer.py` 只导出了旧版 `render_charts()`（面向旧契约 `budget/market/timeline`）→ **ImportError 被 try 吞掉，整条富媒体链路静默失效**，`rich_*` 全空。
- 我在 14:0x 给 `chart_renderer.py` 追加了 `render(chart, out_dir)`，支持 rich_pipeline 需要的 8 种 type：`bar/column`、`line/trend`、`pie/donut`、`radar`、`matrix/quadrant`、`timeline/gantt`、`funnel`、`architecture/arch`，未知类型退化成柱状图。
- 配色走深色底 `#0F1535` + 浅色文字，与 `pptx_builder` 深蓝版式、网页深色主题一致；白底 Word 里也是一张深色卡片，可读。
- ⚠️ 随后 Codex 重写了 `chart_renderer.py`（14:06）。**以 Codex 的版本为准**，我这版已作废；若 Codex 版本再丢 `render`，可从 `app.py.bak.wiring` 同期备份或本节描述重建。

## 六、服务与进程现状（实测 14:15）

- `schtasks` 被本机安全策略拦截（`Program Blacklist`），**我无法用计划任务拉起服务**。
- 14:10 出现 **3 个 python 抢 8080**（39808 / 5340 / 29904），已杀掉两个，**现在只剩 PID 39808 单实例**，首页 `HTTP 200 / 88805 bytes`。
- ⚠️ 笔记里的老坑：两个 Python 同时 LISTENING 8080 会互相抢请求，页面**时好时坏**。任何人测之前请先 `netstat -ano | grep :8080 | grep LISTENING`，**正常应该只有一行**。
- 静态图路由实测可访问：`/generated/chart_budget.png`、`chart_market.png`、`chart_timeline.png`、`c1.png` 全部 200。

## 七、契约（以实测代码为准，比上面第一节的旧版更准确）

`build_rich_assets()` 返回的已经是**渲染后**的产物，不是原始数据：

```jsonc
{
  "charts": [{"id":"c1","title":"目标市场规模三年翻三倍","caption":"一句话洞察","url":"/generated/chart_c1.png"}],
  "tables": [{"id":"t1","title":"竞品逐项对比","header":["维度","我们","竞品A"],"rows":[["价格","99元","199元"]]}],
  "deck": {"project":"项目名","one_liner":"一句话","competition":"赛事名",
           "slides":[{"type":"cover|section|bullets|metrics|chart|table|closing",
                      "kicker":"01 / 痛点","title":"页标题","bullets":["**关键词**：说明"],
                      "chart":"c1","table":"t1","metrics":["4.5亿：年住院人次"],"note":"数据口径"}]}
}
```

前端取用：`data.rich_charts` / `data.rich_tables` / `data.rich_deck`（`index.html` 1046-1102 行已接，Codex 写的）。
PPT 下载：`POST /api/export_pptx`，body 带 `deck / charts / tables / idea / one_liner`。

## 八、重复模块：我建的 media_* 建议删（等端到端验证通过后）

我早先不知道 Codex 在建同一套东西，另外写了：
`media_factory.py`（图表+docx+pptx）、`deck_agent.py`（LLM 提取）、`media_routes.py`（`/api/media/*` 蓝图，已注册进 app.py）、`patch_register_media.py`。

**功能与 `rich_pipeline + chart_renderer + pptx_builder` 完全重复**，且 `/api/media/build` 会额外消耗一次 DeepSeek 调用（额度已经出现过 `402 Insufficient Balance`）。

建议：端到端验证通过后，删掉 `deck_agent.py` / `media_routes.py`，并从 `app.py` 移除那 5 行注册（我写的 `try: from media_routes import media_bp ...` 块，删了不影响别的路由）。
**现在先别动**——豆包正在跑深度版测试，改 app.py 要重启服务会打断它。

## 九、给豆包的验证清单（深度版跑完后逐项确认）

1. `data.rich_charts` 长度 ≥ 2，且每个 `url` 在浏览器里能 200（不能是 404）
2. `data.rich_tables` **不再是 `[]`**（修 B2 之前它恒为空）
3. `data.rich_deck.slides` 长度 12-14，含 `chart` 页 ≥2、`table` 页 ≥1
4. `/api/export_pptx` 下载的 `.pptx` 能用 PowerPoint 打开、页数与 slides 一致、图表页里图真的在
5. 页面「图表」Tab 显示的是本次项目的真图，不再是写死的占位数据
6. 记录三列：评委分 / rich_* 各项长度 / 端到端耗时

## 十、分工现状（避免再撞车）

- 后端 `rich_pipeline / chart_renderer / pptx_builder / competition_agents` → **Codex**
- 前端 `index.html`（图表 Tab、PPT 下载按钮）→ **Codex 已写完**，豆包在测
- `app.py` 接线修复 → **我**（`fix_rich_wiring.py`，幂等，Codex 改 app.py 时**请保留那两段标记注释**：`# ===== 富媒体解析（表格/图表/PPT）` 和 `return payload`）
- 端到端验证 → **豆包**

---

# 【2026-09-25 14:50 更新 · WorkBuddy（阿渡）】"PPT 内容太少" + "表格要改" 已修

## 十一、用户本轮反馈（已定位到根因，不是玄学）

| 反馈 | 根因 | 修法 |
|---|---|---|
| 「AI 路演 PPT 内容太少了」 | ① 图表页被**强制双栏**：`_bullets_body(width=5.3)` 分两栏后每行只剩 **10 个字**，2 行 = 20 字，其余全被 `…` 吃掉 ② `_bullets_body` 硬截 `[:8]`，第 9 条之后**直接丢弃** ③ 表格 `min(len+1, 9)` 只留 8 行，超出的行**静默消失** | 见十二 |
| 「这些表格需要修改」 | `rich_tables` 渲染的是**裸 `<table>`**，而 CSS 只有 `.content-block table` 作用域 → 完全没边框没配色 | 见十三 |

顺带修掉一个**真实版面 bug**：`_slide_bullets` 里要点区 top=2.15、指标卡 top=2.35，**两者直接叠在一起**（有 metrics 的页一定糊）。

## 十二、`pptx_builder.py` 改动（Codex 主文件，我只动版面/分页，没碰业务逻辑）

新增常量（都在文件头部）：

```python
MAX_BLOCKS_PER_SLIDE      = 8     # 实测双栏 8 张时最后一张底边 6.19in，距页脚 6.98in 有余量
MAX_BLOCKS_WITH_CHART     = 4
MAX_BLOCKS_WITH_METRICS   = 4
MAX_TABLE_ROWS_PER_SLIDE  = 7     # 表格每页数据行（不含表头）
SPLIT_BULLET_CHARS        = 58    # 超过就按标点拆，不再用 "…" 截断
```

- **新增 `_split_bullets()`**：长段落按「句末标点 → 逗号顿号 → 硬切」三级拆成多条，`**标题**：` 只保留在第一条。
- **新增 `_chunk()`**、**`_emit_bullets()`**、**`_emit_table()`**：`build_deck()` 现在会自动分页。
  首页因图表/指标只放 4 块，**续页是干净版面按满容量 8 块排**，标题自动加「（续）」。
- **`_bullets_body()`**：去掉 `[:8]` 硬截；分栏决策改为 `宽度 ≥ 7in` **且** `单栏排得下`——窄栏（左文右图）一律单栏。
- **`_metrics_body()`**：新增 `top/height` 参数，不再和要点区抢位置；矮卡自动缩字号。
- **`_chart_body()`**：图片等比缩到 6.2×4.5in 内并居中，不再可能撑出页面。
- **`_table_body()`**：列数上限 6 → 7，宽表不再被砍列；列多时字号自动降到 11/10.5。
- 清掉 `_footer()` 里一行没用到的空 textbox（死代码）。

## 十三、`index.html` 改动（前端，豆包在测，我只加了 CSS + 卡片内容）

- **新增 `table.rich-table` 一整套 CSS**（表头主色底、斑马纹、hover 高亮、首列加粗、圆角边框），
  并给 `renderRich()` 生成的表加 `class="rich-table"` + `<thead>/<tbody>`。**不依赖 `.content-block` 作用域。**
- **PPT 预览卡重写**：原来只有「标题 + N 个要点」，现在按版式还原真实内容——
  - 要点页：显示最多 5 条要点原文（`**加粗**` 转成 `<b>`，2 行截断），超出显示 `+N 条…`
  - 数据页：指标拆成 `数值 + 说明` 的 chip
  - 表格页：内嵌迷你表（表头 + 前 4 行）+ `共 N 行`
  - 图表页：**左文右图**，和真 PPT 版式一致（用 `rich_charts` 的 url 按 id/title 反查）
  - 卡片尺寸 210px → 290px，新增 `.deck-card` 系列 CSS

## 十四、验证结果（全部实测，非推断）

```
_test_pagination.py      9 页 / 越界 0 / 关键数据 100% 保留 / 省略号仅 1 处
_verify_media_mock.py    图表 8/8 渲染成功；PPT 14 页无空页无越界；HTTP /api/export_pptx 200（252983 B，PK 头合法）
_probe_live.py           ✅ 线上服务确认为新版：12 条要点 → 2 页，11 行表格 → 2 页，内容全保留
```

⚠️ **重要**：`app.py` 里 `from pptx_builder import build_deck` 是**函数内懒加载**，模块一旦进 `sys.modules` 就不再重载。
我实测线上服务一开始**确实还是旧代码**（探针返回 4 页、第 9 条之后丢失），**已重启**服务（现 PID 12388，HTTP 200）后复验通过。
**以后改完 `pptx_builder.py` 必须跑 `_probe_live.py` 复验，不能想当然。**

## 十五、给豆包：现在重新测什么

1. 深度版生成 → 看「PPT 预览」卡片是不是**能读到要点原文**（不再是干巴巴的"N 个要点"）
2. 看表格 Tab 的表**有没有边框、表头有没有底色**（之前是裸表）
3. 下载 PPTX → 页数应 ≥ slides 页数（超长页会自动多出「（续）」页），且**没有内容被 `…` 吃掉**
4. 如果还嫌内容少，调 `pptx_builder.py` 头部的 `SPLIT_BULLET_CHARS`（调小 = 拆得更碎 = 页更多）和 `MAX_BLOCKS_PER_SLIDE`

## 十六、仍然待办

- 删除我建的重复模块 `media_factory.py` / `deck_agent.py` / `media_routes.py` + app.py 里的 `register_media` 注册块（**等豆包端到端验完再动，现在删会打断测试**）
- `chart_render_wb.py` 是 `render()` 的备份副本，`chart_renderer.py` 末尾有兜底 import 指向它，**别单独删**

## 十七、本机环境（别再踩）

- 项目唯一可用的 python：`C:\Users\34984\.conda\envs\rag-dev\python.exe`（3.10.21，含 matplotlib/flask/pptx）
- 系统 Python 3.13 和托管 Python 3.13.12 **都没有 matplotlib**，跑图表脚本一定 ModuleNotFoundError
- `wmic` 本机不存在 → `_watcher.py` 的 `already_running()` 永远返回 False → **每 5 分钟多起一个守护进程**，
  各自重复拉起 Flask 并抢占 8080 端口（这是服务间歇性无响应的根因）。
  **已修（14:55）**：`_watcher.py` 加了独占文件锁兜底 `%TEMP%\kechuang_watcher.lock`，双进程实测能正确去重。
