# 交接（WorkBuddy）：我接手改了手机端 10 个适配细节

> 基于你最新提交（769882a）之上改，只动 CSS + 少量 JS/HTML，JS 语法 0 报错。
> 前 4 个是上轮做的（未单独提交，合并在这里），后 6 个是本轮新加的。

## 一、前 4 个（上轮）

1. 赛事快捷 chip 横向可滑 + 藏滚动条。
2. `.card` 手机上 `overflow:visible`（避免折叠板块展开被裁），`.card::after` 装饰光晕隐藏。
3. `#wbFab` 抬高到 `calc(72px + env(safe-area-inset-bottom))`。
4. 压缩 body/hero/card/form 留白。

## 二、后 6 个（本轮）

5. **顶部引导卡被微信导航栏挡**：meta 加了 `viewport-fit=cover`；检测到微信/QQ 时给 `body` 加 `in-app` 类，`body.in-app { padding-top: 44px }`。同时 `body` 顶部用 `max(8px, env(safe-area-inset-top))`。

6. **底部提示文字被悬浮导出按钮挡**：`body` 底部 padding 加到 `150px`，给 FAB 让位。

7. **「清空重写」按钮太小**：`#wbRestoreTip button` 手机上加到 `padding:10px 16px; font-size:14px`。

8. **项目创意输入框太矮**：`#idea` 手机上加到 `min-height:150px !important`。

9. **微信引导没箭头**：在「点右上角 ···」旁加了 `.wb-point-arrow`（↗ 上跳动画）。

10. **选中比赛不明显**：`wbSyncCompChips()` 给选中的 chip 加 `data-on="1"` 并配一圈高亮（`#compQuickRow > span[data-on="1"]`）；输入框命中官方知识库时加 `wb-matched` 类描边。

## 你后续注意

- 我改了 `wbSyncCompChips()`（加 `data-on` + 输入框 `wb-matched` 描边），和之前你可能的改动在同一函数里，注意别覆盖。
- 搜索「Codex 接手」能定位到我加的 CSS 块。

