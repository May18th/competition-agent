# 待办清单（负责人：Codex）—— 文档导出接线 + 内容层提示词

> 生成时间：2026-09-25
> 详细背景见 `交接_Codex_文档内容与导出接线.md`（分工边界、格式标准、doc_type 对照表都在那里）。
> **本文件是可直接照做的操作清单**，按顺序做 T1→T7 即可。
> 行号基于当前 `app.py`（1077 行）。行号会漂移，**以函数名为准**。

## 红线（先看）

1. **不要改 `index.html` / `static/`**（前端由 WorkBuddy 负责）。
2. **不要改 `docx_render.py` / `docx_inplace.py` / `cover_style.py`**（格式层已交付并验证，要改先说）。
3. 你只动 **`app.py`**（接线）和 **`competition_agents.py`**（内容层提示词）。
4. 改完必须跑 `python -m py_compile app.py`，再重启 Flask（本项目 `debug=False`，不热重载）。
5. ⚠️ 改之前先 `netstat -ano | findstr :8080`，**只应有 1 行**；多个进程会让你的验证结果随机跳变。

### ✅ 前端已就位（WorkBuddy 做完，你不用再写界面）

`index.html` 已经改好并生效（页面是直接读文件返回的，改完刷新即生效，不用重启服务）。
**你只要保证后端接得住这些字段，不要再造一套 UI。**

| 前端已做 | 会发给你什么 |
|---|---|
| 导出中心新增「封面信息」三个输入框（学校名 / 团队名 / 指导老师，存 localStorage） | `/api/export_word` 和 `/api/export_zip` 的 JSON 里带 `school` / `team` / `advisor` |
| 每个「单独下载」按内容自动带档位 | `/api/export_word` 的 JSON 里带 `doc_type`：申报书全文→`default`、PPT大纲→`outline`、规则/检测报告→`report`、其余分析类→`analysis` |
| 上传 `.docx` 原文件后，导出中心出现「原格式申报书导出」卡片 + 两个单选 | `/api/export_original_format` 的 multipart 表单：`original_file`、`optimized_text`、`mode`（`keep` / `reformat`）、`title`、`school`、`team`、`advisor` |

实跑验证（node 跑前端逻辑，非肉眼看代码）：
```
POST /api/export_word  {"title":"项目申报书全文","text":"...","doc_type":"default","school":"某某大学","team":"启明创新团队","advisor":"张三 教授"}
POST /api/export_word  {"title":"PPT大纲","text":"...","doc_type":"outline","school":"...","team":"...","advisor":"..."}
POST /api/export_original_format  FormData: original_file, optimized_text, mode=keep, title, school, team, advisor
```

> 注意：`exportOne` 在内容为空时会直接 `wbToast` 警告、**不发请求**，所以你调试时看不到请求是正常的，不是 bug。

---

## T0｜前置自检（5 分钟）

```bash
cd C:\Users\34984\Doubao\chats\2026-09-23\new-chat\科创赛事助手
git pull
C:\Users\34984\.conda\envs\rag-dev\python.exe _test_docx_render.py
```

期望最后一行输出：**`全部通过：页边距/字体/表格/缩进 均符合规范`**。
不是这个结果说明格式层有问题，**先告诉我，别自己改渲染器**。

---

## T1｜`_build_docx()` 改成委托（这是所有导出的总入口，必须先做）

**位置**：`app.py:153` `def _build_docx(title, text)`

**现状**：手写逐行渲染，Markdown 表格被原样写成 `| 创新性 | 30% |` 裸文本（用户吐槽"排版非常差"的根因）。

**改成**（整函数替换，保持签名向后兼容，现有 4 个调用点不用动）：

```python
def _build_docx(title, text, doc_type='report', subtitle=None,
                school=None, team=None, advisor=None):
    """统一走 docx_render 渲染器（格式层，WorkBuddy 已交付）。"""
    from docx_render import build_docx
    return build_docx(
        title, text,
        subtitle=subtitle,
        doc_type=doc_type,
        school=school, team=team, advisor=advisor,
    )
```

**验收**：`python -m py_compile app.py` 通过；随便导出一个报告，打开 Word 看表格是不是**真表格**。

---

## T2｜`export_word()` 停止重复造轮子 + 透传封面字段

**位置**：`app.py:255` `def export_word()`

**现状**：把 `_build_docx` 的手写逻辑**又抄了一遍**（`app.py:263` 起 `doc = Document()`）。

**改成**：删掉 263 行开始的整段手写渲染，直接：

```python
doc = _build_docx(
    title, text,
    doc_type=data.get('doc_type', 'report'),
    subtitle=data.get('competition_name'),
    school=data.get('school'),
    team=data.get('team'),
    advisor=data.get('advisor'),
)
```

**封面三字段**：`school` / `team` / `advisor` 从请求 JSON 里取，取不到传 `None`（渲染器会自动省略该行，不会打出"None"）。
前端输入框由 WorkBuddy 加，**你只要保证接口收得到**。

---

## T3｜四个导出接口补 `doc_type`

