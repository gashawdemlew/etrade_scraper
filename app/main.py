# Here is my main.py
from fastapi import FastAPI
from fastapi import APIRouter, HTTPException, Query, Response
# Debug incoming events
import logging
from scraper import Scraper
from .db import init_db
import uvicorn

app = FastAPI(
    title="Scraper API",
    description="An API to scrape data based on TIN",
    version="1.0",
)


@app.on_event("startup")
async def startup_event():
    # initialize DB tables (creates table if missing)
    await init_db()
    logger.info("Startup: DB initialized")

# Get base URL from environment variables (use app subdomain which serves the checker)
base_url = "https://app.etrade.gov.et"
scraper = Scraper(base_url=base_url)
logger = logging.getLogger(__name__)

@app.get("/scrape", response_model=None)
async def scrape_tin(response: Response, tin: str = Query(..., description="Taxpayer Identification Number (TIN)")):
    """
    Scrape data based on provided TIN, with fallback to scraper if no Athena data is found.
    """
    logger.info(f"Received TIN: {tin}")

    try:
        # Fallback to scraper
        tin_data = await scraper.simulate_button_click(tin)

        if not tin_data:
            logger.info("No content for the provided TIN.")
            response.status_code = 204  # Set status to 204
            return None  # Return no body

        logger.info("Returning data from scraper.")
        return tin_data

    except HTTPException as e:
        logger.error(f"HTTPException for TIN {tin}: {e.detail}")
        raise e
    except Exception as e:
        logger.error(f"Error processing TIN {tin}: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while processing the request")
    
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8011)