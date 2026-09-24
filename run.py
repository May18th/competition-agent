"""启动脚本"""
from app import app

if __name__ == '__main__':
    print("=" * 60)
    print("🚀 科创赛事多智能体协同创作助手 - Web 版")
    print("=" * 60)
    print("📱 浏览器打开: http://127.0.0.1:8080")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8080, debug=False)
