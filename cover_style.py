# -*- coding: utf-8 -*-
"""
cover_style.py —— 按主题自动匹配的 Word 封面背景图。

设计要点：
  1. 用 PIL 现画（渐变 + 几何装饰），不调图像模型 —— 零额度、速度快、风格可参数化。
  2. 六种风格按「赛事名 / 项目名 / 关键词」自动匹配；匹配不到就随机挑一种。
  3. 同一主题用固定 seed，保证同一项目每次导出的封面一致（不会每次都不一样）。
  4. 图片只画背景，不写字 —— 文字由 Word 渲染，保证可编辑、可复制、不模糊。
  5. 底部 40% 统一压一层近白渐变，给标题留出干净的深色文字区，任何风格都可读。

对外主入口：
    cover_path, style_key, ink_rgb = get_cover(topic='助老陪护机器人', ...)
"""
import hashlib
import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

# A4 竖版 @150dpi
W, H = 1240, 1754

# 缓存目录（放在 static 下，便于 http 访问与 .gitignore 忽略）
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'covers')


# ============ 风格库 ============
# c_top / c_mid / c_bot : 竖向渐变三段色
# accent                : 装饰高光色
# ink                   : 封面标题文字色（与风格呼应，保证在浅色区可读）
# motif                 : 装饰主题（决定画什么）
STYLES = {
    'tech': {
        'label': '科技蓝',
        'c_top': (9, 30, 66), 'c_mid': (19, 62, 122), 'c_bot': (30, 92, 168),
        'accent': (72, 176, 255), 'ink': (11, 38, 82), 'motif': 'grid',
    },
    'ink': {
        'label': '水墨中国风',
        'c_top': (238, 233, 221), 'c_mid': (228, 221, 205), 'c_bot': (216, 209, 192),
        'accent': (74, 92, 108), 'ink': (43, 43, 43), 'motif': 'mountains',
    },
    'warm': {
        'label': '暖橙人文',
        'c_top': (196, 78, 44), 'c_mid': (232, 122, 62), 'c_bot': (245, 168, 96),
        'accent': (255, 216, 150), 'ink': (138, 59, 30), 'motif': 'waves',
    },
    'eco': {
        'label': '生态青绿',
        'c_top': (9, 58, 44), 'c_mid': (23, 110, 82), 'c_bot': (72, 158, 118),
        'accent': (130, 226, 178), 'ink': (11, 66, 50), 'motif': 'waves',
    },
    'violet': {
        'label': '紫韵创意',
        'c_top': (58, 32, 104), 'c_mid': (110, 66, 156), 'c_bot': (166, 96, 170),
        'accent': (233, 168, 226), 'ink': (72, 40, 122), 'motif': 'diagonal',
    },
    'minimal': {
        'label': '极简商务',
        'c_top': (226, 232, 240), 'c_mid': (240, 244, 249), 'c_bot': (249, 251, 253),
        'accent': (34, 49, 79), 'ink': (30, 44, 72), 'motif': 'diagonal',
    },
}

