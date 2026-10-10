import io

import pytest
from pypdf import PdfReader

from app.render import render_pdf

PL = "żarówka, ściąga, łódź, certified profile"


@pytest.mark.parametrize(("template", "data", "families"), [
    ("cv.html", {"contact": [[PL]], "experience": [{"title": "x", "right": PL}]}, {"SpaceGrotesk", "Anton", "JetBrainsMono"}),
    ("letter.html", {"date": PL, "role": "x", "letter": [PL]}, {"SpaceGrotesk", "Anton", "JetBrainsMono", "Yellowtail"}),
])
def test_polish_pdf_is_one_page_in_the_kit_fonts(template, data, families):
    # PL lands in the name (Anton, plus Yellowtail on the letter), the body and a mono line.
    r = PdfReader(io.BytesIO(render_pdf({"lang": "pl", "name": PL, "about": PL, **data}, template)))
    assert len(r.pages) == 1
    text = r.pages[0].extract_text()
    assert PL.upper() in text and text.count(PL) >= 2, text
    # A system-font fallback would still extract fine but may draw boxes; only the kit fonts may be embedded.
    fonts = [f.get_object() for f in r.pages[0]["/Resources"]["/Font"].values()]
    assert all(f["/Subtype"] != "/Type3" for f in fonts)
    names = {f["/BaseFont"].split("+")[-1].split("-")[0] for f in fonts}
    assert names == families, names
