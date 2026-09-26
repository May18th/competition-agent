# 交接（WorkBuddy）：首页精简第 2 轮

> 只动 HTML 文字/结构，删了新手引导三步卡片，JS 语法 0 报错。

## 改了什么

1. 「已恢复上次填写内容」提示改成一行小字（去掉大框/背景/边框）。
2. 知识库说明改成 `已内置 15 个比赛评分标准`。
3. 比赛快捷按钮只留 5 个常用：iCAN / 互联网+ / 大挑 / 小挑 / 数模，其余进下拉框。
4. 删掉 Hero 副标题、新手引导三步卡片（`#wbGuide` / `#wbGuideBar` / `.wb-guide-hint`）。

现在首页就是：标题 → 选比赛 → 输创意 → 点生成，干净。

## 你后续注意

- 我删了 `#wbGuide` 三步引导卡片，但 JS 里的 `wbGuideInit/wbGuideGo/wbGuideExpand/coachStart` 还留着（都有 null 判断，不会崩）。如果你要彻底清理这些 JS，可以再删，不影响功能。
- 快捷 chip 现在 5 个，其余赛事都在 `#competitionList` datalist 下拉里。

