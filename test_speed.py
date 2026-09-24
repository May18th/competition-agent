import time
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

llm = ChatOpenAI(
    model="deepseek-chat",
    api_key="sk-cbeae9f2e4524efb88336393916109a0",
    base_url="https://api.deepseek.com",
    max_tokens=500
)

print("开始测试API调用时间...")
start = time.time()
response = llm.invoke([HumanMessage(content="写一段200字的项目简介：基于计算机视觉的教室智能签到系统")])
end = time.time()

print(f"一次API调用耗时：{end - start:.1f} 秒")
print(f"返回内容长度：{len(response.content)} 字")
