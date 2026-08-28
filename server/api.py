"""Main-owned return transport. This build has no hardware actuation or payouts."""

from contextlib import asynccontextmanager
import secrets

from fastapi import Depends, FastAPI, Header
from fastapi.exceptions import RequestValidationError
from starlette.responses import JSONResponse

from .contracts import Action, Inference, StartSession, StationReady
from .return_store import Conflict, NotFound, ReturnStore
from .settings import Settings


class RequestLimit:
    def __init__(self, app, limit=16384):
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if scope["method"] == "POST" and headers.get(b"content-type", b"").split(b";")[0] != b"application/json":
            return await JSONResponse({"error": "JSON body required"}, status_code=415)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.limit:
                return await JSONResponse({"error": "Request too large"}, status_code=413)(scope, receive, send)
            if not message.get("more_body", False):
                break
        delivered = False

        async def buffered_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def secured_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"cache-control", b"no-store"), (b"x-content-type-options", b"nosniff"),
                ]
            await send(message)

        return await self.app(scope, buffered_receive, secured_send)


def create_app(settings: Settings, *, clock=None):
    store = ReturnStore(settings, clock)

    @asynccontextmanager
    async def lifespan(app):
        store.open()
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="BinSight return integration", version="1.0.0", lifespan=lifespan)
    app.add_middleware(RequestLimit)
    app.state.store = store

    def bearer(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            return ""
        return authorization[7:]

    def citizen(authorization: str | None = Header(default=None)):
        value = bearer(authorization)
        for citizen_id, token in settings.citizen_tokens.items():
            if value.isascii() and secrets.compare_digest(value, token):
                return citizen_id
        from fastapi import HTTPException
        raise HTTPException(401, "Citizen authentication required", headers={"WWW-Authenticate": "Bearer"})

    def device(authorization: str | None = Header(default=None)):
        value = bearer(authorization)
        if not value.isascii() or not secrets.compare_digest(value, settings.device_token):
            from fastapi import HTTPException
            raise HTTPException(401, "Device authentication required", headers={"WWW-Authenticate": "Bearer"})

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=409)

    @app.exception_handler(NotFound)
    async def not_found(request, exc):
        return JSONResponse({"error": str(exc)}, status_code=404)

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return JSONResponse({"error": "Invalid request", "fields": [list(error["loc"]) for error in exc.errors()]}, status_code=422)

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "simulation", "actuation_enabled": False, "payments_enabled": False}

    @app.post("/api/v1/return-sessions")
    def start(body: StartSession, owner=Depends(citizen)):
        return store.start_session(owner, body)

    @app.get("/api/v1/return-sessions/{session_id}")
    def read(session_id: str, owner=Depends(citizen)):
        return store.get_session(owner, session_id)

    @app.post("/api/v1/return-sessions/{session_id}/inspections")
    def inspect(session_id: str, body: Action, owner=Depends(citizen)):
        return store.begin_inspection(owner, session_id, body)

    @app.post("/api/v1/return-sessions/{session_id}/finish")
    def finish(session_id: str, body: Action, owner=Depends(citizen)):
        return store.finish_session(owner, session_id, body)

    @app.get("/api/v1/recycling/stations/{station_id}", dependencies=[Depends(device)])
    def state(station_id: str):
        if station_id != settings.station_id:
            raise NotFound("Station not found")
        return store.station_state()

    @app.post("/api/v1/recycling/stations/{station_id}/ready", dependencies=[Depends(device)])
    def ready(station_id: str, body: StationReady):
        if station_id != settings.station_id:
            raise NotFound("Station not found")
        return store.station_ready(body)

    @app.post("/api/v1/recycling/inferences", dependencies=[Depends(device)])
    def inference(body: Inference):
        return store.ingest(body)

    return app
