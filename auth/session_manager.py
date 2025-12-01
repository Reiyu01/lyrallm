"""Utilities for issuing and validating session cookies shared between frontend and backend."""
from __future__ import annotations

import os
import re
import secrets
from typing import Optional

SESSION_COOKIE_NAME = os.getenv("SESSION_COOKIE_NAME", "app_session_id")
SESSION_COOKIE_MAX_AGE = int(os.getenv("SESSION_COOKIE_MAX_AGE", str(60 * 60 * 24 * 365)))
SESSION_COOKIE_PATH = os.getenv("SESSION_COOKIE_PATH", "/")
SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "lax").lower()

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,191}$")


def generate_session_id() -> str:
    """Return a cryptographically random session identifier."""
    return secrets.token_urlsafe(32)


def normalize_session_id(value: Optional[str]) -> Optional[str]:
    """Validate a session id value and return it if acceptable."""
    if not value:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if _SESSION_ID_PATTERN.match(candidate):
        return candidate[:191]
    return None


def cookie_kwargs() -> dict:
    """Common kwargs for Response.set_cookie so settings stay centralized."""
    return {
        "max_age": SESSION_COOKIE_MAX_AGE,
        "expires": SESSION_COOKIE_MAX_AGE,
        "httponly": True,
        "secure": SESSION_COOKIE_SECURE,
        "samesite": SESSION_COOKIE_SAMESITE,
        "path": SESSION_COOKIE_PATH,
    }
