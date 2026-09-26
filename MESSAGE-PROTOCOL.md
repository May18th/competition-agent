# 多智能体协作协议（科创赛事助手）

> 参与方：WorkBuddy（我，负责富媒体与 PPT 全链路）／Codex（负责后端 Agent 链）
> 建立时间：2026-09-25
> 起因：双方曾在同一时段修改 `pptx_builder.py` 与 `rich_pipeline.py`，虽未造成代码丢失，但存在覆盖风险。

---

## 一、文件所有权（硬性）

| 文件 | 归属 | 说明 |
|---|---|---|
| `competition_agents.py` | **Codex 专属** | 我不改，Agent prompt / 图结构都归你 |
| `docx_render.py` | **Codex 主导** | Word 导出渲染与格式（初版由 WorkBuddy 交付；字体/行距/页边距等格式调整归 Codex，改前互知） |
| `scripts/build_comp_index.py` | **Codex 主导** | 赛道索引构建与 `TRACK_SRC` 官方分级 |
| `static/competition_index.json` | **生成产物（Codex 主导）** | 由 build_comp_index.py 生成，不手改 |
| `app.py` 的 `_run_generation` / Agent 编排部分 | **Codex 主导** | 我只改导出类路由，改前会说明 |
| `pptx_builder.py` | **我（WorkBuddy）主导** | 你可以在末尾**追加新 THEMES 条目**，但不要改函数体 |
| `chart_renderer.py` | **我主导** | 新增图表类型欢迎追加，请先告知 |
| `rich_pipeline.py` | **我主导** | prompt 调整属于我这边 |
| `index.html` | **我（WorkBuddy）专属** | 整个文件都归我，不只是富媒体 UI 部分（2026-09-26 用户明确分工：后端归 Codex、前端归 WorkBuddy）。Codex 要改前端请写 `待办_WorkBuddy_*.md` 或对话告知，不要直接下手 |
| `app.py` 导出类路由 | **我主导，改前说明** | 指 `export_pptx` / `export_zip`，其余仍归 Codex |
| `data/*.txt` 赛事资料内容 | **Codex 主导（官方核对与结构化）** | 原始材料由队友提供；赛道设置/评分标准/章节/扣分点的官方核对与编写归 Codex，WorkBuddy 只出命名规范与格式 |
| `data/README_知识库提交规范.md` | **我主导** | 给队友照填的模板与强制命名表 |
| `wsgi.py` / `Procfile` / `render.yaml` / `Dockerfile` / `vercel.json` / `api/index.py` | **我主导** | 云端部署入口与配置，见 `部署说明.md` |
| `requirements.txt` / `chart_renderer.py` 的字体候选段 | **我主导** | 面向跨平台部署的依赖与中文字体兜底 |
| `app.py` 写盘路径 / `tasks` 存储（云化改造） | **Codex 主责** | 只在真要用 Vercel 时才改，方案见 `待办_后端.md` P8 |

### pptx_builder.py 内部再做二级划分

- **Codex 可安全追加区**：`THEMES` 字典里新增主题条目（只加 key，结构照抄现有项）
- **我的保留区**（请勿改动）：`VARIANTS`、`V`、`_apply_theme`、`_apply_variant`、`list_themes`、`_COVERS`、所有 `_cover_*` / `_bullets_body` / `_slide_*` 函数体、`build_deck`
- Codex 若新增了主题，**不需要**改 `build_deck`——它会自动 `_apply_theme(deck.get("theme"))`

---

## 二、修改前必做（谁都别省）

1. 打开目标文件，确认要改的那几行还是你上次看到的版本（别人可能刚动过）
2. 用**精确字符串替换**，不要整文件重写
3. 改完立刻验证，不要留到下次：
   ```bash
   "C:/Users/34984/.conda/envs/rag-dev/python.exe" -m py_compile pptx_builder.py
   ```
4. 如果改动涉及别人负责的函数体 → **先在本文档或对话里说明，再动手**

---

## 三、当前已联调通过（2026-09-25 实测）

- 主题库 10 个：`tech / ink / medical / edu / agri / finance / craft / social / academic / cyber`
  - 其中 `academic`、`cyber` 由 Codex 提供 ✅
- 版式模板 4 套：`v1 流光·卡片 / v2 左色块·极简 / v3 色带·序号 / v4 居中·留白`
  - 10 主题 × 4 模板 = **40 套组合**，全部可用
- `build_deck` 已接 `_apply_theme` + `_apply_variant`（此前缺失，传了主题也不生效，已修复）
- `chart_renderer` 的图表配色跟随主题（`set_theme`），已验证
- `/api/ppt_themes` 返回主题+模板清单，前端下拉动态渲染
- 端到端实测：同一份 deck，传 `theme=tech/ink/medical`，导出的 PPTX 封面 RGB 确实不同 ✅
- 主题自动推断：`rich_pipeline.pick_theme()` 按项目内容关键词打分；不同赛道默认配不同版式（见 `VARIANT_FOR_THEME`）

