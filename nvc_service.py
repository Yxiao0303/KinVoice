"""
NVC 破冰转换服务 —— 将原始发言转换为非暴力沟通四要素
"""
import json
from app.services.llm_service import chat_completion
from app.utils.logger import logger

# 优化后的提示词：强制输出标准JSON，同时遵守NVC全部规则
NVC_SYSTEM_PROMPT = """你是一位专业的非暴力沟通（NVC）专家。
你的任务是把用户输入的、可能带有攻击性或负面情绪的语言，转换成温和、尊重、建设性的表达，并严格按照NVC四要素拆分。

执行规则：
1. 严格使用「观察-感受-需要-请求」四要素拆分内容；
2. 完全保留原文本意，仅优化语气，不添加原文以外的内容；
3. 不对原始表达做任何评价、批评、评判；
4. 额外识别用户当下情绪；
5. 仅输出标准JSON字符串，**不要输出任何额外解释、前缀、后缀、markdown格式**。

JSON固定字段要求：
- observation: 客观观察（描述事实，不带评判）
- feeling: 内心感受（情绪）
- need: 背后的需求/期待
- request: 具体、正向的请求
- emotion: 简短概括整体情绪（如生气、委屈、烦躁等）
"""


async def convert_to_nvc(raw_text: str, emotion_hint: str | None = None) -> dict:
    """
    将原始文本转换为 NVC 四要素结构化数据
    """
    # 前置校验：过滤空文本
    raw_text = raw_text.strip()
    if not raw_text:
        return {
            "observation": "",
            "feeling": "",
            "need": "",
            "request": "",
            "emotion": "未知"
        }

    user_content = raw_text
    if emotion_hint:
        user_content = f"【情绪提示】{emotion_hint}\n【原文】{raw_text}"

    messages = [
        {"role": "system", "content": NVC_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    response = await chat_completion(messages, temperature=0.3, max_tokens=512)
    response = response.strip()

    # 尝试解析 JSON
    try:
        result = json.loads(response)
        return {
            "observation": result.get("observation", "").strip(),
            "feeling": result.get("feeling", "").strip(),
            "need": result.get("need", "").strip(),
            "request": result.get("request", "").strip(),  # 统一默认空字符串
            "emotion": result.get("emotion", "未知").strip(),
        }
    except json.JSONDecodeError as e:
        # 日志增加原始返回内容，方便排错
        logger.warning(f"NVC 输出非标准JSON，错误信息：{e}，模型原始返回：{response}")
        # 兜底：把原文放入观察字段，保证接口正常返回
        return {
            "observation": raw_text,
            "feeling": "",
            "need": "",
            "request": "",
            "emotion": "未知",
        }