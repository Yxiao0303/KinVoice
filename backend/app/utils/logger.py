"""
日志配置 —— 基于 loguru
"""
import sys
from loguru import logger
from app.config import settings

# 移除默认 handler
logger.remove()

# 控制台输出
logger.add(
    sys.stderr,
    level=settings.LOG_LEVEL.upper(),
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

# 文件输出（按天轮转）
logger.add(
    "logs/kinvoice_{time:YYYY-MM-DD}.log",
    level="DEBUG",
    rotation="00:00",
    retention="30 days",
    encoding="utf-8",
)
