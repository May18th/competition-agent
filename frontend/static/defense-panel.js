/* 第二百七十一轮：答辩模拟问答面板
 *
 * 纯静态预置，不调任何接口、不新增 LLM 消耗。
 * 评委点问题即出「回答框架」（要点 + 数据支撑建议 + 避坑提示），
 * 用于交互式展示答辩 Agent 的能力，不作为正式答辩答案。
 *
 * 独立区块（#defenseQA），不侵入结果页正文渲染（#defenseQuestions 仍由后端填充）。
 * 接口版（可选调 /api 答辩接口）默认关闭，如后续接入在此文件内加开关即可。
 */
(function () {
    'use strict';
    if (window.__wbDefenseInit) return;
    window.__wbDefenseInit = true;

    // 评委高频问题 + 回答框架（基于科创赛事通用答辩范式整理）
    var QA = [
        {
            q: '你的创新点是什么？和现有方案的本质区别在哪？',
            points: [
                '用一句话说清「别人做不到／做不好，而你能」的那一点，不要罗列功能清单',
                '对比对象要具体（点名现有方案或竞品），而不是泛泛说「现有方案存在不足」',
                '创新点控制在 2–3 个，讲多评委会记不住'
            ],
            data: '建议支撑：与对照方案的实测对比（准确率／耗时／成本）、查新或专利检索结论、用户使用前后对比',
            trap: '避坑：别说「我们用了智能技术所以更智能」——那是手段不是创新点；别说「国内首创／国际领先」却拿不出佐证'
        },
        {
            q: '这个需求真实存在吗？你是怎么验证的？',
            points: [
                '先说你接触了多少真实用户／场景，再说从他们嘴里听到了什么',
                '区分「用户说想要」和「用户真的会用」——最好有行为数据',
                '说清需求出现的频率和场景，而不是讲一个极端个案'
            ],
            data: '建议支撑：访谈／问卷的样本量与结论、试点期间的真实使用数据、需求出现的频次统计',
            trap: '避坑：别把「我觉得」当需求验证；样本量很小时要主动说明，不要包装成普遍结论'
        },
        {
            q: '技术方案为什么这样选？有没有考虑过别的方案？',
            points: [
                '给出你考虑过的 1–2 个备选方案和否决理由，说明这是权衡后的选择',
                '说清关键技术指标是怎么定出来的（为什么是这个数）',
                '承认当前方案的边界——哪些场景它还不好使'
            ],
            data: '建议支撑：方案对比表、关键技术指标的实测值、原型／Demo 的完成情况',
            trap: '避坑：别堆技术名词；被问到短板时坦诚说明边界和后续计划，比硬撑更得分'
        },
        {
            q: '和同类竞品相比，你的优势在哪？',
            points: [
                '选 2–3 个真实竞品做对比，维度要可比（功能／成本／体验／落地条件）',
                '优势要落在用户可感知的价值上，不是参数表上的数字',
                '如果某项不如竞品，主动说明你的替代策略'
            ],
            data: '建议支撑：竞品对比表（标注数据来源与时间）、试用截图或记录、价格／成本测算',
            trap: '避坑：别把竞品说成一无是处，评委会反感；也别只比优点不比缺点'
        },
        {
            q: '商业模式怎么成立？谁付钱、付多少？',
            points: [
                '先说清买单的人是谁（用户／企业／平台），再说他为什么愿意付',
                '给出定价依据（成本、竞品价、用户可承受度），不要拍脑袋',
                '说清从现在到收入的下一步动作'
            ],
            data: '建议支撑：成本结构与毛利测算、同类产品定价区间、已有意向客户或试点订单',
            trap: '避坑：别画一个「未来靠广告／增值服务变现」的大饼而无路径；早期项目没收入很正常，把路径说清即可'
        },
        {
            q: '团队为什么能做成这件事？',
            points: [
                '把成员能力与项目关键难点对应起来，而不是罗列履历',
                '说清分工和已完成的进度，证明不是刚起步',
                '缺什么能力、打算怎么补，也要讲'
            ],
            data: '建议支撑：已完成的原型／版本里程碑、分工与投入时间、指导老师或合作资源',
            trap: '避坑：别说「我们学习能力强」这类空话；成员数是弱点时强调外部资源与执行进度'
        },
        {
            q: '你的数据从哪来？样本量够吗？',
            points: [
                '说清数据来源（自测／公开数据集／合作方）和采集方式',
                '主动说明样本规模与局限，再说明为什么在这个规模下结论仍可信',
                '区分「自测值」「测算值」「引用值」——口径必须标注'
            ],
            data: '建议支撑：样本量与采集时间、对照组设置、误差范围或置信说明',
            trap: '避坑：别把测算值说成实测值；评委追问口径时答不上来是硬伤'
        },
        {
            q: '落地过程中最大的风险是什么？你怎么应对？',
            points: [
                '先主动说出 1–2 个真实风险（技术、供应链、合规、获客都行）',
                '每个风险给具体应对动作和触发条件',
                '说明最坏情况下的止损方案'
            ],
            data: '建议支撑：风险清单与等级、已做的验证或备案、关键环节的备选方案',
            trap: '避坑：别说「没有明显风险」；也别只提风险不给应对'
        },
        {
            q: '这个项目能规模化／复制吗？',
            points: [
                '说清复制的前提条件（哪些场景满足就能用）',
                '给出单位成本随规模变化的判断依据',
                '说明规模化时最先遇到的瓶颈'
            ],
            data: '建议支撑：单场景投入产出测算、可复制场景的数量估计、边际成本变化曲线',
            trap: '避坑：别把「市场很大」等同于「我能规模化」；要讲清楚从 1 到 N 的具体动作'
        },
        {
            q: '如果给你更多时间或资金，你下一步做什么？',
            points: [
                '给出 3–6 个月的明确里程碑，而不是「继续优化」',
                '说明这笔资源解决的是哪个关键瓶颈',
                '说清达成后的验证标准是什么'
            ],
            data: '建议支撑：里程碑排期、资金用途分配、每个节点的验收指标',
            trap: '避坑：别答「先把产品做好」这类没有信息量的话；里程碑要可验证'
        }
    ];

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function render() {
        var box = document.getElementById('defenseQA');
        if (!box) return false;

        var html = '';
        html += '<h3>答辩模拟问答'
            + '<span style="margin-left:10px;font-size:12px;font-weight:400;color:var(--text-dim);">'
            + '点问题看回答框架 · 静态预置，不消耗额度</span></h3>';
        html += '<div style="margin:8px 0 12px;padding:8px 12px;border-radius:8px;'
            + 'background:var(--surface-2);font-size:12.5px;color:var(--text-dim);line-height:1.7;">'
            + '以下为评委高频问题的<strong>回答框架</strong>（要点 + 数据支撑建议 + 避坑提示），'
            + '用于演练思路，<strong>不是可直接照读的答辩答案</strong>。'
            + '请结合你自己的真实数据填充，框架仅为多智能体答辩预测 Agent 的静态范式，仅供参考。</div>';

        for (var i = 0; i < QA.length; i++) {
            var it = QA[i];
            html += '<div class="wb-qa-item" data-idx="' + i + '" style="margin-bottom:8px;'
                + 'border:1px solid var(--line);border-radius:8px;overflow:hidden;">';
            html += '<button type="button" class="wb-qa-q" data-idx="' + i + '" '
                + 'style="width:100%;text-align:left;padding:10px 14px;font-size:13.5px;'
                + 'background:var(--btn-ghost);color:var(--text);border:none;cursor:pointer;">'
                + '<span style="color:var(--c-a);font-weight:700;">Q' + (i + 1) + '.</span> '
                + esc(it.q) + ' <span style="float:right;color:var(--text-dim);">▾</span></button>';
            html += '<div class="wb-qa-a" data-idx="' + i + '" style="display:none;padding:4px 14px 14px;">';

            html += '<div style="font-size:12.5px;color:var(--text-dim);margin:8px 0 4px;">回答要点</div>';
            html += '<ul style="margin:0 0 10px;padding-left:20px;font-size:13px;line-height:1.8;">';
            for (var j = 0; j < it.points.length; j++) {
                html += '<li>' + esc(it.points[j]) + '</li>';
            }
            html += '</ul>';

            html += '<div style="font-size:12.5px;color:var(--text-dim);margin:10px 0 4px;">数据支撑建议</div>';
            html += '<div style="font-size:13px;line-height:1.8;">' + esc(it.data) + '</div>';

            html += '<div style="font-size:12.5px;color:var(--text-dim);margin:10px 0 4px;">避坑提示</div>';
            html += '<div style="font-size:13px;line-height:1.8;color:var(--text);">' + esc(it.trap) + '</div>';

            html += '</div></div>';
        }

        box.innerHTML = html;

        // 事件委托：点问题展开/收起（只展开一个，避免面板过长）
        box.addEventListener('click', function (e) {
            var btn = e.target.closest ? e.target.closest('.wb-qa-q') : null;
            if (!btn) return;
            var idx = btn.getAttribute('data-idx');
            var ans = box.querySelector('.wb-qa-a[data-idx="' + idx + '"]');
            if (!ans) return;
            var willOpen = ans.style.display === 'none';
            var all = box.querySelectorAll('.wb-qa-a');
            for (var k = 0; k < all.length; k++) all[k].style.display = 'none';
            ans.style.display = willOpen ? 'block' : 'none';
        });

        return true;
    }

    // 结果区内容是异步渲染的，一次抓不到就重试几轮
    var tries = 0, timer = null;
    function boot() {
        tries++;
        var ok = false;
        try { ok = render(); } catch (e) {}
        if (!ok && tries < 12) timer = setTimeout(boot, 400);
        else if (timer) { clearTimeout(timer); timer = null; }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }

    window.WB_DEFENSE_QA = QA;
})();
