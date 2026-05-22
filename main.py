import io
import os
import re
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import requests

app = FastAPI()


# Definujeme, ako vyzerajú prichádzajúce dáta z n8n
class EmailInput(BaseModel):
    text: str


@app.post("/process-pdf")
async def process_pdf(payload: EmailInput):
    # 1. Nájdenie URL adresy v texte mailu pomocou regulárneho výrazu
    # Tento výraz vyhľadá čokoľvek, čo začína na http:// alebo https://
    urls = re.findall(r"(https?://[^\s"']+)", payload.text)

    if not urls:
        raise HTTPException(
            status_code=400, detail="V texte e-mailu sa nenašiel žiadny odkaz."
        )

    # Vezmeme prvý nájdený odkaz
    download_url = urls[0]

    try:
        # 2. Python sám stiahne PDF súbor z odkazu do pamäte
        response = requests.get(download_url, timeout=30)
        response.raise_for_status()  # Skontroluje, či stiahnutie prebehlo v poriadku
        pdf_data = response.content
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Nepodarilo sa stiahnuť PDF z odkazu: {str(e)}"
        )

    # 3. TU BUDE TVOJ KÓD NA ÚPRAVU PDF (pypdf, atď.)
    # Pre test posielame stiahnutý súbor bez zmeny ďalej
    modified_pdf = pdf_data

    # 4. Odoslanie hotového upraveného PDF späť do n8n
    return StreamingResponse(
        io.BytesIO(modified_pdf),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=upravene_doc.pdf"},
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)