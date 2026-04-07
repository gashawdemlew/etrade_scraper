**Project**
- **Name**: `eTrade Scraper API`
- **Purpose**: Scrape business registration info from the eTrade site by TIN and cache results to avoid repetitive scraping.

**Quick Setup**
- **Install deps**: `python -m pip install -r requirements.txt`
- **Run locally**: `uvicorn main:app --reload --host 0.0.0.0 --port 8011`

**Environment variables**
- **`DATABASE_URL`**: async SQLAlchemy URL. Example Postgres: `postgresql+asyncpg://user:pass@db:5432/dbname`. If not set, the app uses `sqlite+aiosqlite:///./data/app.db`.
- **`ETRADE_INSECURE`**: set to `1`, `true`, or `yes` to disable SSL certificate verification (testing only). Prefer installing the correct CA instead.

**HTTP API**
- `GET /scrape?tin=<TIN>` : Returns JSON scraped data (HTTP 200) or `204 No Content` when site returns no content for that `TIN`.

**Caching & Persistence**
- In-memory cache: `cachetools.TTLCache` (default TTL = 3600s) to reduce repeat work within the process.
- Persistent cache: `scraped_tins` table in the configured database. The scraper checks DB before scraping and upserts results after successful scraping.
- DB table columns: `tin` (primary key), `data` (JSON), `updated_at` (timestamp).

**Files changed / added**
- `main.py` : calls `init_db()` on startup and exposes the `/scrape` endpoint.
- `scraper.py` : checks DB cache (`get_scraped_tin`) before scraping, upserts scraped results (`upsert_scraped_tin`). Default `base_url` set to `https://app.etrade.gov.et`.
- `db.py` : new async DB helper using SQLAlchemy (placed at `app/db.py`).
- `requirements.txt` : app dependencies.
- `Dockerfile` : simple image to run the app.
- `README.md` : this file.

**Docker**
- Build: `docker build -t etrade-scraper .`
- Run (example using Postgres):
  - `docker run -e DATABASE_URL=postgresql+asyncpg://user:pass@db:5432/dbname -p 8011:8011 etrade-scraper`

**SSL / Certificate issues**
- If you see `certificate verify failed` logs, either:
  - Install the proper CA bundle on your host/container, or
  - For quick local testing only, set `ETRADE_INSECURE=1` (disables verification).

**Logs & Troubleshooting**
- Scraper logs are written to `/tmp/scraper.log` (and stdout).
- If a TIN returns `204`, the remote endpoint returned no content for that TIN.
- To force re-scrape for a TIN, delete the row from the `scraped_tins` table or update code to bypass DB cache.

**Next steps (suggested)**
- Add TTL / freshness column to DB to automatically re-scrape stale entries.
- Add Alembic migrations for schema management in production.

If you'd like, I can add a `docker-compose.yml` with Postgres and a simple test runner to exercise the `/scrape` endpoint.
