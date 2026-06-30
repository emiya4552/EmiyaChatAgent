# -*- coding: utf-8 -*-
"""情绪引擎核心：prompt-based 情绪分析 + 加权滑动平均状态机。"""
import json
import logging
import re

from app.config import settings
from app.schemas.emotion import EmotionAnalysisResult
from app.services.llm_service import call_deepseek_non_stream

logger = logging.getLogger(__name__)

# 10 种情绪标签
EMOTION_LABELS = [
    "开心", "平静", "低落", "焦虑", "愤怒",
    "兴奋", "疲惫", "困惑", "感动", "思念",
]

# 每种情绪的 emoji 映射
EMOTION_EMOJI = {
    "开心": "😊", "平静": "😌", "低落": "😔",
    "焦虑": "😰", "愤怒": "😤", "兴奋": "🤩",
    "疲惫": "😴", "困惑": "🤔", "感动": "🥹", "思念": "💭",
}

# 情绪分析 prompt 模板
EMOTION_ANALYSIS_PROMPT = """请分析以下用户消息的情绪，仅返回 JSON，不要有任何其他内容：

用户消息：{user_message}

返回格式：
{{
  "emotion": "低落",
  "intensity": 7,
  "confidence": 0.85,
  "triggers": ["考试", "没考好"]
}}

情绪标签必须从以下选择：{emotion_labels}

注意：
- emotion 必须是列表中的值，不能是其他
- intensity 是 0-10 的整数
- confidence 是 0-1 之间的浮点数
- triggers 是触发该情绪的关键词列表，可以为空数组"""


def _safe_parse_emotion_json(text: str) -> dict:
    """容错解析情绪分析的 JSON 返回。

    Args:
        text: LLM 返回的原始文本。

    Returns:
        解析后的字典，包含 emotion/intensity/confidence/triggers。
    """
    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 尝试提取 JSON 块
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # 3. 返回默认值
    return {"emotion": "平静", "intensity": 5, "confidence": 0.3, "triggers": []}


async def analyze_emotion(user_message: str) -> EmotionAnalysisResult:
    """调用 DeepSeek API 分析用户消息的情绪。

    Args:
        user_message: 用户输入的消息文本。

    Returns:
        EmotionAnalysisResult 对象，解析失败时返回默认值。
    """
    prompt = EMOTION_ANALYSIS_PROMPT.format(
        user_message=user_message,
        emotion_labels="/".join(EMOTION_LABELS),
    )

    messages = [{"role": "user", "content": prompt}]

    try:
        response = await call_deepseek_non_stream(
            messages=messages,
            temperature=settings.EMOTION_TEMPERATURE,
            max_tokens=settings.EMOTION_MAX_TOKENS,
        )
        logger.debug(f"情绪分析原始响应: {response[:200]}")

        data = _safe_parse_emotion_json(response)

        # 验证 emotion 标签
        if data.get("emotion") not in EMOTION_LABELS:
            data["emotion"] = "平静"

        # 验证 intensity 范围
        intensity = data.get("intensity", 5)
        if not isinstance(intensity, (int, float)) or intensity < 0 or intensity > 10:
            data["intensity"] = 5

        # 验证 confidence 范围
        confidence = data.get("confidence", 0.3)
        if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
            data["confidence"] = 0.3

        return EmotionAnalysisResult(
            emotion=data["emotion"],
            intensity=int(data["intensity"]),
            confidence=float(data["confidence"]),
            triggers=data.get("triggers", []),
        )
    except Exception as e:
        logger.error(f"情绪分析失败，使用默认值。错误: {e}")
        return EmotionAnalysisResult(
            emotion="平静",
            intensity=5,
            confidence=0.3,
            triggers=[],
        )


AFFINITY_EVAL_PROMPT = """你正在扮演一个 AI 角色。请以这个角色的第一人称视角，判断当前这次互动让你对用户的感受发生了什么变化。

你的角色设定：
- 性格：{personality}
- 说话风格：{speaking_style}

当前对话：
- 用户说：{user_message}
- 用户的情绪状态：{emotion}（强度 {intensity}/10）
- 你（作为这个角色）回复了：{assistant_reply}

当前你们的好感度：{affinity_score}/100

请判断这次互动让你对这个用户的感受：
返回 JSON：{{"affinity_delta": N, "affinity_reason": "以第一人称简述原因（15字以内）"}}
N 为正表示好感上升（用户让你更愿意交流了），为负表示下降，0 表示无变化。
N 必须在 -3 到 +3 之间（含）。

判断标准 - 升好感（+）：
- 用户真诚地分享个人经历、情感或脆弱面
- 用户尊重你表达的边界和偏好
- 用户对对话投入、追问、展现真实兴趣
- 用户积极回应你的关怀与引导

判断标准 - 降好感（-）：
- 用户反复踩你已明确表达过的不适话题
- 用户全程敷衍（"嗯""哦""随便"）
- 用户对你的善意表露冷漠、攻击或嘲讽

注意：
- 情绪分析和好感评估是两项独立任务
- 你的回复约束是回复行为规范，不是用户好感评判标准
- 只返回 JSON，不要其他内容"""