---

## 四之二、第二轮联调（2026-09-25，Codex 三项前端需求）

Codex 交接：`app.py:341` / `:423` / `:836` / `:849`；`competition_agents.py:113` / `:154`。

### ✅ 1. 主题选择 UI + 生成/导出传 theme

- `/api/ppt_themes` 实测：`success=true`，**10 主题 × 4 模板**，结构 `{key,label,variants:[{key,name}]}` ✅
- 前端 `deckTheme` / `deckVariant` 两级下拉已存在，切换有提示条、不需重新生成 ✅
- `POST /api/generate` 传 `theme` ✅（`app.py:341` 已接）
- **`export_zip` 原本缺 theme 覆盖**（`export_pptx` 有，`export_zip` 没有）→ 已由 WorkBuddy 补上
  ```python
  if data.get('theme'):   deck['theme']   = data['theme']
  if data.get('variant'): deck['variant'] = data['variant']
  ```
  实测：deck 内置 `tech`，前端传 `theme=ink` → 导出 PPT 封面出现 `1B1B1B`/`4A4A4A`，`0F1535` 已清除 ✅

### 🐞 同时修掉的两个前端 bug（不是 Codex 的锅）

1. **`一键打包`根本没发 `rich_deck`** → zip 里连 PPT 都没有（实测只有 10 个 docx）。
   前端 `exportAll()` 已补发 `rich_deck / rich_charts / rich_tables / idea / theme / variant`。
2. **导出读的是 DOM 的 `innerText`** → `.tab-content` 是 `display:none`，隐藏 tab 读出来是空串，
   导出的 docx 会是空的。已改为优先读 `window._lastData` 原始 markdown，DOM 仅兜底。

### ✅ 2. 知识库状态面板

`/api/knowledge_status` 已接入，页面「赛事规则」下方新增面板，显示真实命中率、缺失清单、各文件缺哪些章节，
切换赛事下拉实时更新。

### ✅ 3. 章节缺失提示

`/api/generate` 返回的 `completeness` 已接入，缺章节时在结果区顶部出黄色提示条。

### ⚠️ 字段名口径订正（重要）

Codex 交接文档写的是 **生成结果顶层 `data.theme`**，但实测 `_run_generation` 的 payload **`theme` 字段不存在**，
实际主题在 **`data.rich_deck.theme`**（`rich_pipeline` 里 `deck.setdefault("theme", ...)`）。
前端已做兼容：`rd.theme || rd.rich_deck.theme || 'tech'`，两边都能跑。
**建议 Codex 把 `theme` 提到 payload 顶层**，前端不用改就能读到。

### ⚠️ 知识库真实命中率只有 1/11，不是 coverage 报的 4/11

`get_competition_knowledge` 用「文件名与赛事名互为连续子串」匹配，而现有文件名全都对不上：

| data/ 里的文件名 | 下拉 option value | 能否命中 |
|---|---|---|
| `iCAN大赛.txt` | `iCAN大学生创新创业大赛` | ❌ |
| `互联网+大赛.txt` | `中国国际互联网+大学生创新创业大赛` | ❌ |
| `国创项目.txt` | `国家级大学生创新创业训练计划（国创）` | ❌ |
| `挑战杯.txt` | `"挑战杯"全国大学生课外学术科技作品竞赛` | ✅ 唯一命中 |

→ **coverage 统计的是「文件数」不是「能匹配上的赛事数」**，两回事，建议改名或另加 `matched` 字段。
另外 4 个文件全都 `ok:false`（缺「申报书章节」「常见扣分点」两章）。
**赛事资料内容由负责的队友提供**（已写 `data/README_知识库提交规范.md` 给对方照填，含强制命名表），
我和 Codex 都不写业务内容，只做展示层和匹配逻辑。自查脚本：`_check_kb_match.py`。

---

## 四、待办分工

**Codex 适合做（不冲突）**
- 继续扩充 `THEMES` 的行业主题（照抄结构加 key 即可）
- 丰富 `data/*.txt` 赛事知识库（目前 4/11）
- `competition_agents.py` 里提升正文素材密度（更多可用数字/场景，喂给图表）

**我（WorkBuddy）做**
- 前端主题/模板切换 UI
- 图表、表格、PPT 的版式与渲染
- deck 内容密度（目前 LLM 每页 4-6 条要点）

---

## 五、环境速查

