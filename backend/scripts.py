from fastapi import HTTPException
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor
import easyocr
import numpy as np
import redis
import hashlib
import cv2, os
import logging
from dotenv import load_dotenv

load_dotenv()

class Helper:
    def __init__(self):
        # Initialize EasyOCR
        self.reader = easyocr.Reader(["en"], gpu=False)
        
        # Redis setup with improved connection handling
        self.redis_client = redis.StrictRedis(
            host=os.getenv("REDIS_HOST"), 
            port=os.getenv("REDIS_PORT"), 
            password=os.getenv("REDIS_PASSWORD"),
            ssl=True,
            decode_responses=True ,
            socket_timeout=5
        )
        
        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def get_ocr_cache(self, image_bytes):
        """Get OCR result from Redis cache, if exists."""
        cache_key = hashlib.md5(image_bytes).hexdigest()  # MD5 hash of image bytes as key
        cached_result = self.redis_client.get(cache_key)
        if cached_result:
            return eval(cached_result)  # Return cached result as Python list
        return None

    def set_ocr_cache(self, image_bytes, ocr_result):
        """Set OCR result in Redis cache."""
        cache_key = hashlib.md5(image_bytes).hexdigest()
        self.redis_client.setex(cache_key, 3600, str(ocr_result))  # Cache for 1 hour

    def ocr_image_with_easyocr(self, image_bytes):
        """Perform OCR on an image using EasyOCR."""
        try:
            # Check if OCR result is in Redis cache
            cached_result = self.get_ocr_cache(image_bytes)
            if cached_result:
                return cached_result

            # Convert bytes to numpy array for image processing
            nparr = np.frombuffer(image_bytes, np.uint8)
            # Decode the image using OpenCV
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                self.logger.error("Failed to decode image")
                return []
                
            result = self.reader.readtext(img)
            ocr_output = []
            for detection in result:
                bbox, text, confidence = detection
                ocr_output.append({
                    "text": text.strip(),
                    "bbox": bbox,  # Bounding box coordinates
                    "confidence": confidence,
                })

            # Cache OCR result in Redis
            self.set_ocr_cache(image_bytes, ocr_output)
            return ocr_output
        except Exception as e:
            self.logger.error(f"OCR Error: {str(e)}")
            return []

    def process_page(self, page):
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
            ocr_result = self.ocr_image_with_easyocr(img_bytes)

            for ocr_item in ocr_result:
                page_chunks.append({
                    "text": ocr_item["text"],
                    "bbox": ocr_item["bbox"],  # Bounding box from EasyOCR
                    "confidence": ocr_item["confidence"],
                    "page": page.number + 1
                })

        return page_chunks

    def process_pdf(self, pdf_bytes):
        """Process the PDF file and extract text and bounding boxes."""
        chunks = []
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                with ThreadPoolExecutor(max_workers=min(4, os.cpu_count())) as executor:
                    results = executor.map(self.process_page, doc)
                    for page_chunks in results:
                        chunks.extend(page_chunks)
        except fitz.FileDataError:
            raise HTTPException(status_code=400, detail="Invalid PDF file format")
        except Exception as e:
            self.logger.error(f"Error processing PDF: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
        return chunks
