# WorkBuddy 回执 · 417-1 Word 封面+目录 实测结论

- 时间：2026-09-30 05:16 (GMT+8)
- 调查人：WorkBuddy（接手 Codex 未完成的 417-1）
- 对象：kcwx.online / kechuang2026.cn 线上导出「项目作品说明书全文」(proposalText)

## 结论（一句话）
**417-1 的「Word 封面 + 目录」功能在代码与部署层面均已具备且实测可用，dispatch 投诉应为旧版本/短文档阈值所致，非当前线上缺陷。**

## 证据链
1. `static/wbconst.js`：`proposalText → 'default'`。
2. `docx_render.py` PROFILES：`'default'` = `{cover:True, toc:True}`（封面+目录双开）。
   - 封面：`_cover()`（line 504）；目录：`_add_toc()` + TOC 域 + 静态页码缓存（line 672/635）。
   - git 历史：封面逻辑在 ~202 轮、TOC 域在 234/235 轮（`6f23fcb2`）已落地。
3. 直接渲染实测（服务器 venv `/opt/comp-agent/.venv/bin/python3`）：
   - 长文档（4960 字符）→ `HAS_COVER_TITLE=True, HAS_SUBTITLE=True, HAS_TOC_FIELD=True, HAS_TOC_HEADING(目 录)=True, HAS_BOOKMARK=True, PAGE_BREAKS=2`。**封面+目录均正常生成**。
   - 短文档（1860 字符）→ `toc=False`（被见下「风险1」阈值关掉），但封面仍在。
4. 部署一致性：运行中 gunicorn 启动于 04:46；`docx_render.py` mtime 04:38（启动前），故线上加载的就是当前含封面/目录版本。prod 与 staging 两份 `docx_render.py` mtime 完全一致。

## 两个真实风险（建议处理，非 417-1 阻塞项）
- **风险1 · 2500 字阈值（docx_render.py:1174）**：正文去空白后 <2500 字时，目录被**静默关闭**（封面仍在）。若某次导出的说明书偏短/被截断，用户会拿到「有封面无目录」。
  - 建议：对 `default/report` 这类「封面文档」改用「章节数 ≥3 即出目录」判据，或对封面文档把阈值降到 ~1200 字。
- **风险2 · app.py 部署滞后**：`app.py` mtime 05:08，晚于 gunicorn 启动 04:46 → 05:08 之后的 app.py 改动**未生效**。
  - 建议：改动 .py 后必须 `systemctl restart comp-agent`（gunicorn 不热重载）。本轮未动 app.py，仅提示。

## 备注
- `/api/export_word` 需有效用户 cookie（`_require_uid`），匿名无法直连实测；上述结论由「磁盘代码渲染实测 + mtime 比对」双重确认，不需登录。
- 若投诉在 04:38 之后仍复现「无封面」，需排查：移动端 WPS 是否不刷新域（封面是普通段落不受影响）；或导出的是否为更早生成的旧文件。