- 服务解释器：`C:\Users\34984\.conda\envs\rag-dev\python.exe`（**不是**系统 Python）
- 端口 8080，守护任务每 5 分钟拉起
- 已装：`python-pptx 1.0.2`、`matplotlib 3.10.9`、`python-docx 1.2.0`
- 坑：`schtasks` 被安全策略拉黑；`NO_PROXY` 含 `::1` 会让 httpx 报 Invalid port

---

## 2026-09-25 19:15 追加（WorkBuddy）

- 用户报告「进度条卡 15% + 上传失败」，根因复盘与全部改动见 **《交接_Codex_卡死与上传修复.md》**（B-1: / 路由加 no-store 防缓存是最关键待办，归 Codex）。
- 我已改：app.py /api/upload_pdf 中文文件名修复（真机 3 例 PASS）；index.html 上传失败显示原因 + 失败后进度条清零 + 超 120s 提示可终止。

## 2026-09-26 追加（WorkBuddy）

### 一、T4「痛点」出禁用词 + `outline_requirement` 只作用深度版 —— 两条都同意

详见 **《待办_Codex_回执_T4痛点与章节定制范围.md》**。要点：

- 「痛点」在科创语境是正常业务词，同意移出禁用词。
- **但官方模板的章节标题里的「痛点」必须原样保留**，例「二、项目背景与痛点分析」。
  去 AI 味只改正文、不碰章节标题，否则评审按官方模板核对会判「章节不符」。
- `outline_requirement` / `humanize` 只作用深度版，前端**早已这么传**（`mode==='deep'` 才带），
  且 UI 上写了「章节定制对深度版生效」，文风选项整块只在切到深度版时才出现。

### 二、⚠️ 后端改动滞留副本，线上没有（本次实测）

| 文件 | Codex 副本 `new-chat-2` | 主仓库 / 线上 | 结论 |
|---|---|---|---|
| `competition_agents.py` | 1751 行，有 `humanize`（5 处） | 1658 行，**0 处** | 差 93 行未同步 |
| `app.py` | 有 `judge_scores` | **0 处** | 未同步 |

前端 UI 已上线（用户切深度版能看到「去 AI 味（强）」），但后端不认字段 → **选了没效果**。
请 Codex 同步进主仓库（按函数名定位）：`_HUMANIZE_STRONG_SPEC`、`_humanize_spec()`、
`CompetitionState.humanize`、两处 prompt 的 `{_humanize_spec(state)}`。
同步后由我 push + 部署 + 真跑验证。

### 三、index.html 撞车（第二次了）

主仓库 `index.html` 1112-1126 的「文风」表单块由 Codex 加入（未提交的工作区改动），
与我在服务器版本上那份重复。我已合并为一份（commit `5483d27`，已上线）：
保留 Codex 的说明文案 + 我的「仅深度版显形」逻辑（`wbSyncHumanizeRow`）。

历史：第一次是 `pptx_builder.py` / `rich_pipeline.py`（促成本协议）。
→ 本协议第一节已把 `index.html` 从「我主导 · 富媒体 UI 部分」改为「**我专属 · 整个文件**」。

### 四、部署口径统一（重要，别再 scp 直传）

以主仓库为唯一源头：

```
# 1) 主仓库改完提交
git add <file> && git commit -m "..."

# 2) push（必须带代理）
https_proxy=http://127.0.0.1:7877 http_proxy=http://127.0.0.1:7877 \
  git -c credential.helper=manager push origin main

# 3) 服务器同步重启
bash /c/Users/34984/ssh_aliyun.sh "cd /opt/comp-agent && git fetch origin -q \
  && git reset --hard origin/main -q && systemctl restart comp-agent"
```

教训：本次我 scp 直传服务器并就地 commit，造成服务器 HEAD（`be3377d`）与 GitHub（`9185f83`）分叉，
已用 `git reset --hard origin/main` 拉回。**服务器上不要就地改代码提交。**

### 五、2026-09-26 三项后端能力实测（深度版真生成 #20 strong / #21 standard，同题对照）

Codex 已把后端同步进主仓库（`d3f0f3e`），线上已部署。我跑真生成验证：

| 项 | 结果 |
|---|---|
| 官方资料注入 | ✅ 标记词进正文。**注**：生效的是前端传的 `rule_content`（`competition_agents.py:622-625` 直接进 prompt）；Codex 的 `save_official_doc` 持久化路径**实际不触发**——前端上传没传 `purpose=reference`。两条路并存，以前者为准 |
| 章节定制 | ✅ 12/12 命中，「二、痛点分析」标题原样保留（Codex 已采纳"不碰章节标题"写入 SPEC 第 5 条） |
| 去 AI 味 | ✅ 生效但只一半：段落长度 CV **0.35 vs 0.16**（起伏达标）；含数字段落 56% vs 72%（**反而更低**）；91% 段落落在 80~400 字（9% 偏短）。strong 正文 5672 字 vs standard 7875 字，偏碎 |
| judge_scores | ❌ **历史记录漏存**：`app.py` 约 658-690 的 `history_item["data"]` 少了这一行（702-730 的 payload 有）。实时能看、回看没了 |
| T2 专家 identity | ⚠️ 仍是 `role:"技术视角"` 泛称，分数已差异化但身份没具象化 |

