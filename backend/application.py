from fastapi import FastAPI, HTTPException, Query
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
import time
import logging

from scripts import Helper

# Initialize FastAPI app
app = FastAPI()
helper = Helper()

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

@app.post("/extract")
async def extract_pdf(
    pdf_url: str,
    start_page: int = Query(1, ge=1),  # Default to start from the first page
    end_page: int = Query(None, ge=1),  # End page is optional
):
    """
    Extract text from the provided PDF URL with pagination support.
    """
    # Validate the URL
    if not pdf_url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL. Please provide a valid http/https URL.")

    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as client:
        try:
            # Download the PDF
            response = await client.get(pdf_url)
            response.raise_for_status()
            pdf_bytes = response.content
        except httpx.RequestError as e:
            logger.error(f"Failed to fetch PDF: {e}")
            raise HTTPException(status_code=400, detail="Failed to fetch PDF from the provided URL.")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Error fetching PDF: {e}")
            raise HTTPException(status_code=response.status_code, detail="Error downloading the PDF file.")

    try:
        # Process the PDF with pagination
        start = time.time()
        result, totalPages = helper.process_pdf(pdf_bytes, start_page=start_page, end_page=end_page)
        end = time.time()
        print(f"PDF processed in {end - start:.2f} seconds")

        response = {
            "text_chunks": result,
            "current_page_range": (start_page, end_page or len(result)),
            "total_pages": len(result),  # Total pages processed
        }
        return JSONResponse(content=response, status_code=200)
    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")

@app.get("/pdf/")
async def get_pdf(pdf_url: str):
    """
    Retrieve the PDF from the provided URL.
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
    uvicorn.run("application:app", host="0.0.0.0", port=8000, reload=True)  # Disable reload in production
