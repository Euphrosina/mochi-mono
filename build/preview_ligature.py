#!/usr/bin/env python3
"""Render ligature / icon preview images for Mochi Mono Ligature (needs Playwright + Chromium)."""
import html
import os

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.abspath(os.path.join(HERE, "..", "fonts"))
OUT = os.path.abspath(os.path.join(HERE, "..", "images"))

CSS = """
@font-face{font-family:ML;src:url(file://%s/MochiMonoLigature-Regular.otf);font-weight:400}
@font-face{font-family:ML;src:url(file://%s/MochiMonoLigature-Bold.otf);font-weight:700}
body{margin:0;background:#fff5f8;font-family:ML;color:#52344a}
.card{background:#fff;margin:40px;border-radius:40px;padding:50px 60px;white-space:pre;line-height:1.45}
.mute{color:#aa8296}.pink{color:#ec78a0}.b{font-weight:700}
""" % (FONTS, FONTS)

LIG = "-> --> <-> => ==> <=> >= <= >>= <|> |> ~> <~> </> /* */ ## :: && ||"
HTML = {
    "ligatures": """<div class="card" style="font-size:44px">
<span class="mute" style="font-size:26px">Ligatures (Regular / Bold)</span>
%s
<span class="b">%s</span>
<span class="mute" style="font-size:26px">In code</span>
<span style="font-size:40px">if a != b and x >= 3 and y <= 9:  // 注释
    f = lambda v => v == 0 ? v : v -> v
    xs |> map(f) &amp;&amp; ys &lt;|&gt; zs  /* 繁體字 */</span></div>""" % (html.escape(LIG), html.escape(LIG)),
    "icons": """<div class="card" style="font-size:64px">
<span class="mute" style="font-size:26px">Powerline</span>
&#xE0B0;&#xE0B1;&#xE0B2;&#xE0B3;&#xE0B4;&#xE0B5;&#xE0B6;&#xE0B7;&#xE0B8;&#xE0B9;&#xE0BA;&#xE0BB;&#xE0BC;&#xE0BD;&#xE0BE;&#xE0BF;
<span class="mute" style="font-size:26px">Icons</span>
&#xE0A0; &#xE0A1; &#xE0A2; &#xE0A3; &#xF07B; &#xF07C; &#xF15B; &#xF00C; &#xF00D; &#xF071; &#xF015; &#xF002;
&#xF005; &#xF004; &#xF0E7; &#xF121; &#xF120; &#xF013; &#xF017; &#xF023; &#xF067; &#xF0C9;</div>""",
}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1800, "height": 600}, device_scale_factor=1)
        for name, body in HTML.items():
            # fonts are file:// URLs, so the page itself must be a file:// page too
            html_path = os.path.join(OUT, "_" + name + ".html")
            with open(html_path, "w", encoding="utf-8") as fh:
                fh.write("<html><head><meta charset='utf-8'><style>%s</style></head><body>%s</body></html>" % (CSS, body))
            page.goto("file://" + html_path)
            page.evaluate("document.fonts.ready")
            page.wait_for_timeout(1200)
            page.screenshot(path=os.path.join(OUT, name + ".png"), full_page=True)
            os.remove(html_path)
        browser.close()
    print("wrote previews to", OUT)
