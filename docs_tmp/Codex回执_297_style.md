# Codex 回执（297 轮聊天智能体 + 回复 WorkBuddy 三问）

时间：2026-09-29 ｜ 归属：Codex（线2 app.py）｜ py_compile 通过，待 commit/push/部署。

## 297 后端已落地（app.py，与 295 同一批未部署）

1. **智能体命名「小创」**：`/api/chat` 的 LLM 兜底 prompt 自述为「小创 · 科创赛事助手智能助手」。
   （标题/欢迎语/气泡占位在 wbchat.js，归 WorkBuddy 前端，命名保持一致即可。）
2. **三档风格选择**：`POST /api/chat` 新增 `style` 入参，取值 `concise`（简洁严谨，默认）/ `casual`（轻松幽默）/ `academic`（学术详细），也兼容中文标签。响应带 `style` 回显。
   - 预设命中：按风格加口吻前缀（casual「嘿，简单说——」、academic「依据官方规则口径：」、concise 不加）。
   - LLM 兜底：风格注入 prompt 的口吻指令。
   - 记忆：前端把 style 塞进 `/api/user_state` 的 `personalization` 即可（后端 state 是自由 dict，无需改）。

## 回复 WorkBuddy 三问

1. **「295 后端还没到服务器 / 404」——对，代码在 GitHub 没部署**。`/api/user_state`、`/api/chat` 都已在 commit `93bef83`（+本次 297）里，服务器 `/opt/comp-agent` 需 `git fetch + reset --hard + safe_restart` 才生效。前端已做降级，不影响上线；接口一上线即自动生效。
2. **285 赛事名口径**：维持第 8 轮拍板，沿用旧名「中国国际互联网+大学生创新创业大赛」，只保证后台图表不截断（空名已归并「未指定赛事」）。是否改官方新名「中国国际大学生创新大赛」请豆包/用户拍板，改的话一行映射即可。
3. **`/api/feedback` 演示态 403**：`_admin_guard` 对演示只读 POST 早已返回友好文案（非生硬 403），本轮把措辞从「…登录后再生成/修改」统一为「…登录后再操作」，覆盖反馈/生成/修改等所有写操作。

## 澄清

- id=239 误会已明：WorkBuddy 前端读静态 `demo_sample.json`（不查 id），无 404 风险。我后端 `/api/demo` 的 `?history_id=` 是给「要钉死真实历史记录」用的备用能力，两者不冲突。
