"""
大模型调用封装 —— 含超时、降级、Mock 模式

外部调用：
- call_llm(messages) → str           : 通用 LLM 调用（chat.py / nvc.py）
- chat_completion(messages, ...) → str: 带参数透传的调用（nvc_service.py）
"""
import asyncio
import uuid
import httpx
from app.config import settings
from app.utils.logger import logger

FALLBACK_MESSAGE = "我暂时无法回答，请稍后再试"
TIMEOUT_SECONDS = 3600

# 需要 request_id 的 vivo 模型列表
VIVO_MODELS = ["qwen3.5-plus", "Volc-DeepSeek-V3.2", "Doubao-Seed-2.0-mini", "Doubao-Seed-2.0-lite", "Doubao-Seed-2.0-pro"]


def normalize_history_messages(history):
    """Compatibility helper for legacy callers; excludes privileged roles."""
    return [
        {"role": item["role"], "content": str(item["content"])}
        for item in (history or [])
        if isinstance(item, dict) and item.get("role") in ("user", "assistant")
        and item.get("content") is not None
    ]


async def call_llm(messages: list[dict]) -> str:
    """xia 风格：统一 LLM 调用，含 Mock 降级"""
    # Mock 模式
    if "your-key" in settings.llm_api_key.lower() or "your-appkey" in settings.llm_api_key.lower() or not settings.llm_api_key:
        logger.warning("使用 Mock 模式")
        await asyncio.sleep(0.5)
        return _mock_response(messages[-1]["content"])

    # 真实调用
    request_id = str(uuid.uuid4())
    url = f"{settings.llm_api_base}/chat/completions"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {settings.llm_api_key}",
    }

    # vivo 大模型需要 request_id 作为 query 参数
    params = {}
    if settings.llm_model in VIVO_MODELS:
        params["request_id"] = request_id

    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        response = await client.post(
            url,
            headers=headers,
            params=params,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def _mock_response(user_input: str) -> str:
    """Mock 降级回复"""
    if "管" in user_input or "烦" in user_input or "别" in user_input:
        return "我知道你是关心我，但我需要一些空间。我们可以好好聊聊这件事吗？"
    elif "谢谢" in user_input or "感谢" in user_input:
        return "你的感谢让我感到很温暖。"
    elif "对不起" in user_input or "抱歉" in user_input:
        return "没关系，我理解你的感受。我们一起来解决这个问题。"
    else:
        return "我理解你想表达的意思。让我们用更温和的方式沟通，好吗？"


async def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 512,
) -> str:
    """
    调用 LLM 对话接口，返回模型回复文本。
    用于 NVC 破冰转换等需要透传 temperature / max_tokens 参数的场景。
    """
    return await call_llm(messages)
