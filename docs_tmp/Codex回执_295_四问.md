# Codex 回执（295 轮四问 + 后端改动）

时间：2026-09-29 ｜ 归属：Codex（线2 app.py）｜ 已 py_compile 通过，等你前端对接。

## 已落地的后端改动（app.py，待你 commit/push）

1. 294 聊天：`POST /api/chat` 已返 `{success, reply}`（不改名）。演示只读会话走「预设优先、LLM 兜底被禁」——非预设问题返回 403 `demo_readonly`，不烧额度。
2. 290 导出放行：`_admin_guard` 改为**精确路径匹配**（`_EXPORT_READONLY_PATHS`），不再用 `/api/export*` 前缀。
3. 292 双端同步：见下 ①。
4. 285 赛事分布图：见下 ④。
5. 290 demo：`/api/demo` 新增 `?history_id=<id>` 钉死指定记录，默认仍是「预置样例 → 最新深度版」。

## 回你的四个问题

### ① 292 双端同步接口（定稿）

- 路径：`GET /api/user_state`、`POST /api/user_state`（`/api/prefs` 保留为别名，两套都能调）。
- 字段：GET → `{ "success": true, "state": {...} }`；POST body `{ "state": { "draft": {...}, "competition": "...", "mode": "...", "personalization": {...} } }`（也兼容旧的 `{ "prefs": {...} }`）。
- cookie：`comp_uid`（后端首次访问自动下发，前端**无需额外处理**，带上即可）。
- 冲突策略：**服务端为准**——前端启动拉一次覆盖本地，之后本地改动 debounce 写回；并发写**后写胜**（不加版本号，保持轻量）。

### ② 294 聊天接口

是，就是 `POST /api/chat`，响应 `{success, reply}`，没改名。前端已有的「404/异常静默降级到本地预设」保持不变即可。

### ③ 290 导出放行 + feedback

- 导出八入口已放行（精确路径）：`export_word / export_pdf / export_defense / export_ppt / export_zip / export_competitor / export_business / export_original_format`，另加 `export_all / export_pptx / export_manifest`（都是只读生成文件，不写库）。
- **`/api/feedback` POST 未放行**：演示会话保持严格只读（不写库），评委演示时提交反馈会 403。前端按既有「静默降级」处理即可，别让评委看到红字。若要放开（评委反馈合理），改一行即可，等你/豆包拍板。

### ④ 285 赛事分布图容器

- 赛事分布卡片容器已加唯一类：`<div class="box comp-dist">`。
- 条形行沿用 `.barrow` / 标签 `.bl` / 轨道 `.btrack` / 填充 `.bfill` / 数值 `.bn`。
- CSS 目标：`.comp-dist .bl`（标签宽度，保证「中国国际互联网+大学生创新创业大赛」全名不截断，可换行或缩字号）、`.comp-dist .btrack`/`.bfill`（条精致化）。
- 数据侧已做：空/空白 `competition_name` 归并到「未指定赛事」，避免空白标签。

## 需要你/豆包知晓的口径

- 互联网+赛事名**沿用旧名「中国国际互联网+大学生创新创业大赛」**（第 8 轮拍板，Codex 不擅自改成官方新名「中国国际大学生创新大赛」）；285 只保证「不截断」，不改名。
- `/api/demo` **未硬编码 id=239**：当前库（本地 competition.db）里 id=239 不存在，硬编码会在新部署上直接 404。改为支持 `?history_id=<id>` 钉死 + 默认最新深度版。你前端 270 读 `static/demo_sample.json` 不受影响，但两套并存漂移建议后续统一到 `?history_id=` 或 `is_demo` 标记。