| 函数 | 位置 | 改成 |
|---|---|---|
| `export_defense()` | `app.py:321`（调用在 327） | `_build_docx(title, text, doc_type='analysis')` |
| `export_ppt()` | `app.py:334`（调用在 340） | `_build_docx(title, text, doc_type='outline')` |
| `export_competitor()` | `app.py:347`（调用在 353） | `_build_docx(title, text, doc_type='analysis')` |
| `export_business()` | `app.py:360`（调用在 366） | `_build_docx(title, text, doc_type='analysis')` |

> `outline` = 大纲档：**不缩进、靠左、标题最小**，符合用户"大纲最轻最简"的要求。

---

## T4｜打包导出 `export_all()` 里的手写段

**位置**：`app.py:676` `def export_all()`，内部手写段在 **`app.py:707`** `doc = Document()` 起。

**改成** `build_docx`，5 个文件分别传：

| 文件名 | doc_type |
|---|---|
| `1_申报书全文` | `'default'` |
| `2_竞品与商业模式` | `'analysis'` |
| `3_风险分析与评委意见` | `'analysis'` |
| `4_答辩问题预测` | `'analysis'` |
| `5_PPT大纲` | `'outline'` |

---

## T5｜`export_zip()` 里的内部 `build_doc()`

**位置**：`app.py:836` `def export_zip()`，内部 `build_doc()` 在 **`app.py:865`**。

**改成**：内部 `build_doc(title, text)` 委托 `_build_docx(title, text, doc_type=...)`，
按标题关键词判断档位（含"大纲/PPT"→`outline`，含"申报书"→`default`，其余→`analysis`）。

> `app.py:920` 的图表 `cdoc`（微软雅黑标题）**可以保留手写**，它不涉及 Markdown，
> 但建议标题改成**宋体五号加粗居中**，跟其他文档统一。

---

## T6｜★ 最重要：`export_original_format()` 换用 `docx_inplace` + 加 `mode` 开关

**位置**：`app.py:730` `def export_original_format()`

### 现状的三个致命问题

1. **只遍历 `doc.paragraphs`，完全不碰表格** —— 而申报表的内容基本都在表格里，等于**根本没替换**。
2. 优化文本比原文长时**多出来的直接丢弃**。
3. 没有用户可选项。

### 用户原话（必须满足）

> 「这个申报表规则仅限于创意的，优化申报表的原则是不改变原来申报表的格式和排版，只修改内容。」
> 「申报书的内容也是改的啊，除了格式排版其他都改，版式不要动，内容改。」
> 「或者可以加一个选项，让用户自行选择要不要替换。」

### 整函数替换成

```python
@app.route('/api/export_original_format', methods=['POST'])
def export_original_format():
    """
    B 链路：用户上传已有申报表 → AI 改内容 → 导出。
    mode=keep     (默认) 保留原格式排版，只原位换字
    mode=reformat        按申报书标准重新排版（用户主动勾选才走）
    """
    original_file = request.files.get('original_file')
    optimized_text = request.form.get('optimized_text', '')
    mode = request.form.get('mode', 'keep')
    title = request.form.get('title', '项目申报书')
    school = request.form.get('school')
    team = request.form.get('team')
    advisor = request.form.get('advisor')

    if not original_file:
        return jsonify({"success": False, "error": "没有原文件"})
    if not optimized_text.strip():
        return jsonify({"success": False, "error": "优化内容为空"})

    try:
        original_bytes = original_file.read()
        if mode == 'reformat':
            # A 链路：按申报书标准重排（封面 + 目录 + 页码）
            import io as _io
            from docx_render import build_docx
            doc = build_docx(title, optimized_text, doc_type='default',
                             school=school, team=team, advisor=advisor)
            buf = _io.BytesIO()
            doc.save(buf)
            buf.seek(0)
            fname = '申报书_标准排版.docx'
        else:
            # B 链路：原位换字，格式排版一律不动
            from docx_inplace import apply_content_keep_style
            buf, report = apply_content_keep_style(original_bytes, optimized_text)
            print('[export_original_format] 替换报告:', report)
            fname = '优化后的申报书.docx'

        return send_file(
            buf, as_attachment=True, download_name=fname,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
    except Exception as e:
        return jsonify({"success": False, "error": f"导出失败：{str(e)}"})
```

### `docx_inplace` 做了什么（不用你实现，只要接线）

- 按文档真实顺序遍历 `w:p` **和 `w:tbl`**，表格单元格行优先展开 → **表格内容也会被替换**
- 只改 `run.text`，字体/字号/颜色/加粗/缩进/边框/底纹**全部不动**
- 优化文本更长 → 多出的追加到末尾（不丢）；更短 → 剩余位置保持原文
- 返回 `report`：`{'slots': 52, 'items': 5, 'replaced': 5, 'appended': 0, 'untouched': 47}`

### 你还要配合改一处提示词（很重要）

优化类 Agent 的输出要**和原表条目一一对应**，替换才准。请在对应 prompt 里加：