# 关键词 → 风格。长词优先（命中后按长度加权）
KEYWORDS = {
    # 科技 / 人工智能 / 硬核技术
    '人工智能': 'tech', 'AI': 'tech', '机器': 'tech', '算法': 'tech', '大数据': 'tech',
    '数据': 'tech', '芯片': 'tech', '传感': 'tech', '物联网': 'tech', '智能': 'tech',
    '软件': 'tech', '区块链': 'tech', '机器人': 'tech', '自动化': 'tech', '视觉': 'tech',
    '无人': 'tech', '算力': 'tech', '模型': 'tech', '识别': 'tech', '嵌入式': 'tech',
    # 农业 / 生态 / 环保 / 生物
    '农业': 'eco', '生态': 'eco', '环保': 'eco', '绿色': 'eco', '低碳': 'eco', '碳': 'eco',
    '生物': 'eco', '种植': 'eco', '养殖': 'eco', '环境': 'eco', '可持续': 'eco',
    '新能源': 'eco', '林业': 'eco', '土壤': 'eco', '水质': 'eco', '食': 'eco',
    # 人文 / 公益 / 医疗 / 教育
    '养老': 'warm', '助老': 'warm', '老人': 'warm', '教育': 'warm', '儿童': 'warm',
    '公益': 'warm', '乡村': 'warm', '振兴': 'warm', '医疗': 'warm', '健康': 'warm',
    '心理': 'warm', '社区': 'warm', '服务': 'warm', '扶': 'warm', '医护': 'warm',
    '康复': 'warm', '残': 'warm', '支教': 'warm', '银发': 'warm',
    # 文化 / 非遗 / 国风
    '文化': 'ink', '非遗': 'ink', '传统': 'ink', '国风': 'ink', '汉服': 'ink',
    '书法': 'ink', '茶': 'ink', '文创': 'ink', '历史': 'ink', '旅游': 'ink',
    '民俗': 'ink', '工艺': 'ink', '古': 'ink', '诗词': 'ink', '博物': 'ink',
    # 创意 / 设计 / 传媒
    '设计': 'violet', '创意': 'violet', '传媒': 'violet', '艺术': 'violet',
    '品牌': 'violet', '营销': 'violet', '短视频': 'violet', '直播': 'violet',
    '游戏': 'violet', '动漫': 'violet', '音乐': 'violet', '影': 'violet',
    '服装': 'violet', '美妆': 'violet', 'IP': 'violet',
    # 商务 / 制造 / 供应链（兜底偏商务）
    '管理': 'minimal', '金融': 'minimal', '供应链': 'minimal', '物流': 'minimal',
    '制造': 'minimal', '机械': 'minimal', '材料': 'minimal', '电商': 'minimal',
    '财务': 'minimal', '供应链金融': 'minimal', '办公': 'minimal', '法务': 'minimal',
}


def pick_style(topic=''):
    """按主题关键词挑风格；都没命中就随机一种（用户要求：可随机、可匹配）。"""
    text = str(topic or '')
    scores = {k: 0 for k in STYLES}
    for kw, style in KEYWORDS.items():
        if kw.lower() in text.lower():
            scores[style] += len(kw) * 2      # 词越长，信号越强
    best = max(scores, key=lambda k: scores[k])
    if scores[best] == 0:
        return random.choice(list(STYLES.keys()))
    return best


def _seed_of(topic, style):
    """同一主题 → 固定 seed，保证封面稳定不跳变。"""
    return int(hashlib.md5(('%s|%s' % (topic, style)).encode('utf-8')).hexdigest()[:8], 16)


# ============ 绘制原语 ============

def _lerp(c1, c2, t):
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def _ease(t):
    """平滑缓动，让渐变过渡更自然。"""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _base_gradient(c_top, c_mid, c_bot):
    img = Image.new('RGB', (W, H))
    d = ImageDraw.Draw(img)
    mid_at = 0.55
    for y in range(H):
        t = y / (H - 1.0)
        if t < mid_at:
            c = _lerp(c_top, c_mid, _ease(t / mid_at))
        else:
            c = _lerp(c_mid, c_bot, _ease((t - mid_at) / (1 - mid_at)))
        d.line([(0, y), (W, y)], fill=c)
    return img


def _blank():
    return Image.new('RGBA', (W, H), (0, 0, 0, 0))


def _glow(layer, cx, cy, r, color, alpha):
    """柔和光晕：画个实心圆再高斯模糊。"""
    r = int(r)
    if r <= 2:
        return
    g = Image.new('RGBA', (2 * r, 2 * r), (0, 0, 0, 0))
    ImageDraw.Draw(g).ellipse([0, 0, 2 * r, 2 * r], fill=tuple(color) + (int(alpha),))
    g = g.filter(ImageFilter.GaussianBlur(r * 0.32))
    layer.alpha_composite(g, dest=(int(cx - r), int(cy - r)))


