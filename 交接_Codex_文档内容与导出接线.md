# 交接给 Codex：文档「内容层」改造 + app.py 导出接线

> 生成时间：2026-09-25
> 分工：**WorkBuddy 已交付「格式层」**（排版渲染器），**Codex 负责「内容层」**（Agent 提示词）+ app.py 接线。
> 用户原话诉求：文档「质量一般、排版差、不够专业」，并给出了一套明确的**文档格式标准**和**内容深度要求**。

---

## 0. 分工边界（重要，别越界也别漏）

| 层 | 负责人 | 状态 |
|---|---|---|
| **格式层**：Word 排版渲染（字体/字号/页边距/行距/缩进/表格/标点/页码/目录） | WorkBuddy | ✅ 已交付 `docx_render.py` + `cover_style.py`，本地四档验证全通过 |
| **内容层**：Agent 提示词（报告要写多长、什么结构、目录怎么起） | **Codex** | ⬜ 待做 |
| **接线**：app.py 各导出接口调用新渲染器 | **Codex** | ⬜ 待做 |

WorkBuddy **不会**改 `competition_agents.py`，也不会改 `app.py` 的路由结构，避免和你冲突。

---

## 1. Codex 要做的第 1 件事：app.py 导出接线

### 1.1 背景
原来 `app.py` 里有 **5 处**各自手写的 docx 生成逻辑（`_build_docx`、`export_word`、打包里的 `build_doc`、图表 `cdoc` 等），
共同毛病是**逐行纯文本渲染** —— Markdown 表格被原样写成 `| 创新性 | 30% | ... |` 一行行裸文本，
引用块 `>`、代码块 ```` ``` ```` 也全部退化。这是用户看到的"排版非常差"的直接原因。

### 1.2 新模块（已提交，直接用）
```
docx_render.py   # 统一渲染器，对外只暴露 build_docx()
cover_style.py   # 封面背景图（默认关闭，申报书标准禁止底色）
```

调用签名：
```python
from docx_render import build_docx

doc = build_docx(
    title,              # 文档主标题（封面黑体小初）
    text,               # Markdown 正文
    subtitle=None,      # 封面副标题（黑体二号），如赛事名
    org=None,           # 封面单位行（黑体小三），如「XX大学 · 团队名」
    toc=None,           # 目录页；None = 按 doc_type 档位自动决定
    cover=None,         # 封面页；None = 按 doc_type 档位自动决定
    cover_image=False,  # 封面背景图，默认 False（申报书标准禁止底色/特效）
    topic=None,         # 背景图风格匹配文本
    doc_type='report',  # 'report'报告 / 'analysis'分析 / 'outline'大纲 / 'default'申报书
)
doc.save(path)
```

### 1.3 需要改的位置（按行号，当前 main 分支）

| 位置 | 现状 | 改成 |
|---|---|---|
| `app.py:153` `_build_docx()` | 手写逐行渲染 | **改为委托**：`from docx_render import build_docx` 后 `return build_docx(title, text, doc_type=doc_type)` |
| `app.py:255` `export_word()` | 又抄了一遍同样的手写渲染 | 改用 `_build_docx(title, text, doc_type=data.get('doc_type','report'))` |
| `app.py:327` `export_defense()` | `_build_docx(title, text)` | 加 `doc_type='analysis'` |
| `app.py:340` `export_ppt()` | `_build_docx(title, text)` | 加 `doc_type='outline'` |
| `app.py:353` `export_competitor()` | `_build_docx(title, text)` | 加 `doc_type='analysis'` |
| `app.py:366` `export_business()` | `_build_docx(title, text)` | 加 `doc_type='analysis'` |
| `app.py:707` 打包 `export_all()` 里的 `doc = Document()` 手写段 | 微软雅黑 + 逐段 | 改用 `build_docx`，5 个文件分别传：`1_申报书全文→'default'`、`2_竞品与商业模式→'analysis'`、`3_风险分析与评委意见→'analysis'`、`4_答辩问题预测→'analysis'`、`5_PPT大纲→'outline'` |
| `app.py:865` `export_zip()` 里的内部 `build_doc()` | 微软雅黑 + 逐行 | 同上，按标题关键词判断 doc_type |
| `app.py:920` 图表 `cdoc` | 微软雅蓝标题 | 图表标题用宋体五号加粗居中即可，可保留手写（不涉及 Markdown） |

### 1.4 doc_type 与格式的对应关系（已在 docx_render.py 里固化，Codex 只需传对参数）

| doc_type | 一级标题 | 二级标题 | 三级标题 | 正文 | 首行缩进 | 封面 | 目录 |
|---|---|---|---|---|---|---|---|
| `default`（申报书） | 黑体二号加粗 | 黑体小三加粗 | 黑体四号加粗 | 宋体小四 | ✅ 2 字符 | ✅ | ✅ |
| `report`（报告） | 黑体二号加粗 | 黑体小三加粗 | 黑体四号加粗 | 宋体小四 | ✅ 2 字符 | ✅ | ✅ |
| `analysis`（分析） | 黑体二号加粗 | 黑体小三加粗 | 黑体四号加粗 | 宋体小四 | ✅ 2 字符 | ✅ | ❌ |
| `outline`（大纲） | **黑体四号加粗** | **宋体小四加粗** | **宋体小四常规** | 宋体小四 | ❌ **不缩进、靠左对齐** | ❌ | ❌ |

通用：A4、页边距上下 2.54cm / 左右 2.5cm、1.5 倍行距、
中文只允许宋体/黑体、数字英文统一 Times New Roman、中文标点全角、页码底部居中（封面无页码）。

---

## 2. Codex 要做的第 2 件事：内容层提示词改造（这是重点）

格式只能让文档"好看"，**用户真正不满的是内容太单薄**。以下全部来自用户原话，请逐条落到 `competition_agents.py` 的提示词里。

### 2.1 报告类（proposal / 各类 report / rich_deck 里的报告性章节）

**必须满足：**

1. **必须有三级目录**，且三级标题要用**正式短语**，**不能是句子**。
   - ❌ 错误：`## 我们的项目是怎么解决老人摔倒问题的`
   - ✅ 正确：`## 二、技术方案` → `### （一）多模态感知层`
