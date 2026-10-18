# 后台运营工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将后台统计、质量、Token、告警、工单和留存能力统一为可操作的运营工作台。

**Architecture:** 在 `app.py` 中先抽出纯函数和统计服务接口，页面继续沿用现有服务端 HTML，逐步把数据以 JSON 提供给后台视图。所有统计先经过统一范围和赛事目录规范化，再由页面渲染。

**Tech Stack:** Flask、SQLite、原生 HTML/CSS/JavaScript、现有 `llm_usage_store` 和质量门模块。

**Spec:** `docs/superpowers/specs/2026-10-18-admin-operations-design.md`

## Global Constraints

- 不修改前台生成、聊天、导出质量门核心判定。
- 不删除生产用户数据、数据库、回滚点和运行产物。
- Token 统计只展示脱敏用户键。
- 未收录赛事只隐藏/规范展示，不删除原始历史记录。
- staging 8081 通过后再更新生产 8080。

## Review Focus

- 同一时间范围下 `/admin`、`/admin/panel`、`/monitor` 和 API 的总数必须一致。
- 未收录赛事不能出现在图表、列表、反馈摘要和 CSV 展示字段中。
- 只读角色可以查看但不能改变工单、导出全量数据或修改配置。
- Token 聚合失败时页面必须显示“暂不可用”，不能泄露异常堆栈。
- 日志留存清理不能触碰用户作品和回滚数据库。

### Task 1: 统一统计范围与赛事目录

**Files:** Modify `app.py`; Test `tests/probes/test_admin_operations.py`.

- [ ] 写失败测试：同一时间范围下四个统计入口使用相同计数；别名归并，未收录赛事被排除。
- [ ] 运行测试确认因缺少统一统计函数而失败。
- [ ] 实现 `admin_scope(args) -> dict`、`admin_history_where(scope) -> tuple`、`admin_competition_display(raw, profiles) -> str|None`。
- [ ] 让 `/admin`、`/admin/panel`、`/monitor`、`/api/admin/stats`、`/api/admin/quota` 复用范围和目录逻辑。
- [ ] 运行目标测试和全量 `unittest discover -s tests/probes`。
- [ ] 提交 `fix(admin): unify statistics scope`。

### Task 2: 生成与导出质量总览

**Files:** Modify `app.py`; Test `tests/probes/test_admin_operations.py`.

- [ ] 写失败测试：质量统计区分可交付成功、软警告、硬拦截、恢复成功，并可按赛事/时间范围聚合。
- [ ] 运行测试确认失败。
- [ ] 基于 `history`、`export_reviews`、`gen_failures` 提供 `/api/admin/quality-summary`。
- [ ] 在后台首页增加质量指标卡和弱项列表，数据为空时显示样本边界。
- [ ] 运行目标测试和全量探针。
- [ ] 提交 `feat(admin): add quality summary`。

### Task 3: Token 与成本工作台

**Files:** Modify `app.py`, `llm_usage_store.py`, active admin HTML/JS; Test `tests/probes/test_admin_operations.py`.

- [ ] 写失败测试：按日期、功能、模型、脱敏用户键聚合 Token；非法天数有界；无数据不报错。
- [ ] 运行测试确认失败。
- [ ] 扩展现有 `/api/admin/llm-usage` 返回按日和按功能聚合数据。
- [ ] 在后台增加 Token 用量、均值、异常高耗任务和额度预测展示。
- [ ] 运行目标测试、Node 语法检查和全量探针。
- [ ] 提交 `feat(admin): expose llm usage dashboard`。

### Task 4: 告警与服务诊断工作台

**Files:** Modify `app.py`; Test `tests/probes/test_admin_operations.py`.

- [ ] 写失败测试：额度、失败率、逾期工单和服务延迟产生稳定告警结构，确认状态可区分。
- [ ] 运行测试确认失败。
- [ ] 复用 `/api/admin/alert_status` 和 `/api/admin/diagnose`，增加告警详情、更新时间和去重键；页面顶部显示告警。
- [ ] 将诊断探测改为直接函数/健康检查，不用 `app.test_client()` 模拟生产请求。
- [ ] 运行目标测试和全量探针。
- [ ] 提交 `feat(admin): add operational alerts`。

### Task 5: 工单与审计完善

**Files:** Modify `app.py`; Test `tests/probes/test_admin_operations.py`.

- [ ] 写失败测试：工单状态变更记录操作者、时间、旧状态、新状态；只读账号不能变更。
- [ ] 运行测试确认失败。
- [ ] 增加优先级/负责人/处理期限字段或兼容元数据；补工单筛选和逾期统计；所有状态变更调用 `_audit_write`。
- [ ] 运行目标测试和全量探针。
- [ ] 提交 `feat(admin): improve issue workflow audit`。

### Task 6: 留存、导出与性能收口

**Files:** Modify `app.py`, `.gitignore`, admin assets; Test `tests/probes/test_admin_operations.py`.

- [ ] 写失败测试：留存任务只报告候选文件，不删除用户作品、数据库和最近回滚点；管理员导出字段脱敏。
- [ ] 运行测试确认失败。
- [ ] 增加仅管理员可执行的预览式留存报告、审计日志轮换提示、分页/按需图表加载；默认不自动删除业务数据。
- [ ] 运行全量探针、diff 检查、语法检查和 staging 回归。
- [ ] 提交 `chore(admin): add retention and performance guardrails`。

## Final Verification

- [ ] `python -m unittest discover -s tests/probes` 全部通过。
- [ ] `python -m py_compile app.py llm_usage_store.py` 通过。
- [ ] `git diff --check` 通过，工作树仅含本期文件。
- [ ] staging 服务 active、健康接口 200、四个统计入口口径一致。
- [ ] 生产更新前确认 systemd 工作目录、提交号、回滚点；更新后重复服务和页面核验。
