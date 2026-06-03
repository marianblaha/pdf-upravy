from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
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
    Pôvodný POC endpoint.
    Môžeš ho zatiaľ nechať.
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

                    if re.match(r"SOH:\d+\s*%", text):

                        rect = fitz.Rect(span["bbox"])

                        page.draw_rect(
                            rect,
                            color=(1, 1, 1),
                            fill=(1, 1, 1)
                        )

                        new_text = f"SOH:{soh} %"

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


def extract_pdf_data(text: str):

    def find(pattern):
        m = re.search(
            pattern,
            text,
            re.I | re.S
        )
        return m.group(1).strip() if m else ""

    return {

        # hlavný blok
        "soc": find(r"SOC:(\d+\.\d+)"),
        "packVoltage": find(r"Total voltage:(\d+\.\d+)"),
        "totalCurrent": find(r"Total current:([-\d\.]+)"),

        "maxCellVoltage": find(r"Max voltage:(\d+\.\d+)"),
        "minCellVoltage": find(r"Min voltage:(\d+\.\d+)"),

        "maxVoltageCellNo": find(
            r"Max-voltage cell No\.:(\d+)"
        ),

        "minVoltageCellNo": find(
            r"Min-voltage cell No\.:(.+?)\n"
        ),

        # Voltage sekcia
        "cellCount": find(
            r"VoltageV \((\d+)\)"
        ),

        "cellDelta": find(
            r"Voltage difference:(\d+\.\d+)"
        ),

        # Temperature sekcia
        "tempSensorCount": find(
            r"Temperature℃ \((\d+)\)"
        ),

        "maxTemp": find(
            r"Temperature℃.*?Max:(\d+)"
        ),

        "minTemp": find(
            r"Temperature℃.*?Min:(\d+)"
        ),

        "tempDelta": find(
            r"Temperature difference:(\d+\.\d+)"
        )
    }


@app.post("/parse-html")
async def parse_html(
    html_file: UploadFile = File(...),
    pdf_file: UploadFile = File(...),
    model: str = Form(""),
    soh: str = Form("")
):

    # HTML

    html_bytes = await html_file.read()

    html_text = html_bytes.decode(
        "utf-8",
        errors="ignore"
    )

    result = extract_html_data(
        html_text
    )

    # PDF

    pdf_bytes = await pdf_file.read()

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    pdf_text = ""

    for page in doc:
        pdf_text += page.get_text()

    doc.close()

    pdf_data = extract_pdf_data(
        pdf_text
    )

    # merge

    result.update(pdf_data)

    result["model"] = model
    result["soh"] = soh

    # report date / time

    inspection_date = result.get(
        "inspection_date",
        ""
    )

    if " " in inspection_date:

        report_date, report_time = inspection_date.split(
            " ",
            1
        )

    result["reportDate"] = report_date
    result["reportTime"] = report_time

    return JSONResponse(result)


@app.post("/pdf-text")
async def pdf_text(
    file: UploadFile = File(...)
):

    pdf_bytes = await file.read()

    doc = fitz.open(
        stream=pdf_bytes,
        filetype="pdf"
    )

    text = ""

    for page in doc:
        text += page.get_text()

    doc.close()

    return {
        "text": text
    }

@app.post("/generate-report")
async def generate_report(data: dict):


    buffer = BytesIO()

    c = canvas.Canvas(
        buffer,
        pagesize=A4
    )

    width, height = A4

    #
    # logo
    #

    try:
        c.drawImage(
            "logo.png",
            170,
            height - 170,
            width=250,
            height=120,
            preserveAspectRatio=True,
            mask="auto"
        )
    except:
        pass

    #
    # titulok
    #

    y = height - 210

    c.setFont(
        "Helvetica-Bold",
        22
    )

    c.drawCentredString(
        width / 2,
        y,
        "Battery Health Report"
    )

    y -= 50

    #
    # SOH
    #

    c.setFillColor(
        colors.green
    )

    c.setFont(
        "Helvetica-Bold",
        42
    )

    c.drawCentredString(
        width / 2,
        y,
        f"SOH {data.get('soh','')}%"
    )

    c.setFillColor(
        colors.black
    )

    y -= 70

    #
    # vozidlo
    #

    c.setFont(
        "Helvetica",
        11
    )

    lines = [

        f"VIN: {data.get('vin','')}",
        f"Manufacturer: {data.get('manufacturer','')}",
        f"Model: {data.get('model','')}",
        f"Year: {data.get('year','')}",
        f"Date: {data.get('reportDate','')}",
        f"Time: {data.get('reportTime','')}",

        "",

        "BATTERY",

        f"SOC: {data.get('soc','')} %",
        f"Pack Voltage: {data.get('packVoltage','')} V",
        f"Current: {data.get('totalCurrent','')} A",

        "",

        "CELLS",

        f"Max Cell Voltage: {data.get('maxCellVoltage','')} V",
        f"Min Cell Voltage: {data.get('minCellVoltage','')} V",
        f"Max Cell No: {data.get('maxVoltageCellNo','')}",
        f"Min Cell No: {data.get('minVoltageCellNo','')}",
        f"Cell Count: {data.get('cellCount','')}",
        f"Cell Delta: {data.get('cellDelta','')} V",

        "",

        "TEMPERATURE",

        f"Max Temp: {data.get('maxTemp','')} °C",
        f"Min Temp: {data.get('minTemp','')} °C",
        f"Temp Delta: {data.get('tempDelta','')} °C",
        f"Temp Sensors: {data.get('tempSensorCount','')}"
    ]

    for line in lines:

        if line in [
            "BATTERY",
            "CELLS",
            "TEMPERATURE"
        ]:

            y -= 10

            c.setFont(
                "Helvetica-Bold",
                14
            )

            c.drawString(
                50,
                y,
                line
            )

            c.setFont(
                "Helvetica",
                11
            )

        else:

            c.drawString(
                50,
                y,
                line
            )

        y -= 18

    #
    # footer
    #

    c.setFont(
        "Helvetica",
        9
    )

    c.drawCentredString(
        width / 2,
        30,
        "EV Diagnostika"
    )

    c.save()

    pdf = buffer.getvalue()

    buffer.close()

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
            "attachment; filename=battery-report.pdf"
        }
    )

