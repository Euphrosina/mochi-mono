#!/usr/bin/env python3
"""Render README preview images for Mochi Mono (needs Pillow)."""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "..", "fonts")
OUT = os.path.join(HERE, "..", "images")
REG = os.path.join(FONTS, "MochiMono-Regular.otf")
BOLD = os.path.join(FONTS, "MochiMono-Bold.otf")

BG = (255, 245, 248)
INK = (82, 52, 74)
PINK = (236, 120, 160)
MUTE = (170, 130, 150)
CARD = (255, 255, 255)


def font(path, size):
    return ImageFont.truetype(path, size)


def rounded_card(draw, box, fill=CARD, r=28):
    draw.rounded_rectangle(box, radius=r, fill=fill)


def banner():
    W, H = 1600, 760
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    rounded_card(d, (40, 40, W - 40, H - 40), r=48)
    d.text((100, 80), "Mochi Mono", font=font(BOLD, 150), fill=PINK)
    d.text((100, 270), "圆润软萌的等宽字体 · 適合寫程式與日常閱讀", font=font(REG, 56), fill=INK)
    d.text((100, 360), "简体 · 繁體 · English · 0123456789 · あいうえお", font=font(REG, 56), fill=INK)
    d.text((100, 470), "永字八法 愛戀龍鳳 你好世界!", font=font(BOLD, 96), fill=INK)
    d.text((100, 610), "Regular   +   Bold      SIL OFL 1.1", font=font(REG, 40), fill=MUTE)
    im.save(os.path.join(OUT, "banner.png"))


def code():
    W, H = 1600, 900
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    rounded_card(d, (40, 40, W - 40, H - 40), r=40)
    lines = [
        ("# 一起写代码吧", MUTE),
        ("def greet(name: str) -> str:", INK),
        ('    """给可爱的人打招呼"""', MUTE),
        ('    msg = f"你好, {name}! 今天也要加油~"', INK),
        ("    return msg if name != '' else None", INK),
        ("", INK),
        ("for i in range(1, 11):", INK),
        ("    print(greet('Mia'), i ** 2, 0 == O)", INK),
        ("", INK),
        ("# l1I  0O  {} [] () <> => != 繁體字也可以", MUTE),
    ]
    f = font(REG, 44)
    y = 90
    for text, color in lines:
        d.text((100, y), text, font=f, fill=color)
        y += 76
    im.save(os.path.join(OUT, "code.png"))


def weights():
    W, H = 1600, 520
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im)
    rounded_card(d, (40, 40, W - 40, H - 40), r=40)
    d.text((100, 80), "Regular  今天天气很好 Hello 0123", font=font(REG, 76), fill=INK)
    d.text((100, 220), "Bold  今天天气很好 Hello 0123", font=font(BOLD, 76), fill=INK)
    small = "小字号 14 / 16 / 18px: 今天天气很好,我们一起写代码吧 abcdefg 0123456789"
    for i, s in enumerate((14, 16, 18)):
        d.text((100, 350 + i * 40), small, font=font(REG, s), fill=INK)
    im.save(os.path.join(OUT, "weights.png"))


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    banner()
    code()
    weights()
    print("wrote previews to", os.path.abspath(OUT))
