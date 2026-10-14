> Codex 接手前请先读 `交接_Codex_文档内容与导出接线.md`（分工与约定），
> 再读本文件。定位代码请**按函数名搜索，不要用行号**——文件已被改动多次，行号会漂移。

# 待办_Codex：两档区分度（简洁版 vs 深度版）

## 一、背景：我这边刚做了什么

用户反馈真实生成的申报书「太空白」，我把写作 Agent 重做了一遍，并**重新确立了两档定位**：

| 档位 | 前端卡片名 | 写作 Agent | 章节 | 目标字数 |
|---|---|---|---|---|
| `fast` | 简洁快速版 | `proposal_writer_agent` | 5 章（项目简介/痛点分析/解决方案/核心创新点/社会价值） | **约 1300 字**（1100～1600） |
| `deep` | 深度完整版 | `deep_writer_agent` | 12 章 | **约 5000 字**（4500～6000） |

配套改动（已落盘、已跑通）：

1. 新增 `_PROPOSAL_SPEC`：申报书专属输出规格，覆盖通用 `_REPORT_SPEC` 的「摘要/背景/内容/分析/总结/展望」六段骨架（原来模型会套用这个通用骨架，导致写出很泛的内容）。
2. 新增 `_cjk_len()` / `_expand_to_length()`：篇幅兜底。剥掉 Markdown 标记后统计真实字数，不足阈值就再扩写一轮（最多 2 轮）。**只在字数不够时才发起 LLM 调用，达标则零额外开销。**
3. `llm` 的 `max_tokens` 6000 → **8192**（deepseek-chat 单次输出上限），`request_timeout` 60 → **180** 秒（输出 8192 token 需要 1～2 分钟，60 秒会断流）。
4. 前端卡片文案已改为真实字数：简洁版「约1300字从零生成」、深度版「1300字精简版→5000字完整版」。

## 二、根因：目前只有申报书有区分，其余产物是两档共用同一套

`fast_app` 和 `deep_app` 两个图**共用同一批 Agent 函数**：

- `rule_parser_agent`、`similarity_checker_agent`
- `judge_agent`、`proposal_analysis_agent`
- `defense_questions_agent`、`ppt_outline_agent`、`speech_agent`

这些函数内部统一套 `_REPORT_SPEC`，**拿不到当前是 fast 还是 deep**，所以规则解析、评委点评、答辩问题、PPT 大纲这些产物在两档下长得一模一样。

用户要的「明显区分」只做了一半——申报书区分开了，其余没区分。这是本单要解决的核心问题。

## 三、任务清单

### T1（最高优先级）：让共享 Agent 感知档位

**落点**：`competition_agents.py` + `app.py`

1. 在 `CompetitionState` 里加字段 `tier: str`（取值 `"fast"` / `"deep"`）。
2. `app.py` 的 `_run_generation()` 在构造 state 时写入：`"tier": "deep" if mode == "deep" else "fast"`。
3. 各共享 Agent 按 `state.get("tier")` 选规格常量，不要硬套 `_REPORT_SPEC`。

**建议实现方式**（改动最小，别拆函数）：

```python
_SPEC_BY_TIER = {
    "fast": _BRIEF_SPEC,   # 精简档
    "deep": _FULL_SPEC,    # 完整档
}

def _spec_for(state):
    return _SPEC_BY_TIER.get(state.get("tier"), _FULL_SPEC)
```

然后在 `rule_parser_agent` / `similarity_checker_agent` / `judge_agent` / `proposal_analysis_agent`
里把写死的 `_REPORT_SPEC` 换成 `{_spec_for(state)}`（注意这些是 f-string，直接替换即可）。

**验收**：同一个创意分别用 fast / deep 跑一次，`parsed_rules` 与 `judge_feedback` 的字数比值应 ≥ 2 倍。

### T2：新增两档规格常量

在 `_PROPOSAL_SPEC` 附近新增：

