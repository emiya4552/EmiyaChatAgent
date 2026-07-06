# -*- coding: utf-8 -*-
"""情感感知核心：情绪 + 好感度合并评估（assess_turn，ADR-0019）+ 加权滑动平均状态机。"""
import json
import logging
import re
from dataclasses import dataclass

from app.config import settings
from app.services.llm_service import call_deepseek_non_stream
from app.utils.token_counter import count_tokens

logger = logging.getLogger(__name__)

# 10 种情绪标签
EMOTION_LABELS = [
    "开心", "平静", "低落", "焦虑", "愤怒",
    "兴奋", "疲惫", "困惑", "感动", "思念",
]


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


@dataclass
class TurnAssessment:
    """一次互动的合并感知结果（ADR-0019）：用户情绪 + 角色好感变化。"""

    emotion: str
    intensity: int
    confidence: float
    triggers: list[str]
    affinity_delta: int
    affinity_reason: str


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """把文本裁到 max_tokens 以内（token 估算，比字符截断更贴合成本）。"""
    if max_tokens <= 0 or not text:
        return ""
    if count_tokens(text) <= max_tokens:
        return text
    # 先按 token 比例砍字符，再收敛几步（count_tokens 是估算，不追求精确）
    approx = max(1, int(len(text) * max_tokens / max(count_tokens(text), 1)))
    t = text[:approx]
    while t and count_tokens(t) > max_tokens:
        t = t[: max(1, int(len(t) * 0.9))]
    return t


def _build_budgeted_dialogue(
    messages: list[tuple[str, str]], max_tokens: int, max_messages: int
) -> str:
    """从最新往回按 token 预算累加最近对话，**最新消息优先**。

    Args:
        messages: [(role, content), ...]，时间正序（旧 → 新）。
        max_tokens: 总 token 预算。
        max_messages: 防呆上限（token 预算才是主控）。

    单条最新消息超预算时截断入选，保证本轮用户消息一定进得来。
    """
    picked: list[str] = []
    used = 0
    for role, content in reversed(messages):  # 最新优先
        if len(picked) >= max_messages:
            break
        line = f"{'用户' if role == 'user' else '你'}：{(content or '').strip()}"
        t = count_tokens(line)
        if used + t <= max_tokens:
            picked.append(line)
            used += t
        else:
            remaining = max_tokens - used
            if not picked and remaining > 0:  # 最新一条即便超预算也截断入选
                picked.append(_truncate_to_tokens(line, remaining))
            break
    return "\n".join(reversed(picked))  # 还原为时间正序


