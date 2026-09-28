# WorkBuddy 回执 · 第一百九十三轮（2026-09-29 05:10，前端线全量清零 + 一个 P0 安全止血）

提交：`92e1c6f`（P1 批次）、`a378a0f`（P2 批次）、口令脱敏提交（紧接着）。线上版本号 **v=20260929c**。
服务器 `/opt/comp-agent` 已部署并 `safe_restart`，备份在 `/tmp/wb_bak_*_20260929_033943` 与 `_20260929_050512`。

本轮按用户「多任务默认并行」的指示，把剩余项拆成 4 条线同时跑（3 个 Agent + 我自己一条），下面按线汇报。

---

## 一、P0 安全止血（顺手发现，最高优先）

**发现**：`May18th/competition-agent` 是 **PUBLIC** 仓库，而 198 轮账号体系的**明文口令被写进了入库文档**——
`MESSAGE-PROTOCOL.md:2184`（`3498414260 / ******`、`admin / ******`、`kcwx123 / ******`）、
`docs/指令_2026-09-28.md` 201 轮段落（7 处）。等于把后台账密公开发在了 GitHub 上。

**已做**：共 11 处明文口令脱敏为 `******`，已提交。
**未消除的风险（必须用户拍板）**：git **历史提交里仍保留明文**。脱敏只改了当前 HEAD。
正确处置二选一：
1. 立刻把仓库改成 Private（最快，但历史仍在，将来转 Public 会再次泄露）；
2. 轮换后台口令（推荐，配合改 Private 一起做）。
`口令备忘.md` 与 `.env` 经确认**未被 git 跟踪**（已在 .gitignore），没有入库，本机保留明文未动。

**顺带实测澄清（不是 bug）**：`/admin` 裸访 401 是「未登录」的正常行为，不是 197 轮 401 死锁复发。
服务器审计日志 04:50 `user=3498414260 ... ok role=admin` 证明后台登录可用；我的 curl 拿 400 是因为没带 CSRF，属防抖生效。

---

## 二、H4 截断根治（第二段，用户点名项）

上次只修了 `.card{overflow:hidden}`，这次把**真正的第二个裁切源**挖出来了：

| 位置 | 原写法 | 问题 | 现写法 |
|---|---|---|---|
| `.deck-card` | `aspect-ratio: 16/9` | PPT 预览卡高度被比例**钉死**，正文一多就被 `overflow:hidden` 从底部整段裁掉 | `min-height: 150px`，高度由内容撑，同行卡片靠 grid `stretch` 拉齐 |
| `.deck-card .dc-body` | `overflow: hidden` | 内容超了直接吞 | `overflow: visible` |
| `.dc-mini th/td` | `nowrap + ellipsis + max-width:84px` | 「市场规模 1.2 亿元」被截成「市场规…」 | `normal + word-break:break-word + overflow-wrap:anywhere`，不限宽 |

服务器复查：`grep -c "max-width: 84px" static/style.css` = **0**，写死数字残留清零。

---

## 三、其余前端项（并行线产出）

- **L7 占位词清零**：`wbDataTodoScan` 数不出条数时填「若干」，页面变成「有 若干 项数据需要替换」。
  改为数得出来报数、数不出来说定性结论（`清单里有数据需要替换成真实值（按正文里的标记逐条核对）`）。
  全仓复查：仅剩我新增注释里提到的「若干」二字，页面文案已无。
- **L8 favicon**：`static/favicon.ico` 已生成（16/32/48 三尺寸，由 `logo.png` 用 PIL 程序化转换，5.2KB），
  index.html 增加 `<link rel="icon" href="/static/favicon.ico" sizes="any">`。服务器 `ico=200`。
- **M10 赛事规则来源与核实日期**（新）：规则解析卡片下方新增 `#ruleSrcNote`。
  实测三种输入：iCAN → `评分口径来源：官方规则（核实 2026-09-28）· https://www.g-ican.com/...`；
  挑战杯（track 无 source）→ `内置评分库（官方来源待核）`；未知赛事 → `通用评审标准（本赛事官方口径待核）`。
  **不编造任何 URL/日期**——没有 source 就老实标待核；赛道 note 含「待核实」时额外提示「暂按通用标准评分」。
- **M7 前端瘦身**：`app.js` 478,674 → **448,305 B（-6.34%）**，20 个纯数据常量外置到新 `static/wbconst.js`。
  校验做到了三层：常量**逐字节一致**（20 个 JSON md5 全部匹配）+ 反向重建 md5 与原始 app.js 一致 +
  headless Edge 真实页面 **pageErrors=0**、`/static/wbconst.js` 与 `app.js` 均 200。
  ⚠️ 如实说明：这只动了 6%，**478KB 里 94% 是代码不是数据**，「巨石拆分」这一目标本档没有真正达成；
  且两文件合计净 +1,371 B，对首屏没有优化价值，只是把文件切开。真正的拆分要动函数结构，赛前不建议做。
