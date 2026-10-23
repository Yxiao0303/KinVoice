"""
NVC（非暴力沟通）转换接口

将情绪化的言辞转化为揭示背后真实意图的温和表达，
帮助家庭成员更好地沟通。
"""
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from app.services.llm_service import call_llm, _mock_response
from app.middleware.user_identity import get_user_id
from app.middleware.rate_limiter import check_rate_limit
from app.utils.logger import logger

router = APIRouter(prefix="/nvc", tags=["NVC 非暴力沟通"])


# ── 数据模型 ──

class NVCConvertRequest(BaseModel):
    """NVC 转换请求"""
    original_text: str = Field(..., min_length=1, max_length=2000, description="原始输入文本")


class NVCConvertResponse(BaseModel):
    """NVC 转换响应"""
    original_text: str = Field(..., description="原始文本")
    converted_text: str = Field(..., description="转换后的文本")
    insight: str = Field(..., description="对原始文本背后情感意图的分析")


# ── NVC 系统提示词 ──

NVC_SYSTEM_PROMPT = """你是一位专业的家庭沟通顾问，擅长运用「非暴力沟通」(Non-Violent Communication, NVC) 方法。

你的任务是分析用户输入的情绪化言辞，将其转换为能够揭示真实意图的温和表达。

## 非暴力沟通四要素：
1. **观察** — 客观描述事实，不带评价
2. **感受** — 表达自己的情绪状态
3. **需要** — 指出哪些需要未被满足
4. **请求** — 提出具体可执行的行动请求

## 工作流程：

### 第一步：深度洞察
仔细阅读用户的原文，分析其背后隐藏的真实情感和需要：
- 这个人表面在说什么？
- 他/她真正担心的是什么？
- 哪些基本需要没有被满足？（安全、被尊重、被理解、连接等）
- 是否有未说出口的关心或爱意？

### 第二步：生成转换后的表达
将原文改写为一段温和、真诚的话，要求：
- 使用「我感到……因为我想……」的句式
- 揭示出言语背后的真实关切
- 不指责、不评判，只表达感受和需要
- 语气要温暖、真诚、有同理心
- 长度控制在 50-150 字之间
- 保持口语化自然风格，适合家庭聊天场景

### 第三步：输出格式
严格按照以下 JSON 格式输出，不要输出其他任何内容：
{
  "converted": "转换后的温和表达文本",
  "insight": "对原文背后情感意图的分析说明（30-80字）"
}

注意：
- 如果原文本身已经很温和，也请用 NVC 方式重新组织，使其更清晰
- 不要过度解读，保持合理推断范围
- 始终假设说话者是出于善意（即使表达方式不当）
"""


@router.post("/convert", response_model=NVCConvertResponse)
async def nvc_convert(
    req: NVCConvertRequest,
    request: Request,
    user_id: str = Depends(get_user_id),
):
    """
    NVC 文本转换 —— 将情绪化言辞转为温和表达。

    返回转换后的文本 + 对原话背后情感意图的洞察分析。
    """
    # 频率限制
    await check_rate_limit(request, user_id)

    logger.info(f"[NVC] 收到转换请求: user={user_id}, len={len(req.original_text)}")

    messages = [
        {"role": "system", "content": NVC_SYSTEM_PROMPT},
        {"role": "user", "content": req.original_text},
    ]

    try:
        raw_reply = await call_llm(messages)
        # 尝试解析 JSON 输出
        import json
        reply_text = raw_reply.strip()

        # 处理可能的 markdown 代码块包裹
        if reply_text.startswith("```"):
            lines = reply_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            reply_text = "\n".join(lines).strip()

        result = json.loads(reply_text)
        converted = result.get("converted", "").strip()
        insight = result.get("insight", "").strip()

        if not converted:
            converted = req.original_text
            insight = "未能识别到明显的情绪变化，建议直接发送原消息。"

        logger.info(f"[NVC] 转换成功: user={user_id}")
        return NVCConvertResponse(
            original_text=req.original_text,
            converted_text=converted,
            insight=insight,
        )

    except json.JSONDecodeError as e:
        logger.warning(f"[NVC] JSON 解析失败，使用原文作为回复: {e}")
        return NVCConvertResponse(
            original_text=req.original_text,
            converted_text=raw_reply.strip() if raw_reply else req.original_text,
            insight="已为您重新整理了这段话的表达方式。",
        )

    except Exception as e:
        logger.error(f"[NVC] LLM 调用异常: {e}")
        # Mock 降级
        mock_converted = _mock_response(req.original_text)
        return NVCConvertResponse(
            original_text=req.original_text,
            converted_text=mock_converted,
            insight="检测到您的话语中可能包含强烈的情绪，已帮您转化为更温和的表达。",
        )
