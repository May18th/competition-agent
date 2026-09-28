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
├── run.py                 # 启动入口
├── app.py                 # Flask后端+前端页面
├── competition_agents.py  # 多智能体工作流定义（LangGraph 编排，多Agent并行协作）
├── data/                  # 比赛知识库
│   ├── iCAN大赛.txt
│   ├── 互联网+大赛.txt
│   ├── 挑战杯.txt
│   └── 国创项目.txt
└── uploads/               # 用户上传文件临时目录
```

## 配置
在环境变量中设置：
- `DEEPSEEK_API_KEY`：DeepSeek大模型密钥
- `CLAUDE_API_KEY`：火山引擎Claude密钥
