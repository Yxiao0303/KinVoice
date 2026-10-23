"""
请求频率限制 —— 零依赖内存限流器

设计决策：
- 用 dict + deque 而非引入 Redis/第三方库，保持零依赖
- 按 user_id 维度限流（每个用户独立计数器）
- 超过限制时写入日志文件 + 返回 429
- 进程重启后计数器清零（可接受，内存限流的固有特性）
"""
import time
from collections import deque
from fastapi import Request, HTTPException
from app.utils.logger import logger

# ── 配置 ──
WINDOW_SECONDS = 60      # 时间窗口
MAX_REQUESTS = 10         # 窗口内最大请求数

# ── 存储：{user_id: deque([timestamp, ...])}
_buckets: dict[str, deque[float]] = {}


def _cleanup_expired(user_id: str, now: float) -> None:
    """移除窗口外的过期时间戳"""
    if user_id not in _buckets:
        return
    cutoff = now - WINDOW_SECONDS
    bucket = _buckets[user_id]
    while bucket and bucket[0] < cutoff:
        bucket.popleft()


def _evict_old_entries(now: float) -> None:
    """定期清理已空的 bucket，防止内存泄漏"""
    empty_keys = [k for k, v in _buckets.items() if not v]
    for k in empty_keys:
        del _buckets[k]


async def check_rate_limit(request: Request, user_id: str) -> None:
    """
    FastAPI 依赖：检查当前用户是否超过频率限制。

    用法：
        @router.post("/chat")
        async def chat(req: Request, user_id: str = Depends(get_user_id)):
            await check_rate_limit(req, user_id)
            ...

    Raises:
        HTTPException(429): 超过限制时返回
    """
    now = time.time()
    _cleanup_expired(user_id, now)

    bucket = _buckets.setdefault(user_id, deque())
    count = len(bucket)

    if count >= MAX_REQUESTS:
        logger.warning(
            f"[RATE_LIMIT] user_id={user_id} "
            f"requests={count}/{MAX_REQUESTS} "
            f"window={WINDOW_SECONDS}s "
            f"path={request.url.path}"
        )
        raise HTTPException(
            status_code=429,
            detail=f"请求太频繁，请 {WINDOW_SECONDS} 秒后再试",
        )

    bucket.append(now)

    # 每 100 次检查清理一次空桶
    if hash(user_id) % 100 == 0:
        _evict_old_entries(now)