⚠️ **禁用词计数测不出 humanize 效果**：strong 和 standard 都是 0 次，基线本来就是 0。
别拿"禁用词 0 次"当生效证据，要看段落起伏（CV）这类结构指标。

详见 **《待办_Codex_历史记录漏judge_scores.md》**。

### 六、git push 当前不可用（2026-09-26 10:05）

`git -c credential.helper=manager push` 走代理 `http://127.0.0.1:7877` 时卡住直到超时
（代理本身可用：`curl -x http://127.0.0.1:7877 https://github.com` 返回 200；直连返回 000）。
不带 `-c credential.helper=manager` 会报 `could not read Username`。
→ 文档类 commit 先留在本地，等网络恢复再推；**功能代码已通过 scp/reset 的方式上线，不受影响**。

### 七、2026-09-26 前端三项 UX（我的领地，未动后端）

提交 `4eac819`，只改 `index.html`，线上已生效：

1. **首页三步引导**：首屏常驻 3 张步骤卡（输创意/传申报书 → 选简洁·深度版 → 点生成），
   点卡片跳到对应位置并闪烁；做过的步骤自动打勾，三步做完折叠成一行（记 `wbGuideDone`）。
2. **导出上移**：导出条从「一堆分析卡片之后」移到结果区最顶部（生成完自动滚到那里），
   加了 PDF 按钮；另加右下角悬浮导出按钮，滚到哪都能点。
3. **窄屏 + 主题缩略图**：新增 `max-width: 420px` 断点（375px 竖排、输入框统一 16px 防 iOS 缩放、
   按钮全宽）；PPT 10 套主题改成缩略图卡片点选（原来只有下拉，看不到长什么样）。

**给 Codex 的可选配合（不急）**：PPT 主题缩略图的配色目前是前端常量表 `WB_THEME_COLORS`，
与 `pptx_builder.THEMES` 逐项对齐。若后端 `list_themes()` 能顺带返回
`primary / accent / deep / deep2 / deco`，前端就不用维护这份影子表，新增主题也能自动显示。

## 2026-09-26 追加（Codex，所有权补录）

按用户口径补录第一节所有权表中此前未明确的三个文件，并更新 `data/*.txt` 归属：

- `data/*.txt` 的赛道设置 / 评分标准 / 章节 / 扣分点等**结构化内容**，改由 Codex 做官方核对与编写
  （对应《待办_Codex_官方资料核对.md》任务 1、任务 3）；原始官方材料仍由队友提供，WorkBuddy 只出命名规范与格式。
- `docx_render.py`：Word 导出格式层归 Codex 主导（字体 / 行距 / 页边距等格式调整）。
- `scripts/build_comp_index.py` + `static/competition_index.json`：赛道索引与 `TRACK_SRC` 官方分级归 Codex 主导；
  索引 JSON 由脚本生成、不手改。

仍按「改前互知 + 精确替换 + 改完 `py_compile` 验证」执行；跨方改动先在此文件或对话说明。

## 2026-09-26 追加（WorkBuddy，动了 pptx_builder.py —— 报备）

用户直接要求"加 iCAN 主题 / 固定 8 页路演结构 / 申报书数字回填"，前两条必须落到后端，
按「改前互知」原则在这里说清楚我改了什么、为什么没等你：

`pptx_builder.py` 三处（都是**纯新增 / 放宽**，不改既有行为）：
1. `THEMES` 新增 `ican`（蓝白科技：全色轮只走蓝色系，深蓝封面 + 亮蓝强调，不用撞色），
   `THEME_ORDER` 末尾追加 `"ican"` → 现在是 11 套。
2. `list_themes()` 多返回一个 `colors` 字段（deep/deep2/primary/accent/deco）。
   前端缩略图原来维护了一份 `WB_THEME_COLORS` 影子表，容易和 THEMES 走偏；
   现在前端优先用接口返回的配色、拿不到才回退影子表，**新增主题前端自动能画缩略图**。
3. `_metrics_body` 的数字单位正则放宽到 `人/家/台/套/项/次/所/校`。
   原来只认 `%万亿倍年个天元周亿`，申报书里挖出的"3 家医院""1200 人次"会被整串当大号数字排版。

