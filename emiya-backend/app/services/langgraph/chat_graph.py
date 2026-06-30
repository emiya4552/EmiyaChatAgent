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
    node_analyze_emotion,
    node_assess_relationship,
    node_build_prompt,
    node_resolve_constraints,
    node_resolve_profile_section,
    node_retrieve_memories,
)

_compiled_analysis_graph: StateGraph | None = None


def build_analysis_graph() -> StateGraph:
    """构建分析流水线（7 个节点），不含回复生成和后处理。"""
    global _compiled_analysis_graph
    if _compiled_analysis_graph is not None:
        return _compiled_analysis_graph

    workflow = StateGraph(ChatState)

    workflow.add_node("analyze_emotion", node_analyze_emotion)
    workflow.add_node("retrieve_memories", node_retrieve_memories)
    workflow.add_node("activate_worldbook", node_activate_worldbook)
    workflow.add_node("resolve_profile_section", node_resolve_profile_section)
    workflow.add_node("resolve_constraints", node_resolve_constraints)
    workflow.add_node("assess_relationship", node_assess_relationship)
    workflow.add_node("build_prompt", node_build_prompt)

    workflow.add_edge(START, "analyze_emotion")
    workflow.add_edge("analyze_emotion", "retrieve_memories")
    workflow.add_edge("retrieve_memories", "activate_worldbook")
    workflow.add_edge("activate_worldbook", "resolve_profile_section")
    workflow.add_edge("resolve_profile_section", "resolve_constraints")
    workflow.add_edge("resolve_constraints", "assess_relationship")
    workflow.add_edge("assess_relationship", "build_prompt")
    workflow.add_edge("build_prompt", END)

    _compiled_analysis_graph = workflow.compile()
    return _compiled_analysis_graph
