from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
import sqlite3
import time

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .auth import AuthStore
from .config import Settings
from .engine import Engine
from .provider import ProviderUnavailable, RemoteProvider
from .schemas import Credentials, TurnRequest, TurnResponse
from .streaming import TurnStreamResponse

WEB = Path(__file__).parent / "web"


class BodyLimit:
    def __init__(self, app, limit=65536):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            size += len(message.get("body", b""))
            if size > self.limit:
                return await JSONResponse({"detail": "请求过大"}, 413)(scope, receive, send)
            chunks.append(message)
            if not message.get("more_body", False):
                break

        async def replay():
            return chunks.pop(0) if chunks else await receive()

        await self.app(scope, replay, send)


class Limiter:
    """Single-process development limiter. Production needs shared storage."""
    def __init__(self):
        self.events = defaultdict(deque)

    def check(self, key, count, window):
        now = time.monotonic()
        # Bound unique keys without evicting active limits.
        for stale in [k for k, v in self.events.items() if not v or v[-1] < now - 3600]:
            del self.events[stale]
        if key not in self.events and len(self.events) >= 5000:
            raise HTTPException(429, "服务繁忙，请稍后再试")
        queue = self.events[key]
        while queue and queue[0] < now - window:
            queue.popleft()
        if len(queue) >= count:
            raise HTTPException(429, "请求过于频繁，请稍后再试")
        queue.append(now)


def create_app(config=None, provider=None):
    config = config or Settings()
    store = AuthStore(config.auth_db, config.session_seconds)
    engine = Engine(config, provider or (RemoteProvider(config) if config.mode == "remote" else None))
    limiter, active = Limiter(), set()

    @asynccontextmanager
    async def lifespan(app):
        await store.initialize()
        yield

    app = FastAPI(title="KinVoice C-CARE 本地研究原型", version="0.5.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    app.state.store, app.state.engine = store, engine
    app.add_middleware(BodyLimit)
    # Restrict this milestone to loopback, including Host/DNS rebinding protection.
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "只接受本地同源请求"}, 403)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # FastAPI's default validation errors can echo passwords and conversation text.
        return JSONResponse({"detail": "输入格式或长度不符合要求"}, 422)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse({"detail": "服务暂时不可用"}, 500)

    async def identity(authorization: str | None = Header(default=None)):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "请先登录")
        token = authorization[7:]
        if not 30 <= len(token) <= 100:
            raise HTTPException(401, "登录已失效")
        uid = await store.resolve(token)
        if not uid:
            raise HTTPException(401, "登录已失效")
        return uid, token

    def auth_limit(request):
        limiter.check(("auth", request.client.host if request.client else "local"), 20, 300)

    @app.get("/ping")
    async def ping():
        return {"status": "ok", "version": "0.5.0", "mode": config.mode,
                "progress_stream": "ccare-stream-v1",
                "model": config.model if config.mode == "remote" else "",
                "turn_timeout_seconds": config.turn_timeout,
                "provider": config.provider_label if config.mode == "remote" else "",
                "provider_privacy_url": config.provider_privacy_url if config.mode == "remote" else "",
                "conversation_storage": "none", "professional_review": "pending"}

    @app.post("/auth/register", status_code=201)
    async def register(req: Credentials, request: Request):
        auth_limit(request)
        try:
            uid = await store.register(req.username.lower(), req.password)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "用户名不可用") from None
        return {"access_token": await store.issue(uid), "token_type": "bearer", "expires_in": config.session_seconds}

    @app.post("/auth/login")
    async def login(req: Credentials, request: Request):
        auth_limit(request)
        uid = await store.login(req.username.lower(), req.password)
        if not uid:
            raise HTTPException(401, "用户名或密码错误")
        return {"access_token": await store.issue(uid), "token_type": "bearer", "expires_in": config.session_seconds}

    @app.post("/auth/logout")
    async def logout(auth=Depends(identity)):
        await store.revoke(auth[1])
        return {"ok": True}

    @app.delete("/account")
    async def erase_account(auth=Depends(identity)):
        await store.erase(auth[0])
        return {"ok": True}

    @app.get("/account/export")
    async def export_account(auth=Depends(identity)):
        return {"account_id": auth[0], "conversation_storage": "none", "conversations": [],
                "notice": "对话仅在当前页面内存中；关闭、清空或退出后不保留。"}

    def admit(req, auth):
        if not req.eligible:
            raise HTTPException(403, "此原型仅供18–25岁在校大学生场景的内部评审")
        limiter.check(("turn", auth[0]), 30, 60)
        if auth[0] in active or len(active) >= 2:
            raise HTTPException(409, "上一条请求尚未完成，请稍后再试")
        active.add(auth[0])

    @app.post("/support/stream")
    async def stream(req: TurnRequest, auth=Depends(identity)):
        admit(req, auth)

        async def authorized():
            return await store.resolve(auth[1]) == auth[0]

        return TurnStreamResponse(engine, req, authorized, lambda: active.discard(auth[0]))

    @app.post("/support/turn", response_model=TurnResponse)
    async def turn(req: TurnRequest, auth=Depends(identity)):
        admit(req, auth)
        try:
            result = await engine.respond(req)
            # Logout/deletion while the model is running invalidates the response.
            if await store.resolve(auth[1]) != auth[0]:
                raise HTTPException(401, "登录已失效")
            return result
        except ProviderUnavailable:
            raise HTTPException(503, "模型未启用或尚未同意外部处理；未发送对话到模型服务") from None
        finally:
            active.discard(auth[0])

    app.mount("/assets", StaticFiles(directory=WEB), name="assets")

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(WEB / "site.html")

    return app