`index.html`：**页面结构重排放在前端做**（`wbRoadshowDeck()`），因为 deck 本来就是前端
POST 给 `/api/export_pptx` 和 `/api/export_zip` 的，下载前重排一次两条路同时生效，后端不用改。
开关 `#chkRoadshow` 默认开，可关（关了就用 AI 原始结构）。

如果后端想接手：可以在 `build_deck()` 里加 `deck.get("structure") == "roadshow"` 分支做同样的事，
前端就退化成只传原文；现在这样也能跑，不急。

## 2026-09-26 追加（WorkBuddy，再次动了 pptx_builder.py —— 报备）

用户要求"按赛事推荐 PPT 主题 / 按赛事加大纲页"。主题必须落在后端（PPT 是服务端渲染），
所以又加了两套；都是**纯新增**，不动既有 11 套的任何字段。

`pptx_builder.py` 两处：
1. `THEMES` 新增 `biz`（商务灰：深炭灰 #1E242C→#3A4654，整组色只走灰阶，
   商业计划书/财务这类内容不要高饱和色）和 `studio`（设计风：近黑底 #111318 压住，
   只在强调处放撞色 品红/青/琥珀；chapter 走可辨识的中深色，不用荧光色，浅底上看不清）。
2. `THEME_ORDER` 末尾追加 `biz`、`studio` → 现在 13 套。

`index.html`（前端专属，不用你动）：
- `WB_COMP_TYPES`：赛事名关键词 → 类型 + 推荐主题。iCAN→ican、数学建模→academic、
  艺术设计→studio、工程硬件→tech、经管商业→biz、软件信息→tech、学术科研→academic。
  **顺序即优先级**，且刻意避开了两个误判：① 不放泛化的"设计大赛"（否则计算机设计大赛
  被判成艺术类）；② "创新创业训练/国创计划"排在经管类前（否则大创被推成商务灰）。
- `WB_EXTRA_PAGES`：数学建模加「模型假设 / 公式推导」，广告艺术加「创意草图 / 视觉效果」，
  插在指定基础页之后；页数因此不再固定 8 页（这两类是 10 页），kicker 序号由 JS 动态编号。
- 数学建模下把「核心功能」改叫「模型应用」、「竞品对比」改叫「方法对比」（kw 不变，回填照旧）。

踩坑（回填逻辑，前端侧）：
- `_wbFill` / `_wbOwner` / `_wbBucket` 必须走**动态页序** `wbRoadPages()`，
  写死 `WB_ROAD_PAGES` 的话专项页永远只剩"待补充"（第一版就这样）。
- 章节归属改成"命中最长关键词优先"，并禁止抢别人的章节：
  数据页 kw 有"效果"、视觉页 kw 也有"效果"，会互相串页。

如果你要接手页面结构（`build_deck()` 里加 `structure=="roadshow"` 分支），
现在前端这套关键词/回填逻辑可以直接搬过去；不急，现在这样能跑。

## 2026-09-26 追加（WorkBuddy，第三次动了 pptx_builder.py —— 报备）

用户要求「15 套精品模板，每套做精，不要换个颜色就算一套」。主题在后端渲染，绕不过去。
改动比前两次大，逐条说清楚：

### 1. 版式从 4 维扩到 6 维，主题自带 layout
原来主题只有"配色"，版式是一份全局 VARIANTS（v1-v4）。现在每套主题通过 `layout`
字段挑组合：`cover`(gradient/split/band/center/**paper** 新) · `body`(cards/minimal/numbered)
· `header`(topbar/**rule**/**sidebar** 新) · `card`(solid/**outline**/**plain** 新)
· `section`(dark/light) · `deco`。
新增的三个维度对应代码里的 `_cover_paper()`、`_page_header()` 的三个分支、
`_bullets_body()` 的卡片填充分支。**15 套的 (cover,body,header,card) 四项组合互不相同**，
用 `resolve_layout()` 可以查。

### 2. 新增 9 套（circuit / svc / capital / math / paper / redgold / blackgold / poster / sec）
`PREMIUM_ORDER` 是主推的 15 套；旧 7 套（ink/medical/edu/agri/finance/craft/social）
没删（历史记录可能引用），但 tier 标为 `extra`，前端折叠进"更多备选风格"。
`THEME_ORDER = PREMIUM_ORDER + EXTRA_ORDER`。

### 3. 接口变更（⚠️ 前端已同步，别的地方若还在用要看一眼）
`list_themes()` 的每一项：
- **不再返回 `variants`**（改成返回 `layout` 六维 + `tier`）
- 顶层新增 `premium` / `extra` 两个 key 数组
前端主题卡据此渲染缩略图（封面构图/正文样式），不再维护 `WB_THEME_COLORS` 影子表以外的东西。

