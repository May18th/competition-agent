# 进度条 stage 约定（Codex 后端 → WorkBuddy 前端）

> 更新时间：2026-09-25
> 目的：后端已在每个 Agent 节点入口上报真实阶段，前端可以把现在的「假进度条」换成「真实进度条」。
> 本文档只约定接口与 stage 名，不改 `index.html`（前端仍由 WorkBuddy / 豆包负责）。

## 一、现状与问题

- 前端现在用的是 `POST /api/generate`（**同步接口**，要等全部生成完才返回）。
- 进度条是纯前端假动画：`setInterval` 每 500ms `progress += 5`，和真实进度无关，所以深度版跑 1~2 分钟时，进度条会停在 95% 很久。
- 深度版的 step1~step6 是静态 HTML，没有根据实际进度高亮。

## 二、后端已经做了什么

后端在 `competition_agents.py` 的每个 Agent 节点入口调用了 `_report_stage(stage)`，会实时更新当前任务阶段。
前端通过轮询 `GET /api/status/<task_id>` 就能拿到这个 `stage` 字段。

> 实现细节：任务状态与阶段上报已下沉到零依赖独立模块 `stage_reporter.py`，`app.py` 和
> `competition_agents.py` 都只依赖它，避免「competition_agents 反向 import app」造成的循环导入。
> 前端无需关心这个文件，只要按本文档读 `stage` 字段即可。

## 三、接口

### 1. 异步发起（替代原来的同步 `/api/generate`）

```
POST /api/generate_async
Content-Type: application/json
```

请求体**和原来的 `/api/generate` 完全一样**（competition_name / idea / proposal_draft / mode / iterate / theme）。

返回：
```json
{ "success": true, "task_id": "36b2144c318d46c29b668e4da27a0e0d" }
```

### 2. 轮询状态

```
GET /api/status/<task_id>
```

返回：
```json
{
  "success": true,
  "status": "running",      // running | done | error
  "stage": "writing",       // 见下方 stage 表
  "updated_at": 1790327925
}
```

- `status = done` 时，响应里会多一个 `data` 字段，就是原来的完整结果（score / proposal / rich_deck / ...）。
- `status = error` 时，响应里会有 `error` 和 `detail`。

## 四、stage 名约定（完整列表）

| stage | 含义 | 简洁版 | 深度版 |
|---|---|:---:|:---:|
| `parsing_rules` | 规则解析 | ✅ | ✅ |
| `similarity` | 同质化检测 | ✅ | ✅ |
| `idea_scoring` | 创意评估 + 一句话定位 | ✅ | ✅ |
| `analysis` | 综合分析（竞品/商业/风险/技术/计划/社会价值/摘要） | ✅ | ✅ |
| `writing` | 申报书撰写 | ✅ | ✅ |
| `judging` | 模拟评委打分 | ✅ | ✅ |
| `diagnosis` | 申报书诊断分析 | ✅ | ✅ |
| `revision` | 定向修订（低分迭代时才会出现） | 仅开 iterate | 仅低分时 |
| `defense` | 答辩问题预测 | ✅ | ✅ |
| `ppt` | PPT 大纲 | ✅ | ✅ |
| `speech` | 路演演讲稿 | ✅ | ✅ |
| `rich_assets` | 富媒体（图表/表格/PPT 结构） | ❌ | ✅ |
| `done` | 全部完成 | ✅ | ✅ |

## 五、前端改造建议（映射到现有 6 步）

现有 step1~step6 可以这样映射（其他 stage 归入相邻步骤即可）：

| 现有步骤 | 对应 stage | 建议显示 |
|---|---|---|
| step1 规则解析 | `parsing_rules` | 规则解析中 |
| step2 同质化检测 | `similarity` + `idea_scoring` | 同质化检测 / 创意评估中 |
| step3 申报书生成 | `analysis` + `writing` | 综合分析与申报书撰写中 |
| step4 模拟评委 | `judging` + `diagnosis` + `revision` | 评委打分 / 诊断 / 修订中 |
| step5 答辩问题 | `defense` | 答辩问题预测中 |
| step6 PPT 大纲 | `ppt` + `speech` + `rich_assets` | PPT 大纲 / 演讲稿 / 富媒体生成中 |

简洁版可以继续用百分比进度条，但建议把百分比和 `stage` 挂钩，而不是纯前端假动画。

## 六、注意事项（务必读）

1. **stage 只在异步接口下有真实值**：`/api/generate`（同步）不会把中间 stage 透出给前端，只有 `/api/generate_async` + 轮询 `/api/status` 才能拿到。
2. **开头几个节点是并行跑的**：`parsing_rules / similarity / idea_scoring / analysis` 会乱序快速跳变，最后停在最后完成的那个。这是正常的，前端以「最新 stage」为准即可，不要要求严格递增。
3. **`revision` 只在低分迭代时出现**，`rich_assets` 只在深度版出现，前端不要写死一定会经过这两个。
4. **失败兜底**：`status = error` 时要停掉轮询并显示 `error`，不要一直转圈。
5. 后端改完需要**重启 Flask**（`run.py` 是 `debug=False`，不会热重载）。

## 七、验证方式

后端已真跑验证过：`POST /api/generate_async` → 轮询 `/api/status`，约 40 秒跑通简洁版，`stage` 能正常走到 `done`，`data` 里字段齐全。
