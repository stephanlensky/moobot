from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from moobot.fastapi.routers import google_oauth, health
from moobot.settings import get_settings

settings = get_settings()

ROUTERS = [
    health.router,
    google_oauth.router,
]


def create_app() -> FastAPI:
    """
    Perform application setup tasks and create FastAPI app instance.
    """
    app = FastAPI(openapi_url=None)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    for router in ROUTERS:
        app.include_router(router)

    return app


app = create_app()
