from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.templating import _TemplateResponse

from moobot.db.crud.google import create_api_user, get_auth_session_by_state
from moobot.db.session import get_session
from moobot.util.google import fetch_credentials

router = APIRouter(prefix="/google_oauth")
templates = Jinja2Templates(directory="templates")


@router.get("/auth", response_class=HTMLResponse)
def handle_oauth_response(
    code: str | None,
    state: str,
    request: Request,
    session: Session = Depends(get_session),
) -> _TemplateResponse:
    if code is None:
        return templates.TemplateResponse(
            "google_oauth.html",
            {"request": request, "message": "❌ Missing authorization code! Please try again."},
        )

    auth_session = get_auth_session_by_state(session, state)
    if auth_session is None:
        return templates.TemplateResponse(
            "google_oauth.html",
            {"request": request, "message": "❌ Invalid authorization state. Please try again."},
        )

    user_id = int(auth_session.user_id)
    session.delete(auth_session)

    credentials = fetch_credentials(code)
    create_api_user(
        session,
        user_id=user_id,
        token=credentials.token,
        refresh_token=credentials.refresh_token,
        token_uri=credentials.token_uri,
        scopes=credentials.scopes,
        commit=True,
    )

    return templates.TemplateResponse(
        "google_oauth.html", {"request": request, "message": "✅ Success!"}
    )
