"""
KinVoice 后端 —— FastAPI 入口
"""
raise RuntimeError("Legacy routes are quarantined after the privacy audit. Use app.main:app.")

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.config import settings
from app.utils.logger import logger

# 数据库模型（确保建表时注册）  # noqa: F401
import app.models.folder  # noqa: F401

# 路由导入
from app.api.chat import router as chat_router
from app.api.memory import router as memory_router
from app.api.summarize import router as summarize_router
from app.api.profile import router as profile_router
from app.api.tts import router as tts_router
from app.api.replica import router as replica_router
from app.api.family import router as family_router
from app.api.chatroom import router as chatroom_router
from app.api.profile_ai import router as profile_ai_router
from app.api.cards_ai import router as cards_ai_router
from app.api.auth import router as auth_router
from app.api.convert import router as convert_router
from app.api.nvc import router as nvc_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    logger.info(f"KinVoice 后端启动中... APP_NAME={settings.APP_NAME}")
    yield
    logger.info("KinVoice 后端已关闭")


app = FastAPI(
    title=settings.APP_NAME or "KinVoice API",
    description="KinVoice 家庭沟通智能助手",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS —— 允许快应用前端访问
origins = [origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",")] if settings.ALLOWED_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由（si 全部保留 + xia TTS/replica） ──

# AI 陪伴对话
app.include_router(chat_router)
# 经验卡片 CRUD + 同步 + 收藏
app.include_router(memory_router)
# 对话总结（si 保留）
app.include_router(summarize_router)
# 家庭成员档案（si 保留）
app.include_router(profile_router)
# TTS 文本转语音（xia）
app.include_router(tts_router)
# 音色克隆（xia）
app.include_router(replica_router)
# 家庭组管理（独立模块）
app.include_router(family_router)
# 家庭聊天室（独立模块）
app.include_router(chatroom_router)
# AI 档案编写（profile_ai）
app.include_router(profile_ai_router)
# AI 卡片提取（cards_ai）
app.include_router(cards_ai_router)
# 用户认证（注册/登录）
app.include_router(auth_router)
# NVC 破冰转换
app.include_router(convert_router)
# NVC 非暴力沟通
app.include_router(nvc_router)


# ── 健康检查 ──

@app.get("/", tags=["健康检查"])
async def root():
    return {"status": "ok", "service": "KinVoice", "version": "0.2.0"}


@app.get("/ping", tags=["健康检查"])
async def ping():
    return {"status": "ok"}


# ── 全局异常处理器（xia 新增） ──

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """所有未捕获异常的兜底处理"""
    logger.error(f"未捕获异常: {type(exc).__name__}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试"},
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """参数校验错误"""
    logger.warning(f"参数错误: {str(exc)}")
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )
