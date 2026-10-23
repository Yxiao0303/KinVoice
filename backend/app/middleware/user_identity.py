"""
用户身份依赖注入 —— 从请求 Header 提取 user_id

使用方式：
    @router.post("/xxx")
    async def handler(user_id: str = Depends(get_user_id)):
        ...
"""
from fastapi import Header, HTTPException


async def get_user_id(x_user_id: str | None = Header(None, alias="X-User-Id")) -> str:
    """
    从请求头提取用户 ID。

    当前阶段不强制登录，未传则默认为 "1"（兼容现有数据）。
    后续可改为强制要求并返回 401。
    """
    if not x_user_id:
        # 兼容模式：未传 user_id 时使用默认用户
        return "1"
    return x_user_id
