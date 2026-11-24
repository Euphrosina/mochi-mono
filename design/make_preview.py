# -*- coding: utf-8 -*-
"""按 type-design-review-SKILL.md「预览图」规范生成 Mochi Kai Mono 样张。
逻辑画布 1000 x H，2 倍输出 -> 2000 x 2H，sRGB PNG。
浅底深字 / 深底浅字各一版。
"""
from PIL import Image, ImageDraw, ImageFont
import os

FONT_PATH = '/usr/share/fonts/opentype/source-han-sans/SourceHanSansSC-Regular.otf'
S = 2                      # 2 倍图
LW, PAD = 1000, 100        # 逻辑宽度 / 安全边距 10%
CW = LW - 2 * PAD          # 内容宽 800
LEFT = PAD

THEMES = {
    'light': dict(bg='#FAF7F2', ink='#2B2622', note='#6B5F57', accent='#C96F4A', faint='#E3DCD2'),
    'dark':  dict(bg='#221E1B', ink='#F7F1E8', note='#C4B7A9', accent='#E9A178', faint='#3A332E'),
}

# 字号阶梯（逻辑 px）
STEPS = [10, 12, 16, 24, 36, 48, 72]
LINE_RATIO = 1.45

PARA = ('圆润软萌的等宽字体，适合写代码，也适合日常阅读。Mochi Kai Mono 在手写楷的起笔顿与收笔出锋上'
        '保留了楷意，又把横竖对比压到一点一五比一，让小字号下的横画不发灰。所有字符共用同一套前进宽度，'
        '汉字正好是两个拉丁宽，注释混排不跳格。字腔留白按等面积控制，转角外圆内圆，钩改短钝圆点，不甩长尾。'
        '基于 Noto Sans Mono CJK SC 派生，SIL OFL 1.1 授权，Regular 与 Bold 两个字重。')