def _grid(layer, rng, color, alpha, step=64, width=1):
    d = ImageDraw.Draw(layer)
    fill = tuple(color) + (int(alpha),)
    x = 0
    while x < W:
        d.line([(x, 0), (x, H)], fill=fill, width=width)
        x += step
    y = 0
    while y < H:
        d.line([(0, y), (W, y)], fill=fill, width=width)
        y += step
    # 若干高亮节点，避免死板
    for _ in range(rng.randint(10, 18)):
        gx = rng.randrange(0, W, step)
        gy = rng.randrange(0, int(H * 0.42), step)
        rr = rng.randint(3, 6)
        d.ellipse([gx - rr, gy - rr, gx + rr, gy + rr], fill=tuple(color) + (min(255, alpha + 60),))


def _diagonal_lines(layer, rng, color, alpha, count=7, width=2):
    d = ImageDraw.Draw(layer)
    for i in range(count):
        off = rng.randint(-200, 900)
        a = alpha - i * 6
        if a <= 0:
            continue
        d.line([(off, 0), (off + int(H * 0.9), int(H * 0.9))],
               fill=tuple(color) + (int(a),), width=width)


def _waves(layer, rng, color, alpha, amp=46, freq=1.6, ybase=0.30, width=3, layers=4):
    d = ImageDraw.Draw(layer)
    for k in range(layers):
        y0 = H * (ybase + k * 0.055)
        a = int(alpha * (1 - k * 0.16))
        if a <= 4:
            continue
        pts = []
        for x in range(0, W + 8, 8):
            t = x / float(W)
            y = y0 + amp * math.sin(t * math.pi * 2 * freq + k * 0.8)
            pts.append((x, y))
        d.line(pts, fill=tuple(color) + (a,), width=width, joint='curve')


def _mountains(layer, rng, color, alpha, ybase=0.30, peaks=5):
    """水墨远山：两层山脊，远淡近浓。"""
    d = ImageDraw.Draw(layer)
    for k in range(2):
        a = int(alpha * (0.55 if k == 0 else 1.0))
        base_y = H * (ybase + k * 0.075)
        pts = [(0, H)]
        seg = W / float(peaks + k)
        for i in range(peaks + k + 1):
            x = i * seg
            y = base_y - rng.uniform(0.25, 1.0) * (H * 0.10)
            pts.append((x, y))
        pts.append((W, H))
        d.polygon(pts, fill=tuple(color) + (a,))


def _diagonal_blocks(layer, rng, color, alpha):
    """斜切色块（紫韵 / 极简通用）。"""
    d = ImageDraw.Draw(layer)
    for i, (x0, y0, x1, y1, a) in enumerate([
        (0, 0, W * 0.62, 0, alpha),
        (W * 0.38, H * 0.13, W, H * 0.13, alpha * 0.6),
    ]):
        pass
    d.polygon([(0, 0), (W * 0.72, 0), (W * 0.30, H * 0.34), (0, H * 0.20)],
              fill=tuple(color) + (int(alpha * 0.85),))
    d.polygon([(W * 0.55, H * 0.10), (W, H * 0.02), (W, H * 0.26), (W * 0.42, H * 0.30)],
              fill=tuple(color) + (int(alpha * 0.5),))


def _ink_wash(layer, rng, color, alpha):
    """水墨晕染：几个模糊的墨团。"""
    for _ in range(rng.randint(3, 5)):
        cx = rng.uniform(W * 0.1, W * 0.9)
        cy = rng.uniform(H * 0.05, H * 0.40)
        r = rng.uniform(W * 0.10, W * 0.26)
        _glow(layer, cx, cy, r, color, int(alpha * rng.uniform(0.5, 1.0)))


def _bottom_fade(layer, start=0.40, color=(250, 251, 253), max_alpha=238):
    """底部压一层近白渐变，给标题留干净的可读区。"""
    m = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(m)
    y0 = int(H * start)
    span = max(1, H - y0)
    for y in range(y0, H):
        t = (y - y0) / float(span)
        d.line([(0, y), (W, y)], fill=tuple(color) + (int(max_alpha * _ease(t)),))
    layer.alpha_composite(m)


