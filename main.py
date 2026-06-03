from fastapi.responses import JSONResponse
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
import fitz
import tempfile
import os
import re

app = FastAPI(
    title="PDF SOH Updater",
    version="1.0.0"
)


@app.get("/")
def root():
    return {
        "status": "ok"
    }


@app.post("/update-pdf")
async def update_pdf(
    file: UploadFile = File(...),
    soh: str = Form(...)
):
    """
    Nahradi hodnotu SOH v PDF.
    Napr:
        SOH:55 %
    za
        SOH:87 %
    """

    pdf_bytes = await file.read()

    with tempfile.NamedTemporaryFile(
        delete=False,
        suffix=".pdf"
    ) as tmp:
        tmp.write(pdf_bytes)
        input_path = tmp.name

    output_path = input_path.replace(
        ".pdf",
        "_updated.pdf"
    )

    doc = fitz.open(input_path)

    for page in doc:

        text_dict = page.get_text("dict")

        for block in text_dict.get("blocks", []):

            for line in block.get("lines", []):

                for span in line.get("spans", []):

                    text = span.get("text", "")

                    # najde SOH:xx %
                    if re.match(r"SOH:\d+\s*%", text):

                        rect = fitz.Rect(span["bbox"])

                        # prekry povodny text
                        page.draw_rect(
                            rect,
                            color=(1, 1, 1),
                            fill=(1, 1, 1)
                        )

                        new_text = f"SOH:{soh} %"

                        # mierne vacsie a vyssie
                        font_size = span["size"] + 1

                        page.insert_text(
                            (
                                rect.x0,
                                rect.y0 + font_size - 4
                            ),
                            new_text,
                            fontsize=font_size,
                            fontname="helv",
                            color=(0.0, 0.65, 0.0)
                        )

    doc.save(
        output_path,
        garbage=4,
        deflate=True
    )
    doc.close()

    with open(output_path, "rb") as f:
        result = f.read()

    try:
        os.remove(input_path)
    except:
        pass

    try:
        os.remove(output_path)
    except:
        pass

    return Response(
        content=result,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
            "attachment; filename=updated.pdf"
        }
    )

def extract_html_data(html: str):

    def find(pattern):
        m = re.search(pattern, html, re.I | re.S)
        return m.group(1).strip() if m else ""

    vin = find(
        r'VIN.*?</b>\s*([^<]+)'
    )

    manufacturer_raw = find(
        r'Vehicle manufacturer/model:\s*</b>\s*([^<]+)'
    )

    manufacturer = ""

    if manufacturer_raw:
        manufacturer = manufacturer_raw.split("/")[0].strip()

    year = find(
        r'Year of manufacture:\s*</b>\s*([^<]+)'
    )

    inspection_date = find(
        r'Time and date of inspection.*?</b>\s*([^<]+)'
    )

    return {
        "vin": vin,
        "manufacturer": manufacturer,
        "year": year,
        "inspection_date": inspection_date
    }


@app.post("/parse-html")
async def parse_html(
    file: UploadFile = File(...),
    model: str = Form("")
):

    html_bytes = await file.read()

    html_text = html_bytes.decode(
        "utf-8",
        errors="ignore"
    )

    result = extract_html_data(html_text)

    result["model"] = model

    return JSONResponse(result)