- **L3 生产目录清理**：28 个一次性调试产物（dump/bundle/patch/临时 js）移入 `_archive_tmp/` 并加 `.gitignore`。
  **只移动不删除**；别人的 `app.py.bak_*`、项目文档、`_wbcheck.py` 一律未动。`git status` 里没有误伤（无 ` D`）。

---

## 四、H8 导出文档口径（扫描结论，与预期不同）

派 agent 全量扫了 `app.py / pptx_builder.py / competition_agents.py / rich_pipeline.py` 及所有导出函数：

- **代码里 0 处真写死**：命中的全是 docstring / 注释 / 日志 / 排障文案，与导出件正文无关。
- **真正的存量在交付物**：`README.md`（3/14/15/32 行）和 `项目说明.docx` 正文里还是
  「LangGraph+Flask」「4个Agent串行」「30秒/1-2分钟」「500字/2000字」。这两处不是代码生成的，是手工产物。
- **新发现的口径冲突（建议记入漏洞库）**：
  1. `competition_agents.py:6/2727/2761` 与 `app.py:27/3174/3334/3345` 显示 **LangGraph 仍在真实使用**，
     但 `项目说明.md` 已改成「去 LangGraph」——文档与代码事实相反，验收方对照会抓。**以代码为准修文档**，不要为了对齐文档去删 LangGraph（那要动编排主链路，风险大）。
  2. `competition_agents.py:2156/2158` docstring 写「约 1300 字」，与承诺的「2000~4000 字级」矛盾。
     ⚠️ 只改注释文字，**不要改 prompt 字符串**——改 prompt 会改变生成行为、影响实测字数分布，需另跑实测再定。

`README.md` 与 `项目说明.docx` 的同步由另一个并行 agent 在处理，完成后单独补回执。

---

## 五、没能验证的项（如实）

1. **公网端到端渲染**：本机访问不了 kechuang2026.cn（TLS/403），所有页面级验证都在服务器 `curl` + headless 本地副本上做的。
   服务器冒烟全绿：`home=200`、`wbconst=200`、`appjs=200`、`/admin/login=200`、`/admin/vulns=200`、`/api/health` 正常（已无 `history_count`，M11 生效）。
   但**真机/移动端观感**（尤其 PPT 卡片去掉 16:9 后的排版）没有真机截图，需豆包或用户肉眼复核。
2. **M7 拆分后依赖后端数据的业务链路**：本地静态服务没有 Flask，`/api/*` 全 404，
   下拉/历史/导出等真正消费这些常量的功能**没跑端到端**。已证明的是「加载期零报错 + 常量逐字节一致 + 主流程初始化跑完」。
3. **M10 标注行的真实排版**：函数级实测通过，未在真实 DOM 里目视过。

---

## 六、给 Codex 的剩余项

1. **【P0】公开仓库明文口令**（见第一节）：改 Private + 轮换口令。历史里的明文我改不掉，需要你配合。
2. **H8 交付物口径**：`项目说明.docx` 需以修好的 `项目说明.md` 为唯一源重制；`README.md` 同步。
   LangGraph 那句请按**代码事实**写（仍在用），别照抄「已去 LangGraph」的错误表述。
3. **漏洞库数据脏**：`/api/vulns` 61 条里 `updated_at` **全为空**（更新时间列全是 `-`），
   `owner` 字段混进了 `未修复/待核实/已确认/待审计/豆包` 这种非责任人取值。需要清洗 `data/vulns.json` 或修解析。
4. **M7 后端（app.py 巨石拆分）**：前端这档只做到 6%，后端按你自己的判断来，赛前求稳建议留赛后。
5. **L5 导出文件名**：`app.py:5141` 的 `_deck_export.pptx` 临时名，按「{赛事}_{创意}_路演PPT.pptx」规范命名（八个入口同规则）。
6. **L6 PPT 无图**：8 页 0 图，需嵌入图表/示意图。

---

## 七、本轮提交

| commit | 内容 |
|---|---|
| `92e1c6f` | H4 截断二段 + L7 占位词 + L8 favicon + v=20260929a |
| `a378a0f` | M10 规则来源标注 + M7 前端瘦身（wbconst.js）+ L3 归档 + v=20260929c |
| （口令脱敏） | MESSAGE-PROTOCOL 4 处 + 指令文档 7 处明文口令 → `******` |

部署方式：bundle（`92e1c6f..HEAD`）→ scp → 服务器 `git fetch + reset --hard + safe_restart`。
服务器 push 无凭据，github 同步走本机 SOCKS 隧道（`ssh -D 1080` → `git -c http.proxy=socks5h://127.0.0.1:1080 push`）。
