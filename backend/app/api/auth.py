from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.dropbox_svc import (
    build_authorize_url,
    exchange_code_for_tokens,
    get_client,
    save_tokens,
    tokens_exist,
)

router = APIRouter(prefix="/auth/dropbox", tags=["auth"])


@router.get("/status")
def status() -> dict:
    if not tokens_exist():
        return {"connected": False}
    client = get_client()
    if client is None:
        return {"connected": False}
    try:
        info = client.account_info()
    except Exception as e:
        return {"connected": False, "error": str(e)}
    return {"connected": True, "account": info}


@router.get("/start")
def start():
    try:
        url = build_authorize_url()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return RedirectResponse(url=url)


@router.get("/callback", response_class=HTMLResponse)
def callback(request: Request):
    params = dict(request.query_params)
    if "error" in params:
        raise HTTPException(status_code=400, detail=f"Dropbox returned error: {params['error']}")
    try:
        tokens = exchange_code_for_tokens(params)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth exchange failed: {e}") from e

    save_tokens(tokens)

    return HTMLResponse(
        """
        <!doctype html>
        <html><body style="font-family: system-ui; padding: 2rem;">
          <h1>Connected to Dropbox</h1>
          <p>You can close this window and return to the app.</p>
          <script>setTimeout(() => { window.location.href = "/"; }, 1500);</script>
        </body></html>
        """
    )