```python
_BRIEF_SPEC = """【精简档输出规格】
1. 每个小节 120～200 字，写成 1～2 个完整自然段
2. 只要有结论和关键依据，不展开推演过程
3. 严禁空小节；中文标点用全角
"""

_FULL_SPEC = """【完整档输出规格】
1. 每个二级小节 300～500 字，拆成 2～3 个自然段
2. 按「现状 → 原因 → 影响 → 应对」展开，要有推算过程和可验证依据
3. 需要对比时用标准 Markdown 表格，表格前后各写一段说明
4. 严禁空小节；中文标点用全角
"""
```

### T3：各产物的字数目标（两档对照）

| 产物（state 字段） | 负责 Agent | 简洁版 fast | 深度版 deep |
|---|---|---|---|
| `parsed_rules` | `rule_parser_agent` | 600～900 字 | 2000～3000 字 |
| `similarity_report` | `similarity_checker_agent` | 500～800 字 | 1500～2500 字 |
| `proposal` | `proposal_writer_agent` / `deep_writer_agent` | 1100～1600 字 | 4500～6000 字 |
| `judge_feedback` | `judge_agent` | 400～600 字 | 1200～1800 字 |
| `proposal_analysis` | `proposal_analysis_agent` | 300～500 字 | 1000～1500 字 |
| `defense_questions` | `defense_questions_agent` | 5 问 × 每题 80 字 | 10 问 × 每题 200 字 |
| `ppt_outline` | `ppt_outline_agent` | 8～10 页，每页要点式 | 15～20 页，每页要点 + 讲解稿 |
| `speech_script` | `speech_agent` | 800～1000 字（约 3 分钟） | 2000～2500 字（约 8 分钟） |

`_expand_to_length()` 已经可以用作兜底，阈值传对应档位的下限即可。

### T4：前端卡片文案与实际对齐

**落点**：`index.html` 约 898～923 行的两张版本卡片。

需要核对并改成实测值的项：

- 简洁版耗时：卡片写「约20秒 / 约30秒」「约30秒出结果」→ 用实测值替换
- 深度版耗时：卡片写「约1分钟 / 约1-2分钟」「约1-2分钟出结果」→ 用实测值替换
- 两档的字数描述保持与 T3 表格一致

**注意**：改文案前必须真跑一次计时，不要凭感觉写。

### T5：补一个验收脚本

参考已有的 `_rich_test.py`（可直接改造），要求：

- 同一创意跑 fast + deep 两遍
- 输出所有产物的字数对照表，并标出「区分度不足」的项（比值 < 2 倍即告警）
- 同时导出两份 docx 供人工核对排版

## 四、边界（不要动）

- **不要改 `docx_render.py` / `docx_inplace.py`**：排版层已验收通过（22/22 断言），动它会影响已交付的格式。
- **不要改 `_OPTIMIZE_SPEC`**：那是 B 链路「保留原表格版式、只换内容」的规格，字数刻意要求与原条目 ±30% 以内，跟本单的两档加厚是两回事。
- **不要降低 `_PROPOSAL_SPEC` 的密度要求**：用户明确要求内容充实，别为了提速又写回「一句话一段」。
- **`max_tokens` 不要再调小**：8192 已是 deepseek-chat 上限，调小会把长申报书截断成半篇。

## 五、验证方式

```bash
cd "C:/Users/34984/Doubao/chats/2026-09-23/new-chat/科创赛事助手"
"C:/Users/34984/.conda/envs/rag-dev/python.exe" _rich_test.py fast
"C:/Users/34984/.conda/envs/rag-dev/python.exe" _rich_test.py deep
```

注意：项目依赖装在 **Conda 环境 `rag-dev`**（`C:\Users\34984\.conda\envs\rag-dev\python.exe`），
不是系统 Python，也不是 workbuddy 托管的 Python——用错解释器会报 `ModuleNotFoundError: langchain_deepseek`。
