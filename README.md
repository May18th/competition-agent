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
pip install -r requirements.txt
python run.py
# 访问 http://127.0.0.1:8080
```

## 目录结构
```
├── run.py                 # 启动入口
├── app.py                 # Flask后端+前端页面
├── competition_agents.py  # LangGraph多Agent工作流定义
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
