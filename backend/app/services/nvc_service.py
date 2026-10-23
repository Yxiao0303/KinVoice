"""
NVC 破冰转换服务 —— 将原始发言转换为非暴力沟通四要素
"""
import json
from app.services.llm_service import chat_completion
from app.utils.logger import logger

NVC_SYSTEM_PROMPT = """你是一个非暴力沟通（NVC）专家。你的任务是将用户的原始发言转换为 NVC 四要素格式。

请严格按以下 JSON 格式输出（不要输出其他内容）：
{
  "observation": "客观描述观察到的事实，不带评判",
  "feeling": "说话者可能的感受",
  "need": "说话者未满足的需要",
  "request": "可以提出的具体请求（可选，填 null 如果无法推断）",
  "emotion": "识别到的情绪关键词（如：生气、委屈、焦虑）"
}

规则：
1. observation 只描述事实，不添加评价
2. feeling 使用 NVC 感受词汇表中的词
3. need 从 NVC 需要词汇表中选择
4. 保持中文输出
"""


async def convert_to_nvc(raw_text: str, emotion_hint: str | None = None) -> dict:
    """
    将原始文本转换为 NVC 四要素
    """
    user_content = raw_text
    if emotion_hint:
        user_content = f"【情绪提示】{emotion_hint}\n【原文】{raw_text}"

    messages = [
        {"role": "system", "content": NVC_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    response = await chat_completion(messages, temperature=0.3, max_tokens=512)

    # 尝试解析 JSON
    try:
        result = json.loads(response)
        return {
            "observation": result.get("observation", ""),
            "feeling": result.get("feeling", ""),
            "need": result.get("need", ""),
            "request": result.get("request"),
            "emotion": result.get("emotion", "未知"),
        }
    except json.JSONDecodeError:
        logger.warning(f"NVC 输出不是有效 JSON，原样返回: {response}")
        return {
            "observation": raw_text,
            "feeling": "",
            "need": "",
            "request": None,
            "emotion": "未知",
        }
