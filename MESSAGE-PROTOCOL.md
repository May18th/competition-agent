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
