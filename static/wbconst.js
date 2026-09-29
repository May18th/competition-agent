/* 科创赛事助手 —— 静态常量外置（M7 前端瘦身）
   来源：static/app.js 中 20 个「纯数据」顶层字面量，逐字节机械搬迁，未改任何值。
   规则：全部显式挂 window（本项目 index.html 有多个 script 块，跨块/跨文件访问必须显式挂 window；
   本文件在 app.js 之前加载，保证任何时机、任何块里都能读到）。
   引入顺序：必须在 static/app.js 之前。 */
(function () {
    window._DOM_TO_KEY = {
            parsedRules: 'parsed_rules', similarityReport: 'similarity_report',
            proposalText: 'proposal', proposalAnalysis: 'proposal_analysis',
            judgeFeedback: 'judge_feedback', competitorAnalysis: 'competitor_analysis',
            businessModel: 'business_model', riskAnalysis: 'risk_analysis',
            techSolution: 'tech_solution', defenseQuestions: 'defense_questions',
            pptOutline: 'ppt_outline',
            // 实施计划：zip 里早就有 12_实施计划.docx，但导出中心一直没有单文件入口
            implementationPlan: 'implementation_plan'
        };
    window._DOC_TYPE = {
            parsedRules: 'report', similarityReport: 'report', proposalText: 'default',
            proposalAnalysis: 'analysis', judgeFeedback: 'analysis',
            competitorAnalysis: 'analysis', businessModel: 'analysis',
            riskAnalysis: 'analysis', defenseQuestions: 'analysis', pptOutline: 'outline',
            techSolution: 'analysis', implementationPlan: 'analysis'
        };
    window.EVENT_REQ = {
            "iCAN大学生创新创业大赛": {
                label: "应用方案", doc_type: "应用方案（PDF，不超过 20 页 / 50MB）",
                alias: ["ican", "ican大赛", "ican大学生", "创新创业", "AI应用创新挑战赛", "iCAN AI挑战赛"],
                sections: ["一、项目背景与痛点", "二、需求分析与目标用户", "三、开发工具与技术选型",
                           "四、技术方案与系统架构", "五、功能说明与智能核心作用",
                           "六、使用说明", "七、应用前景与商业模式", "八、团队分工与知识产权"],
                // 官方口径（创新赛道·2026 现行，与 data/competition_profiles.json 一致）：创新性35/实用性25/原创性20/技术方案20
                scoring: [["创新性", 35], ["实用性", 25], ["原创性", 20], ["技术方案", 20]],
                deduct: "扣分点：AI 只做套壳点缀 / 无可运行 Demo / 技术细节空洞 / 缺少使用说明 / 硬件赛道交渲染图",
                // 官方提交物（AI 应用创新挑战赛）：应用方案 PDF + 演示视频 + 可运行程序
                submit: ["应用方案 PDF（≤20页、≤50MB）", "演示视频 MP4（≤5分钟）",
                         "可运行程序链接或源码", "硬件赛道另交：硬件设计说明 + 实物原型照片"]
            },
            "挑战杯全国大学生课外学术科技作品竞赛": {
                label: "申报书", doc_type: "申报书（学术论文 / 科技发明类）",
                alias: ["挑战杯", "课外学术科技作品"],
                sections: ["一、项目概述", "二、国内外研究现状", "三、研究内容与方法",
                           "四、创新点与成果", "五、应用前景与社会价值", "六、团队与进度安排"],
                scoring: [["创新性", 30], ["可行性", 30], ["科学性与先进性", 20], ["综合答辩与展示", 20]],
                deduct: "扣分点：缺少文献综述 / 创新点不清晰 / 无数据或实验支撑"
            },
            "中国国际互联网+大学生创新创业大赛": {
                label: "商业计划书", doc_type: "商业计划书",
                alias: ["互联网+", "互联网+大赛", "中国国际大学生创新大赛"],
                sections: ["一、项目概述", "二、市场分析", "三、产品与技术方案", "四、商业模式",
                           "五、财务预测与融资计划", "六、团队与教育维度", "七、社会价值"],
                scoring: [["个人成长", 30], ["项目创新", 30], ["产业价值", 25], ["团队协作", 15]],
                deduct: "扣分点：商业模式不成立 / 财务数据拍脑袋 / 缺少教育维度"
            }
        };
    window.EV_DEFAULT = {
            label: "申报书", doc_type: "申报书（通用科创赛事结构）",
            sections: ["一、项目概述", "二、项目背景与痛点分析", "三、解决方案与技术方案",
                       "四、核心创新点", "五、应用场景与市场分析", "六、商业模式",
                       "七、团队介绍与分工", "八、社会价值与应用前景"],
            scoring: [["创新性", 30], ["实用性", 25], ["技术难度", 20], ["团队展示", 15], ["社会价值", 10]],
            deduct: "通用结构：可在上方卡片里增删改章节，生成会按你改的来"
        };
    window.COACH_STEPS = [
            // 这里刻意用中文数字：表单区块已经占用了「第 1~6 步」这套阿拉伯数字编号，
            // 引导气泡要是也写「第 3 步」，就会和表单的「第 3 步 · 补充规则」撞号，
            // 用户分不清到底说的是哪一步。两套各用一套写法，一眼能分辨。
            { id: 'competition', text: '第一步：选择参赛赛事。系统将按该赛事的官方评分标准与章节要求组织内容；未收录的赛事按通用标准生成。' },
            { id: 'idea', text: '第二步：填写项目创意。用一两句话说明目标用户、解决的核心问题与技术路径，描述越具体，产出越贴合评审视角。' },
            { id: 'startBtn', text: '第三步：选择生成档位并开始。简洁版出稿快、字数精；深度版内容更全，含图表与路演 PPT。两档的实际字数与用时见档位卡上的实测统计。' }
        ];
    window.WB_IDEA_COMP = [
            {name: 'iCAN大学生创新创业大赛', kw: ['ican', '物联网', '智能硬件', '传感器', '可穿戴']},
            {name: '中国国际互联网+大学生创新创业大赛', kw: ['互联网+', '互联网＋', '商业计划', '融资', '路演', '商业模式']},
            {name: '全国大学生数学建模竞赛', kw: ['数学建模', '数模', '数学模', '优化模型', '预测模型', '评价体系']},
            {name: '全国大学生电子设计竞赛', kw: ['电子设计', '电赛', '单片机', '电路设计', '嵌入式', '硬件设计']},
            {name: '挑战杯全国大学生课外学术科技作品竞赛', kw: ['大挑', '课外学术科技', '学术作品', '调研报告', '社会调查']},
            {name: '挑战杯中国大学生创业计划竞赛（小挑）', kw: ['小挑', '创业计划竞赛']},
            {name: '国家级大学生创新创业训练计划', kw: ['国创', '大创', '创新创业训练']},
            {name: '全国大学生广告艺术大赛', kw: ['大广赛', '广告艺术', '品牌策划', '视觉传达', '海报设计']},
            {name: '中国大学生服务外包创新创业大赛', kw: ['服务外包']},
            {name: '蓝桥杯全国软件和信息技术专业人才大赛', kw: ['蓝桥杯', '算法竞赛', '程序设计竞赛']},
            {name: '全国大学生信息安全竞赛', kw: ['信息安全', '网安', '网络安全', '攻防', '漏洞']},
            {name: '中国大学生计算机设计大赛', kw: ['计算机设计', '软件作品', '应用系统']},
            {name: 'RoboMaster全国大学生机器人大赛', kw: ['robomaster', '机器人', '机甲', '机械臂']},
            {name: '西门子杯中国智能制造挑战赛', kw: ['西门子', '智能制造', '工业自动化', '产线']}
        ];
    window.WB_COMP_SHORT = [
            ['ican', 'iCAN'],
            ['互联网', '互联网+'],
            ['课外学术科技作品', '大挑'],
            ['创业计划', '小挑'],
            ['创新创业训练计划', '国创'],
            ['数学建模', '数模'],
            ['电子设计', '电赛'],
            ['西门子', '西门子杯'],
            ['计算机设计', '计算机设计'],
            ['蓝桥杯', '蓝桥杯'],
            ['robomaster', 'RoboMaster'],
            ['信息安全', '信安'],
            ['服务外包', '服务外包'],
            ['广告艺术', '大广赛'],
            ['金砖', '金砖']
        ];
    window.WB_ROAD_PAGES = [
            {key: 'cover',    type: 'cover',   name: '封面',     kw: [], strong: []},
            {key: 'pain',     type: 'bullets', name: '项目痛点',
             kw: ['痛点', '问题', '现状', '背景', '需求', '挑战', '难点', '困难', '刚需', '为什么'],
             strong: ['痛点', '难点', '难以', '无法', '不足', '缺失', '缺少', '成本高', '效率低', '信息不对称']},
            {key: 'solution', type: 'bullets', name: '解决方案',
             kw: ['解决方案', '方案', '技术', '原理', '思路', '路径', '方法', '路线', '架构', '创新点', '实现'],
             strong: ['采用', '通过', '本方案', '本平台', '架构', '算法', '机制', '实现']},
            {key: 'feature',  type: 'bullets', name: '核心功能',
             kw: ['功能', '产品', '模块', '特性', '亮点', '优势', '服务', '场景', '形态'],
             strong: ['功能', '模块', '支持', '提供', '一键', '自动', '可查', '可追溯']},
            {key: 'data',     type: 'metrics', name: '落地数据',
             kw: ['数据', '成果', '验证', '落地', '试点', '效果', '指标', '市场', '规模', '财务', '营收', '用户', '测试', '进展'],
             strong: ['试点', '测试', '验证', '覆盖', '累计', '准确率', '提升', '降低', '增长']},
            {key: 'compete',  type: 'table',   name: '竞品对比',
             kw: ['竞品', '对比', '竞争', '差异化', '对手', '同类', '友商'],
             strong: ['竞品', '对比', '相比', '同类', '友商', '优于', '差异', '领先']},
            {key: 'team',     type: 'bullets', name: '团队介绍',
             kw: ['团队', '成员', '分工', '指导', '师资', '负责人', '年级', '专业'],
             strong: ['团队成员', '成员', '分工', '指导教师', '团队由', '专业年级']},
            {key: 'thanks',   type: 'closing', name: '致谢',     kw: [], strong: []}
        ];
    window.WB_EXTRA_PAGES = {
            math: [
                {key: 'assume',  type: 'bullets', name: '模型假设', after: 'solution',
                 kw: ['假设', '前提', '符号', '变量', '约定', '符号说明', '假定'],
                 strong: ['假设', '假定', '不妨设', '符号说明', '记为', '忽略', '不考虑']},
                {key: 'formula', type: 'bullets', name: '公式推导', after: 'assume',
                 kw: ['公式', '推导', '求解', '目标函数', '约束', '模型建立', '算法', '求解过程', '灵敏度', '检验'],
                 strong: ['公式', '推导', '由', '可得', '代入', '目标函数', '约束条件', '求解', '迭代']}
            ],
            art: [
                {key: 'sketch', type: 'bullets', name: '创意草图', after: 'feature',
                 kw: ['创意', '草图', '构思', '概念', '灵感', '脚本', '分镜', '文案', '主题'],
                 strong: ['创意', '构思', '草图', '脚本', '分镜', '创意点', '概念来源', '灵感']},
                // 不放泛化的"效果"：落地数据页的关键词里也有它，两边都认就会串页
                {key: 'visual', type: 'bullets', name: '视觉效果', after: 'sketch',
                 kw: ['视觉', '画面', '呈现', '配色', '版式', '海报', '物料', 'KV'],
                 strong: ['视觉', '配色', '版式', '画面', '海报', '呈现', '物料', '字体', '构图']}
            ]
        };
    window.WB_COMP_TYPES = [
            {type: 'ican',  name: 'iCAN 大赛', theme: 'star',
             kw: ['iCAN', 'ican', 'Ican']},
            {type: 'math',  name: '数学建模类', theme: 'math',
             rename: {feature: '模型应用', compete: '方法对比'},
             kw: ['数学建模', '数模', '建模', '运筹', '统计建模']},
            {type: 'art',   name: '艺术设计类', theme: 'morandi',
             // 不放泛化的"设计大赛"：中国大学生计算机设计大赛是软件类赛事，
             // 被它命中就会推成设计风，反而错
             kw: ['广告艺术', '大广赛', '视觉传达', '艺术设计', '数字媒体', '动画', '影视', '文创']},
            {type: 'eng',   name: '工程硬件类', theme: 'star',
             kw: ['电子设计', '电赛', '蓝桥杯', '机器人', '智能制造', '西门子', '机械', '嵌入式',
                  '单片机', '硬件', '电路', '自动化', 'RoboMaster', '工程训练', '智能车']},
            // 国创/大创计划名称里带"创业"两字（创新创业训练计划），但它是科研训练类，
            // 排在经管类前面先命中，不然会被推成商务灰
            {type: 'acad',  name: '学术科研类', theme: 'paper',
             kw: ['创新创业训练', '国创计划', '大创']},
            {type: 'biz',   name: '经管商业类', theme: 'flat',
             kw: ['互联网+', '互联网＋', '创业', '小挑', '服务外包', '商业', '经管', '金融',
                  '供应链', '市场', '营销', '电商', '财务']},
            {type: 'it',    name: '软件信息类', theme: 'star',
             kw: ['信息安全', '计算机设计', '软件', '程序', '算法', '网络', '大数据', '人工智能',
                  '信息技术', '金砖', '技能']},
            {type: 'acad',  name: '学术科研类', theme: 'academic',
             kw: ['挑战杯', '课外学术', '国创', '创新创业训练', '科研', '论文', '学术']}
        ];
    window.WB_COMP_THEME = [
            {kw: ['ican'], theme: 'star'},
            {kw: ['传统文化', '非遗', '非物质文化', '国学', '汉服', '书法', '中医药',
                  '国风', '文物', '戏曲', '古籍', '民俗', '汉字', '中医药'], theme: 'ink'},
            {kw: ['绘本', '书籍', '出版', '展览', '书店', '文艺'], theme: 'literary'},
            {kw: ['文创', '文旅', '手作', '博物馆', '文化创', '乡村振兴'], theme: 'verdant'},
            {kw: ['互联网+', '互联网＋'], theme: 'flat'},
            {kw: ['服务外包'], theme: 'biz'},
            {kw: ['创业计划', '小挑'], theme: 'blackgold'},
            {kw: ['课外学术科技作品', '大挑'], theme: 'redgold'},
            {kw: ['挑战杯'], theme: 'redgold'},
            {kw: ['创新创业训练', '国创计划', '大创'], theme: 'paper'},
            {kw: ['数学建模', '数模', '建模'], theme: 'math'},
            {kw: ['电子设计', '电赛', '嵌入式', '单片机', '电路'], theme: 'star'},
            {kw: ['西门子', '智能制造', '机械', '自动化', '工程训练', '智能车'], theme: 'star'},
            {kw: ['蓝桥杯', '计算机设计', '软件', '程序', '算法'], theme: 'star'},
            {kw: ['广告艺术', '大广赛', '视觉传达', '艺术设计', '数字媒体', '动画', '影视'], theme: 'morandi'},
            {kw: ['包装', '平面', '品牌', '海报', '展陈', '文创产品'], theme: 'clay'},
            {kw: ['信息安全', '网安', '网络安全', '攻防', '漏洞'], theme: 'cyber'},
            {kw: ['机器人', 'robomaster', '人工智能', '深度学习', '机器学习', '神经网络'], theme: 'cyber'},
            {kw: ['金砖', '技能发展', '青年创客'], theme: 'capital'},
            {kw: ['创业', '商业', '融资', '创投', '经管', '金融', '供应链', '市场', '营销', '电商', '财务'], theme: 'biz'},
            {kw: ['论文', '科研', '结题', '开题', '学术'], theme: 'academic'}
        ];
    window.WB_THEME_COLORS = {
            tech:     { deep: '#0F1535', deep2: '#3B2170', primary: '#4A55B8', accent: '#22B8CF', deco: ['#22B8CF', '#F59E0B', '#DB3F72'] },
            ink:      { deep: '#1B1B1B', deep2: '#4A4A4A', primary: '#8B2E2E', accent: '#B98A3C', deco: ['#8B2E2E', '#B98A3C', '#4A5D4E'] },
            medical:  { deep: '#09332F', deep2: '#0E6B60', primary: '#0E9E8C', accent: '#34D3B5', deco: ['#34D3B5', '#F5C86B', '#2E86C1'] },
            edu:      { deep: '#4A2410', deep2: '#8A4B1F', primary: '#E2803A', accent: '#F0B429', deco: ['#F0B429', '#E2803A', '#D45B5B'] },
            agri:     { deep: '#1E3D1A', deep2: '#3E6B2A', primary: '#4E8C3A', accent: '#C9A227', deco: ['#C9A227', '#7BA05B', '#E08A3C'] },
            finance:  { deep: '#0C1A33', deep2: '#1F3864', primary: '#1F3864', accent: '#B8860B', deco: ['#B8860B', '#C99700', '#40607A'] },
            craft:    { deep: '#1F2A30', deep2: '#3D4C55', primary: '#5C6B73', accent: '#E08A38', deco: ['#E08A38', '#A63A2F', '#7A8B5A'] },
            social:   { deep: '#4A2320', deep2: '#8A3F33', primary: '#D46A5C', accent: '#E4A03C', deco: ['#E4A03C', '#D46A5C', '#5E8C7E'] },
            academic: { deep: '#00254D', deep2: '#003F88', primary: '#002FA7', accent: '#2E75B6', deco: ['#2E75B6', '#5B8C5A', '#8B6914'] },
            cyber:    { deep: '#160826', deep2: '#3B2170', primary: '#7C3AED', accent: '#22D3EE', deco: ['#22D3EE', '#A855F7', '#F472B6'] },
            ican:     { deep: '#072C55', deep2: '#0F5C9E', primary: '#0E5EA8', accent: '#2AA9E0', deco: ['#2AA9E0', '#7FC4EE', '#0E5EA8'] },
            biz:      { deep: '#1E242C', deep2: '#3A4654', primary: '#374151', accent: '#6B7280', deco: ['#9AA5B1', '#6B7280', '#C0C8D2'] },
            studio:   { deep: '#111318', deep2: '#2C303C', primary: '#C2185B', accent: '#00ACC1', deco: ['#FF4D6D', '#00E5C0', '#FFC94D'] },
            // 15 套精品（后端会回传 colors，这里是接口拿不到时的兜底）
            star:     { deep: '#06152F', deep2: '#123A6B', primary: '#1F6FB2', accent: '#3FBFEA', deco: ['#3FBFEA', '#7CC4F5', '#1F6FB2'] },
            flat:     { deep: '#0F4C9E', deep2: '#2E7BD6', primary: '#1B6AC9', accent: '#FFB020', deco: ['#FFB020', '#2E9E6B', '#E4572E'] },
            morandi:  { deep: '#3E4C55', deep2: '#6B7A83', primary: '#7C95A6', accent: '#B08C7A', deco: ['#9DAE9E', '#B08C7A', '#A8998C'] },
            clay:     { deep: '#5A4A46', deep2: '#8A736A', primary: '#B08C7A', accent: '#9C8AA5', deco: ['#9C8AA5', '#7D8F69', '#C0A090'] },
            verdant:  { deep: '#EDF4EE', deep2: '#D6E7DA', primary: '#4C9A8A', accent: '#E0A46B', deco: ['#4C9A8A', '#7BA05B', '#E0A46B'] },
            literary: { deep: '#F6EFE2', deep2: '#E8DCC8', primary: '#3E5C6B', accent: '#C87F4A', deco: ['#3E5C6B', '#C87F4A', '#8C7BA6'] },
            ink:      { deep: '#F7F3E8', deep2: '#E8DFC9', primary: '#9E2B25', accent: '#B08D57', deco: ['#9E2B25', '#2F4858', '#B08D57'] }
        };
    window._STREAM_MAP = [
            ['parsed_rules',        'parsedRules',        'analysis'],
            ['similarity_report',   'similarityReport',   'analysis'],
            ['idea_feedback',       'ideaFeedback',       'analysis'],
            ['competitor_analysis', 'competitorAnalysis', 'deep'],
            ['business_model',      'businessModel',      'deep'],
            ['risk_analysis',       'riskAnalysis',       'deep'],
            ['tech_solution',       'techSolution',       'deep'],
            ['implementation_plan', 'implementationPlan', 'deep'],
            ['social_value',        'socialValue',        'deep'],
            ['project_summary',     'projectSummary',     'analysis'],
            ['proposal_outline',    'proposalOutline',    'proposal'],
            ['proposal',            'proposalText',       'proposal'],
            ['judge_feedback',      'judgeFeedback',      'proposal'],
            ['proposal_analysis',   'proposalAnalysis',   'proposal'],
            ['defense_questions',   'defenseQuestions',   'defense'],
            ['ppt_outline',         'pptOutline',         'defense'],
            ['speech_script',       'speechScript',       'defense']
        ];
    window.WB_STAGE_WORD = {
            start:          '开工，先把手头的材料理一理…',
            parsing_rules:  '正在读你们赛事的评分标准…',
            similarity:     '看看有没有人写过一模一样的…',
            idea_scoring:   '给你的创意找一句能记住的定位…',
            analysis:       '把赛题和你的方案对上对…',
            rich_assets:    '先把图表和 PPT 的素材备好…',
            writing:        '正在把创意变成能交的稿子…',
            judging:        '先让 AI 自己当一次评委…',
            expert_review:  '换几位专家轮流挑毛病…',
            diagnosis:      '找出最容易扣分的地方…',
            revision:       '按挑出来的毛病改一遍…',
            defense:        '猜评委待会儿会问你什么…',
            ppt:            '正在排路演 PPT 的骨架…',
            speech:         '写一份能照着念的路演稿…',
            queued:         '正在给你安排生成引擎…',
            done:           '收个尾，马上就好…',
            error:          '这一步卡住了，正在收尾…'
        };
    window.WB_STAGE_SHORT = {
            start: '准备中', parsing_rules: '读评分标准', similarity: '查重比对',
            idea_scoring: '定位创意', analysis: '赛题分析', rich_assets: '备图表素材',
            writing: '写正文', judging: '自评打分', expert_review: '专家评审',
            diagnosis: '找扣分点', revision: '改写润色', defense: '答辩预测',
            ppt: '排 PPT', speech: '写演讲稿', queued: '排队中', running: '生成中',
            pending: '准备中', done: '收尾', finished: '收尾', error: '收尾中', failed: '收尾中'
        };
    window.WB_TEAM_TPL = {
            '工程创新类': '队长（计算机 / 自动化学院）：统筹进度 + 核心算法\n' +
                          '硬件 / 结构：样机设计与加工、可靠性测试\n' +
                          '软件 / 算法：模型训练与接口开发\n' +
                          '调研 / 文档：用户调研、数据采集与材料撰写',
            '创新创业类': '负责人：整体统筹 + 对外对接\n' +
                          '技术：产品原型与技术实现\n' +
                          '市场：用户调研、渠道与定价\n' +
                          '运营 / 财务：成本测算、收支与落地推进',
            '学术类': '第一作者：研究设计与论文主笔\n' +
                      '实验：数据采集与实验验证\n' +
                      '分析：数据处理与结果分析\n' +
                      '文献：文献综述与格式校对',
            '建模类': '建模：模型假设与建立\n' +
                      '求解：算法实现与编程\n' +
                      '写作：论文撰写与排版',
            'default': '队长：统筹进度 + 核心模块\n' +
                       '技术：原型开发与测试\n' +
                       '调研：用户调研与数据\n' +
                       '文档：材料撰写与排版'
        };
    window.WB_ANCHORS = [
            {n: '规则解析', t: 'analysis', id: 'parsedRules'},
            {n: '查重',     t: 'analysis', id: 'similarityReport'},
            {n: '项目简介', t: 'proposal', id: 'projectSummary'},
            {n: '申报书',   t: 'proposal', id: 'proposalText'},
            {n: '诊断',     t: 'proposal', id: 'proposalAnalysis'},
            {n: '评审意见', t: 'proposal', id: 'judgeFeedback'},
            {n: '竞品',     t: 'deep',     id: 'competitorAnalysis'},
            {n: '商业',     t: 'deep',     id: 'businessModel'},
            {n: '风险',     t: 'deep',     id: 'riskAnalysis'},
            {n: '技术方案', t: 'deep',     id: 'techSolution'},
            {n: '实施计划', t: 'deep',     id: 'implementationPlan'},
            {n: '社会价值', t: 'deep',     id: 'socialValue'},
            {n: '图表',     t: 'charts',   id: 'tab-charts'},
            {n: '答辩',     t: 'defense',  id: 'defenseQuestions'},
            {n: 'PPT大纲',  t: 'defense',  id: 'pptOutline'},
            {n: '导出',     t: 'export',   id: 'tab-export'}
        ];
    window.KB_TAG_RULES = [
            ['文化文旅', ['文旅', '苏轼', '景区', '文化旅游', '游客', '博物馆', '传统文化']],
            ['非遗', ['非遗', '传承人', '刺绣', '苏绣', '绣娘', '手艺', '非物质文化']],
            ['人工智能', ['AI', '人工智能', '识别', '模型', '算法', '深度学习', '视觉', '机器学习']],
            ['web网站', ['网站', '网页', 'web', '小程序', '平台', '线上', 'APP', 'APP']],
            ['校园服务', ['校园', '学生', '高校', '大学', '宿舍', '食堂', '图书馆', '同学']],
            ['乡村振兴', ['乡村', '农业', '农户', '种植', '农村', '振兴', '县域', '农产品']],
            ['项目简介', ['项目简介', '项目概述', '本项目', '我们做', '项目是']],
            ['社会价值', ['社会价值', '社会意义', '公益', '带动', '文化自信']],
            ['商业模式', ['商业模式', '收入', '盈利', '收费', '付费', '成本', '变现', '定价', '订阅']],
            ['风险分析', ['风险', '局限', '不足', '挑战', '困难', '尚未', '误报']],
            ['创新点', ['创新', '与众不同', '首次', '独特', '突破']],
            ['实践过程', ['实践', '阶段', '进度', '实施', '落地', '试点', '下一步', '计划']]
        ];
    window.WB_CHART_THEMES = {
            soft: {
                label: '柔和默认',
                series: ['#6B9BC3', '#7BB6A6', '#9C8BC4', '#D9A05B', '#8CBF86', '#C98C94', '#A8C47A'],
                bar: ['#8FB8D9', '#5E87B0'], line: '#6B9BC3', area: 'rgba(107,155,195,.18)',
                text: '#5B6B82', axis: 'rgba(91,107,130,.35)', split: 'rgba(91,107,130,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(91,107,130,.22)', '#1F2A3A'],
                bgL: ['rgba(255,255,255,.55)', 'rgba(244,247,252,.72)'],
                bgD: ['rgba(28,34,52,.45)', 'rgba(18,22,38,.58)']
            },
            tech: {
                label: '科技蓝紫',
                // 与后端 chart_renderer_pro 的 tech 主题一致，改这里要同步后端
                series: ['#818CF8', '#22B8CF', '#C084FC', '#F59E0B', '#34D399', '#FB7185', '#A3E635'],
                bar: ['#67e8f9', '#4f46e5'], line: '#c084fc', area: 'rgba(192,132,252,.22)',
                text: '#93a0c4', axis: 'rgba(148,163,255,.35)', split: 'rgba(148,163,255,.12)',
                tip: ['rgba(10,15,43,.92)', 'rgba(148,163,255,.3)', '#e9eefc'],
                bgL: ['rgba(22,28,62,.62)', 'rgba(8,12,32,.78)'],
                bgD: ['rgba(22,28,62,.62)', 'rgba(8,12,32,.78)']
            },
            green: {
                label: '环保绿',
                series: ['#4F9D7C', '#6FAE86', '#8FBF95', '#B0C97F', '#7FB49E', '#9BCE8E', '#C3D59B'],
                bar: ['#7FBBA0', '#3F8C6E'], line: '#4F9D7C', area: 'rgba(79,157,124,.18)',
                text: '#4A6559', axis: 'rgba(74,101,89,.35)', split: 'rgba(74,101,89,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(74,101,89,.22)', '#1E2F28'],
                bgL: ['rgba(247,252,249,.6)', 'rgba(237,245,240,.74)'],
                bgD: ['rgba(22,40,33,.45)', 'rgba(14,26,22,.58)']
            },
            warm: {
                label: '温暖橙',
                series: ['#C2854E', '#D3A15E', '#BF7F63', '#E0B473', '#A9774F', '#CBA97E', '#D98F5B'],
                bar: ['#E0B473', '#C2854E'], line: '#C2854E', area: 'rgba(194,133,78,.18)',
                text: '#6B563F', axis: 'rgba(107,86,63,.35)', split: 'rgba(107,86,63,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(107,86,63,.22)', '#31251A'],
                bgL: ['rgba(255,251,245,.6)', 'rgba(250,242,232,.74)'],
                bgD: ['rgba(42,32,22,.45)', 'rgba(26,20,14,.58)']
            },
            biz: {
                label: '经典商务',
                series: ['#3F6A94', '#5C7E96', '#7A8FA0', '#94776B', '#5E7B6B', '#836C86', '#6C7A8C'],
                bar: ['#5C7E96', '#33526F'], line: '#3F6A94', area: 'rgba(63,106,148,.18)',
                text: '#42505F', axis: 'rgba(66,80,95,.35)', split: 'rgba(66,80,95,.12)',
                tip: ['rgba(255,255,255,.96)', 'rgba(66,80,95,.22)', '#1C2530'],
                bgL: ['rgba(248,250,252,.6)', 'rgba(240,243,247,.74)'],
                bgD: ['rgba(24,30,42,.45)', 'rgba(16,20,30,.58)']
            }
        };
    window.WB_BG_PRESETS = [
            /* 极光的青+紫和默认底色的光晕撞色，所以绿色那团加重并上移到首屏可见处，
               否则切了看不出区别（实测顶部带色差只有 3.5，跟噪声基线差不多） */
            { id: 'aurora', name: '极光', color: '#070b18', img: 'radial-gradient(1200px 700px at 12% 26%, rgba(56,189,248,.46), transparent 60%), radial-gradient(900px 620px at 82% 16%, rgba(168,85,247,.38), transparent 62%), radial-gradient(1000px 760px at 58% 72%, rgba(52,211,153,.36), transparent 66%)' },
            { id: 'nebula', name: '星云', color: '', img: 'radial-gradient(900px 620px at 78% 22%, rgba(244,114,182,.34), transparent 62%), radial-gradient(1100px 700px at 20% 78%, rgba(59,130,246,.34), transparent 64%), linear-gradient(160deg, #0a0f22, #120b24)' },
            { id: 'ocean', name: '深海', color: '', img: 'radial-gradient(1000px 700px at 50% 0%, rgba(20,184,166,.34), transparent 62%), radial-gradient(900px 700px at 10% 90%, rgba(37,99,235,.30), transparent 66%), linear-gradient(180deg, #04121f, #061a2c)' },
            { id: 'ember', name: '熔岩', color: '', img: 'radial-gradient(900px 620px at 20% 20%, rgba(249,115,22,.32), transparent 60%), radial-gradient(1000px 700px at 80% 80%, rgba(190,24,93,.30), transparent 64%), linear-gradient(160deg, #150a10, #1c0f0a)' },
            { id: 'ink', name: '水墨', color: '', img: 'radial-gradient(1000px 700px at 30% 30%, rgba(148,163,184,.26), transparent 62%), radial-gradient(800px 600px at 75% 70%, rgba(71,85,105,.30), transparent 64%), linear-gradient(180deg, #0b0e14, #10141c)' },
            { id: 'cyber', name: '赛博', color: '', img: 'radial-gradient(900px 600px at 15% 80%, rgba(34,211,238,.34), transparent 60%), radial-gradient(900px 600px at 85% 20%, rgba(217,70,239,.30), transparent 62%), linear-gradient(150deg, #0a0716, #131024)' },
            { id: 'forest', name: '林雾', color: '', img: 'radial-gradient(1000px 700px at 60% 20%, rgba(74,222,128,.26), transparent 62%), radial-gradient(900px 700px at 20% 85%, rgba(21,94,117,.30), transparent 66%), linear-gradient(180deg, #07130f, #0a1712)' },
            { id: 'plain', name: '纯净', color: '', img: 'linear-gradient(180deg, #080b14, #0d1220)' }
        ];
})();
