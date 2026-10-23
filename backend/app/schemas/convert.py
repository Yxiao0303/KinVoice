"""
破冰转换 —— 请求/响应模型
"""
from pydantic import BaseModel, Field


class ConvertRequest(BaseModel):
    """NVC 破冰转换请求"""
    raw_text: str = Field(..., min_length=1, max_length=2000, description="原始发言文本")
    emotion_hint: str | None = Field(None, description="情绪提示（可选，帮助模型更准确）")


class ConvertResponse(BaseModel):
    """NVC 破冰转换响应"""
    observation: str = Field(..., description="观察（事实描述）")
    feeling: str = Field(..., description="感受")
    need: str = Field(..., description="需要")
    request: str | None = Field(None, description="请求（可选）")
    emotion: str = Field(..., description="识别到的情绪关键词")