async def assess_turn(
    *,
    recent_messages: list[tuple[str, str]],
    assistant_reply: str,
    persona_name: str,
    persona_desc: str,
    scenario: str,
    affinity_score: float,
    assess_affinity: bool,
) -> TurnAssessment:
    """ADR-0019：一次 LLM 调用同时判断用户情绪 + 角色好感变化（上下文感知）。

    合并了旧的 `analyze_emotion`（裸情绪、无上下文）与 `assess_affinity`（好感度）。
    输入按 token 预算裁剪（config `EMOTION_*_MAX_TOKENS`），近期对话最新优先。

    人设可缺失（高版本卡人设常在世界书里、`personality`/`background` 都可能空）：
    此时不写"性格：（无）"，而是提示模型从角色自己的这条回复推断态度——回复即角色行为。
    `assess_affinity=False`（无 AI 角色）时只判情绪，好感 delta 记 0。

    Args:
        recent_messages: [(role, content)]，时间正序；最后一条"用户"消息是情绪判断对象。
        assistant_reply: 角色本轮刚写的回复（尚未落库，故单独传）。
        persona_desc: 角色描述（personality 或 background 回退 + 说话风格），可为空。
        affinity_score: 当前好感度分数，作为角色视角判断的基线。

    Returns:
        TurnAssessment；解析失败一律返回默认值（不阻断主流程）。
    """
    dialogue = _build_budgeted_dialogue(
        recent_messages,
        settings.EMOTION_CONTEXT_MAX_TOKENS,
        settings.EMOTION_CONTEXT_MAX_MESSAGES,
    ) or "（无）"
    reply = _truncate_to_tokens(assistant_reply or "", settings.EMOTION_REPLY_MAX_TOKENS)

    persona_parts: list[str] = []
    if persona_name:
        persona_parts.append(f"名字：{persona_name}")
    if persona_desc.strip():
        persona_parts.append(f"人设：{persona_desc.strip()}")
    if scenario.strip():
        persona_parts.append(f"场景：{scenario.strip()}")
    persona_block = _truncate_to_tokens(
        "\n".join(persona_parts), settings.EMOTION_PERSONA_MAX_TOKENS
    )
    has_persona = bool(persona_block.strip())

    labels = "/".join(EMOTION_LABELS)

    if has_persona:
        persona_section = f"你的角色设定：\n{persona_block}\n\n"
        infer_note = ""
    else:
        persona_section = ""
        infer_note = (
            "（没有显式人设——你的性格与态度请从下面『你刚写的回复』里推断，"
            "这条回复就是你这个角色的真实行为）\n\n"
        )

    affinity_block = ""
    affinity_json = ""
    if assess_affinity:
        affinity_json = (
            ',\n  "affinity_delta": 1,'
            '\n  "affinity_reason": "以第一人称简述原因（15字内）"'
        )
        affinity_block = f"""
当前你们的好感度：{round(affinity_score, 1)}/100

同时判断"这次互动让你（作为这个角色）对用户的感受变化"：
- affinity_delta 为 -3~+3 的整数（正=更愿意交流，负=下降，0=无变化）
- 升好感：用户真诚分享 / 尊重你的边界 / 投入追问；降好感：反复踩雷 / 全程敷衍 / 冷漠攻击
- affinity_reason 用角色第一人称，15 字内
- 情绪分析与好感评估是两项独立判断，别互相污染
"""

    prompt = f"""你在扮演一个 AI 角色。请基于{"人设与" if has_persona else ""}最近对话完成分析，仅返回一个 JSON，不要任何其他内容。

{persona_section}{infer_note}最近对话（最后一条"用户"消息是本轮要判断情绪的对象）：
{dialogue}

你（作为角色）刚回复了：
{reply or "（无）"}
{affinity_block}
返回格式（仅 JSON）：
{{
  "emotion": "低落",
  "intensity": 7,
  "confidence": 0.85,
  "triggers": ["考试"]{affinity_json}
}}

要求：
- emotion 必须从这些标签里选一个：{labels}
- intensity 是 0-10 的整数，confidence 是 0-1 之间的浮点数
- 情绪要结合上下文判断，而不是只看字面（反讽、口是心非要能识别）
- 只返回 JSON，不要其他文字"""

    default = TurnAssessment("平静", 5, 0.3, [], 0, "")
    try:
        response = await call_deepseek_non_stream(
            messages=[{"role": "user", "content": prompt}],
            temperature=settings.EMOTION_TEMPERATURE,
            max_tokens=settings.EMOTION_ASSESS_MAX_TOKENS,
        )
    except Exception as e:
        logger.warning(f"assess_turn LLM 调用失败，使用默认值: {e}")
        return default

    data = _safe_parse_emotion_json(response)

    emotion = data.get("emotion")
    if emotion not in EMOTION_LABELS:
        emotion = "平静"
    intensity = data.get("intensity", 5)
    if not isinstance(intensity, (int, float)) or intensity < 0 or intensity > 10:
        intensity = 5
    confidence = data.get("confidence", 0.3)
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        confidence = 0.3
    triggers = data.get("triggers", [])
    if not isinstance(triggers, list):
        triggers = []

    delta = 0
    reason = ""
    if assess_affinity:
        raw_delta = data.get("affinity_delta", 0)
        if not isinstance(raw_delta, (int, float)):
            raw_delta = 0
        delta = max(-3, min(3, int(raw_delta)))
        raw_reason = data.get("affinity_reason", "")
        reason = raw_reason if isinstance(raw_reason, str) else ""
        if not reason:
            reason = "互动中" if delta == 0 else ("好感上升" if delta > 0 else "好感下降")

    logger.info(
        f"assess_turn: emotion={emotion}({int(intensity)}), "
        f"affinity_delta={delta:+d} ({'on' if assess_affinity else 'off'})"
    )
    return TurnAssessment(
        emotion=emotion,
        intensity=int(intensity),
        confidence=float(confidence),
        triggers=triggers,
        affinity_delta=delta,
        affinity_reason=reason,
    )


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