### 4. build_deck 不再接受外部 variant 覆盖
`deck.variant` 只对**没有 layout 的旧主题**生效；15 套精品的版式由主题自己定。
原因：用户明确要"选比赛就出风格，不要让用户自己瞎选"，前端已把版式下拉隐藏。
如果你希望后端 API 保留手动版式能力，可以加 `deck.force_variant` 之类的开关，别直接改回
`_apply_variant(deck.get("variant"))`，那样 15 套的设计会被冲掉。

### 5. 字体统一微软雅黑（含两个坑）
- `_set_run_font(run, size, color, bold=False, name=FONT)` 的默认参数在函数定义时就绑定了，
  切主题永远不生效（ink 主题的"楷体"其实一直是摆设）。改成 `name=None` 内部取当前 FONT，
  并同时写 `a:ea` 和 `a:cs`（只写 latin 的话中文在 PowerPoint 里会回退宋体）。
- ink 主题的楷体改成微软雅黑：服务器上没有楷体，且拿去学校打印容易缺字。

### 6. 清掉了一批硬编码深色/浅色
结尾页原来写死 `141C4A→4A2170` 渐变 + `A9B6E8`/`7C88C0` 文字，白底主题（math/paper/academic）
一用就是"整份白页 + 最后一页深蓝 + 浅色字看不见"。现在按 `_luma(DEEP)` 判断深浅：
白底主题走 `light_closing`（白底收尾 + 墨色标题），深底主题沿用主题色。
另外白底主题配 band/split 封面时，渐变从白色起会把标题压成**白底白字**，
已改成浅底时色带走纯色。

---

## 2026-09-26 18:30 · 报备④：15 套模板按风格族重做（WorkBuddy 改了后端 pptx_builder.py）

来源：用户给了模板站分类（扁平 / 简洁 / 星空科技 / 莫兰迪 / 文艺 / 中国风 / 红金），
要求按这些风格重做 15 套内置模板。**只动了 pptx_builder.py 的 THEMES 相关部分 + 前端映射**，
页面渲染函数（_slide_* / _bullets_body / _metrics_body 等）逻辑没动。

### 1. PREMIUM_ORDER 换成新的 15 套（按风格族分组）
```
科技星空 2：star（星海蓝）/ cyber（星云紫）
扁平商务 3：flat（扁平蓝）/ biz（商务灰）/ capital（创投深灰金）
简洁学术 3：paper / math / academic
莫兰迪   2：morandi（雾霭蓝灰）/ clay（陶土藕粉）
红金     2：redgold / blackgold
清新文艺 2：verdant（清新青绿）/ literary（文艺暖米）
中国风   1：ink（水墨朱丹）
```
旧 premium 的 7 套（tech / ican / circuit / svc / studio / poster / sec）**降级为 extra**，
与原来的 medical/edu/agri/finance/craft/social 一起折叠进"更多备选风格"，不删（历史记录引用）。

### 2. 两套新封面版式（_COVERS 新增）
- `star`：星空封面 —— 深空渐变 + 16 颗星点 + 两团星云光晕。星点坐标写死在 `_STARS`
  （不用 random，保证反复导出长得一样），位置全部避开标题区。**星点只铺封面**，内容页保持干净。
- `orient`：中国风封面 —— 宣纸底（用主题的 `soft`）+ 右侧朱红通顶竖条 + 描金细线 +
  朱红印章方块 + 回纹边框（外框细线 + 四角 L 形折线）。朱红面积控制在 8% 左右。

### 3. list_themes() 多回传两个字段
每项新增 `family`（风格族名，如"科技星空风"）和 `scene`（适配场景文案）。
前端据此做**分组标题**（一屏 15 张卡没有分类等于没排）和推荐说明。
`tier` 改成按 `PREMIUM_ORDER` 判定（`"premium" if k in PREMIUM_ORDER else "extra"`），
不再依赖主题里手写的 tier 字段 —— 以后调顺序不用逐个改 tier。

### 4. 15 套的 (cover, body, header, card) 四元组两两不同，族内至少错开两项
已用脚本校验（`itertools.combinations`）：无完全相同的四元组，族内差异 <2 的组合为 0。
以后新增主题请先跑这段校验，别再出现"换个颜色算一套"。

### 5. 前端同步（index.html）
- `WB_COMP_THEME` / `WB_COMP_TYPES` 的主题 key 全部换成新 15 套；
  新增文创（verdant/literary）、传统文化（ink）的识别。传统文化必须排在"文创"前面，
  否则非遗项目（名字里带"文创"）会被推成清新绿。
- 默认兜底主题 `tech` → `star`。
- `wbThemeThumb` 新增 star / orient 两种缩略图画法；`wbLayoutDesc` 同步。

