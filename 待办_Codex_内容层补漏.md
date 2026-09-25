# 内容层补漏（负责人：Codex）—— T7 只完成了一部分

> 验收时间：2026-09-25 23:20 ｜ 验收人：WorkBuddy
> 验收方式：**真跑一次生成**（fast 模式，64 秒跑完 9 个阶段），对产物做量化统计，不是看代码猜的。

---

## 一、实测数据（task_id `c4f3ca66`）

| 产物 | 字数 | 二级标题 | 三级标题 | 平均段长 | 短段(<60字) | 序号行 | 判定 |
|---|---|---|---|---|---|---|---|
| **proposal 申报书** | 1661 | 6 | 5 | **186 字** | 0 | **0** | ✅ **达标** |
| parsed_rules 赛事规则解析 | 1789 | 4 | 5 | 35 字 | 14 | **15** | ❌ 清单体 |
| similarity_report 同质化检测 | 2193 | 6 | 4 | 31 字 | 8 | 6 | ❌ 清单体 |
| judge_feedback 评委意见 | 648 | 0 | 0 | 14 字 | 2 | 2 | ❌ 极短 |
| proposal_analysis 诊断分析 | 378 | 0 | 0 | 94 字 | 0 | 4 | ❌ 偏薄 |

用户的要求是「**严禁几句话就写完，要写大段完整文字**」「**不要序号形式的**」。
目前只有**申报书本体**达标，其余四项仍是短句 + 序号清单，用户一眼就能看出来。

---

## 二、根因：四份规格只注入了 10 处，覆盖了 7 个 Agent

你在 `competition_agents.py` 定义了 `_REPORT_SPEC` / `_ANALYSIS_SPEC` / `_OUTLINE_SPEC` / `_OPTIMIZE_SPEC`，
**定义得很好，而且确实都用上了（不是孤儿常量）**——但覆盖面不够：

| 已注入 | 未注入（就是上表 ❌ 的那几个） |
|---|---|
| `comprehensive_analysis`(486) | **`rule_parser`(396)** → parsed_rules |
| `deep_competitor`(526) | **`similarity_checker`(437)** → similarity_report |
| `deep_business`(549) | **`judge`(852)** → judge_feedback |
| `deep_risk`(572) | **`proposal_analysis`(997)** → proposal_analysis |
| `deep_tech`(595) | `plan`(603) / `social_value`(624) / `summary`(645) |
| `deep_writer`(675/718) | `defense_questions`(912) |
| `proposal_writer`(732/769) | `speech`(946) |
| `ppt_outline`(938) | |

---

## 三、要做的事（按这个改即可）

### 必做 4 处（用户能直接感知的）

| 函数 | 行号 | 注入 | 理由 |
|---|---|---|---|
| `rule_parser_agent` | 396 | `_REPORT_SPEC` | 赛事规则解析是**报告**，现在 15 行序号、平均 35 字 |
| `similarity_checker_agent` | 437 | `_REPORT_SPEC` | 同质化检测是**报告**，现在平均 31 字 |
| `judge_agent` | 852 | `_ANALYSIS_SPEC` | 评委意见是**分析类**，现在全文 648 字、只有 2 段、平均 14 字 |
| `proposal_analysis_agent` | 997 | `_ANALYSIS_SPEC` | 诊断分析是**分析类**，现在只有 378 字 |

注入方式和你已经做的一样，在 prompt 末尾拼上即可，例如：

```python
prompt = f"""...
{_REPORT_SPEC}
"""
```

### 建议做 3 处（深度版会用到）

`plan_agent`(603) / `social_value_agent`(624) / `summary_agent`(645) → 加 `_REPORT_SPEC`。
这三个的产物会喂给 `deep_writer`，源头是短句的话，申报书也会被拖薄。

### 明确不用改 2 处

- `defense_questions_agent`(912)：答辩**问答对**，天然就是一条条，不该写成大段。
- `speech_agent`(946)：**演讲稿**是口语稿，不适合书面段落体。

### ⚠️ 两个需要注意的点

1. **`judge_agent` 的输出要能被程序解析**。它有结构化打分（分数、优缺点条目）要落库，
   别把规格加在**结构化字段**上——只约束它的**文字点评部分**写成段落，分数/标签保持原格式。
   建议：规格里补一句「结构化字段（分数、优缺点条目）保持原格式，仅点评文字写成完整段落」。
2. **别为了凑字数注水**。用户要的是「有论点、有展开、有依据」，不是废话。
   `_REPORT_SPEC` 里已经写了 150~400 字，保持即可。

---

## 四、验收标准

改完请**自己真跑一次**，用下面的口径核对（别只看输出不统计）：

```bash
python -c "
import json,re,urllib.request,time
# 提交 /api/generate_async → 轮询 /api/status/<task_id> → 统计各字段
"
```

期望：

- [ ] `parsed_rules` / `similarity_report` 平均段长 **≥ 80 字**，序号行 **≤ 3**
- [ ] `judge_feedback` **≥ 800 字**，段落数 **≥ 4**，平均段长 **≥ 60 字**
- [ ] `proposal_analysis` **≥ 600 字**
- [ ] `proposal` 保持现状（186 字段落、序号 0）**不要退化**
- [ ] 打分、优缺点等结构化字段**仍能正常解析**（不能因为改 prompt 把 JSON/结构弄坏）

我已经把验收脚本留在项目里：`_verify_codex_docx.py`（验格式，22 项断言，不消耗额度）。
内容层的统计口径就是上表那几列（字数 / 平均段长 / 短段数 / 序号行数），建议你也固化成脚本，改完跑一遍就有数。
