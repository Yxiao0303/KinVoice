"""
AI 档案编写服务 —— 调用千问 API，从对话中提取用户画像并写入 Markdown 文件。

两段式档案：
- stable.md：不变信息（性别、生日、家庭成员等）—— 手动触发，全量重写
- dynamic.md：可变信息（情绪状态、关注话题等）—— 对话结束后自动更新

解耦设计：
- 提取源通过 MessageSource 接口注入，不直接依赖 chat 模块
- 文件读写独立于数据库，零 ORM 依赖
"""
import time
from pathlib import Path
from app.config import settings
from app.services.llm_service import call_llm
from app.utils.logger import logger

# 档案存放根目录
PROFILES_DIR = Path("data/profiles")

# ── 内存缓存：避免每次请求都读磁盘 ──
# 结构：{user_id: {"stable": str, "dynamic": str, "ts": float}}
_profile_cache: dict[str, dict] = {}
_CACHE_TTL = 60  # 缓存有效期（秒）

# ── 固定档案的 system prompt ──
STABLE_SYSTEM_PROMPT = """你是一个专业的用户画像分析师。你的任务是根据对话记录，提取用户不会轻易改变的固定信息。

请从对话中提取以下信息，并用 Markdown 格式输出一份用户档案：

## 基本信息
- 性别（如果对话中有暗示）
- 年龄/年龄段
- 职业/身份

## 家庭成员
- 列出对话中提到的家庭成员及其关系（如：父亲、母亲、配偶、子女等）
- 如果有提到生日、年龄等信息也记录下来

## 重要背景
- 用户提到的重要人生事件、居住城市、文化背景等

规则：
1. 只写对话中明确提到或强烈暗示的信息，不要编造
2. 不确定的信息标注「（推测）」或直接不写
3. 用中文输出，格式整洁
4. 如果对话中没有相关信息，该章节写「暂无信息」
"""

# ── 动态档案的 system prompt ──
DYNAMIC_SYSTEM_PROMPT = """你是一个敏锐的心理观察者。你的任务是根据用户今天的对话记录，更新一份动态心理画像。

请用 Markdown 格式输出以下内容：

## 当前情绪状态
- 今天的整体情绪基调（如：焦虑、平静、开心、疲惫等）
- 情绪变化趋势（如果可观察）

## 近期关注话题
- 今天提到的主要话题和关注点（列举 3-5 个）

## 沟通风格观察
- 用户的表达习惯（如：直接/含蓄、理性/感性）
- 是否有特定的沟通模式

## 潜在需求
- 从对话中推断用户可能未被满足的需求

## 关键对话片段
- 摘录 1-3 句最能体现用户当前状态的原文

规则：
1. 只基于今天的对话进行分析，不要编造
2. 保持温和、共情的语气
3. 如果今天对话很少，可以简短输出，但不要留空章节
4. 标注推测的内容用「（可能）」
"""


def _get_profile_path(user_id: str, profile_type: str) -> Path:
    """获取档案文件路径，自动创建目录"""
    dir_path = PROFILES_DIR / user_id
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path / f"{profile_type}.md"


def _read_existing(file_path: Path) -> str:
    """读取已有档案内容，不存在则返回空字符串"""
    if file_path.exists():
        return file_path.read_text(encoding="utf-8")
    return ""


async def _call_ai_write(
    system_prompt: str,
    user_prompt: str,
    existing_content: str = "",
) -> str:
    """
    调用千问 API 生成/更新档案内容。

    Args:
        system_prompt: 系统提示词（定义输出格式）
        user_prompt: 用户提示词（包含对话记录）
        existing_content: 已有的档案内容（用于增量参考）

    Returns:
        AI 生成的 Markdown 文本
    """
    messages = [
        {"role": "system", "content": system_prompt},
    ]

    # 如果有已有内容，让 AI 参考
    if existing_content.strip():
        messages.append({
            "role": "user",
            "content": f"以下是已有的档案内容，请参考：\n\n{existing_content}\n\n---\n\n{user_prompt}",
        })
    else:
        messages.append({"role": "user", "content": user_prompt})

    try:
        result = await call_llm(messages)
        return result.strip()
    except Exception as e:
        logger.error(f"AI 档案编写失败: {e}")
        raise


