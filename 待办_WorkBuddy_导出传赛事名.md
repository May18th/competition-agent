# 待办 · WorkBuddy：导出请求补充 competition_name

## 背景

后端已完成「导出时按官方章节自动排序」和「iCAN 双盲不出现学校/指导老师」两件事，但需要前端把 `competition_name` 随导出请求一起传过来，否则后端不知道当前是哪个赛事，无法生效。

## 要改的两处（都在 index.html，请保持其它逻辑不动）

### 1. `/api/export_word`

`exportOne()` 里 body 目前是：

```js
body: JSON.stringify({title: name, text: text,
    doc_type: _DOC_TYPE[id] || 'report',
    school: m.school, team: m.team, advisor: m.advisor})
```

请补上 `competition_name`：

```js
body: JSON.stringify({title: name, text: text,
    doc_type: _DOC_TYPE[id] || 'report',
    competition_name: (document.getElementById('competition') || {}).value || '',
    school: m.school, team: m.team, advisor: m.advisor})
```

### 2. `/api/export_pdf`

`exportOnePDF()` 里 body 目前是：

```js
body: JSON.stringify({title: name, text: text})
```

请补上：

```js
body: JSON.stringify({title: name, text: text,
    competition_name: (document.getElementById('competition') || {}).value || ''})
```

## 后端已就绪的行为（改完前端后即可生效，无需再动后端）

- 传了 `competition_name`：导出 Word/PDF 会按知识库里该赛事的「申报书章节」官方顺序重排标题块。
- 赛事名含 `iCAN`：Word 封面自动隐藏学校、单位、指导老师，只保留团队（学生）信息，符合 iCAN 创新赛道双盲要求。

## 顺带发现（可做可不做，做了更稳）

`EVENT_REQ` 里 iCAN 的 `scoring` 目前是 `[创新性30, 实用性25, 技术难度20, 团队展示15, 社会价值10]`，和知识库里 iCAN AI 应用挑战赛官方口径 `创新性30/技术实现30/实用价值20/用户体验10/展示效果10` 不一致。若评委看到权重串了会扣印象分，建议同步成官方口径。
