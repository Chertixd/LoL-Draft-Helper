import os
from dotenv import load_dotenv

# Load environment variables from .env if present
load_dotenv()


def get_supabase_url() -> str:
    url = os.getenv("SUPABASE_URL")
    if not url:
        raise RuntimeError("SUPABASE_URL is not set")
    return url


def get_supabase_key(prefer_service: bool = True) -> str:
    """
    Returns the Supabase API key.
    - If prefer_service is True, use SUPABASE_SERVICE_ROLE_KEY if set, otherwise fall back to SUPABASE_ANON_KEY.
    - If prefer_service is False, use SUPABASE_ANON_KEY.
    """
    if prefer_service:
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
    else:
        key = os.getenv("SUPABASE_ANON_KEY")

    if not key:
        raise RuntimeError(
            "No Supabase key found. Set SUPABASE_SERVICE_ROLE_KEY (server) or SUPABASE_ANON_KEY (public)."
        )
    return key




