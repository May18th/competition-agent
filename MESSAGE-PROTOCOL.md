# 多智能体协作协议（科创赛事助手）

> 参与方：WorkBuddy（我，负责富媒体与 PPT 全链路）／Codex（负责后端 Agent 链）
> 建立时间：2026-09-25
> 起因：双方曾在同一时段修改 `pptx_builder.py` 与 `rich_pipeline.py`，虽未造成代码丢失，但存在覆盖风险。

---

## 一、文件所有权（硬性）

| 文件 | 归属 | 说明 |
|---|---|---|
| `competition_agents.py` | **Codex 专属** | 我不改，Agent prompt / 图结构都归你 |
| `app.py` 的 `_run_generation` / Agent 编排部分 | **Codex 主导** | 我只改导出类路由，改前会说明 |
| `pptx_builder.py` | **我（WorkBuddy）主导** | 你可以在末尾**追加新 THEMES 条目**，但不要改函数体 |
| `chart_renderer.py` | **我主导** | 新增图表类型欢迎追加，请先告知 |
| `rich_pipeline.py` | **我主导** | prompt 调整属于我这边 |
| `index.html` | **我主导** | 富媒体 UI 部分 |
| `app.py` 导出类路由 | **我主导，改前说明** | 指 `export_pptx` / `export_zip`，其余仍归 Codex |
| `data/*.txt` 赛事资料内容 | **队友提供** | 我只出命名规范与格式，不写业务内容 |
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
