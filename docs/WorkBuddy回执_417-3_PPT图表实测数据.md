# WorkBuddy 回执 · 417-3 PPT 图表用实测数据（已定位真缺口 + 改法）

- 时间：2026-09-30 05:5x (GMT+8)
- 调查人：WorkBuddy
- **结论：417-3 是唯一真实缺口。根因 = 用户实测数据未喂进图表生成提示词。修复路径确定，但 LLM 是否真用需真实生成验证。**

## 证据链
1. 前端有完整「实测数据」录入区：`app.js:4144-4171` 字段 udSite(试点单位)/udScale(样本量)/udMetric(实测指标)/udCost(成本)/udExtra(佐证)，并可上传文件「合并进实测数据」。
2. 后端收到：`app.py:3750` `_raw_user_data = data.get("user_data","") or data.get("real_data","")`；`:3752-3753` 长文本走 `_smart_extract_user_data` 提炼；`:3763` 写入生成 state。
3. **缺口**：`rich_pipeline._gen_assets`（图表生成）的 `material`（rich_pipeline.py:120-129）只喂了 idea/one_liner/各 proposal 章节 + `kb_data`（行业数据），**完全没包含 `user_data` 实测数据**。→ 图表 LLM 拿不到用户填的试点准确率/成本/时间线，只能从 proposal 正文或行业数据里找，dispatch 投诉成立。

## 推荐改法（确定性，可本地验证接线）
- 在 `build_rich_assets` 调用处（`app.py:3807`）把 `user_data` 透传进来；
- `_gen_assets(result, competition, idea, kb_data, user_data="")` 把 `user_data` 追加进 `material`，并在提示词「数字必须来自材料」处加一条：**优先采用「团队输入(实测数据)」字段里的数字，作为图表首选来源，并在 source 标「团队输入」**；
- 同理可让 proposal 各章节在生成时就吸收实测数据（若该通道还没接）。
- 这样即便 LLM 不完美，也把真实数据摆到它眼前，契合 dispatch「用户填了实测数据→图表按实测渲染」。

## 验证与部署
- 确定性部分可验：改完确认 `user_data` 字符串出现在发给 LLM 的 prompt 里（本地 venv 打印 material 即可）。
- **LLM 实际采纳率需真实生成才能确认**（依赖线上 DeepSeek API，离线无法验证）→ 属于"跑不出来就如实说没验证"项。
- 改动文件：`rich_pipeline.py`（material）+ `app.py`（透传）→ 必须 `systemctl restart comp-agent`。
- `rich_pipeline.py` mtime 09-29 18:19（早于 04:46 重启），当前线上无滞后；改后需重启生效。

## 417 整轮状态汇总
- 417-1（Word 封面+目录）：**已完成**（234/235 轮，实测验证）。
- 417-2（PPT 页数对齐大纲）：**已完成**（170/235 轮 `_outline_deck` 1:1 + competition_agents:2667 大纲「与 PPT 页数一致」，真实样本实测大纲11↔PPT11）。
- 417-3（PPT 图表实测数据）：**未做 = 真缺口**（见上）。
- 417-4（PDF 页数/体积校验）：**已完成**（125 轮 `_pdf_limits` + quality_gate.check_pdf，含删减建议，接 export_pdf 超限制 422）。
