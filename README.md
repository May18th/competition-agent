# 科创赛事多智能体协同创作助手

面向大学生科创竞赛团队的端到端多智能体系统，基于 Flask + LangGraph 多智能体编排开发，实现赛事规则解析、创意同质化检测、申报书智能生成/优化、模拟评委评审全流程自动化。

## 功能特性
- 📋 赛事规则自动解析
- 🔍 创意同质化检测
- ✍️ 智能申报书生成/优化
- 📝 申报书诊断分析
- ⚖️ 模拟评委评审打分
- 📥 一键导出所有结果

## 版本区分
- **简洁版**：约1-2分钟快速出结果，申报书 2000~4000 字级，包含规则解析、同质化检测、申报书生成、评委点评
- **深度版**：约3-5分钟全面分析，申报书 12000 字级，并增加竞品/商业/风险分析、技术方案+实施计划、答辩问题预测、PPT大纲、可视化图表

## 运行环境
- Python 3.10+
- 依赖：langgraph、langchain、flask、chroma、pypdf、deepseek/openai SDK

## 快速启动
```bash
pip install -r requirements.txt
python run.py
# 访问 http://127.0.0.1:8080
```

## 目录结构
```
├── run.py                 # 本地启动入口
├── wsgi.py                # 云端 WSGI 入口
├── app.py                 # 兼容入口（实际实现位于 backend/）
├── backend/               # Flask 后端、智能体编排与后端模块
│   ├── app.py
│   └── competition_agents.py
├── frontend/              # 首页、静态资源与前端图标
│   ├── index.html
│   └── static/
├── data/                  # 比赛知识库原始资料
│   ├── iCAN大赛.txt
│   ├── 互联网+大赛.txt
│   ├── 挑战杯.txt
│   └── 国创项目.txt
├── knowledge_base/        # 结构化提示与范文库
├── scripts/               # 索引构建等维护脚本
├── tests/                 # 自动化测试与验收探针
├── docs/                  # 项目说明、交接记录与验收资料
└── uploads/               # 用户上传文件临时目录（本地运行时）
```

根目录保留少量兼容入口（如 `app.py`、`competition_agents.py`），以兼容现有 `run.py`、WSGI、Vercel 入口和历史测试；实际后端实现统一位于 `backend/`。`backend/` 下的本地数据库、缓存和归档目录已通过 `.gitignore` 排除。

## 配置
在环境变量中设置：
- `DEEPSEEK_API_KEY`：DeepSeek大模型密钥
- `CLAUDE_API_KEY`：火山引擎Claude密钥
