from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import Response
import fitz
import tempfile
import os

app = FastAPI()


@app.get("/")
def root():
    return {"status": "ok"}


@app.post("/update-pdf")
async def update_pdf(
    file: UploadFile = File(...),
    soh: str = Form(...)
):
    pdf_bytes = await file.read()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(pdf_bytes)
        input_file = tmp.name

    output_file = input_file.replace(".pdf", "_out.pdf")

    doc = fitz.open(input_file)

    for page in doc:

        matches = page.search_for("SOH:0 %")

        for rect in matches:

            page.draw_rect(
                rect,
                color=(1, 1, 1),
                fill=(1, 1, 1)
            )

            page.insert_text(
                (rect.x0, rect.y1 - 2),
                f"SOH:{soh} %",
                fontsize=12
            )

    doc.save(output_file)
    doc.close()

    with open(output_file, "rb") as f:
        result = f.read()

    os.remove(input_file)
    os.remove(output_file)

    return Response(
        content=result,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
            "attachment; filename=updated.pdf"
        }
    )