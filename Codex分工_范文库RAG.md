# 科创赛事助手 · 范文库 RAG 改造 —— 分工任务书

> 目标：在现有「创意 → 申报书」流水线上加一层**范文检索增强**。
> 后台存高分范文片段 + 标签，用户给关键词，检索命中的范文拼进 prompt，
> 让大模型参考高分写法来生成。**不微调模型。**
>
> 项目根目录：`C:/Users/34984/Doubao/chats/2026-09-23/new-chat/科创赛事助手`

---

## 1. 现有代码事实（已逐行核对，按这个来，不要猜）

| 位置 | 内容 |
|---|---|
| `app.py:436` | `_run_generation(data)` —— 构建 `CompetitionState` 并跑流水线 |
| `app.py:638` | `/api/generate_async` 入口，开线程跑 `_run_generation` |
| `app.py:46-58` | sqlite 建表：`history(id, competition_name, idea, mode, result_data, created_time)` |
| `app.py:961` | `/api/knowledge_status` 已有，返回赛事知识库收录状态 |
| `app.py:8` | **注释警告：启动块不能写在文件中间**，否则其后的 `@app.route` 全部不注册（本地直跑会 404） |
| `competition_agents.py:331` | `class CompetitionState(TypedDict)` |
| `competition_agents.py:539` | `rule_parser_agent` —— **规则知识库注入的现成范例，照抄这个模式** |
| `competition_agents.py:818` | `_stream_llm(prompt, field, every=8)` —— 流式写入，**已改造，不要动** |
| `competition_agents.py:841` | `_build_outline` —— 构思纲要 |
| `competition_agents.py:942` | `deep_writer_agent` —— 深度版正文 |
| `competition_agents.py:1072` | `proposal_writer_agent` —— 简洁版正文 |
| `competition_agents.py:657-771` | `deep_competitor` / `deep_business` / `deep_risk` / `deep_tech` / `plan` / `social_value` 六个专项 agent |
| `data/*.txt` | 赛事规则知识库（8 个文件，按赛事名匹配） |
| `knowledge_base/` | **空目录**，本次用来放范文库 |
| `index.html:960/992/1043` | 赛事下拉 `id="competition"` / 创意输入 `id="idea"` / 生成按钮 |
| `index.html:1014,1028` | 模式单选 `name="mode"`（fast 默认 / deep） |

**依赖实测**：`chromadb`、`langchain_chroma`、`sentence_transformers` 已装；
`jieba`、`faiss`、`rank_bm25` **未装**。

---

## 2. 技术选型（已定，按这个做，别自作主张换）

| 事项 | 决策 | 理由 |
|---|---|---|
| 存储 | **Phase 1 用 sqlite 标签检索**，不用向量库 | 核心是标签交集匹配；chroma 首次要下载 embedding 模型，离线可能失败且慢。向量检索留到 Phase 2 做语义补充 |
| 分词 | 优先 `pip install jieba`（纯 python，很小）；装不上就**退化为标签词表字符串包含匹配** | 不允许因为缺依赖卡住任务 |
| 检索兜底 | 任何异常**静默降级**为空上下文，绝不能让生成流程崩 | 生成是主链路，范文只是增强 |

---

## 3. 标签体系（三类，写入词表，可持续扩充）

```python
MODULE_TAGS = ["项目简介", "社会价值", "实践过程", "商业模式", "创新点", "风险分析"]
TRACK_TAGS  = ["文化文旅", "非遗", "人工智能", "web网站", "校园服务", "乡村振兴"]
FEATURE_TAGS= ["初创阶段", "有软著", "学生团队", "4人团队", "已试点", "用户量小"]
```

**模块标签 → 现有 agent 的映射（注入时必须对应，别注错地方）**

| 模块标签 | 注入目标 |
|---|---|
| 项目简介 | `_build_outline` + `deep_writer_agent` + `proposal_writer_agent` |
| 创新点 | `_build_outline` + 两个 writer |
| 社会价值 | `social_value_agent`（`competition_agents.py:771`） |
| 商业模式 | `deep_business_agent`（`:679`） |
| 风险分析 | `deep_risk_agent`（`:702`） |
| 实践过程 | `plan_agent`（`:748`） |

赛道/特征标签不单独注入，只用于**筛选命中的范文**。

---

