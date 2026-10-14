# 交接（WorkBuddy）：我接手加了「赛事 quick-pick chip 自动高亮」

> 用户授权我继续协助前端。本轮基于你已上线的 d51df2e 之上改，diff 干净（+20/-1），没有动你的其它逻辑。

## 改了什么

**赛事名称下方的横排快捷 chip（iCAN / 互联网+ / 大挑 / 小挑 …）现在会「自动高亮」当前选中的那个**：

1. 给那一排容器加了 `id="compQuickRow"`。
2. 新增 `wbSyncCompChips()`：读取 `#competition` 当前值，遍历 `compQuickRow` 的子元素，从每个 chip 的 `onclick="wbPickComp('xxx')"` 里解析出赛事名，命中就把该 chip 设成主色背景+白字+加粗，其余保持灰色。
3. `onCompetitionChange()` 里第一行调用 `wbSyncCompChips()`，所以输入、点 chip、自动识别赛事、清空、初始加载，都会同步刷新高亮。

## 赛道高亮

赛道 chip（`evTrackChips`）你之前就已经做了「选中高亮」（主色背景+白字），我没动，保持原样。

## 你无需做什么

- 如果你之后要改这排 chip 的样式，注意 `wbSyncCompChips()` 是直接覆盖 `background/color/borderColor/fontWeight` 四个内联样式的；要改默认色就在这个函数里一起改。

