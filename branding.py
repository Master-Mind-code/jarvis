"""
Branding and compatibility helpers for the Orion project.
"""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "Orion"
LEGACY_APP_NAME = "Jarvis"
APP_SLUG = "orion"
LEGACY_APP_SLUG = "jarvis"

UI_FILE_NAME = "orion_ui.html"
LEGACY_UI_FILE_NAME = "jarvis_ui.html"
TRADING_UI_FILE_NAME = "trading_dashboard.html"

DEFAULT_SECRET_TOKEN = "orion_secret_change_me"
ONLINE_STATUS = f"{APP_NAME} online"
LEGACY_ONLINE_STATUS = f"{LEGACY_APP_NAME} online"

TRADING_TOKEN_HEADER = "X-Orion-Token"
LEGACY_TRADING_TOKEN_HEADER = "X-Jarvis-Token"

_COMPAT_ENV_KEYS = (
    "PROVIDER",
    "ANTHROPIC_MODEL",
    "GEMINI_MODEL",
    "SECRET_TOKEN",
    "RPC_TIMEOUT",
    "SERVER_URL",
    "DEVICE_ID",
    "AGENT_MODE",
    "TRADER_MODEL",
    "TRADER_MIN_INTERVAL",
)


def env_key(name: str, legacy: bool = False) -> str:
    prefix = "JARVIS" if legacy else "ORION"
    return f"{prefix}_{name}"


def get_env(name: str, default: str | None = None) -> str | None:
    for key in (env_key(name), env_key(name, legacy=True)):
        value = os.getenv(key)
        if value not in (None, ""):
            return value
    return default


def sync_env_aliases(extra_keys: tuple[str, ...] = ()) -> None:
    for name in _COMPAT_ENV_KEYS + tuple(extra_keys):
        primary = env_key(name)
        legacy = env_key(name, legacy=True)
        primary_value = os.getenv(primary)
        legacy_value = os.getenv(legacy)

        if primary_value and not legacy_value:
            os.environ[legacy] = primary_value
        elif legacy_value and not primary_value:
            os.environ[primary] = legacy_value


def resolve_ui_file(root: Path) -> Path:
    primary = root / UI_FILE_NAME
    if primary.exists():
        return primary

    legacy = root / LEGACY_UI_FILE_NAME
    if legacy.exists():
        return legacy

    return primary
