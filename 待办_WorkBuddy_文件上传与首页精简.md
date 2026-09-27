# 待办 · WorkBuddy：文件智能识别 + 首页精简（后端已就绪）

> 后端 Codex 已完成，以下 5 项都是前端 index.html 的活，按优先级排。

---

## P0-1 实测数据区加「上传文件」+ 智能识别路由

后端 `/api/upload_file` 已支持 pdf/docx/txt/md/csv/xlsx/xlsm，并在解析后返回：

```json
{"success": true, "text": "原文", "file_type": "赛事规则|申报书草稿|实测数据|参考文献|其他", "summary": "一句话", "key_points": ["关键点"]}
```

前端要做：

1. 实测数据采集区加「上传数据文件」按钮，`accept=".pdf,.docx,.txt,.md,.csv,.xlsx,.xlsm"`，POST `/api/upload_file`。
2. 上传后展示识别结果：「已识别为【实测数据】：测试报告含取件耗时、错拿率等指标」，让用户确认。
3. 按 `file_type` 路由：
   - `实测数据` → 合并进 `user_data`
   - `申报书草稿` → 填 `proposal_draft`
   - `赛事规则` → 提示「规则已内置，无需上传」或填 `rule_content`
   - `参考文献/其他` → 合并进 `user_data` 的「其它佐证」
4. 拒绝 `.doc`（提示另存 docx）和图片（提示导出 PDF）。
5. 失败弹后端 `error`，别静默。

## P0-2 删掉/降级「上传赛事规则」入口

15 个赛事规则已内置知识库，用户选了比赛就自动匹配评分标准，**没必要再让用户传规则**。

- 删掉首页醒目的「上传规则」入口，或降级成折叠的「补充规则（可选）」小字链接，默认收起。
- 主打流程变成：**选比赛 → 输创意 →（选填）填实测数据 → 点生成**，规则那一步去掉。

## P1-3 手机端底部标签栏挤压

底部赛事标签栏在手机端有挤压，改成横向可滑动 + 标签不换行截断，别让后面的比赛选项被裁掉。

## P1-4 今日额度展示

后端 `/api/quota` 已就绪（返回 calls/limit/remaining/date/exceeded）。前端在合适位置（如顶部或生成按钮旁）显示「今日剩余额度 X 次」，超限时给提示。

## P1-5 简洁版「低分自动补写」开关

后端已把简洁版 `iterate` 接好：默认 `false`（不迭代，保持快速），传 `true` 才低分返工。前端在简洁版选项旁加一个「低分自动补写（会多花一轮时间）」开关，勾选时 `iterate: true`。

---

## 后端接口速查

- `POST /api/upload_file`（form-data `file`）→ 返回 `text / file_type / summary / key_points`
- `GET /api/quota` → 返回今日额度
- `POST /api/generate_async` 的 `user_data` 字段（字符串，兼容旧名 `real_data`）
- 简洁版 `iterate` 字段（bool）