## 4. 任务拆分（6 个，文件归属已划清，可并行）

### 任务 1 · 数据层 —— 新建 `kb_samples.py`

范文库存储与 CRUD，sqlite 表建在 `competition.db` 里（与 history 同库）。

```sql
CREATE TABLE IF NOT EXISTS kb_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  content TEXT NOT NULL,          -- 范文片段原文
  tags TEXT NOT NULL,             -- 逗号分隔，如 "项目简介,文化文旅,web网站"
  source TEXT DEFAULT '',         -- 来源说明（选填）
  score INTEGER DEFAULT 0,        -- 范文评分（选填，用于排序）
  created_time TEXT
);
CREATE INDEX IF NOT EXISTS idx_kb_tags ON kb_samples(tags);
```

必须提供的函数（签名固定，其他任务按这个调用）：

```python
def add_sample(content: str, tags: list, source: str = "", score: int = 0) -> int
def list_samples(tag: str = None, limit: int = 100) -> list   # 每项含 id/content/tags/source/score/created_time
def delete_sample(sample_id: int) -> bool
def get_all_tags() -> dict        # {"module": [...], "track": [...], "feature": [...]}，含词表 + 库中已用标签
```

**验收**：`python -c "import kb_samples as k; print(k.add_sample('测试范文', ['项目简介']))"` 能插入并查回。

---

### 任务 2 · 检索层 —— 新建 `kb_retrieve.py`

```python
def extract_keywords(text: str) -> list
    # 从用户描述里抽关键词。优先 jieba 分词后与三类词表求交集；
    # jieba 不可用时退化为词表字符串包含匹配。
    # 必须同时识别别名：web/网站/网页 → "web网站"；AI/人工智能/机器学习 → "人工智能"

def search_samples(user_keywords: list, module_tag: str = None,
                   top_k: int = 3, max_chars: int = 3000) -> str
    # 1) 与 tags 求交集打分：模块标签权重 3，赛道标签 2，特征标签 1
    # 2) 按分降序取 top_k
    # 3) 拼接，总长截断到 max_chars（超出部分丢弃，不截断到一半的句子就整段丢）
    # 4) 返回格式化文本；无命中返回 ""
```

**验收**：
```python
from kb_retrieve import extract_keywords, search_samples
ks = extract_keywords("我做了一个苏轼文旅网站，4人团队，要写项目简介")
print(ks)                                  # 应含 "文化文旅"/"web网站"/"项目简介"/"4人团队"
print(len(search_samples(ks, "项目简介")))  # > 0
```

---

### 任务 3 · 注入层 —— 改 `competition_agents.py`

1. 在 `CompetitionState`（`:331`）**新增可选字段** `user_keywords: str`（不删改任何已有字段）
2. `app.py:_run_generation` 里从 `data.get("keywords", "")` 填进去
3. 新增统一函数（放在 `_stream_llm` 之前）：

```python
def _ref_block(state: dict, module_tag: str) -> str:
    """取该模块的范文参考块；检索失败或为空返回空串，绝不抛异常。"""
    try:
        from kb_retrieve import extract_keywords, search_samples
        kws = extract_keywords(state.get("idea", "") + " " + state.get("user_keywords", ""))
        ref = search_samples(kws, module_tag)
        return f"【高分范文参考（务必学习其结构与表述风格，不要照抄内容）】\n{ref}\n" if ref else ""
    except Exception as e:
        print(f"[kb] 范文检索跳过：{e}")
        return ""
```

4. 在下列 agent 的 prompt 里**拼接 `{_ref_block(state, '对应模块标签')}`**：
   `_build_outline`、`deep_writer_agent`、`proposal_writer_agent`（模块标签用「项目简介」）；
   `social_value_agent`、`deep_business_agent`、`deep_risk_agent`、`plan_agent`（各用对应标签）。

> 参照 `rule_parser_agent:545` 里 `kb_block` 的写法拼进 prompt。
> **不要动 `_stream_llm` 和任何流式逻辑。**

**验收**：`python -m py_compile competition_agents.py` 通过；
跑一次生成，日志应出现 `[kb] 范文检索命中 N 段`。

---

### 任务 4 · 接口层 —— 改 `app.py`

新增 4 个路由，**必须写在文件末尾所有现有路由之后、`if __name__ == '__main__'` 之前**
（见第 1 节的启动块警告）：

