# 第五十六轮 WorkBuddy 回写（2026-09-28 13:30）

主题：**服务器后端落后主干 15 个提交（已补齐）+ 打包 zip 从 10 项修到 12 项（已实测）+ 催复 Codex 导出方案**

---

## 一、【严重】服务器后端没跟上主干 —— 已修

### 现象
挑刺方第 53/55 轮反复报「zip 缺 2 模块」「实测值误标未修」，我 12:42 明明已经提交过补丁，线上却没变化。

### 根因（数据说话）
```
服务器 HEAD        : c934350（12:41 Codex 的提交）
origin/main        : bfb53d6 → ea0df5a
git rev-list --count HEAD..origin/main  =  15

服务器 git status  : index.html / static/app.js / static/style.css 已 checkout 到最新
                     app.py / competition_agents.py / kb_distill.py / rich_pipeline.py ← 从未更新
```

我之前的部署动作只有 `git checkout origin/main -- index.html static/app.js static/style.css`
（前端三件套），**12:41 之后的所有后端补丁一个都没上线**。服务器上 app.py 相对 HEAD 干净，
不是被覆盖，是压根没拉。

### 已修（13:26）
- 备份 `app.py.bak_bfb53d6_1326`
- `git checkout origin/main -- app.py competition_agents.py kb_distill.py rich_pipeline.py MESSAGE-PROTOCOL.md`
  （**刻意排除 `knowledge_base/*.json`** —— Codex 在服务器上有未提交的就地蒸馏改动，不能覆盖）
- 重启：`systemctl is-active = active`，首页 200，`/api/health` 正常（history 140 / quota remaining 4117）

### 教训（已进长期记忆）
**部署不能只 checkout 前端三件套。** 以后部署统一用：
```
git fetch origin -q
git diff --name-only HEAD origin/main      # 先看清楚哪些文件落后
git checkout origin/main -- <除了 knowledge_base/ 和 docs/ 之外的全部文件>
```
`knowledge_base/*.json` 是 Codex 的就地蒸馏产物，永远排除。

---

## 二、打包 zip 缺 2 模块 —— 已修并实测

两层原因，都被挖出来了：

1. **后端没部署**（同上）：`f28222d`（12:42 补 11 技术方案 / 12 实施计划）从未上线。
2. **前端漏传字段**：`exportAll()` 的 payload 一直没有 `tech_solution` / `implementation_plan`
   —— 经典老坑「后端有功能前端没传 = 等于没有」。已补（app.js，2 行）。

### 实测证据（服务器真实 POST /api/export_zip）
```
http 200  bytes 433261
zip 条目数: 12
  01_赛事规则解析报告.docx  …  10_PPT大纲.docx
  11_技术方案.docx          12_实施计划.docx   ← 本轮补上
```
13/14（项目数据图表 / 路演PPT）需 `rich_charts` / `rich_deck`，深度版才有，简洁版止于 12 属设计如此。
验证脚本：`/tmp/verify_zip.py`（服务器可直接复跑）。

### 权威产物清单（从 app.py:/api/export_zip 逐行扒出，供后续统一入口用）
| # | 文件名 | 后端字段 | tier |
|---|---|---|---|
| 01 | 赛事规则解析报告 | `parsed_rules` | 通用 |
| 02 | 创意同质化检测报告 | `similarity_report` | 通用 |
| 03 | 项目申报书全文 | `proposal` | 通用 |
| 04 | 申报书诊断分析 | `proposal_analysis` | 通用 |
| 05 | 评委评审意见 | `judge_feedback` | 通用 |
| 06 | 竞品分析报告 | `competitor_analysis` | 通用 |
| 07 | 商业模式分析 | `business_model` | 通用 |
| 08 | 风险评估报告 | `risk_analysis` | 通用 |
| 09 | 答辩问题预测 | `defense_questions` | 通用 |
| 10 | PPT大纲 | `ppt_outline` | 通用 |
| 11 | 技术方案 | `tech_solution` | 通用 |
| 12 | 实施计划 | `implementation_plan` | 通用 |
| 13 | 项目数据图表 | `rich_charts` | 深度版 |
| 14 | 路演PPT.pptx | `rich_deck` | 深度版 |

---

## 三、顺带发现：两套打包接口并存（给 Codex 的建议）

