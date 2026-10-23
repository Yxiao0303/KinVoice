"""
破冰转换接口 —— POST /convert
将用户原始发言转换为 NVC（非暴力沟通）四要素
"""
from fastapi import APIRouter
from app.schemas.convert import ConvertRequest, ConvertResponse
from app.services.nvc_service import convert_to_nvc
from app.utils.logger import logger

router = APIRouter(prefix="/convert", tags=["破冰转换"])


@router.post("", response_model=ConvertResponse)
async def convert_text(req: ConvertRequest):
    """
    将原始文本转换为 NVC 四要素：
    observation（观察）、feeling（感受）、need（需要）、request（请求）
    """
    logger.info(f"收到转换请求: text_len={len(req.raw_text)}, emotion_hint={req.emotion_hint}")
    result = await convert_to_nvc(req.raw_text, req.emotion_hint)
    return ConvertResponse(**result)
