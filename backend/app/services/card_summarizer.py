"""
对话总结 → 传承笔记 服务（精简版）
从多轮对话中提取值得传承的家庭记忆，生成 Markdown 笔记
"""
import json
from app.services.llm_service import call_llm
from app.utils.logger import logger

SUMMARIZE_SYSTEM_PROMPT = """你是一个家庭记忆整理师。你的任务是从家庭对话中提取值得传承的记忆，整理成笔记。

## 笔记格式
每篇笔记包含：
- title：简短标题（不超过30字）
- content：Markdown 格式的笔记正文，包含关键信息、感悟或经验

## 判断标准
值得记录的内容包括：
- 家庭故事、人生经验
- 菜谱、生活技巧
- 家训、价值观
- 重要决定和感悟
- 有趣的回忆

## 输出格式
返回纯 JSON 数组，不要加任何解释：
[{"title":"妈妈的拿手菜-红烧肉","content":"## 食材\\n- 五花肉 500g\\n...\\n\\n## 步骤\\n1. ..."}, ...]

## 规则
- 如果对话没有实质性内容（纯寒暄），返回空数组 []
- 一次最多返回 3 篇笔记
- title 控制在 30 字以内
- content 用 Markdown 格式，清晰结构化
"""


async def summarize_to_notes(history: list[dict]) -> list[dict]:
    """
    从对话历史中提取传承笔记。

    Args:
        history: 对话历史 [{role, content}, ...]

    Returns:
        list[dict]: [{title, content}, ...]
    """
    dialogue = "\n".join(
        [f"{'用户' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in history]
    )

    user_prompt = f"""## 对话记录
{dialogue}

请从以上对话中提取值得传承的家庭记忆笔记。"""

    try:
        messages = [
            {"role": "system", "content": SUMMARIZE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        raw = await call_llm(messages)
        logger.info(f"笔记总结 LLM 返回: {raw[:200]}...")

        # 清洗 JSON
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        result = json.loads(raw)
        if not isinstance(result, list):
            logger.warning(f"LLM 返回格式异常: {type(result)}")
            return []
        return result

    except json.JSONDecodeError as e:
        logger.error(f"LLM 返回 JSON 解析失败: {e}")
        return []
    except Exception as e:
        logger.error(f"笔记总结失败: {e}")
        return []