def _accent_rule(layer, color, y=None, thickness=5, alpha=210):
    """浅色区上沿的一条风格色细线，收束视觉。"""
    if y is None:
        y = int(H * 0.455)
    d = ImageDraw.Draw(layer)
    d.line([(int(W * 0.08), y), (int(W * 0.92), y)],
           fill=tuple(color) + (int(alpha),), width=thickness)


# ============ 主绘制 ============

def _render(style_key, seed):
    st = STYLES[style_key]
    rng = random.Random(seed)

    img = _base_gradient(st['c_top'], st['c_mid'], st['c_bot'])
    layer = _blank()

    motif = st['motif']
    accent = st['accent']

    if motif == 'grid':
        _grid(layer, rng, accent, 26, step=rng.choice([56, 64, 72]))
        _glow(layer, W * rng.uniform(0.55, 0.85), H * rng.uniform(0.08, 0.22),
              W * rng.uniform(0.35, 0.5), accent, 92)
        _diagonal_lines(layer, rng, accent, 34, count=rng.randint(4, 7), width=2)
    elif motif == 'mountains':
        _ink_wash(layer, rng, st['accent'], 46)
        _mountains(layer, rng, st['accent'], 84, ybase=0.26, peaks=rng.randint(4, 6))
        _mountains(layer, rng, (58, 72, 88), 52, ybase=0.33, peaks=rng.randint(3, 5))
    elif motif == 'waves':
        _glow(layer, W * rng.uniform(0.2, 0.8), H * rng.uniform(0.06, 0.2),
              W * rng.uniform(0.4, 0.55), accent, 96)
        _waves(layer, rng, (255, 255, 255), 60,
               amp=rng.uniform(34, 54), freq=rng.uniform(1.2, 2.2),
               ybase=0.24, width=rng.randint(2, 4), layers=rng.randint(3, 5))
    elif motif == 'diagonal':
        _diagonal_blocks(layer, rng, accent, 70)
        _glow(layer, W * rng.uniform(0.6, 0.9), H * rng.uniform(0.10, 0.26),
              W * rng.uniform(0.3, 0.45), accent, 78)

    # 通用：底部浅色区 + 一条风格色细线
    _bottom_fade(layer)
    _accent_rule(layer, accent)

    out = Image.alpha_composite(img.convert('RGBA'), layer).convert('RGB')
    return out


def get_cover(topic='', style=None, cache_dir=None):
    """取（必要时生成）封面背景图。

    :param topic: 用来匹配风格 + 固定 seed 的文本（赛事名 + 项目名即可）
    :param style: 强制指定风格键（tech/ink/warm/eco/violet/minimal），None = 自动
    :return: (图片绝对路径, 风格键, 封面标题文字色 RGB 元组)
    """
    style_key = style if style in STYLES else pick_style(topic)
    seed = _seed_of(topic or '', style_key)
    cache_dir = cache_dir or _CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, '%s_%08x.jpg' % (style_key, seed & 0xFFFFFFFF))

    if not os.path.exists(path):
        img = _render(style_key, seed)
        img.save(path, 'JPEG', quality=90, optimize=True)

    return path, style_key, STYLES[style_key]['ink']


def style_label(style_key):
    return STYLES.get(style_key, {}).get('label', style_key)


if __name__ == '__main__':
    # 自测：把六种风格各画一张
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_cover_preview')
    os.makedirs(out, exist_ok=True)
    for k in STYLES:
        p, sk, ink = get_cover('测试主题', style=k, cache_dir=out)
        print('%-8s %-10s ink=%s  %s  %.0fKB' % (
            sk, STYLES[k]['label'], ink, os.path.basename(p),
            os.path.getsize(p) / 1024.0))
    print('预览目录:', out)
