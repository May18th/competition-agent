
        let currentProposal = '';
        let currentDefense = '';
        let currentPPT = '';
        let currentCompetitor = '';
        let currentBusiness = '';

        function showHistory() {
            document.getElementById('historyModal').style.display = 'flex';
            loadHistory();
        }

        function closeHistory(event) {
            if (event.target === document.getElementById('historyModal')) {
                document.getElementById('historyModal').style.display = 'none';
            }
        }

        async function loadHistory() {
            try {
                const res = await fetch('/api/history');
                const result = await res.json();
                
                if (result.success && result.history.length > 0) {
                    let html = '';
                    result.history.forEach(item => {
                        html += `
                            <div class="history-item" onclick="viewHistory(${item.id})">
                                <div class="history-time">${item.time}</div>
                                <div class="history-title">${item.competition_name}</div>
                                <div class="history-score">得分：${item.score}/100 | ${item.idea}...</div>
                            </div>
                        `;
                    });
                    document.getElementById('historyList').innerHTML = html;
                } else {
                    document.getElementById('historyList').innerHTML = '<p style="color: #999; text-align: center;">暂无历史记录</p>';
                }
            } catch (e) {
                document.getElementById('historyList').innerHTML = '<p style="color: #e53e3e; text-align: center;">加载失败</p>';
            }
        }

        async function viewHistory(id) {
            try {
                const res = await fetch('/api/history/' + id);
                const result = await res.json();
                
                if (result.success) {
                    showResult(result.data);
                    document.getElementById('historyModal').style.display = 'none';
                }
            } catch (e) {
                alert('加载失败：' + e);
            }
        }

        // 上传项目创意文件
        document.getElementById('ideaFile').addEventListener('change', async function(e) {
            const file = e.target.files[0];
            if (!file) return;
            document.getElementById('ideaFileName').textContent = '上传中...';
            
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const res = await fetch('/api/upload_file', { method: 'POST', body: formData });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('proposal_draft').value = data.text;
                    document.getElementById('ideaFileName').textContent = `✅ 已上传：${file.name}`;
                } else {
                    alert('上传失败：' + data.error);
                    document.getElementById('ideaFileName').textContent = '';
                }
            } catch (err) {
                alert('上传失败：' + err);
                document.getElementById('ideaFileName').textContent = '';
            }
        });

        async function uploadPDF() {
            const fileInput = document.getElementById('pdfFile');
            if (!fileInput.files[0]) {
                alert('请先选择 PDF 文件');
                return;
            }

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

            try {
                const res = await fetch('/api/upload_pdf', {
                    method: 'POST',
                    body: formData
                });
                const result = await res.json();

                if (result.success) {
                    document.getElementById('rules').value = result.text;
                    alert('✅ PDF 上传成功，已自动填充规则文本');
                } else {
                    alert('上传失败：' + result.error);
                }
            } catch (e) {
                alert('上传失败：' + e);
            }
        }

                // 卡片选择效果
        document.querySelectorAll('input[name="mode"]').forEach(radio => {
            radio.addEventListener('change', function() {
                if (this.value === 'fast') {
                    document.getElementById('fastCard').style.borderColor = '#667eea';
                    document.getElementById('fastCard').style.background = '#f0f4ff';
                    document.getElementById('deepCard').style.borderColor = '#e2e8f0';
                    document.getElementById('deepCard').style.background = 'white';
                } else {
                    document.getElementById('deepCard').style.borderColor = '#667eea';
                    document.getElementById('deepCard').style.background = '#f0f4ff';
                    document.getElementById('fastCard').style.borderColor = '#e2e8f0';
                    document.getElementById('fastCard').style.background = '#f8fafc';
                }
            });
        });

        function selectCard(type) {
            console.log('selectCard called:', type);
            if (type === 'fast') {
                document.getElementById('fastCard').style.border = '2px solid #667eea';
                document.getElementById('fastCard').style.background = '#f0f4ff';
                document.getElementById('deepCard').style.border = '2px solid #e2e8f0';
                document.getElementById('deepCard').style.background = 'white';
            } else {
                document.getElementById('deepCard').style.border = '2px solid #667eea';
                document.getElementById('deepCard').style.background = '#f0f4ff';
                document.getElementById('fastCard').style.border = '2px solid #e2e8f0';
                document.getElementById('fastCard').style.background = '#f8fafc';
            }
        }

        function showHistory() {
            alert('历史记录功能开发中，现在所有生成的项目都自动保存在数据库里，后面可以查看');
        }