async def update_dynamic_profile(
    user_id: str,
    messages: list[dict],
) -> dict:
    """
    从今日对话中提取信息，更新动态档案。

    Args:
        user_id: 用户标识
        messages: [{role, content, created_at}, ...] 今日对话消息

    Returns:
        {ok, profile_type, path, content_preview, messages_used}
    """
    if not messages:
        logger.info(f"用户 {user_id} 今日无对话，跳过动态档案更新")
        return {
            "ok": True,
            "profile_type": "dynamic",
            "path": str(_get_profile_path(user_id, "dynamic")),
            "content_preview": "（今日无对话，跳过更新）",
            "messages_used": 0,
        }

    # 构造对话记录文本
    conversation_text = _format_messages(messages)
    user_prompt = f"以下是用户今天的对话记录，请据此更新动态心理画像：\n\n{conversation_text}"

    # 读取已有动态档案作为参考
    existing = _read_existing(_get_profile_path(user_id, "dynamic"))

    # 调用 AI
    new_content = await _call_ai_write(DYNAMIC_SYSTEM_PROMPT, user_prompt, existing)

    # 写入文件
    file_path = _get_profile_path(user_id, "dynamic")
    file_path.write_text(new_content, encoding="utf-8")
    _invalidate_profile_cache(user_id)
    logger.info(f"动态档案已更新: {file_path}")

    return {
        "ok": True,
        "profile_type": "dynamic",
        "path": str(file_path),
        "content_preview": new_content[:200],
        "messages_used": len(messages),
    }


async def update_stable_profile(
    user_id: str,
    messages: list[dict],
) -> dict:
    """
    从对话记录中提取固定信息，更新固定档案（全量重写）。

    Args:
        user_id: 用户标识
        messages: [{role, content, created_at}, ...] 对话消息

    Returns:
        {ok, profile_type, path, content_preview, messages_used}
    """
    if not messages:
        logger.info(f"用户 {user_id} 无对话记录，跳过固定档案更新")
        return {
            "ok": False,
            "profile_type": "stable",
            "path": str(_get_profile_path(user_id, "stable")),
            "content_preview": "（无对话记录，无法生成档案）",
            "messages_used": 0,
        }

    # 构造对话记录文本（取最近 200 条，避免 token 超限）
    recent = messages[-200:] if len(messages) > 200 else messages
    conversation_text = _format_messages(recent)
    user_prompt = f"以下是用户的对话记录，请从中提取固定信息生成档案：\n\n{conversation_text}"

    # 固定档案不参考已有内容，每次全量重写
    new_content = await _call_ai_write(STABLE_SYSTEM_PROMPT, user_prompt)

    # 写入文件
    file_path = _get_profile_path(user_id, "stable")
    file_path.write_text(new_content, encoding="utf-8")
    _invalidate_profile_cache(user_id)
    logger.info(f"固定档案已更新: {file_path}")

    return {
        "ok": True,
        "profile_type": "stable",
        "path": str(file_path),
        "content_preview": new_content[:200],
        "messages_used": len(recent),
    }


def read_profiles(user_id: str) -> dict:
    """
    读取用户的两份档案（带内存缓存，60 秒内重复读取不碰磁盘）。

    Returns:
        {user_id, stable: str, dynamic: str}
    """
    now = time.time()
    cached = _profile_cache.get(user_id)
    if cached and (now - cached.get("ts", 0)) < _CACHE_TTL:
        return {
            "user_id": user_id,
            "stable": cached.get("stable", ""),
            "dynamic": cached.get("dynamic", ""),
        }

    stable = _read_existing(_get_profile_path(user_id, "stable"))
    dynamic = _read_existing(_get_profile_path(user_id, "dynamic"))
    _profile_cache[user_id] = {"stable": stable, "dynamic": dynamic, "ts": now}
    return {
        "user_id": user_id,
        "stable": stable,
        "dynamic": dynamic,
    }


def _invalidate_profile_cache(user_id: str) -> None:
    """写入档案后清除对应缓存，保证下次读取为最新内容"""
    _profile_cache.pop(user_id, None)


def _format_messages(messages: list[dict]) -> str:
    """将消息列表格式化为可读的对话文本"""
    lines = []
    for m in messages:
        role_label = "用户" if m["role"] == "user" else "AI"
        lines.append(f"**{role_label}**：{m['content']}")
    return "\n\n".join(lines)
