# apps/backend/backend.spec
# Build with:  pyinstaller --clean --noconfirm apps/backend/backend.spec
#
# Spec discoveries belong here, NOT in CLI flags, so the discovery process
# is captured in git history.
#
# NOTE ON pathex: we deliberately use pathex=[] (an empty list, NOT a list
# containing 'src') because `lolalytics_api` is installed via
# `pip install -e .` per pyproject.toml's
# `[tool.setuptools.package-dir] "" = "src"` mapping. PyInstaller resolves
# the import from the installed site-packages entry, not from the source
# tree. Adding the source directory to pathex would create dual-resolution
# ambiguity (install path vs. source path) that breaks in frozen mode where
# the source layout does not exist.

import certifi
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis(
    ['backend.py'],
    pathex=[],  # editable-install layout — see header NOTE ON pathex
    binaries=[],
    datas=[
        # certifi: bundle the CA bundle into the _MEIPASS/certifi/ directory.
        # SSL_CERT_FILE is set at runtime in backend.main() to point here.
        (certifi.where(), 'certifi'),
        # If/when Phase 2/3 needs to ship static assets (champion images, etc.),
        # add tuples here. Mutable runtime files (cache_data.json) belong in
        # platformdirs.user_cache_dir(), NOT in this list (CONTEXT D-11).
    ],
    hiddenimports=[
        # ----- Locked seed (CONTEXT D-08) -----
        # Flask-SocketIO + engineio dynamic async driver loader.
        # Without this: "Invalid async_mode specified" on first Socket.IO connect.
        'engineio.async_drivers.threading',
        # httpx's optional SOCKS proxy support — referenced conditionally by some deps.
        'httpx.socks',
        # websocket-client is used by league_client_websocket.py; collect every
        # submodule because it lazy-loads protocol handlers.
        *collect_submodules('websocket'),
        # requests sometimes needs these on trimmed bundles.
        'charset_normalizer',
        'urllib3',
        'certifi',
        # ----- Phase 1 additions -----
        # The installed editable package and its new resources submodule.
        # collect_submodules('lolalytics_api') would also pick these up, but
        # explicit > implicit in the spec and this survives module-loader
        # edge cases in frozen mode.
        'lolalytics_api',
        'lolalytics_api.resources',
        # ----- Discovery list (uncomment as CI surfaces failures) -----
        # 'engineio.async_drivers',  # parent package, defensive
        # 'engineio',
        # 'socketio',
        # 'flask_socketio',
        # 'dns',  # if any dep pulls dnspython
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # NOTE: Phase 1 local-test discovery (2026-04-14): CONTEXT D-09 tried to
        # exclude the supabase family here, but backend.py still imports
        # `from lolalytics_api.supabase_repo import ...` at module load (per
        # N-03, the full cutover to json_repo.py is Phase 2 work). Excluding
        # supabase made the frozen .exe crash at startup with
        # ModuleNotFoundError. Excludes are re-added in Phase 2 when the
        # supabase_repo import is replaced by json_repo.
        #
        # Phase 2 will restore:
        #     'supabase', 'gotrue', 'postgrest', 'realtime', 'storage3',
        #     'supabase_functions', 'supabase_auth',
        #
        # Locked async_mode='threading' — exclude the alternatives so PyInstaller
        # doesn't waste cycles trying to bundle them.
        'eventlet',
        'gevent',
        # Heavy stdlib leaves we never use:
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='backend-x86_64-pc-windows-msvc',  # Tauri externalBin target-triple
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                # CRITICAL — Pitfall #2. Never flip to True.
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # No black terminal flash on sidecar spawn.
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
