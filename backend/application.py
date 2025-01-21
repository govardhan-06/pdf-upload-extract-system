from fastapi import FastAPI, HTTPException
import uvicorn
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
import easyocr
import numpy as np
import redis
import hashlib
import time
import os
import io
import cv2
import logging

# EasyOCR initialization
reader = easyocr.Reader(["en"], gpu=False)

# Redis setup with improved connection handling
redis_client = redis.StrictRedis(host='localhost', port=6379, db=0, decode_responses=True, socket_timeout=5)

# Initialize FastAPI app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Helper function for caching OCR results in Redis
def get_ocr_cache(image_bytes):
    """Get OCR result from Redis cache, if exists."""
    cache_key = hashlib.md5(image_bytes).hexdigest()  # MD5 hash of image bytes as key
    cached_result = redis_client.get(cache_key)
    if cached_result:
        return eval(cached_result)  # Return cached result as Python list
    return None

def set_ocr_cache(image_bytes, ocr_result):
    """Set OCR result in Redis cache."""
    cache_key = hashlib.md5(image_bytes).hexdigest()
    redis_client.setex(cache_key, 3600, str(ocr_result))  # Cache for 1 hour

def ocr_image_with_easyocr(image_bytes):
    """Perform OCR on an image using EasyOCR."""
    try:
        # Check if OCR result is in Redis cache
        cached_result = get_ocr_cache(image_bytes)
        if cached_result:
            return cached_result

        # Convert bytes to numpy array for image processing
        nparr = np.frombuffer(image_bytes, np.uint8)
        # Decode the image using OpenCV
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("Failed to decode image")
            return []
            
        result = reader.readtext(img)
        ocr_output = []
        for detection in result:
            bbox, text, confidence = detection
            ocr_output.append({
                "text": text.strip(),
                "bbox": bbox,  # Bounding box coordinates
                "confidence": confidence,
            })

        # Cache OCR result in Redis
        set_ocr_cache(image_bytes, ocr_output)
        return ocr_output
    except Exception as e:
        logger.error(f"OCR Error: {str(e)}")
        return []

def process_page(page):
    """Process a single page of the PDF, extracting text and images."""
    page_chunks = []

    # Extract searchable text with bounding boxes
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

    # Perform OCR for only non-searchable pdfs
    if not page_chunks:
        pixmap = page.get_pixmap(dpi=150)  # Adjust DPI to balance quality and speed
        img_bytes = pixmap.tobytes(output="png")
        ocr_result = ocr_image_with_easyocr(img_bytes)

        for ocr_item in ocr_result:
            page_chunks.append({
                "text": ocr_item["text"],
                "bbox": ocr_item["bbox"],  # Bounding box from EasyOCR
                "confidence": ocr_item["confidence"],
                "page": page.number + 1
            })

    return page_chunks

def process_pdf(pdf_bytes):
    """Process the PDF file and extract text and bounding boxes."""
    chunks = []
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            with ThreadPoolExecutor(max_workers=4) as executor:  # Limiting number of threads
                results = executor.map(process_page, doc)
                for page_chunks in results:
                    chunks.extend(page_chunks)
    except fitz.FileDataError:
        raise HTTPException(status_code=400, detail="Invalid PDF file format")
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    return chunks

@app.post("/extract/")
async def extract_pdf(pdf_url: str):
    """
    This function is used to extract text from the provided PDF URL.
    """
    # Validate the URL
    if not pdf_url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    async with httpx.AsyncClient() as client:
        try:
            # Download the PDF
            response = await client.get(pdf_url, timeout=10)
            response.raise_for_status()
            pdf_bytes = response.content
        except httpx.RequestError:
            raise HTTPException(status_code=400, detail="Failed to fetch PDF from the provided URL")
    
    try:
        start = time.time()
        result = process_pdf(pdf_bytes)
        end = time.time()
        logger.info(f"Total processing time in seconds: {end - start}")
        return JSONResponse(content={"text_chunks": result}, status_code=200)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.get("/pdf/")
async def get_pdf(pdf_url: str):
    """
    This function is used to retrieve the PDF from the provided URL.
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(pdf_url, timeout=10)
            response.raise_for_status()
            
            return Response(
                content=response.content,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": "inline",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "*",
                    "Cache-Control": "public, max-age=3600"
                }
            )
        except Exception as e:
            logger.error(f"Error fetching PDF: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("application:app", host="0.0.0.0", port=8000, reload=False)  # Disable reload in production
