from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import Response
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
import json
import io

app = FastAPI()

@app.post("/edit-pdf")
async def edit_pdf(
    file: UploadFile = File(...),
    edits: str = Form(...)
):
    """
    Očakáva PDF súbor a JSON string (edits) vo formáte:
    [{"page": 0, "x": 100, "y": 700, "text": "Chýbajúci údaj"}]
    """
    # 1. Načítanie inštrukcií a pôvodného PDF do pamäte
    edit_data = json.loads(edits)
    original_pdf_bytes = await file.read()
    reader = PdfReader(io.BytesIO(original_pdf_bytes))
    writer = PdfWriter()

    # Zoskupenie úprav podľa strán (ak dopisujete na viaceré strany)
    edits_by_page = {}
    for edit in edit_data:
        page_num = edit.get("page", 0) # Indexované od 0
        if page_num not in edits_by_page:
            edits_by_page[page_num] = []
        edits_by_page[page_num].append(edit)

    # 2. Iterácia cez strany PDF a aplikovanie zmien
    for i, page in enumerate(reader.pages):
        if i in edits_by_page:
            # Vytvorenie prázdneho plátna (overlay) pre aktuálnu stranu
            packet = io.BytesIO()
            # Extrakcia reálnych rozmerov aktuálnej strany
            box = page.mediabox
            width, height = float(box.width), float(box.height)
            
            can = canvas.Canvas(packet, pagesize=(width, height))
            
            # Zápis všetkých textov pre túto stranu
            for edit_item in edits_by_page[i]:
                # Voliteľne: nastavenie fontu (can.setFont("Helvetica", 12))
                can.drawString(edit_item["x"], edit_item["y"], edit_item["text"])
            
            can.save()
            packet.seek(0)
            
            # Načítanie overlay vrstvy a jej zlúčenie s pôvodnou stranou
            overlay_pdf = PdfReader(packet)
            overlay_page = overlay_pdf.pages[0]
            page.merge_page(overlay_page)
        
        # Pridanie (upravenej alebo neupravenej) strany do nového dokumentu
        writer.add_page(page)

    # 3. Zápis do výstupného streamu a odoslanie späť ako PDF
    output_stream = io.BytesIO()
    writer.write(output_stream)
    output_stream.seek(0)

    return Response(content=output_stream.read(), media_type="application/pdf")