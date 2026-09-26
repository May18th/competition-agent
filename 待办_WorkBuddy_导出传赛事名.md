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

## 更新：后端已提供统一结构化配置（建议前端改成读接口，避免两处硬编码）

后端新增 `data/competition_profiles.json`，15 个比赛的章节顺序 / 评分重点 / 比赛类型 / 提示词侧重 / 字数要求都在这一份里，并暴露接口：

```
GET /api/competition_profiles
```

返回 `{ success: true, competitions: [...] }`，每个比赛包含：

- `name` / `aliases`：赛事名与别名，用于匹配
- `chapters`：官方章节顺序（导出 Word/PDF 时后端会按这个自动排序）
- `scoring`：重点评分项
- `focus`：生成 Prompt 的赛事侧重（iCAN 重创新、互联网+ 重落地、大挑 重社会价值等）
- `defense_focus`：答辩问题类型（engineering / business / modeling / academic）
- `word_requirement`：`official` 只写官方明确给过的字数上限，`suggested` 是系统内写作档位，不是官方口径
- `double_blind`：true 表示封面隐藏学校/导师（如 iCAN）

建议前端在赛事卡片、章节编辑器里优先读这个接口，失败再回退到现有 `EVENT_REQ`，这样以后改配置只改 JSON 一处，不用前端后端各改一遍。