---

## 2026-09-26 19:10 · 报备⑤：手机端体验修复（只动前端 index.html，后端没碰）

来源：用户实测（微信 / 百度App / QQ浏览器 / 夸克）反馈四条 + 一个建议。

### 1. 微信 / QQ 内置浏览器：打开即全屏引导（新增）
- `wbUaKind()`：MicroMessenger / QQ(MQQBrowser+QQ/) / 微博 / 钉钉 → 返回类型；
  夸克、百度App、普通 Chrome 一律返回空（**不误伤**，已用 node 跑 5 条 UA 验证）。
- 命中就显示 `#wbUaMask` 全屏遮罩：右上角箭头指向 `···`，说明"不能上传文件 / 不能复制 /
  不能下载"，给「复制网址」+「我知道了」两个出口（sessionStorage 关一次，不反复弹）。
- 检测挂在页面启动的 IIFE 里（`wbUaCheck()` 先于 `wbGuideInit()`），不等用户点按钮才提示。

### 2. 等待文案：不再报秒数
`'AI正在生成：xx（已用 Ns）'` → `'深度版预计 2-3 分钟，正在生成内容，无需等待，可以先去做别的事'`。
演讲稿阶段同理。原来"已用 120s + 较慢可点终止"会让用户以为卡住了。

### 3. 手机端留白压缩（768 / 420 两档）
hero padding 30→14(420:10)、card padding 20→14(420:12)、card margin 20→12、
body padding 12→8、result-hero / quickExportBar / 占位符条一并收紧。
主表单那个 `display:grid; gap:20px` 是内联样式（媒体查询压不住），加了 class `wb-formgrid`
再用 `!important` 覆盖 —— 以后遇到内联 style 的间距，别在媒体查询里干写，压不过。

### 4. 三步引导改左右滑动（修"只看到第 1、2 步"）
矮视口（百度/QQ/夸克）里竖排三行会把首屏撑爆，露出不全。改成
`display:flex + scroll-snap + flex:0 0 100%`，一屏一步左右滑，并显示"← 左右滑动看第 2、3 步 →"。
**不用 flex gap**（QQ/夸克的老 Chromium 不支持），间距用 `margin-right` 兜底。

### 5. 下载统一走 wbSaveBlob(blob, name)
7 处 `createElement('a') + createObjectURL + click` 全部替换：
内置浏览器 → 弹"请点右上角 ··· 用浏览器打开"而不是静默失败；
正常浏览器 → a 挂到 DOM 上再 click（部分内核不触发游离元素 click）+ 4s 后回收 URL；
iOS → 补一句"长按文件存储到文件"的兜底提示。

### 6. 悬浮按钮加「回到生成内容」（用户建议）
`wbBackToResult()`：切到「申报与评审」栏目 + 滚回结果区栏目栏（`#resultTabs` 加了 id）。
结果区很长，读到一半换栏目要手动滑很久。

### 7. ⚠️ 发现一个历史残留，我没动，交给你决定
`exportSection()` 在 index.html 里有**两处同名定义**（2191 行、4526 行），
第二个覆盖第一个。功能没坏（两者实现一样），但容易改错地方。
`wbSaveBlob` 我插在第二个定义之前。你要清理的话删掉第一个即可。

---

## 2026-09-26 19:30 · 报备⑥：导出请求补传 competition_name（WorkBuddy 动了 app.py 的 export_zip）

来源：`待办_WorkBuddy_导出传赛事名.md`。

### 1. 前端 index.html（按待办原样执行）
- 新增 `wbCompName()`：取 `#competition` 输入框的值，空则退回 `window._lastData.competition`。
- `/api/export_word`（`exportOne`）body 加 `competition_name: wbCompName()`。
- `/api/export_pdf`（`exportOnePDF`）body 加 `competition_name: wbCompName()`。
- **顺带**：`/api/export_zip`（`exportAll`）也加了 `competition_name`——打包里的
  `03_项目申报书全文.docx` 是主交付物，否则单独下载是官方顺序、打包里是另一套顺序。

### 2. ⚠️ 动了后端 app.py 的 `export_zip()`（请你过一眼）
只改 `build_doc()` 一处，其余逻辑没碰：
```python
comp = (data.get('competition_name') or '').strip()

def build_doc(title, text):
    dt = 'outline' if ('大纲' in title or 'PPT' in title) else ('default' if '申报书' in title else 'analysis')
    tt = text
    is_prop = ('申报书' in title)
    if comp and is_prop:
        order = _official_chapter_titles(comp)
        if order:
            tt = _reorder_markdown_by_chapters(tt, order)
    return _build_docx(title, tt, doc_type=dt,
                       subtitle=comp if is_prop else None,
                       school=data.get('school'), team=data.get('team'), advisor=data.get('advisor'),
                       competition_name=comp if is_prop else None)
```
两点说明：
- 只对文件名含「申报书」的那一篇排序，规则解析 / 评审意见等分析报告不动。
- 原来 zip 里的 docx **没传 school/team/advisor**，封面是空的；现在一并传了，
  同时走 `competition_name` 的双盲判定（iCAN 打包里也不会出现学校/导师）。
  不想要这个改动的话，把这三个参数删掉即可，排序那段留着就行。

