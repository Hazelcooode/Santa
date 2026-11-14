"""Runtime settings, read once from the environment (and backend/.env if present)."""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

if load_dotenv:
    load_dotenv(BACKEND_DIR / ".env", override=False)
    load_dotenv(REPO_DIR / ".env", override=False)


def _float(name, default):
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return float(default)


def _int(name, default):
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return int(default)


class Settings:
    app_name = "Taimi"
    environment = os.getenv("APP_ENV", "development")
    data_mode = os.getenv("DATA_MODE", "live")
    seed_demo_account = os.getenv("SEED_DEMO_ACCOUNT", "0") == "1"
    auto_price_lookup = os.getenv("AUTO_PRICE_LOOKUP", "0") == "1"
    allowed_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",") if h.strip()]
    agent_name = os.getenv("AGENT_NAME", "Taimi")
    db_path = os.getenv("TAIMI_DB", str(BACKEND_DIR / "data" / "taimi.sqlite3"))
    session_days = _int("SESSION_DAYS", 14)
    cookie_secure = os.getenv("COOKIE_SECURE", "0") == "1"
    cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

    # --- Exa: the only web search source for the agents -------------------
    exa_api_key = os.getenv("EXA_API_KEY", "")
    # live = call Exa (falls back to demo data when budget/keys are missing)
    # cache_only = never spend, only serve cached Exa results, else demo
    # mock = never call Exa (offline demo / tests)
    exa_mode = os.getenv("EXA_MODE", "live")
    exa_total_budget_usd = _float("EXA_TOTAL_BUDGET_USD", 40.0)   # hard stop below the $50 credit
    exa_daily_budget_usd = _float("EXA_DAILY_BUDGET_USD", 4.0)
    exa_user_daily_requests = _int("EXA_USER_DAILY_REQUESTS", 60)
    # Used only when Exa does not report costDollars for a call.
    exa_est_search_usd = _float("EXA_EST_SEARCH_USD", 0.007)
    exa_est_page_usd = _float("EXA_EST_PAGE_USD", 0.001)
    exa_timeout_s = _float("EXA_TIMEOUT_S", 25)

    # --- Optional LLM for casual chat / vision (never used as a search source)
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    gemini_model = os.getenv("MODEL_ID", "") or "gemini-2.0-flash"

    # --- Cloudinary (media side challenge) ---------------------------------
    cloudinary_url = os.getenv("CLOUDINARY_URL", "")
    cloudinary_folder = os.getenv("CLOUDINARY_FOLDER", "taimi")

    # --- Background scheduler ---------------------------------------------
    scheduler_enabled = os.getenv("SCHEDULER", "1") == "1"
    scheduler_interval_s = _int("SCHEDULER_INTERVAL_S", 60)

    test_email = os.getenv("TEST_ACCOUNT_EMAIL", "test@taimi.app")
    test_password = os.getenv("TEST_ACCOUNT_PASSWORD", "taimi-demo-2026")


settings = Settings()
