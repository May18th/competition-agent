# 科创赛事多智能体协同创作助手

面向大学生科创竞赛团队的端到端多Agent创作系统，基于LangGraph+Flask开发。

## 功能特性
- 📋 赛事规则自动解析
- 🔍 创意同质化检测
- ✍️ 智能申报书生成/优化
- 📝 申报书诊断分析
- ⚖️ 模拟评委评审打分
- 📥 一键导出所有结果

## 版本区分
- **简洁版**：30秒快速出结果，包含规则解析、同质化检测、精简申报书、评委点评
- **深度版**：1-2分钟全面分析，增加2000字完整申报书、竞品/商业/风险分析、答辩问题预测、PPT大纲、可视化图表

## 运行环境
- Python 3.10+
- 依赖：langgraph、langchain、flask、chroma、pypdf、deepseek/openai SDK

## 快速启动
```bash
pip install -r backend/requirements.txt
python backend/run.py
# 访问 http://127.0.0.1:8080
```

## 目录结构
```
├── frontend/              # 首页 HTML、CSS、浏览器端 JS 与静态资源
├── backend/               # Flask、智能体、导出器、知识库与运行期数据
├── docs/                  # 架构、赛事资料、验收、交接和模板
├── tests/                 # 可重复测试与探针
├── artifacts/             # 演示、参考样例、研究与 QA 产物
└── logs/                  # 运行与调试日志
```

完整归档规则见 [`docs/PROJECT_STRUCTURE.md`](docs/PROJECT_STRUCTURE.md)。运行时数据库、上传、生成和临时导出目录仍由 `backend/run.py` / `backend/wsgi.py` 固定在 `backend/`，整理文件不会改变服务路径。

本地发布到线上前请按 [`docs/operations/本地到线上同步.md`](docs/operations/本地到线上同步.md) 执行备份、白名单同步、平滑重载和接口回归；不要上传本地数据库或运行期目录。

## 配置
在环境变量中设置：
- `DEEPSEEK_API_KEY`：DeepSeek大模型密钥
- `CLAUDE_API_KEY`：火山引擎Claude密钥
