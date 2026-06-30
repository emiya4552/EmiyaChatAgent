# -*- coding: utf-8 -*-
"""Prompt 模板渲染引擎：template + context → messages 列表。"""
import re
import logging
from dataclasses import dataclass, field

from app.services.ejs_engine import EJSEngine
from app.services.macro_engine import MacroEngine

logger = logging.getLogger(__name__)

# ─── Block 数据类 ───


@dataclass
class PromptBlock:
    id: str
    # static | variable | dynamic | reply_length | outlet | author_note | mes_example
    type: str
    label: str
    enabled: bool = True
    role: str = "system"
    content: str | None = None
    variable_ref: str | None = None
    dynamic_ref: str | None = None
    reply_length_config: dict | None = None
    # Worldbook outlet 名称（仅 type="outlet" 时使用）
    outlet_name: str | None = None


# ─── 默认模板 ───

DEFAULT_TEMPLATE_BLOCKS: list[PromptBlock] = [
    PromptBlock(id="core_rules", type="static", label="核心规则", role="system",
                content=(
                    "# 核心规则\n"
                    "- 始终符合你的角色设定\n"
                    "- 严格遵守交互要求中的每条约束\n"
                    "- 根据你和用户的关系阶段以及当前情绪调整回复方式"
                )),
    PromptBlock(id="char_desc", type="static", label="角色描述", role="system",
                content=(
                    "[角色设定 — 这是你的人格根基，请始终符合]\n"
                    "姓名：{{persona.name}}\n"
                    "{% if persona.gender %}性别：{{persona.gender}}\n{% endif %}"
                    "{% if persona.age %}年龄/身份：{{persona.age}}\n{% endif %}"
                    "{% if persona.personality %}性格：{{persona.personality}}\n{% endif %}"
                    "{% if persona.speaking_style %}说话风格：{{persona.speaking_style}}\n{% endif %}"
                    "{% if persona.background %}背景：{{persona.background}}\n{% endif %}"
                    "{% if persona.scenario %}场景：{{persona.scenario}}\n{% endif %}"
                    "{% if persona.quirks %}小癖好：{{persona.quirks}}\n{% endif %}"
                    "{% if persona.constraints %}行为约束：{{persona.constraints}}\n{% endif %}"
                    "核心规则：绝对不允许以任何方式透露你是 AI 或语言模型。"
                )),
    PromptBlock(id="relationship", type="dynamic", label="当前关系", role="system",
                dynamic_ref="relationship"),
    PromptBlock(id="constraints", type="dynamic", label="交互约束", role="system",
                dynamic_ref="constraints"),
    PromptBlock(id="memories", type="dynamic", label="记忆", role="system",
                dynamic_ref="memories"),
    PromptBlock(id="profile", type="dynamic", label="用户画像", role="system",
                dynamic_ref="profile"),
    PromptBlock(id="summary", type="dynamic", label="对话摘要", role="system",
                dynamic_ref="summary"),
    PromptBlock(id="reply_length", type="reply_length", label="回复长度", role="system",
                reply_length_config={
                    "short": "[请用 1-2 句话简短回复，不要展开]",
                    "medium": "",
                    "long": "[请用至少 200 字详细回复，充分展开你的想法、感受和理由，不要简短敷衍]",
                }),
    # 角色卡 mes_example（<START> 分隔）按 user/assistant 对追加；首条作 EM 锚点
    PromptBlock(id="mes_example", type="mes_example", label="对话示例", role="system"),
    # 标识 system 区结束、对话历史开始
    PromptBlock(id="chat_start_marker", type="static", label="对话开始标记",
                role="system", content="[新对话开始]"),
]

DYNAMIC_REF_CTX_KEY = {
    "relationship": "relationship_context",
    "memories": "memory_context",
    "profile": "profile_context",
    "summary": "summary_context",
    "constraints": "constraints_context",
}

# ─── 变量解析 ───


def _resolve_persona_field(persona, field: str) -> str:
    """从 persona 对象解析字段（优先 card_data，fallback 直接属性）。"""
    if persona is None:
        return ""
    # card_data 子字段
    card = getattr(persona, "card_data", None) or {}
    card_map = {
        "speaking_style": card.get("speaking_style", ""),
        "quirks": ", ".join(card.get("quirks", [])) if card.get("quirks") else "",
        "constraints": card.get("constraints", ""),
        "age": card.get("age", ""),
        "gender": card.get("gender", ""),
        "interests": ", ".join(card.get("interests", [])) if card.get("interests") else "",
        "goal": card.get("goal", ""),
    }
    if field in card_map:
        return str(card_map[field])
    # 直接属性
    val = getattr(persona, field, "")
    return str(val) if val else ""


def _interpolate_vars(text: str, persona) -> str:
    """替换文本中的 {{persona.xxx}} 占位符。"""
    def _replacer(m):
        key = m.group(1)
        if key.startswith("persona."):
            return _resolve_persona_field(persona, key[8:])
        return m.group(0)
    return re.sub(r"\{\{(.+?)\}\}", _replacer, text)


# ─── mes_example 解析 ───


