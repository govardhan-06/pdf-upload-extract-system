from fastapi import FastAPI, HTTPException
import uvicorn
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pytesseract
import io
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import requests
from functools import lru_cache

app = FastAPI()

pytesseract.pytesseract.tesseract_cmd = r'D:\Tesseract-OCR\tesseract.exe'

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Caching to avoid reprocessing duplicate images
@lru_cache(maxsize=128)
def ocr_image(image_bytes, config=None):
    """Perform OCR on an image with custom configuration."""
    image = Image.open(io.BytesIO(image_bytes)).convert("L")
    # Apply image preprocessing for better OCR
    image = image.point(lambda x: 0 if x < 128 else 255)  # Binarize
    return pytesseract.image_to_string(image, config=config)

def process_page(page):
    """Process a single page of the PDF, extracting text and images."""
    page_chunks = []

    # Extract searchable text with bounding boxes
    # Use a more granular text extraction approach
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") == 0:  # Text block
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        page_chunks.append({
                            "text": span["text"].strip(),
                            "bbox": [
                                span["bbox"][0],  # x0
                                span["bbox"][1],  # y0 
                                span["bbox"][2],  # x1
                                span["bbox"][3]   # y1
                            ],
                            "page": page.number + 1
                        })

    # Improve OCR handling
    # Only perform OCR if no text was extracted
    if not page_chunks:
        # Increase DPI for better OCR quality
        pixmap = page.get_pixmap(dpi=300)  # Increased from 150
        img_bytes = pixmap.tobytes(output="png")
        
        # Configure Tesseract for better accuracy
        custom_config = '--psm 6 --oem 3'  # Page segmentation mode 6 (Assume uniform text block) with LSTM OCR Engine
        ocr_text = ocr_image(img_bytes, custom_config)
        
        if ocr_text.strip():
            # Split OCR text into paragraphs for more manageable chunks
            paragraphs = [p.strip() for p in ocr_text.split('\n\n') if p.strip()]
            for paragraph in paragraphs:
                page_chunks.append({
                    "text": paragraph,
                    "bbox": None,  # OCR text doesn't have bounding boxes
                    "page": page.number + 1
                })

    return page_chunks

def process_pdf(pdf_bytes):
    """Process the PDF file and extract text and bounding boxes."""
    chunks = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            with ThreadPoolExecutor(max_workers=min(8, len(doc))) as executor:
                results = executor.map(process_page, doc)
                for page_chunks in results:
                    chunks.extend(page_chunks)
    except fitz.FileDataError:
        raise HTTPException(status_code=400, detail="Invalid PDF file format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    return chunks

@app.post("/extract/")
async def extract_pdf(pdf_url: str):
    # Validate the URL
    if not pdf_url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        # Download the PDF
        response = requests.get(pdf_url, timeout=10)
        response.raise_for_status()
        pdf_bytes = response.content

        # Save the PDF to a file
        with open("./pdf.pdf", "wb") as f:
            f.write(pdf_bytes)
    except requests.exceptions.RequestException:
        raise HTTPException(status_code=400, detail="Failed to fetch PDF from the provided URL")
    
    try:
        result = process_pdf(pdf_bytes)
        return JSONResponse(content={"text_chunks": result}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("application:app", host="0.0.0.0", port=8000, reload=True)
