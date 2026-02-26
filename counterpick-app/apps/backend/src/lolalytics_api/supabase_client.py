from functools import lru_cache
from supabase import create_client, Client
from lolalytics_api.config import get_supabase_url, get_supabase_key


@lru_cache(maxsize=1)
def get_supabase_client(prefer_service: bool = True) -> Client:
    url = get_supabase_url()
    key = get_supabase_key(prefer_service=prefer_service)
    return create_client(url, key)