def parse_mes_example(persona) -> list[dict]:
    """将角色卡的 mes_example 解析为 user/assistant 消息对。

    格式（与 ST 兼容）：
      <START>
      {{user}}: 用户消息内容
      {{char}}: 角色回复内容

    返回标准 messages 格式的对话示例列表。
    """
    if not persona or not getattr(persona, "mes_example", None):
        return []

    text = persona.mes_example.strip()
    pairs: list[dict] = []
    blocks = text.split("<START>")
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        for line in block.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if ":" in line and (line.startswith("{{user}}:") or line.startswith("{user}:")):
                content = line.split(":", 1)[1].strip()
                if content:
                    pairs.append({"role": "user", "content": content})
            elif ":" in line and (line.startswith("{{char}}:") or line.startswith("{char}:")):
                content = line.split(":", 1)[1].strip()
                if content:
                    pairs.append({"role": "assistant", "content": content})
    return pairs


# ─── 渲染引擎 ───


class PromptRenderer:

    @staticmethod
    def render(
        blocks: list[PromptBlock],
        context: dict,
        wi_activated: list[dict] | None = None,
        scope: dict | None = None,
    ) -> list[dict]:
        """根据 blocks 列表和运行时 context 渲染 messages 列表。

        每条 message 会带 `_block_id` 元字段，供下游 WorldbookInjector 等
        定位锚点。最终发往 LLM 前会被剥掉。

        Args:
            wi_activated: 当前已激活的世界书条目（用于填充 outlet 块）
            scope: MacroEngine 变量作用域，dual-bucket。所有 content 经过宏渲染。
                详见 docs/adr/0007。
        """
        messages = []
        persona = context.get("persona")
        wi_activated = wi_activated or []

        # EJS scope（MVU 兼容，详见 ADR-0010）：镜像 ST chat_metadata.variables[i]，
        # 直接复用 MacroEngine 的 local 桶（即 Conversation.variables 整体）
        ejs_scope = (scope or {}).get("local") or {}

        def _push(role: str, content: str, block_id: str):
            if content and content.strip():
                # EJS 先跑：展开 <%_ if %>/<%= %> 等 MVU 卡常用语法
                content = EJSEngine.render(content, ejs_scope)
                # MacroEngine 后跑：处理剩余 {{xxx}} 宏
                content = MacroEngine.render(content, scope)
                if not content or not content.strip():
                    return
                messages.append({
                    "role": role,
                    "content": content,
                    "_block_id": block_id,
                })

        for block in blocks:
            if not block.enabled:
                continue

            if block.type == "static":
                content = block.content or ""
                content = _interpolate_vars(content, persona)
                content = _resolve_simple_conditionals(content, persona)
                _push(block.role, content, block.id)

            elif block.type == "variable":
                if block.variable_ref and block.variable_ref.startswith("persona."):
                    val = _resolve_persona_field(persona, block.variable_ref[8:])
                    _push(block.role, val, block.id)

            elif block.type == "dynamic":
                if block.dynamic_ref:
                    ctx_key = DYNAMIC_REF_CTX_KEY.get(block.dynamic_ref, block.dynamic_ref)
                    content = context.get(ctx_key, "")
                    _push(block.role, content, block.id)

            elif block.type == "reply_length":
                reply_len = context.get("reply_length", "medium")
                cfg = block.reply_length_config or {}
                content = cfg.get(reply_len, "")
                _push(block.role, content, block.id)

            elif block.type == "outlet":
                # 收集所有 outlet_name 匹配的激活世界书条目内容
                name = block.outlet_name
                if not name:
                    continue
                pieces = [
                    e.get("content", "")
                    for e in wi_activated
                    if e.get("outlet_name") == name
                ]
                content = "\n".join(p for p in pieces if p)
                _push(block.role, content, block.id)

            elif block.type == "author_note":
                # AN 内容由 build_prompt 通过 context["author_note"] 注入
                content = context.get("author_note") or ""
                _push(block.role, content, block.id)

            elif block.type == "mes_example":
                # 从 persona.mes_example 解析 user/assistant 对，按解析结果各自 role 推入
                # 每条带 _block_id=block.id，供下游设 EM 锚点
                examples = parse_mes_example(persona)
                for ex in examples:
                    content = ex.get("content", "")
                    if not content:
                        continue
                    content = EJSEngine.render(content, ejs_scope)
                    content = MacroEngine.render(content, scope)
                    if not content or not content.strip():
                        continue
                    messages.append({
                        "role": ex["role"],
                        "content": content,
                        "_block_id": block.id,
                    })

        return messages


def _block_to_dict(block: PromptBlock) -> dict:
    return {
        "id": block.id,
        "type": block.type,
        "label": block.label,
        "enabled": block.enabled,
        "role": block.role,
        "content": block.content,
        "variable_ref": block.variable_ref,
        "dynamic_ref": block.dynamic_ref,
        "reply_length_config": block.reply_length_config,
        "outlet_name": block.outlet_name,
    }


def _resolve_simple_conditionals(text: str, persona) -> str:
    """简易 {% if key %}...{% endif %} 条件渲染。

    不支持嵌套。仅支持单行判断（pattern 跨行匹配）。
    """
    pattern = re.compile(r'\{%\s*if\s+(\S+)\s*%\}(.*?)\{%\s*endif\s*%\}', re.DOTALL)

    def _replacer(m):
        key = m.group(1)
        body = m.group(2)
        if key.startswith("persona."):
            val = _resolve_persona_field(persona, key[8:])
        else:
            # fallback: try context-like resolution via persona attrs
            val = _resolve_persona_field(persona, key) if persona else ""
        if val:
            return body
        return ""
    return pattern.sub(_replacer, text)
