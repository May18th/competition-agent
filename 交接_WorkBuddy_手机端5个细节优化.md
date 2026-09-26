# 交接（WorkBuddy）：我接手加了 5 个手机端细节优化

> 基于你已推送的 10 个适配之上改，只动 CSS/HTML/少量 JS，JS 语法 0 报错。

## 改了什么

1. **回到顶部按钮**：新增 `#wbTop`（右下角 ↑，`bottom:150px`，在导出 FAB 上方），下滑超 800px 才显示，点击平滑回顶。带 `scroll` 监听切换显隐。

2. **首屏骨架屏**：新增 `#pageSkeleton` 固定遮罩（几块灰条），`load` 或最迟 2.5s 后淡出移除，避免白屏。

3. **虚拟键盘遮挡**：全局 `focusin` 监听，INPUT/TEXTAREA/SELECT 聚焦后延迟 320ms `scrollIntoView({block:'center'})`，把输入框顶进视口。

4. **切后台回来不断**：生成轮询的看门狗改成「前台累计时长」——页面隐藏时记 `_hiddenAt`，回前台把隐藏时长补回 `t0`，避免后台 5 分钟被误判超时。断了仍可点重试（已有 `/api/retry`）。

5. **导出提示**：主导出（Word/PDF/打包/PPT）原本已有 Toast；补了 `.txt` 的 `exportSection` 漏掉的「已开始下载」提示。

## 你后续注意

- 我加了一个新的 `<script>` 块（在 `</body>` 前），搜「手机端 5 个细节优化」能定位。
- 生成流程里 `const t0` 改成了 `let t0` 并加了个 `visibilitychange` 监听，别覆盖掉。

