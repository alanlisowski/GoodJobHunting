import io

from pypdf import PdfReader

from app.render import render_pdf

PL = "żarówka, ściąga, łódź"


def test_polish_pdf_is_one_page_in_the_bundled_font():
    r = PdfReader(io.BytesIO(render_pdf({"lang": "pl", "name": PL, "about": PL})))
    assert len(r.pages) == 1
    assert r.pages[0].extract_text().count(PL) == 2
    # A system-font fallback would still extract fine but may draw boxes; only Lato may be embedded.
    fonts = {f.get_object()["/BaseFont"] for f in r.pages[0]["/Resources"]["/Font"].values()}
    assert fonts and all("Lato" in f for f in fonts), fonts