async def assess_affinity(
    user_message: str,
    emotion: str,
    intensity: int,
    assistant_reply: str,
    personality: str,
    speaking_style: str,
    affinity_score: float,
) -> tuple[int, str]:
    """调用 LLM 评估本轮对话的好感度变动。

    Args:
        user_message: 用户消息
        emotion: 用户情绪标签
        intensity: 情绪强度 0-10
        assistant_reply: AI 角色本轮的回复
        personality: persona 的性格描述
        speaking_style: persona 的说话风格
        affinity_score: 当前好感度分数

    Returns:
        (delta, reason): delta 范围 [-3, 3]，reason 为自然语言简述
    """
    prompt = AFFINITY_EVAL_PROMPT.format(
        personality=personality[:300],
        speaking_style=speaking_style[:200],
        user_message=user_message[:500],
        emotion=emotion,
        intensity=intensity,
        assistant_reply=assistant_reply[:500],
        affinity_score=round(affinity_score, 1),
    )

    try:
        response = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=100,
        )
        data = _safe_parse_emotion_json(response)
        delta = data.get("affinity_delta", 0)
        reason = data.get("affinity_reason", "")

        # 硬 clamp ±3
        if not isinstance(delta, (int, float)):
            delta = 0
        delta = max(-3, min(3, int(delta)))

        if not isinstance(reason, str) or not reason:
            reason = "互动中" if delta == 0 else ("好感上升" if delta > 0 else "好感下降")

        logger.info(f"亲和评估: delta={delta:+d}, reason={reason}")
        return delta, reason

    except Exception as e:
        logger.warning(f"亲和评估失败，使用默认值: {e}")
        return 0, ""


class MoodStateMachine:
    """情绪状态机 — 使用加权滑动平均防止情绪跳变。"""

    def __init__(self):
        self.current_mood: str | None = None
        self.current_intensity: int = 5
        self.recent_emotions: list[dict] = []  # 最近 5 条情绪记录

    def update(
        self, new_emotion: str, new_intensity: int, new_confidence: float
    ) -> tuple[str, int]:
        """根据新情绪更新状态机。

        Args:
            new_emotion: 新的情绪标签。
            new_intensity: 新的情绪强度。
            new_confidence: 新的置信度。

        Returns:
            (updated_mood, updated_intensity) 元组。
        """
        self.recent_emotions.append({
            "emotion": new_emotion,
            "confidence": new_confidence,
        })
        # 只保留最近 5 条
        if len(self.recent_emotions) > 5:
            self.recent_emotions = self.recent_emotions[-5:]

        # 首次调用：直接设置
        if self.current_mood is None:
            self.current_mood = new_emotion
            self.current_intensity = new_intensity
            return self.current_mood, self.current_intensity

        # 规则 1：同情绪 → 加权平均强度
        if new_emotion == self.current_mood:
            self.current_intensity = round(new_intensity * 0.7 + self.current_intensity * 0.3)
            return self.current_mood, self.current_intensity

        # 规则 5：连续 3 条同一新情绪且置信度均 > 0.5 → 强制切换
        same_count = sum(
            1 for e in self.recent_emotions[-3:]
            if e["emotion"] == new_emotion and e["confidence"] > 0.5
        )
        if same_count >= 3:
            self.current_mood = new_emotion
            self.current_intensity = round(new_intensity * 0.6)
            return self.current_mood, self.current_intensity

        # 规则 2：不同情绪 → 按置信度处理
        if new_confidence > 0.8:
            # 高置信度 → 情绪切换
            self.current_mood = new_emotion
            self.current_intensity = round(new_intensity * 0.6)
        elif new_confidence >= 0.5:
            # 中置信度 → 不切换情绪，强度降低
            self.current_intensity = round(self.current_intensity * 0.5)
        # else 低置信度 → 忽略，保持旧状态

        return self.current_mood, self.current_intensity