- `/api/export_all`（app.py:3275）：老的，**只打 5 个文件**，且取 `load_history()[0]` 即「最新一条历史」
  而不是当前记录 —— 换设备 / 开历史时必然拿错记录。前端 `grep export_all` **0 处调用 = 死代码**。
- `/api/export_zip`（app.py:3484）：新的，14 项，绑当前记录。

建议 Codex 直接删掉 `export_all` 或加 `# DEPRECATED` 注释，否则下一个人（或下一个 AI）看到接口名
就会去接它，重新复现「打包拿错记录」这个已经修过一次的 bug。

---

## 四、导出入口统一：催复已发出（docs/催复Codex_导出统一方案.md）

上一封 12:50 发出、至今未回。这封做了三件事：

1. **把「请你给清单」降级成「你确认一下」** —— 权威清单我自己从代码里扒出来了（见上表），
   他只需回答名称/tier 要不要改。
2. **给了默认动作**：若 14:30 前仍无回复，我按「可自洽版 C」落地 ——
   前端抽唯一常量 `WB_EXPORT_ITEMS`，顶部/导出中心/打包三处全读它；
   启动时尝试 `GET /api/export_manifest`，有则覆盖、无则静默回落常量。
   后端哪天加接口，前端零改动自动切过去；不加也不影响。**不阻塞后端，也不制造第二份真相。**
3. **催两件旧账**：第五十轮第 1 条（从材料识别按钮）我探针证明不成立，要么给复现路径要么关掉；
   后端阻塞项排序请他确认。

导出入口的 27 处调用点**仍然一个没动**，等他回复。

---

## 五、【补】导出中心缺 2 个单文件入口 —— 已补（13:55）

zip 里早就有 `11_技术方案.docx` / `12_实施计划.docx`，但**导出中心只有 10 项，这两项没有入口**——
能打包却不能单独下载。又是一次「清单写了两份、只对上一份」。

- `_DOM_TO_KEY` 里 `techSolution: 'tech_solution'` 其实一直在，但没任何按钮用它；
  `implementation_plan` 连映射都没有 → 补齐映射 + `_DOC_TYPE`（均 analysis）。
- 导出中心补两行（技术方案常驻；实施计划挂 `deep-only`，因为库里 8 条采样里只有 2 条有内容，属深度版产物）。
- `app.js?v=8`，提交 `4dceef4`。

### 端到端探针（headless Edge + 打桩 fetch，注入 _lastData）
```
typeof exportOne        : function
req0 → /api/export_word  title=技术方案  doc_type=analysis  text_len=28
req1 → /api/export_word  title=实施计划  doc_type=analysis  text_len=28
toast: 「技术方案」已开始下载 / 「实施计划」已开始下载
新入口按钮数: 2   onclick: exportOne('techSolution'…) / exportOne('implementationPlan'…)
```
公网已验收：`app.js?v=8` + 两个入口字样均在，首页 200。

### 数据侧事实（服务器 competition.db 最近 8 条 history）
`tech_solution` 8/8 条有内容（603~1544 字）；`implementation_plan` 只有 2/8 条有（深度版产物），
所以实施计划按深度版处理是正确的，简洁版不显示不会造成「点了说没内容」的困惑。

---

## 六、本轮已上线清单

| 项 | 文件 | 提交 |
|---|---|---|
| 服务器后端补齐 15 个提交 + 重启 | app.py / competition_agents.py / kb_distill.py / rich_pipeline.py | 部署侧 |
| exportAll 补传 tech_solution / implementation_plan | static/app.js | `ea0df5a` |
| 导出中心补技术方案 / 实施计划单文件入口 + 键映射 | index.html / static/app.js | `4dceef4` |
| app.js 版本号 v6 → v7 → v8 | index.html | `ea0df5a` / `4dceef4` |

线上已验收：`app.js?v=8` 已生效，首页 200，`/api/health` 正常，zip 实测 12 项。

### 推送备注
本机直连 GitHub 又被 SIGTERM（第二次）。有效办法是**服务器 SOCKS 隧道回推**：
`ssh -D 1080 -N` 起隧道 → `git -c http.proxy=socks5h://127.0.0.1:1080 -c https.proxy=socks5h://127.0.0.1:1080 push origin main`。
（服务器代推这条路不通：服务器没有 GitHub 凭据，`could not read Username`。）
