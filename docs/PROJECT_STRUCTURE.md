# 项目目录约定

根目录只保留项目入口与两份跨模块规范，运行代码和产物按职责归档：

| 目录 | 内容 | 运行约束 |
| --- | --- | --- |
| `frontend/` | 首页 HTML、CSS、浏览器端 JS、图标 | 静态资源由 Flask 直接提供 |
| `backend/` | Flask 入口、智能体、导出器、知识库与运行期数据 | `run.py` / `wsgi.py` 的工作目录固定为此目录 |
| `docs/architecture/` | 架构、接口、规范、安全和协作约定 | 只读文档 |
| `docs/handoff/` | 待办、交接、回执与历史协作记录 | 不参与运行 |
| `docs/evaluation/` | 评委视角、验收标准、质量与对标报告 | 发布前检查依据 |
| `docs/research/` | 官方赛事资料、研究资料、知识库搜集记录 | 不直接作为事实来源，需标注出处 |
| `docs/templates/` | 申报书、答辩、PPT 等参考模板 | 参考材料，不覆盖用户输入 |
| `docs/operations/` | 部署、运行、域名与操作说明 | 可能含环境信息，不提交密码 |
| `docs/archive/` | 旧版本、编码异常或无法归类的历史文件 | 归档，不进入生成链路 |
| `artifacts/reference/` | 可展示的样例 Word/PDF/PPT | 版权和来源需单独核验 |
| `artifacts/demo-video/` | 演示视频及配套截图 | 演示材料，不是运行依赖 |
| `artifacts/qa/` | 浏览器、云端和端到端检查产物 | 可清理、不可作为业务数据 |
| `artifacts/research/` | 临时网页抓取与研究快照 | 仅用于核查，不能直接训练或引用 |
| `artifacts/legacy-runtime/` | 旧入口遗留的生成/上传目录 | 当前入口不使用，迁移前保留 |
| `artifacts/releases/current/` | 当前可交付发布包与校验清单 | 只保留当前包和一个回滚包 |
| `artifacts/releases/archive/` | 历史发布包 | 只做回溯，不参与运行或部署 |
| `site_inspect/` | 远程页面检查临时快照 | 不进发布包，检查完成后移入研究归档 |
| `backend/archive/` | 已停用入口、远程探针和临时脚本 | 不参与运行，保留用于回滚取证 |
| `logs/` | 运行日志与调试日志 | 不写入源码目录 |
| `tests/` | 可重复的测试脚本与测试输出 | 测试不应修改生产数据 |

## 运行期路径

当前 Flask 入口将工作目录固定为 `backend/`，因此以下目录必须留在 `backend/`：

- `backend/competition.db`
- `backend/uploads/`
- `backend/generated/`
- `backend/tmp_export/`
- `backend/knowledge_base/`、`backend/data/`、`backend/chroma_db/`

整理目录时只能移动归档产物；如果要调整上述路径，必须同步修改 `run.py`、`wsgi.py`、导出接口和部署脚本，并做一次启动与导出回归。

发布包整理规则：`artifacts/releases/current/` 仅保留当前发布包及一个可回滚包；旧版本放入 `artifacts/releases/archive/`，不上传线上，也不进入运行时目录。
