"""
数据库连接管理 —— 异步式调用数据库 & 数据库会话实现
支持两种方式：
1. get_session() — FastAPI 依赖注入（自动 commit/rollback）
2. AsyncSessionLocal — 手动管理会话（用于复杂事务）
"""
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 优先用配置的 database_url，否则自动构建
DATABASE_URL = settings.database_url or f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, 'data', 'kinvoice.db')}"

# 异步引擎
engine = create_async_engine(DATABASE_URL, echo=False)

# 手动会话工厂（xia 风格）
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# 依赖注入会话工厂（si 风格，兼容旧代码）
async_session_factory = AsyncSessionLocal


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncSession:
    """FastAPI 依赖注入：获取异步数据库会话（自动 commit/rollback）"""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