| 方法 | 路径 | 用途 | 请求体 / 返回 |
|---|---|---|---|
| POST | `/api/kb/add` | 新增范文 | `{content, tags, source, score}` → `{success, id}` |
| GET | `/api/kb/list` | 列表 | `?tag=&limit=` → `{success, items}` |
| DELETE | `/api/kb/delete/<id>` | 删除 | → `{success}` |
| GET | `/api/kb/tags` | 标签词表 | → `{success, module, track, feature}` |

`/api/generate_async` 额外接收 `keywords` 字段并透传给 `_run_generation`。

**验收**：`curl -s -X POST localhost:8080/api/kb/add -H "Content-Type: application/json" -d '{"content":"测试","tags":["项目简介"]}'` 返回 `{"success":true,...}`。

---

### 任务 5 · 前端 —— 改 `index.html`

1. **关键词输入**：在 `id="idea"` 的 textarea 下方加一行输入框 `id="keywords"`，
   placeholder：`关键词（选填，逗号分隔）：如 苏轼文旅, web网站, 4人团队`。
   提交时随 `competition_name / idea / mode` 一起带上 `keywords`。
2. **范文库管理页**：新增一个 Tab（照现有 Tab 结构加，按钮 + `tab-content`，
   并同步 `_STREAM_MAP` 里没有的字段不用管）。页面包含：
   - 表单：范文内容 textarea + 标签输入（逗号分隔）+ 提交按钮
   - 标签快捷选择：三类标签做成可点击 chip，点了自动填进标签框
   - 列表：已有范文（内容摘要 + 标签 + 删除按钮）
   - 检索测试框：输入关键词 → 显示命中的范文（调任务 4 的接口）

**验收**：页面能新增一条范文并在列表里看到；生成时能带上关键词。

---

### 任务 6 · 种子数据 —— `knowledge_base/seed_samples.json`

准备 **8-12 段**范文片段，覆盖：项目简介 / 社会价值 / 商业模式 / 风险分析 四个模块，
赛道覆盖 文化文旅 + web网站、人工智能、校园服务 至少三类。
每段 300-600 字（实践过程这类分阶段的章节天然偏长，不必硬砍），
写成**真实的高分申报书语气**（数据化表达、无 AI 空话），并配好标签。
写一个 `import_seed.py` 导入（调 `kb_samples.add_sample`）。

> 本项**已由主项目完成并可直接复用**：`knowledge_base/seed_samples.json`（13 段，
> 模块标签 6/6、赛道标签 6/6 全覆盖）+ `import_seed.py`。
> Codex 无需重复生成，直接导入即可。

> 内容质量直接决定生成效果，这一步别敷衍。

---

## 5. 硬性约束（违反会出问题）

1. **`app.py` 启动块位置**：绝不能把 `app.run(...)` 写在路由中间，否则后面的路由全部 404（第 8 行有警告注释）。
2. **文件读写全部显式 `encoding='utf-8'`**，Windows 环境。
3. sqlite 历史表字段是 `result_data`，不是 `data`（容易写错）。
4. **不要动**：`_stream_llm` 流式逻辑、六个 Tab 结构、导出链路（Word/PDF/PPT/zip）。
5. **范文注入长度封顶 3000 字**，否则 prompt 膨胀会拖慢流式、甚至超 token。
6. 检索任何异常都要 **try/except 吞掉并降级为空**，生成主链路优先。
7. 新增依赖前先确认能装上；装不上就用降级方案，不要卡住。

---

## 6. 建议交付顺序

```
任务1(数据层) → 任务2(检索层) → 任务6(种子数据) → 任务3(注入) → 任务4(接口) → 任务5(前端)
```

任务 4 和 5 依赖 1-3，可最后做；任务 6 可与 1、2 并行。

## 7. 总验收

1. `python -m py_compile app.py competition_agents.py kb_samples.py kb_retrieve.py` 全过
2. 服务启动，`/api/health` 返回 200
3. 调 `/api/kb/add` 加一条范文 → `/api/kb/list` 能查到
4. 带关键词跑一次生成（简洁版即可），确认日志有范文命中，且生成内容明显带有范文的结构风格
5. 不带关键词跑一次，确认流程照常、无报错（降级路径）
6. 前端能加范文、能带关键词生成