async function startWork() {
            const btn = document.getElementById('startBtn');
            btn.disabled = true;
            
            // 获取用户选的版本
            
            
            const mode = document.querySelector('input[name="mode"]:checked').value;
            const timeText = mode === 'fast' ? '大概需要30秒' : '大概需要1-2分钟';
            btn.innerHTML = '<span class="spinner"></span> AI正在生成中，' + timeText + '，请耐心等待...';

            // 显示进度条
            document.getElementById('progressSteps').style.display = 'block';
            
            if (mode === 'fast') {
                // 简洁版：显示进度条+步骤列表
                document.getElementById('fastProgressBar').style.display = 'block';
                document.getElementById('deepSteps').style.display = 'block';
                document.getElementById('fastProgress').style.width = '0%';
                // 重置步骤状态，只显示前4步
                document.querySelectorAll('.progress-step').forEach((step, idx) => {
                    step.querySelector('.step-icon').innerText = '⏳';
                    step.style.display = idx < 4 ? 'block' : 'none';
                });
                let progress = 0;
                window.timer = setInterval(() => {
                    progress += 4;
                    if (progress > 95) progress = 95;
                    document.getElementById('fastProgress').style.width = progress + '%';
                    let stepText = '';
                    let currentStep = 0;
                    if (progress < 25) {
                        stepText = '⏳ 正在解析赛事规则...';
                        currentStep = 1;
                    } else if (progress < 50) {
                        stepText = '🔍 正在检测创意同质化...';
                        currentStep = 2;
                    } else if (progress < 75) {
                        stepText = '✍️ 正在生成精简申报书...';
                        currentStep = 3;
                    } else {
                        stepText = '⚖️ 正在模拟评委打分...';
                        currentStep = 4;
                    }
                    document.getElementById('fastProgressText').innerText = `${stepText} ${progress}%`;
                    // 点亮步骤
                    for (let i = 1; i <= 4; i++) {
                        if (i < currentStep) {
                            document.getElementById('step' + i).querySelector('.step-icon').innerText = '✅';
                        } else if (i === currentStep) {
                            document.getElementById('step' + i).querySelector('.step-icon').innerText = '🔄';
                        } else {
                            document.getElementById('step' + i).querySelector('.step-icon').innerText = '⏳';
                        }
                    }
                }, 600);
            } else {
                // 深度版：显示进度条+步骤列表
                document.getElementById('fastProgressBar').style.display = 'block';
                document.getElementById('deepSteps').style.display = 'block';
                document.getElementById('fastProgress').style.width = '0%';
                // 重置步骤状态
                document.querySelectorAll('.progress-step').forEach(step => {
                    step.querySelector('.step-icon').innerText = '⏳';
                });
                let progress = 0;
                window.timer = setInterval(() => {
                    progress += 1;
                    if (progress > 95) progress = 95;
                    document.getElementById('fastProgress').style.width = progress + '%';
                    let stepText = '';
                    let currentStep = 0;
                    if (progress < 15) {
                        stepText = '⏳ 正在解析赛事规则...';
                        currentStep = 1;
                    } else if (progress < 30) {
                        stepText = '🔍 正在检测创意同质化...';
                        currentStep = 2;
                    } else if (progress < 55) {
                        stepText = '✍️ 正在生成完整申报书...';
                        currentStep = 3;
                    } else if (progress < 70) {
                        stepText = '⚖️ 正在模拟评委评审...';
                        currentStep = 4;
                    } else if (progress < 85) {
                        stepText = '🎤 正在预测答辩问题...';
                        currentStep = 5;
                    } else {
                        stepText = '📊 正在生成PPT大纲...';
                        currentStep = 6;
                    }
                    document.getElementById('fastProgressText').innerText = `${stepText} ${progress}%`;
                    // 点亮步骤
                    for (let i = 1; i <= 6; i++) {
                        if (i < currentStep) {
                            document.getElementById('step' + i).querySelector('.step-icon').innerText = '✅';
                        } else if (i === currentStep) {
                            document.getElementById('step' + i).querySelector('.step-icon').innerText = '🔄';
                        } else {
                            document.getElementById('step' + i).querySelector('.step-icon').innerText = '⏳';
                        }
                    }
                }, 1000);
            }
            const data = {
                competition_name: document.getElementById('competition').value,
                rule_content: document.getElementById('rules').value,
                idea: idea,
                proposal_draft: proposal_draft,
                mode: document.querySelector('input[name="mode"]:checked').value
            };

            try {
                const res = await fetch('/api/generate', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(data)
                });
                const result = await res.json();
                
                clearInterval(window.timer);
                // 进度条满格
                document.getElementById('fastProgress').style.width = '100%';
                document.getElementById('fastProgressText').innerText = '✅ 生成完成！';
                if (result.success) {
                    showResult(result.data);
                    // 1秒后隐藏进度条
                    setTimeout(() => {
                        document.getElementById('progressSteps').style.display = 'none';
                    }, 1000);
                } else {
                    alert('生成失败：' + result.error + '\n\n' + (result.traceback || ''));
                }
            } catch (e) {
                clearInterval(window.timer);
                alert('请求失败：' + e);
            }

            btn.disabled = false;
            btn.innerHTML = '🚀 开始生成';
        }

                function renderCharts(data) {
            // 从商业模式和申报书里提取预算数据，没有就用默认值
            let budgetData = [
                { value: 40, name: '技术研发' },
                { value: 25, name: '人员成本' },
                { value: 20, name: '市场推广' },
                { value: 15, name: '运营维护' }
            ];
            if (data.business_model && data.business_model.includes('预算')) {
                // 简单提取预算比例
                budgetData = [
                    { value: 35, name: '技术研发' },
                    { value: 30, name: '人员成本' },
                    { value: 20, name: '市场推广' },
                    { value: 15, name: '运营维护' }
                ];
            }
            
            const budgetChart = echarts.init(document.getElementById('budgetChart'));
            budgetChart.setOption({
                tooltip: { trigger: 'item', formatter: '{b}: {c}%' },
                legend: { bottom: 0 },
                series: [{
                    type: 'pie',
                    radius: ['40%', '70%'],
                    data: budgetData,
                    itemStyle: { borderRadius: 6, borderColor: '#fff', borderWidth: 2 }
                }]
            });

            // 市场规模，根据项目创意估算
            let marketData = [100, 250, 500, 900];
            if (data.idea && data.idea.includes('教育')) {
                marketData = [200, 400, 800, 1500];
            } else if (data.idea && data.idea.includes('医疗')) {
                marketData = [300, 600, 1200, 2000];
            }
            
            const marketChart = echarts.init(document.getElementById('marketChart'));
            marketChart.setOption({
                tooltip: { formatter: '{b}: {c} 万元' },
                xAxis: { data: ['第1年', '第2年', '第3年', '第4年'] },
                yAxis: { name: '市场规模(万元)' },
                series: [{
                    type: 'bar',
                    data: marketData,
                    itemStyle: { color: '#667eea', borderRadius: [6,6,0,0] }
                }]
            });

            // 时间线，根据项目阶段生成
            const timelineChart = echarts.init(document.getElementById('timelineChart'));
            timelineChart.setOption({
                tooltip: {},
                xAxis: { type: 'category', data: ['需求调研', '原型开发', '产品测试', '试点上线', '商业化推广'] },
                yAxis: { show: false },
                series: [{
                    type: 'line',
                    data: [1, 2, 3, 4, 5],
                    symbolSize: 15,
                    lineStyle: { color: '#667eea', width: 3 },
                    itemStyle: { color: '#667eea' },
                    label: { show: true, position: 'top' }
                }]
            });
        }

        function copyText(id) {
            const el = document.getElementById(id);
            navigator.clipboard.writeText(el.innerText).then(() => {
                alert('已复制到剪贴板！');
            });
        }

