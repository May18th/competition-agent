# 待办（WorkBuddy）：知识库面板显示「0/0 收录」—— 前端选择器 bug

## 现象
首页知识库面板显示「0/0 赛事已收录资料」，选中 iCAN 时显示「未匹配内置知识库，0/0 收录」。

## 根因（前端，不是后端）
`index.html` 的 `_kbHitList()`（约 3147-3154 行）：

```js
var sel = document.querySelectorAll('#competition option');
```

但 `#competition` 现在是 `<input type="text" list="competitionList">`（约 1160 行），
`option` 在 `<datalist id="competitionList">` 里，不在 input 内部。
所以 `#competition option` 永远返回空数组 → `list.length=0` → 覆盖率显示「0/0」。

## 修法（一行）
把选择器从 `#competition option` 改成 `#competitionList option`：

```js
var sel = document.querySelectorAll('#competitionList option');
```

## 顺带建议（不阻塞）
`_kbMatch()`（约 3143-3145 行）目前只做「互为子串」，会漏掉别名命中：

- 国创：文件 `国创.txt` vs 选项「国家级大学生创新创业训练计划」→ 子串不命中（后端靠别名表命中）。
- 大小写：`ican` vs 文件 `iCAN.txt` 也不命中。

建议要么 `toLowerCase()` 后比较，要么优先用后端 `/api/knowledge_status` 或未来动态索引的 matched 结果。

## 后端结论（已验证）
后端 `get_competition_knowledge_structured('iCAN大学生创新创业大赛')` 已正确命中 `iCAN.txt`，
评分标准也正确注入（AI 应用挑战赛 30/30/20/10/10）。所以生成其实在用 iCAN 的评分标准，
只是前端面板误报「未匹配」。
