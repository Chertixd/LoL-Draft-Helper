"""lolalytics_api — runtime data layer for the desktop client.

Only ``json_repo`` (CDN reads) and ``resources`` (platformdirs paths) are on
the runtime path. The legacy Lolalytics scraper that used to live in
``main.py`` is gone — installed clients never call lolalytics.com.
The ``supabase_client`` / ``supabase_repo`` / ``config`` modules stay in
source for the Phase 2 contract tests but are excluded from the
PyInstaller bundle (see backend.spec excludes).
"""

__version__ = "0.0.7"