CHARSET_LATIN_UP = list('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
CHARSET_LATIN_LO = list('abcdefghijklmnopqrstuvwxyz')
CHARSET_NUM = list('0123456789') + list('!?#$%&()*+,-./:;<=>@[]^_{|}~')[:16]
CHARSET_AMB = ['0O', '1lI', 'rn m', '==', '!=', '->', '=>', '<=', '&&', '||', '::', '##', '//']
CHARSET_CJK_1 = list('永国文与一十日田口中大上')
CHARSET_CJK_2 = list('下人山火字体萌圆あアㄅㄆ')

SPEC_LADDER = '永 国 文 A g 0 O 1 l I → => == != 0123'


def f(size_logic):
    return ImageFont.truetype(FONT_PATH, max(1, int(round(size_logic * S))))


def px(v):
    return int(round(v * S))


def build(theme_name):
    c = THEMES[theme_name]
    # 先按逻辑坐标布局，记录绘制指令，再一次性输出到 2x 画布
    ops = []
    y = PAD

    def text(x, yy, s, size, color=None, anchor='ls', font=None):
        ops.append(('text', x, yy, s, size, color or c['ink'], anchor, font))

    def rect(x0, y0, x1, y1, fill=None, outline=None, width=1, radius=0):
        ops.append(('rect', x0, y0, x1, y1, fill, outline, width, radius))

    def line(pts, fill=None, width=1):
        ops.append(('line', pts, fill or c['ink'], width))

    def arc(box, start, end, fill=None, width=1):
        ops.append(('arc', box, start, end, fill or c['accent'], width))

    # ---------- 01 头部 ----------
    text(LEFT, y + 52, 'Mochi Kai Mono', 54)
    text(LEFT, y + 100, '萌系手写楷 · 等宽 Regular', 40, c['note'])
    text(LEFT, y + 140, 'v0.1.0  ·  SIL OFL 1.1（待确认）  ·  2026-11-24', 30, c['note'])
    y += 158
    text(LEFT, y + 16, '代用字体 Source Han Sans SC，仅用于验证版式，字形非本字体实际轮廓', 13, c['note'])
    y += 24
    text(LEFT, y + 16, '主预设 手写楷 ｜ 横竖 1:1.15 ｜ 字面率 86~88% ｜ 前进宽度 0.6em / 汉字 1.2em', 13, c['note'])
    y += 24 + 30   # 区块留白 ~ 一个行高

    # ---------- 02 字符集总览 ----------
    text(LEFT, y + 16, '01  字符集总览  ·  统一 em 框对齐，不逐字微调位置', 13, c['note'])
    y += 26
    cell_l = CW / 26.0          # 拉丁 0.6em
    cell_c = cell_l * 2.0       # 汉字 1.2em = 2× 拉丁
    row_h = 34

    def grid_row(chars, cell, size, yy, color=None):
        for i, ch in enumerate(chars):
            cx = LEFT + (i + 0.5) * cell
            text(cx, yy + row_h * 0.72, ch, size, color, 'ms')

    grid_row(CHARSET_LATIN_UP, cell_l, 19, y)
    y += row_h
    grid_row(CHARSET_LATIN_LO, cell_l, 19, y)
    y += row_h
    grid_row(CHARSET_NUM, cell_l, 19, y)
    y += row_h
    grid_row(CHARSET_AMB, cell_c, 16, y, c['accent'])
    y += row_h
    grid_row(CHARSET_CJK_1, cell_c, 26, y)
    y += row_h
    grid_row(CHARSET_CJK_2, cell_c, 26, y)
    y += row_h + 30

    # ---------- 03 字号阶梯 ----------
    text(LEFT, y + 16, '02  字号阶梯  ·  10 / 12 / 16 / 24 / 36 / 48 / 72，行距 1.45×', 13, c['note'])
    y += 26
    for sz in STEPS:
        lh = sz * LINE_RATIO
        # 自适应截断，避免拉伸或压扁
        probe = ImageDraw.Draw(Image.new('RGB', (px(LW), 10)))
        parts = SPEC_LADDER.split(' ')
        while probe.textlength(' '.join(parts), font=f(sz)) / S > CW - 70 and parts:
            parts.pop()
        sample = ' '.join(parts)
        text(LEFT, y + lh * 0.78, sample, sz)
        text(LEFT + CW, y + lh * 0.78, str(sz), 12, c['note'], 'rs')
        y += lh
    y += 30

    # ---------- 04 段落样本 ----------
    text(LEFT, y + 16, '03  段落样本  ·  行宽 30~45 字，行距 1.45×', 13, c['note'])
    y += 26
    para_size = 18
    para_lh = para_size * LINE_RATIO
    import re
    probe = ImageDraw.Draw(Image.new('RGB', (px(LW), 10)))
    font_p = f(para_size)
    tokens = re.findall(r'[A-Za-z0-9\.]+|\s+|.', PARA)
    lines, cur = [], ''
    for tk in tokens:
        trial = cur + tk
        if probe.textlength(trial, font=font_p) / S > CW and cur.strip():
            lines.append(cur.rstrip())
            cur = tk.lstrip() if tk.strip() else ''
        else:
            cur = trial
    if cur.strip():
        lines.append(cur.rstrip())
    for ln in lines:
        text(LEFT, y + para_lh * 0.78, ln, para_size)
        y += para_lh
    y += 30

    # ---------- 05 细节特写（设计参数矢量示意，非代用字体放大） ----------
    text(LEFT, y + 16, '04  细节特写  ·  字腔 / 收笔角度 / 笔画端点（设计参数示意，非最终轮廓）', 13, c['note'])
    y += 26
    box_y = y
    col_w = (CW - 2 * 24) / 3.0

    # 栏 1：「国」字腔示意
    x0 = LEFT
    bx, by, bw, bh = x0 + 12, box_y + 8, 96, 128
    rect(bx, by, bx + bw, by + bh, outline=c['ink'], width=7, radius=15)
    # 内部「玉」：三横一竖一点，端点圆顿
    ix1, ix2 = bx + 24, bx + bw - 24
    for k, yy2 in enumerate([by + 36, by + 66, by + 100]):
        line([(ix1, yy2), (ix2, yy2)], c['ink'], 7)
    line([(bx + bw / 2, by + 26), (bx + bw / 2, by + 108)], c['ink'], 7)
    rect(bx + bw - 34, by + 76, bx + bw - 24, by + 86, fill=c['accent'], radius=4)
    # 字腔引线
    line([(bx + bw + 4, by + 52), (bx + bw + 26, by + 44)], c['accent'], 1.5)
    text(x0, box_y + 154, '国 · 字腔留白 ±10%', 12, c['note'])
    text(x0, box_y + 170, '最小腔宽 ≥ 0.8×笔画宽', 12, c['note'])
    text(x0, box_y + 186, '圆角 R = 0.45×笔画宽', 12, c['note'])

    # 栏 2：笔画端点 / 收笔角度
    x1 = LEFT + col_w + 24
    sy = box_y + 56
    line([(x1 + 10, sy), (x1 + 150, sy)], c['ink'], 12)
    rect(x1 + 4, sy - 6, x1 + 16, sy + 6, fill=c['ink'], radius=6)       # 起笔圆顿
    line([(x1 + 150, sy - 6), (x1 + 166, sy + 12)], c['ink'], 12)         # 20° 圆钝短锋
    rect(x1 + 162, sy + 8, x1 + 172, sy + 18, fill=c['accent'], radius=5)
    arc((x1 + 118, sy - 26, x1 + 178, sy + 34), -30, 40, c['accent'], 1.5)
    text(x1 + 150, sy - 32, '20°', 13, c['accent'])
    text(x1, box_y + 154, '起笔圆角短顿', 12, c['note'])
    text(x1, box_y + 170, '收笔圆钝短锋，方向统一右下', 12, c['note'])
    text(x1, box_y + 186, '横画收笔角度全批一致', 12, c['note'])

    # 栏 3：A 尖顶超调
    x2 = LEFT + 2 * (col_w + 24)
    cap_y = box_y + 30          # 大写高基准
    line([(x2 + 8, cap_y), (x2 + 148, cap_y)], c['accent'], 1.5)
    line([(x2 + 24, box_y + 128), (x2 + 78, cap_y - 5), (x2 + 132, box_y + 128)], c['ink'], 9)
    line([(x2 + 42, box_y + 96), (x2 + 114, box_y + 96)], c['ink'], 9)
    text(x2 + 152, cap_y - 2, '大写高', 11, c['accent'])
    text(x2, box_y + 154, 'A · 尖顶视错觉补偿', 12, c['note'])
    text(x2, box_y + 170, '上下超调 1~1.5%', 12, c['note'])
    text(x2, box_y + 186, 'x-height = 0.65em', 12, c['note'])

    y = box_y + 200

    # ---------- 输出 ----------
    H = y + PAD
    img = Image.new('RGB', (px(LW), px(H)), c['bg'])
    d = ImageDraw.Draw(img)
    for op in ops:
        kind = op[0]
        if kind == 'text':
            _, x, yy, s, size, color, anchor, _f = op
            d.text((px(x), px(yy)), s, font=f(size), fill=color, anchor=anchor)
        elif kind == 'rect':
            _, x0, y0, x1, y1, fill, outline, width, radius = op
            box = (px(x0), px(y0), px(x1), px(y1))
            if radius:
                d.rounded_rectangle(box, radius=px(radius), fill=fill,
                                    outline=outline, width=px(width) if width else 1)
            else:
                d.rectangle(box, fill=fill, outline=outline,
                            width=px(width) if width else 1)
        elif kind == 'line':
            _, pts, fill, width = op
            d.line([(px(a), px(b)) for a, b in pts], fill=fill, width=px(width), joint='curve')
        elif kind == 'arc':
            _, box, st, en, fill, width = op
            d.arc(tuple(px(v) for v in box), st, en, fill=fill, width=px(width))
    out = '/data/workspace/MochiKaiMono-preview-%s.png' % theme_name
    img.save(out, 'PNG', dpi=(144, 144))
    print(theme_name, '| logical', LW, 'x', H, '| output', img.size, '| bytes', os.path.getsize(out))
    return out, H


if __name__ == '__main__':
    for t in ('light', 'dark'):
        build(t)
