"""Dropbox OAuth2 (PKCE-less, server-side flow with offline access).

Flow:
  1. /api/auth/dropbox/start -> redirect user to build_authorize_url()
  2. Dropbox redirects back to /api/auth/dropbox/callback?code=...&state=...
  3. exchange_code_for_tokens(code) returns a refresh token + initial access token
  4. save_tokens() persists them to backend/data/dropbox_tokens.json (gitignored)
  5. DropboxClient uses refresh token to mint short-lived access tokens on demand
"""

from __future__ import annotations

import json
import secrets
from dataclasses import asdict, dataclass
from typing import Any

from dropbox import DropboxOAuth2Flow

from app.config import settings


@dataclass
class StoredTokens:
    refresh_token: str
    access_token: str | None = None
    expires_at: float | None = None
    account_id: str | None = None
    user_id: str | None = None


def _csrf_session() -> dict[str, Any]:
    return {}


def _flow(csrf_holder: dict[str, Any]) -> DropboxOAuth2Flow:
    if not settings.dropbox_app_key or not settings.dropbox_app_secret:
        raise RuntimeError(
            "Dropbox app key/secret not configured. "
            "Set PCA_DROPBOX_APP_KEY and PCA_DROPBOX_APP_SECRET in backend/.env "
            "(see backend/.env.example)."
        )
    return DropboxOAuth2Flow(
        consumer_key=settings.dropbox_app_key,
        consumer_secret=settings.dropbox_app_secret,
        redirect_uri=settings.dropbox_redirect_uri,
        session=csrf_holder,
        csrf_token_session_key="dropbox-auth-csrf-token",
        token_access_type="offline",
    )


# In-memory CSRF holder, keyed by `state` value we generate. Suitable for a
# single-user local app; not safe for multi-user.
_pending: dict[str, dict[str, Any]] = {}


def build_authorize_url() -> str:
    state = secrets.token_urlsafe(24)
    holder = _csrf_session()
    flow = _flow(holder)
    url = flow.start(url_state=state)
    _pending[state] = holder
    return url


def exchange_code_for_tokens(query_params: dict[str, str]) -> StoredTokens:
    state_full = query_params.get("state", "")
    state = state_full.split("|", 1)[0] if state_full else ""
    holder = _pending.pop(state, None)
    if holder is None:
        raise RuntimeError("Unknown or expired OAuth state — start the flow again.")
    flow = _flow(holder)
    result = flow.finish(query_params)
    return StoredTokens(
        refresh_token=result.refresh_token,
        access_token=result.access_token,
        expires_at=result.expires_at.timestamp() if result.expires_at else None,
        account_id=result.account_id,
        user_id=result.user_id,
    )


def save_tokens(t: StoredTokens) -> None:
    settings.tokens_path.parent.mkdir(parents=True, exist_ok=True)
    settings.tokens_path.write_text(json.dumps(asdict(t), indent=2))


def load_tokens() -> StoredTokens | None:
    if not settings.tokens_path.exists():
        return None
    raw = json.loads(settings.tokens_path.read_text())
    return StoredTokens(**raw)


def tokens_exist() -> bool:
    return settings.tokens_path.exists()
