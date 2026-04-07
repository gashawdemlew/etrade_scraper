# app/core/scraper.py
import httpx
import os
import json
import logging
from cachetools import TTLCache
from backoff import expo, on_exception
from httpx import HTTPStatusError, RequestError
from .db import get_scraped_tin, upsert_scraped_tin

# Configure logging
# logging.basicConfig(
#     level=logging.DEBUG,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
#     handlers=[logging.FileHandler("scraper.log"), logging.StreamHandler()]
# )

LOG_FILE_PATH = "/tmp/scraper.log"  # Use /tmp for writable file system

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE_PATH),  # Write logs to /tmp/scraper.log
        logging.StreamHandler(),  # Also log to console
    ],
)

class Scraper:
    LEGAL_CONDITION_MAP = {
        "1": "Private",
        "2": "Private Limited Company",
        "3": "Share Company",
        "4": "Commercial Representative",
        "5": "Public Enterprise",
        "6": "Partnership",
        "7": "Cooperatives Association",
        "9": "Trade Sectoral Association",
        "10": "Non Public Enterprise",
        "11": "NGO",
        "12": "Branch of A foreign Chamber of Commerce",
        "13": "Holding Company",
        "14": "Franchising",
        "15": "Border Trade",
        "19": "International Bid Winners Foreign Companies",
        "21": "One Man Private Limited Company"
    }

    STATUS_MAP = {
        0: "Two years have passed since it was renewed and cannot be renewed",
        1: "Can be renewed",
        2: "It can be renewed with fine",
        3: "N/A",
        4: "Empty",
        5: "Active It's not renewal time",
        6: "Canceled"
    }

    def __init__(self, base_url: str = "https://app.etrade.gov.et", cache_ttl=3600, verify_ssl: bool = True):
        self.base_url = base_url
        self.logger = logging.getLogger(self.__class__.__name__)
        self.cache = TTLCache(maxsize=1000, ttl=cache_ttl)
        # Allow disabling SSL verification via constructor or env var ETRADE_INSECURE=1/true
        env_insecure = "1"
        self.verify_ssl = verify_ssl and not env_insecure

    # Retry on both HTTP status errors and transient request errors (network issues)
    @on_exception(expo, (HTTPStatusError, RequestError), max_tries=3, jitter=None)
    async def _make_request(self, url, headers):
        # Pass through verify flag to httpx so caller can disable certificate checks
        async with httpx.AsyncClient(timeout=15.0, verify=self.verify_ssl) as client:
            try:
                response = await client.get(url, headers=headers)
            except RequestError as e:
                # If it's an SSL cert verification error, give an actionable log message
                msg = str(e)
                if "certificate verify failed" in msg.lower() or "certificat" in msg.lower():
                    self.logger.warning(
                        "SSL certificate verification failed for %s. "
                        "If you trust this host in your environment, set ETRADE_INSECURE=1 to disable verification. "
                        "Prefer installing the proper CA bundle instead of disabling verification.",
                        url,
                    )
                else:
                    self.logger.warning(f"Network/request error for {url}: {e}")
                raise

            if response.status_code == 204:  # Handle 204 No Content explicitly
                self.logger.info(f"204 No Content for URL: {url}")
                return None

            response.raise_for_status()  # Raise an error for other 4xx/5xx status codes
            return response

    async def simulate_button_click(self, tin):
        # In-memory cache check
        if tin in self.cache:
            self.logger.debug(f"Cache hit for TIN {tin}")
            return self.cache[tin]

        # Persistent DB cache check
        try:
            db_row = await get_scraped_tin(tin)
            if db_row:
                self.logger.info(f"Found TIN {tin} in DB cache, returning stored data")
                self.cache[tin] = db_row["data"]
                return db_row["data"]
        except Exception as e:
            self.logger.warning(f"DB cache check failed for {tin}: {e}")
        
        url = f"{self.base_url}/api/Registration/GetRegistrationInfoByTin/{tin}/am"
        headers = self._get_headers()

        try:
            response = await self._make_request(url, headers)
            if response is None:  # No content from the scraper
                return None

            data = response.json()
            formatted_data = await self.format_data(data, tin)
            print(formatted_data)
            # persist to in-memory cache and DB
            self.cache[tin] = formatted_data
            try:
                await upsert_scraped_tin(tin, formatted_data)
            except Exception as e:
                self.logger.warning(f"Failed to upsert TIN {tin} to DB: {e}")
            return formatted_data

        except HTTPStatusError as e:
            self.logger.error(f"Request failed for TIN {tin}: {e}")
            return None

    def safe_get(self, data, *keys):
        """Safely access nested dictionary keys, handling lists as well."""
        for key in keys:
            if isinstance(data, dict):  # If data is a dictionary, use get()
                data = data.get(key, None)
            elif isinstance(data, list) and isinstance(key, int):  # If data is a list, use index
                if key < len(data):
                    data = data[key]
                else:
                    return None  # Return None if index is out of range
            else:
                return None  # Return None if data is neither dict nor list or if key is invalid
            if data is None:
                return None  # Return None if intermediate data is None
        return data

    async def format_data(self, initial_data, tin):
        legal_condition_code = initial_data.get("LegalCondtion")
        legal_condition_desc = self.LEGAL_CONDITION_MAP.get(legal_condition_code, "N/A")

        associate_info = initial_data.get("AssociateShortInfos", [{}])[0]
        manager_name = associate_info.get("ManagerName", "N/A")
        manager_name_eng = associate_info.get("ManagerNameEng", "N/A")

        # Format main data structure
        formatted_data = {
            "Tin": tin,
            "LegalCondtion": legal_condition_desc,
            "RegNo": initial_data.get("RegNo"),
            "RegDate": initial_data.get("RegDate"),
            "BusinessName": initial_data.get("BusinessName"),
            "BusinessNameAmh": initial_data.get("BusinessNameAmh"),
            "PaidUpCapital": initial_data.get("PaidUpCapital"),
            "ManagerName": manager_name,
            "ManagerNameEng": manager_name_eng,
            "Businesses": [await self._get_business_data(business, tin) for business in initial_data.get("Businesses", [])]
        }

        self.logger.debug(f"Formatted data for TIN {tin}: {json.dumps(formatted_data, indent=2)}")
        return formatted_data

    async def _get_business_data(self, business, tin):
        business_data = {
            "LicenceNumber": business.get("LicenceNumber"),
            "RenewalDate": business.get("RenewalDate"),
            "RenewedFrom": business.get("RenewedFrom"),
            "RenewedTo": business.get("RenewedTo"),
            "Description": self.safe_get(business, "SubGroups", 0, "Description")
        }

        if business.get("LicenceNumber"):
            additional_data = await self.send_second_request(business["LicenceNumber"], tin)
            if additional_data:
                business_data.update(additional_data)

        return business_data

    def _get_headers(self):
        return {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            # Use the app subdomain referer which matches the UI the browser loads
            'Referer': 'https://app.etrade.gov.et/business-license-checker',
        }

    async def send_second_request(self, license_no, tin):
        cache_key = f"{license_no}_{tin}"
        if cache_key in self.cache:
            self.logger.debug(f"Cache hit for LicenseNo {license_no}")
            return self.cache[cache_key]

        url = f"{self.base_url}/api/BusinessMain/GetBusinessByLicenseNo?LicenseNo={license_no}&Tin={tin}&Lang=en"
        headers = self._get_headers()

        try:
            response = await self._make_request(url, headers)
            data = response.json()
            status_code = data.get("Status")
            status_description = self.STATUS_MAP.get(status_code, "N/A")

            additional_data = {
                "AddressInfo": data.get("AddressInfo") or {},
                "Capital": data.get("Capital"),
                "Status": status_description
            }
            self.cache[cache_key] = additional_data
            return additional_data
        except HTTPStatusError as e:
            self.logger.error(f"Request failed for LicenseNo {license_no}: {e}")
            return None