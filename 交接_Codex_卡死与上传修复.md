# 交接 Codex：卡死事故复盘 + 上传修复 + 后端待改清单

> 2026-09-25 19:15 · WorkBuddy 写
> 背景：用户桌面端 + 手机端都出现「进度条卡在 AI正在优化: 15% 不动」+「上传申报书草稿失败」。

---

## 一、事故根因（两个独立问题叠加）

### 1. 进度条卡死 —— 元凶是浏览器缓存了旧版前端
- 卡住的截图里文案是 `AI正在优化: 15%`（老版假进度格式）。
  **新版**真实进度格式是 `AI正在优化：检索同质化项目（已用 45s）`（stage_label + 秒数），
  说明用户浏览器里跑的是**旧 JS**。
- 期间后端重启过（17:56 / 18:36 两次），旧页面的生成请求被掐断，
  旧代码把错误**静默吞掉** → 进度条永远停在一半。
- 临时解法：**硬刷新（Ctrl+F5）**。手机端关掉标签页重开。
- 根治方案见下面 B-1（`/` 路由加 no-store），**这条最关键**。

### 2. 上传失败 —— `secure_filename` 吃掉中文字符（我已修，见 A-1）
- 纯中文文件名《申报书草稿.pdf》经 `secure_filename()` 变成 `"pdf"`，
  `endswith('.pdf')` 判定失败 → 返回「不支持的文件格式」→ 前端显示「上传失败」。
- uploads/ 里那个叫 `pdf` 的孤儿文件就是现场证据（已清理）。

---

## 二、A. WorkBuddy 已改完并验证（Codex 勿回退）

### A-1 `app.py` → `/api/upload_pdf`（重写）
- 扩展名先取（`os.path.splitext`）→ 白名单校验 `.pdf/.docx/.txt` →
  主体名 `secure_filename` 兜底 + 时间戳重命名防重名 → 解析包 try/except →
  空文本时返回「扫描版/图片型 PDF 提取不了」友好提示。
- 真机验证 3 例全 PASS：纯中文 txt ✓ / 纯中文 docx ✓ / .md 友好拒绝 ✓。

### A-2 `index.html`
- 上传失败显示具体原因 + wbToast 弹窗；成功提示改用 innerHTML
  （原来 innerText 会把 SVG 图标当文字显示）。
- 生成失败/取消后把 `fastProgress` 清零（原来残留旧百分比）。
- 轮询超 120 秒追加「较慢可点终止生成」提示。

---

## 三、B. 需要 Codex 改（后端 app.py，按优先级）

### B-1 ★ `/` 路由加 no-store（防缓存，本次事故根治）
```python
@app.route('/')
def index():
    resp = make_response(open('index.html', encoding='utf-8').read())
    resp.headers['Cache-Control'] = 'no-store, must-revalidate'
    return resp
```

### B-2 旧同步接口 `/api/generate`（565 行）建议下线
旧版前端会调它；服务重启时请求被掐断就静默失败（本次卡死的帮凶）。
若暂时保留，请标注 deprecated。

### B-3 `/api/upload_file`（738 行）图片分支引用不存在的 `claude_llm`
competition_agents.py 里 `claude_llm` 是注释掉的 → jpg/png 上传必 ImportError。
要么接真多模态模型，要么先返回「暂不支持图片」明确提示。
另：它读的是 `request.files['file']` 直取（无 'file' in request.files 判断），顺手补个兜底。

### B-4 `app.py` 末尾 `app.run(debug=True)` → 改 False
debug=True 的 reloader 会派生双进程抢 8080（本机踩过：netstat 两行 LISTENING）。
run.py 里已经是 False，别让这个入口把坑带回来。

### B-5 任务心跳/兜底超时
worker 若在非 LLM 环节卡死（文件 IO 等），status 永远 running，前端只能干等。
建议：`/api/status` 对 running 且 `updated_at` 超过 10 分钟的任务直接返回
error「任务超时，请重试」。可选：加 `/api/tasks` 调试端点列出运行中任务
（今天排查时没有这个能力，只能靠猜）。

### B-6 取消的即时性说明
cancel 只在下一个 report_stage 才抛 TaskCancelled；若正卡在一次 60s 的
LLM 调用里，点终止后最多还要等 60s。行为可接受，建议 `/api/cancel`
响应里带一句文案（如 `eta_note: "最迟约 1 分钟内停止"`），前端拿去 toast。

### B-7 任务状态写入路径统一
worker 的 except 分支直接 `tasks[task_id] = {...}`（整字典覆盖），
而正常完成走 `progress.mark_done` —— 两条写路径容易把字段写丢。
建议错误路径也走 progress / stage_reporter 的封装，保持单一真相源。

---

## 四、C. 挂起待决（沿用之前约定，不动）
- `progress.write_live`（live 快照）
- `progress.resolve_workers`（并发数）
等深度版并行真走 ThreadPoolExecutor 时再接。

---

## 五、当前服务状态（19:15）
- 单进程 PID 40748 监听 8080，`/api/health` ok，uptime 正常。
- quota 71/500，最近 3 次生成（history 24→27）都成功，链路本身通畅。
- 未提交改动：`app.py`（上传修复 + 取消链路收尾）、`index.html`（上传/进度条体验）、本文件。
