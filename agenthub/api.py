"""HTTP routes: the UI's API, the live-update stream, the session-facing /internal routes, reports,
run files and the built UI. Local only: the server binds 127.0.0.1 and refuses foreign hosts and origins."""

from __future__ import annotations

import json
import queue
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Config, check_model
from .errors import HubError
from .hub import Hub
from .projects import ProjectError
from .reports import ReportError
from .tickets import STAGES

WEB_DIST = Path(__file__).resolve().parent.parent / "web" / "dist"
LOCAL_HOST_RE = re.compile(r"^(127\.0\.0\.1|localhost)(:\d+)?$")
LOCAL_ORIGIN_RE = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d+)?$")
MUTATIONS = ("POST", "PATCH", "PUT", "DELETE")
SSE_KEEPALIVE_S = 15


def _error(message: str, status: int, **extra: Any) -> JSONResponse:
    return JSONResponse({"message": message, **{k: v for k, v in extra.items() if v is not None}}, status_code=status)


def create_app(config: Config | None = None, start: bool = True) -> FastAPI:
    config = config or Config.from_env()
    hub = Hub(config)
    if start:
        hub.start()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        hub.shutdown()

    app = FastAPI(title="AgentHub", lifespan=lifespan)
    app.state.hub = hub

    # ------------------------------------------------------------ guard and errors
    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        if not LOCAL_HOST_RE.match(host):
            return _error("AgentHub answers only on 127.0.0.1 and localhost", 403)
        if origin and not LOCAL_ORIGIN_RE.match(origin):
            return _error("requests from other sites are refused", 403)
        path = request.url.path
        if request.method in MUTATIONS and (path.startswith("/api/") or path.startswith("/internal/")):
            if not request.headers.get("content-type", "").startswith("application/json"):
                return _error("send the request as application/json", 415)
        return await call_next(request)

    @app.exception_handler(HubError)
    async def hub_error(request: Request, e: HubError):
        return _error(e.message, e.status)

    @app.exception_handler(ProjectError)
    async def project_error(request: Request, e: ProjectError):
        return _error(e.message, e.status, created_repo=e.created_repo)

    @app.exception_handler(ReportError)
    async def report_error(request: Request, e: ReportError):
        return _error(e.message, e.status)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, e: StarletteHTTPException):
        return _error(str(e.detail), e.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, e: RequestValidationError):
        return _error("invalid request: " + "; ".join(str(err.get("msg")) for err in e.errors()), 422)

    # ------------------------------------------------------------ bootstrap, settings, users
    @app.get("/api/bootstrap")
    def bootstrap():
        return {
            "users": hub.db.users(),
            "stages": STAGES,
            "models": config.models,
            "default_model": hub.db.setting("default_model"),
            "projects": hub.projects.list_projects(),
            "login": hub.sessions.login_status(),
            "usage": hub.usage.current(),
            "server_time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @app.get("/api/settings")
    def get_settings():
        return {"default_model": hub.db.setting("default_model")}

    @app.patch("/api/settings")
    def patch_settings(body: dict = Body(...)):
        model = body.get("default_model")
        check_model(config, model)
        hub.db.set_setting("default_model", model)
        hub.events.publish("settings")
        return {"default_model": model}

    @app.get("/api/login")
    def login():
        return hub.sessions.login_status(fresh=True)

    @app.patch("/api/users/{user_id}")
    def patch_user(user_id: str, body: dict = Body(...)):
        user = hub.db.user(user_id)
        if user is None:
            raise HubError("no such user", 404)
        if user["kind"] != "ai":
            raise HubError("only an AI user has a role prompt", 422)
        prompt = str(body.get("prompt") or "").strip()
        if not prompt:
            raise HubError("the prompt is empty", 422)
        hub.db.run("UPDATE users SET prompt = ? WHERE id = ?", (prompt, user_id))
        hub.events.publish("users")
        return hub.db.user(user_id)

    # ------------------------------------------------------------ tickets and comments
    @app.get("/api/tickets")
    def list_tickets():
        return {"tickets": hub.tickets.list()}

    @app.post("/api/tickets")
    def create_ticket(body: dict = Body(...)):
        detail, warning = hub.tickets.create(body)
        return {**detail, **({"warning": warning} if warning else {})}

    @app.get("/api/tickets/{ticket_id}")
    def get_ticket(ticket_id: int):
        return hub.tickets.detail(ticket_id)

    @app.patch("/api/tickets/{ticket_id}")
    def patch_ticket(ticket_id: int, body: dict = Body(...)):
        return hub.tickets.update(ticket_id, body)

    @app.post("/api/tickets/{ticket_id}/comments")
    def post_comment(ticket_id: int, body: dict = Body(...)):
        reply_to = body.get("reply_to")
        comment, delivered, started = hub.tickets.add_comment(
            ticket_id, "pablo", str(body.get("body") or ""), int(reply_to) if reply_to is not None else None
        )
        return {"comment": comment, "delivered_to": delivered, "started": started}

    # ------------------------------------------------------------ tasks
    @app.get("/api/tasks")
    def list_tasks(status: str | None = None):
        return {"tasks": hub.tasks.list(status)}

    @app.post("/api/tasks")
    def create_task(body: dict = Body(...)):
        ai_user_id = body.get("ai_user_id")
        if not ai_user_id:
            raise HubError("choose the AI user that receives the task", 422)
        task = hub.tasks.create(
            str(ai_user_id), body.get("model") or hub.db.setting("default_model"), str(body.get("message") or ""), origin="manual"
        )
        return hub.tasks.view(task["id"], with_events=True)

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: int):
        return hub.tasks.view(task_id, with_events=True)

    @app.patch("/api/tasks/{task_id}")
    def patch_task(task_id: int, body: dict = Body(...)):
        hub.tasks.update(task_id, title=body.get("title"), model=body.get("model"))
        return hub.tasks.view(task_id, with_events=True)

    @app.post("/api/tasks/{task_id}/messages")
    def post_message(task_id: int, body: dict = Body(...)):
        hub.tasks.send(task_id, str(body.get("text") or body.get("message") or ""))
        return hub.tasks.view(task_id, with_events=True)

    @app.post("/api/tasks/{task_id}/stop")
    def stop_task(task_id: int):
        hub.tasks.stop(task_id)
        return hub.tasks.view(task_id, with_events=True)

    @app.post("/api/tasks/{task_id}/archive")
    def archive_task(task_id: int):
        hub.tasks.archive(task_id)
        return hub.tasks.view(task_id, with_events=True)

    # ------------------------------------------------------------ activity
    @app.get("/api/activity")
    def activity():
        items, unseen = hub.tickets.activity()
        return {"items": items, "unseen": unseen}

    @app.post("/api/activity/seen")
    def activity_seen():
        return {"unseen": hub.tickets.mark_activity_seen()}

    # ------------------------------------------------------------ live updates
    @app.get("/api/events")
    def events():
        q = hub.events.subscribe()

        def stream():
            try:
                yield "retry: 2000\n\n"
                while True:
                    try:
                        message = q.get(timeout=SSE_KEEPALIVE_S)
                    except queue.Empty:
                        yield ": keepalive\n\n"
                        continue
                    yield f"data: {json.dumps(message)}\n\n"
            finally:
                hub.events.unsubscribe(q)

        return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    # ------------------------------------------------------------ for sessions (Bearer <task token>)
    def session_task(request: Request) -> dict:
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        task = hub.tasks.by_token(token) if token else None
        if task is None:
            raise HubError("unknown task token", 401)
        return task

    @app.post("/internal/title")
    def internal_title(request: Request, body: dict = Body(...)):
        task = session_task(request)
        applied = hub.tasks.set_ai_title(task["id"], str(body.get("title") or ""))
        return {"applied": applied, "title": hub.tasks.get(task["id"])["title"]}

    @app.get("/internal/search")
    def internal_search(request: Request, q: str = ""):
        session_task(request)
        return hub.tickets.search(q)

    @app.post("/internal/harness/start")
    def internal_harness_start(request: Request, body: dict = Body(...)):
        task = session_task(request)
        run_id = hub.bridge.start(
            task, str(body.get("feature") or ""), str(body.get("ticket_text") or ""),
            project=body.get("project") or None, workflow=body.get("workflow") or "feature-v1",
        )
        return {"run_id": run_id, "run_dir": str(config.layout().run_dir(run_id))}

    @app.get("/internal/harness/status")
    def internal_harness_status(request: Request):
        return {"runs": hub.bridge.status(session_task(request))}

    @app.post("/internal/harness/resume")
    def internal_harness_resume(request: Request, body: dict = Body(...)):
        task = session_task(request)
        return {"run_id": hub.bridge.resume(task, str(body.get("run_id") or ""))}

    # ------------------------------------------------------------ reports and run files
    @app.get("/reports/{task_id}/{path:path}")
    def report(task_id: int, path: str, raw: int = 0):
        content, media = hub.reports.report(task_id, path, raw=bool(raw))
        return Response(content, media_type=media)

    @app.get("/runs/{run_id}/files/{name}")
    def run_file(run_id: str, name: str, raw: int = 0):
        content, media = hub.reports.run_file(run_id, name, raw=bool(raw))
        return Response(content, media_type=media)

    # ------------------------------------------------------------ the built UI
    @app.get("/{path:path}", include_in_schema=False)
    def ui(path: str):
        if path.startswith(("api/", "internal/")):
            return _error("not found", 404)
        if not WEB_DIST.is_dir():
            return HTMLResponse(
                "<p>The AgentHub UI is not built. Run <code>npm --prefix web ci</code> and "
                "<code>npm --prefix web run build</code>, then reload.</p>"
            )
        target = (WEB_DIST / path).resolve()
        if path and target.is_file() and WEB_DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")

    return app
