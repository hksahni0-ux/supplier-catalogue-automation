"""HTTP API for the React front end (web/), plus the built page itself.

Every outside service comes in through `Services`, so tests run without Gmail, Drive or NVIDIA.
Safety rules:
- sign-in links are single-use, expire after 15 minutes and are rate-limited per email and IP;
- the session is a signed, HttpOnly, SameSite=Lax cookie;
- every POST needs the X-Requested-With header, which cross-site forms cannot send;
- runs only start from an explicit Confirm, only for SKUs in the Products sheet, one at a time.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, TimestampSigner, URLSafeTimedSerializer
from pydantic import BaseModel, Field, field_validator

from fci.assistant.agent import AssistantReply
from fci.workflow import ProductRun

EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[A-Za-z]{2,}$")
COOKIE = "fci_session"
DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


@dataclass
class WebSettings:
    secret: str
    base_url: str
    operators: set[str] | Literal["any"] = "any"  # who may press Confirm; "any" = every signed-in user
    link_minutes: int = 15
    session_days: int = 7
    per_email: tuple[int, int] = (3, 15 * 60)  # sign-in emails per address per window (count, seconds)
    per_ip: tuple[int, int] = (10, 60 * 60)

    def can_run(self, email: str) -> bool:
        """Operators are full addresses or whole domains written as '@fcilondon.co.uk'."""
        if self.operators == "any":
            return True
        email = email.lower()
        return email in self.operators or "@" + email.rsplit("@", 1)[-1] in self.operators


@dataclass
class Services:
    assistant: Callable[[list[dict[str, Any]]], AssistantReply]
    products: Callable[[], list[dict[str, Any]]]
    review_items: Callable[[], dict[str, Any]]
    runner: Callable[[list[str], bool, Callable[[str], None]], list[ProductRun]]
    send_link: Callable[[str, str], None]
    known_skus: Callable[[], set[str]]


class LoginBody(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid(cls, value: str) -> str:
        value = value.strip().lower()
        if not EMAIL.match(value):
            raise ValueError("not an email address")
        return value


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatBody(BaseModel):
    messages: list[Message] = Field(max_length=30)


class RunBody(BaseModel):
    skus: list[str] = Field(min_length=1, max_length=50)
    publish: bool = True


@dataclass
class Job:
    id: str
    skus: list[str]
    publish: bool
    started_by: str
    state: str = "queued"
    log: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class RateLimit:
    def __init__(self, clock: Callable[[], float]) -> None:
        self.clock = clock
        self.hits: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: tuple[int, int]) -> bool:
        count, window = limit
        now, hits = self.clock(), self.hits[key]
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= count:
            return False
        hits.append(now)
        return True


def _result(run: ProductRun) -> dict[str, Any]:
    return {
        "sku": run.sku,
        "name": run.name,
        "base_price": run.base_price,
        "combinations": run.combinations,
        "flags": run.flags,
        "changes": run.changes.summary() if run.changes else None,
        "drive": f"https://drive.google.com/drive/folders/{run.drive_folder}" if run.drive_folder else None,
        "error": run.error,
    }


def create_app(
    settings: WebSettings,
    services: Services,
    *,
    clock: Callable[[], float] = time.time,
    background: Callable[[Callable[[], None]], None] | None = None,
) -> FastAPI:
    app = FastAPI(title="FCI Catalogue", docs_url=None, redoc_url=None, openapi_url=None)

    class ClockSigner(TimestampSigner):
        def get_timestamp(self) -> int:
            return int(clock())

    links = URLSafeTimedSerializer(settings.secret, salt="sign-in-link", signer=ClockSigner)
    sessions = URLSafeTimedSerializer(settings.secret, salt="session", signer=ClockSigner)
    used: dict[str, float] = {}
    limits = RateLimit(clock)
    jobs: dict[str, Job] = {}
    run_lock = threading.Lock()
    start = background or (lambda fn: threading.Thread(target=fn, daemon=True).start())

    def _loads(serializer: URLSafeTimedSerializer, token: str, max_age: int) -> dict[str, Any]:
        """itsdangerous reads the wall clock; check the age against our clock instead."""
        data, signed_at = serializer.loads(token, return_timestamp=True)
        if clock() - signed_at.timestamp() > max_age:
            raise BadSignature("expired")
        return dict(data)

    def same_site(request: Request) -> None:
        if request.headers.get("x-requested-with") != "fci":
            raise HTTPException(403, "missing X-Requested-With header")

    def user(request: Request) -> str:
        token = request.cookies.get(COOKIE)
        if not token:
            raise HTTPException(401, "sign in first")
        try:
            data = _loads(sessions, token, settings.session_days * 86400)
        except BadSignature as error:
            raise HTTPException(401, "session expired, sign in again") from error
        return str(data["email"])

    @app.post("/api/login", dependencies=[Depends(same_site)])
    def login(body: LoginBody, request: Request) -> dict[str, str]:
        ip = request.client.host if request.client else "unknown"
        if not limits.allow(f"ip:{ip}", settings.per_ip) or not limits.allow(
            f"email:{body.email}", settings.per_email
        ):
            raise HTTPException(429, "too many sign-in emails; try again later")
        token = links.dumps({"email": body.email, "nonce": secrets.token_urlsafe(12)})
        services.send_link(body.email, f"{settings.base_url}/auth?token={token}")
        return {"status": "sent"}

    @app.get("/auth")
    def auth(token: str) -> Response:
        try:
            data = _loads(links, token, settings.link_minutes * 60)
        except BadSignature:
            return HTMLResponse(
                "This sign-in link has expired or is invalid. Request a new one.", status_code=400
            )
        if data["nonce"] in used:
            return HTMLResponse(
                "This sign-in link has already been used. Request a new one.", status_code=400
            )
        used[data["nonce"]] = clock()
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE,
            sessions.dumps({"email": data["email"]}),
            max_age=settings.session_days * 86400,
            httponly=True,
            samesite="lax",
            secure=settings.base_url.startswith("https://"),
        )
        return response

    @app.post("/api/logout", dependencies=[Depends(same_site)])
    def logout(response: Response) -> dict[str, str]:
        response.delete_cookie(COOKIE)
        return {"status": "signed out"}

    @app.get("/api/me")
    def me(email: str = Depends(user)) -> dict[str, Any]:
        return {"email": email, "can_run": settings.can_run(email)}

    @app.post("/api/chat", dependencies=[Depends(same_site)])
    def chat(body: ChatBody, email: str = Depends(user)) -> dict[str, Any]:
        reply = services.assistant([m.model_dump() for m in body.messages])
        return {
            "text": reply.text,
            "verified": reply.verified,
            "proposals": reply.proposals,
            "tools_used": reply.tools_used,
        }

    @app.get("/api/products")
    def products(email: str = Depends(user)) -> dict[str, Any]:
        return {"products": services.products(), "review": services.review_items()}

    @app.post("/api/runs", dependencies=[Depends(same_site)])
    def start_run(body: RunBody, email: str = Depends(user)) -> dict[str, str]:
        if not settings.can_run(email):
            raise HTTPException(403, "your account can view but not run products")
        unknown = sorted(set(body.skus) - services.known_skus())
        if unknown:
            raise HTTPException(422, f"not in the Products sheet: {', '.join(unknown)}")
        if run_lock.locked():
            raise HTTPException(409, "a run is already in progress")
        job = Job(uuid.uuid4().hex[:12], body.skus, body.publish, email)
        jobs[job.id] = job

        def work() -> None:
            with run_lock:
                job.state = "running"
                try:
                    results = services.runner(job.skus, job.publish, job.log.append)
                    job.results = [_result(r) for r in results]
                    job.state = "done"
                except Exception as error:  # noqa: BLE001 - reported to the user, never swallowed
                    job.state, job.error = "failed", f"{type(error).__name__}: {error}"

        start(work)
        return {"id": job.id}

    @app.get("/api/runs/{job_id}")
    def run_status(job_id: str, email: str = Depends(user)) -> dict[str, Any]:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "no such run")
        return {"id": job.id, "state": job.state, "skus": job.skus, "log": job.log, "results": job.results,
                "error": job.error}  # fmt: skip

    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def page() -> Response:
        index = DIST / "index.html"
        if index.exists():
            return FileResponse(index)
        return HTMLResponse(
            "<h1>FCI Catalogue</h1><p>Build the front end: <code>cd web && npm run build</code></p>"
        )

    return app
