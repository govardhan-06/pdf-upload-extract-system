from fastapi import HTTPException
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor
from paddleocr import PaddleOCR 
from PIL import Image
import numpy as np
import redis
from celery import chord
from celery.result import AsyncResult
import os,io
import logging
from tasks import perform_ocr
from dotenv import load_dotenv

load_dotenv()

class Helper:
    def __init__(self):

        self.TEXT_DENSITY_THRESHOLD = 0.3
        self.MIN_WORD_COUNT = 50

        try:
            # Redis setup with connection handling and timeout
            self.redis_client = redis.StrictRedis(
                host=os.getenv("REDIS_HOST"), 
                port=os.getenv("REDIS_PORT"), 
                password=os.getenv("REDIS_PASSWORD"),
                ssl=False,  #ssl=True for deployment
                decode_responses=True,
                socket_timeout=10
            )
            print("Connected to Redis successfully!")
        except redis.ConnectionError as e:
            print(f"Redis connection failed: {e}")
        except redis.TimeoutError as e:
            print(f"Redis connection timeout: {e}")

        # Set up logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def process_page(self, page):
        """Process a single PDF page to extract text and perform OCR if needed."""
        page_chunks = []

        # Get page dimensions and area
        width, height = page.rect.width, page.rect.height
        page_area = width * height
        text_area = 0
        word_count = 0

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

                        # Calculate area of text span
                        span_width = span["bbox"][2] - span["bbox"][0]
                        span_height = span["bbox"][3] - span["bbox"][1]
                        text_area += span_width * span_height
                        
                        # Count words
                        word_count += len(span.get("text", "").split())
        
        # Calculate text density
        text_density = text_area / page_area if page_area > 0 else 0
        
        # Get image count
        image_count = len(page.get_images())

        # Perform OCR for non-searchable PDFs
        if text_density < self.TEXT_DENSITY_THRESHOLD or word_count < self.MIN_WORD_COUNT:
            try:
                # Prepare image for OCR
                dpi = 150
                zoom = dpi / 72
                matrix = fitz.Matrix(zoom, zoom)
                pixmap = page.get_pixmap(matrix=matrix)
                img_bytes = pixmap.tobytes(output="png")
                
                print("Performing OCR on page", page.number + 1)
                # Create Celery task for OCR
                task = perform_ocr.delay(
                    img_bytes,
                    page.number + 1,
                    page.rect.width,
                    page.rect.height
                )
                print("OCR task ID:", task.id)
                
                # Store task ID in Redis for tracking
                task_key = f"ocr_task:{page.number + 1}"
                self.redis_client.set(task_key, task.id, ex=3600)  # 1 hour expiration
                
                # Note: The actual results will be collected in process_pdf
                return []
                
            except Exception as e:
                self.logger.error(f"OCR error on page {page.number + 1}: {str(e)}")
                return []
                
        return page_chunks

    def process_pdf(self, pdf_bytes, start_page=1, end_page=None):
        """Process the PDF and extract text within the specified page range."""
        chunks = []
        ocr_tasks= []

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
                    
                    # Collect text results and OCR task IDs
                    for page_num, page_chunks in enumerate(results, start=start_page):
                        chunks.extend(page_chunks)
                        
                        # Check if there's a pending OCR task for this page
                        task_key = f"ocr_task:{page_num}"
                        task_id = self.redis_client.get(task_key)
                        if task_id:
                            ocr_tasks.append(task_id)
                
                if ocr_tasks:
                    for task_id in ocr_tasks:
                        result = AsyncResult(task_id)
                        try:
                            ocr_chunks = result.get(timeout=300)  # 5 minutes timeout
                            chunks.extend(ocr_chunks)
                        except Exception as e:
                            self.logger.error(f"Error collecting OCR results: {str(e)}")
                        finally:
                            # Clean up Redis key
                            self.redis_client.delete(f"ocr_task:{task_id}")


        except fitz.FileDataError:
            raise HTTPException(status_code=400, detail="Invalid PDF file format.")
        except Exception as e:
            self.logger.error(f"Error processing PDF: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

        return chunks, total_pages