2. **结构必须完整**：`摘要 / 背景 / 内容 / 分析 / 总结 / 展望` 一个都不能少。
3. **严禁短句、严禁几句话就写完**。每个小节要写成**完整的大段文字**（一段 150～400 字），
   有论点、有展开、有数据或事实支撑。用户明确说：**"严禁几句话就写完，严禁短句，要写一大段完整的大段文字"**。
4. **要有完整分析，不要只给结果**。
   - ❌ 错误：`创新性得分 30 分。`
   - ✅ 正确：先说评分依据 → 再展开技术细节 → 再对比同类方案 → 最后点出优势与风险。
5. 表格用**标准 Markdown 表格**输出（`| a | b |` + `|---|---|`），渲染器会转成真 Word 表格。

### 2.2 分析类（competitor_analysis / business_model / risk_analysis / judge_feedback / diagnosis）

- **必须分段阐述**，不能只有结论清单。
- 每个分析维度：现状 → 原因 → 影响 → 应对，写成段落，不要一句话一行。
- 不要出现"综上所述"一句话收尾就结束的情况。

### 2.3 大纲类（ppt_outline / speech_script 的大纲部分）

- **最轻最简**：只要层级清晰的条目，**不要段落、不要大段阐述**。
- 每页/每条一行短语，不要写完整句子。
- 用户原话：**"大纲不要段落、不要大段阐述"**。

### 2.4 通用红线

- **目录里的三级标题不要是句子**，要像"1.1 技术架构"这种正式条目。
- 报告里**严禁**出现"以下是……"这种口水过渡句堆篇幅。
- 内容宁可长，不可短。用户明确表示：**短 = 质量差**。

### 2.5 建议的实现方式

在各 Agent 的 system/user prompt 里加一段**输出规格约束**，例如：

```
【输出规格 —— 必须遵守】
1. 使用 Markdown，最多三级标题（## / ###），一级用「一、二、三、」，二级用「（一）（二）」，三级用「1. 2. 3.」
2. 三级标题必须是正式短语，不是完整句子
3. 结构必须包含：摘要 / 背景 / 内容 / 分析 / 总结 / 展望
4. 每个小节必须写成 150～400 字的完整段落，有论点、有展开、有依据；严禁一句话一段、严禁短句罗列
5. 分析类内容必须给出「现状→原因→影响→应对」的完整链条，不能只给结论
6. 表格用标准 Markdown 表格语法
7. 全文中文标点用全角
```

并在 `_run_generation` 或后处理里加一个**长度自检**：
若某章节正文 < 150 字，记录 warning 日志（方便我们后续定位是哪个 Agent 偷懒）。

---

## 3. 验收标准（改完请自测）

```bash
cd /opt/comp-agent
git pull
systemctl restart comp-agent
```

然后从网站跑一次生成，导出各类文档，检查：

- [ ] Word 里表格是**真表格**（能选中单元格、有边框），不是 `| xxx |` 文本
- [ ] 正文字体是**宋体小四**、一级标题**黑体二号**、数字英文 **Times New Roman**
- [ ] 大纲类文档**没有首行缩进**、全部靠左
- [ ] 报告类文档**有三级目录**，且三级标题不是句子
- [ ] 报告类每个小节**段落完整**，不是三五行就结束
- [ ] 页边距 / 1.5 倍行距 / 页码居中 / 封面无页码

本地可先跑格式自检（不涉及内容）：
```bash
python _test_docx_render.py     # 四档格式断言，应输出「全部通过」
```

---

## 4. WorkBuddy 已交付的东西（Codex 不用重复做）

- `docx_render.py`：块级 Markdown 解析 + 四档样式 + 真表格 + 全角标点 + 页码 + 目录域
- `cover_style.py`：按主题匹配的封面背景图（**默认不启用**，因为申报书标准禁止底色）
- `_test_docx_render.py`：四档格式断言脚本
- 部署运维：`deploy_aliyun.sh`、nginx 反代、`/opt/comp-agent`

**注意**：`cover_image` 默认 `False`。如果用户哪天要"花哨版封面"（非申报场景），
只要给 `build_docx(..., cover_image=True, topic='项目关键词')` 即可，风格会自动匹配或随机。
