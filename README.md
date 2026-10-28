# 科创赛事多智能体协同创作助手

面向大学生科创竞赛团队的端到端多智能体系统，基于 Flask + LangGraph 多智能体编排，实现赛事规则解析、创意同质化检测、申报书生成/优化、模拟评委评审的全流程自动化。

## 目录

- `backend/`：Flask 应用、智能体编排与全部后端模块
  - `backend/assets/`：内容资产（赛事资料 `data/`、知识库 `knowledge_base/`、`训练库/`）
  - `backend/.data/`：运行产物（数据库、配额、上传、生成物、临时导出、日志），不入库
- `frontend/`：首页与静态资源（`index.html` + `static/`）
- `docs/`：项目说明、接口契约、边界与排障文档；`docs/assets/` 放交付样例
- `scripts/`：索引构建等维护脚本
- `tests/`：自动化测试；`tests/probes/` 为一次性探针与手工校验脚本

完整结构：

```
competition-agent
├─ backend/            后端源码（app.py / competition_agents.py 等）
│  ├─ assets/          内容资产
│  │  ├─ data/         赛事资料（按赛事分 txt）
│  │  ├─ knowledge_base/  结构化提示与范文库（JSON）
│  │  └─ 训练库/       成品样本归档
│  └─ .data/           运行产物（不入库）
│     ├─ competition.db / chat_history.db / quota.json
│     └─ uploads/ generated/ tmp_export/ logs/
├─ frontend/           前端源码
│  ├─ index.html
│  └─ static/          样式、脚本、图标
├─ docs/               说明、契约、边界文档
│  └─ assets/          申报书/说明书等交付样例
├─ scripts/            维护脚本
├─ tests/              测试与探针
├─ app.py              兼容入口（实际实现见 backend/app.py）
├─ run.py              本地启动入口
├─ wsgi.py             云端 WSGI 入口
└─ requirements.txt
```

**不要把临时日志、数据库、上传文件和生成产物放进版本库**：它们统一落在 `backend/.data/`，已由 `.gitignore` 整体排除，仅存在于本地。

根目录保留 9 个薄壳（`app.py`、`chat_store.py`、`competition_agents.py`、`deploy_guard.py`、`docx_render.py`、`export_quality.py`、`export_recovery.py`、`llm_usage_store.py`、`pptx_builder.py`），把导入转发到 `backend/` 同名模块，用于兼容 `run.py`、WSGI、Vercel 入口与历史脚本。

## 快速启动

```bash
pip install -r requirements.txt
python run.py
# 打开 http://127.0.0.1:8080
```

云端入口用 WSGI：

```bash
gunicorn wsgi:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 600
```

`workers` 必须为 1：异步任务状态保存在进程内字典，多进程会让「提交任务」和「轮询进度」落到不同进程。

## 验证

```bash
python -m unittest tests.test_repository_layout   # 目录布局与静态资源可访问
python tests/probes/_check_startup.py             # 启动块位置防回归
```

## 配置

环境变量：

- `DEEPSEEK_API_KEY`：DeepSeek 模型密钥
- `CLAUDE_API_KEY`：火山引擎 Claude 密钥

## 版本区分

- **简洁版**：约 1-2 分钟，申报书 2000-4000 字，含规则解析、同质化检测、申报书生成、评委点评
- **深度版**：约 3-5 分钟，申报书 12000 字级，增加竞品/商业/风险分析、技术方案与实施计划、答辩问题预测、PPT 大纲、可视化图表

## 协作

```bash
git pull
git checkout -b feature/your-topic
git add .
git commit -m "describe your change"
git push -u origin feature/your-topic
```

提交前请确认 `python -m unittest tests.test_repository_layout` 通过，且没有把数据库、日志或生成产物带进提交。

## 许可

MIT License，详见 [LICENSE](LICENSE)。引用或二次开发请保留版权声明。
