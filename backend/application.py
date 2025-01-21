from fastapi import FastAPI, HTTPException
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import httpx
import time
import logging

from scripts import Helper

# Initialize FastAPI app
app = FastAPI()
helper=Helper()

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
        result = helper.process_pdf(pdf_bytes)
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
