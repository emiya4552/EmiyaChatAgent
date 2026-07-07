# -*- coding: utf-8 -*-
"""LangGraph 聊天流水线 — State Graph 定义。

仅含 7 个节点的"分析流水线"。回复生成由 `chat_service` 直接调
`call_deepseek_stream` 实现真正逐 token 流式；后处理在流式完成后由
`chat_service` 手动调用 `node_post_process`。
"""
from langgraph.graph import StateGraph, START, END
from app.services.langgraph.state import ChatState
from app.services.langgraph.nodes import (
    node_activate_worldbook,
    node_assess_relationship,
    node_build_prompt,
    node_resolve_constraints,
    node_resolve_profile_section,
    node_retrieve_memories,
)

_compiled_analysis_graph: StateGraph | None = None


def build_analysis_graph() -> StateGraph:
    """构建分析流水线（6 个节点），不含回复生成和后处理。

    ADR-0019：情绪分析已从分析图移除（原为首节点），合并进 node_post_process 的
    assess_turn（与好感度评估合一、上下文感知）。图现在从 retrieve_memories 起。
    """
    global _compiled_analysis_graph
    if _compiled_analysis_graph is not None:
        return _compiled_analysis_graph

    workflow = StateGraph(ChatState)

    workflow.add_node("retrieve_memories", node_retrieve_memories)
    workflow.add_node("activate_worldbook", node_activate_worldbook)
    workflow.add_node("resolve_profile_section", node_resolve_profile_section)
    workflow.add_node("resolve_constraints", node_resolve_constraints)
    workflow.add_node("assess_relationship", node_assess_relationship)
    workflow.add_node("build_prompt", node_build_prompt)

    # 检索记忆 -> 激活世界书 -> 解析人设片段 -> 解析约束 -> 好感度评估 -> 构建 prompt
    workflow.add_edge(START, "retrieve_memories")
    workflow.add_edge("retrieve_memories", "activate_worldbook")
    workflow.add_edge("activate_worldbook", "resolve_profile_section")
    workflow.add_edge("resolve_profile_section", "resolve_constraints")
    workflow.add_edge("resolve_constraints", "assess_relationship")
    workflow.add_edge("assess_relationship", "build_prompt")
    workflow.add_edge("build_prompt", END)

    _compiled_analysis_graph = workflow.compile()
    return _compiled_analysis_graph
