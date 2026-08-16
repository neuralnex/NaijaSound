"""URL-safe share token helpers."""
from __future__ import annotations

import secrets


def new_share_token() -> str:
    """32-byte URL-safe token, base64-encoded (43 chars). Plenty for a non-secret share link."""
    return secrets.token_urlsafe(32)
