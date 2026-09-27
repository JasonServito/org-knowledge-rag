"""FastAPI app factory."""

from fastapi import FastAPI, Response, status

from orgknow.db.health import is_reachable
from orgknow.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    # Settings are read when the app is built, not at import time, so tests can pass their own.
    app_settings = settings if settings is not None else Settings()
    app = FastAPI(title="orgknow")

    @app.get("/health")
    def health() -> dict[str, str]:
        # Liveness: the process is up and answering HTTP. Deliberately ignores the database.
        return {"status": "ok"}

    @app.get("/ready")
    def ready(response: Response) -> dict[str, str]:
        # Readiness: can this process serve real traffic? A plain `def` (not `async def`)
        # makes FastAPI run it in a worker thread, so the blocking DB ping can't stall the
        # event loop.
        if is_reachable(app_settings.database_url, app_settings.db_connect_timeout_s):
            return {"status": "ready"}
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}

    return app
