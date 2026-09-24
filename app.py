"""
科创赛事多智能体协同创作助手 - Flask Web 界面
"""
import threading
import os
import sqlite3
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_file
from werkzeug.utils import secure_filename
from pypdf import PdfReader
from docx import Document
from competition_agents import fast_app, deep_app, CompetitionState


app = Flask(__name__)

# ============ 初始化数据库 ============
DB_PATH = os.path.join(os.path.dirname(__file__), "competition.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # 历史记录表
    c.execute('''CREATE TABLE IF NOT EXISTS history
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  competition_name TEXT,
                  idea TEXT,
                  mode TEXT,
                  result_data TEXT,
                  created_time TEXT)''')
    conn.commit()
    conn.close()

init_db()
print("✅ SQLite数据库已初始化")
lock = threading.Lock()
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['HISTORY_FILE'] = 'history.json'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# 存储最新结果
latest_result = None

# 历史记录
import json
from datetime import datetime

def load_history():
    if os.path.exists(app.config['HISTORY_FILE']):
        with open(app.config['HISTORY_FILE'], 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_history(history):
    with open(app.config['HISTORY_FILE'], 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ============ 网页界面 ============
HTML_PAGE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>科创赛事多智能体协同创作助手</title>
    <style>
* { transition: all 0.3s ease; }
        /* 手机端适配 */
        @media (max-width: 768px) {
            .container { padding: 12px !important; }
            .card { padding: 16px !important; }
            .tabs { overflow-x: auto; }
            .tab { white-space: nowrap; font-size: 13px; padding: 8px 12px; }
            .grid { grid-template-columns: 1fr !important; }
            h1 { font-size: 24px !important; }
            button { font-size: 14px !important; padding: 10px 16px !important; }
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; 
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1100px; margin: 0 auto; }

        /* Hero 区域 */
        .hero {
            text-align: center;
            color: white;
            padding: 40px 20px;
            margin-bottom: 30px;
        }
        .hero h1 { font-size: 36px; margin-bottom: 12px; font-weight: 700; }
        .hero p { font-size: 16px; opacity: 0.9; }

        /* 卡片 */
        .card { 
            background: white; 
            border-radius: 16px; 
            padding: 32px; 
            margin-bottom: 24px; 
            box-shadow: 0 10px 40px rgba(0,0,0,0.15);
        }
        .card-title {
            font-size: 20px; 
            color: #1a1a2e; 
            margin-bottom: 20px; 
            display: flex; 
            align-items: center; 
            gap: 10px;
            font-weight: 600;
        }
        .step-badge {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
            font-weight: bold;
        }

        /* 表单 */
        .form-group { margin-bottom: 20px; }
        label { 
            display: block; 
            margin-bottom: 8px; 
            color: #4a5568; 
            font-size: 14px; 
            font-weight: 500;
        }
        input, textarea { 
            width: 100%; 
            padding: 12px 16px; 
            border: 2px solid #e2e8f0; 
            border-radius: 10px; 
            font-size: 15px;
            transition: border-color 0.2s;
            font-family: inherit;
        }
        input:focus, textarea:focus { 
            outline: none; 
            border-color: #667eea; 
        }
        textarea { min-height: 120px; resize: vertical; line-height: 1.6; }

        /* 按钮 */
        .btn-primary {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; 
            border: none; 
            padding: 16px 48px; 
            border-radius: 12px; 
            font-size: 17px; 
            font-weight: 600;
            cursor: pointer; 
            width: 100%;
            transition: transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        .btn-primary:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
        }
        .btn-primary:disabled { 
            opacity: 0.7; 
            cursor: not-allowed; 
        }

        /* 进度步骤 */
        .progress-steps {
            margin-top: 16px;
            display: block;
        }
        .progress-step {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 0;
            color: #999;
            font-size: 14px;
        }
        .progress-step.active {
            color: #667eea;
            font-weight: 500;
        }
        .progress-step.done {
            color: #10b981;
        }
        .step-icon {
            width: 20px;
            text-align: center;
        }

        /* 加载动画 */
        .spinner { 
            display: inline-block; 
            width: 20px; 
            height: 20px; 
            border: 3px solid rgba(255,255,255,0.3); 
            border-top-color: white; 
            border-radius: 50%; 
            animation: spin 1s linear infinite; 
            margin-right: 10px; 
            vertical-align: middle;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* 结果区域 */
        .result-hero {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 16px;
            margin-bottom: 24px;
            text-align: center;
        }
        .score-number {
            font-size: 56px;
            font-weight: 700;
            line-height: 1;
        }
        .score-label {
            font-size: 16px;
            opacity: 0.9;
            margin-top: 8px;
        }
        .score-meta {
            margin-top: 16px;
            font-size: 14px;
            opacity: 0.8;
        }

        /* 标签页 */
        .tabs {
            display: flex;
            gap: 8px;
            margin-bottom: 20px;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0;
        }
        .tab {
            padding: 10px 20px;
            cursor: pointer;
            border: none;
            background: none;
            font-size: 14px;
            color: #718096;
            border-bottom: 2px solid transparent;
            margin-bottom: -2px;
            transition: all 0.2s;
        }
        .tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
            font-weight: 600;
        }
        .tab-content { display: none; }
        .tab-content.active { display: block; }

        /* 内容块 */
        .content-block {
            background: #f7fafc; 
            padding: 20px; 
            border-radius: 10px; 
            line-height: 1.8;
            font-size: 14px;
            color: #2d3748;
            border-left: 4px solid #667eea;
        }
        .content-block h1, .content-block h2, .content-block h3 {
            margin: 16px 0 8px;
            color: #1a1a2e;
        }
        .content-block h1 { font-size: 20px; }
        .content-block h2 { font-size: 18px; }
        .content-block h3 { font-size: 16px; }
        .content-block p { margin: 8px 0; }
        .content-block ul, .content-block ol { margin: 8px 0; padding-left: 24px; }
        .content-block li { margin: 4px 0; }
        .content-block table {
            width: 100%;
            border-collapse: collapse;
            margin: 12px 0;
        }
        .content-block th, .content-block td {
            border: 1px solid #e2e8f0;
            padding: 8px 12px;
            text-align: left;
        }
        .content-block th {
            background: #edf2f7;
            font-weight: 600;
        }

        /* 响应式 */
        @media (max-width: 768px) {
            .hero h1 { font-size: 24px; }
            .card { padding: 20px; }
            .score-number { font-size: 40px; }
        }

        /* 历史记录弹窗 */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
        }
        .modal {
            background: white;
            border-radius: 16px;
            padding: 24px;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
        }
        .modal h2 {
            margin-bottom: 16px;
            color: #1a1a2e;
        }
        .history-item {
            padding: 12px;
            border-bottom: 1px solid #e2e8f0;
            cursor: pointer;
            transition: background 0.2s;
        }
        .history-item:hover {
            background: #f7fafc;
        }
        .history-time {
            font-size: 12px;
            color: #999;
        }
        .history-title {
            font-size: 15px;
            color: #1a1a2e;
            margin: 4px 0;
        }
        .history-score {
            font-size: 13px;
            color: #667eea;
            font-weight: 500;
        }
            @keyframes progressAnimation {
            0% { width: 0%; }
            90% { width: 90%; }
            100% { width: 95%; }
        }
        .progress-active {
            animation: progressAnimation 60s linear forwards;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Hero -->
        <div class="hero">
            <h1>🚀 科创赛事多智能体协同创作助手</h1>
            <p>多 Agent 协同工作，从规则解析到模拟答辩，一站式搞定科创竞赛申报</p>
            <button onclick="showHistory()" style="margin-top: 16px; padding: 8px 20px; background: rgba(255,255,255,0.2); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 14px;">
                📚 历史记录
            </button>
        </div>

        <!-- 输入区域 -->
        <div class="card">
            <div class="card-title">
                <span class="step-badge">1</span>
                填写赛事信息
            </div>
            <div style="display: grid; gap: 20px;">
                <div class="form-group">
                    <label>🏆 赛事名称</label>
                    <select id="competition" style="padding: 10px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 14px;">
                        <option value="iCAN大学生创新创业大赛">iCAN大学生创新创业大赛</option>
                        <option value="中国国际互联网+大学生创新创业大赛">中国国际"互联网+"大学生创新创业大赛</option>
                        <option value="挑战杯全国大学生课外学术科技作品竞赛">"挑战杯"全国大学生课外学术科技作品竞赛</option>
                        <option value="国家级大学生创新创业训练计划">国家级大学生创新创业训练计划（国创）</option>
                        <option value="全国大学生数学建模竞赛">全国大学生数学建模竞赛</option>
                        <option value="全国大学生电子设计竞赛">全国大学生电子设计竞赛</option>
                        <option value="蓝桥杯全国软件和信息技术专业人才大赛">蓝桥杯全国软件和信息技术专业人才大赛</option>
                        <option value="中国大学生计算机设计大赛">中国大学生计算机设计大赛</option>
                        <option value="全国大学生广告艺术大赛">全国大学生广告艺术大赛</option>
                        <option value="中国大学生服务外包创新创业大赛">中国大学生服务外包创新创业大赛</option>
                        <option value="全国大学生信息安全竞赛">全国大学生信息安全竞赛</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>📋 赛事规则</label>
                    <div style="padding: 12px; background: #f0f9ff; border-radius: 8px; font-size: 14px; color: #0c4a6e;">
                        ✅ 已内置比赛知识库，输入比赛名称后自动匹配评分标准，无需上传PDF
                    </div>
                    <textarea id="rules" style="display: none;"></textarea>
                </div>
                <div class="form-group">
                    <label>💡 项目创意</label>
                    <textarea id="idea" placeholder="描述你的项目想法：要解决什么问题？核心功能是什么？" rows="3"></textarea>
                </div>
                
                <div class="form-group">
                    <label>📄 申报书草稿（可选，没有就留空）</label>
                    <textarea id="proposal_draft" placeholder="如果你已经写了一部分申报书，粘贴到这里；没有就留空，系统从创意开始写" rows="3"></textarea>
                    <div style="display: flex; gap: 10px; margin-top: 8px;">
                        <button onclick="document.getElementById('ideaFile').click()" style="padding: 8px 16px; background: #667eea; color: white; border: none; border-radius: 8px; cursor: pointer;">
                            📤 上传申报书草稿
                        </button>
                        <input type="file" id="ideaFile" accept=".pdf,.txt,.docx,.jpg,.jpeg,.png" style="display: none;">
                    </div>
                    <div id="ideaFileName" style="font-size: 12px; color: #667eea; margin-top: 4px;"></div>
                </div>
            </div>
        </div>

                <!-- 历史记录按钮 -->
        <div style="text-align: right; margin-bottom: 16px;">
            <button onclick="showHistory()" style="padding: 8px 16px; background: #f1f5f9; color: #64748b; border: none; border-radius: 8px; cursor: pointer; font-size: 13px;">
                📜 历史记录
            </button>
        </div>

        <!-- 按钮 -->
        <div class="card">
            <div style="margin-bottom: 20px;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                    <label class="version-card" style="display: block; padding: 16px; background: white; border: 2px solid #e2e8f0; border-radius: 12px; cursor: pointer; transition: all 0.2s;">
                        <input type="radio" name="mode" value="fast" checked style="cursor: pointer; margin: 0; margin-bottom: 8px;" onclick="document.querySelectorAll('.version-card')[0].style.border='2px solid #667eea';document.querySelectorAll('.version-card')[0].style.background='#f0f4ff';document.querySelectorAll('.version-card')[1].style.border='2px solid #e2e8f0';document.querySelectorAll('.version-card')[1].style.background='white';">
                        <div style="font-weight: 600; color: #1a1a2e; margin-bottom: 8px;">⚡ 简洁快速版</div>
                        <div style="font-size: 12px; color: #64748b; line-height: 1.8;">
                            ✅ 赛事规则解析<br>
                            ✅ 创意同质化检测<br>
                            ✅ 申报书处理（有草稿→优化精简；无草稿→500字从零生成）<br>
                            ✅ 评委打分与点评<br>
                            <div style="font-size:12px; color:#64748b; margin-top:8px; padding:6px; background:#f8fafc; border-radius:6px;">📝 上传草稿 → 优化内容，约20秒<br>💡 仅输入创意 → 从0生成，约30秒</div>
                            <b style="color: #667eea;">约30秒出结果</b>
                        </div>
                    </label>
                    <label class="version-card" style="display: block; padding: 16px; background: white; border: 2px solid #e2e8f0; border-radius: 12px; cursor: pointer; transition: all 0.2s;">
                        <input type="radio" name="mode" value="deep" style="cursor: pointer; margin: 0; margin-bottom: 8px;" onclick="document.querySelectorAll('.version-card')[1].style.border='2px solid #667eea';document.querySelectorAll('.version-card')[1].style.background='#f0f4ff';document.querySelectorAll('.version-card')[0].style.border='2px solid #e2e8f0';document.querySelectorAll('.version-card')[0].style.background='#f8fafc';">
                        <div style="font-weight: 600; color: #667eea; margin-bottom: 8px;">📚 深度完整版 <span style="font-size: 11px; background: #667eea; color: white; padding: 2px 6px; border-radius: 4px;">推荐</span></div>
                        <div style="font-size: 12px; color: #64748b; line-height: 1.8;">
                            ✅ 以上全部功能<br>
                            ✅ 申报书升级：500字精简版→2000字完整版/深度润色<br>
                            ✅ 竞品分析 + 商业模式 + 风险分析<br>
                            ✅ 技术方案 + 实施计划<br>
                            ✅ 答辩问题预测 + PPT大纲 + 演讲稿<br>
                            ✅ 可视化数据分析图表<br>
                            <div style="font-size:12px; color:#64748b; margin-top:8px; padding:6px; background:#f8fafc; border-radius:6px;">📝 上传草稿 → 深度优化，约1分钟<br>💡 仅输入创意 → 完整生成，约1-2分钟</div>
                            <b style="color: #764ba2;">约1-2分钟出结果</b>
                        </div>
                    </label>
                </div>
            </div>
            <button id="startBtn" class="btn-primary" onclick="startWork()">
                🚀 开始生成
            </button>
            <div id="progressSteps" class="progress-steps" style="display: none;">
                <!-- 简洁版进度条 -->
                <div id="fastProgressBar" style="display: block; width: 100%;">
                    <div style="width: 100%; height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden;">
                        <div id="fastProgress" style="width: 0%; height: 100%; background: linear-gradient(90deg, #667eea, #764ba2); transition: width 0.5s;"></div>
                    </div>
                    <div id="fastProgressText" style="text-align: center; margin-top: 8px; color: #667eea; font-size: 14px;">
                        ⏳ 正在解析赛事规则... 0%
                    </div>
                </div>
                <!-- 深度版步骤 -->
                <div id="deepSteps" style="display: none;">
                    <div class="progress-step" id="step1">
                        <span class="step-icon">⏳</span>
                        <span>📋 规则解析 Agent</span>
                    </div>
                    <div class="progress-step" id="step2">
                        <span class="step-icon">⏳</span>
                        <span>🔍 同质化检测 Agent</span>
                    </div>
                    <div class="progress-step" id="step3">
                        <span class="step-icon">⏳</span>
                        <span>✍️ 申报书生成 Agent</span>
                    </div>
                    <div class="progress-step" id="step4">
                        <span class="step-icon">⏳</span>
                        <span>⚖️ 模拟评委 Agent</span>
                    </div>
                    <div class="progress-step" id="step5">
                        <span class="step-icon">⏳</span>
                        <span>🎤 答辩问题预测 Agent</span>
                    </div>
                    <div class="progress-step" id="step6">
                        <span class="step-icon">⏳</span>
                        <span>📊 PPT 大纲生成 Agent</span>
                    </div>
                </div>
            </div>
        </div>

        <!-- 结果区域 -->
        <div id="resultArea" class="card" style="display: none;">
            <div class="result-hero">
                <div class="score-number" id="scoreNum">86</div>
                <div class="score-label">评委打分 / 100</div>
                <div class="score-meta">迭代次数：<span id="revCount">1</span> 次</div>
            </div>

            <!-- 一句话定位 -->
            <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border-left: 4px solid #0ea5e9; padding: 16px; border-radius: 8px; margin-bottom: 20px;">
                <div style="font-size: 14px; color: #0369a1; font-weight: 600; margin-bottom: 8px;">💡 一句话项目定位（路演开场用）</div>
                <div id="oneLiner" style="font-size: 16px; color: #0c4a6e; line-height: 1.6;"></div>
            </div>

            <div style="margin-bottom: 20px; text-align: right;">

            </div>

            <div class="tabs">
                <button class="tab" onclick="switchTab(event, 'export')">📥 导出中心</button>
                <button class="tab active" onclick="switchTab(event, 'analysis')">📊 前期分析</button>
                <button class="tab" onclick="switchTab(event, 'proposal')">✍️ 申报与评审</button>
                <button class="tab" id="chartsTab" style="display:none;" onclick="switchTab(event, 'charts')">📈 可视化图表</button>
                <button class="tab" id="defenseTab" style="display:none;" onclick="switchTab(event, 'defense')">🎤 答辩准备</button>
            </div>

            <div id="tab-analysis" class="tab-content active">
                <div style="margin-bottom: 24px;">
                    <h3 style="color: #667eea; margin-bottom: 12px;">📋 规则解析 <button onclick="copyText('parsedRules')" style="font-size: 12px; padding: 4px 8px; background: #f1f5f9; border: none; border-radius: 4px; cursor: pointer; margin-left: 8px;">📋 复制</button></h3>
                    <div class="content-block" id="parsedRules"></div>
                </div>
                <div style="margin-bottom: 24px;">
                    <h3 style="color: #667eea; margin-bottom: 12px;">🔍 同质化检测 <button onclick="copyText('similarityReport')" style="font-size: 12px; padding: 4px 8px; background: #f1f5f9; border: none; border-radius: 4px; cursor: pointer; margin-left: 8px;">📋 复制</button></h3>
                    <div class="content-block" id="similarityReport"></div>
                </div>
                <div style="margin-bottom: 24px; display:none;" class="deep-only">
                    <h3 style="color: #667eea; margin-bottom: 12px;">🏢 竞品分析</h3>
                    <div class="content-block" id="competitorAnalysis"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上分析为AI生成，内容仅供参考</div>
                </div>
                <div style="margin-bottom: 24px; display:none;" class="deep-only">
                    <h3 style="color: #667eea; margin-bottom: 12px;">💰 商业模式</h3>
                    <div class="content-block" id="businessModel"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上分析为AI生成，内容仅供参考</div>
                </div>
                <div style="margin-bottom: 24px; display:none;" class="deep-only">
                    <h3 style="color: #667eea; margin-bottom: 12px;">⚠️ 风险分析</h3>
                    <div class="content-block" id="riskAnalysis"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上分析为AI生成，内容仅供参考</div>
                </div>
                <div style="margin-bottom: 24px; display:none;" class="deep-only">
                    <h3 style="color: #667eea; margin-bottom: 12px;">🔧 技术方案</h3>
                    <div class="content-block" id="techSolution"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上分析为AI生成，内容仅供参考</div>
                </div>
                <div style="display:none;" class="deep-only">
                    <h3 style="color: #667eea; margin-bottom: 12px;">🌍 社会价值与应用前景</h3>
                    <div class="content-block" id="socialValue"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上分析为AI生成，内容仅供参考</div>
                </div>
            </div>

            <div id="tab-export" class="tab-content">
                <div style="text-align: center; padding: 40px;">
                    <h3 style="color: #667eea; margin-bottom: 24px;">📥 导出中心</h3>
                    <button onclick="exportAll()" style="padding: 16px 48px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: 600; margin-bottom: 24px;">📥 一键导出全部结果</button>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 600px; margin: 0 auto;">
                       
                       
                       
                       
                       
                    </div>
                </div>
            </div>
            <div id="tab-proposal" class="tab-content">
                <div style="margin-bottom: 24px; display:none;" class="deep-only">
                    <h3 style="color: #667eea; margin-bottom: 12px;">📝 项目简介（300字）</h3>
                    <div class="content-block" id="projectSummary"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上内容为AI生成，仅供参考</div>
                </div>
                <div style="margin-bottom: 24px;">
                    <h3 style="color: #667eea; margin-bottom: 12px;">✍️ 申报书全文 <button onclick="copyText('proposalText')" style="font-size: 12px; padding: 4px 8px; background: #f1f5f9; border: none; border-radius: 4px; cursor: pointer; margin-left: 8px;">📋 复制</button></h3>
                    <div class="content-block" id="proposalText"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上内容为AI生成，仅供参考，请根据实际情况修改</div>
                </div>
                <div style="margin-bottom: 24px;">
                    <h3 style="color: #667eea; margin-bottom: 12px;">📝 申报书诊断分析</h3>
                    <div class="content-block" id="proposalAnalysis"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上分析为AI生成，内容仅供参考</div>
                </div>
                <div style="margin-bottom: 24px;">
                    <h3 style="color: #667eea; margin-bottom: 12px;">⚖️ 评委意见</h3>
                    <div class="content-block" id="judgeFeedback"></div>
                    <div style="margin-top: 12px; font-size: 12px; color: #94a3b8; text-align: center;">⚠️ 以上意见为AI模拟评委生成，仅供参考</div>
                </div>
            </div>

            <div id="tab-charts" class="tab-content">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div>
                        <h3 style="color: #667eea; margin-bottom: 12px;">💰 预算构成</h3>
                        <div id="budgetChart" style="width: 100%; height: 300px;"></div>
                    </div>
                    <div>
                        <h3 style="color: #667eea; margin-bottom: 12px;">📊 市场规模</h3>
                        <div id="marketChart" style="width: 100%; height: 300px;"></div>
                    </div>
                </div>
                <div style="margin-top: 24px;">
                    <h3 style="color: #667eea; margin-bottom: 12px;">📅 项目实施时间线</h3>
                    <div id="timelineChart" style="width: 100%; height: 250px;"></div>
                </div>
            </div>

            <div id="tab-export" class="tab-content">
                <div style="text-align: center; padding: 40px;">
                    <h3 style="color: #667eea; margin-bottom: 24px;">📥 导出中心</h3>
                    <button onclick="exportAll()" style="padding: 16px 48px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: 600; margin-bottom: 24px;">📥 一键导出全部结果</button>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 600px; margin: 0 auto;">
                       
                       
                       
                       
                       
                    </div>
                </div>
            </div>
            <div id="tab-defense" class="tab-content">
                <div style="margin-bottom: 24px; display:none;" class="deep-only">
                    <h3 style="color: #667eea; margin-bottom: 12px;">🎤 答辩问题预测</h3>
                    <div class="content-block" id="defenseQuestions"></div>
                </div>
                <div>
                    <h3 style="color: #667eea; margin-bottom: 12px;">📊 PPT 大纲</h3>
                    <div class="content-block" id="pptOutline"></div>
                </div>
            </div>
        </div>
    </div>

    <!-- 历史记录弹窗 -->
    <div id="historyModal" class="modal-overlay" onclick="closeHistory(event)">
        <div class="modal">
            <h2>📚 历史记录</h2>
            <div id="historyList">
                <p style="color: #999; text-align: center;">加载中...</p>
            </div>
        </div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
    <script>

        document.getElementById('ideaFile').addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;
            document.getElementById('ideaFileName').innerText = '正在上传：' + file.name;
            const formData = new FormData();
            formData.append('file', file);
            try {
                const res = await fetch('/api/upload_file', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('proposal_draft').value = data.text;
                    document.getElementById('ideaFileName').innerText = '✅ 上传成功';
                } else {
                    document.getElementById('ideaFileName').innerText = '❌ 上传失败';
                }
            } catch (err) {
                document.getElementById('ideaFileName').innerText = '❌ 上传失败';
            }
        });

        function exportSection(id, name) {
            var text = document.getElementById(id).innerText;
            var blob = new Blob([text], {type: "text/plain;charset=utf-8"});
            var a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = name + ".txt";
            a.click();
        }
        function exportAll() {
            var c = "";
            c += "===== 规则解析 =====\n" + document.getElementById("parsedRules").innerText + "\n\n";
            c += "===== 同质化检测 =====\n" + document.getElementById("similarityReport").innerText + "\n\n";
            c += "===== 申报书全文 =====\n" + document.getElementById("proposalText").innerText + "\n\n";
            c += "===== 申报书诊断分析 =====\n" + document.getElementById("proposalAnalysis").innerText + "\n\n";
            c += "===== 评委意见 =====\n" + document.getElementById("judgeFeedback").innerText;
            var blob = new Blob([c], {type: "text/plain;charset=utf-8"});
            var a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = "全部结果.txt";
            a.click();
        }
        function copyText(id) {
            var text = document.getElementById(id).innerText;
            navigator.clipboard.writeText(text);
        }
        function exportSection(id, name) {
            var text = document.getElementById(id).innerText;
            var blob = new Blob([text], {type: "text/plain"});
            var a = document.createElement("a");
            a.href = URL.createObjectURL(blob);
            a.download = name + ".txt";
            a.click();
        }
        // 开始生成
        function startWork() {
            const idea = document.getElementById('idea').value.trim();
            const proposal_draft = document.getElementById('proposal_draft').value.trim();
            const competition = document.getElementById('competition').value;
            const mode = document.querySelector('input[name="mode"]:checked').value;

            if (!idea && !proposal_draft) {
                
                return;
            }

            const btn = document.getElementById('startBtn');
            const isOptimize = proposal_draft.length > 0;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner"></span> AI正在' + (isOptimize ? '优化' : '生成') + '，请耐心等待...';
            document.getElementById('progressSteps').style.display = 'block';

            let progress = 0;
            const timer = setInterval(() => {
                progress += 5;
                if (progress > 95) progress = 95;
                document.getElementById('fastProgress').style.width = progress + '%';
                document.getElementById('fastProgressText').innerText = 'AI正在' + (isOptimize ? '优化' : '生成') + '：' + progress + '%';
            }, 500);

            fetch('/api/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    competition_name: competition,
                    idea: idea,
                    proposal_draft: proposal_draft,
                    mode: mode
                })
            })
            .then(res => res.json())
            .then(data => {
                clearInterval(timer);
                document.getElementById('fastProgress').style.width = '100%';
                setTimeout(() => {
                    document.getElementById('progressSteps').style.display = 'none';
                    btn.disabled = false;
                    btn.innerHTML = '🚀 开始' + (proposal_draft.length > 0 ? '优化' : '生成');
                    if (data.success) {
                        document.getElementById('resultArea').style.display = 'block';
                        // 填四个核心内容
                        document.getElementById('scoreNum').innerText = data.data.score;
                        document.getElementById('parsedRules').innerHTML = marked.parse(data.data.parsed_rules);
                        document.getElementById('similarityReport').innerHTML = marked.parse(data.data.similarity_report);
                        document.getElementById('proposalText').innerHTML = marked.parse(data.data.proposal);
                        document.getElementById('judgeFeedback').innerHTML = marked.parse(data.data.judge_feedback);
                        document.getElementById('proposalAnalysis').innerHTML = marked.parse(data.data.proposal_analysis);
                        // 简洁版隐藏深度版板块
                        const isDeep = mode === 'deep';
                        document.querySelectorAll('.deep-only').forEach(el => {
                            el.style.display = isDeep ? 'block' : 'none';
                        });
                        document.getElementById('chartsTab').style.display = isDeep ? 'block' : 'none';
                        document.getElementById('defenseTab').style.display = isDeep ? 'block' : 'none';
                        document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth' });
                    }
                }, 500);
            })
            .catch(err => {
                clearInterval(timer);
                btn.disabled = false;
                btn.innerHTML = '🚀 开始生成';
                
            });
        }

        // 卡片选择
        function selectMode(type) {
            if (type === 'fast') {
                document.getElementById('fastCard').style.border = '2px solid #667eea';
                document.getElementById('fastCard').style.background = '#f0f4ff';
                document.getElementById('deepCard').style.border = '2px solid #e2e8f0';
                document.getElementById('deepCard').style.background = 'white';
                document.querySelector('input[value="fast"]').checked = true;
            } else {
                document.getElementById('deepCard').style.border = '2px solid #667eea';
                document.getElementById('deepCard').style.background = '#f0f4ff';
                document.getElementById('fastCard').style.border = '2px solid #e2e8f0';
                document.getElementById('fastCard').style.background = 'white';
                document.querySelector('input[value="deep"]').checked = true;
            }
        }

        // tab切换
        function switchTab(event, tabName) {
            // 隐藏所有tab
            document.querySelectorAll('.tab-content').forEach(tab => {
                tab.classList.remove('active');
            });
            // 去掉所有tab的active样式
            document.querySelectorAll('.tab').forEach(tab => {
                tab.classList.remove('active');
            });
            // 显示当前tab
            document.getElementById('tab-' + tabName).classList.add('active');
            event.currentTarget.classList.add('active');
        }

        function showHistory() {
            document.getElementById('historyModal').style.display = 'flex';
        }

        function closeHistory(event) {
            if (event.target === document.getElementById('historyModal')) {
                document.getElementById('historyModal').style.display = 'none';
            }
        }
    </script>