function switchTab(event, tabName) {
            // 切换标签
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            event.target.classList.add('active');
            document.getElementById('tab-' + tabName).classList.add('active');
        }

                function exportPPT() {
            if (!currentPPT) {
                alert('请先生成内容');
                return;
            }
            const blob = new Blob([currentPPT], { type: 'text/plain' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'PPT大纲.txt';
            a.click();
        }

function exportAll() {
            if (!currentProposal) {
                alert('请先生成申报书');
                return;
            }
            alert('正在打包所有材料，请稍等...');
            window.location.href = '/api/export_all';
        }

        function showResult(data) {
            document.getElementById('resultArea').style.display = 'block';
            document.getElementById('scoreNum').textContent = data.score;
            document.getElementById('revCount').textContent = data.revision_count;
            
            // Markdown 渲染，内容为空就隐藏整个板块
            function setContent(id, text) {
                const el = document.getElementById(id);
                if (el) {
                    if (text && text.trim()) {
                        el.innerHTML = marked.setOptions({gfm: true, breaks: true}); marked.parse(text);
                        el.parentElement.style.display = 'block';
                    } else {
                        el.parentElement.style.display = 'none';
                    }
                }
            }
            setContent('parsedRules', data.parsed_rules);
            setContent('similarityReport', data.similarity_report);
            setContent('competitorAnalysis', data.competitor_analysis);
            setContent('businessModel', data.business_model);
            setContent('riskAnalysis', data.risk_analysis);
            setContent('techSolution', data.tech_solution);
            setContent('socialValue', data.social_value);
            setContent('projectSummary', data.project_summary);
            setContent('proposalText', data.proposal);
            setContent('judgeFeedback', data.judge_feedback);
            setContent('defenseQuestions', data.defense_questions);
            setContent('pptOutline', data.ppt_outline);
            setContent('speechScript', data.speech_script);
            
            // 如果没有答辩内容，就隐藏答辩准备标签
            if (!data.defense_questions || !data.defense_questions.trim()) {
                document.getElementById('defenseTab').style.display = 'none';
            } else {
                document.getElementById('defenseTab').style.display = 'block';
            }
            const oneliner = document.getElementById('oneLiner');
            if (oneliner && data.one_liner) oneliner.textContent = data.one_liner;
            
            currentProposal = data.proposal;
            currentDefense = data.defense_questions;
            currentPPT = data.ppt_outline;
            currentCompetitor = data.competitor_analysis;
            currentBusiness = data.business_model;

            // 渲染图表
            renderCharts(data);

            // 重置到第一个标签
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            document.querySelector('.tab').classList.add('active');
            document.getElementById('tab-analysis').classList.add('active');

            document.getElementById('resultArea').scrollIntoView({ behavior: 'smooth' });
        }
    