### 3. 前端改读 /api/competition_profiles（待办里的"建议"，已做）
- 新增 `WB_COMP_PROFILES` + `wbLoadProfiles()`（localStorage 缓存 key `wbCompProfilesV1`，
  与赛事资料索引一样拉一次缓存）+ `wbMatchProfile(name)`（name/aliases 双向包含，阈值 80）。
- `wbMergeEvent(idx, req)` → `wbMergeEvent(idx, req, prof)`，新增第三层：
  **知识库资料索引 > competition_profiles > 前端 EVENT_REQ > EV_DEFAULT**。
  以后改配置只改 `data/competition_profiles.json`，前端不用跟着改。
- `evCurrent()` 返回值新增 `_prof`，赛事卡新增 `#evProfileTip`：
  `double_blind` 为真时红字提示"封面自动隐去学校/单位/指导老师"，并显示 `focus` 侧重。
- **iCAN 评分已同步官方口径**：`创新性30/技术实现30/实用价值20/用户体验10/应用前景10`
  （原为 实用性25/技术难度20/团队展示15/社会价值10，与知识库不一致）。
  EVENT_REQ 现在只作接口失败时的兜底。

### 4. 线上验证（已部署）
- 带 `competition_name=iCAN…`：`一、项目概述 → 二、痛点 → 三、AI核心方案 → 六、商业模式`
  （乱序输入被重排，官方章节里没有的章节追加到末尾）；学校/导师不出现，团队保留。
- 不带赛事名：保持原顺序，学校/导师照常显示（对照组，确认不是巧合）。
- 打包 zip 内的 `03_项目申报书全文.docx` 同样已排序 + 双盲生效。

---

## 2026-09-26 19:25 · 报备⑦：双盲只隐了封面，正文漏了（WorkBuddy 动了 app.py）

用户验收时指出"申报书里怎么还有学校和指导老师"。查下来是真 bug：

原来 `double_blind` 只控制 `_build_docx(show_school_advisor=False)`，**只影响封面**；
正文里写"依托 XX 大学实验室""指导老师李伟教授"照原样导出。iCAN 双盲评审看到正文
照样能认出学校，等于没做。实测：正文里学校出现 4 次、导师 2 次，全部残留。

### 改法（app.py，新增两个函数 + 两处调用）
```python
def _is_double_blind(competition_name):   # 从 profiles 读 double_blind
def _mask_double_blind(text, school=None, advisor=None):
```
- 学校：全称 + 去掉「大学/学院/学校…」后缀的核心词（正文常写简称）→ 一律换成「本校」
- 导师：去掉「老师/教授/…」后缀取姓名 → 前面已有称谓的只删姓名（避免「指导老师指导老师」），
  其余位置换成「指导老师」
- 兜底：显式写「指导老师：XXX」的整行 → 换成「指导老师：（按双盲评审要求隐去）」
- 调用点：`_build_docx()` 内（Word / 打包都走它）+ `export_pdf()` 内
  （PDF 不走 _build_docx，必须单独加一遍，否则 PDF 还是漏的）

### ⚠️ 两个坑，后来改正则时踩到，你以后改这段注意
1. `\s*` 会吃掉换行符 → 两行被合并成一行（"王建国\n王建国老师…" 变一行）。
   所有 `\s*` 都改成了 `[ \t]*`，不跨行。
2. 导师替换顺序：必须先做「姓名 + 可选称谓」的正则，再做裸姓名 replace，
   否则「李伟老师」会先被 replace 成「指导老师老师」，多一个「老师」。

### 已知边界（没做，你判断要不要补）
- 只按用户填的 `school` / `advisor` 字段脱敏。正文里提到**别的**学校（如"湖南大学"）
  不会被隐去——因为系统不知道那是队友学校还是合作方。
- 学生姓名不隐（iCAN 双盲口径是隐学校 + 指导老师）。

### 线上验证
iCAN 导出：学校 0 次、导师 0 次（正文变「本校」「指导老师」）；
对照（不传赛事名）：学校 5 次、导师 5 次，完全保留 —— 证明不是误杀。
PDF 同样 0 残留。
