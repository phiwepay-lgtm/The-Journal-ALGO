"""Outbound write guard for any future Vercel journal adapter.

There is intentionally no HTTP client in this project. A future read-only
adapter must call enforce_read_only_request() before constructing a request.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOGGER = logging.getLogger("read_only_guard")
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = True
if not any(isinstance(handler, logging.FileHandler) for handler in LOGGER.handlers):
    file_handler = logging.FileHandler(DATA_DIR / "security.log")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOGGER.addHandler(file_handler)


class ReadOnlyViolation(PermissionError):
    """Raised when a write to a Vercel journal URL is attempted."""


def is_vercel_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == "vercel.app" or hostname.endswith(".vercel.app")


def enforce_read_only_request(method: str, url: str) -> bool:
    """Block POST and every other mutation method targeted at a Vercel URL."""
    normalized_method = method.strip().upper()
    if is_vercel_url(url) and normalized_method in {"POST", "PUT", "PATCH", "DELETE"}:
        LOGGER.error("READ-ONLY VIOLATION BLOCKED | method=%s | url=%s", normalized_method, url)
        raise ReadOnlyViolation("READ-ONLY VIOLATION BLOCKED")
    return True
