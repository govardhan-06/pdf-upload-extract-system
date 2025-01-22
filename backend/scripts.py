from fastapi import HTTPException
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor
import easyocr
import numpy as np
import redis
import hashlib
import cv2
import os
import logging
from dotenv import load_dotenv

load_dotenv()

class Helper:
    def __init__(self):
        # Initialize EasyOCR
        self.reader = easyocr.Reader(["en"], gpu=False)
        
        # Redis setup with connection handling and timeout
        self.redis_client = redis.StrictRedis(
            host=os.getenv("REDIS_HOST"), 
            port=os.getenv("REDIS_PORT"), 
            password=os.getenv("REDIS_PASSWORD"),
            ssl=True,
            decode_responses=True,
            socket_timeout=10
        )
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def get_ocr_cache(self, image_bytes):
        """Retrieve cached OCR result from Redis."""
        cache_key = hashlib.md5(image_bytes).hexdigest()
        cached_result = self.redis_client.get(cache_key)
        if cached_result:
            return eval(cached_result)  # Deserialize cached string
        return None

    def set_ocr_cache(self, image_bytes, ocr_result):
        """Cache OCR result in Redis."""
        cache_key = hashlib.md5(image_bytes).hexdigest()
        self.redis_client.setex(cache_key, 3600, str(ocr_result))  # Cache for 1 hour

    def ocr_image_with_easyocr(self, image_bytes):
        """Perform OCR on an image using EasyOCR."""
        try:
            # Check Redis cache first
            cached_result = self.get_ocr_cache(image_bytes)
            if cached_result:
                return cached_result

            # Convert bytes to numpy array and decode as an image
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                self.logger.error("Failed to decode image")
                return []

            # Perform OCR using EasyOCR
            result = self.reader.readtext(img)
            ocr_output = [
                {
                    "text": text.strip(),
                    "bbox": bbox,  # Bounding box coordinates
                    "confidence": confidence,
                }
                for bbox, text, confidence in result
            ]

            # Cache OCR result
            self.set_ocr_cache(image_bytes, ocr_output)
            return ocr_output
        except Exception as e:
            self.logger.error(f"OCR Error: {str(e)}")
            return []

    def process_page(self, page):
        """Process a single PDF page to extract text and perform OCR if needed."""
        page_chunks = []

        # Extract searchable text with bounding boxes
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") == 0:  # Text block
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text", "").strip()
                        if text:
                            page_chunks.append({
                                "text": text,
                                "bbox": [
                                    span["bbox"][0],  # x0
                                    span["bbox"][1],  # y0 
                                    span["bbox"][2],  # x1
                                    span["bbox"][3],  # y1
                                ],
                                "page": page.number + 1,
                            })

        # Perform OCR for non-searchable PDFs
        if not page_chunks:
            pixmap = page.get_pixmap(dpi=150)  # Adjust DPI for quality/speed tradeoff
            img_bytes = pixmap.tobytes(output="png")
            ocr_result = self.ocr_image_with_easyocr(img_bytes)
            for ocr_item in ocr_result:
                page_chunks.append({
                    "text": ocr_item["text"],
                    "bbox": ocr_item["bbox"],  # Bounding box from OCR
                    "confidence": ocr_item["confidence"],
                    "page": page.number + 1,
                })

        return page_chunks

    def process_pdf(self, pdf_bytes, start_page=1, end_page=None):
        """Process the PDF and extract text within the specified page range."""
        chunks = []
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                total_pages = len(doc)

                # Validate and adjust page range
                start_page = max(start_page, 1)
                end_page = min(end_page or total_pages, total_pages)
                if start_page > end_page:
                    raise HTTPException(status_code=400, detail="Invalid page range specified.")

                # Process pages within the range using multithreading
                with ThreadPoolExecutor(max_workers=min(4, os.cpu_count())) as executor:
                    results = executor.map(self.process_page, doc[start_page - 1:end_page])
                    for page_chunks in results:
                        chunks.extend(page_chunks)

        except fitz.FileDataError:
            raise HTTPException(status_code=400, detail="Invalid PDF file format.")
        except Exception as e:
            self.logger.error(f"Error processing PDF: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

        return chunks, total_pages
