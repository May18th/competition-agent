# WorkBuddy 回执 · 第二百三十四/二百三十五轮（2026-09-29 11:40）

部署版本 `v=20260929i`，提交 `35101d2`（234 轮 + 合入 Codex 218/219/220 WIP）、`cadc891`（235 轮 PPT 清洗）。
GitHub 已同步（`origin/main` == 本地，`0 0` 无分叉）。

---

## 一、P0：Word 导出全线 422 —— 三个根因同一轮修完

豆包实测的现象是「简洁版被打分门拦、深度版被 TOC 门拦，两种档位都导不出 Word」。
查下来不是一处，是**三处叠加**：

| # | 根因 | 修法 |
|---|---|---|
| ① | `docx_render._add_toc` 只写静态页码，**没有 TOC 域** | 写入可刷新域 `TOC \o "1-2" \h \z \u`，静态目录作为域结果缓存（Word 可 F9 刷新，WPS 照常显示） |
| ② | `export_guard.check_word_toc` 硬编码 `w:val="Heading1"` 判定标题 | 改成「按实际存在的最高层级判定」。渲染器把正文 `## 章节` 挂成 **Heading2**，全文没有 Heading1 是正常的，旧规则 100% 误判 |
| ③ | 打分门 `_export_review_gate` 签名默认 `mode="deep"`，简洁版被深度版标准拦死 | 后端取 `data.mode`；**前端 export payload 此前压根没有 mode 字段**，一并补传 |
| ④ | 连带：短文档（<2500 字）`build_docx` 本就不出目录，但门禁无条件要求 TOC 域 | 门禁用**同一个 2500 阈值**豁免，简洁版不再被拦 |

### 服务器真环境端到端实测（POST /api/export_word，带签名 cookie）

```
COOKIES: ['comp_uid']
[PASS] fast_long    HTTP 200    39758 bytes  TOC域=True(期望True)  H1=1 H2=4
[PASS] deep_long    HTTP 200    39758 bytes  TOC域=True(期望True)  H1=1 H2=4
[PASS] fast_short   HTTP 200    39424 bytes  TOC域=False(期望False) H1=1 H2=3
[PASS] thin_doc     预期被拦 HTTP 422 : 导出质量未达标：Heading 层级过少（2）

OVERALL: PASS
```

第 4 条（极薄文档：文档主名 + 仅 1 个章节 = 2 个标题）**预期被拦**——
`quality_gate.check_docx` 的「Heading 数 <3」是**无条件**硬校验，这是有意的质量控制。
我保留它，是为了证明这次改动没有把质量门改废。

> 说明：我最初造的短用例只有 1 个章节，一度判 FAIL。查清后确认是**我的用例不真实**
> （真实简洁版至少 3 个章节），不是代码 bug —— 已改成「真实形态 PASS + 极薄形态预期被拦」双用例。

---

## 二、235 轮 PPT 产物清洗（大纲页 + Markdown 残留）

豆包实测深度版 PPT 36 页：第 2 页残留「路演 PPT 大纲（17页）」，正文页残留 `*标题：**`。

清洗做在 `pptx_builder.build_deck` **入口**，覆盖打包 / 单独下载所有路径：
1. 丢弃大纲规划页（正则命中 title/subtitle/kicker 即丢）；
2. 递归清洗 slide 全部文本字段的 Markdown；
3. ⚠️ `meta.project / one_liner / competition` 是 **deck 顶层字段、不进 slides** ——
   第一次漏了，结果整副 PPT **每一页页眉都挂星号**，补洗后清零。

服务器真环境实测（构造带脏数据的 deck）：

```
总页数: 4        （清洗前 5 页，大纲页已丢）
  p1 智能助老陪伴机器人 / iCAN 大学生创新创业大赛 · 2026-09
  p2 市场分析 / 目标人群：60 岁以上独居老人超 2.9 亿 / 付费意愿每月 200 元以上 / 核心结论：需求真实存在
  p3 竞品对比
  p4 谢谢

  大纲页残留 : 0      星号残留 : 0      井号残留 : 0
VERDICT: PASS
```

---

## 三、234 轮其余项

- **③ 打回原因明细**：后端打分门已回传 `reasons`、前端已展示；导出终检门 `export_quality_fail`
  此前只弹「导出失败」，我补了分支——转述具体原因 + 明确「正文还在页面上，不用重头再来」。
- **⑤ PPT 深度版前置说明**：已有（`wbSyncPptRow`：无 deck 时按钮变「深度版可用」+「（深度版）」标识）。
- **② 达标线注释统一 / ④ 评分口径统一**：属 `app.py`，**Codex 正在实时改这个文件**（11:25 还有新 WIP
  进来：211 轮并发限流 `_MAX_PER_KEY`、后台写审计 `_audit_write`），我没有抢，留给 Codex。

---

## 四、过程中的一次生产事故与止血

按 5 个文件 checkout 部署后重启，服务**直接崩**：
`ModuleNotFoundError: No module named 'vulns_data'` —— 新版 `app.py` 依赖的新模块没跟着过去。

- 止血：从 `/tmp/wb_bak_app_238_*` 还原 → `safe_restart.sh` → curl 200。
- 改法：**按完整变更清单部署**（`git diff --name-only`），不再手挑文件；
  并且**重启前先干跑** `.venv/bin/python -c "import app"` 拿到 `IMPORT_OK` 再重启。

---

## 五、线上复查（11:38 实测）

```
/ = 200   /admin/login = 200   /admin = 401(登录门有效)   /api/health = 200
app.js/style.css/wbconst.js/favicon.ico = 200
版本 v=20260929i   TOC域=7   PPT清洗=5   mode传参=2
ellipsis = 0   虚构人名 = 0   模拟字样 = 0
Codex 未提交 WIP 保留 10 项（没有被我覆盖）
```

---

## 六、没能闭环的（如实）

1. **235-4 / 235-5 未做**：PPT 两版（正文版 17 页默认 + 讲解稿完整版 36 页）、PPT 插入图表。
   这两项改动面大（牵扯 deck 结构与图表管线），本轮没动。
2. **234-2 / 234-4 留给 Codex**：`app.py` 阈值注释统一、自评分与导出分口径统一。
3. **PPT 清洗用的是离线构造验证**，不是真实深度版生成链路（本机与服务器都跑不通真实 LLM 生成），
   实测证明的是「清洗逻辑对这类脏数据有效」，不等于线上那一份 36 页 PPT 已康复。
4. 公网真机观感仍需肉眼复核（本机访问不了 kechuang2026.cn）。

---

## 七、本轮新增的经验（已写进技能 §29/§30 与 backend-content §5）

- 部署漏文件 = 生产崩；必须**按完整变更清单** + **重启前干跑 import**。
- 服务器真环境：`python3` 没 docx/pptx，用 `.venv/bin/python`；测试脚本 `sys.path.insert`
  顺序决定加载新版还是旧版（后插的在前）。
- 测导出口必须先 `GET /` 拿签名 cookie `comp_uid`，否则全是 401 假失败。
- 两道导出门 code 不同（`quality_fail` 带 reasons / `export_quality_fail` 只带 error）。
