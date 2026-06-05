from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML
from pathlib import Path
from playwright.async_api import async_playwright

from datetime import datetime
from zoneinfo import ZoneInfo

import fitz
import tempfile
import os
import re

import qrcode
import json
import base64

from io import BytesIO

app = FastAPI(
    title="PDF SOH Updater",
    version="1.0.0"
)

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
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
    
    gps = re.search(
        r'google\.maps\.LatLng\(([\d\.]+),([\d\.]+)\)',
        html
    )

    latitude = gps.group(1) if gps else ""
    longitude = gps.group(2) if gps else ""    

    return {
        "vin": vin,
        "manufacturer": manufacturer,
        "year": year,
        "inspection_date": inspection_date,
        "latitude": latitude,
        "longitude": longitude        
    }


def extract_pdf_data(text: str):

    # print("===- PDF TEXT -===")
    # print(text)
    # print("===============")

    def find(pattern):
        m = re.search(
            pattern,
            text,
            re.I | re.S
        )
        return m.group(1).strip() if m else ""

    return {

        
        # hlavný blok
        "soc": str(int(float(find(r"SOC:(\d+\.\d+)")))),
        "packVoltage": str(round(float(find(r"Total voltage:(\d+\.\d+)")), 1)),
        "totalCurrent": find(r"Total current:([-\d\.]+)"),
        "odometer": find(r"Odometer.*?(\d+)"),

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

    env = Environment(
        loader=FileSystemLoader("templates")
    )

    template = env.get_template(
        "report.html"
    )

    html = template.render(**data)

    return Response(
        content=html,
        media_type="text/html"
    )

@app.get("/preview")
async def preview():

    env = Environment(
        loader=FileSystemLoader("templates")
    )

    template = env.get_template(
        "report.html"
    )

    sample_data = {
        "vin": "TMBJC7NY9PF******",
        "manufacturer": "Skoda",
        "year": "2023",
        "model": "enyaq 80",
        "soh": "92",
        "soc": "49.9",
        "packVoltage": "354.1",
        "maxCellVoltage": "3.692",
        "minCellVoltage": "3.685",
        "cellDelta": "0.007",
        "maxTemp": "25",
        "minTemp": "24",
        "tempDelta": "1.0",
        "reportDate": "2026-06-01",
        "reportTime": "21:25:47"
    }

    return HTMLResponse(
        template.render(**sample_data)
    )

@app.post("/generate-report-pdf")
async def generate_report_pdf(data: dict):

    env = Environment(
        loader=FileSystemLoader("templates")
    )

    template = env.get_template(
        "report.html"
    )

    html = template.render(**data)

    base_path = Path(__file__).resolve().parent

    pdf = HTML(
        string=html,
        base_url=str(base_path)
    ).write_pdf()

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition":
            "attachment; filename=report.pdf"
        }
    )

@app.get("/test-playwright")
async def test_playwright():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        page = await browser.new_page()

        await page.set_content("<h1>Playwright OK</h1>")

        title = await page.text_content("h1")

        await browser.close()

        return {"title": title}

@app.post("/generate-report-pdf-playwright")
async def generate_report_pdf_playwright(
    request: Request,
    data: dict
):

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True,
            executable_path="/usr/bin/chromium",
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        page = await browser.new_page()

        env = Environment(
            loader=FileSystemLoader("templates")
        )

        template = env.get_template(
            "report.html"
        )

        base_url = str(request.base_url).rstrip("/")
        
        report_id = (
            f"EVD-"
            f"{data['manufacturer'].strip()[:2].upper()}-"
            f"{datetime.now(ZoneInfo('Europe/Bratislava')).strftime('%Y%m%d-%H%M')}"
        )
        
        data["report_id"] = report_id
        
        qr_payload = f"""
        Report ID: {report_id}
        SOH: {data['soh']} %
        SOC: {data['soc']} %
        Najazdené km: {data.get('odometer', '')}
        Miesto: {data.get('location', 'Trnava')}
        Vygenerované: {data['reportDate']}
        """
        
        qr = qrcode.make(qr_payload)

        buffer = BytesIO()
        qr.save(buffer, format="PNG")

        qr_base64 = base64.b64encode(
            buffer.getvalue()
        ).decode()

        data["qr_code"] = (
            f"data:image/png;base64,{qr_base64}"
        )        

        html = template.render(
            **data,
            base_url=base_url
        )

        await page.set_content(
            html,
            wait_until="networkidle"
        )

        pdf_bytes = await page.pdf(
            format="A4",
            print_background=True,
            scale=0.90
        )

        await browser.close()

        filename = f"EV_Diagnostika_{data['vin']}_{data['reportDate']}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )