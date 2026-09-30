"""CV data -> one A4 PDF. The template is the schema: see templates/cv.html.

Run: python -m app.render cv_pl.yaml output/cv_pl.pdf
"""

import base64
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.sync_api import sync_playwright

APP = Path(__file__).parent
env = Environment(loader=FileSystemLoader(APP / "templates"), autoescape=select_autoescape())
# Inlined as data URIs: set_content pages can't load file:// fonts, and a missing font
# silently falls back to a system one that may lack Polish glyphs.
FONTS = {f.stem: base64.b64encode(f.read_bytes()).decode()
         for f in (APP / "static" / "fonts").glob("*.woff2")}


def render_pdf(data: dict, template: str = "cv.html") -> bytes:
    # ponytail: doesn't enforce one page; overflow shows when you open the PDF. Check page count here if drafts start spilling.
    html = env.get_template(template).render(fonts=FONTS, **data)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        page.evaluate("document.fonts.ready.then(() => true)")
        pdf = page.pdf(prefer_css_page_size=True, print_background=True)
        browser.close()
    return pdf


if __name__ == "__main__":
    src, dst = map(Path, sys.argv[1:3])
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(render_pdf(yaml.safe_load(src.read_text(encoding="utf-8"))))
    print(dst)
