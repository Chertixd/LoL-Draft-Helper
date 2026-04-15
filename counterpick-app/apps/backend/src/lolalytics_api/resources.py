"""
Path resolution helpers for both dev mode and PyInstaller --onefile bundles.

In a frozen bundle, ``sys._MEIPASS`` is the absolute path to the temp
directory the bootloader extracted resources into. In dev mode, ``__file__``
anchors paths to the source tree.

User-writable directories (cache, logs, persistent data) are NEVER inside
``_MEIPASS`` — that directory is wiped on process exit and is per-launch.
They live under ``platformdirs.user_*_dir()``.

This module is installed as ``lolalytics_api.resources`` via the existing
editable install (``pip install -e .`` in ``apps/backend/``, which picks up
``[tool.setuptools.package-dir] "" = "src"`` from ``pyproject.toml``).

:note: The three ``user_*_dir`` helpers are intentionally kept as three
    distinct functions (not a single ``kind=``-dispatched helper) so call
    sites read and grep more clearly (see 01-CONTEXT.md §"Claude's
    Discretion" bullet 3).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import platformdirs

# Mutable placeholder — Phase 3 (TAURI-01) will swap this for the finalized
# Tauri identifier (e.g. "dev.till.lol-draft-analyzer"). Do NOT inline this
# string anywhere else; import it from here.
LOL_DRAFT_APP_NAME: str = "lol-draft-analyzer"


def _is_frozen() -> bool:
    """
    Return True if running inside a PyInstaller bundle.

    Both checks are required: ``sys.frozen`` alone is set by cx_Freeze /
    py2exe as well, but only PyInstaller also provides ``sys._MEIPASS``.
    This is the canonical PyInstaller idiom per the official docs.

    :return: ``True`` if frozen by PyInstaller, ``False`` otherwise.
    """
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def bundled_resource(relative_path: str) -> Path:
    """
    Resolve a read-only resource that ships inside the bundle.

    In a frozen bundle the base is ``sys._MEIPASS``; in dev mode the base
    is ``apps/backend/`` so that files the spec declares via
    ``datas=[(..., 'certifi')]`` resolve consistently regardless of
    runtime mode.

    :param relative_path: Path relative to the bundle root,
        e.g. ``"certifi/cacert.pem"`` or ``"static/champion_roles.json"``.
    :return: Absolute :class:`pathlib.Path`. The file may or may not
        exist; the caller verifies existence. This function never
        raises.
    """
    if _is_frozen():
        base = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    else:
        # apps/backend/src/lolalytics_api/resources.py -> apps/backend/
        # Three .parent steps:
        #   resources.py -> lolalytics_api/ -> src/ -> apps/backend/
        base = Path(__file__).resolve().parent.parent.parent
    return base / relative_path


def user_cache_dir() -> Path:
    """
    Return the per-user cache directory, creating it if missing.

    On Windows this resolves to
    ``%LOCALAPPDATA%\\lol-draft-analyzer\\Cache``.

    :return: Absolute :class:`pathlib.Path` to an existing directory.
    """
    return Path(
        platformdirs.user_cache_dir(LOL_DRAFT_APP_NAME, ensure_exists=True)
    )


def user_log_dir() -> Path:
    """
    Return the per-user log directory, creating it if missing.

    On Windows this resolves to
    ``%LOCALAPPDATA%\\lol-draft-analyzer\\Logs``.

    :return: Absolute :class:`pathlib.Path` to an existing directory.
    """
    return Path(
        platformdirs.user_log_dir(LOL_DRAFT_APP_NAME, ensure_exists=True)
    )


def user_data_dir() -> Path:
    """
    Return the per-user persistent-data directory, creating it if missing.

    On Windows this resolves to ``%APPDATA%\\lol-draft-analyzer``.

    :return: Absolute :class:`pathlib.Path` to an existing directory.
    """
    return Path(
        platformdirs.user_data_dir(LOL_DRAFT_APP_NAME, ensure_exists=True)
    )