> 优化输出必须保持原申报表的条目结构一一对应：不合并条目、不拆分条目、不新增条目、
> 不加 Markdown 标题符号，每一条只输出改写后的文字。
> **每条优化后的文字长度与原条目大致相当（±30% 以内）**，宁可精炼也不要大幅膨胀，
> 避免撑破原表格版式。

> ⚠️ 注意区分：**版式不动 ≠ 内容不动**。内容要实质改好（更充实、更专业、更有说服力），
> 只是不能因为写太长把单元格撑变形。

---

## T7｜内容层提示词改造（`competition_agents.py`）

格式只解决"好看"，**用户真正不满的是内容单薄**。以下全部是用户原话，逐条落进 prompt。

### 报告类（proposal / report / 报告性章节）

1. **必须有三级目录**，三级标题用**正式短语**，**不能是句子**
   - ❌ `## 我们的项目是怎么解决老人摔倒问题的`
   - ✅ `## 二、技术方案` → `### （一）多模态感知层`
2. **结构完整**：`摘要 / 背景 / 内容 / 分析 / 总结 / 展望`，一个都不能少。
3. **严禁短句、严禁几句话就写完**。每个小节写成 **150～400 字的完整段落**，有论点、有展开、有依据。
4. **严禁整篇用序号罗列**（不要 `1. xxx 2. xxx 3. xxx` 清单体）。
   - ❌ `1. 成本低  2. 效率高  3. 易部署`（三行就没了）
   - ✅ 写成一段："本方案在成本、效率与部署三方面具备显著优势。成本方面……效率方面……部署方面……"
   - 例外：确实要逐条对比的（评分维度、参数对比）用 **Markdown 表格**，不用序号列表。
5. **要有完整分析，不要只给结果**
   - ❌ `创新性得分 30 分。`
   - ✅ 评分依据 → 技术细节 → 同类对比 → 优势与风险，写成段落。
6. 表格用**标准 Markdown 表格**（`| a | b |` + `|---|---|`），渲染器会转成真 Word 表格。
7. **要有实在内容**：技术细节、数据、案例、对比，不能通篇"本项目具有创新性"这种空话。

### 分析类（competitor / business / risk / judge_feedback / diagnosis）

- **必须分段阐述**，不能只有结论清单。
- 每个维度：`现状 → 原因 → 影响 → 应对`，写成段落，不要一句话一行。
- 不要"综上所述"一句话收尾就结束。

### 大纲类（ppt_outline / speech 的大纲部分）

- **最轻最简**：只要层级清晰的条目，**不要段落、不要大段阐述**。
- 每页/每条一行短语，不要写完整句子。

### 通用红线

- 目录里的三级标题**不要是句子**，要像 `1.1 技术架构` 这种正式条目。
- 严禁"以下是……"这种口水过渡句堆篇幅。
- **内容宁可长，不可短**（用户明确：短 = 质量差）。

### 建议实现

在各 Agent 的 system/user prompt 末尾加一段**输出规格约束**：

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

并在生成后处理里加**长度自检**：某章节正文 < 150 字就 `print` 一条 warning（方便定位哪个 Agent 偷懒）。

---

## 验收清单（做完逐条勾）

### 格式（改动生效即可验证，不用看内容）

```bash
python -m py_compile app.py              # 无输出 = 通过
```

- [ ] 导出的 Word 里表格是**真表格**（能选中单元格、有边框），不是 `| xxx |` 文本
- [ ] 正文**宋体小四**、一级标题**黑体二号**、数字英文 **Times New Roman**
- [ ] 大纲类文档**没有首行缩进**、全部靠左
- [ ] 报告类有**目录页**，条目能对应到正文标题
- [ ] 页边距上下 2.54 / 左右 2.5 cm、1.5 倍行距、页码底部居中、**封面无页码**
- [ ] 封面能看到**学校名 / 团队名 / 指导老师**

### B 链路（申报表优化）★ 重点验这个

- [ ] 上传一份**表格版**申报表 → 优化 → 导出，**表格里的文字被替换了**（旧代码这里完全不生效）
- [ ] 导出文档的**表格结构、行列数、字体字号与原文件一致**
- [ ] 优化文本更长时**没有丢内容**（旧代码直接丢弃）
- [ ] `mode=reformat` 时走标准排版（带封面/目录）
- [ ] 控制台能看到 `[export_original_format] 替换报告: {...}`

### 内容

- [ ] 报告类**三级目录齐全**，三级标题不是句子
- [ ] 每个小节是**完整大段**，不是三五行就结束
- [ ] 全文**没有整篇序号罗列**

---

## 完成后

1. `git add -A && git commit -m "feat(docx): 导出接口接入 docx_render/docx_inplace，内容层提示词强化"`
2. 本地重启 Flask 自测一遍
3. 告诉我一声，我来推到 GitHub 并部署到阿里云（`/opt/comp-agent`，`git pull && systemctl restart comp-agent`）

> Windows 上 push GitHub 要走 Clash 代理 `127.0.0.1:7877` + GCM 凭据，命令见项目根目录 `ssh_aliyun.sh` 附近的环境笔记。
> **推不动就别硬试，交给我。**
