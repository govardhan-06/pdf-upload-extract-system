from fastapi import HTTPException
import fitz
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import redis
from paddleocr import PaddleOCR
import os
import logging
from PIL import Image
import io
from typing import List, Dict, Any, Tuple
import hashlib
import gc
from dotenv import load_dotenv

load_dotenv()

class Helper:
    def __init__(self):
        self.TEXT_DENSITY_THRESHOLD = 0.3
        self.MIN_WORD_COUNT = 50
        self.CHUNK_SIZE = 5
        self.OCR_BATCH_SIZE = 3
        self.OCR_DPI = 150
        self.CACHE_EXPIRY = 3600

        # Initialize OCR once
        self.reader = PaddleOCR(
            use_angle_cls=True,
            lang='en',
            use_gpu=True if os.getenv('USE_GPU', 'false').lower() == 'true' else False,
            enable_mkldnn=True
        )

        # Redis setup
        self.redis_client = redis.StrictRedis(
            host=os.getenv("REDIS_HOST"),
            port=os.getenv("REDIS_PORT"),
            password=os.getenv("REDIS_PASSWORD"),
            ssl=False,
            decode_responses=True,
            socket_timeout=10,
            socket_keepalive=True,
            health_check_interval=30
        )

        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)

    def _get_cache_key(self, image_bytes: bytes, page_num: int) -> str:
        return f"ocr:{hashlib.md5(image_bytes.hex().encode()).hexdigest()}:{page_num}"

    def _process_ocr_batch(self, images: List[Tuple[bytes, int, float, float]]) -> List[Dict[str, Any]]:
        """Process a batch of images with OCR"""
        all_chunks = []
        for img_data, page_num, pdf_width, pdf_height in images:
            try:
                image = Image.open(io.BytesIO(img_data))
                image_np = np.array(image)
                
                img_width, img_height = image_np.shape[1], image_np.shape[0]
                scale_x = pdf_width / img_width
                scale_y = pdf_height / img_height
                
                ocr_result = self.reader.ocr(image_np, cls=True)
                
                if ocr_result and ocr_result[0]:
                    chunks = []
                    for line in ocr_result[0]:
                        if line and len(line) == 2:
                            bbox, (text, confidence) = line
                            if bbox and len(bbox) == 4:
                                x0 = min(point[0] for point in bbox) * scale_x
                                y0 = min(point[1] for point in bbox) * scale_y
                                x1 = max(point[0] for point in bbox) * scale_x
                                y1 = max(point[1] for point in bbox) * scale_y
                                
                                if text.strip() and confidence > 0.5:
                                    chunks.append({
                                        "text": text.strip(),
                                        "bbox": [x0, y0, x1, y1],
                                        "page": page_num,
                                        "confidence": confidence
                                    })
                    all_chunks.extend(chunks)
                
                image.close()
                del image_np
                gc.collect()
                
            except Exception as e:
                self.logger.error(f"OCR error on page {page_num}: {str(e)}")
                continue
                
        return all_chunks

    def process_page(self, page) -> List[Dict[str, Any]]:
        """Process a single PDF page"""
        page_chunks = []
        width, height = page.rect.width, page.rect.height
        page_area = width * height
        text_area = 0
        word_count = 0

        try:
            # Extract searchable text
            text_dict = page.get_text("dict")
            for block in text_dict.get("blocks", []):
                if block.get("type") == 0:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "").strip()
                            if text:
                                bbox = span["bbox"]
                                page_chunks.append({
                                    "text": text,
                                    "bbox": bbox,
                                    "page": page.number + 1,
                                })
                                text_area += (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                                word_count += len(text.split())

            text_density = text_area / page_area if page_area > 0 else 0
            image_count = len(page.get_images())

            if image_count>2 and text_density < self.TEXT_DENSITY_THRESHOLD or word_count < self.MIN_WORD_COUNT:
                zoom = self.OCR_DPI / 72
                matrix = fitz.Matrix(zoom, zoom)
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                img_bytes = pixmap.tobytes(output="png")
                
                cache_key = self._get_cache_key(img_bytes, page.number)
                cached_result = self.redis_client.get(cache_key)
                
                if cached_result:
                    return eval(cached_result)
                
                ocr_chunks = self._process_ocr_batch([(img_bytes, page.number + 1, width, height)])
                if ocr_chunks:
                    self.redis_client.setex(cache_key, self.CACHE_EXPIRY, str(ocr_chunks))
                    return ocr_chunks
                
                pixmap = None
                gc.collect()

        except Exception as e:
            self.logger.error(f"Page processing error: {str(e)}")
            return []

        return page_chunks

    def process_pdf(self, pdf_bytes: bytes, start_page: int = 1, end_page: int = None) -> Tuple[List[Dict[str, Any]], int]:
        """Process PDF with optimized chunking"""
        chunks = []
        total_pages = 0
        
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                total_pages = len(doc)
                start_page = max(1, min(start_page, total_pages))
                end_page = min(end_page or total_pages, total_pages)
                
                if start_page > end_page:
                    raise HTTPException(status_code=400, detail="Invalid page range")

                page_ranges = range(start_page - 1, end_page)
                chunk_ranges = [page_ranges[i:i + self.CHUNK_SIZE] 
                              for i in range(0, len(page_ranges), self.CHUNK_SIZE)]

                max_workers = min(os.cpu_count() or 4, 8)
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = [
                        executor.submit(self.process_page, doc[page_num])
                        for chunk_range in chunk_ranges
                        for page_num in chunk_range
                    ]
                    
                    for future in as_completed(futures):
                        if result := future.result():
                            chunks.extend(result)

        except Exception as e:
            self.logger.error(f"PDF processing error: {str(e)}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            gc.collect()

        return chunks, total_pages