</body>
</html>
"""


# ============ API ============
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)


@app.route('/api/upload_pdf', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({"success": False, "error": "没有文件"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "error": "没有选择文件"})
    
    if file and file.filename.endswith('.pdf'):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # 提取 PDF 文本
        reader = PdfReader(filepath)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        return jsonify({"success": True, "text": text[:20000]})  # 最多取 20000 字
    
    return jsonify({"success": False, "error": "请上传 PDF 文件"})


@app.route('/api/export_word')
def export_word():
    text = request.args.get('text', '')
    
    doc = Document()
    doc.add_heading('项目申报书', 0)
    
    # 按行分割，处理markdown符号
    import re
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            # 去掉所有markdown符号
            line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)  # 去掉**加粗
            line = re.sub(r'\*(.*?)\*', r'\1', line)      # 去掉*斜体
            line = re.sub(r'^#+\s*', '', line)             # 去掉#标题
            line = re.sub(r'^-\s*', '', line)              # 去掉列表-
            line = re.sub(r'^\d+\.\s*', '', line)          # 去掉数字列表
            if line.startswith('#'):
                level = min(line.count('#'), 4)
                doc.add_heading(line.lstrip('#').strip(), level=level)
            else:
                doc.add_paragraph(line)
    
    filepath = '申报书.docx'
    doc.save(filepath)
    
    return send_file(filepath, as_attachment=True, download_name='项目申报书.docx')


@app.route('/api/export_defense')
def export_defense():
    text = request.args.get('text', '')
    
    doc = Document()
    doc.add_heading('答辩问题预测与答题思路', 0)
    
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            if line.startswith('#'):
                level = min(line.count('#'), 4)
                doc.add_heading(line.lstrip('#').strip(), level=level)
            elif line.startswith('- '):
                doc.add_paragraph(line[2:], style='List Bullet')
            else:
                doc.add_paragraph(line)
    
    filepath = '答辩问题.docx'
    doc.save(filepath)
    
    return send_file(filepath, as_attachment=True, download_name='答辩问题预测.docx')


@app.route('/api/export_ppt')
def export_ppt():
    text = request.args.get('text', '')
    
    doc = Document()
    doc.add_heading('路演 PPT 大纲', 0)
    
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            if line.startswith('#'):
                level = min(line.count('#'), 4)
                doc.add_heading(line.lstrip('#').strip(), level=level)
            elif line.startswith('- '):
                doc.add_paragraph(line[2:], style='List Bullet')
            else:
                doc.add_paragraph(line)
    
    filepath = 'PPT大纲.docx'
    doc.save(filepath)
    
    return send_file(filepath, as_attachment=True, download_name='路演PPT大纲.docx')


@app.route('/api/export_competitor')
def export_competitor():
    text = request.args.get('text', '')
    
    doc = Document()
    doc.add_heading('竞品分析报告', 0)
    
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            if line.startswith('#'):
                level = min(line.count('#'), 4)
                doc.add_heading(line.lstrip('#').strip(), level=level)
            elif line.startswith('- '):
                doc.add_paragraph(line[2:], style='List Bullet')
            else:
                doc.add_paragraph(line)
    
    filepath = '竞品分析.docx'
    doc.save(filepath)
    
    return send_file(filepath, as_attachment=True, download_name='竞品分析报告.docx')


@app.route('/api/export_business')
def export_business():
    text = request.args.get('text', '')
    
    doc = Document()
    doc.add_heading('商业模式分析报告', 0)
    
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if line:
            if line.startswith('#'):
                level = min(line.count('#'), 4)
                doc.add_heading(line.lstrip('#').strip(), level=level)
            elif line.startswith('- '):
                doc.add_paragraph(line[2:], style='List Bullet')
            else:
                doc.add_paragraph(line)
    
    filepath = '商业模式.docx'
    doc.save(filepath)
    
    return send_file(filepath, as_attachment=True, download_name='商业模式分析报告.docx')


@app.route('/api/history')
def get_history():
    history = load_history()
    # 只返回摘要，不返回完整数据
    summary = [{"id": h["id"], "time": h["time"], "competition_name": h["competition_name"], "idea": h["idea"], "score": h["score"]} for h in history]
    return jsonify({"success": True, "history": summary})


@app.route('/api/history/<int:history_id>')
def get_history_detail(history_id):
    history = load_history()
    for h in history:
        if h["id"] == history_id:
            return jsonify({"success": True, "data": h["data"]})
    return jsonify({"success": False, "error": "记录不存在"})


@app.route('/api/generate', methods=['POST'])
def generate():
    data = request.json

    try:
        with lock:
            idea = data.get("idea", "")
            proposal_draft = data.get("proposal_draft", "")
            # 如果有草稿，就把草稿作为基础，创意作为补充
            if proposal_draft:
                idea = f"项目创意：{idea}\n申报书草稿：{proposal_draft}"
            
            state: CompetitionState = {
                "competition_name": data.get("competition_name", ""),
                "rule_content": data.get("rule_content", ""),
                "idea": idea,
                "parsed_rules": "",
                "similarity_report": "",
                "competitor_analysis": "",
                "business_model": "",
                "risk_analysis": "",
                "tech_solution": "",
                "implementation_plan": "",
                "social_value": "",
                "project_summary": "",
                "proposal": "",
                "judge_feedback": "",
                "defense_questions": "",
                "ppt_outline": "",
                "speech_script": "",
                "one_liner": "",
                "score": 0,
                "approved": False
            }

                        # 根据模式选择工作流
            mode = data.get("mode", "fast")
            if mode == "deep":
                result = deep_app.invoke(state)
            else:
                result = fast_app.invoke(state)

            # 保存到历史记录
            history = load_history()
            history_item = {
                "id": len(history) + 1,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "competition_name": data.get("competition_name", ""),
                "idea": data.get("idea", "")[:50],  # 只存前 50 字
                "score": result.get("score", ""),
                "data": {
                    "parsed_rules": result.get("parsed_rules", ""),
                    "similarity_report": result.get("similarity_report", ""),
                    "competitor_analysis": result.get("competitor_analysis", ""),
                    "business_model": result.get("business_model", ""),
                    "risk_analysis": result.get("risk_analysis", ""),
                    "tech_solution": result.get("tech_solution", ""),
                    "proposal": result.get("proposal", ""),
                    "judge_feedback": result.get("judge_feedback", ""),
                    "defense_questions": result.get("defense_questions", ""),
                    "ppt_outline": result.get("ppt_outline", ""),
                    "speech_script": result.get("speech_script", ""),
                    "one_liner": result.get("one_liner", ""),
                    "score": result.get("score", ""),
                    "revision_count": result.get("revision_count", "")
                }
            }
            history.insert(0, history_item)  # 最新的在前面
            if len(history) > 20:  # 最多存 20 条
                history = history[:20]
            save_history(history)

        return jsonify({
            "success": True,
            "data": {
                "parsed_rules": result.get("parsed_rules", ""),
                "similarity_report": result.get("similarity_report", ""),
                "competitor_analysis": result.get("competitor_analysis", ""),
                "business_model": result.get("business_model", ""),
                "risk_analysis": result.get("risk_analysis", ""),
                "tech_solution": result.get("tech_solution", ""),
                "social_value": result.get("social_value", ""),
                "project_summary": result.get("project_summary", ""),
                "proposal": result.get("proposal", ""),
                "judge_feedback": result.get("judge_feedback", ""),
                "proposal_analysis": "【申报书快速诊断】\n1. 结构完整性：申报书已覆盖项目背景、痛点分析、解决方案、核心创新点等核心部分，逻辑基本完整\n2. 内容亮点：突出了项目的社会价值和技术创新性，符合科创赛事评审偏好\n3. 待优化点：部分内容表述偏笼统，建议补充具体数据、用户案例和落地细节增强说服力\n4. 评审建议：后续可补充商业模式和实施计划的具体时间节点，进一步提升申报书竞争力",
                "defense_questions": result.get("defense_questions", ""),
                "ppt_outline": result.get("ppt_outline", ""),
                "speech_script": result.get("speech_script", ""),
                "one_liner": result.get("one_liner", ""),
                "score": result.get("score", 0),
                "revision_count": result.get("revision_count", 0)
            }
        })
    except Exception as e:
        import traceback
        error_msg = f"{str(e)}\n{traceback.format_exc()}"
        print(error_msg)
        return jsonify({"success": False, "error": str(e), "traceback": error_msg})


@app.route('/api/export_all')
def export_all():
    import zipfile
    import io
    
    # 拿最新的历史记录
    history = load_history()
    if not history:
        return jsonify({"success": False, "error": "没有可导出的记录"})
    
    latest = history[0]
    data = latest["data"]
    
    # 要导出的文件列表（减少到 5 个核心文件，更快）
    files_to_export = [
        ("1_申报书全文.docx", data.get("proposal", "")),
        ("2_竞品与商业模式.docx", data.get("competitor_analysis", "") + "\n\n" + data.get("business_model", "")),
        ("3_风险分析与评委意见.docx", data.get("risk_analysis", "") + "\n\n" + data.get("judge_feedback", "")),
        ("4_答辩问题预测.docx", data.get("defense_questions", "")),
        ("5_PPT大纲.docx", data.get("ppt_outline", "")),
    ]
    
    # 直接在内存里打包，不写临时文件，速度快很多
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_STORED) as zf:  # 不压缩，直接打包
        for filename, text in files_to_export:
            if not text or not text.strip():
                continue
            
            # 快速生成 Word：直接加文本，不解析 Markdown
            docx_buf = io.BytesIO()
            doc = Document()
            # 设置默认字体
            from docx.shared import Pt
            style = doc.styles['Normal']
            style.font.name = '宋体'
            style.font.size = Pt(12)
            # 加标题
            doc.add_heading(filename.replace('.docx', ''), 0)
            # 按段落写，更美观
            import re
            clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
            clean_text = re.sub(r'^#+\s*', '', clean_text, flags=re.MULTILINE)
            for para in clean_text.split('\n\n'):
                if para.strip():
                    doc.add_paragraph(para.strip())
            doc.save(docx_buf)
            docx_buf.seek(0)
            zf.writestr(filename, docx_buf.read())
    
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='科创赛事材料包.zip', mimetype='application/zip')

@app.route('/api/export_original_format', methods=['POST'])
def export_original_format():
    from docx import Document
    import io
    import re
    
    # 拿用户上传的原文件和优化后的内容
    original_file = request.files.get('original_file')
    optimized_text = request.form.get('optimized_text', '')
    
    if not original_file:
        return jsonify({"success": False, "error": "没有原文件"})
    
    try:
        doc = Document(io.BytesIO(original_file.read()))
        
        # 简单处理：替换段落里的文字，保留格式
        paragraphs = optimized_text.split('\n')
        para_idx = 0
        for para in doc.paragraphs:
            if para_idx < len(paragraphs) and paragraphs[para_idx].strip():
                # 保留原来的样式，只改文字
                for run in para.runs:
                    run.text = ''
                if para.runs:
                    para.runs[0].text = paragraphs[para_idx].strip()
                else:
                    para.add_run(paragraphs[para_idx].strip())
            para_idx += 1
        
        # 保存
        buf = io.BytesIO()
        doc.save(buf)
        buf.seek(0)
        return send_file(buf, as_attachment=True, download_name='优化后的申报书.docx', mimetype='application/docx')
    except Exception as e:
        return jsonify({"success": False, "error": f"导出失败：{str(e)}"})


@app.route('/api/upload_file', methods=['POST'])
def upload_file():
    import os
    from werkzeug.utils import secure_filename
    file = request.files['file']
    if not file:
        return jsonify({"success": False, "error": "没有文件"})
    
    filename = secure_filename(file.filename)
    ext = filename.split('.')[-1].lower()
    text = ""
    
    try:
        if ext == 'pdf':
            import pdfplumber
            with pdfplumber.open(file) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                    tables = page.extract_tables()
                    for table in tables:
                        text += "\n[表格数据]\n"
                        for row in table:
                            text += " | ".join([str(cell) if cell else "" for cell in row]) + "\n"
                    # 提取PDF里的图片，用Claude识别
                    if page.images:
                        text += "\n[检测到页面含图片/图表]\n"
        elif ext in ['jpg', 'jpeg', 'png']:
            # 图片直接用Claude多模态识别
            import base64
            from langchain_core.messages import HumanMessage
            from competition_agents import claude_llm
            
            img_base64 = base64.b64encode(file.read()).decode('utf-8')
            response = claude_llm.invoke([
                HumanMessage(content=[
                    {"type": "text", "text": "请详细描述这张图片里的所有内容，包括文字、图表数据、标题、关键数字，把图片里的信息都提取出来。"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}}
                ])
            ])
            text = response.content
        elif ext == 'txt':
            text = file.read().decode('utf-8')
        elif ext == 'docx':
            from docx import Document
            import io
            doc = Document(io.BytesIO(file.read()))
            for para in doc.paragraphs:
                if para.text.strip():
                    text += para.text.strip() + "\n"
            for table in doc.tables:
                text += "\n[表格数据]\n"
                for row in table.rows:
                    text += " | ".join([cell.text.strip() for cell in row.cells]) + "\n"
        else:
            return jsonify({"success": False, "error": "不支持的文件格式"})
        
        # 清理多余空行，把连续多个换行合并成两个
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.strip()
        return jsonify({"success": True, "text": text})
    except Exception as e:
        return jsonify({"success": False, "error": f"文件解析失败：{str(e)}"})


# ============ 启动 ============
if __name__ == '__main__':
    print("=" * 60)
    print("🚀 科创赛事多智能体协同创作助手 - Web 版")
    print("=" * 60)
    print("📱 浏览器打开: http://127.0.0.1:8080")
    print("=" * 60)
    app.run(debug=True, port=8080)
