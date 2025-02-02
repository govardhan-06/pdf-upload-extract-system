from celery import shared_task
from paddleocr import PaddleOCR
import numpy as np
from PIL import Image
import io
import logging

logger = logging.getLogger(__name__)

@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={'max_retries': 3, 'countdown': 60},
    queue='ocr_processing'
)
def perform_ocr(self, page_image: bytes, page_num: int, 
                pdf_width: float, pdf_height: float):
    """Celery task to perform OCR on a page image."""
    try:
        reader = PaddleOCR(use_angle_cls=True, lang='en')

        # Validate input
        if not page_image:
            raise ValueError("Empty page image received")

        image = Image.open(io.BytesIO(page_image))
        image_np = np.array(image)
        
        # Validate image dimensions
        if image_np.size == 0:
            raise ValueError("Invalid image dimensions")

        # Calculate scaling factors
        img_width, img_height = image_np.shape[1], image_np.shape[0]
        scale_x = pdf_width / img_width
        scale_y = pdf_height / img_height
        
        ocr_result = reader.ocr(image_np, cls=True)
        chunks = []
        
        if ocr_result and ocr_result[0]:
            for line in ocr_result[0]:
                if line is None:
                    continue
                
                bbox, text_info = line
                text, confidence = text_info
                
                if not bbox or len(bbox) != 4:
                    continue
                
                # Convert coordinates
                x0 = min(point[0] for point in bbox) * scale_x
                y0 = min(point[1] for point in bbox) * scale_y
                x1 = max(point[0] for point in bbox) * scale_x
                y1 = max(point[1] for point in bbox) * scale_y
                
                if text.strip() and all(coord >= 0 for coord in [x0, y0, x1, y1]):
                    chunks.append({
                        "text": text.strip(),
                        "bbox": [x0, y0, x1, y1],
                        "page": page_num,
                        "confidence": confidence
                    })
        
        logger.info(f"Successfully processed OCR for page {page_num}")
        return chunks
        
    except Exception as e:
        print(f"OCR error on page {page_num}: {str(e)}")
        return []

